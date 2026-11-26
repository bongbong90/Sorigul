"""Server-authorized provisioning on the inference session's owned kernel only.

No local ML imports, caller commands, URLs, retry or alternate model/device.
The default authorizer refuses all provisioning. Launch gates are independent.
"""

from enum import Enum
import threading

from src.services.colab_inference_worker import MODEL_REVISION, PACKAGES, MODEL_REPOSITORY
from src.services.colab_jupyter_inference import InferenceCode, InferenceError


class ProvisionState(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    CHECKING = "CHECKING"
    INSTALL_REQUIRED = "INSTALL_REQUIRED"
    INSTALLING = "INSTALLING"
    MODEL_DOWNLOAD_REQUIRED = "MODEL_DOWNLOAD_REQUIRED"
    DOWNLOADING = "DOWNLOADING"
    VERIFYING = "VERIFYING"
    READY = "READY"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    STATE_UNCERTAIN = "STATE_UNCERTAIN"


MESSAGES = {
    state.value: message for state, message in (
        (ProvisionState.NOT_STARTED, "전사 환경 준비를 기다리고 있습니다."),
        (ProvisionState.CHECKING, "GPU와 전사 환경을 확인하고 있습니다."),
        (ProvisionState.INSTALL_REQUIRED, "전사 패키지 설치가 필요합니다."),
        (ProvisionState.INSTALLING, "전사 패키지를 준비하고 있습니다."),
        (ProvisionState.MODEL_DOWNLOAD_REQUIRED, "모델 다운로드가 필요합니다."),
        (ProvisionState.DOWNLOADING, "모델을 준비하고 있습니다."),
        (ProvisionState.VERIFYING, "전사 환경을 검증하고 있습니다."),
        (ProvisionState.READY, "전사 환경 준비가 완료되었습니다."),
        (ProvisionState.FAILED, "전사 환경 준비에 실패했습니다."),
        (ProvisionState.CANCELLED, "전사 환경 준비를 중지했습니다."),
        (ProvisionState.STATE_UNCERTAIN, "원격 준비 상태를 확인할 수 없습니다."),
    )
}


class FailClosedProvisioningAuthorizer:
    def authorize(self, owned_runtime):
        return False


class ColabModelProvisioner:
    def __init__(self, inference, *, authorizer=None, emit=lambda event: None):
        self.inference = inference
        self.authorizer = authorizer if authorizer is not None else FailClosedProvisioningAuthorizer()
        self.emit = emit
        self.state = ProvisionState.NOT_STARTED
        self.events = []
        self._lock = threading.Lock()

    def _state(self, state):
        self.state = state
        event = dict(kind="colab_provisioning", state=state.value, message=MESSAGES[state.value])
        self.events.append(event)
        self.emit(dict(event))

    def run(self):
        if not self._lock.acquire(blocking=False):
            raise InferenceError(InferenceCode.DUPLICATE_EXECUTION)
        try:
            if self.state is not ProvisionState.NOT_STARTED:
                raise InferenceError(InferenceCode.DUPLICATE_EXECUTION)
            try:
                self.inference._check_cancel()
                owned = self.inference._runtime.get_owned_runtime()
                # Identity/account binding is checked by _BoundRuntime on every step.
                if self.authorizer.authorize(owned) is not True:
                    raise InferenceError(InferenceCode.PROVISIONING_NOT_APPROVED)
                self._state(ProvisionState.CHECKING)
                report = self.inference.provision_step("CHECK", authorizer=self.authorizer)
                if report["missing"]:
                    self._state(ProvisionState.INSTALL_REQUIRED)
                    self._state(ProvisionState.INSTALLING)
                    # Recheck authorization immediately before each remote mutation.
                    self._authorize()
                    report = self.inference.provision_step("INSTALL", authorizer=self.authorizer)
                if not report["model_cached"]:
                    self._state(ProvisionState.MODEL_DOWNLOAD_REQUIRED)
                    self._state(ProvisionState.DOWNLOADING)
                    self._authorize()
                    self.inference.provision_step("DOWNLOAD", authorizer=self.authorizer)
                self._state(ProvisionState.VERIFYING)
                report = self.inference.provision_step("VERIFY", authorizer=self.authorizer)
                if report["missing"] or not report["model_cached"]:
                    raise InferenceError(InferenceCode.MODEL_LOAD_FAILED)
                self._state(ProvisionState.READY)
                return report
            except Exception as exc:
                code = exc.code if isinstance(exc, InferenceError) else InferenceCode.STATE_UNCERTAIN
                uncertain = self.inference.provisioning_uncertain
                state = (ProvisionState.STATE_UNCERTAIN if uncertain or code is InferenceCode.STATE_UNCERTAIN
                         else ProvisionState.CANCELLED if code is InferenceCode.CANCELLED
                         else ProvisionState.FAILED)
                self._state(state)
                raise InferenceError(InferenceCode.STATE_UNCERTAIN if uncertain else code) from None
        finally:
            self._lock.release()

    def _authorize(self):
        self.inference._check_cancel()
        owned = self.inference._runtime.get_owned_runtime()
        if self.authorizer.authorize(owned) is not True:
            raise InferenceError(InferenceCode.PROVISIONING_NOT_APPROVED)


# This source is sent exclusively through the fixed owned-kernel executor.
# subprocess output, package exceptions and Hub credentials never cross its receipt.
PROVISION_SOURCE = r'''
def _sorigul_provision(params):
    import contextlib
    import importlib
    import importlib.metadata
    import logging
    import os
    import pathlib
    import subprocess
    import sys

    class Discard:
        def write(self, text):
            return len(text)
        def flush(self):
            pass

    receipt = dict(execution_id=params["execution_id"], action=params["action"],
                   revision=params["revision"], missing=[], model_cached=False,
                   error_code=None, device="cuda", diagnostic=None)
    previous = logging.root.manager.disable
    error, stage, detail = "GPU_UNAVAILABLE", "gpu_check", None

    import re

    def clean(text):
        # ASCII only, no ids/URLs/secret-shaped runs, bounded.
        text = "".join(ch if 32 <= ord(ch) < 127 else " " for ch in str(text))
        text = re.sub(r"https?://\S+", "<url>", text)
        text = re.sub(r"[0-9a-fA-F]{24,}", "<id>", text)
        text = re.sub(r"[A-Za-z0-9_\-]{40,}", "<redacted>", text)
        text = re.sub(r"(?i)\S*(?:token|secret|passw|credential|bearer|api.?key|hf_[A-Za-z0-9])\S*", "<redacted>", text)
        return " ".join(text.split())[-240:]

    def preload_cublas12():
        # dlopen("libcublas.so.12") by ctranslate2 then resolves to this copy.
        import ctypes
        import site
        try:
            ctypes.CDLL("libcublas.so.12", mode=ctypes.RTLD_GLOBAL)
            return
        except OSError:
            pass
        for root in site.getsitepackages():
            try:
                ctypes.CDLL(root + "/nvidia/cublas/lib/libcublas.so.12", mode=ctypes.RTLD_GLOBAL)
                return
            except OSError:
                continue
        raise OSError("libcublas.so.12 not loadable (nvidia-cublas-cu12 missing)")
    try:
        logging.disable(logging.CRITICAL)
        with contextlib.redirect_stdout(Discard()), contextlib.redirect_stderr(Discard()):
            if sys.version_info < (3, 10):
                receipt["error_code"] = "PYTHON_UNSUPPORTED"
                return receipt
            # Driver/device check does not depend on the yet-uninstalled ML packages.
            gpu = subprocess.run(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True, timeout=15)
            if not gpu.stdout.strip():
                receipt["error_code"] = error
                return receipt

            def missing():
                result = []
                for package, version in params["packages"].items():
                    try:
                        valid = importlib.metadata.version(package) == version
                    except importlib.metadata.PackageNotFoundError:
                        valid = False
                    if not valid:
                        result.append(package)
                return result

            needed = missing()
            if params["action"] == "INSTALL" and needed:
                error, stage = "PACKAGE_INSTALL_FAILED", "package_install"
                pip_env = {key: value for key, value in os.environ.items() if not key.startswith("PIP_")}
                pip_env["PIP_CONFIG_FILE"] = os.devnull
                result = subprocess.run([
                    sys.executable, "-m", "pip", "--isolated", "--disable-pip-version-check",
                    "--no-input", "install", "--only-binary=:all:", "--index-url", "https://pypi.org/simple",
                    *[p + "==" + params["packages"][p] for p in needed]],
                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=1200,
                    env=pip_env)
                if result.returncode != 0:
                    detail = "pip exit %d: %s" % (result.returncode,
                                                  result.stderr.decode("utf-8", "replace")[-600:])
                    raise RuntimeError("pip failed")
                importlib.invalidate_caches()
                # Loaded mismatched native modules cannot safely be upgraded in place.
                # The controller only provisions before any ML imports in this session.
                needed = missing()
                if needed:
                    receipt["error_code"] = "PACKAGE_VERSION_MISMATCH"
                    return receipt
            receipt["missing"] = needed
            if needed:
                if params["action"] != "CHECK":
                    receipt["error_code"] = "PACKAGE_VERSION_MISMATCH"
                return receipt

            error, stage = "PACKAGE_IMPORT_FAILED", "package_import"
            import ctranslate2
            import faster_whisper
            import huggingface_hub
            from faster_whisper import WhisperModel
            from huggingface_hub import snapshot_download
            if any(getattr(module, "__version__", None) != params["packages"][name]
                   for name, module in (("ctranslate2", ctranslate2),
                       ("faster-whisper", faster_whisper), ("huggingface-hub", huggingface_hub))):
                receipt["error_code"] = "PACKAGE_IMPORT_FAILED"
                return receipt
            error, stage = "GPU_UNAVAILABLE", "gpu_check"
            if ctranslate2.get_cuda_device_count() < 1:
                receipt["error_code"] = error
                return receipt

            required = ("model.bin", "config.json", "tokenizer.json", "preprocessor_config.json")
            def cache(download=False):
                try:
                    path = pathlib.Path(snapshot_download(
                        params["repository"], revision=params["revision"],
                        endpoint="https://huggingface.co", token=False,
                        local_files_only=not download,
                        **({"force_download": True, "allow_patterns": list(required) + ["vocabulary.json"]}
                           if download else {})))
                except Exception:
                    if download:
                        raise
                    return None
                if path.name != params["revision"]:
                    raise ValueError("MODEL_REVISION_MISMATCH")
                if (not path.is_dir() or any(not (path / name).is_file()
                        or (path / name).stat().st_size == 0 for name in required)
                        or any(path.rglob("*.incomplete"))):
                    return None
                return path

            error, stage = "MODEL_REVISION_MISMATCH", "model_cache"
            path = cache()
            if params["action"] == "DOWNLOAD" and path is None:
                error = "MODEL_DOWNLOAD_FAILED"
                path = cache(download=True)
            receipt["model_cached"] = path is not None
            if params["action"] in ("DOWNLOAD", "VERIFY") and path is None:
                receipt["error_code"] = "MODEL_CACHE_INCOMPLETE"
                return receipt
            if params["action"] == "VERIFY":
                error, stage = "CUDA_FAILED", "cublas_load"
                preload_cublas12()
                error, stage = "MODEL_LOAD_FAILED", "model_init"
                # Loading validates corrupt contents beyond file names/lengths.
                model = WhisperModel(str(path), device="cuda", compute_type="float16")
                # A load alone does not prove GPU compute: cuBLAS/cuDNN are only
                # dlopened at the first kernel. One encoder pass over 30 s of
                # silence exercises GEMM + conv on the GPU (no audio, no decode).
                error, stage = "CUDA_FAILED", "gpu_verify"
                import numpy as np
                # Same shapes/calls faster-whisper 1.2.1 uses: (1, n_mels, nb_max_frames).
                frames = model.feature_extractor.nb_max_frames
                features = np.zeros((1, model.model.n_mels, frames), dtype=np.float32)
                model.model.encode(ctranslate2.StorageView.from_array(np.ascontiguousarray(features)),
                                   to_cpu=True)
                globals().setdefault("_sorigul_models_v1", {})[
                    (params["revision"], "cuda", "float16")] = model
            return receipt
    except Exception as exc:
        receipt["error_code"] = error
        try:
            receipt["diagnostic"] = {"stage": stage, "exception": clean(type(exc).__name__),
                                     "message": clean(detail if detail else exc), "runtime": None}
        except Exception:
            receipt["diagnostic"] = None
        return receipt
    finally:
        logging.disable(previous)
'''


def build_provisioning_code(execution_id, action):
    import re
    if (not isinstance(execution_id, str) or not re.fullmatch(r"[0-9a-f]{32}", execution_id)
            or action not in ("CHECK", "INSTALL", "DOWNLOAD", "VERIFY")):
        raise ValueError("INVALID_INPUT")
    params = dict(execution_id=execution_id, action=action, packages=dict(PACKAGES),
                  repository=MODEL_REPOSITORY, revision=MODEL_REVISION)
    return PROVISION_SOURCE + "\n_sorigul_receipt = _sorigul_provision(" + repr(params) + ")\n"
