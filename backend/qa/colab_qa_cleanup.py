"""QA cleanup evidence bridge: product cleanup THEN independent absence probes.

Product contracts are unchanged. Product file cleanup treats DELETE 204/404 as
done, and product Runtime cleanup checkpoints CLEANED on DELETE. Neither alone
is QA evidence. Here PASS needs, separately:
- files: owned target + clean product report + target GET 404 + run-dir GET 404
- Runtime: verified same account + DELETE result + GET 404 + complete list
  without it (and no other uncertain sorigul Runtime) + durable CLEANED record
Probes are read-only (GET). Anything but an exact 404 / complete listing is
UNCERTAIN, which maps to None and can never become PASS. No retries.
"""
from dataclasses import dataclass
from enum import Enum
import re
from urllib.error import HTTPError

import httpx

from qa.colab_qa_deadline import bounded_timeout
from qa.colab_qa_run import FileCleanupEvidence, RuntimeCleanupEvidence
from src.services.colab_jupyter_files import CleanupReport, RemoteOwnership
from src.services.colab_runtime_client import API_ROOT
from src.services.colab_runtime_ownership import OwnershipState, RecoveryResult

_RUNTIME = re.compile(r"runtimes/sorigul-[0-9a-f]{32}")
_RUN_DIR = re.compile(r"sorigul-transfer/[0-9a-f]{32}")
MAX_LIST_PAGES = 5


class Presence(str, Enum):
    ABSENT = "ABSENT"
    PRESENT = "PRESENT"
    UNCERTAIN = "UNCERTAIN"


def _fact(presence):
    """ABSENT -> True, PRESENT -> False, anything else -> None (unverified)."""
    return {Presence.ABSENT: True, Presence.PRESENT: False}.get(presence)


def _quiet_close(resource):
    try:
        resource.close()
    except Exception:
        pass


class NativeContentsPresenceProbe:
    """GET ?content=0 of the two pinned owned paths only. Never DELETE.

    The wire is the explicit NativeReadbackWire boundary (proxy-token header,
    TLS verified, no proxies/redirects). Tests inject a fake wire only.
    """

    def __init__(self, *, wire, approved_base, run_dir, file_path):
        if (not isinstance(approved_base, str) or not approved_base.startswith("https://")
                or not isinstance(run_dir, str) or not _RUN_DIR.fullmatch(run_dir)
                or not isinstance(file_path, str)
                or not re.fullmatch(re.escape(run_dir) + r"/chunk-[0-9]{5}\.mp3", file_path)):
            raise ValueError("QA_PROBE_CONFIG_INVALID")
        self._wire, self._base = wire, approved_base
        self.run_dir, self.file_path = run_dir, file_path

    def __repr__(self):
        return "NativeContentsPresenceProbe(<private>)"

    def presence(self, path, *, token, timeout_seconds):
        if path not in (self.run_dir, self.file_path) or not bounded_timeout(timeout_seconds):
            return Presence.UNCERTAIN
        url = self._base + "/api/contents/" + path + "?content=0"
        try:
            manager = self._wire.open(url, token, timeout_seconds)
        except HTTPError as exc:
            status = exc.code
            _quiet_close(exc)
            return Presence.ABSENT if status == 404 else Presence.UNCERTAIN
        except Exception:
            return Presence.UNCERTAIN
        try:
            with manager as raw:
                if raw.geturl() != url:
                    return Presence.UNCERTAIN
                return Presence.PRESENT if raw.status == 200 else Presence.UNCERTAIN
        except Exception:
            return Presence.UNCERTAIN


class NativeRuntimePresenceProbe:
    """Read-only GET of one owned name plus bounded runtimes.list.

    The caller supplies an httpx.Client already bound to the verified account's
    token, with redirects and environment proxies disabled. Never DELETE/POST.
    """

    def __init__(self, http, runtime_name):
        if (type(http) is not httpx.Client or http.follow_redirects is not False
                or http.trust_env is not False
                or not isinstance(runtime_name, str) or not _RUNTIME.fullmatch(runtime_name)):
            raise ValueError("QA_PROBE_CONFIG_INVALID")
        self._http, self.runtime_name = http, runtime_name

    def __repr__(self):
        return "NativeRuntimePresenceProbe(<private>)"

    def _get(self, path, timeout_seconds, params=None):
        if not bounded_timeout(timeout_seconds):
            return None, None
        try:
            response = self._http.request("GET", API_ROOT + path, params=params,
                                          timeout=timeout_seconds)
            status = response.status_code
            try:
                payload = response.json()
            except ValueError:
                payload = None
            return status, payload
        except Exception:
            return None, None  # Never keep raw httpx errors (URLs/headers).

    def get(self, *, timeout_seconds):
        status, payload = self._get("/v1beta/" + self.runtime_name, timeout_seconds)
        if status == 404:
            return Presence.ABSENT
        if status == 200 and isinstance(payload, dict) and payload.get("name") == self.runtime_name:
            return Presence.PRESENT
        return Presence.UNCERTAIN

    def list(self, *, timeout_seconds):
        """(our Presence, other sorigul Runtime seen: True/False/None)."""
        names, token = set(), None
        for _ in range(MAX_LIST_PAGES):
            status, payload = self._get("/v1beta/runtimes", timeout_seconds,
                                        params={"pageToken": token} if token else None)
            if (status != 200 or not isinstance(payload, dict)
                    or not set(payload) <= {"runtimes", "nextPageToken"}):
                return Presence.UNCERTAIN, None  # e.g. 200 {"error": ...} is not a listing.
            runtimes = payload.get("runtimes", [])
            if not isinstance(runtimes, list) or any(
                    not isinstance(item, dict) or not isinstance(item.get("name"), str)
                    for item in runtimes):
                return Presence.UNCERTAIN, None
            names.update(item["name"] for item in runtimes)
            token = payload.get("nextPageToken")
            if token in (None, ""):
                others = any(name.startswith("runtimes/sorigul-") and name != self.runtime_name
                             for name in names)
                return (Presence.PRESENT if self.runtime_name in names else Presence.ABSENT), others
            if not isinstance(token, str):
                return Presence.UNCERTAIN, None
        return Presence.UNCERTAIN, None  # Incomplete listing is never absence.


