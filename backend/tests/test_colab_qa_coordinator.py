"""LIVE-B2D offline integration. Real OwnershipStore/RuntimeOwnership/transfer
objects over Mock transports, fake clock, fake Contents wire. No network."""
import base64
import hashlib
import io
import json
import socket
from datetime import datetime, timezone
from dataclasses import replace
from types import SimpleNamespace
from urllib.error import HTTPError

import httpx
import pytest

from qa.colab_qa_cleanup import NativeContentsPresenceProbe, NativeRuntimePresenceProbe, Presence
from qa.colab_qa_coordinator import CoordinatorBlocked, QACoordinator, TrustedSources
from qa.colab_qa_deadline import RunDeadline, WORK_LIMIT_SECONDS, authorize_runtime_creation
from qa.colab_qa_writer import QAResultWriter
from src.services.colab_jupyter_files import ColabJupyterFileTransfer, RemoteOwnership, TransferStatus
from src.services.colab_runtime_client import ColabRuntimeClient
from src.services.colab_runtime_ownership import OwnershipRecord, OwnershipState as State, OwnershipStore, RuntimeOwnership
from test_colab_jupyter_files import FakeContents
from test_colab_runtime_client import OAUTH, PROXY, Server

BASE = "https://runtime.example.invalid/prefix"
NOW = datetime(2026, 11, 13, tzinfo=timezone.utc)
RUN = "0123456789abcdef0123456789abcdef"
FILE = f"sorigul-transfer/{RUN}/chunk-00000.mp3"
DATA = bytes((i * 37 + 11) % 256 for i in range(200_000))
ACCOUNT = hashlib.sha256(b"mock-issuer\0subject-a").hexdigest()
OTHER = hashlib.sha256(b"mock-issuer\0subject-b").hexdigest()


@pytest.fixture(autouse=True)
def deny_network(monkeypatch):
    def forbidden(*a, **k):
        raise AssertionError("NETWORK_FORBIDDEN")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", forbidden)


class RuntimeApi(Server):
    """Colab REST Mock: DELETE really removes; GET then 404s; list reflects it."""

    def __init__(self):
        super().__init__()
        self.deleted = False
        self.extra = []
        self.list_response = None
        self.get_after_delete = None

    def runtime(self):
        payload = super().runtime()
        payload["connectionInfo"]["url"] = BASE
        return payload

    def handle(self, request):
        key = request.method, request.url.path
        if key == ("GET", "/v1beta/runtimes"):
            self.calls.append(request)
            if self.list_response is not None:
                return self.list_response(request)
            names = ([] if self.deleted or self.runtime_name is None else [self.runtime_name]) + self.extra
            return httpx.Response(200, json={"runtimes": [{"name": n} for n in names]})
        if self.deleted and key == ("GET", "/v1beta/" + str(self.runtime_name)):
            self.calls.append(request)
            if self.get_after_delete is not None:
                return self.get_after_delete(request)
            return httpx.Response(404, json={"error": {"code": 404, "status": "NOT_FOUND"}})
        response = super().handle(request)
        if request.method == "DELETE" and key not in self.overrides:
            self.deleted = True
        return response

    def count(self, method, suffix=""):
        return sum(1 for r in self.calls if r.method == method and r.url.path.endswith(suffix))


class Raw(io.BytesIO):
    def __init__(self, url, body, status=200):
        super().__init__(body)
        self.url, self.status = url, status
        self.headers = {"Content-Length": str(len(body))}

    def geturl(self):
        return self.url


