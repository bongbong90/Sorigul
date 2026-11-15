"""Trusted serial QA coordinator for ONE owned run. Verified offline only.

Nothing here creates a Runtime, loads credentials or authorizes a live run.
Every source is an in-process product object for the same execution:
OwnershipStore + the RuntimeOwnership that holds the execution lease, its
ColabRuntimeClient (verified account, owned Runtime GET) and the run's
ColabJupyterFileTransfer. Caller booleans, UI/settings labels or JSON are never
ownership authority. Any preflight doubt BLOCKS before a request or cleanup.

Flow: preflight (single use, no prior result, bounded operations, live lease,
trusted observation) -> deadline/cancel gate -> run_qa (readback, file cleanup
+ absence, Runtime cleanup + GET/list absence + durable CLEANED) -> sanitized
atomic write -> final verdict. PASS needs every gate, all four checks and a
verified commit. Lease release is never treated as remote cleanup.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from typing import Callable

import httpx

from qa.colab_owned_readback import OwnedObservation, OwnedReadbackAdapter
from qa.colab_qa_cleanup import (NativeContentsPresenceProbe, NativeRuntimePresenceProbe,
                                 confirm_file_cleanup, confirm_runtime_cleanup)
from qa.colab_qa_deadline import REQUEST_TIMEOUT_SECONDS, RunDeadline, bounded_timeout
from qa.colab_qa_run import FileCleanupEvidence, QAResultSaveError, UploadEvidence, checks, run_qa
from qa.colab_qa_writer import SCHEMA, QAResultWriter
from qa.colab_readback import CheckFailed, Code
from src.services.colab_jupyter_client import ColabJupyterClient
from src.services.colab_jupyter_files import ColabJupyterFileTransfer, IntegrityLevel, TransferStatus
from src.services.colab_runtime_client import ColabRuntimeClient, RuntimeClientError
from src.services.colab_runtime_ownership import OwnershipState, OwnershipStore, RuntimeOwnership


class CoordinatorBlocked(Exception):
    """Fixed text only; never carries remote data."""

    def __init__(self):
        super().__init__("QA_COORDINATOR_BLOCKED")


@dataclass(frozen=True, repr=False)
class TrustedSources:
    store: OwnershipStore
    owner: RuntimeOwnership
    verify_account: Callable[[], str]
    get_owned_runtime: Callable[[], object]
    transfer: ColabJupyterFileTransfer
    # The verified client's own httpx session: absence probes run as the same
    # account/TLS/no-redirect configuration that created and deleted the Runtime.
    runtime_http: httpx.Client

    @classmethod
    def from_owner(cls, store, owner, client, transfer):
        """Bind the product objects of one execution; reject foreign wiring."""
        if (type(store) is not OwnershipStore or type(owner) is not RuntimeOwnership
                or type(client) is not ColabRuntimeClient or owner.store is not store
                or owner.client is not client or type(transfer) is not ColabJupyterFileTransfer):
            raise CoordinatorBlocked()

        def get_owned_runtime():
            # Its RUNTIME_CONFIRMED checkpoint must persist under the store lock.
            with store.transaction():
                return client.get_owned_runtime()
        return cls(store, owner, client.verified_account_binding, get_owned_runtime, transfer,
                   client._http)


@dataclass(frozen=True)
class Pin:
    execution_id: str
    request_id: str
    runtime_name: str
    account_binding: str


class TrustedObserver:
    def __init__(self, sources, *, execution_id, request_id, file_index):
        self._s, self._execution_id = sources, execution_id
        self._request_id, self._file_index = request_id, file_index

    def __repr__(self):
        return "TrustedObserver(<private>)"

    def lease_held(self):
        """This process's owner holds the lease, and nobody else can take it.

        A probe that unexpectedly acquires the lease proves it was NOT held; it
        is released at once. The lease file is never deleted or forced.
        """
        owner = self._s.owner
        record = getattr(owner, "_record", None)
        if (type(owner) is not RuntimeOwnership or owner.store is not self._s.store
                or record is None or record.execution_id != self._execution_id
                or getattr(owner, "_lease", None) is None):
            return False
        try:
            probe = self._s.store.execution_lease(self._execution_id)
        except Exception:
            return False
        try:
            probe.__enter__()
        except RuntimeClientError:
            return True
        except Exception:
            return False
        probe.__exit__(None, None, None)
        return False

    def record(self):
        records = self._s.store.load()
        mine = [r for r in records if r.execution_id == self._execution_id]
        if len(mine) != 1 or any(r.execution_id != self._execution_id
                                 and r.state is not OwnershipState.CLEANED for r in records):
            raise CoordinatorBlocked()  # Another unresolved run: ownership uncertain.
        if mine[0].request_id != self._request_id:
            raise CoordinatorBlocked()
        return mine[0]

    def observe(self):
        """Fresh trusted observation; the adapter re-validates it at open."""
        try:
            if not self.lease_held():
                raise CoordinatorBlocked()
            record = self.record()
            binding = self._s.verify_account()
            runtime = self._s.get_owned_runtime()
            files = [f for f in self._s.transfer.records() if f.index == self._file_index]
            if len(files) != 1:
                raise CoordinatorBlocked()
            matches = self._s.transfer.matches_connection(runtime.connection_info) is True
            return OwnedObservation(record, binding, runtime, files[0], matches)
        except CoordinatorBlocked:
            raise
        except Exception:
            raise CoordinatorBlocked() from None

    def cleanup_authorized(self, pin, states):
        try:
            if not self.lease_held():
                return False
            record = self.record()
            return ((record.request_id, record.runtime_name, record.account_binding)
                    == (pin.request_id, pin.runtime_name, pin.account_binding)
                    and record.state in states and record.cleanup_required is True
                    and self._s.verify_account() == pin.account_binding)
        except Exception:
            return False


def _bounded_operations(sources):
    """Every blocking product call must carry a <= 20 s socket timeout."""
    transfer_timeout = getattr(sources.transfer, "_timeout", None)
    timeout = getattr(getattr(getattr(sources.owner, "client", None), "_http", None), "timeout", None)
    return (bounded_timeout(transfer_timeout) and isinstance(timeout, httpx.Timeout)
            and all(bounded_timeout(value) for value in
                    (timeout.connect, timeout.read, timeout.write, timeout.pool)))


def _all_cleaned(store):
    try:
        return all(r.state is OwnershipState.CLEANED for r in store.load())
    except Exception:
        return False


@dataclass(frozen=True)
class CoordinatorResult:
    final_verdict: str          # PASS / FAIL / BLOCKED
    checks: dict
    coordinator: dict
    committed: bool
    recovery_required: bool
    hard_deadline_enforcement: str = "NOT_VERIFIED"


def _empty_coordinator():
    return {
        "lease": "NOT_RUN", "observer": "NOT_RUN", "bounded_operations": "NOT_RUN",
        "readback_gate": "NOT_RUN", "deadline": "NOT_VERIFIED",
        "hard_deadline_enforcement": "NOT_VERIFIED",
        "work_elapsed_seconds": None, "runtime_elapsed_seconds": None,
        "file_cleanup": dict.fromkeys(("delete_confirmed", "file_absent", "run_directory_absent",
                                       "ownership_conflict")),
        "runtime_cleanup": {**dict.fromkeys(("delete_confirmed", "get_absent", "list_absent",
                                             "ownership_cleaned", "account_binding_matched",
                                             "uncertain_runtime_found")),
                            "delete_attempted": False},
        "recovery_required": True, "pre_commit_verdict": "FAIL",
    }


class QACoordinator:
    """Single-use. A second run() — on this or a later instance — is BLOCKED."""

    def __init__(self, *, sources, execution_id, request_id, file_index, approved_base,
                 expected, wire, writer, deadline,
                 cancel_requested=lambda: False, utcnow=lambda: datetime.now(timezone.utc),
                 timeout_seconds=REQUEST_TIMEOUT_SECONDS):
        self._s, self._wire, self._probe, self._writer = sources, wire, None, writer
        self._execution_id, self._request_id = execution_id, request_id
        self._base, self._expected, self._deadline = approved_base, expected, deadline
        self._cancel, self._utcnow, self._timeout = cancel_requested, utcnow, timeout_seconds
        self._observer = TrustedObserver(sources, execution_id=execution_id,
                                         request_id=request_id, file_index=file_index)
        self._used = False

    def __repr__(self):
        return "QACoordinator(<private>)"

    def _blocked(self, coordinator):
        return CoordinatorResult("BLOCKED", {}, coordinator, False, not _all_cleaned(self._s.store))

    def _preflight(self, c):
        if (type(self._writer) is not QAResultWriter or self._writer.exists(self._execution_id)
                or type(self._deadline) is not RunDeadline or self._deadline.runtime_created is None
                or self._deadline.cleanup_started is not None or not bounded_timeout(self._timeout)
                or type(self._expected) is not bytes or type(self._s) is not TrustedSources
                or self._s.runtime_http is not getattr(getattr(self._s.owner, "client", None), "_http", None)):
            raise CoordinatorBlocked()  # Probe session must be the verified client's own.
        c["bounded_operations"] = "PASS" if _bounded_operations(self._s) else "BLOCKED"
        if c["bounded_operations"] != "PASS":
            raise CoordinatorBlocked()
        c["lease"] = "PASS" if self._observer.lease_held() else "BLOCKED"
        if c["lease"] != "PASS":
            raise CoordinatorBlocked()
        c["observer"] = "BLOCKED"
        initial = self._observer.observe()
        try:
            adapter = OwnedReadbackAdapter(initial=initial, observe=self._observer.observe,
                                           wire=self._wire, expected_execution_id=self._execution_id,
                                           approved_base=self._base, utcnow=self._utcnow)
        except Exception:
            raise CoordinatorBlocked() from None
        r = initial.record
        pin = Pin(r.execution_id, r.request_id, r.runtime_name, r.account_binding)
        try:
            self._probe = NativeRuntimePresenceProbe(self._s.runtime_http, pin.runtime_name)
        except ValueError:
            raise CoordinatorBlocked() from None
        file_path = adapter.expected_path
        try:
            contents_probe = NativeContentsPresenceProbe(
                wire=self._wire, approved_base=self._base,
                run_dir=file_path.rsplit("/", 1)[0], file_path=file_path)
        except ValueError:
            raise CoordinatorBlocked() from None
        c["observer"] = "PASS"
        return initial, adapter, pin, contents_probe

    def _connection_token(self, pin):
        runtime = self._s.get_owned_runtime()
        info = runtime.connection_info
        if (runtime.name != pin.runtime_name or ColabJupyterClient._validate_info(info) != self._base
                or info.expire_time <= self._utcnow()):
            raise CoordinatorBlocked()
        return info.token

    def run(self):
        c = _empty_coordinator()
        if self._used:
            return self._blocked(c)
        self._used = True
        try:
            initial, adapter, pin, contents_probe = self._preflight(c)
        except Exception:
            return self._blocked(c)  # Nothing requested, nothing cleaned.

        f, deadline = initial.file, self._deadline
        try:
            upload = UploadEvidence(
                verified=f.status is TransferStatus.VERIFIED,
                content_sha256_verified=(f.integrity is IntegrityLevel.CONTENT_SHA256
                                         and f.sha256 == hashlib.sha256(self._expected).hexdigest()),
                size_equal=f.size == len(self._expected),
                chunks_total=f.chunks_total, chunks_acknowledged=f.chunks_acknowledged)
        except Exception:
            # Ownership is verified: still reach cleanup with NOT_VERIFIED upload.
            upload = UploadEvidence(None, None, None, None, None)
        c["readback_gate"] = "UPLOAD_NOT_VERIFIED"
        state = {"committed": False}
        coordinator = self

        class GatedTransport:
            def open_readback(self, *, timeout_seconds):
                if coordinator._cancel():
                    c["readback_gate"] = "CANCELLED"
                elif not deadline.may_start(timeout_seconds):
                    c["readback_gate"] = "DEADLINE_BLOCKED"
                else:
                    c["readback_gate"] = "ALLOWED"
                    return adapter.open_readback(timeout_seconds=timeout_seconds)
                raise CheckFailed(Code.OWNED_TRANSPORT_BLOCKED)

        def file_cleanup():
            deadline.check_step()
            deadline.begin_cleanup()
            if not self._observer.cleanup_authorized(pin, {OwnershipState.ACTIVE_OWNED}):
                return FileCleanupEvidence(False, None, None)  # Ownership changed: no DELETE.
            detail = confirm_file_cleanup(
                transfer=self._s.transfer, file_path=adapter.expected_path, probe=contents_probe,
                connection_token=lambda: self._connection_token(pin),
                timeout_seconds=self._timeout, after_step=deadline.check_step)
            e = detail.evidence
            c["file_cleanup"] = {"delete_confirmed": e.delete_confirmed, "file_absent": e.file_absent,
                                 "run_directory_absent": e.run_directory_absent,
                                 "ownership_conflict": detail.ownership_conflict}
            return e

        def runtime_cleanup():
            deadline.begin_cleanup()
            detail = confirm_runtime_cleanup(
                owner_cleanup=self._s.owner.cleanup, probe=self._probe, store=self._s.store,
                pin=pin, verify_account=self._s.verify_account,
                authorized=lambda: self._observer.cleanup_authorized(
                    pin, {OwnershipState.ACTIVE_OWNED, OwnershipState.CLEANUP_REQUIRED}),
                timeout_seconds=self._timeout, after_step=deadline.check_step)
            e = detail.evidence
            if all(v is True for v in (e.delete_confirmed, e.get_absent, e.list_absent, e.ownership_cleaned)):
                deadline.mark_runtime_cleaned()
            c["runtime_cleanup"] = {
                "delete_attempted": detail.delete_attempted, "delete_confirmed": e.delete_confirmed,
                "get_absent": e.get_absent, "list_absent": e.list_absent,
                "ownership_cleaned": e.ownership_cleaned,
                "account_binding_matched": detail.account_binding_matched,
                "uncertain_runtime_found": detail.uncertain_runtime_found}
            return e

        def save(snapshot):
            verdicts = checks(snapshot)
            c["deadline"] = deadline.verdict()
            c["work_elapsed_seconds"], c["runtime_elapsed_seconds"] = deadline.elapsed()
            c["recovery_required"] = verdicts["QA_RUNTIME_CLEANUP_CONFIRMED"] != "PASS"
            c["pre_commit_verdict"] = "PASS" if (
                all(v == "PASS" for v in verdicts.values())
                and c["lease"] == c["observer"] == c["bounded_operations"] == c["deadline"] == "PASS"
                and c["readback_gate"] == "ALLOWED") else "FAIL"
            state["checks"] = verdicts
            self._writer.write({"schema": SCHEMA, "diagnostics": snapshot, "coordinator": c},
                               execution_id=self._execution_id)
            state["committed"] = True

        try:
            run_qa(upload=upload, expected=self._expected, expected_path=adapter.expected_path,
                   transport=GatedTransport(), file_cleanup=file_cleanup,
                   runtime_cleanup=runtime_cleanup, save_snapshot=save)
        except QAResultSaveError:
            pass  # Not committed; the in-memory verdict below is FAIL.
        committed = state["committed"]
        final = "PASS" if committed and c["pre_commit_verdict"] == "PASS" else "FAIL"
        return CoordinatorResult(final, dict(state.get("checks", {})), c, committed,
                                 c["recovery_required"])
