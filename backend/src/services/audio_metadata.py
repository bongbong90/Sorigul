import math
from pathlib import Path
from typing import Optional

class AudioMetadataService:
    def duration_seconds(self, path: Path) -> Optional[float]:
        if not path.exists() or not path.is_file():
            return None

        try:
            from mutagen.mp3 import MP3
            audio = MP3(path)
            duration = float(audio.info.length)
            if duration > 0 and math.isfinite(duration):
                return duration
        except Exception:
            pass
        return None