class ContentsWire:
    """Fake NativeReadbackWire over FakeContents state; records every GET."""

    def __init__(self, contents):
        self.contents, self.calls, self.hooks = contents, [], []

    def open(self, url, token, timeout):
        assert token == PROXY and 0 < timeout <= 20 and url.startswith(BASE + "/api/contents/")
        self.calls.append(url[len(BASE + "/api/contents/"):])
        for hook in list(self.hooks):
            result = hook(url)
            if isinstance(result, BaseException):
                raise result
            if result is not None:
                return result
        path, _, query = url[len(BASE + "/api/contents/"):].partition("?")
        if path not in self.contents.files and path not in self.contents.dirs:
            raise HTTPError("", 404, "", {}, None)
        if query == "content=1&format=base64":
            data = bytes(self.contents.files[path])
            body = {"path": path, "type": "file", "format": "base64", "size": len(data),
                    "content": base64.encodebytes(data).decode("ascii")}
        else:
            body = self.contents.model(path)
        return Raw(url, json.dumps(body).encode())


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


@pytest.fixture
def world(tmp_path):
    clock, account = Clock(), [ACCOUNT]
    deadline = RunDeadline(clock=clock)
    store = OwnershipStore(tmp_path / "ownership")
    api = RuntimeApi()
    client = ColabRuntimeClient(OAUTH, transport=httpx.MockTransport(api.handle),
                                account_verifier=lambda token: account[0],
                                timeout_seconds=10, max_polls=2, sleep=lambda s: None)
    owner = RuntimeOwnership(store, client)
    deadline.start_work()
    assert authorize_runtime_creation(store, deadline)
    runtime = owner.create()
    contents = FakeContents()
    transfer = ColabJupyterFileTransfer(runtime.connection_info, run_id=RUN, http_request=contents.http,
                                        chunk_bytes=64 * 1024, request_timeout=20, utcnow=lambda: NOW)
    transfer.prepare()
    audio = tmp_path / "synthetic.mp3"
    audio.write_bytes(DATA)
    uploaded = transfer.upload(0, audio)
    assert uploaded.status is TransferStatus.VERIFIED and uploaded.chunks_total == 4
    probe_http = httpx.Client(transport=httpx.MockTransport(api.handle), follow_redirects=False,
                              trust_env=False, headers={"Authorization": "Bearer " + OAUTH})
    wire = ContentsWire(contents)
    writer = QAResultWriter(tmp_path / "sorigul-qa-results")
    execution = store.load()[0].execution_id
    sources = TrustedSources.from_owner(store, owner, client, transfer)

    def make(**overrides):
        options = dict(sources=sources, execution_id=execution, request_id=client.request_id,
                       file_index=0, approved_base=BASE, expected=DATA, wire=wire,
                       writer=writer, deadline=deadline, utcnow=lambda: NOW)
        options.update(overrides)
        return QACoordinator(**options)

    w = SimpleNamespace(clock=clock, account=account, deadline=deadline, store=store, api=api,
                        client=client, owner=owner, contents=contents, transfer=transfer, wire=wire,
                        writer=writer, execution=execution, make=make, probe_http=probe_http,
                        sources=sources, tmp=tmp_path)
    yield w
    owner.close()
    client.close()
    probe_http.close()


def state(w):
    return w.store.load()[0].state


def saved(w):
    path = w.writer.root / f"qa-result-{w.execution}.json"
    raw = path.read_bytes()
    for secret in (PROXY.encode(), OAUTH.encode(), BASE.encode(), FILE.encode(), RUN.encode(),
                   ACCOUNT.encode(), w.execution.encode(), base64.b64encode(DATA[:48])):
        assert secret not in raw
    return json.loads(raw)


def assert_blocked_without_effects(w, result):
    assert result.final_verdict == "BLOCKED" and not result.committed and result.recovery_required
    assert w.wire.calls == [] and w.api.count("DELETE") == 0
    assert FILE in w.contents.files and state(w) is State.ACTIVE_OWNED
    assert not w.writer.exists(w.execution)


# ---- full flow -----------------------------------------------------------------

