"""Crash-safe Runtime attempt records; no tokens, URLs, Job/UI or live auth.

Default storage is per-user app data, instantiated only by an explicit caller.
Tests MUST pass their own directory. Account verification is a trusted adapter
bound to RuntimeClient's exact OAuth token; without it all remote work blocks.
Checksums detect corruption, not malicious edits by the current OS user. The
private ACL/owner and no-reparse checks are part of the trust boundary.
"""

import ctypes
import hashlib
import json
import os
import re
import stat
import threading
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from functools import lru_cache
from pathlib import Path

from src.services.colab_runtime_client import ColabRuntimeClient, RuntimeClientError, RuntimeErrorCode
from src.utils.paths import get_app_data_dir


class OwnershipState(str, Enum):
    PREPARED = "PREPARED"
    CREATE_UNCERTAIN = "CREATE_UNCERTAIN"
    ACTIVE_OWNED = "ACTIVE_OWNED"
    CLEANUP_REQUIRED = "CLEANUP_REQUIRED"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
    CLEANED = "CLEANED"
    BLOCKED = "BLOCKED"


def _blocked():
    return RuntimeClientError(RuntimeErrorCode.PRECONDITION_UNVERIFIED, cleanup_required=True)


def _uuid4(value):
    return isinstance(value, str) and str(uuid.UUID(value)) == value and uuid.UUID(value).version == 4


def _now():
    return datetime.now(timezone.utc).isoformat()


def _unique_object(pairs):
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError("Duplicate JSON field")
    return result


@dataclass(frozen=True)
class OwnershipRecord:
    execution_id: str
    request_id: str
    runtime_name: str
    account_binding: str
    state: OwnershipState = OwnershipState.PREPARED
    operation_name: str | None = None
    last_remote_state: str = "NOT_REQUESTED"
    cleanup_required: bool = True
    checked_at: str = ""

    def validate(self):
        try:
            valid = (
                _uuid4(self.execution_id) and _uuid4(self.request_id)
                and isinstance(self.runtime_name, str)
                and re.fullmatch(r"runtimes/sorigul-[0-9a-f]{32}", self.runtime_name)
                and isinstance(self.account_binding, str)
                and re.fullmatch(r"[0-9a-f]{64}", self.account_binding)
                and isinstance(self.state, OwnershipState)
                and (self.operation_name is None or (
                    isinstance(self.operation_name, str) and len(self.operation_name) <= 256
                    and re.fullmatch(r"operations/[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*", self.operation_name)))
                and self.last_remote_state in {"NOT_REQUESTED", "REQUEST_SENT_OR_PENDING", "OPERATION_OBSERVED",
                                               "CONFIRMED", "REJECTED", "ABSENT", "DELETED"}
                and type(self.cleanup_required) is bool
                and isinstance(self.checked_at, str)
                and datetime.fromisoformat(self.checked_at).utcoffset() is not None
            )
            if self.state == OwnershipState.CLEANED:
                valid = valid and not self.cleanup_required and self.last_remote_state in {"ABSENT", "DELETED"}
            if self.state == OwnershipState.ACTIVE_OWNED:
                valid = valid and self.operation_name is not None and self.last_remote_state == "CONFIRMED"
        except (ValueError, TypeError, AttributeError):
            valid = False
        if not valid:
            raise _blocked()
        return self


@dataclass(frozen=True)
class RecoveryResult:
    state: OwnershipState
    cleanup_required: bool
    error_code: RuntimeErrorCode | None = None
    local_transcription_available: bool = True  # Signal only; no engine switch.


@lru_cache(maxsize=1)
def _windows_sid():
    # Existing System32-only, no-shell SID resolver; never reads Drive auth.
    from src.services.drive import _resolve_current_windows_sid
    return _resolve_current_windows_sid()