@dataclass(frozen=True)
class FileCleanupDetail:
    evidence: FileCleanupEvidence
    ownership_conflict: bool | None


def confirm_file_cleanup(*, transfer, file_path, probe, connection_token, timeout_seconds,
                         after_step=lambda: None):
    """Run product file cleanup once, then probe absence independently.

    connection_token() must re-derive the proxy token from the trusted owned
    Runtime observation; a failure leaves both absence facts unverified.
    """
    delete_confirmed, conflict = False, None
    try:
        records = tuple(transfer.records())
        conflict = any(r.remote_may_exist and not r.remote_deleted
                       and r.ownership is not RemoteOwnership.OWNED for r in records)
        target_owned = sum(1 for r in records if r.remote_path == file_path
                           and r.ownership is RemoteOwnership.OWNED and r.remote_may_exist) == 1
        report = transfer.cleanup()
        delete_confirmed = (type(report) is CleanupReport and target_owned and not conflict
                            and report.cleanup_required is False and not report.failed_paths
                            and not report.skipped_paths and file_path in report.deleted_paths
                            and report.run_dir_deleted is True
                            and report.runtime_cleanup_claimed is False)
    except Exception:
        delete_confirmed = False
    after_step()
    file_absent = directory_absent = None
    try:
        token = connection_token()
    except Exception:
        token = None
    if isinstance(token, str) and token:
        file_absent = _fact(probe.presence(file_path, token=token, timeout_seconds=timeout_seconds))
        after_step()
        directory_absent = _fact(probe.presence(probe.run_dir, token=token,
                                                timeout_seconds=timeout_seconds))
        after_step()
    return FileCleanupDetail(FileCleanupEvidence(delete_confirmed, file_absent, directory_absent),
                             conflict)


@dataclass(frozen=True)
class RuntimeCleanupDetail:
    evidence: RuntimeCleanupEvidence
    account_binding_matched: bool | None
    uncertain_runtime_found: bool | None
    delete_attempted: bool


def _durable_cleaned(store, pin):
    """True only for this exact identity in a durable CLEANED state."""
    try:
        matches = [r for r in store.load() if r.execution_id == pin.execution_id]
    except Exception:
        return None
    if len(matches) != 1:
        return None
    record = matches[0]
    if (record.request_id, record.runtime_name, record.account_binding) != (
            pin.request_id, pin.runtime_name, pin.account_binding):
        return False
    return (record.state is OwnershipState.CLEANED and record.cleanup_required is False
            and record.last_remote_state in {"DELETED", "ABSENT"})


def confirm_runtime_cleanup(*, owner_cleanup, probe, store, pin, verify_account, authorized,
                            timeout_seconds, after_step=lambda: None):
    """DELETE only after a same-account/identity check; then read-only proof.

    `authorized()` re-checks lease + durable identity immediately before DELETE.
    A failed check never deletes. Probes still run for diagnostics only.
    """
    def account():
        try:
            return verify_account() == pin.account_binding
        except Exception:
            return None
    matched = account()
    delete_confirmed, attempted = False, False
    if matched is True and authorized() is True:
        attempted = True
        try:
            result = owner_cleanup()
            delete_confirmed = (type(result) is RecoveryResult and result.state is OwnershipState.CLEANED
                                and result.cleanup_required is False and result.error_code is None)
        except Exception:
            delete_confirmed = None  # Outcome of an interrupted DELETE is unknown.
    after_step()
    get_absent = _fact(probe.get(timeout_seconds=timeout_seconds))
    after_step()
    ours, others = probe.list(timeout_seconds=timeout_seconds)
    after_step()
    list_absent = _fact(ours)
    if list_absent is True and others is not False:
        list_absent = None  # Another sorigul Runtime of unknown ownership: never PASS.
    after = account()
    if after is not True:
        matched = after if matched is True else matched
    cleaned = _durable_cleaned(store, pin)
    if matched is not True and cleaned is True:
        cleaned = None  # Same durable record, but account binding unverified now.
    return RuntimeCleanupDetail(RuntimeCleanupEvidence(delete_confirmed, get_absent, list_absent, cleaned),
                                matched, others, attempted)