def test_full_offline_flow_passes_only_with_every_gate(world):
    w = world
    w.clock.t = 300
    result = w.make().run()
    assert result.final_verdict == "PASS" and result.committed and not result.recovery_required
    assert set(result.checks.values()) == {"PASS"} and len(result.checks) == 4
    assert result.hard_deadline_enforcement == "NOT_VERIFIED"
    assert w.wire.calls == [FILE + "?content=1&format=base64", FILE + "?content=0",
                            f"sorigul-transfer/{RUN}?content=0"]
    assert w.contents.files == {} and f"sorigul-transfer/{RUN}" not in w.contents.dirs
    assert w.api.count("DELETE") == 1 and w.api.deleted and state(w) is State.CLEANED
    record = saved(w)
    assert record["coordinator"]["pre_commit_verdict"] == "PASS"
    assert record["coordinator"]["deadline"] == "PASS"
    assert record["coordinator"]["runtime_cleanup"] == {
        "delete_attempted": True, "delete_confirmed": True, "get_absent": True, "list_absent": True,
        "ownership_cleaned": True, "account_binding_matched": True, "uncertain_runtime_found": False}
    assert record["diagnostics"]["readback"]["bytes_equal"] is True
    assert record["diagnostics"]["upload_chunks_total"] == 4
    assert PROXY not in repr(w.make()) and BASE not in repr(w.sources)


def test_repeat_run_is_blocked_on_same_and_new_instance(world):
    w = world
    coordinator = w.make()
    assert coordinator.run().final_verdict == "PASS"
    calls, api_calls = list(w.wire.calls), len(w.api.calls)
    assert coordinator.run().final_verdict == "BLOCKED"
    again = w.make().run()
    assert again.final_verdict == "BLOCKED" and not again.recovery_required
    assert w.wire.calls == calls and len(w.api.calls) == api_calls


# ---- TASK A: observer and lease -------------------------------------------------

def test_lost_lease_blocks_before_any_request(world):
    world.owner.close()  # Lease released; remote cleanup NOT implied.
    result = world.make().run()
    assert_blocked_without_effects(world, result)
    assert result.coordinator["lease"] == "BLOCKED"


def test_lease_held_by_another_process_blocks(world):
    world.owner.close()
    other = world.store.execution_lease(world.execution)
    other.__enter__()  # Models a different owner process holding the kernel lock.
    try:
        assert_blocked_without_effects(world, world.make().run())
    finally:
        other.__exit__(None, None, None)
    assert (world.store.root / (world.execution + ".lease")).exists()  # Never deleted.


def test_owner_lease_claim_without_kernel_lock_blocks(world):
    world.owner.close()
    world.owner._lease = object()  # Stale in-memory claim; nobody holds the OS lock.
    try:
        result = world.make().run()
    finally:
        world.owner._lease = None
    assert_blocked_without_effects(world, result)
    probe = world.store.execution_lease(world.execution)
    probe.__enter__()  # The QA probe released what it briefly acquired.
    probe.__exit__(None, None, None)


def test_owner_bound_to_other_store_or_wrong_wiring_blocks(world):
    with pytest.raises(CoordinatorBlocked):
        TrustedSources.from_owner(OwnershipStore(world.store.root), world.owner, world.client, world.transfer)
    with pytest.raises(CoordinatorBlocked):
        TrustedSources.from_owner(world.store, world.owner, world.client, object())


@pytest.mark.parametrize("change", ["execution", "request", "account", "foreign_probe_session", "base", "expected"])
def test_identity_mismatch_blocks_before_any_request(world, change):
    w = world
    kwargs = {}
    if change == "execution":
        kwargs["execution_id"] = "00000000-0000-4000-8000-0000000000ff"
    if change == "request":
        kwargs["request_id"] = "00000000-0000-4000-8000-0000000000fe"
    if change == "account":
        w.account[0] = OTHER
    if change == "foreign_probe_session":
        # A caller-wired client (other account / unverified TLS) is never absence authority.
        kwargs["sources"] = replace(w.sources, runtime_http=w.probe_http)
    if change == "base":
        kwargs["approved_base"] = "https://other.example.invalid/prefix"
    if change == "expected":
        kwargs["expected"] = "not bytes"
    result = w.make(**kwargs).run()
    w.account[0] = ACCOUNT
    assert_blocked_without_effects(w, result)


