"""Bounded audio-chunk upload over the official Jupyter Contents API.

PHASE 06 scope: move FFmpegAudioSplitter's local MP3 chunks into one
per-run remote directory. No model install, inference, merge, Job or UI wiring.

Protocol references checked 2026-11-13:
https://jupyter-server.readthedocs.io/en/latest/developers/rest-api.html
https://jupyter-server.readthedocs.io/en/latest/developers/contents.html
  PUT /api/contents/{path} {"type": "file", "format": "base64", "content", "chunk"}
  chunk 1 creates, 2..n-1 append, -1 appends and finishes (LargeFileManager).
  201 = created, 200 = an existing file was saved (overwritten).
  GET ...?content=0&hash=1 may return "size" and "hash"/"hash_algorithm".

Rules enforced here:
- Only the Jupyter Proxy Token header is sent (no Google OAuth token), over the
  PHASE 03 transport: HTTPS only, redirects and proxies disabled, bounded reply.
- Remote paths are derived from a run id and chunk index, never from input
  paths or URLs, and must stay under ``sorigul-transfer/<run_id>/``.
- A file is never sent in one piece: each request carries at most
  ``chunk_bytes`` raw bytes (default 4 MiB, max 8 MiB -> body < 12 MB, far under
  the 50 MB limit). Local data is streamed, not loaded whole.
- An unconfirmed response is never completion. Lost responses leave the record
  STATE_UNCERTAIN; nothing is re-sent automatically. Only an attempt that sent
  nothing may be repeated, and only a bounded number of times.
- 401/403/413/429 halt this transfer object permanently (no retry loops).
- Local files are only read. The shared root is never deleted. Cleanup
  failures are reported separately from transfer failures.
- Ownership (#232): the Contents API documents no atomic create-if-absent
  (no If-None-Match, POST picks its own name). The preflight GET 404 therefore
  does NOT prevent a concurrent writer from creating the same path before our
  first PUT; that race is narrowed, not eliminated. Only a first-PUT 201 with a
  matching model proves this transfer created the file (OWNED). A first-PUT
  200 (an existing file was saved) is a CONFLICT, and a lost or 5xx first-PUT
  reply is UNCERTAIN. Neither is ever DELETEd, retried, moved or promoted to
  owned. Cleanup reports them as skipped and keeps cleanup_required.
- The run directory is deleted only when no file in it has unresolved
  ownership and a fresh listing shows it empty, because the docs leave DELETE
  of a non-empty directory undefined (it may be recursive or trashed).
- This module does not manage Runtime or kernel lifetime; a clean file cleanup
  report says nothing about Runtime deletion or kernel recovery.
- Nothing here logs. Exceptions carry only a code.
"""

import base64
import hashlib
import math
import os
import re
import stat
import threading
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable
from urllib.parse import quote

from src.services.colab_jupyter_client import (
    ColabJupyterClient, JupyterClientError, _http_request,
)
from src.services.colab_runtime_client import ConnectionInfo


REMOTE_ROOT = "sorigul-transfer"
LOCAL_SUFFIX = ".mp3"
DEFAULT_CHUNK_BYTES = 4 * 1024 * 1024
MIN_CHUNK_BYTES = 64 * 1024
MAX_CHUNK_BYTES = 8 * 1024 * 1024
MAX_FILE_BYTES = 256 * 1024 * 1024
MAX_INDEX = 99999
MAX_ATTEMPTS_PER_INDEX = 2

_RUN_ID = re.compile(r"[0-9a-f]{32}")
_SHA256 = re.compile(r"[0-9a-f]{64}")


