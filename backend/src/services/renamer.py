import os
from pathlib import Path
from typing import List, Tuple

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


class BundleRenamer:
    EXTENSIONS = [".mp3", ".txt", ".json", ".srt"]

    def apply_rename(self, folder_path: str, old_stem: str, new_stem: str) -> bool:
        folder = Path(folder_path)

        # 1. Preflight check
        moves: List[Tuple[Path, Path]] = []
        for ext in self.EXTENSIONS:
            old_file = folder / f"{old_stem}{ext}"
            new_file = folder / f"{new_stem}{ext}"

            if old_file.exists():
                if new_file.exists():
                    # Conflict! Cannot rename safely without overwrite.
                    return False
                moves.append((old_file, new_file))

        if not moves:
            return False # Nothing to rename

        # 2. Apply rename
        completed_moves: List[Tuple[Path, Path]] = []
        try:
            for old_file, new_file in moves:
                old_file.rename(new_file)
                completed_moves.append((old_file, new_file))
            return True
        except Exception:
            # 3. Rollback on failure
            for old_file, new_file in reversed(completed_moves):
                try:
                    new_file.rename(old_file)
                except Exception:
                    pass # Best effort rollback
            return False
