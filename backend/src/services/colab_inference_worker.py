"""Trusted, self-contained remote worker. Imported locally without ML imports.

Provisioning (installed only by the separate authorized provisioner): faster-whisper==1.2.1,
ctranslate2==4.6.0, huggingface-hub==0.36.0, nvidia-cublas-cu12==12.4.5.8. No pip or external scripts.
Model: Systran/faster-whisper-large-v3 at the immutable revision below.
References: https://github.com/SYSTRAN/faster-whisper/tree/v1.2.1
https://huggingface.co/Systran/faster-whisper-large-v3/commits/main
Only an explicit allow_model_download=True permits a pinned model download.
The default requires a pre-provisioned cache. Real Colab support NOT VERIFIED.
"""

import re


# ctranslate2 4.6.0 is a CUDA 12.2 build that dlopens "libcublas.so.12" (wheel
# ELF, CUDA_DYNAMIC_LOADING=ON; cudart static, cuDNN 9.1 bundled). Colab images
# can be CUDA 13 only, so cuBLAS 12 comes from this pinned wheel (12.x >= 12.2,
# no Python deps; its .so needs only glibc + libcublasLt via $ORIGIN). It does
# not replace the image's CUDA 13 / PyTorch libraries.
PACKAGES = {"faster-whisper": "1.2.1", "ctranslate2": "4.6.0", "huggingface-hub": "0.36.0",
            "nvidia-cublas-cu12": "12.4.5.8"}
MODEL_REPOSITORY = "Systran/faster-whisper-large-v3"
MODEL_REVISION = "edaa852ec7e145841d8ffdb056a99866b5f0a478"
MAX_RESULT_BYTES = 32 * 1024  # base64 + Contents envelope fits PHASE 03's 64 KiB