class TransferCode(str, Enum):
    INVALID_CONNECTION = "INVALID_CONNECTION"
    TOKEN_REFRESH_REQUIRED = "TOKEN_REFRESH_REQUIRED"
    AUTH_REJECTED = "AUTH_REJECTED"
    POLICY_REJECTED = "POLICY_REJECTED"
    RATE_LIMITED = "RATE_LIMITED"
    NETWORK_TIMEOUT = "NETWORK_TIMEOUT"
    CONNECTION_REJECTED = "CONNECTION_REJECTED"
    STATE_UNCERTAIN = "STATE_UNCERTAIN"
    NOT_PREPARED = "NOT_PREPARED"
    LOCAL_FILE_INVALID = "LOCAL_FILE_INVALID"
    LOCAL_FILE_CHANGED = "LOCAL_FILE_CHANGED"
    REMOTE_PATH_INVALID = "REMOTE_PATH_INVALID"
    REMOTE_EXISTS = "REMOTE_EXISTS"
    UPLOAD_REJECTED = "UPLOAD_REJECTED"
    RESPONSE_INVALID = "RESPONSE_INVALID"
    CHUNK_SEQUENCE_INVALID = "CHUNK_SEQUENCE_INVALID"
    INTEGRITY_MISMATCH = "INTEGRITY_MISMATCH"
    DUPLICATE_UPLOAD = "DUPLICATE_UPLOAD"
    ATTEMPTS_EXHAUSTED = "ATTEMPTS_EXHAUSTED"
    CANCELLED = "CANCELLED"
    TRANSFER_CLOSED = "TRANSFER_CLOSED"
    NOT_OWNED = "NOT_OWNED"
    DELETE_FAILED = "DELETE_FAILED"


_HALT_CODES = frozenset({TransferCode.AUTH_REJECTED, TransferCode.POLICY_REJECTED,
                         TransferCode.RATE_LIMITED})


class TransferError(Exception):
    def __init__(self, code):
        super().__init__(code.value)
        self.code = code


class TransferStatus(str, Enum):
    FAILED = "FAILED"                    # definitely not a complete remote file
    STATE_UNCERTAIN = "STATE_UNCERTAIN"  # a sent request's outcome is unknown
    ACKNOWLEDGED = "ACKNOWLEDGED"        # every request confirmed by the server
    VERIFIED = "VERIFIED"                # ACKNOWLEDGED + remote SHA256 matched


class IntegrityLevel(str, Enum):
    NONE = "NONE"
    RESPONSE_ONLY = "RESPONSE_ONLY"            # replies confirmed; size not reported
    SIZE_CONFIRMED = "SIZE_CONFIRMED"          # remote size == local size, no hash
    CONTENT_SHA256 = "CONTENT_SHA256"          # remote sha256 == local sha256


class RemoteOwnership(str, Enum):
    NONE = "NONE"            # nothing of ours was written
    OWNED = "OWNED"          # first PUT answered 201 with a matching model
    CONFLICT = "CONFLICT"    # first PUT answered 200: an existing file was saved
    UNCERTAIN = "UNCERTAIN"  # first PUT sent, creation not proven


@dataclass(frozen=True)
class FileTransferRecord:
    index: int
    remote_path: str
    size: int | None
    sha256: str | None
    chunks_total: int
    chunks_acknowledged: int
    status: TransferStatus
    integrity: IntegrityLevel
    error_code: TransferCode | None
    verification_error: TransferCode | None
    remote_may_exist: bool   # this transfer may have written the remote path
    all_chunks_sent: bool
    attempts: int
    remote_deleted: bool = False
    ownership: RemoteOwnership = RemoteOwnership.NONE  # only OWNED is ever deleted

    @property
    def completed(self):
        return self.status in (TransferStatus.ACKNOWLEDGED, TransferStatus.VERIFIED)

    @property
    def retryable(self):
        return (self.status is TransferStatus.FAILED and not self.remote_may_exist
                and self.error_code not in _HALT_CODES
                and self.error_code is not TransferCode.REMOTE_EXISTS)


