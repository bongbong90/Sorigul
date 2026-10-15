import importlib
import threading
from pathlib import Path
from typing import Any, Callable, Optional

from src.domain.transcription import (
    CancellationToken,
    EngineError,
    ErrorCategory,
    EventCallback,
    ProgressCallback,
    TranscriptionResult,
)


class LocalWhisperEngine:
    MODEL_NAME = "medium"
    TRANSCRIBE_OPTIONS = {
        "language": "ko",
        "task": "transcribe",
        "temperature": 0,
        "beam_size": 5,
        "best_of": 5,
        "patience": 1,
        "condition_on_previous_text": False,
    }

    def __init__(
        self,
        whisper_loader: Optional[Callable[[], Any]] = None,
        torch_loader: Optional[Callable[[], Any]] = None,
    ):
        self._whisper_loader = whisper_loader or (lambda: importlib.import_module("whisper"))
        self._torch_loader = torch_loader or (lambda: importlib.import_module("torch"))
        self._model = None
        self._device: Optional[str] = None
        self._model_lock = threading.Lock()
        self._transcribe_lock = threading.Lock()

    def _runtime_modules(self):
        try:
            return self._whisper_loader(), self._torch_loader()
        except Exception as exc:
            raise EngineError(
                "LOCAL_RUNTIME_MISSING",
                ErrorCategory.RUNTIME,
                "Local Whisper 실행 환경이 설치되어 있지 않습니다.",
                technical_detail=str(exc),
                fatal=True,
            ) from exc

    def _load_model(self, event_callback: EventCallback):
        if self._model is not None:
            return self._model, self._device

        with self._model_lock:
            if self._model is not None:
                return self._model, self._device

            whisper, torch = self._runtime_modules()
            event_callback("info", "Local", "Local model loading")
            cuda_available = bool(torch.cuda.is_available())
            if cuda_available:
                try:
                    self._model = whisper.load_model(self.MODEL_NAME, device="cuda")
                    self._device = "cuda"
                    event_callback("info", "Local", "CUDA 사용")
                    return self._model, self._device
                except Exception as exc:
                    event_callback("warning", "Local", "CUDA 초기화 실패로 CPU를 사용합니다.")
                    cuda_detail = str(exc)
            else:
                event_callback("info", "Local", "CUDA unavailable → CPU")
                cuda_detail = "CUDA is unavailable"

            try:
                self._model = whisper.load_model(self.MODEL_NAME, device="cpu")
                self._device = "cpu"
                return self._model, self._device
            except Exception as exc:
                raise EngineError(
                    "LOCAL_MODEL_LOAD_FAILED",
                    ErrorCategory.RUNTIME,
                    "Local Whisper medium 모델을 불러오지 못했습니다.",
                    technical_detail=f"{cuda_detail}; CPU: {exc}",
                    fatal=True,
                ) from exc

    @staticmethod
    def _is_fp16_error(exc: Exception) -> bool:
        detail = str(exc).lower()
        return any(marker in detail for marker in ("fp16", "float16", "half", "cublas"))

    def transcribe(
        self,
        source_path: Path,
        token: CancellationToken,
        event_callback: EventCallback,
        progress_callback: ProgressCallback,
    ) -> TranscriptionResult:
        token.raise_if_requested()
        model, device = self._load_model(event_callback)
        progress_callback(None)

        with self._transcribe_lock:
            token.raise_if_requested()
            options = dict(self.TRANSCRIBE_OPTIONS)
            options["fp16"] = device == "cuda"
            try:
                payload = model.transcribe(str(source_path), **options)
            except Exception as exc:
                token.raise_if_requested()
                if options["fp16"] and self._is_fp16_error(exc):
                    event_callback("warning", "Local", "fp16 fallback")
                    options["fp16"] = False
                    try:
                        payload = model.transcribe(str(source_path), **options)
                    except Exception as fallback_exc:
                        token.raise_if_requested()
                        raise self._transcription_error(fallback_exc) from fallback_exc
                else:
                    raise self._transcription_error(exc) from exc

        # OpenAI Whisper does not expose a safe mid-call cancellation callback.
        # A request observed here prevents any output from being committed.
        token.raise_if_requested()
        try:
            return TranscriptionResult.from_engine_payload(payload)
        except (TypeError, ValueError) as exc:
            raise EngineError(
                "LOCAL_RESULT_INVALID",
                ErrorCategory.OUTPUT,
                "Local Whisper 결과 형식이 올바르지 않습니다.",
                technical_detail=str(exc),
            ) from exc

    @staticmethod
    def _transcription_error(exc: Exception) -> EngineError:
        detail = str(exc)
        lowered = detail.lower()
        if "ffmpeg" in lowered or "no such file" in lowered:
            return EngineError(
                "FFMPEG_UNAVAILABLE",
                ErrorCategory.RUNTIME,
                "오디오를 읽는 데 필요한 ffmpeg를 사용할 수 없습니다.",
                technical_detail=detail,
                fatal=True,
            )
        return EngineError(
            "LOCAL_TRANSCRIPTION_FAILED",
            ErrorCategory.INPUT,
            "Local 전사에 실패했습니다.",
            technical_detail=detail,
        )
