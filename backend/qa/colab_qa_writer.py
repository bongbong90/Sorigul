"""Atomic, sanitized QA result writer. QA-only directory; never overwrites.

Only an allowlisted schema is accepted: exact key sets, and leaves that are
None/bool/bounded int or a string from fixed QA enumerations. Tokens, proxy
URLs, paths, account data, response bodies and MP3 bytes cannot be represented.

Commit = exclusive temp create + write + fsync -> no-overwrite publish
(Windows rename / POSIX link) -> POSIX directory fsync -> re-read and compare.
Windows has no portable directory flush here; NTFS rename durability across
power loss is NOT VERIFIED. Any failure is a fixed QAResultSaveError and a
published-but-unverifiable file is moved aside, never presented as committed.
"""
import json
import os
from pathlib import Path
import stat
import uuid

from qa.colab_qa_run import QAResultSaveError
from qa.colab_readback import _EXCEPTION_TYPES, Code, QADiagnostics, Stage
from src.utils.paths import get_app_data_dir

RESULT_DIR_NAME = "sorigul-qa-results"
SCHEMA = "SORIGUL_QA_LIVE_B2D_V1"
_MAX_INT = 10 ** 9

GATE_VALUES = {"NOT_RUN", "PASS", "FAIL", "BLOCKED", "NOT_VERIFIED", "ALLOWED",
               "DEADLINE_BLOCKED", "CANCELLED", "UPLOAD_NOT_VERIFIED"}
ALLOWED_STRINGS = frozenset(
    {SCHEMA} | GATE_VALUES | {s.value for s in Stage} | {c.value for c in Code} | set(_EXCEPTION_TYPES)
    | {"RUNNING", "UNCONFIRMED", "FILE_CLEANUP", "RUNTIME_CLEANUP",
       "FILE_CLEANUP_UNCONFIRMED", "RUNTIME_CLEANUP_UNCONFIRMED"})

_LEAF = None


def _shape(value):
    return {key: _shape(item) for key, item in value.items()} if isinstance(value, dict) else _LEAF


COORDINATOR_TEMPLATE = {
    **dict.fromkeys(("lease", "observer", "bounded_operations", "readback_gate", "deadline",
                     "hard_deadline_enforcement", "work_elapsed_seconds",
                     "runtime_elapsed_seconds", "recovery_required", "pre_commit_verdict")),
    "file_cleanup": dict.fromkeys(("delete_confirmed", "file_absent", "run_directory_absent",
                                   "ownership_conflict")),
    "runtime_cleanup": dict.fromkeys(("delete_attempted", "delete_confirmed", "get_absent",
                                      "list_absent", "ownership_cleaned",
                                      "account_binding_matched", "uncertain_runtime_found")),
}
RECORD_TEMPLATE = {"schema": _LEAF, "diagnostics": _shape(QADiagnostics().snapshot()),
                   "coordinator": COORDINATOR_TEMPLATE}


def _validate(value, template):
    if isinstance(template, dict):
        if type(value) is not dict or set(value) != set(template):
            raise ValueError
        for key, child in template.items():
            _validate(value[key], child)
    elif not (value is None or type(value) is bool
              or (type(value) is int and 0 <= value <= _MAX_INT)
              or (type(value) is str and value in ALLOWED_STRINGS)):
        raise ValueError


def validate_record(record):
    _validate(record, RECORD_TEMPLATE)
    if record["schema"] != SCHEMA:
        raise ValueError
    return record


def _uuid4(value):
    try:
        return isinstance(value, str) and str(uuid.UUID(value)) == value and uuid.UUID(value).version == 4
    except ValueError:
        return False


def _no_links(path):
    """lstat every component; never follow a symlink, junction or reparse point."""
    for entry in reversed((path, *path.parents)):
        try:
            attrs = os.lstat(entry)
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(attrs.st_mode) or getattr(attrs, "st_file_attributes", 0) & 0x400:
            raise ValueError


class QAResultWriter:
    """One result file per execution: <root>/qa-result-<execution_id>.json."""

    def __init__(self, root):
        root = Path(root)
        if not root.is_absolute() or ".." in root.parts or root.name != RESULT_DIR_NAME:
            raise QAResultSaveError("QA_RESULT_SAVE_FAILED")
        try:
            app_data = get_app_data_dir().absolute()
            inside_product_data = root == app_data or app_data in root.parents
        except Exception:
            inside_product_data = True
        if inside_product_data:
            raise QAResultSaveError("QA_RESULT_SAVE_FAILED")
        self.root = root

    def __repr__(self):
        return "QAResultWriter(<private>)"

    def _final(self, execution_id):
        if not _uuid4(execution_id):
            raise ValueError
        return self.root / f"qa-result-{execution_id}.json"

    def exists(self, execution_id):
        """True also when undecidable, so a caller fails closed."""
        try:
            return os.path.lexists(self._final(execution_id))
        except Exception:
            return True

    def _prepare_root(self):
        _no_links(self.root)
        if not os.path.lexists(self.root):
            os.mkdir(self.root, 0o700)  # Parent must already exist; no mkdir -p.
        _no_links(self.root)
        if not stat.S_ISDIR(os.lstat(self.root).st_mode):
            raise ValueError

    def _write_temp(self, temp, data):
        flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
                 | getattr(os, "O_NOFOLLOW", 0))
        descriptor = os.open(temp, flags, 0o600)
        try:
            view = memoryview(data)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise OSError
                view = view[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _publish(self, temp, final):
        if os.name == "nt":
            os.rename(temp, final)  # MoveFileEx without REPLACE_EXISTING.
        else:
            os.link(temp, final)    # Fails if final exists; rename would overwrite.
            os.unlink(temp)

    def _sync_directory(self):
        if os.name != "nt":
            descriptor = os.open(self.root, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)

    def _verify(self, final, data, record):
        _no_links(final)
        attrs = os.lstat(final)
        if not stat.S_ISREG(attrs.st_mode) or attrs.st_nlink != 1 or attrs.st_size != len(data):
            raise ValueError
        with open(final, "rb") as handle:
            stored = handle.read(len(data) + 1)
        if stored != data or json.loads(stored) != record:
            raise ValueError

    def write(self, record, *, execution_id):
        """Return only after a verified commit; otherwise raise the fixed error."""
        temp = published = None
        try:
            validate_record(record)
            final = self._final(execution_id)
            data = (json.dumps(record, sort_keys=True, separators=(",", ":"),
                               ensure_ascii=True) + "\n").encode("ascii")
            self._prepare_root()
            if os.path.lexists(final):
                raise ValueError  # Never overwrite an existing (possibly user) file.
            temp = self.root / f".qa-result-{uuid.uuid4().hex}.tmp"
            self._write_temp(temp, data)
            self._publish(temp, final)
            published = final
            self._sync_directory()
            self._verify(final, data, record)
            published = None
            return final
        except BaseException as exc:
            if published is not None:
                try:  # Quarantine (never delete) an unverifiable published result.
                    os.rename(published, self.root / f".qa-result-{execution_id}.invalid-{uuid.uuid4().hex}")
                except Exception:
                    pass
            if not isinstance(exc, Exception):
                raise  # Cancellation is preserved, never relabelled.
            raise QAResultSaveError("QA_RESULT_SAVE_FAILED") from None
        finally:
            if temp is not None:
                try:
                    if os.path.lexists(temp):
                        os.unlink(temp)  # Only our own exclusive temp file.
                except Exception:
                    pass