@dataclass(frozen=True)
class CleanupReport:
    deleted_paths: tuple
    failed_paths: tuple          # ((remote_path, TransferCode), ...) DELETE failed
    run_dir_deleted: bool
    cleanup_required: bool
    error_code: TransferCode | None
    # Files only. Runtime deletion / kernel recovery is never claimed here.
    runtime_cleanup_claimed: bool = False
    # ((remote_path, TransferCode), ...) deliberately NOT deleted because
    # ownership is unproven (CONFLICT/UNCERTAIN) or the run dir is not empty.
    skipped_paths: tuple = ()


class _ChunkSequence:
    """Strict 1..n issue/ack order; maps n to the Contents API chunk marker."""

    def __init__(self, total):
        if type(total) is not int or total < 1:
            raise TransferError(TransferCode.CHUNK_SEQUENCE_INVALID)
        self.total = total
        self.issued = 0
        self.acknowledged = 0

    def issue(self):
        if self.issued != self.acknowledged or self.issued >= self.total:
            raise TransferError(TransferCode.CHUNK_SEQUENCE_INVALID)
        self.issued += 1
        number = self.issued
        if self.total == 1:
            return number, None  # single request, no "chunk" field
        return number, (-1 if number == self.total else number)

    def acknowledge(self, number):
        if (type(number) is not int or number != self.issued
                or self.acknowledged != number - 1):
            raise TransferError(TransferCode.CHUNK_SEQUENCE_INVALID)
        self.acknowledged = number

    @property
    def complete(self):
        return self.acknowledged == self.total


class _Fail(Exception):
    def __init__(self, code, uncertain=False):
        super().__init__(code.value)
        self.code, self.uncertain = code, uncertain


def _status_code(status):
    if status == 401:
        return TransferCode.AUTH_REJECTED
    if status in (403, 413):
        return TransferCode.POLICY_REJECTED
    if status == 429:
        return TransferCode.RATE_LIMITED
    return None


@dataclass(frozen=True)
class _LocalSnapshot:
    size: int
    mtime_ns: int
    sha256: str


