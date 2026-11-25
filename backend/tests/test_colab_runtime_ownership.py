import hashlib
import json
import os
import socket
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from src.services import colab_runtime_ownership as module
from src.services.colab_runtime_client import ColabRuntimeClient, RuntimeClientError, RuntimeErrorCode as Code
from src.services.colab_runtime_ownership import OwnershipStore, OwnershipState as State, RuntimeOwnership
from test_colab_runtime_client import Server, OAUTH, PROXY


ACCOUNT = hashlib.sha256(b"mock-verified-issuer\0mock-subject-a").hexdigest()
OTHER_ACCOUNT = hashlib.sha256(b"mock-verified-issuer\0mock-subject-b").hexdigest()


class SimulatedCrash(BaseException):
    """Unwinds test stack only. No real process is killed."""


@pytest.fixture(autouse=True)
def deny_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Live network forbidden in PHASE 04")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", forbidden)


@pytest.fixture
def environment(tmp_path):
    server = Server()
    clients = []
    store = OwnershipStore(tmp_path / "ownership")
    def client(account=ACCOUNT):
        def verified(token):
            assert token == OAUTH  # Proof provider is bound to exact credential.
            return account
        result = ColabRuntimeClient(OAUTH, transport=httpx.MockTransport(server.handle),
            account_verifier=verified, max_polls=2, sleep=lambda _: None)
        clients.append(result)
        return result
    yield store, server, client
    for instance in clients:
        owner = getattr(instance._checkpoint, "__self__", None)
        if isinstance(owner, RuntimeOwnership):
            owner.close()
        instance.close()


def start(environment):
    store, server, make_client = environment
    owner = RuntimeOwnership(store, make_client())
    owner.create()
    owner.close()  # Model previous owner no longer running, no remote cleanup.
    return owner, store.load()[0]


def test_record_is_durable_before_first_create_post(environment):
    store, server, make_client = environment
    client = make_client()
    original = server.handle
    def handle(request):
        if request.method == "POST":
            paths = list(store.root.glob("*.json"))
            assert len(paths) == 1
            persisted = store._read(paths[0])
            assert persisted.state == State.CREATE_UNCERTAIN
            assert persisted.request_id == request.url.params["requestId"]
            assert persisted.runtime_name == "runtimes/" + request.url.params["runtimeId"]
            assert persisted.account_binding == ACCOUNT
        return original(request)
    client._http.close()
    client._http = httpx.Client(transport=httpx.MockTransport(handle),
                              headers={"Authorization": "Bearer " + OAUTH})
    owner = RuntimeOwnership(store, client)
    runtime = owner.create()
    record = store.load()[0]
    assert runtime.name == record.runtime_name
    assert record.state == State.ACTIVE_OWNED and record.cleanup_required
    assert record.operation_name == "operations/mock-op"
    assert record.last_remote_state == "CONFIRMED"


