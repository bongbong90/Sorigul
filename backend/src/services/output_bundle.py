import json
import hashlib
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Optional

from src.domain.transcription import (
    CancelRequested,
    EngineError,
    ErrorCategory,
    StopRequested,
    TranscriptionResult,
    SILENCE_MARKER,
    validate_silence_marker,
)


@dataclass(frozen=True)
class BundlePaths:
    txt: Path
    json: Path
    srt: Path
    source: Optional[Path] = field(default=None, compare=False, repr=False)

    @classmethod
    def final_for(cls, source_path: Path) -> "BundlePaths":
        return cls(
            txt=source_path.with_suffix(".txt"),
            json=source_path.with_suffix(".json"),
            srt=source_path.with_suffix(".srt"),
            source=source_path,
        )

    def as_dict(self) -> Dict[str, Path]:
        return {"txt": self.txt, "json": self.json, "srt": self.srt}


class OutputBundleValidator:
    @staticmethod
    def _unique_fields(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("Duplicate result field")
            value[key] = item
        return value

    @staticmethod
    def _validate_silence(paths, payload):
        try:
            marker = payload[SILENCE_MARKER]
            validate_silence_marker(marker, "file")
            if (set(payload) != {"text", "segments", SILENCE_MARKER}
                    or payload["text"] != "" or payload["segments"] != []
                    or paths.txt.stat().st_size != 0 or paths.srt.stat().st_size != 0
                    or paths.source is None or paths.source.suffix.lower() != ".mp3"
                    or not paths.source.is_file() or paths.source.stat().st_size != marker["source_size"]):
                raise ValueError
            digest = hashlib.sha256()
            with paths.source.open("rb") as handle:
                for block in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(block)
            if digest.hexdigest() != marker["source_sha256"]:
                raise ValueError
        except (OSError, ValueError, TypeError, KeyError):
            raise EngineError("SILENCE_INVALID", ErrorCategory.OUTPUT,
                              "무음 완료 결과의 형식 또는 원본 파일이 일치하지 않습니다.") from None

    def validate(self, paths: BundlePaths):
        if not paths.txt.exists():
            raise EngineError(
                "TXT_INVALID",
                ErrorCategory.OUTPUT,
                "TXT 결과가 비어 있거나 존재하지 않습니다.",
            )
        if not paths.json.exists() or paths.json.stat().st_size <= 0:
            raise EngineError(
                "JSON_INVALID",
                ErrorCategory.OUTPUT,
                "JSON 결과가 비어 있거나 존재하지 않습니다.",
            )
        if not paths.srt.exists():
            raise EngineError(
                "SRT_MISSING",
                ErrorCategory.OUTPUT,
                "SRT 결과가 존재하지 않습니다.",
            )

        try:
            payload = json.loads(paths.json.read_text(encoding="utf-8"), object_pairs_hook=self._unique_fields)
        except (ValueError, UnicodeDecodeError, OSError) as exc:
            raise EngineError(
                "JSON_INVALID",
                ErrorCategory.OUTPUT,
                "JSON 결과를 읽을 수 없습니다.",
                technical_detail=str(exc),
            ) from exc
        if not isinstance(payload, dict) or "text" not in payload or "segments" not in payload:
            raise EngineError(
                "JSON_SCHEMA_INVALID",
                ErrorCategory.OUTPUT,
                "JSON 결과에 text 또는 segments가 없습니다.",
            )
        if SILENCE_MARKER in payload:
            self._validate_silence(paths, payload)
        elif paths.txt.stat().st_size <= 0:
            raise EngineError("TXT_INVALID", ErrorCategory.OUTPUT, "TXT 결과가 비어 있거나 존재하지 않습니다.")
        try:
            TranscriptionResult.from_engine_payload(payload)
        except (TypeError, ValueError) as exc:
            raise EngineError(
                "JSON_SCHEMA_INVALID",
                ErrorCategory.OUTPUT,
                "JSON 결과의 segment 형식이 올바르지 않습니다.",
                technical_detail=str(exc),
            ) from exc


class OutputBundleWriter:
    def __init__(
        self,
        validator: Optional[OutputBundleValidator] = None,
        replace: Callable[[Path, Path], None] = os.replace,
    ):
        self.validator = validator or OutputBundleValidator()
        self._replace = replace

    def commit(
        self,
        source_path: Path,
        result: TranscriptionResult,
        verification_callback: Optional[Callable[[], None]] = None,
        before_promotion: Optional[Callable[[], None]] = None,
    ) -> BundlePaths:
        """Write, validate, then promote a TXT/JSON/SRT bundle.

        Order: write staged -> verification_callback -> validate staged ->
        before_promotion -> promote. ``before_promotion`` is the last point
        at which a Stop/Cancel can prevent the commit; raising from it
        discards the staged files and leaves any existing bundle untouched.
        Once promotion starts it is a short non-interruptible transaction
        that either completes or rolls back -- never a half-installed bundle.
        """
        final_paths = BundlePaths.final_for(source_path)
        token = uuid.uuid4().hex
        staged_paths = BundlePaths(
            txt=source_path.parent / f".{source_path.stem}.{token}.txt.tmp",
            json=source_path.parent / f".{source_path.stem}.{token}.json.tmp",
            srt=source_path.parent / f".{source_path.stem}.{token}.srt.tmp",
            source=source_path,
        )
        backup_paths = BundlePaths(
            txt=source_path.parent / f".{source_path.stem}.{token}.txt.bak",
            json=source_path.parent / f".{source_path.stem}.{token}.json.bak",
            srt=source_path.parent / f".{source_path.stem}.{token}.srt.bak",
        )

        try:
            self._write_staged(staged_paths, result)
            if verification_callback is not None:
                verification_callback()
            self.validator.validate(staged_paths)
            if before_promotion is not None:
                before_promotion()
            self._replace_bundle(staged_paths, final_paths, backup_paths)
            self._remove_paths(backup_paths)
            return final_paths
        except (EngineError, StopRequested, CancelRequested):
            self._remove_paths(staged_paths)
            raise
        except Exception as exc:
            self._remove_paths(staged_paths)
            raise EngineError(
                "OUTPUT_REPLACE_FAILED",
                ErrorCategory.OUTPUT,
                "결과 파일을 안전하게 교체하지 못했습니다.",
                technical_detail=str(exc),
            ) from exc

    @staticmethod
    def _format_timestamp(seconds: float) -> str:
        milliseconds = max(0, round(seconds * 1000))
        hours, remainder = divmod(milliseconds, 3_600_000)
        minutes, remainder = divmod(remainder, 60_000)
        secs, millis = divmod(remainder, 1_000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    def _write_staged(self, paths: BundlePaths, result: TranscriptionResult):
        paths.txt.write_text(result.text, encoding="utf-8")
        paths.json.write_text(
            json.dumps(result.output_payload(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        blocks = []
        for index, segment in enumerate(result.segments, 1):
            blocks.append(
                f"{index}\n"
                f"{self._format_timestamp(segment.start)} --> "
                f"{self._format_timestamp(segment.end)}\n"
                f"{segment.text}\n"
            )
        paths.srt.write_text("\n".join(blocks), encoding="utf-8")

    def _replace_bundle(
        self,
        staged: BundlePaths,
        final: BundlePaths,
        backup: BundlePaths,
    ):
        moved_backups = []
        installed = []
        try:
            for key, final_path in final.as_dict().items():
                if final_path.exists():
                    backup_path = backup.as_dict()[key]
                    self._replace(final_path, backup_path)
                    moved_backups.append((final_path, backup_path))
            for key, staged_path in staged.as_dict().items():
                final_path = final.as_dict()[key]
                self._replace(staged_path, final_path)
                installed.append(final_path)
            self.validator.validate(final)
        except Exception:
            rollback_errors = []
            for final_path in reversed(installed):
                try:
                    final_path.unlink(missing_ok=True)
                except OSError as exc:
                    rollback_errors.append(str(exc))
            for final_path, backup_path in reversed(moved_backups):
                try:
                    if backup_path.exists():
                        self._replace(backup_path, final_path)
                except OSError as exc:
                    rollback_errors.append(str(exc))
            if rollback_errors:
                raise RuntimeError("rollback failed: " + "; ".join(rollback_errors))
            raise

    @staticmethod
    def _remove_paths(paths: BundlePaths):
        for path in paths.as_dict().values():
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