class ColabJupyterFileTransfer:
    """One run's uploads into ``sorigul-transfer/<run_id>/`` and their cleanup.

    refresh_connection follows ColabJupyterClient: caller-initiated, same
    Runtime origin only, never automatic.
    """

    def __init__(self, connection_info: ConnectionInfo, *, run_id: str | None = None,
                 refresh_connection: Callable[[], ConnectionInfo] | None = None,
                 http_request=_http_request, chunk_bytes=DEFAULT_CHUNK_BYTES,
                 request_timeout=30.0,
                 utcnow=lambda: datetime.now(timezone.utc)):
        if (type(chunk_bytes) is not int
                or not MIN_CHUNK_BYTES <= chunk_bytes <= MAX_CHUNK_BYTES):
            raise ValueError("Invalid chunk size")
        if (not isinstance(request_timeout, (int, float)) or isinstance(request_timeout, bool)
                or not math.isfinite(request_timeout) or request_timeout <= 0):
            raise ValueError("Timeout must be positive and finite")
        try:
            self._base_url = ColabJupyterClient._validate_info(connection_info)
        except JupyterClientError:
            raise TransferError(TransferCode.INVALID_CONNECTION) from None
        run_id = uuid.uuid4().hex if run_id is None else run_id
        if not isinstance(run_id, str) or not _RUN_ID.fullmatch(run_id):
            raise TransferError(TransferCode.REMOTE_PATH_INVALID)
        self.run_id = run_id
        self.run_dir = f"{REMOTE_ROOT}/{run_id}"
        self._file_path = re.compile(re.escape(self.run_dir) + r"/chunk-\d{5}\.mp3")
        self._info = connection_info
        self._refresh = refresh_connection
        self._http_request = http_request
        self._chunk_bytes = chunk_bytes
        self._timeout = float(request_timeout)
        self._utcnow = utcnow
        self._lock = threading.RLock()
        self._cancel = threading.Event()
        self._prepared = False
        self._closed = False
        self._halt = None
        self._run_dir_state = "ABSENT"   # ABSENT / CREATED / UNCERTAIN / DELETED
        self._records = {}
        self._local_keys = {}

    # ---- connection -------------------------------------------------------

    def refresh_connection(self):
        with self._lock:
            valid = False
            try:
                if self._refresh is not None:
                    updated = self._refresh()
                    valid = (ColabJupyterClient._validate_info(updated) == self._base_url
                             and updated.expire_time > self._utcnow())
            except Exception:
                pass
            if not valid:
                raise TransferError(TransferCode.TOKEN_REFRESH_REQUIRED)
            self._info = updated

    def remote_path_for(self, index):
        if type(index) is not int or not 0 <= index <= MAX_INDEX:
            raise TransferError(TransferCode.REMOTE_PATH_INVALID)
        return self._guard(f"{self.run_dir}/chunk-{index:05d}{LOCAL_SUFFIX}")

    def matches_connection(self, connection_info):
        """Read-only binding check for consumers of this run's owned files.

        A refreshed token must first be installed by refresh_connection(); this
        never retargets a transfer or claims ownership of another Runtime.
        """
        with self._lock:
            try:
                return (ColabJupyterClient._validate_info(connection_info) == self._base_url
                        and connection_info.token == self._info.token)
            except JupyterClientError:
                return False

    def _guard(self, path):
        if not isinstance(path, str) or not (
                path in (REMOTE_ROOT, self.run_dir) or self._file_path.fullmatch(path)):
            raise TransferError(TransferCode.REMOTE_PATH_INVALID)
        return path

    def _request(self, method, path, body=None, query=""):
        path = self._guard(path)
        if self._info.expire_time <= self._utcnow():
            raise TransferError(TransferCode.TOKEN_REFRESH_REQUIRED)
        url = self._base_url + "/api/contents/" + quote(path, safe="/") + query
        headers = {"X-Colab-Runtime-Proxy-Token": self._info.token,
                   "Content-Type": "application/json"}
        try:
            return self._http_request(method, url, headers, body, self._timeout)
        except JupyterClientError as exc:
            code = {"NETWORK_TIMEOUT": TransferCode.NETWORK_TIMEOUT,
                    "CONNECTION_REJECTED": TransferCode.CONNECTION_REJECTED}.get(
                        exc.code.value, TransferCode.STATE_UNCERTAIN)
            raise TransferError(code) from None
        except Exception:
            # Never chain raw transport exceptions (they may carry URL/token).
            raise TransferError(TransferCode.STATE_UNCERTAIN) from None

    def _check_open(self):
        if self._closed:
            raise TransferError(TransferCode.TRANSFER_CLOSED)
        if self._halt is not None:
            raise TransferError(self._halt)
        if self._cancel.is_set():
            raise TransferError(TransferCode.CANCELLED)

    def _halt_if_fatal(self, code):
        if code in _HALT_CODES:
            self._halt = code

    # ---- remote directory -------------------------------------------------

    def prepare(self):
        """Create (or reuse) the shared root and create a NEW run directory."""
        with self._lock:
            self._check_open()
            if self._prepared:
                return self.run_dir
            try:
                status, payload = self._request("GET", REMOTE_ROOT, query="?content=0")
                if status == 404:
                    status, payload = self._request("PUT", REMOTE_ROOT, {"type": "directory"})
                    if status not in (200, 201):
                        raise TransferError(_status_code(status) or TransferCode.UPLOAD_REJECTED)
                elif status != 200:
                    raise TransferError(_status_code(status) or TransferCode.RESPONSE_INVALID)
                if not (isinstance(payload, dict) and payload.get("type") == "directory"
                        and payload.get("path") == REMOTE_ROOT):
                    raise TransferError(TransferCode.REMOTE_PATH_INVALID)

                status, _ = self._request("GET", self.run_dir, query="?content=0")
                if status == 200:
                    raise TransferError(TransferCode.REMOTE_EXISTS)
                if status != 404:
                    raise TransferError(_status_code(status) or TransferCode.RESPONSE_INVALID)
                self._run_dir_state = "UNCERTAIN"  # PUT may succeed despite reply loss
                try:
                    status, payload = self._request("PUT", self.run_dir, {"type": "directory"})
                except TransferError:
                    raise TransferError(TransferCode.STATE_UNCERTAIN) from None
                if status == 201:
                    if not (isinstance(payload, dict) and payload.get("type") == "directory"
                            and payload.get("path") == self.run_dir):
                        raise TransferError(TransferCode.RESPONSE_INVALID)
                    self._run_dir_state = "CREATED"
                elif status == 200:
                    # Appeared concurrently: not provably ours, never delete it.
                    self._run_dir_state = "ABSENT"
                    raise TransferError(TransferCode.REMOTE_EXISTS)
                elif 400 <= status < 500:
                    self._run_dir_state = "ABSENT"
                    raise TransferError(_status_code(status) or TransferCode.UPLOAD_REJECTED)
                else:
                    raise TransferError(TransferCode.STATE_UNCERTAIN)
            except TransferError as exc:
                self._halt_if_fatal(exc.code)
                raise
            self._prepared = True
            return self.run_dir

    # ---- upload -----------------------------------------------------------

    def cancel(self):
        """Stops before the next request; an in-flight request is not aborted."""
        self._cancel.set()

    def records(self):
        with self._lock:
            return tuple(self._records[key] for key in sorted(self._records))

    def upload(self, index, local_path) -> FileTransferRecord:
        with self._lock:
            self._check_open()
            if not self._prepared:
                raise TransferError(TransferCode.NOT_PREPARED)
            remote = self.remote_path_for(index)
            previous = self._records.get(index)
            if previous is not None and not previous.retryable:
                raise TransferError(TransferCode.DUPLICATE_UPLOAD)
            attempts = 1 if previous is None else previous.attempts + 1
            if attempts > MAX_ATTEMPTS_PER_INDEX:
                raise TransferError(TransferCode.ATTEMPTS_EXHAUSTED)
            try:
                resolved = Path(os.fspath(local_path)).resolve(strict=True)
            except (OSError, TypeError, ValueError, RuntimeError):
                resolved = None
            if resolved is not None:
                key = os.path.normcase(str(resolved))
                owner = self._local_keys.get(key)
                if owner is not None and owner != index:
                    raise TransferError(TransferCode.DUPLICATE_UPLOAD)
                self._local_keys[key] = index
            record = self._upload_one(index, remote, resolved, attempts)
            self._records[index] = record
            return record

    def _inspect_local(self, path):
        if path is None or path.suffix.lower() != LOCAL_SUFFIX:
            raise _Fail(TransferCode.LOCAL_FILE_INVALID)
        try:
            info = os.lstat(path)
            if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_FILE_BYTES:
                raise _Fail(TransferCode.LOCAL_FILE_INVALID)
            digest = hashlib.sha256()
            total = 0
            with open(path, "rb") as handle:
                while True:
                    block = handle.read(self._chunk_bytes)
                    if not block:
                        break
                    total += len(block)
                    digest.update(block)
            after = os.stat(path)
        except OSError:
            raise _Fail(TransferCode.LOCAL_FILE_INVALID) from None
        if (total != info.st_size or after.st_size != info.st_size
                or after.st_mtime_ns != info.st_mtime_ns):
            raise _Fail(TransferCode.LOCAL_FILE_CHANGED)
        return _LocalSnapshot(info.st_size, info.st_mtime_ns, digest.hexdigest())

    def _upload_one(self, index, remote, local, attempts):
        snapshot = None
        chunks_total = acked = 0
        remote_may_exist = False
        ownership = RemoteOwnership.NONE
        all_sent = False
        size_confirmed = False

        def record(status, integrity=IntegrityLevel.NONE, error=None, verify_error=None):
            return FileTransferRecord(
                index=index, remote_path=remote,
                size=snapshot.size if snapshot else None,
                sha256=snapshot.sha256 if snapshot else None,
                chunks_total=chunks_total, chunks_acknowledged=acked,
                status=status, integrity=integrity, error_code=error,
                verification_error=verify_error, remote_may_exist=remote_may_exist,
                all_chunks_sent=all_sent, attempts=attempts, ownership=ownership)

        try:
            snapshot = self._inspect_local(local)
            chunks_total = math.ceil(snapshot.size / self._chunk_bytes)
            sequence = _ChunkSequence(chunks_total)
            try:
                status, _ = self._request("GET", remote, query="?content=0")
            except TransferError as exc:
                raise _Fail(exc.code) from None
            if status == 200:
                raise _Fail(TransferCode.REMOTE_EXISTS)  # never overwrite
            if status != 404:
                raise _Fail(_status_code(status) or TransferCode.RESPONSE_INVALID)

            digest = hashlib.sha256()
            offset = 0
            with open(local, "rb") as handle:
                opened = os.fstat(handle.fileno())
                if (opened.st_size != snapshot.size
                        or opened.st_mtime_ns != snapshot.mtime_ns):
                    raise _Fail(TransferCode.LOCAL_FILE_CHANGED)
                while not sequence.complete:
                    if self._cancel.is_set():
                        raise _Fail(TransferCode.CANCELLED)
                    number, marker = sequence.issue()
                    expected = min(self._chunk_bytes, snapshot.size - offset)
                    block = handle.read(self._chunk_bytes)
                    if len(block) != expected:
                        raise _Fail(TransferCode.LOCAL_FILE_CHANGED)
                    digest.update(block)
                    body = {"type": "file", "format": "base64",
                            "content": base64.b64encode(block).decode("ascii")}
                    del block
                    if marker is not None:
                        body["chunk"] = marker
                    if self._info.expire_time <= self._utcnow():
                        raise _Fail(TransferCode.TOKEN_REFRESH_REQUIRED)
                    if number == 1:
                        # Sent but not yet proven created: never deletable as-is.
                        remote_may_exist = True
                        ownership = RemoteOwnership.UNCERTAIN
                    all_sent = number == chunks_total
                    try:
                        status, payload = self._request("PUT", remote, body)
                    except TransferError:
                        raise _Fail(TransferCode.STATE_UNCERTAIN, uncertain=True) from None
                    finally:
                        del body
                    if status != (201 if number == 1 else 200):
                        if number == 1 and status == 200:
                            # Another writer created the path after our GET 404 and
                            # the server saved over it. Not ours: never delete, retry,
                            # move or promote it.
                            ownership = RemoteOwnership.CONFLICT
                            raise _Fail(TransferCode.REMOTE_EXISTS, uncertain=True)
                        fatal = _status_code(status)
                        if status is not None and 400 <= status < 500:
                            all_sent = False  # a 4xx reply means this chunk was not applied
                            if number == 1:
                                remote_may_exist = False
                                ownership = RemoteOwnership.NONE
                            raise _Fail(fatal or TransferCode.UPLOAD_REJECTED)
                        raise _Fail(TransferCode.STATE_UNCERTAIN, uncertain=True)
                    is_final = number == chunks_total
                    # ContentsManager documents intermediate models as unreliable.
                    # Only the first PUT's ownership proof and the final saved
                    # model require path/type; later interim ACKs use HTTP/order.
                    # An incomplete first 201 remains blocked: a GET (also
                    # unreliable before final save) cannot prove who created it.
                    if number == 1 or is_final:
                        if not (isinstance(payload, dict) and payload.get("path") == remote
                                and payload.get("type") == "file"):
                            raise _Fail(TransferCode.RESPONSE_INVALID, uncertain=True)
                    if number == 1:
                        ownership = RemoteOwnership.OWNED  # 201 + matching model
                    offset += expected
                    if is_final:
                        reported = payload.get("size")
                        if isinstance(reported, int) and not isinstance(reported, bool):
                            if reported != snapshot.size:
                                # Only final metadata can detect remote loss or
                                # duplication; interim sizes prove no byte count.
                                raise _Fail(TransferCode.INTEGRITY_MISMATCH)
                            size_confirmed = True
                    sequence.acknowledge(number)
                    acked = number
                if handle.read(1):
                    raise _Fail(TransferCode.LOCAL_FILE_CHANGED)
            final = os.stat(local)
            if (digest.hexdigest() != snapshot.sha256 or final.st_size != snapshot.size
                    or final.st_mtime_ns != snapshot.mtime_ns):
                raise _Fail(TransferCode.LOCAL_FILE_CHANGED)
        except _Fail as fail:
            self._halt_if_fatal(fail.code)
            status = TransferStatus.STATE_UNCERTAIN if fail.uncertain else TransferStatus.FAILED
            return record(status, error=fail.code)
        except TransferError as exc:
            return record(TransferStatus.FAILED, error=exc.code)

        integrity = (IntegrityLevel.SIZE_CONFIRMED if size_confirmed
                     else IntegrityLevel.RESPONSE_ONLY)
        verified, verify_error = self._verify(remote, snapshot)
        if verify_error is TransferCode.INTEGRITY_MISMATCH:
            return record(TransferStatus.FAILED, error=verify_error)
        if verified is IntegrityLevel.CONTENT_SHA256:
            return record(TransferStatus.VERIFIED, verified)
        if verified is IntegrityLevel.SIZE_CONFIRMED:
            integrity = verified
        return record(TransferStatus.ACKNOWLEDGED, integrity, verify_error=verify_error)

    def _verify(self, remote, snapshot):
        """Return (IntegrityLevel|None, TransferCode|None); never re-sends data."""
        try:
            status, payload = self._request("GET", remote, query="?content=0&hash=1")
        except TransferError as exc:
            return None, exc.code
        if status == 404:
            return None, TransferCode.INTEGRITY_MISMATCH
        if status != 200:
            code = _status_code(status) or TransferCode.RESPONSE_INVALID
            self._halt_if_fatal(code)
            return None, code
        if not (isinstance(payload, dict) and payload.get("path") == remote
                and payload.get("type") == "file"):
            return None, TransferCode.RESPONSE_INVALID
        size = payload.get("size")
        size_ok = isinstance(size, int) and not isinstance(size, bool)
        if size_ok and size != snapshot.size:
            return None, TransferCode.INTEGRITY_MISMATCH
        digest, algorithm = payload.get("hash"), payload.get("hash_algorithm")
        if (isinstance(digest, str) and isinstance(algorithm, str)
                and algorithm.lower() == "sha256" and _SHA256.fullmatch(digest.lower())):
            if digest.lower() != snapshot.sha256:
                return None, TransferCode.INTEGRITY_MISMATCH
            return IntegrityLevel.CONTENT_SHA256, None
        return (IntegrityLevel.SIZE_CONFIRMED if size_ok else None), None

    def reconcile(self, index) -> FileTransferRecord:
        """Explicit, read-only check of an uncertain upload. Only a matching
        remote SHA256 promotes it; size alone leaves it STATE_UNCERTAIN."""
        with self._lock:
            self._check_open()
            current = self._records.get(index)
            if current is None:
                raise TransferError(TransferCode.NOT_OWNED)
            if (current.status is not TransferStatus.STATE_UNCERTAIN
                    or not current.all_chunks_sent or current.sha256 is None):
                return current
            snapshot = _LocalSnapshot(current.size, 0, current.sha256)
            verified, error = self._verify(current.remote_path, snapshot)
            if verified is IntegrityLevel.CONTENT_SHA256:
                updated = replace(current, status=TransferStatus.VERIFIED,
                                  integrity=verified, chunks_acknowledged=current.chunks_total,
                                  verification_error=None)
            else:
                updated = replace(current, verification_error=error)
            self._records[index] = updated
            return updated

    # ---- cleanup ----------------------------------------------------------

    def cleanup(self) -> CleanupReport:
        """Delete only OWNED remote files, then the run directory if it is
        provably empty. Unproven paths are skipped, never DELETEd.
        Closes the transfer. May be called again explicitly to retry."""
        with self._lock:
            self._closed = True
            self._cancel.set()
            deleted, failed, skipped = [], [], []
            stop = None
            for index in sorted(self._records):
                current = self._records[index]
                if not current.remote_may_exist or current.remote_deleted:
                    continue
                if current.ownership is not RemoteOwnership.OWNED:
                    code = (TransferCode.REMOTE_EXISTS
                            if current.ownership is RemoteOwnership.CONFLICT
                            else TransferCode.STATE_UNCERTAIN)
                    skipped.append((current.remote_path, code))
                    continue
                if stop is not None:
                    failed.append((current.remote_path, stop))
                    continue
                code = self._delete_owned(current.remote_path)
                if code is None:
                    self._records[index] = replace(current, remote_deleted=True)
                    deleted.append(current.remote_path)
                else:
                    failed.append((current.remote_path, code))
                    if code in _HALT_CODES or code is TransferCode.TOKEN_REFRESH_REQUIRED:
                        stop = code  # one pass, no hammering a rejecting server
            run_dir_deleted = self._run_dir_state == "DELETED"
            if self._run_dir_state in ("CREATED", "UNCERTAIN"):
                if failed:
                    failed.append((self.run_dir, stop or TransferCode.DELETE_FAILED))
                elif skipped:
                    # May hold content we do not own: leave it for the owner/caller.
                    skipped.append((self.run_dir, TransferCode.NOT_OWNED))
                else:
                    listing = self._run_dir_listing()
                    if listing == "EMPTY":
                        code = self._delete_owned(self.run_dir)
                        if code is None:
                            self._run_dir_state = "DELETED"
                            run_dir_deleted = True
                            deleted.append(self.run_dir)
                        else:
                            failed.append((self.run_dir, code))
                    elif listing == "ABSENT":
                        self._run_dir_state = "DELETED"
                        run_dir_deleted = True
                    else:
                        skipped.append((self.run_dir, listing))
            unresolved = failed + skipped
            return CleanupReport(
                deleted_paths=tuple(deleted), failed_paths=tuple(failed),
                run_dir_deleted=run_dir_deleted, cleanup_required=bool(unresolved),
                error_code=unresolved[0][1] if unresolved else None,
                skipped_paths=tuple(skipped))

    def _run_dir_listing(self):
        """'EMPTY', 'ABSENT', or a TransferCode meaning: do not DELETE.
        Listing-then-DELETE is not atomic either; it only narrows the window."""
        try:
            status, payload = self._request("GET", self.run_dir, query="?content=1")
        except TransferError as exc:
            return exc.code
        if status == 404:
            return "ABSENT"
        if status != 200:
            return _status_code(status) or TransferCode.RESPONSE_INVALID
        if not (isinstance(payload, dict) and payload.get("type") == "directory"
                and payload.get("path") == self.run_dir
                and isinstance(payload.get("content"), list)):
            return TransferCode.RESPONSE_INVALID
        return "EMPTY" if not payload["content"] else TransferCode.REMOTE_EXISTS

    def _owned(self, path):
        if path == self.run_dir:
            return self._run_dir_state in ("CREATED", "UNCERTAIN") and not any(
                r.remote_may_exist and not r.remote_deleted
                and r.ownership is not RemoteOwnership.OWNED
                for r in self._records.values())
        return any(r.remote_path == path and r.remote_may_exist
                   and r.ownership is RemoteOwnership.OWNED
                   for r in self._records.values())

    def _delete_owned(self, path):
        if not self._owned(path):
            return TransferCode.NOT_OWNED
        try:
            status, _ = self._request("DELETE", path)
        except TransferError as exc:
            return exc.code
        if status in (204, 404):
            return None
        return _status_code(status) or TransferCode.DELETE_FAILED