def test_other_unresolved_execution_record_blocks(world):
    with world.store.transaction():
        world.store._save(OwnershipRecord("00000000-0000-4000-8000-0000000000cc",
            "00000000-0000-4000-8000-0000000000cd", "runtimes/sorigul-" + "4" * 32, ACCOUNT,
            state=State.CREATE_UNCERTAIN, last_remote_state="REQUEST_SENT_OR_PENDING",
            checked_at="2026-11-15T00:00:00+00:00"))
    result = world.make().run()
    assert result.final_verdict == "BLOCKED" and world.wire.calls == [] and world.api.count("DELETE") == 0


def test_existing_result_file_blocks_and_is_preserved(world):
    world.writer.root.mkdir()
    existing = world.writer.root / f"qa-result-{world.execution}.json"
    existing.write_bytes(b"previous")
    assert_blocked_without_effects_except_file(world, world.make().run())
    assert existing.read_bytes() == b"previous"


def assert_blocked_without_effects_except_file(w, result):
    assert result.final_verdict == "BLOCKED" and w.wire.calls == [] and w.api.count("DELETE") == 0


def test_unbounded_blocking_operation_blocks(world, monkeypatch):
    monkeypatch.setattr(world.transfer, "_timeout", 30.0)  # Product default exceeds 20 s.
    result = world.make().run()
    assert result.coordinator["bounded_operations"] == "BLOCKED"
    assert_blocked_without_effects(world, result)


def test_ownership_change_mid_run_stops_all_deletes(world):
    w = world
    def flip(url):
        w.account[0] = OTHER
    w.wire.hooks.append(flip)
    result = w.make().run()
    assert result.final_verdict == "FAIL" and result.recovery_required
    assert FILE in w.contents.files and w.api.count("DELETE") == 0
    assert result.coordinator["runtime_cleanup"]["delete_attempted"] is False
    assert result.coordinator["runtime_cleanup"]["account_binding_matched"] is False
    assert state(w) is not State.CLEANED


# ---- TASK B: file cleanup evidence -------------------------------------------------

def test_delete_204_without_real_removal_is_not_pass(world):
    w = world
    w.contents.hooks.append(lambda m, p, b, n: (204, None) if m == "DELETE" and p == FILE else None)
    result = w.make().run()
    assert result.checks["QA_FILE_CLEANUP_CONFIRMED"] == "FAIL" and result.final_verdict == "FAIL"
    assert result.coordinator["file_cleanup"]["file_absent"] is False
    assert result.checks["QA_RUNTIME_CLEANUP_CONFIRMED"] == "PASS"  # Runtime still cleaned.


def test_absence_probe_failure_is_unconfirmed_not_pass(world):
    w = world
    w.wire.hooks.append(lambda url: TimeoutError() if url.endswith("?content=0") else None)
    result = w.make().run()
    assert result.checks["QA_FILE_CLEANUP_CONFIRMED"] == "NOT_VERIFIED"
    assert saved(w)["diagnostics"]["file_cleanup"]["outcome"] == "UNCONFIRMED"
    assert result.final_verdict == "FAIL"


def test_conflicting_or_uncertain_file_blocks_file_pass_and_is_never_deleted(world, tmp_path):
    w = world
    other = f"sorigul-transfer/{RUN}/chunk-00001.mp3"
    def race(method, path, body, n):
        if method == "PUT" and path == other and other not in w.contents.files:
            w.contents.files[other] = bytearray(b"someone else")
    w.contents.hooks.append(race)
    second = tmp_path / "second.mp3"
    second.write_bytes(DATA[:70_000])
    assert w.transfer.upload(1, second).ownership is RemoteOwnership.CONFLICT
    w.contents.hooks.clear()
    result = w.make().run()
    assert result.coordinator["file_cleanup"]["ownership_conflict"] is True
    assert result.checks["QA_FILE_CLEANUP_CONFIRMED"] != "PASS" and result.final_verdict == "FAIL"
    assert other in w.contents.files and not any(c[0] == "DELETE" and c[1] == other for c in w.contents.calls)


