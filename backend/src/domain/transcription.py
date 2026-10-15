import math
import threading
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol

from pydantic import BaseModel, Field, model_validator


class TranscriptionSegment(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    text: str
    metadata: Dict[str, Any] = Field(default_factory=dict, exclude=True)

    @model_validator(mode="after")
    def validate_timestamps(self):
        if not math.isfinite(self.start) or not math.isfinite(self.end):
            raise ValueError("segment timestamps must be finite")
        if self.end < self.start:
            raise ValueError("segment end must not precede start")
        return self


class TranscriptionResult(BaseModel):
    text: str
    segments: List[TranscriptionSegment]
    language: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict, exclude=True)

    @classmethod
    def from_engine_payload(cls, payload: Dict[str, Any]) -> "TranscriptionResult":
        if not isinstance(payload, dict):
            raise ValueError("engine result must be an object")
        if "text" not in payload or "segments" not in payload:
            raise ValueError("engine result requires text and segments")
        if not isinstance(payload["text"], str) or not isinstance(payload["segments"], list):
            raise ValueError("engine result text/segments have invalid types")

        segments = []
        for raw in payload["segments"]:
            if not isinstance(raw, dict):
                raise ValueError("each segment must be an object")
            missing = {"start", "end", "text"} - raw.keys()
            if missing:
                raise ValueError(f"segment missing fields: {sorted(missing)}")
            metadata = {
                key: value
                for key, value in raw.items()
                if key not in {"start", "end", "text"}
            }
            segments.append(
                TranscriptionSegment(
                    start=raw["start"],
                    end=raw["end"],
                    text=raw["text"],
                    metadata=metadata,
                )
            )

        segments.sort(key=lambda segment: (segment.start, segment.end))
        return cls(
            text=payload["text"],
            segments=segments,
            language=payload.get("language"),
            metadata={
                key: value
                for key, value in payload.items()
                if key not in {"text", "segments", "language"}
            },
        )

    def output_payload(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "segments": [
                {
                    "start": segment.start,
                    "end": segment.end,
                    "text": segment.text,
                    **segment.metadata,
                }
                for segment in self.segments
            ],
        }


class ErrorCategory(str, Enum):
    RUNTIME = "runtime"
    CONFIGURATION = "configuration"
    NETWORK = "network"
    AUTHENTICATION = "authentication"
    INPUT = "input"
    OUTPUT = "output"
    CANCEL = "cancel"


class EngineError(Exception):
    def __init__(
        self,
        code: str,
        category: ErrorCategory,
        user_message: str,
        *,
        technical_detail: Optional[str] = None,
        retryable: bool = False,
        fatal: bool = False,
    ):
        super().__init__(user_message)
        self.code = code
        self.category = category
        self.user_message = user_message
        self.technical_detail = technical_detail
        self.retryable = retryable
        self.fatal = fatal


class StopRequested(Exception):
    pass


class CancelRequested(Exception):
    pass


class CancellationToken:
    def __init__(self):
        self._stop = threading.Event()
        self._cancel = threading.Event()

    def request_stop(self):
        self._stop.set()

    def request_cancel(self):
        self._cancel.set()

    @property
    def is_stop_requested(self) -> bool:
        return self._stop.is_set()

    @property
    def is_cancel_requested(self) -> bool:
        return self._cancel.is_set()

    def raise_if_requested(self):
        if self.is_cancel_requested:
            raise CancelRequested()
        if self.is_stop_requested:
            raise StopRequested()


EventCallback = Callable[[str, str, str], None]
ProgressCallback = Callable[[Optional[float]], None]


class TranscriptionEngine(Protocol):
    def transcribe(
        self,
        source_path: Path,
        token: CancellationToken,
        event_callback: EventCallback,
        progress_callback: ProgressCallback,
    ) -> TranscriptionResult:
        ...
