import os
from pathlib import Path
from typing import List, Tuple

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