def _windows_permissions(path, *, create=False):
    """Replace ACL only on a newly-created private object; inspect others."""
    from ctypes import wintypes
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    ptr = ctypes.c_void_p
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(ptr), ptr]
    advapi.SetFileSecurityW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ptr]
    advapi.GetFileSecurityW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ptr, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    advapi.ConvertSecurityDescriptorToStringSecurityDescriptorW.argtypes = [ptr, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ptr), ptr]
    kernel.LocalFree.argtypes = [ptr]
    sid = _windows_sid()
    if create:
        descriptor = ptr()
        flags = "OICI" if path.is_dir() else ""
        if not advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(
                f"O:{sid}D:P(A;{flags};FA;;;{sid})", 1, ctypes.byref(descriptor), None):
            raise _blocked()
        try:
            if not advapi.SetFileSecurityW(str(path), 0x80000005, descriptor):
                raise _blocked()
        finally:
            kernel.LocalFree(descriptor)
    needed = wintypes.DWORD()
    advapi.GetFileSecurityW(str(path), 5, None, 0, ctypes.byref(needed))
    if not needed.value:
        raise _blocked()
    buffer = ctypes.create_string_buffer(needed.value)
    if not advapi.GetFileSecurityW(str(path), 5, buffer, needed, ctypes.byref(needed)):
        raise _blocked()
    rendered = ptr()
    if not advapi.ConvertSecurityDescriptorToStringSecurityDescriptorW(buffer, 1, 5, ctypes.byref(rendered), None):
        raise _blocked()
    try:
        sddl = ctypes.wstring_at(rendered)
    finally:
        kernel.LocalFree(rendered)
    if not re.fullmatch(r"O:" + re.escape(sid) + r"D:P(?:AI)?\(A;[A-Z]*;FA;;;" + re.escape(sid) + r"\)", sddl):
        raise _blocked()


def _permissions(path, *, create=False):
    if os.name == "nt":
        _windows_permissions(path, create=create)
    else:
        if create:
            os.chmod(path, 0o700 if path.is_dir() else 0o600)
        attrs = path.lstat()
        if attrs.st_uid != os.getuid() or attrs.st_mode & 0o077:
            raise _blocked()


def _no_links(path, *, must_exist=True):
    # Check before resolve/open: never follow a symlink, junction or reparse.
    for entry in reversed((path, *path.parents)):
        try:
            attrs = entry.lstat()
        except FileNotFoundError:
            if entry == path and must_exist:
                raise _blocked()
            continue
        if stat.S_ISLNK(attrs.st_mode) or getattr(attrs, "st_file_attributes", 0) & 0x400:
            raise _blocked()
    if path.exists() and path.is_file() and path.stat().st_nlink != 1:
        raise _blocked()


@contextmanager
def _file_lock(path):
    """Persistent private lock, never delete/steal it. Kernel owns the lease."""
    descriptor = None
    locked = False
    try:
        _no_links(path, must_exist=False)
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
            _permissions(path, create=True)
            os.write(descriptor, b"0")
            os.fsync(descriptor)
        except FileExistsError:
            _permissions(path)
            descriptor = os.open(path, os.O_RDWR)
        if os.name == "nt":
            import msvcrt
            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        locked = True
        yield
    except OSError:
        raise _blocked() from None
    finally:
        if descriptor is not None:
            if locked:
                if os.name == "nt":
                    import msvcrt
                    os.lseek(descriptor, 0, os.SEEK_SET)
                    msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)