def test_file_cleanup_failure_still_cleans_runtime(world):
    w = world
    w.contents.hooks.append(lambda m, p, b, n: (500, None) if m == "DELETE" else None)
    result = w.make().run()
    assert result.checks["QA_FILE_CLEANUP_CONFIRMED"] == "FAIL"
    assert result.checks["QA_RUNTIME_CLEANUP_CONFIRMED"] == "PASS" and state(w) is State.CLEANED
    assert result.final_verdict == "FAIL" and result.committed


# ---- TASK B: Runtime cleanup evidence ---------------------------------------------

def test_delete_ok_but_get_fails_is_not_pass(world):
    w = world
    w.api.get_after_delete = lambda r: httpx.Response(500, json={})
    result = w.make().run()
    assert result.coordinator["runtime_cleanup"]["get_absent"] is None
    assert result.checks["QA_RUNTIME_CLEANUP_CONFIRMED"] == "NOT_VERIFIED"
    assert result.recovery_required and result.final_verdict == "FAIL"
    assert result.coordinator["deadline"] == "NOT_VERIFIED"  # CLEANED never observed.


@pytest.mark.parametrize("listing", [
    lambda r: httpx.Response(503, json={}),
    lambda r: httpx.Response(200, json={"runtimes": "bad"}),
    lambda r: httpx.Response(200, json={"runtimes": [], "nextPageToken": "again"}),  # Unbounded.
    lambda r: httpx.Response(200, content=b"not json"),
])
def test_delete_ok_but_list_uncertain_is_not_pass(world, listing):
    world.api.list_response = listing
    result = world.make().run()
    assert result.coordinator["runtime_cleanup"]["list_absent"] is None
    assert result.checks["QA_RUNTIME_CLEANUP_CONFIRMED"] == "NOT_VERIFIED" and result.recovery_required


def test_get_absent_but_list_still_shows_runtime_fails(world):
    w = world
    w.api.list_response = lambda r: httpx.Response(200, json={"runtimes": [{"name": w.api.runtime_name}]})
    result = w.make().run()
    assert result.coordinator["runtime_cleanup"]["get_absent"] is True
    assert result.coordinator["runtime_cleanup"]["list_absent"] is False
    assert result.checks["QA_RUNTIME_CLEANUP_CONFIRMED"] == "FAIL"


def test_uncertain_other_sorigul_runtime_is_never_pass_or_deleted(world):
    w = world
    w.api.extra = ["runtimes/sorigul-" + "7" * 32]
    result = w.make().run()
    assert result.coordinator["runtime_cleanup"]["uncertain_runtime_found"] is True
    assert result.checks["QA_RUNTIME_CLEANUP_CONFIRMED"] == "NOT_VERIFIED"
    assert w.api.count("DELETE") == 1 and w.api.count("DELETE", "7" * 32) == 0


def test_runtime_absent_but_durable_record_not_cleaned_fails(world):
    w = world
    def delete(request):
        w.api.deleted = True
        return httpx.Response(200, json={"unexpected": True})  # Product: DELETE_FAILED.
    w.api.overrides[("DELETE", "/v1beta/" + w.api.runtime_name)] = delete
    result = w.make().run()
    e = result.coordinator["runtime_cleanup"]
    assert e["get_absent"] is True and e["list_absent"] is True
    assert e["delete_confirmed"] is False and e["ownership_cleaned"] is False
    assert state(w) is State.CLEANUP_REQUIRED and result.recovery_required


