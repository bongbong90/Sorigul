import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from src.domain.models import BundleStatus
from src.services.scanner import FileScanner


ResultFilter = Literal["all", "complete", "incomplete", "results"]
RESULT_EXTENSIONS = {".txt", ".json", ".srt"}
KNOWN_EXTENSIONS = {".mp3", *RESULT_EXTENSIONS}


class FolderItem(BaseModel):
    id: str
    filename: str
    kind: Literal["MP3", "TXT", "JSON", "SRT"]
    status: Literal["COMPLETE", "INCOMPLETE", "RESULT"]
    size: int
    modified_at: datetime
    has_source: bool


class FolderScanResult(BaseModel):
    scan_id: str
    folder: str
    filter: ResultFilter
    items: list[FolderItem]
    counts: Dict[str, int] = Field(default_factory=dict)


class TextContent(BaseModel):
    filename: str
    text: str
    truncated: bool = False


class OpenFolderIntent(BaseModel):
    action: Literal["OPEN_FOLDER"] = "OPEN_FOLDER"
    folder: str
    item_filename: Optional[str] = None


class _ScanContext:
    def __init__(self, root: Path, paths: Dict[str, Path]):
        self.root = root
        self.paths = paths


class ResultsService:
    def __init__(self, preview_chars: int = 500, max_text_bytes: int = 5 * 1024 * 1024):
        self.preview_chars = preview_chars
        self.max_text_bytes = max_text_bytes
        self._contexts: Dict[str, _ScanContext] = {}

    def scan(self, folder: str, result_filter: ResultFilter = "all") -> FolderScanResult:
        root = Path(folder).expanduser().resolve(strict=True)
        if not root.is_dir():
            raise NotADirectoryError(folder)

        bundle_statuses = {
            item.id: item.completion_status for item in FileScanner(str(root)).scan()
        }
        source_stems = set(bundle_statuses)
        items: list[FolderItem] = []
        paths: Dict[str, Path] = {}

        for path in sorted(root.iterdir(), key=lambda value: value.name.casefold()):
            if not path.is_file() or path.suffix.lower() not in KNOWN_EXTENSIONS:
                continue
            extension = path.suffix.lower()
            if extension == ".mp3":
                status = (
                    "COMPLETE"
                    if bundle_statuses.get(path.stem) == BundleStatus.DONE
                    else "INCOMPLETE"
                )
            else:
                status = "RESULT"
            if result_filter == "complete" and status != "COMPLETE":
                continue
            if result_filter == "incomplete" and status != "INCOMPLETE":
                continue
            if result_filter == "results" and status != "RESULT":
                continue

            item_id = hashlib.sha256(path.name.encode("utf-8")).hexdigest()[:24]
            stat = path.stat()
            paths[item_id] = path
            items.append(
                FolderItem(
                    id=item_id,
                    filename=path.name,
                    kind=extension[1:].upper(),
                    status=status,
                    size=stat.st_size,
                    modified_at=datetime.fromtimestamp(stat.st_mtime),
                    has_source=path.stem in source_stems,
                )
            )

        all_entries = [
            path for path in root.iterdir()
            if path.is_file() and path.suffix.lower() in KNOWN_EXTENSIONS
        ]
        complete_count = sum(status == BundleStatus.DONE for status in bundle_statuses.values())
        incomplete_count = len(bundle_statuses) - complete_count
        result_count = sum(path.suffix.lower() in RESULT_EXTENSIONS for path in all_entries)
        scan_id = uuid4().hex
        self._contexts[scan_id] = _ScanContext(root, paths)
        self._trim_contexts()
        return FolderScanResult(
            scan_id=scan_id,
            folder=str(root),
            filter=result_filter,
            items=items,
            counts={
                "all": len(all_entries),
                "complete": complete_count,
                "incomplete": incomplete_count,
                "results": result_count,
            },
        )

    def read_text(self, scan_id: str, item_id: str, full: bool = False) -> TextContent:
        path = self._resolve_item(scan_id, item_id, expected_suffix=".txt")
        size = path.stat().st_size
        if full and size > self.max_text_bytes:
            raise ValueError("TXT_TOO_LARGE")
        try:
            if full:
                text = path.read_text(encoding="utf-8")
            else:
                with path.open("r", encoding="utf-8") as handle:
                    text = handle.read(self.preview_chars + 1)
        except UnicodeDecodeError as exc:
            raise ValueError("TXT_NOT_UTF8") from exc
        if full:
            return TextContent(filename=path.name, text=text)
        truncated = len(text) > self.preview_chars
        return TextContent(
            filename=path.name,
            text=text[: self.preview_chars],
            truncated=truncated,
        )

    def open_folder_intent(self, scan_id: str, item_id: Optional[str] = None) -> OpenFolderIntent:
        context = self._contexts.get(scan_id)
        if context is None:
            raise KeyError("SCAN_NOT_FOUND")
        item_filename = None
        if item_id is not None:
            item_filename = self._resolve_item(scan_id, item_id).name
        return OpenFolderIntent(folder=str(context.root), item_filename=item_filename)

    def _resolve_item(self, scan_id: str, item_id: str, expected_suffix: Optional[str] = None) -> Path:
        context = self._contexts.get(scan_id)
        if context is None:
            raise KeyError("SCAN_NOT_FOUND")
        path = context.paths.get(item_id)
        if path is None:
            raise KeyError("ITEM_NOT_FOUND")
        resolved = path.resolve(strict=True)
        if resolved.parent != context.root or resolved.suffix.lower() not in KNOWN_EXTENSIONS:
            raise PermissionError("PATH_OUTSIDE_SCAN")
        if expected_suffix is not None and resolved.suffix.lower() != expected_suffix:
            raise ValueError("UNEXPECTED_EXTENSION")
        return resolved

    def _trim_contexts(self):
        while len(self._contexts) > 32:
            self._contexts.pop(next(iter(self._contexts)))