WORKER_SOURCE = r'''
def _sorigul_prepare(params):
    import contextlib
    import importlib.metadata
    import logging
    import pathlib
    class Discard:
        def write(self, text):
            return len(text)
        def flush(self):
            pass
    receipt = dict(execution_id=params["execution_id"], ready=False,
                   error_code="MODEL_INSTALL_REQUIRED", device=None,
                   compute_type=None, revision=params["revision"])
    previous = logging.root.manager.disable
    try:
        logging.disable(logging.CRITICAL)
        with contextlib.redirect_stdout(Discard()), contextlib.redirect_stderr(Discard()):
            for package, version in params["packages"].items():
                if importlib.metadata.version(package) != version:
                    return receipt
            import ctranslate2
            import faster_whisper
            from huggingface_hub import snapshot_download
            receipt["error_code"] = "MODEL_LOAD_FAILED"
            cached = pathlib.Path(snapshot_download(
                params["repository"], revision=params["revision"], local_files_only=True))
            required = ("model.bin", "config.json", "tokenizer.json", "preprocessor_config.json")
            if cached.name != params["revision"] or any(
                    not (cached / name).is_file() or (cached / name).stat().st_size == 0
                    for name in required):
                return receipt
            try:
                cuda = ctranslate2.get_cuda_device_count() > 0
            except Exception:
                cuda = False
            receipt.update(ready=True, error_code=None, device="cuda" if cuda else "cpu",
                           compute_type="float16" if cuda else "int8")
            return receipt
    except Exception:
        return receipt
    finally:
        logging.disable(previous)

def _sorigul_worker(params):
    # Keep all imports inside: this function's source is sent to the kernel.
    import contextlib
    import hashlib
    import importlib.metadata
    import json
    import logging
    import math
    import os
    import pathlib
    import re
    import stat

    class Discard:
        def write(self, text):
            return len(text)

        def flush(self):
            pass

    class Failure(Exception):
        def __init__(self, code, stage=None, cause=None):
            super().__init__(code)
            self.stage, self.cause = stage, cause

    def clean(text):
        # ASCII only (drops any transcript), no ids/URLs/secret-shaped runs.
        text = "".join(ch if 32 <= ord(ch) < 127 else " " for ch in str(text))
        text = re.sub(r"https?://\S+", "<url>", text)
        text = re.sub(r"[0-9a-fA-F]{24,}", "<id>", text)
        text = re.sub(r"[A-Za-z0-9_\-]{40,}", "<redacted>", text)
        text = re.sub(r"(?i)\S*(?:token|secret|passw|credential|bearer|api.?key|hf_[A-Za-z0-9])\S*", "<redacted>", text)
        return " ".join(text.split())[:240]

    def probe():
        # Read-only facts about this runtime's CUDA stack. No GPU work.
        facts = {}
        try:
            import ctranslate2 as ct2
            facts["ctranslate2"] = clean(getattr(ct2, "__version__", "?"))
            facts["cuda_devices"] = int(ct2.get_cuda_device_count())
            facts["cuda_compute_types"] = sorted(clean(t) for t in ct2.get_supported_compute_types("cuda"))
        except Exception as exc:
            facts["ctranslate2_error"] = clean(type(exc).__name__ + ": " + str(exc))
        import ctypes
        libs = {}
        for name in ("libcuda.so.1", "libcudart.so.12", "libcublas.so.12", "libcublasLt.so.12",
                     "libcudnn.so.9", "libcudnn_ops.so.9", "libcudnn_cnn.so.9",
                     "libcudnn.so.8", "libcudnn_ops_infer.so.8", "libcublas.so.11"):
            try:
                ctypes.CDLL(name)
                libs[name] = True
            except OSError:
                libs[name] = False
        facts["libs"] = libs
        try:
            facts["cuda_lib_files"] = cuda_lib_files()
        except Exception:
            facts["cuda_lib_files"] = None
        for module in ("av", "numpy", "torch"):
            try:
                facts[module] = clean(importlib.metadata.version(module))
            except Exception:
                facts[module] = None
        try:
            import torch
            facts["torch_cuda"] = clean(torch.version.cuda)
            facts["torch_cudnn"] = torch.backends.cudnn.version()
        except Exception as exc:
            facts["torch_error"] = clean(type(exc).__name__)
        return facts

    def cuda_lib_files():
        # Names only of CUDA runtime/cuBLAS/cuDNN files present on this image.
        import glob
        import site
        roots = ["/usr/local/cuda*/lib64", "/usr/local/cuda*/targets/*/lib",
                 "/usr/lib/x86_64-linux-gnu", "/usr/lib64-nvidia"]
        try:
            roots += [p + "/nvidia/*/lib" for p in site.getsitepackages()]
        except Exception:
            pass
        found = set()
        for root in roots:
            for pattern in ("libcublas*.so*", "libcudart.so*", "libcudnn.so*"):
                for path in glob.glob(root + "/" + pattern):
                    parts = path.split("/")
                    found.add(clean(parts[-3] + "/" + parts[-1] if "nvidia" in parts else parts[-1]))
        return sorted(found)[:32]

    def preload_cuda12():
        # ctranslate2 4.6.0 (CUDA 12 build) dlopens cuBLAS 12 lazily at the first
        # GPU compute. Colab images may ship CUDA 13 only (live run 6: torch
        # cu130, libcublas.so.12 not on the loader path). Preload an existing
        # CUDA 12 copy if one is present. No install, no package change.
        import ctypes
        import glob
        import site
        dirs = sorted(glob.glob("/usr/local/cuda-12*/lib64")) + ["/usr/local/cuda/lib64"]
        try:
            dirs += [p + "/nvidia/" + sub_dir + "/lib" for p in site.getsitepackages()
                     for sub_dir in ("cuda_runtime", "cublas")]
        except Exception:
            pass
        for name in ("libcudart.so.12", "libcublasLt.so.12", "libcublas.so.12"):
            try:
                ctypes.CDLL(name, mode=ctypes.RTLD_GLOBAL)
                continue
            except OSError:
                pass
            for directory in dirs:
                try:
                    ctypes.CDLL(directory + "/" + name, mode=ctypes.RTLD_GLOBAL)
                    break
                except OSError:
                    continue

    def diagnose(stage, cause):
        return {"stage": stage, "exception": clean(type(cause).__name__) if cause else None,
                "message": clean(cause) if cause else None, "runtime": probe()}

    def decode_audio(handle):
        # faster-whisper 1.2.1 decode_audio(), minus av.open(metadata_errors=...),
        # which PyAV >= 15 rejects (Colab ships av 19: live run 6, #60).
        # Same s16 mono 16 kHz resample, invalid-frame skip and grouping.
        import gc
        import io
        import itertools
        import av
        import numpy as np
        resampler = av.audio.resampler.AudioResampler(format="s16", layout="mono", rate=16000)
        raw, dtype = io.BytesIO(), None

        def valid(frames):
            iterator = iter(frames)
            while True:
                try:
                    yield next(iterator)
                except StopIteration:
                    break
                except av.error.InvalidDataError:
                    continue

        def grouped(frames, num_samples=500000):
            fifo = av.audio.fifo.AudioFifo()
            for frame in frames:
                frame.pts = None
                fifo.write(frame)
                if fifo.samples >= num_samples:
                    yield fifo.read()
            if fifo.samples > 0:
                yield fifo.read()

        with av.open(handle, mode="r") as container:
            for frame in itertools.chain(grouped(valid(container.decode(audio=0))), [None]):
                for out in resampler.resample(frame):
                    array = out.to_ndarray()
                    dtype = array.dtype
                    raw.write(array)
        del resampler
        gc.collect()
        return np.frombuffer(raw.getbuffer(), dtype=dtype).astype(np.float32) / 32768.0

    run, execution, index = params["run_id"], params["execution_id"], params["index"]
    if (not re.fullmatch(r"[0-9a-f]{32}", run)
            or not re.fullmatch(r"[0-9a-f]{32}", execution)
            or type(index) is not int or not 0 <= index <= 99999):
        raise ValueError("INVALID_INPUT")
    root = pathlib.Path("sorigul-transfer") / run
    source = root / f"chunk-{index:05d}.mp3"
    output_dir = root / ("inference-" + execution)
    # Never follow a user-controlled symlink or reuse another execution's dir.
    if any(p.is_symlink() for p in (root.parent, root, source)):
        raise ValueError("INVALID_INPUT")
    output_dir.mkdir()  # exclusive; failure gives no cleanup ownership receipt
    envelope = {"execution_id": execution, "run_id": run, "index": index,
                "input_sha256": params["sha256"], "complete": True,
                "error_code": None, "device": None, "compute_type": None,
                "gpu_error": None, "silence": False, "payload": None, "duration_seconds": None,
                "diagnostic": None}
    previous_logging = logging.root.manager.disable
    try:
        logging.disable(logging.CRITICAL)
        with contextlib.redirect_stdout(Discard()), contextlib.redirect_stderr(Discard()):
            try:
                handle = source.open("rb")
            except OSError:
                raise Failure("INPUT_MISSING") from None
            with handle:
                def check_input():
                    info = os.fstat(handle.fileno())
                    if not stat.S_ISREG(info.st_mode) or info.st_size != params["size"]:
                        raise Failure("INPUT_INTEGRITY_MISMATCH")
                    handle.seek(0)
                    digest = hashlib.sha256()
                    for block in iter(lambda: handle.read(65536), b""):
                        digest.update(block)
                    if digest.hexdigest() != params["sha256"]:
                        raise Failure("INPUT_INTEGRITY_MISMATCH")
                    handle.seek(0)
                check_input()  # hash before imports, downloads or model execution
                try:
                    for package, version in params["packages"].items():
                        if importlib.metadata.version(package) != version:
                            raise ValueError
                    import ctranslate2
                    from faster_whisper import WhisperModel
                    from huggingface_hub import snapshot_download
                except Exception:
                    raise Failure("MODEL_INSTALL_REQUIRED") from None
                try:
                    model_path = snapshot_download(
                        params["repository"], revision=params["revision"],
                        local_files_only=not params["allow_model_download"],
                        allow_patterns=["config.json", "model.bin", "tokenizer.json",
                                        "vocabulary.json", "preprocessor_config.json"],
                    )
                except Exception:
                    raise Failure("MODEL_LOAD_FAILED") from None
                try:
                    has_cuda = ctranslate2.get_cuda_device_count() > 0
                    if not has_cuda:
                        envelope["gpu_error"] = "GPU_UNAVAILABLE"
                except Exception:
                    has_cuda = False
                    envelope["gpu_error"] = "CUDA_FAILED"
                device = "cuda" if has_cuda else "cpu"
                if has_cuda:
                    try:
                        preload_cuda12()
                    except Exception:
                        pass  # the decode itself reports any missing library
                if params.get("require_cuda") and not has_cuda:
                    raise Failure("GPU_UNAVAILABLE") from None
                compute = "float16" if has_cuda else "int8"
                # Cache supports reuse if a future separately reviewed controller
                # keeps this kernel. File sessions retain it; one-shot runs clean it.
                cache = globals().setdefault("_sorigul_models_v1", {})
                key = (params["revision"], device, compute)
                try:
                    if key not in cache:
                        cache[key] = WhisperModel(model_path, device=device, compute_type=compute)
                except Exception as exc:
                    if params.get("require_cuda"):
                        raise Failure("CUDA_FAILED", "model_init", exc) from None
                    if not has_cuda:
                        raise Failure("MODEL_LOAD_FAILED", "model_init", exc) from None
                    envelope["gpu_error"] = "CUDA_FAILED"
                    device, compute = "cpu", "int8"
                    key = (params["revision"], device, compute)
                    try:
                        if key not in cache:
                            cache[key] = WhisperModel(model_path, device=device, compute_type=compute)
                    except Exception as exc:
                        raise Failure("MODEL_LOAD_FAILED", "model_init", exc) from None
                envelope.update(device=device, compute_type=compute)
                failed = "CUDA_FAILED" if device == "cuda" else "KERNEL_EXECUTION_FAILED"
                stage = "audio_decode"
                try:
                    audio = decode_audio(handle)
                except Exception as exc:
                    raise Failure("KERNEL_EXECUTION_FAILED", stage, exc) from None
                try:
                    stage = "inference_start"
                    segments, info = cache[key].transcribe(
                        audio, language="ko", task="transcribe", temperature=0,
                        beam_size=5, best_of=5, patience=1.0,
                        condition_on_previous_text=False,
                    )
                    rows, text_bytes = [], 0
                    duration = info.duration
                    if not math.isfinite(duration) or not 0 < duration <= 301:
                        raise Failure("RESULT_INVALID", "result")
                    envelope["duration_seconds"] = duration
                    stage = "inference"
                    for s in segments:  # exhaust lazy generator before completion
                        if (not math.isfinite(s.start) or not math.isfinite(s.end)
                                or not 0 <= s.start <= s.end <= duration + 0.1
                                or not isinstance(s.text, str) or not s.text.strip()):
                            raise Failure("RESULT_INVALID", "result")
                        text_bytes += len(s.text.encode("utf-8"))
                        if len(rows) >= 2000 or text_bytes > 12000:
                            raise Failure("RESULT_INVALID", "result")
                        rows.append({"start": s.start, "end": s.end, "text": s.text})
                    stage = "result"
                    check_input()  # never publish a result after input mutation
                    envelope["payload"] = {"text": "".join(s["text"] for s in rows),
                                           "language": "ko", "segments": rows}
                    envelope["silence"] = not rows
                except Failure:
                    raise
                except Exception as exc:
                    # Never retry a started decode, including lazy CUDA failure.
                    raise Failure(failed, stage, exc) from None
    except Failure as exc:
        envelope["error_code"] = str(exc)
        envelope["payload"] = None
        if exc.stage is not None:
            try:
                envelope["diagnostic"] = diagnose(exc.stage, exc.cause)
            except Exception:
                envelope["diagnostic"] = {"stage": exc.stage, "exception": None,
                                          "message": None, "runtime": None}
    except Exception as exc:
        envelope["error_code"] = "KERNEL_EXECUTION_FAILED"
        envelope["payload"] = None
        try:
            envelope["diagnostic"] = diagnose("worker", exc)
        except Exception:
            pass
    finally:
        logging.disable(previous_logging)
    raw = json.dumps(envelope, ensure_ascii=False, allow_nan=False).encode("utf-8")
    if len(raw) > 32768:
        envelope.update(error_code="RESULT_INVALID", payload=None, silence=False, diagnostic=None)
        raw = json.dumps(envelope).encode("utf-8")
    with (output_dir / "result.tmp").open("xb") as result:
        result.write(raw)
    os.replace(output_dir / "result.tmp", output_dir / "result.json")
    return {"execution_id": execution, "owned": True}
'''


