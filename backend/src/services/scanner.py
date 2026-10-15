import os
import json
from pathlib import Path
from datetime import datetime
from src.domain.models import ScannedFile, BundleStatus

class FileScanner:
    def __init__(self, folder_path: str):
        self.folder_path = Path(folder_path)

    def scan(self) -> list[ScannedFile]:
        if not self.folder_path.exists() or not self.folder_path.is_dir():
            return []

        results = []
        for file_path in self.folder_path.iterdir():
            if not file_path.is_file():
                continue

            if file_path.suffix.lower() == ".mp3":
                stat = file_path.stat()
                status = self.check_bundle(file_path)

                scanned_file = ScannedFile(
                    id=file_path.stem,
                    filename=file_path.name,
                    source_path=str(file_path.absolute()),
                    size=stat.st_size,
                    modified_at=datetime.fromtimestamp(stat.st_mtime),
                    completion_status=status
                )
                results.append(scanned_file)

        return results

    def check_bundle(self, mp3_path: Path) -> BundleStatus:
        txt_path = mp3_path.with_suffix('.txt')
        json_path = mp3_path.with_suffix('.json')
        srt_path = mp3_path.with_suffix('.srt')

        # Check TXT
        if not txt_path.exists() or txt_path.stat().st_size == 0:
            return BundleStatus.INCOMPLETE

        # Check SRT
        if not srt_path.exists():
            return BundleStatus.INCOMPLETE

        # Check JSON
        if not json_path.exists() or json_path.stat().st_size == 0:
            return BundleStatus.INCOMPLETE

        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if not isinstance(data, dict):
                return BundleStatus.INVALID_RESULT

            if "text" not in data or "segments" not in data:
                return BundleStatus.INVALID_RESULT

        except (json.JSONDecodeError, UnicodeDecodeError):
            return BundleStatus.INVALID_RESULT

        return BundleStatus.DONE
