from pathlib import Path
from datetime import datetime
from typing import Optional
from src.domain.models import ScannedFile, BundleStatus
from src.domain.transcription import EngineError
from src.services.output_bundle import BundlePaths, OutputBundleValidator
from src.services.audio_metadata import AudioMetadataService

class FileScanner:
    def __init__(
        self,
        folder_path: str,
        audio_metadata_service: Optional[AudioMetadataService] = None,
    ):
        self.folder_path = Path(folder_path)
        self.audio_metadata_service = audio_metadata_service or AudioMetadataService()

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
                    completion_status=status,
                    duration_seconds=self.audio_metadata_service.duration_seconds(file_path),
                )
                results.append(scanned_file)

        return results

    def check_bundle(self, mp3_path: Path) -> BundleStatus:
        txt_path = mp3_path.with_suffix('.txt')
        json_path = mp3_path.with_suffix('.json')
        srt_path = mp3_path.with_suffix('.srt')

        # Missing members are incomplete. Empty TXT is decided with the JSON
        # completion contract by the same validator used during atomic writes.
        if not txt_path.exists():
            return BundleStatus.INCOMPLETE

        # Check SRT
        if not srt_path.exists():
            return BundleStatus.INCOMPLETE

        # Check JSON
        if not json_path.exists() or json_path.stat().st_size == 0:
            return BundleStatus.INCOMPLETE

        try:
            OutputBundleValidator().validate(BundlePaths.final_for(mp3_path))
        except EngineError as exc:
            return BundleStatus.INCOMPLETE if exc.code == "TXT_INVALID" else BundleStatus.INVALID_RESULT
        except (OSError, TypeError, ValueError):
            return BundleStatus.INVALID_RESULT

        return BundleStatus.DONE
