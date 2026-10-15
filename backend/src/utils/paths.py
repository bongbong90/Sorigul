import os
from pathlib import Path

def get_app_data_dir() -> Path:
    # Windows: %LOCALAPPDATA%\Sorigul
    # Others: ~/.config/Sorigul (or similar fallback)
    if os.name == 'nt' and "LOCALAPPDATA" in os.environ:
        base = Path(os.environ["LOCALAPPDATA"])
    else:
        # Fallback for tests or non-Windows
        base = Path.home() / ".config"

    return base / "Sorigul"