def test_failed_disk_write_blocks_all_remote_calls(environment, monkeypatch):
    store, server, make_client = environment
    monkeypatch.setattr(store, "_save", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(RuntimeClientError):
        RuntimeOwnership(store, make_client()).create()
    assert server.calls == []


def test_checkpoint_failure_before_post_preserves_prepared_record(environment, monkeypatch):
    store, server, make_client = environment
    original = store._save
    def save(record, **kwargs):
        if record.state == State.CREATE_UNCERTAIN:
            raise OSError("disk full")
        return original(record, **kwargs)
    monkeypatch.setattr(store, "_save", save)
    with pytest.raises(RuntimeClientError):
        RuntimeOwnership(store, make_client()).create()
    assert all(request.method == "GET" for request in server.calls)
    assert store.load()[0].state == State.PREPARED


def test_mock_crash_after_post_operation_checkpoint_recovers_and_deletes(environment):
    store, server, make_client = environment
    server.pending = True
    server.overrides["GET", "/v1/operations/mock-op"] = SimulatedCrash()
    # Server's generic fake handles Exception, while this intentional process
    # loss is a BaseException; inject a callable to raise it explicitly.
    def crash(request):
        raise SimulatedCrash
    server.overrides["GET", "/v1/operations/mock-op"] = crash
    with pytest.raises(SimulatedCrash):
        RuntimeOwnership(store, make_client()).create()
    record = store.load()[0]
    assert record.state == State.RECOVERY_REQUIRED
    assert record.operation_name == "operations/mock-op"
    del server.overrides["GET", "/v1/operations/mock-op"]
    before = len(server.calls)
    result = RuntimeOwnership(OwnershipStore(store.root), make_client()).recover(record.execution_id)
    assert result.state == State.CLEANED and not result.cleanup_required
    assert [r.method for r in server.calls[before:]] == ["GET", "GET", "DELETE"]
    assert store.load()[0].state == State.CLEANED


def test_lost_create_response_keeps_uncertainty_no_adoption(environment):
    store, server, make_client = environment
    server.overrides["POST", "/v1beta/runtimes"] = httpx.ReadTimeout(PROXY)
    with pytest.raises(RuntimeClientError):
        RuntimeOwnership(store, make_client()).create()
    record = store.load()[0]
    assert record.state == State.CREATE_UNCERTAIN and record.operation_name is None
    before = len(server.calls)
    result = RuntimeOwnership(OwnershipStore(store.root), make_client()).recover(record.execution_id)
    assert result.state == State.RECOVERY_REQUIRED and result.cleanup_required
    assert result.local_transcription_available
    assert len(server.calls) == before
    assert store.load()[0].runtime_name == record.runtime_name


def test_same_account_proof_and_operation_runtime_match_before_delete(environment):
    _, record = start(environment)
    store, server, make_client = environment
    before = len(server.calls)
    result = RuntimeOwnership(OwnershipStore(store.root), make_client()).recover(record.execution_id)
    assert result.state == State.CLEANED
    requests = server.calls[before:]
    assert [r.url.path for r in requests] == [
        "/v1/operations/mock-op", "/v1beta/" + record.runtime_name,
        "/v1beta/" + record.runtime_name,
    ]
    assert all(r.method != "POST" for r in requests)


@pytest.mark.parametrize("account", [OTHER_ACCOUNT, None, "email@example.invalid", OAUTH])
def test_other_or_unverifiable_account_blocks_query_and_delete(environment, account):
    _, record = start(environment)
    store, server, make_client = environment
    before = len(server.calls)
    original = (store.root / (record.execution_id + ".json")).read_bytes()
    result = RuntimeOwnership(store, make_client(account)).recover(record.execution_id)
    assert result.state == State.BLOCKED
    assert len(server.calls) == before
    assert (store.root / (record.execution_id + ".json")).read_bytes() == original


def test_no_trusted_account_verifier_means_zero_create_calls(environment):
    store, server, _ = environment
    client = ColabRuntimeClient(OAUTH, transport=httpx.MockTransport(server.handle))
    try:
        with pytest.raises(RuntimeClientError):
            RuntimeOwnership(store, client).create()
        assert server.calls == [] and store.load() == []
    finally:
        client.close()


def test_delete_failure_persists_cleanup_required_then_restart_can_retry(environment):
    _, record = start(environment)
    store, server, make_client = environment
    server.overrides["DELETE", "/v1beta/" + record.runtime_name] = httpx.Response(500, json={})
    result = RuntimeOwnership(store, make_client()).recover(record.execution_id)
    assert result.state == State.CLEANUP_REQUIRED and result.error_code == Code.DELETE_FAILED
    assert store.load()[0].state == State.CLEANUP_REQUIRED
    del server.overrides["DELETE", "/v1beta/" + record.runtime_name]
    result = RuntimeOwnership(OwnershipStore(store.root), make_client()).recover(record.execution_id)
    assert result.state == State.CLEANED


def test_completed_delete_before_crash_is_confirmed_absent_on_restart(environment):
    _, record = start(environment)
    store, server, make_client = environment
    server.overrides["GET", "/v1beta/" + record.runtime_name] = httpx.Response(404, json={})
    before = len(server.calls)
    result = RuntimeOwnership(store, make_client()).recover(record.execution_id)
    assert result.state == State.CLEANED
    assert store.load()[0].last_remote_state == "ABSENT"
    assert all(r.method == "GET" for r in server.calls[before:])


@pytest.mark.parametrize("status", [401, 403, 404, 429, 500])
def test_operation_query_denied_or_missing_never_deletes(environment, status):
    _, record = start(environment)
    store, server, make_client = environment
    server.overrides["GET", "/v1/operations/mock-op"] = httpx.Response(status, json={})
    before = len(server.calls)
    result = RuntimeOwnership(store, make_client()).recover(record.execution_id)
    assert result.state == State.RECOVERY_REQUIRED
    assert all(r.method == "GET" for r in server.calls[before:])
    assert store.load()[0].cleanup_required


def test_conflicting_operation_cannot_adopt_other_execution(environment):
    _, record = start(environment)
    store, server, make_client = environment
    server.overrides["GET", "/v1/operations/mock-op"] = httpx.Response(200, json={
        "name": "operations/mock-op", "done": True,
        "response": {"name": "runtimes/sorigul-" + "a" * 32},
    })
    before = len(server.calls)
    result = RuntimeOwnership(store, make_client()).recover(record.execution_id)
    assert result.state == State.RECOVERY_REQUIRED
    assert len(server.calls) == before + 1


def test_duplicate_create_across_store_instances_blocked(environment):
    _, record = start(environment)
    store, server, make_client = environment
    before = len(server.calls)
    with pytest.raises(RuntimeClientError) as error:
        RuntimeOwnership(OwnershipStore(store.root), make_client()).create()
    assert error.value.code == Code.DUPLICATE_CREATE
    assert len(server.calls) == before and store.load() == [record]


def test_cleaned_record_not_redeleted_and_new_run_keeps_old_file(environment):
    owner, record = start(environment)
    store, server, make_client = environment
    assert owner.cleanup().state == State.CLEANED
    before = len(server.calls)
    path = store.root / (record.execution_id + ".json")
    original = path.read_bytes()
    result = RuntimeOwnership(store, make_client()).recover(record.execution_id)
    assert result.state == State.CLEANED and len(server.calls) == before
    RuntimeOwnership(store, make_client()).create()
    assert len(store.load()) == 2 and path.read_bytes() == original


@pytest.mark.parametrize("raw", [b"{broken", b"[]", b'{"version":1}', b'null'])
def test_corrupt_json_is_preserved_without_reset_or_remote_work(environment, raw):
    _, record = start(environment)
    store, server, make_client = environment
    path = store.root / (record.execution_id + ".json")
    path.write_bytes(raw)
    before = len(server.calls)
    result = RuntimeOwnership(store, make_client()).recover(record.execution_id)
    assert result.state == State.BLOCKED
    assert path.read_bytes() == raw and len(server.calls) == before
    with pytest.raises(RuntimeClientError):
        RuntimeOwnership(store, make_client()).create()
    assert path.read_bytes() == raw


@pytest.mark.parametrize("mutate", [
    lambda r: r.update(token=OAUTH), lambda r: r.update(operation_name="https://proxy.invalid/" + PROXY),
    lambda r: r.update(account_binding="email@example.invalid"),
    lambda r: r.update(cleanup_required="false"), lambda r: r.pop("operation_name"),
    lambda r: r.update(runtime_name="../../other.json"),
])
def test_wrong_fields_rejected_even_with_recomputed_checksum(environment, mutate):
    _, record = start(environment)
    store, server, make_client = environment
    path = store.root / (record.execution_id + ".json")
    data = json.loads(path.read_bytes())
    mutate(data["record"])
    data["sha256"] = hashlib.sha256(store._encode(data["record"])).hexdigest()
    raw = store._encode(data)
    path.write_bytes(raw)
    before = len(server.calls)
    assert RuntimeOwnership(store, make_client()).recover(record.execution_id).state == State.BLOCKED
    assert path.read_bytes() == raw and len(server.calls) == before


def test_durable_records_contain_only_allowed_metadata(environment):
    owner, _ = start(environment)
    store, _, _ = environment
    owner.cleanup()
    raw = b"".join(path.read_bytes() for path in store.root.iterdir())
    for secret in (OAUTH, PROXY, "runtime.example.invalid", "MP3", "access_token", "refresh_token"):
        assert secret.encode() not in raw
    record = store.load()[0]
    assert record.state == State.CLEANED and len(record.account_binding) == 64


def test_atomic_replace_failure_preserves_previous_good_record(environment, monkeypatch):
    _, record = start(environment)
    store, server, make_client = environment
    path = store.root / (record.execution_id + ".json")
    raw = path.read_bytes()
    def fail(*args):
        raise OSError("replace failed")
    monkeypatch.setattr(module.os, "replace", fail)
    before = len(server.calls)
    assert RuntimeOwnership(store, make_client()).recover(record.execution_id).state == State.BLOCKED
    assert path.read_bytes() == raw and len(server.calls) == before
    assert list(store.root.glob("*.tmp")) == []


def test_existing_normal_record_cannot_be_overwritten_by_new_prepare(environment):
    _, record = start(environment)
    store, _, _ = environment
    with store.transaction():
        with pytest.raises(RuntimeClientError):
            store._save(record)
        with pytest.raises(RuntimeClientError):
            store._save(replace(record, runtime_name="runtimes/sorigul-" + "f" * 32), expected=record)
    assert store.load() == [record]


def test_hardlink_record_blocks_reads_without_modification(environment, tmp_path):
    _, record = start(environment)
    store, server, make_client = environment
    path = store.root / (record.execution_id + ".json")
    os.link(path, tmp_path / "alias.json")
    before = len(server.calls)
    assert RuntimeOwnership(store, make_client()).recover(record.execution_id).state == State.BLOCKED
    assert len(server.calls) == before


def test_reparse_or_symlink_root_is_rejected(environment, monkeypatch):
    store, server, make_client = environment
    store.root.mkdir()
    original = Path.lstat
    def lstat(path, *args, **kwargs):
        attrs = original(path, *args, **kwargs)
        if path == store.root:
            return SimpleNamespace(st_mode=attrs.st_mode, st_file_attributes=0x400)
        return attrs
    monkeypatch.setattr(Path, "lstat", lstat)
    with pytest.raises(RuntimeClientError):
        RuntimeOwnership(store, make_client()).create()
    assert server.calls == []


def test_permissions_failure_blocks_create(environment, monkeypatch):
    store, server, make_client = environment
    def denied(*args, **kwargs):
        raise module._blocked()
    monkeypatch.setattr(module, "_permissions", denied)
    with pytest.raises(RuntimeClientError):
        RuntimeOwnership(store, make_client()).create()
    assert server.calls == []


def test_path_escape_is_rejected_without_io(tmp_path):
    with pytest.raises(RuntimeClientError):
        OwnershipStore(tmp_path / ".." / "outside")


def test_os_lock_contention_blocks_second_writer(environment):
    store, server, make_client = environment
    with store.transaction():
        with pytest.raises(RuntimeClientError):
            RuntimeOwnership(OwnershipStore(store.root), make_client()).create()
    assert server.calls == []


def test_live_execution_lease_blocks_restart_recovery(environment):
    store, server, make_client = environment
    owner = RuntimeOwnership(store, make_client())
    owner.create()
    record = store.load()[0]
    before = len(server.calls)
    result = RuntimeOwnership(OwnershipStore(store.root), make_client()).recover(record.execution_id)
    assert result.state == State.BLOCKED
    assert len(server.calls) == before and store.load()[0] == record
    owner.close()  # Simulates OS releasing lease after owner loss; no killing.
    result = RuntimeOwnership(OwnershipStore(store.root), make_client()).recover(record.execution_id)
    assert result.state == State.CLEANED


def test_duplicate_json_fields_and_checksum_damage_preserved(environment):
    _, record = start(environment)
    store, server, make_client = environment
    path = store.root / (record.execution_id + ".json")
    raw = path.read_bytes().replace(b'"version":1', b'"version":0,"version":1')
    path.write_bytes(raw)
    before = len(server.calls)
    assert RuntimeOwnership(store, make_client()).recover(record.execution_id).state == State.BLOCKED
    assert path.read_bytes() == raw and len(server.calls) == before


def test_account_change_between_operation_and_runtime_get_blocks_delete(environment):
    _, record = start(environment)
    store, server, make_client = environment
    client = make_client()
    verified = [ACCOUNT]
    client._account_verifier = lambda _: verified[0]
    def response(request):
        verified[0] = OTHER_ACCOUNT
        return httpx.Response(200, json=server.operation(True))
    server.overrides["GET", "/v1/operations/mock-op"] = response
    before = len(server.calls)
    result = RuntimeOwnership(store, client).recover(record.execution_id)
    assert result.state == State.RECOVERY_REQUIRED
    assert [r.method for r in server.calls[before:]] == ["GET"]


def test_successful_remote_delete_disk_failure_then_absence_recovery(environment, monkeypatch):
    owner, record = start(environment)
    store, server, make_client = environment
    original_save = store._save
    def save(updated, **kwargs):
        if updated.state == State.CLEANED:
            raise module._blocked()
        return original_save(updated, **kwargs)
    monkeypatch.setattr(store, "_save", save)
    def deleted(request):
        server.overrides["GET", "/v1beta/" + record.runtime_name] = httpx.Response(404, json={})
        return httpx.Response(200, json={})
    server.overrides["DELETE", "/v1beta/" + record.runtime_name] = deleted
    assert owner.cleanup().state == State.CLEANUP_REQUIRED
    assert store.load()[0].state == State.CLEANUP_REQUIRED
    owner.close()
    before = len(server.calls)
    fresh_store = OwnershipStore(store.root)
    result = RuntimeOwnership(fresh_store, make_client()).recover(record.execution_id)
    assert result.state == State.CLEANED
    assert all(r.method == "GET" for r in server.calls[before:])


def test_operation_id_collision_during_recovery_never_deletes(environment):
    _, record = start(environment)
    store, server, make_client = environment
    server.overrides["GET", "/v1/operations/mock-op"] = httpx.Response(200, json={
        "name": "operations/mock-op", "done": True,
        "error": {"code": 6, "status": "ALREADY_EXISTS"},
    })
    before = len(server.calls)
    result = RuntimeOwnership(store, make_client()).recover(record.execution_id)
    assert result.state == State.BLOCKED and not result.cleanup_required
    assert store.load()[0].state == State.BLOCKED
    assert all(r.method == "GET" for r in server.calls[before:])


def test_missing_record_never_becomes_new_attempt(environment):
    store, server, make_client = environment
    result = RuntimeOwnership(store, make_client()).recover("11111111-1111-4111-8111-111111111111")
    assert result.state == State.BLOCKED and server.calls == []
    assert store.load() == []


def test_default_path_is_per_user_and_constructor_does_not_write(tmp_path, monkeypatch):
    base = tmp_path / "fake-app-data"
    monkeypatch.setattr(module, "get_app_data_dir", lambda: base)
    store = OwnershipStore()
    assert store.root == base / "colab_runtime_ownership"
    assert not base.exists()


def test_broadened_real_file_permissions_block_without_repair(environment):
    _, record = start(environment)
    store, server, make_client = environment
    path = store.root / (record.execution_id + ".json")
    original = path.read_bytes()
    if os.name == "nt":
        import subprocess
        from src.services.windows_system import resolve_system32_executable
        subprocess.run([str(resolve_system32_executable("icacls.exe")), str(path),
                        "/grant", "*S-1-1-0:(R)"], check=True, capture_output=True,
                       shell=False, timeout=5)
    else:
        path.chmod(0o644)
    before = len(server.calls)
    result = RuntimeOwnership(store, make_client()).recover(record.execution_id)
    assert result.state == State.BLOCKED and len(server.calls) == before
    assert path.read_bytes() == original
    with pytest.raises(RuntimeClientError):
        module._permissions(path)  # Not silently repaired by recovery.


def test_consumed_client_cannot_prepare_another_attempt_after_cleanup(environment):
    owner, _ = start(environment)
    store, server, _ = environment
    owner.cleanup()
    previous = store.load()
    before = len(server.calls)
    with pytest.raises(RuntimeClientError) as error:
        owner.create()
    assert error.value.code == Code.DUPLICATE_CREATE
    assert len(server.calls) == before and store.load() == previous