class OwnershipStore:
    """One immutable run identity per file; CAS updates under an OS file lock.

    No auto-reset/quarantine and no replacing earlier runs, even CLEANED ones.
    The persistent lock is never deleted/stolen. OS releases it on process loss.
    A missing publication after temp creation cannot have authorized a POST.
    """

    def __init__(self, root: Path | None = None):
        root = root if root is not None else get_app_data_dir() / "colab_runtime_ownership"
        if ".." in Path(root).parts:
            raise _blocked()
        self.root = Path(root).absolute()
        self._lock = threading.RLock()
        self._transaction_thread = None

    @contextmanager
    def transaction(self):
        with self._lock:
            try:
                _no_links(self.root, must_exist=False)
                if not self.root.exists():
                    self.root.mkdir(mode=0o700, parents=True)
                    _permissions(self.root, create=True)
                _permissions(self.root)
                with _file_lock(self.root / "ownership.lock"):
                    _no_links(self.root)
                    self._transaction_thread = threading.get_ident()
                    yield self
            except RuntimeClientError:
                raise
            except (OSError, ValueError):
                raise _blocked() from None
            finally:
                self._transaction_thread = None

    def execution_lease(self, execution_id):
        return _file_lock(self._path(execution_id).with_suffix(".lease"))

    def _path(self, execution_id):
        try:
            valid = _uuid4(execution_id)
        except ValueError:
            valid = False
        if not valid:
            raise _blocked()
        return self.root / (execution_id + ".json")

    def _read(self, path):
        _no_links(path)
        if not stat.S_ISREG(path.lstat().st_mode):
            raise _blocked()
        _permissions(path)
        try:
            with path.open("rb") as handle:
                raw = handle.read(16385)
            if len(raw) > 16384:
                raise ValueError
            envelope = json.loads(raw, object_pairs_hook=_unique_object)
            if set(envelope) != {"version", "record", "sha256"} or type(envelope["version"]) is not int or envelope["version"] != 1:
                raise ValueError
            payload = envelope["record"]
            if not isinstance(payload, dict) or set(payload) != set(OwnershipRecord.__dataclass_fields__):
                raise ValueError
            digest = hashlib.sha256(self._encode(payload)).hexdigest()
            if digest != envelope["sha256"]:
                raise ValueError
            fields = dict(payload)
            fields["state"] = OwnershipState(fields["state"])
            record = OwnershipRecord(**fields).validate()
            if self._path(record.execution_id) != path:
                raise ValueError
            return record
        except (ValueError, TypeError, KeyError, UnicodeError):
            raise _blocked() from None

    @staticmethod
    def _encode(payload):
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def _records(self):
        paths = list(self.root.glob("*.json"))
        if len(paths) > 128:
            raise _blocked()  # Explicit maintenance, never auto-prune history.
        return [self._read(path) for path in paths]

    def load(self):
        with self.transaction():
            return self._records()

    def _save(self, record, *, expected=None):
        if self._transaction_thread != threading.get_ident():
            raise _blocked()
        record.validate()
        path = self._path(record.execution_id)
        _no_links(path, must_exist=False)
        if expected is None:
            if path.exists():
                raise _blocked()
        elif not path.exists() or self._read(path) != expected:
            raise _blocked()
        if expected is not None and any(getattr(record, key) != getattr(expected, key) for key in
                ("execution_id", "request_id", "runtime_name", "account_binding")):
            raise _blocked()
        data = asdict(record)
        envelope = {"version": 1, "record": data,
                    "sha256": hashlib.sha256(self._encode(data)).hexdigest()}
        temp = self.root / ("." + uuid.uuid4().hex + ".tmp")
        try:
            fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as handle:
                _permissions(temp, create=True)
                handle.write(self._encode(envelope))
                handle.flush()
                os.fsync(handle.fileno())
            _no_links(path, must_exist=False)
            if expected is None and path.exists():
                raise _blocked()
            os.replace(temp, path)
            if os.name != "nt":
                directory = os.open(self.root, os.O_RDONLY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            if self._read(path) != record:
                raise _blocked()
        finally:
            if temp.exists():
                temp.unlink()


class RuntimeOwnership:
    """Explicit create/recover service, not wired to startup, Job or UI.

    Holds the storage lock throughout bounded API work. Other processes fail
    closed rather than racing another create or deleting an active owner.
    """

    def __init__(self, store: OwnershipStore, client: ColabRuntimeClient):
        self.store, self.client = store, client
        self._record = None
        self._lease = None

    def close(self):
        """Release this process's lease only; never claim remote cleanup."""
        if self._lease is not None:
            self._lease.__exit__(None, None, None)
            self._lease = None

    def _acquire_lease(self):
        if self._lease is None:
            lease = self.store.execution_lease(self._record.execution_id)
            lease.__enter__()
            self._lease = lease

    def _update(self, **changes):
        previous = self._record
        updated = replace(previous, checked_at=_now(), **changes).validate()
        self.store._save(updated, expected=previous)
        self._record = updated

    def _checkpoint(self, phase, operation_name):
        phases = {
            "CREATE_STARTED": (OwnershipState.CREATE_UNCERTAIN, "REQUEST_SENT_OR_PENDING", True),
            "OPERATION_OBSERVED": (OwnershipState.RECOVERY_REQUIRED, "OPERATION_OBSERVED", True),
            "RUNTIME_CONFIRMED": (OwnershipState.ACTIVE_OWNED, "CONFIRMED", True),
            "CREATE_REJECTED": (OwnershipState.BLOCKED, "REJECTED", False),
            "ABSENCE_CONFIRMED": (OwnershipState.CLEANED, "ABSENT", False),
            "DELETED": (OwnershipState.CLEANED, "DELETED", False),
        }
        if phase not in phases:
            raise _blocked()
        state, remote, cleanup = phases[phase]
        self._update(state=state, last_remote_state=remote,
                     cleanup_required=cleanup, operation_name=operation_name)

    def create(self):
        with self.store.transaction():
            if not self.client.creation_available:
                raise RuntimeClientError(RuntimeErrorCode.DUPLICATE_CREATE,
                                         cleanup_required=self.client.cleanup_required)
            records = self.store._records()
            if any(record.state != OwnershipState.CLEANED for record in records):
                raise RuntimeClientError(RuntimeErrorCode.DUPLICATE_CREATE, cleanup_required=True)
            binding = self.client.verified_account_binding()
            self._record = OwnershipRecord(
                execution_id=str(uuid.uuid4()), request_id=self.client.request_id,
                runtime_name=self.client.candidate_runtime_name,
                account_binding=binding, checked_at=_now(),
            ).validate()
            self.store._save(self._record)
            self._acquire_lease()
            try:
                return self.client.create_runtime(checkpoint=self._checkpoint, account_binding=binding)
            except BaseException:
                self.close()
                raise

    def cleanup(self):
        """Clean this live instance only while its durable storage lock is held."""
        with self.store.transaction():
            if self._record is None:
                raise _blocked()
            self._record = self.store._read(self.store._path(self._record.execution_id))
            if self._record.state == OwnershipState.CLEANED:
                return RecoveryResult(OwnershipState.CLEANED, False)
            if (self.client.verified_account_binding() != self._record.account_binding
                    or self._record.state not in {OwnershipState.ACTIVE_OWNED, OwnershipState.CLEANUP_REQUIRED}):
                return RecoveryResult(OwnershipState.BLOCKED, True, RuntimeErrorCode.NOT_OWNED)
            self._acquire_lease()
            self._update(state=OwnershipState.CLEANUP_REQUIRED)
            try:
                self.client.delete_owned_runtime()
            except RuntimeClientError as exc:
                return RecoveryResult(OwnershipState.CLEANUP_REQUIRED, True, exc.code)
            self.close()
            return RecoveryResult(self._record.state, self._record.cleanup_required)

    def recover(self, execution_id):
        """No POST or broad list API. Missing proof never permits deletion."""
        try:
            with self.store.transaction():
                self._record = self.store._read(self.store._path(execution_id))
                if self._record.state == OwnershipState.CLEANED:
                    return RecoveryResult(OwnershipState.CLEANED, False)
                try:
                    binding = self.client.verified_account_binding()
                except RuntimeClientError:
                    return RecoveryResult(OwnershipState.BLOCKED, True, RuntimeErrorCode.PRECONDITION_UNVERIFIED)
                if binding != self._record.account_binding:
                    return RecoveryResult(OwnershipState.BLOCKED, True, RuntimeErrorCode.NOT_OWNED)
                if self._record.state == OwnershipState.BLOCKED:
                    return RecoveryResult(OwnershipState.BLOCKED, self._record.cleanup_required, RuntimeErrorCode.NOT_OWNED)
                self._acquire_lease()
                self._update(state=OwnershipState.RECOVERY_REQUIRED)
                if self._record.operation_name is None:
                    return RecoveryResult(OwnershipState.RECOVERY_REQUIRED, True, RuntimeErrorCode.STATE_UNCERTAIN)
                try:
                    runtime = self.client.recover_attempt(
                        request_id=self._record.request_id, runtime_name=self._record.runtime_name,
                        operation_name=self._record.operation_name, account_binding=binding,
                        checkpoint=self._checkpoint,
                    )
                    if runtime is not None:
                        self._update(state=OwnershipState.CLEANUP_REQUIRED)
                        self.client.delete_owned_runtime()
                    return RecoveryResult(self._record.state, self._record.cleanup_required)
                except RuntimeClientError as exc:
                    if self._record.state == OwnershipState.BLOCKED:
                        return RecoveryResult(OwnershipState.BLOCKED, self._record.cleanup_required, exc.code)
                    state = (OwnershipState.CLEANUP_REQUIRED if exc.code == RuntimeErrorCode.DELETE_FAILED
                             else OwnershipState.RECOVERY_REQUIRED)
                    self._update(state=state, cleanup_required=True)
                    return RecoveryResult(state, True, exc.code)
        except (RuntimeClientError, OSError):
            return RecoveryResult(OwnershipState.BLOCKED, True, RuntimeErrorCode.PRECONDITION_UNVERIFIED)
        finally:
            self.close()