def test_runtime_delete_timeout_keeps_recovery_required(world):
    w = world
    w.api.overrides[("DELETE", "/v1beta/" + w.api.runtime_name)] = httpx.ReadTimeout("t")
    result = w.make().run()
    assert result.checks["QA_RUNTIME_CLEANUP_CONFIRMED"] == "FAIL" and result.recovery_required
    assert state(w) is State.CLEANUP_REQUIRED
    fresh = RunDeadline(clock=w.clock)
    fresh.start_work()
    assert not authorize_runtime_creation(w.store, fresh)  # No automatic recreation.


def test_interrupted_runtime_cleanup_propagates_and_requires_recovery(world):
    w = world
    def interrupt(request):
        raise KeyboardInterrupt
    w.api.overrides[("DELETE", "/v1beta/" + w.api.runtime_name)] = interrupt
    with pytest.raises(KeyboardInterrupt):
        w.make().run()
    assert state(w) is State.CLEANUP_REQUIRED
    record = saved(w)  # Sanitized FAIL result still committed during unwinding.
    assert record["coordinator"]["pre_commit_verdict"] == "FAIL"
    assert record["coordinator"]["recovery_required"] is True


def test_account_mismatch_at_runtime_cleanup_never_deletes(world):
    w = world
    def flip(method, path, body, n):
        if method == "DELETE" and path == FILE:
            w.account[0] = OTHER
    w.contents.hooks.append(flip)
    result = w.make().run()
    assert w.api.count("DELETE") == 0 and result.coordinator["runtime_cleanup"]["delete_attempted"] is False
    assert result.recovery_required and result.final_verdict == "FAIL"


# ---- TASK C/D: persistence, deadline and cancellation --------------------------------

def test_save_failure_after_successful_cleanup_is_final_fail(world, monkeypatch):
    w = world
    def fail(temp, final):
        raise OSError("disk")
    monkeypatch.setattr(w.writer, "_publish", fail)
    result = w.make().run()
    assert set(result.checks.values()) == {"PASS"} and state(w) is State.CLEANED
    assert not result.committed and result.final_verdict == "FAIL" and not result.recovery_required
    assert not w.writer.root.exists() or list(w.writer.root.iterdir()) == []


def test_cancellation_and_save_failure_preserves_cancellation(world, monkeypatch):
    w = world
    w.wire.hooks.append(lambda url: KeyboardInterrupt() if "format=base64" in url else None)
    monkeypatch.setattr(w.writer, "_publish", lambda t, f: (_ for _ in ()).throw(OSError("disk")))
    with pytest.raises(KeyboardInterrupt):
        w.make().run()
    assert state(w) is State.CLEANED and not w.writer.exists(w.execution)


def test_cancel_requested_skips_readback_but_still_cleans(world):
    w = world
    result = w.make(cancel_requested=lambda: True).run()
    assert result.coordinator["readback_gate"] == "CANCELLED"
    assert not any("format=base64" in c for c in w.wire.calls)
    assert state(w) is State.CLEANED and result.final_verdict == "FAIL" and result.committed


def test_step_too_close_to_work_limit_is_blocked_then_cleaned(world):
    w = world
    w.clock.t = WORK_LIMIT_SECONDS - 19
    result = w.make().run()
    assert result.coordinator["readback_gate"] == "DEADLINE_BLOCKED"
    assert not any("format=base64" in c for c in w.wire.calls)
    assert state(w) is State.CLEANED and result.final_verdict == "FAIL"


def test_readback_overrunning_work_limit_fails_deadline(world):
    w = world
    def slow(url):
        if "format=base64" in url:
            w.clock.t = WORK_LIMIT_SECONDS + 5  # A call that returned late.
    w.wire.hooks.append(slow)
    result = w.make().run()
    assert result.checks["QA_READBACK_PASSED"] == "PASS"
    assert result.coordinator["deadline"] == "FAIL" and result.final_verdict == "FAIL"
    assert state(w) is State.CLEANED


