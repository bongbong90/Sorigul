"""Lightweight live-change revision for the selected transcription folder.

Legacy parity (#111): Legacy watched exactly one target folder with
QFileSystemWatcher and rescanned it after a 1000ms debounce. Sorigul keeps
the user-visible behavior without a native watcher: the frontend polls this
opaque revision and, only when it changes, calls the existing scan/refresh
APIs.

The revision is derived from top-level entry metadata only (name, size,
mtime_ns) of MP3/TXT/JSON/SRT regular files. It never recurses into child
directories, never follows symlinks, and never reads or hashes file contents.
It performs no mutation and has no Job side effects.
"""

import hashlib
import json
import os
from pathlib import Path

from pydantic import BaseModel


REVISION_EXTENSIONS = frozenset({".mp3", ".txt", ".json", ".srt"})


class FolderRevision(BaseModel):
    revision: str
    file_count: int


def folder_revision(folder: str) -> FolderRevision:
    """Return the top-level revision of `folder`.

    Raises FileNotFoundError / NotADirectoryError / OSError (e.g.
    PermissionError) for an unusable folder, mirroring ResultsService.scan.
    """
    root = Path(folder).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise NotADirectoryError(folder)

    entries: list[tuple[str, int, int]] = []
    with os.scandir(root) as iterator:
        for entry in iterator:
            if os.path.splitext(entry.name)[1].lower() not in REVISION_EXTENSIONS:
                continue
            try:
                if not entry.is_file(follow_symlinks=False):
                    continue
                stat = entry.stat(follow_symlinks=False)
            except OSError:
                # Vanished between listing and stat: it is simply not present.
                continue
            entries.append((entry.name, stat.st_size, stat.st_mtime_ns))

    entries.sort()
    canonical = json.dumps(entries, ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return FolderRevision(revision=digest, file_count=len(entries))
