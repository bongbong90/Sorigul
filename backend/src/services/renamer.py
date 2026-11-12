import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from src.services.normalizer import CONTROL_CHARS_PATTERN, FORBIDDEN_CHARS_PATTERN


class UnsafeStemError(ValueError):
    """Raised by validate_safe_stem on a stem that isn't a safe basename."""


def validate_safe_stem(stem: str, field_label: str) -> str:
    """Validate a rename target's filename stem (no extension).

    Deliberately not the same rule as classification-text validation: a
    stem like `개념완성_민법_1주차_1강` must keep its structural underscores.
    This only rejects what would make the stem unsafe as a bare filesystem
    basename -- empty, `.`/`..`, path separators (which could escape the
    target folder via `folder / f"{stem}{ext}"`), Windows-forbidden
    characters, control characters, and a trailing dot/space.
    """
    if not stem:
        raise UnsafeStemError(f"{field_label}이(가) 비어 있습니다.")
    if stem in {".", ".."}:
        raise UnsafeStemError(f"{field_label}에 '.' 또는 '..'을 사용할 수 없습니다.")
    if "/" in stem or "\\" in stem:
        raise UnsafeStemError(f"{field_label}에 경로 구분자(/, \\)를 사용할 수 없습니다.")
    if CONTROL_CHARS_PATTERN.search(stem):
        raise UnsafeStemError(f"{field_label}에 사용할 수 없는 제어 문자가 포함되어 있습니다.")
    if FORBIDDEN_CHARS_PATTERN.search(stem):
        raise UnsafeStemError(f'{field_label}에는 다음 문자를 사용할 수 없습니다: < > : " / \\ | ? *')
    if stem.endswith(".") or stem.endswith(" "):
        raise UnsafeStemError(f"{field_label}은(는) 마침표(.) 또는 공백으로 끝날 수 없습니다.")
    return stem


class RenameStatus(str, Enum):
    SUCCESS = "SUCCESS"
    RENAME_CONFLICT = "RENAME_CONFLICT"
    RENAME_NOTHING_TO_DO = "RENAME_NOTHING_TO_DO"
    RENAME_APPLY_FAILED_ROLLED_BACK = "RENAME_APPLY_FAILED_ROLLED_BACK"
    RENAME_ROLLBACK_FAILED = "RENAME_ROLLBACK_FAILED"


@dataclass(frozen=True)
class RenameResult:
    status: RenameStatus
    apply_error: Optional[str] = None
    rollback_error: Optional[str] = None

    def __bool__(self) -> bool:
        """Keep legacy truth checks meaningful while exposing full outcome."""
        return self.status == RenameStatus.SUCCESS


class BundleRenamer:
    EXTENSIONS = [".mp3", ".txt", ".json", ".srt"]

    def __init__(self, rename_path: Optional[Callable[[Path, Path], None]] = None):
        self._rename_path = rename_path or (lambda source, target: source.rename(target))

    def apply_rename(self, folder_path: str, old_stem: str, new_stem: str) -> RenameResult:
        folder = Path(folder_path)

        # 1. Preflight check
        moves: List[Tuple[Path, Path]] = []
        for ext in self.EXTENSIONS:
            old_file = folder / f"{old_stem}{ext}"
            new_file = folder / f"{new_stem}{ext}"

            if old_file.exists():
                if new_file.exists():
                    # Conflict! Cannot rename safely without overwrite.
                    return RenameResult(RenameStatus.RENAME_CONFLICT)
                moves.append((old_file, new_file))

        if not moves:
            return RenameResult(RenameStatus.RENAME_NOTHING_TO_DO)

        # 2. Apply rename
        completed_moves: List[Tuple[Path, Path]] = []
        try:
            for old_file, new_file in moves:
                self._rename_path(old_file, new_file)
                completed_moves.append((old_file, new_file))
            return RenameResult(RenameStatus.SUCCESS)
        except Exception as apply_error:
            # 3. Rollback on failure
            rollback_error: Optional[Exception] = None
            for old_file, new_file in reversed(completed_moves):
                try:
                    self._rename_path(new_file, old_file)
                except Exception as exc:
                    rollback_error = rollback_error or exc
            if rollback_error is not None:
                return RenameResult(
                    RenameStatus.RENAME_ROLLBACK_FAILED,
                    apply_error=str(apply_error),
                    rollback_error=str(rollback_error),
                )
            return RenameResult(
                RenameStatus.RENAME_APPLY_FAILED_ROLLED_BACK,
                apply_error=str(apply_error),
            )