def test_runtime_limit_reached_during_cleanup_fails_deadline(world):
    w = world
    def slow(request):
        w.clock.t = 30 * 60 + 1
        return httpx.Response(200, json={"runtimes": []})
    w.api.list_response = slow
    result = w.make().run()
    assert result.checks["QA_RUNTIME_CLEANUP_CONFIRMED"] == "PASS"
    assert result.coordinator["deadline"] == "FAIL" and result.final_verdict == "FAIL"


def test_request_timeout_during_readback_is_fail_and_cleanup_follows(world):
    w = world
    w.wire.hooks.append(lambda url: TimeoutError() if "format=base64" in url else None)
    result = w.make().run()
    assert result.checks["QA_READBACK_PASSED"] == "FAIL"
    assert saved(w)["diagnostics"]["readback"]["error_code"] == "TIMEOUT"
    assert state(w) is State.CLEANED and result.final_verdict == "FAIL"


def test_upload_evidence_mismatch_never_reads_back_but_cleans(world):
    w = world
    result = w.make(expected=DATA[:-1] + b"\x00").run()
    assert result.checks["PRODUCT_UPLOAD_VERIFIED"] == "FAIL"
    assert result.coordinator["readback_gate"] == "UPLOAD_NOT_VERIFIED"
    assert not any("format=base64" in c for c in w.wire.calls) and state(w) is State.CLEANED


# ---- probe units ---------------------------------------------------------------

def contents_probe(wire):
    return NativeContentsPresenceProbe(wire=wire, approved_base=BASE, run_dir=f"sorigul-transfer/{RUN}",
                                       file_path=FILE)


@pytest.mark.parametrize("outcome,expected", [
    (HTTPError("", 404, "", {}, None), Presence.ABSENT),
    (HTTPError("", 302, "", {}, None), Presence.UNCERTAIN),
    (HTTPError("", 500, "", {}, None), Presence.UNCERTAIN),
    (OSError("x"), Presence.UNCERTAIN),
    (Raw("https://other.invalid/", b"{}"), Presence.UNCERTAIN),
])
def test_contents_probe_only_exact_404_is_absence(outcome, expected):
    class Wire:
        def open(self, url, token, timeout):
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome
    assert contents_probe(Wire()).presence(FILE, token=PROXY, timeout_seconds=20) is expected


def test_contents_probe_never_requests_unpinned_path_or_unbounded_timeout():
    calls = []
    class Wire:
        def open(self, *a):
            calls.append(a)
    probe = contents_probe(Wire())
    assert probe.presence("sorigul-transfer", token=PROXY, timeout_seconds=20) is Presence.UNCERTAIN
    assert probe.presence(FILE, token=PROXY, timeout_seconds=21) is Presence.UNCERTAIN
    assert calls == []
    with pytest.raises(ValueError):
        NativeContentsPresenceProbe(wire=Wire(), approved_base=BASE, run_dir="../x", file_path=FILE)


def test_runtime_probe_requires_no_redirect_no_env_client():
    for kwargs in ({"follow_redirects": True, "trust_env": False}, {"follow_redirects": False}):
        with httpx.Client(**kwargs) as http:
            with pytest.raises(ValueError):
                NativeRuntimePresenceProbe(http, "runtimes/sorigul-" + "1" * 32)


def test_listing_with_error_or_unknown_fields_is_not_absence(world):
    world.api.list_response = lambda r: httpx.Response(200, json={"error": {"code": 403}})
    result = world.make().run()
    assert result.coordinator["runtime_cleanup"]["list_absent"] is None
    assert result.checks["QA_RUNTIME_CLEANUP_CONFIRMED"] == "NOT_VERIFIED"


def test_absence_probes_use_the_verified_client_session(world):
    w = world
    assert w.make().run().final_verdict == "PASS"
    probes = [r for r in w.api.calls if r.method == "GET" and (
        r.url.path == "/v1beta/runtimes" or (w.api.deleted and r.url.path.endswith(w.api.runtime_name[9:])))]
    assert probes and all(r.headers["Authorization"] == "Bearer " + OAUTH for r in probes)
    assert w.sources.runtime_http is w.client._http
