import math
import re
import threading
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol

from pydantic import BaseModel, Field, PrivateAttr, model_validator


SILENCE_MARKER = "sorigul_silence"


def validate_silence_marker(marker, scope):
    """Readable completion contract, NOT an authentication/cryptographic proof.

    Only trusted producers attach the internal result capability. Disk readers
    check this schema and the source binding; request/engine JSON cannot attach
    that capability via from_engine_payload().
    """
    common = {"version", "scope", "engine", "model_revision", "status", "duration_seconds"}
    extra = ({"index", "input_sha256"} if scope == "chunk" else
             {"chunks_verified", "source_sha256", "source_size", "cleanup_complete"})
    if (scope not in ("chunk", "file") or not isinstance(marker, dict) or set(marker) != common | extra
            or type(marker["version"]) is not int or marker["version"] != 1
            or marker["scope"] != scope or marker["engine"] != "official_colab"
            or marker["status"] != ("verified" if scope == "chunk" else "complete")
            or not isinstance(marker["model_revision"], str)
            or not re.fullmatch(r"[0-9a-f]{40}", marker["model_revision"])
            or type(marker["duration_seconds"]) not in (int, float)
            or not math.isfinite(marker["duration_seconds"]) or marker["duration_seconds"] <= 0):
        raise ValueError("Invalid verified silence contract")
    digest = marker.get("input_sha256" if scope == "chunk" else "source_sha256")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("Invalid verified silence contract")
    if scope == "chunk":
        valid = (type(marker["index"]) is int and 0 <= marker["index"] <= 99999
                 and marker["duration_seconds"] <= 301)
    else:
        valid = (type(marker["chunks_verified"]) is int and 1 <= marker["chunks_verified"] <= 100000
                 and marker["duration_seconds"] <= marker["chunks_verified"] * 301
                 and type(marker["source_size"]) is int and marker["source_size"] > 0
                 and marker["cleanup_complete"] is True)
    if not valid:
        raise ValueError("Invalid verified silence contract")


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
    _silence_proof: Optional[dict] = PrivateAttr(default=None)

    def _set_verified_silence(self, marker):
        """Trusted Worker/Pipeline/cache boundary only; never called by JSON parsing."""
        validate_silence_marker(marker, marker.get("scope") if isinstance(marker, dict) else None)
        if self.text != "" or self.segments != []:
            raise ValueError("Silence must have empty text and segments")
        self._silence_proof = dict(marker)
        self.metadata["verified_silence"] = marker["scope"] == "file"

    @property
    def silence_proof(self):
        return dict(self._silence_proof) if self._silence_proof is not None else None

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
        payload = {
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
        if self._silence_proof is not None:
            validate_silence_marker(self._silence_proof, self._silence_proof["scope"])
            if self.text != "" or self.segments != []:
                raise ValueError("Silence must have empty text and segments")
            payload[SILENCE_MARKER] = self.silence_proof
        return payload


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
        self._finished = threading.Event()

    def request_stop(self):
        self._stop.set()

    def request_cancel(self):
        self._cancel.set()

    def mark_finished(self):
        """Called by the runner inside the mutation that persists the run's
        terminal Job state. After this, a new Stop/Cancel request can no
        longer be acknowledged by this run."""
        self._finished.set()

    @property
    def is_stop_requested(self) -> bool:
        return self._stop.is_set()

    @property
    def is_cancel_requested(self) -> bool:
        return self._cancel.is_set()

    @property
    def is_finished(self) -> bool:
        return self._finished.is_set()

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