def build_worker_code(*, run_id, execution_id, index, size, sha256, allow_model_download=False, require_cuda=False):
    """Only validated scalars are serialized; no caller code/path/URL accepted."""
    if (not isinstance(run_id, str) or not re.fullmatch(r"[0-9a-f]{32}", run_id)
            or not isinstance(execution_id, str) or not re.fullmatch(r"[0-9a-f]{32}", execution_id)
            or type(index) is not int or not 0 <= index <= 99999
            or type(size) is not int or not 0 < size <= 256 * 1024 * 1024
            or not isinstance(sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", sha256)
            or type(allow_model_download) is not bool or type(require_cuda) is not bool):
        raise ValueError("INVALID_INPUT")
    params = dict(run_id=run_id, execution_id=execution_id, index=index, size=size,
                  sha256=sha256, allow_model_download=allow_model_download,
                  packages=PACKAGES, repository=MODEL_REPOSITORY, revision=MODEL_REVISION)
    params["require_cuda"] = require_cuda
    return (WORKER_SOURCE +
            "\n_sorigul_receipt = _sorigul_worker(" + repr(params) + ")\n")


def build_preparation_code(execution_id):
    if not isinstance(execution_id, str) or not re.fullmatch(r"[0-9a-f]{32}", execution_id):
        raise ValueError("INVALID_INPUT")
    params = dict(execution_id=execution_id, packages=PACKAGES,
                  repository=MODEL_REPOSITORY, revision=MODEL_REVISION)
    return WORKER_SOURCE + "\n_sorigul_receipt = _sorigul_prepare(" + repr(params) + ")\n"
