import shutil
import sys
from pathlib import Path
from typing import Optional


def resolve_ffmpeg_path() -> Optional[str]:
    """Resolve the ffmpeg executable the backend should use.

    Resolution order:
    1. PATH -- covers both a developer's system ffmpeg and the packaged
       sidecar's PATH, which the Rust runtime prepends with the bundle's
       `binaries/` resource directory before spawning this process.
    2. A sibling `ffmpeg.exe` next to the running executable -- covers a
       standalone `--self-test` invocation (e.g. from the build script)
       made directly against the frozen exe, before Rust ever spawns it
       and injects PATH.

    Returns None if no ffmpeg executable can be found either way.
    """
    on_path = shutil.which("ffmpeg")
    if on_path:
        return on_path

    if getattr(sys, "frozen", False):
        sibling = Path(sys.executable).parent / "ffmpeg.exe"
        if sibling.is_file():
            return str(sibling)

    return None
