"""Trusted, self-contained remote worker. Imported locally without ML imports.

Provisioning (installed only by the separate authorized provisioner): faster-whisper==1.2.1,
ctranslate2==4.6.0, huggingface-hub==0.36.0. No pip or external scripts.
Model: Systran/faster-whisper-large-v3 at the immutable revision below.
References: https://github.com/SYSTRAN/faster-whisper/tree/v1.2.1
https://huggingface.co/Systran/faster-whisper-large-v3/commits/main
Only an explicit allow_model_download=True permits a pinned model download.
The default requires a pre-provisioned cache. Real Colab support NOT VERIFIED.
"""

import re


PACKAGES = {"faster-whisper": "1.2.1", "ctranslate2": "4.6.0", "huggingface-hub": "0.36.0"}
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
        pass

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
                "gpu_error": None, "silence": False, "payload": None, "duration_seconds": None}
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
                except Exception:
                    if params.get("require_cuda"):
                        raise Failure("CUDA_FAILED") from None
                    if not has_cuda:
                        raise Failure("MODEL_LOAD_FAILED") from None
                    envelope["gpu_error"] = "CUDA_FAILED"
                    device, compute = "cpu", "int8"
                    key = (params["revision"], device, compute)
                    try:
                        if key not in cache:
                            cache[key] = WhisperModel(model_path, device=device, compute_type=compute)
                    except Exception:
                        raise Failure("MODEL_LOAD_FAILED") from None
                envelope.update(device=device, compute_type=compute)
                try:
                    segments, info = cache[key].transcribe(
                        handle, language="ko", task="transcribe", temperature=0,
                        beam_size=5, best_of=5, patience=1.0,
                        condition_on_previous_text=False,
                    )
                    rows, text_bytes = [], 0
                    duration = info.duration
                    if not math.isfinite(duration) or not 0 < duration <= 301:
                        raise Failure("RESULT_INVALID")
                    envelope["duration_seconds"] = duration
                    for s in segments:  # exhaust lazy generator before completion
                        if (not math.isfinite(s.start) or not math.isfinite(s.end)
                                or not 0 <= s.start <= s.end <= duration + 0.1
                                or not isinstance(s.text, str) or not s.text.strip()):
                            raise Failure("RESULT_INVALID")
                        text_bytes += len(s.text.encode("utf-8"))
                        if len(rows) >= 2000 or text_bytes > 12000:
                            raise Failure("RESULT_INVALID")
                        rows.append({"start": s.start, "end": s.end, "text": s.text})
                    check_input()  # never publish a result after input mutation
                    envelope["payload"] = {"text": "".join(s["text"] for s in rows),
                                           "language": "ko", "segments": rows}
                    envelope["silence"] = not rows
                except Failure:
                    raise
                except Exception:
                    # Never retry a started decode, including lazy CUDA failure.
                    raise Failure("CUDA_FAILED" if device == "cuda" else "KERNEL_EXECUTION_FAILED") from None
    except Failure as exc:
        envelope["error_code"] = str(exc)
        envelope["payload"] = None
    except Exception:
        envelope["error_code"] = "KERNEL_EXECUTION_FAILED"
        envelope["payload"] = None
    finally:
        logging.disable(previous_logging)
    raw = json.dumps(envelope, ensure_ascii=False, allow_nan=False).encode("utf-8")
    if len(raw) > 32768:
        envelope.update(error_code="RESULT_INVALID", payload=None, silence=False)
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
