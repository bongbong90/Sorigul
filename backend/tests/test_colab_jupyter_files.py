import base64
import hashlib
import logging
import os
import socket
import traceback
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote

import pytest

from src.services.colab_jupyter_client import JupyterClientError, JupyterCode
from src.services.colab_jupyter_files import (
    MAX_ATTEMPTS_PER_INDEX, REMOTE_ROOT, ColabJupyterFileTransfer, IntegrityLevel,
    RemoteOwnership as Own, TransferCode as Code, TransferError, TransferStatus as Status, _ChunkSequence,
)
from src.services.colab_runtime_client import ConnectionInfo


TOKEN = "mock-proxy-secret"
URL = "https://runtime.example.invalid/prefix"
NOW = datetime(2026, 11, 13, tzinfo=timezone.utc)
RUN = "0123456789abcdef0123456789abcdef"
RUN_DIR = f"{REMOTE_ROOT}/{RUN}"
CHUNK = 64 * 1024


def info(token=TOKEN, url=URL, expiry=None):
    return ConnectionInfo(url, token, expiry or NOW + timedelta(hours=1))


class FakeContents:
    """In-memory Jupyter Contents API with LargeFileManager chunk semantics."""

    def __init__(self):
        self.dirs = set()
        self.files = {}
        self.calls = []
        self.hash_supported = True
        self.report_size = True
        self.hooks = []          # callables(method, path, body, n) -> response | None
        self.drop_chunk = None   # ignore this chunk marker's append (but reply OK)
        self.intermediate_model = None  # override metadata after applying a chunk

    def model(self, path, hashed=False, listing=False):
        if path in self.dirs:
            model = {"path": path, "type": "directory"}
            if listing:
                model["content"] = [
                    {"path": f, "type": "file"} for f in self.files
                    if f.rsplit("/", 1)[0] == path] + [
                    {"path": d, "type": "directory"} for d in self.dirs
                    if d.rsplit("/", 1)[0] == path and d != path]
            return model
        data = bytes(self.files[path])
        model = {"path": path, "type": "file"}
        if self.report_size:
            model["size"] = len(data)
        if hashed and self.hash_supported:
            model.update(hash=hashlib.sha256(data).hexdigest(), hash_algorithm="sha256")
        return model

    def http(self, method, url, headers, body, timeout):
        assert url.startswith(URL + "/api/contents/")
        assert set(headers) == {"X-Colab-Runtime-Proxy-Token", "Content-Type"}
        assert "Authorization" not in headers
        assert headers["X-Colab-Runtime-Proxy-Token"] in (TOKEN, "renewed-proxy")
        assert timeout > 0
        rest = url[len(URL + "/api/contents/"):]
        path, _, query = rest.partition("?")
        path = unquote(path)
        self.calls.append((method, path, query, body))
        for hook in list(self.hooks):
            result = hook(method, path, body, len(self.calls))
            if result is not None:
                return result
        exists = path in self.dirs or path in self.files
        if method == "GET":
            if not exists:
                return 404, None
            return 200, self.model(path, hashed="hash=1" in query,
                                   listing="content=1" in query)
        if method == "DELETE":
            if not exists:
                return 404, None
            if path in self.dirs:
                assert not any(f.startswith(path + "/") for f in self.files)
                self.dirs.discard(path)
            else:
                del self.files[path]
            return 204, None
        assert method == "PUT"
        if body["type"] == "directory":
            self.dirs.add(path)
            return (200 if exists else 201), self.model(path)
        assert body["format"] == "base64"
        parent = path.rsplit("/", 1)[0]
        assert parent in self.dirs
        data = base64.b64decode(body["content"])
        chunk = body.get("chunk")
        if chunk == self.drop_chunk and chunk is not None:
            pass
        elif chunk is None or chunk == 1:
            self.files[path] = bytearray(data)
        else:
            self.files[path] += data
        model = self.model(path)
        if chunk is not None and chunk != -1 and self.intermediate_model is not None:
            model = self.intermediate_model(chunk, model)
        return (200 if exists else 201), model

    def puts(self, path=None):
        return [c for c in self.calls if c[0] == "PUT" and (path is None or c[1] == path)]


@pytest.fixture(autouse=True)
def deny_external_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("External network forbidden in PHASE 06 tests")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)


@pytest.fixture
def server():
    return FakeContents()


def make(server, **kwargs):
    kwargs.setdefault("run_id", RUN)
    kwargs.setdefault("chunk_bytes", CHUNK)
    kwargs.setdefault("utcnow", lambda: NOW)
    return ColabJupyterFileTransfer(kwargs.pop("conn", info()),
                                    http_request=server.http, **kwargs)


def audio(tmp_path, name="chunk-00000.mp3", size=1000, seed=7):
    path = tmp_path / name
    path.write_bytes(bytes((seed + i * 31) % 251 for i in range(size)))
    return path


def remote(index):
    return f"{RUN_DIR}/chunk-{index:05d}.mp3"


def timeout_error():
    return JupyterClientError(JupyterCode.NETWORK_TIMEOUT)


# 1. small file ----------------------------------------------------------------

def test_small_file_single_request_verified_by_remote_sha256(server, tmp_path):
    source = audio(tmp_path, size=1000)
    transfer = make(server)
    assert transfer.prepare() == RUN_DIR
    record = transfer.upload(0, source)
    assert record.status is Status.VERIFIED and record.completed
    assert record.integrity is IntegrityLevel.CONTENT_SHA256
    assert record.sha256 == hashlib.sha256(source.read_bytes()).hexdigest()
    assert (record.size, record.chunks_total, record.chunks_acknowledged) == (1000, 1, 1)
    puts = server.puts(remote(0))
    assert len(puts) == 1 and "chunk" not in puts[0][3]
    assert bytes(server.files[remote(0)]) == source.read_bytes()


def test_without_remote_hash_only_size_is_confirmed(server, tmp_path):
    server.hash_supported = False
    transfer = make(server)
    transfer.prepare()
    record = transfer.upload(0, audio(tmp_path))
    assert record.status is Status.ACKNOWLEDGED and record.completed
    assert record.integrity is IntegrityLevel.SIZE_CONFIRMED


def test_without_size_or_hash_only_response_is_confirmed(server, tmp_path):
    server.hash_supported = server.report_size = False
    transfer = make(server)
    transfer.prepare()
    record = transfer.upload(0, audio(tmp_path))
    assert record.status is Status.ACKNOWLEDGED
    assert record.integrity is IntegrityLevel.RESPONSE_ONLY


def test_prepare_reuses_root_and_rejects_existing_run_dir(server):
    server.dirs.add(REMOTE_ROOT)
    transfer = make(server)
    transfer.prepare()
    assert RUN_DIR in server.dirs
    assert not [c for c in server.puts() if c[1] == REMOTE_ROOT]
    with pytest.raises(TransferError) as exc:
        make(server).prepare()
    assert exc.value.code is Code.REMOTE_EXISTS


def test_upload_requires_prepare(server, tmp_path):
    with pytest.raises(TransferError) as exc:
        make(server).upload(0, audio(tmp_path))
    assert exc.value.code is Code.NOT_PREPARED
    assert server.calls == []


# 2. multi-chunk ----------------------------------------------------------------

def test_multi_chunk_upload_streams_bounded_ordered_chunks(server, tmp_path, monkeypatch):
    size = CHUNK * 3 + 123
    source = audio(tmp_path, size=size)
    reads = []
    real_open = open

    def tracking_open(path, mode="r", *args, **kwargs):
        handle = real_open(path, mode, *args, **kwargs)
        if "b" in mode and str(path) == str(source.resolve()):
            original = handle.read
            handle.read = lambda n=-1: reads.append(n) or original(n)
        return handle
    monkeypatch.setattr("builtins.open", tracking_open)

    transfer = make(server)
    transfer.prepare()
    record = transfer.upload(0, source)
    assert record.status is Status.VERIFIED
    assert (record.chunks_total, record.chunks_acknowledged) == (4, 4)
    puts = server.puts(remote(0))
    assert [p[3]["chunk"] for p in puts] == [1, 2, 3, -1]
    assert all(len(base64.b64decode(p[3]["content"])) <= CHUNK for p in puts)
    assert reads and all(0 < n <= CHUNK for n in reads)  # never read() the whole file
    assert bytes(server.files[remote(0)]) == source.read_bytes()


def test_chunk_size_bounds_enforced():
    for bad in (1024, 9 * 1024 * 1024, 4.0, True):
        with pytest.raises(ValueError):
            ColabJupyterFileTransfer(info(), run_id=RUN, chunk_bytes=bad)


# 3. order gaps and duplicates --------------------------------------------------

def test_chunk_sequence_blocks_gaps_duplicates_and_overrun():
    seq = _ChunkSequence(3)
    assert seq.issue() == (1, 1)
    with pytest.raises(TransferError):
        seq.issue()                 # next issued before ack
    with pytest.raises(TransferError):
        seq.acknowledge(2)          # gap
    seq.acknowledge(1)
    with pytest.raises(TransferError):
        seq.acknowledge(1)          # duplicate
    assert seq.issue() == (2, 2)
    seq.acknowledge(2)
    assert seq.issue() == (3, -1)
    seq.acknowledge(3)
    assert seq.complete
    with pytest.raises(TransferError):
        seq.issue()                 # past the final chunk
    assert _ChunkSequence(1).issue() == (1, None)
    with pytest.raises(TransferError):
        _ChunkSequence(0)


def test_remote_dropped_chunk_detected_by_final_size(server, tmp_path):
    server.drop_chunk = 2
    transfer = make(server)
    transfer.prepare()
    record = transfer.upload(0, audio(tmp_path, size=CHUNK * 3))
    assert record.status is Status.FAILED and not record.completed
    assert record.error_code is Code.INTEGRITY_MISMATCH
    assert record.chunks_acknowledged == 2 and record.remote_may_exist
    assert len(server.puts(remote(0))) == 3   # final size detects loss, no re-send


def test_remote_hash_mismatch_is_not_completion(server, tmp_path):
    def corrupt(method, path, body, n):
        if method == "GET" and path == remote(0) and remote(0) in server.files:
            server.files[remote(0)][0] ^= 0xFF
            server.hooks.clear()
    transfer = make(server)
    transfer.prepare()
    server.hooks.append(corrupt)
    record = transfer.upload(0, audio(tmp_path))
    assert record.status is Status.FAILED
    assert record.error_code is Code.INTEGRITY_MISMATCH


# 4. local change ---------------------------------------------------------------

def test_local_file_growth_during_upload_detected(server, tmp_path):
    source = audio(tmp_path, size=CHUNK * 2 + 5)

    def grow(method, path, body, n):
        if method == "PUT" and body.get("chunk") == 1:
            with open(source, "ab") as handle:
                handle.write(b"x" * 10)
    server.hooks.append(grow)
    transfer = make(server)
    transfer.prepare()
    record = transfer.upload(0, source)
    assert record.status is Status.FAILED and record.error_code is Code.LOCAL_FILE_CHANGED
    assert record.remote_may_exist and not record.completed


def test_same_size_rewrite_with_restored_mtime_detected_by_hash(server, tmp_path):
    source = audio(tmp_path, size=CHUNK * 2 + 5)
    stamp = os.stat(source)

    def rewrite(method, path, body, n):
        if method == "PUT" and body.get("chunk") == 1:
            data = bytearray(source.read_bytes())
            data[-1] ^= 0xFF
            source.write_bytes(bytes(data))
            os.utime(source, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    server.hooks.append(rewrite)
    transfer = make(server)
    transfer.prepare()
    record = transfer.upload(0, source)
    assert record.status is Status.FAILED and record.error_code is Code.LOCAL_FILE_CHANGED


def test_invalid_local_files_rejected_before_network(server, tmp_path):
    transfer = make(server)
    transfer.prepare()
    before = len(server.calls)
    empty = tmp_path / "chunk-00001.mp3"
    empty.write_bytes(b"")
    wav = audio(tmp_path, name="chunk-00002.wav")
    for index, path in ((1, empty), (2, wav), (3, tmp_path / "missing.mp3"), (4, tmp_path)):
        record = transfer.upload(index, path)
        assert record.status is Status.FAILED
        assert record.error_code is Code.LOCAL_FILE_INVALID
        assert not record.remote_may_exist
    assert len(server.calls) == before


# 5. remote path escape ---------------------------------------------------------

@pytest.mark.parametrize("run_id", ["../" + RUN[3:], RUN.upper(), RUN + "/x", "", 7])
def test_invalid_run_id_rejected(server, run_id):
    with pytest.raises(TransferError) as exc:
        make(server, run_id=run_id)
    assert exc.value.code is Code.REMOTE_PATH_INVALID


@pytest.mark.parametrize("index", [-1, 100000, True, "1", 1.0, None])
def test_invalid_index_rejected(server, tmp_path, index):
    transfer = make(server)
    transfer.prepare()
    before = len(server.calls)
    with pytest.raises(TransferError) as exc:
        transfer.upload(index, audio(tmp_path))
    assert exc.value.code is Code.REMOTE_PATH_INVALID
    assert len(server.calls) == before


def test_request_guard_blocks_foreign_paths(server):
    transfer = make(server)
    for path in ("../etc/passwd", f"{REMOTE_ROOT}/{'f' * 32}/chunk-00000.mp3",
                 f"{RUN_DIR}/../x/chunk-00000.mp3", f"{RUN_DIR}/chunk-0.mp3",
                 f"{RUN_DIR}/chunk-00000.mp3/..", "/" + RUN_DIR):
        with pytest.raises(TransferError) as exc:
            transfer._request("GET", path)
        assert exc.value.code is Code.REMOTE_PATH_INVALID
        assert transfer._delete_owned(path) is Code.NOT_OWNED
    assert server.calls == []


def test_response_for_another_path_is_not_accepted(server, tmp_path):
    def foreign(method, path, body, n):
        if method == "PUT" and path == remote(0):
            return 201, {"path": f"{REMOTE_ROOT}/other/chunk-00000.mp3", "type": "file"}
    server.hooks.append(foreign)
    transfer = make(server)
    transfer.prepare()
    record = transfer.upload(0, audio(tmp_path))
    assert record.status is Status.STATE_UNCERTAIN
    assert record.error_code is Code.RESPONSE_INVALID
    assert all(c[1].startswith(REMOTE_ROOT) for c in server.calls)


def test_insecure_or_foreign_connection_rejected():
    for bad in ("http://runtime.example.invalid", "https://user@runtime.example.invalid",
                "https://runtime.example.invalid/x?y=1"):
        with pytest.raises(TransferError) as exc:
            ColabJupyterFileTransfer(info(url=bad), run_id=RUN)
        assert exc.value.code is Code.INVALID_CONNECTION


# 6. lost response --------------------------------------------------------------

def test_lost_chunk_response_keeps_uncertain_state_and_never_resends(server, tmp_path):
    source = audio(tmp_path, size=CHUNK * 3)

    def lose(method, path, body, n):
        if method == "PUT" and body.get("chunk") == 2:
            server.files[path] += base64.b64decode(body["content"])  # applied...
            raise timeout_error()                                   # ...reply lost
    server.hooks.append(lose)
    transfer = make(server)
    transfer.prepare()
    record = transfer.upload(0, source)
    assert record.status is Status.STATE_UNCERTAIN and not record.completed
    assert record.error_code is Code.STATE_UNCERTAIN
    assert record.chunks_acknowledged == 1 and not record.all_chunks_sent
    assert record.remote_may_exist
    puts = len(server.puts())
    with pytest.raises(TransferError) as exc:
        transfer.upload(0, source)
    assert exc.value.code is Code.DUPLICATE_UPLOAD
    assert transfer.reconcile(0) == record          # partial: nothing to promote
    assert len(server.puts()) == puts
    assert transfer.records() == (record,)


def test_lost_final_response_promoted_only_by_matching_remote_hash(server, tmp_path):
    source = audio(tmp_path, size=CHUNK + 10)

    def lose(method, path, body, n):
        if method == "PUT" and body.get("chunk") == -1:
            server.files[path] += base64.b64decode(body["content"])
            raise timeout_error()
    server.hooks.append(lose)
    transfer = make(server)
    transfer.prepare()
    record = transfer.upload(0, source)
    assert record.status is Status.STATE_UNCERTAIN and record.all_chunks_sent
    server.hooks.clear()
    server.hash_supported = False
    still = transfer.reconcile(0)
    assert still.status is Status.STATE_UNCERTAIN       # size alone is not enough
    server.hash_supported = True
    promoted = transfer.reconcile(0)
    assert promoted.status is Status.VERIFIED
    assert promoted.integrity is IntegrityLevel.CONTENT_SHA256
    assert len(server.puts(remote(0))) == 2


def test_server_error_on_put_is_uncertain_not_failed(server, tmp_path):
    server.hooks.append(lambda m, p, b, n: (502, None) if m == "PUT" and p == remote(0) else None)
    transfer = make(server)
    transfer.prepare()
    record = transfer.upload(0, audio(tmp_path))
    assert record.status is Status.STATE_UNCERTAIN and record.remote_may_exist


def test_lost_run_dir_create_reply_is_owned_for_cleanup(server):
    def lose(method, path, body, n):
        if method == "PUT" and path == RUN_DIR:
            server.dirs.add(path)
            raise timeout_error()
    server.hooks.append(lose)
    transfer = make(server)
    with pytest.raises(TransferError) as exc:
        transfer.prepare()
    assert exc.value.code is Code.STATE_UNCERTAIN
    server.hooks.clear()
    report = transfer.cleanup()
    assert report.run_dir_deleted and RUN_DIR not in server.dirs
    assert REMOTE_ROOT in server.dirs     # shared root never deleted


# 7. token expiry / rejection ----------------------------------------------------

def test_expired_token_sends_nothing_and_allows_explicit_refresh(server, tmp_path):
    clock = {"now": NOW}
    transfer = make(server, conn=info(expiry=NOW + timedelta(minutes=5)),
                    utcnow=lambda: clock["now"],
                    refresh_connection=lambda: info("renewed-proxy", expiry=NOW + timedelta(hours=2)))
    transfer.prepare()
    clock["now"] = NOW + timedelta(minutes=10)
    before = len(server.calls)
    source = audio(tmp_path)
    record = transfer.upload(0, source)
    assert record.status is Status.FAILED
    assert record.error_code is Code.TOKEN_REFRESH_REQUIRED
    assert not record.remote_may_exist and len(server.calls) == before
    transfer.refresh_connection()
    retried = transfer.upload(0, source)
    assert retried.status is Status.VERIFIED and retried.attempts == 2


def test_refresh_to_other_origin_rejected(server):
    transfer = make(server, refresh_connection=lambda: info(url="https://evil.example.invalid"))
    with pytest.raises(TransferError) as exc:
        transfer.refresh_connection()
    assert exc.value.code is Code.TOKEN_REFRESH_REQUIRED
    with pytest.raises(TransferError):
        make(server).refresh_connection()


def test_token_expiring_mid_upload_stops_before_next_chunk(server, tmp_path):
    clock = {"now": NOW}

    def expire(method, path, body, n):
        if method == "PUT" and body.get("chunk") == 1:
            clock["now"] = NOW + timedelta(hours=2)
    server.hooks.append(expire)
    transfer = make(server, utcnow=lambda: clock["now"])
    transfer.prepare()
    record = transfer.upload(0, audio(tmp_path, size=CHUNK * 2))
    assert record.error_code is Code.TOKEN_REFRESH_REQUIRED
    assert record.status is Status.FAILED and record.remote_may_exist
    assert len(server.puts(remote(0))) == 1


@pytest.mark.parametrize("status,code", [(401, Code.AUTH_REJECTED), (403, Code.POLICY_REJECTED),
                                         (413, Code.POLICY_REJECTED), (429, Code.RATE_LIMITED)])
def test_auth_policy_and_rate_limit_halt_without_retry(server, tmp_path, status, code):
    server.hooks.append(lambda m, p, b, n: (status, None) if m == "PUT" and p == remote(0) else None)
    transfer = make(server)
    transfer.prepare()
    record = transfer.upload(0, audio(tmp_path))
    assert record.status is Status.FAILED and record.error_code is code
    assert not record.remote_may_exist and not record.retryable
    before = len(server.calls)
    for index in (0, 1):
        with pytest.raises(TransferError) as exc:
            transfer.upload(index, audio(tmp_path, name=f"chunk-0000{index + 5}.mp3"))
        assert exc.value.code is code
    assert len(server.calls) == before


# 8. network timeout ------------------------------------------------------------

def test_timeout_before_send_is_retryable_but_bounded(server, tmp_path):
    def stall(method, path, body, n):
        if method == "GET" and path == remote(0):
            raise timeout_error()
    server.hooks.append(stall)
    transfer = make(server)
    transfer.prepare()
    source = audio(tmp_path)
    for attempt in range(1, MAX_ATTEMPTS_PER_INDEX + 1):
        record = transfer.upload(0, source)
        assert record.status is Status.FAILED and record.error_code is Code.NETWORK_TIMEOUT
        assert not record.remote_may_exist and record.attempts == attempt
    with pytest.raises(TransferError) as exc:
        transfer.upload(0, source)
    assert exc.value.code is Code.ATTEMPTS_EXHAUSTED
    assert server.puts(remote(0)) == []


def test_timeout_retry_succeeds_once_network_returns(server, tmp_path):
    hook = lambda m, p, b, n: (_ for _ in ()).throw(timeout_error()) if m == "GET" and p == remote(0) else None
    server.hooks.append(hook)
    transfer = make(server)
    transfer.prepare()
    source = audio(tmp_path)
    assert transfer.upload(0, source).error_code is Code.NETWORK_TIMEOUT
    server.hooks.clear()
    assert transfer.upload(0, source).status is Status.VERIFIED


def test_verify_timeout_keeps_acknowledged_with_separate_error(server, tmp_path):
    def stall(method, path, body, n):
        if method == "GET" and path == remote(0) and remote(0) in server.files:
            raise timeout_error()
    server.hooks.append(stall)
    transfer = make(server)
    transfer.prepare()
    record = transfer.upload(0, audio(tmp_path))
    assert record.status is Status.ACKNOWLEDGED and record.error_code is None
    assert record.integrity is IntegrityLevel.SIZE_CONFIRMED
    assert record.verification_error is Code.NETWORK_TIMEOUT


# 9. duplicate uploads ----------------------------------------------------------

def test_duplicate_index_and_duplicate_local_file_blocked(server, tmp_path):
    transfer = make(server)
    transfer.prepare()
    source = audio(tmp_path)
    assert transfer.upload(0, source).completed
    puts = len(server.puts())
    for index in (0, 1):
        with pytest.raises(TransferError) as exc:
            transfer.upload(index, source)
        assert exc.value.code is Code.DUPLICATE_UPLOAD
    assert len(server.puts()) == puts


def test_existing_remote_file_is_never_overwritten_or_deleted(server, tmp_path):
    transfer = make(server)
    transfer.prepare()
    server.files[remote(0)] = bytearray(b"someone else")
    record = transfer.upload(0, audio(tmp_path))
    assert record.error_code is Code.REMOTE_EXISTS and not record.remote_may_exist
    assert server.puts(remote(0)) == []
    with pytest.raises(TransferError) as exc:
        transfer.upload(0, audio(tmp_path, name="chunk-00009.mp3"))
    assert exc.value.code is Code.DUPLICATE_UPLOAD
    transfer.cleanup()
    assert bytes(server.files[remote(0)]) == b"someone else"


def test_create_race_200_reply_marks_uncertain(server, tmp_path):
    server.hooks.append(lambda m, p, b, n: (200, {"path": p, "type": "file"}) if m == "PUT" and p == remote(0) else None)
    transfer = make(server)
    transfer.prepare()
    record = transfer.upload(0, audio(tmp_path))
    assert record.status is Status.STATE_UNCERTAIN and record.error_code is Code.REMOTE_EXISTS


def test_cancel_stops_before_next_chunk(server, tmp_path):
    transfer = make(server)

    def cancel(method, path, body, n):
        if method == "PUT" and body.get("chunk") == 1:
            transfer.cancel()
    server.hooks.append(cancel)
    transfer.prepare()
    record = transfer.upload(0, audio(tmp_path, size=CHUNK * 3))
    assert record.status is Status.FAILED and record.error_code is Code.CANCELLED
    assert record.remote_may_exist and len(server.puts(remote(0))) == 1
    with pytest.raises(TransferError) as exc:
        transfer.upload(1, audio(tmp_path, name="chunk-00001.mp3"))
    assert exc.value.code is Code.CANCELLED
    report = transfer.cleanup()
    assert remote(0) in report.deleted_paths and not report.cleanup_required


# 10. cleanup -------------------------------------------------------------------

def test_cleanup_failure_recorded_separately_and_retryable(server, tmp_path):
    transfer = make(server)
    transfer.prepare()
    first = transfer.upload(0, audio(tmp_path))
    second = transfer.upload(1, audio(tmp_path, name="chunk-00001.mp3", seed=3))
    server.hooks.append(lambda m, p, b, n: (500, None) if m == "DELETE" and p == remote(1) else None)
    report = transfer.cleanup()
    assert report.cleanup_required and not report.run_dir_deleted
    assert report.deleted_paths == (remote(0),)
    assert dict(report.failed_paths) == {remote(1): Code.DELETE_FAILED,
                                         RUN_DIR: Code.DELETE_FAILED}
    assert report.error_code is Code.DELETE_FAILED and not report.runtime_cleanup_claimed
    after = {r.index: r for r in transfer.records()}
    assert after[1].status is second.status and after[1].error_code is None
    assert after[0].remote_deleted and not after[1].remote_deleted
    assert first.status is Status.VERIFIED
    with pytest.raises(TransferError) as exc:
        transfer.upload(2, audio(tmp_path, name="chunk-00002.mp3"))
    assert exc.value.code is Code.TRANSFER_CLOSED
    server.hooks.clear()
    retry = transfer.cleanup()
    assert retry.deleted_paths == (remote(1), RUN_DIR)
    assert retry.run_dir_deleted and not retry.cleanup_required
    assert not server.files and server.dirs == {REMOTE_ROOT}
    deletes = [c for c in server.calls if c[0] == "DELETE"]
    assert all(c[1] in (remote(0), remote(1), RUN_DIR) for c in deletes)


def test_cleanup_stops_pass_on_auth_rejection(server, tmp_path):
    transfer = make(server)
    transfer.prepare()
    for i in range(3):
        transfer.upload(i, audio(tmp_path, name=f"chunk-0000{i}.mp3", seed=i))
    server.hooks.append(lambda m, p, b, n: (401, None) if m == "DELETE" else None)
    report = transfer.cleanup()
    assert len([c for c in server.calls if c[0] == "DELETE"]) == 1
    assert all(code is Code.AUTH_REJECTED for _, code in report.failed_paths)
    assert len(report.failed_paths) == 4 and report.cleanup_required


def test_cleanup_skips_files_that_were_never_created(server, tmp_path):
    transfer = make(server)
    transfer.prepare()
    server.hooks.append(lambda m, p, b, n: (400, None) if m == "PUT" and p == remote(0) else None)
    record = transfer.upload(0, audio(tmp_path))
    assert record.error_code is Code.UPLOAD_REJECTED and not record.remote_may_exist
    server.hooks.clear()
    report = transfer.cleanup()
    assert report.deleted_paths == (RUN_DIR,)


# 11. source preservation -------------------------------------------------------

def test_local_sources_are_never_modified_or_deleted(server, tmp_path):
    sources = [audio(tmp_path, name=f"chunk-0000{i}.mp3", size=CHUNK + i * 7, seed=i)
               for i in range(3)]
    before = {p: (p.read_bytes(), os.stat(p).st_mtime_ns) for p in sources}
    server.hooks.append(lambda m, p, b, n: (_ for _ in ()).throw(timeout_error())
                        if m == "PUT" and p == remote(2) else None)
    transfer = make(server)
    transfer.prepare()
    for i, path in enumerate(sources):
        transfer.upload(i, path)
    server.hooks.clear()
    transfer.cleanup()
    for path, (data, mtime) in before.items():
        assert path.exists() and path.read_bytes() == data
        assert os.stat(path).st_mtime_ns == mtime
    assert sorted(p.name for p in tmp_path.iterdir()) == [p.name for p in sources]


# 12. secrets never exposed -----------------------------------------------------

def test_no_token_or_url_in_logs_errors_or_reprs(server, tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    leaked = []

    def leaky(method, path, body, n):
        if method == "PUT" and path == remote(1):
            raise OSError(TOKEN + URL)
        if method == "DELETE" and path == remote(1):
            raise RuntimeError(TOKEN + URL)
    server.hooks.append(leaky)
    transfer = make(server, conn=info(expiry=NOW + timedelta(hours=1)))
    transfer.prepare()
    transfer.upload(0, audio(tmp_path))
    record = transfer.upload(1, audio(tmp_path, name="chunk-00001.mp3", seed=9))
    assert record.error_code is Code.STATE_UNCERTAIN
    report = transfer.cleanup()
    try:
        transfer.upload(2, audio(tmp_path, name="chunk-00002.mp3"))
    except TransferError as exc:
        leaked.append("".join(traceback.format_exception(exc)))
        assert exc.__cause__ is None
    texts = [caplog.text, repr(transfer.records()), repr(report), repr(transfer), *leaked]
    for text in texts:
        assert TOKEN not in text and "runtime.example.invalid" not in text
    assert caplog.records == []


# #233 unreliable intermediate models ------------------------------------------

@pytest.mark.parametrize("size", [None, 0, CHUNK, -1, True, "stale"])
def test_233_intermediate_size_is_not_cumulative_proof(server, tmp_path, size):
    def interim(chunk, model):
        model.pop("size", None)
        if size is not None:
            model["size"] = size
        return model
    server.intermediate_model = interim
    source = audio(tmp_path, size=CHUNK * 3 + 7)
    transfer = make(server)
    transfer.prepare()
    record = transfer.upload(0, source)
    assert record.status is Status.VERIFIED and record.ownership is Own.OWNED
    assert record.integrity is IntegrityLevel.CONTENT_SHA256
    assert record.chunks_acknowledged == record.chunks_total == 4
    assert [c[3]["chunk"] for c in server.puts(remote(0))] == [1, 2, 3, -1]
    assert bytes(server.files[remote(0)]) == source.read_bytes()


@pytest.mark.parametrize("model", [None, {}, {"size": 0}, {"path": "stale", "type": "directory"}])
def test_233_later_intermediate_model_is_ignored(server, tmp_path, model):
    server.intermediate_model = lambda chunk, original: original if chunk == 1 else model
    transfer = make(server)
    transfer.prepare()
    record = transfer.upload(0, audio(tmp_path, size=CHUNK * 3))
    assert record.status is Status.VERIFIED and record.chunks_acknowledged == 3
    assert record.ownership is Own.OWNED
    assert transfer.cleanup().deleted_paths == (remote(0), RUN_DIR)


@pytest.mark.parametrize("model", [None, {}, {"path": remote(0)}, {"type": "file"},
                                        {"path": remote(0), "type": "directory"}])
def test_233_incomplete_first_201_is_blocked_without_ownership(server, tmp_path, model):
    server.intermediate_model = lambda chunk, original: model
    transfer = make(server)
    transfer.prepare()
    source = audio(tmp_path, size=CHUNK * 3)
    record = transfer.upload(0, source)
    assert record.status is Status.STATE_UNCERTAIN
    assert record.error_code is Code.RESPONSE_INVALID
    assert record.ownership is Own.UNCERTAIN and not record.retryable
    assert record.chunks_acknowledged == 0 and not record.all_chunks_sent
    assert transfer.reconcile(0) == record
    with pytest.raises(TransferError) as exc:
        transfer.upload(0, source)
    assert exc.value.code is Code.DUPLICATE_UPLOAD
    assert len(server.puts(remote(0))) == 1
    report = transfer.cleanup()
    assert deletes(server) == [] and report.cleanup_required
    assert (remote(0), Code.STATE_UNCERTAIN) in report.skipped_paths


def test_233_intermediate_size_never_confirms_final_integrity(server, tmp_path):
    server.report_size = server.hash_supported = False
    server.intermediate_model = lambda chunk, model: dict(model, size=CHUNK * chunk)
    transfer = make(server)
    transfer.prepare()
    record = transfer.upload(0, audio(tmp_path, size=CHUNK * 3))
    assert record.status is Status.ACKNOWLEDGED
    assert record.integrity is IntegrityLevel.RESPONSE_ONLY


@pytest.mark.parametrize("fault", ["size", "hash", "duplicate", "unfinished"])
def test_233_final_content_faults_never_complete(server, tmp_path, fault):
    def corrupt(method, path, body, n):
        if path != remote(0):
            return
        if method == "PUT" and body.get("chunk") == 2 and fault == "duplicate":
            server.files[path] += base64.b64decode(body["content"])
        if method == "PUT" and body.get("chunk") == -1 and fault == "unfinished":
            return 200, server.model(path)  # HTTP success without committing final bytes
        if method == "GET" and path in server.files and fault in ("size", "hash"):
            model = server.model(path, hashed=True)
            model.update({"size": len(server.files[path]) + 1} if fault == "size"
                         else {"hash": "0" * 64})
            return 200, model
    server.hooks.append(corrupt)
    transfer = make(server)
    transfer.prepare()
    source = audio(tmp_path, size=CHUNK * 3)
    record = transfer.upload(0, source)
    assert record.status is Status.FAILED and not record.completed
    assert record.error_code is Code.INTEGRITY_MISMATCH
    assert record.integrity is IntegrityLevel.NONE
    assert len(server.puts(remote(0))) == 3
    assert transfer.reconcile(0) == record


@pytest.mark.parametrize("model", [None, {}, {"path": "stale", "type": "file"}])
def test_233_final_model_still_requires_validation(server, tmp_path, model):
    def final(method, path, body, n):
        if method == "PUT" and body.get("chunk") == -1:
            server.files[path] += base64.b64decode(body["content"])
            return 200, model
    server.hooks.append(final)
    transfer = make(server)
    transfer.prepare()
    record = transfer.upload(0, audio(tmp_path, size=CHUNK * 3))
    assert record.status is Status.STATE_UNCERTAIN and record.all_chunks_sent
    assert record.chunks_acknowledged == 2 and record.ownership is Own.OWNED
    before = len(server.calls)
    assert transfer.reconcile(0).status is Status.VERIFIED
    assert all(c[0] == "GET" for c in server.calls[before:])


@pytest.mark.parametrize("applied", [False, True])
def test_233_lost_final_response_requires_hash_and_never_resends(server, tmp_path, applied):
    def lose(method, path, body, n):
        if method == "PUT" and body.get("chunk") == -1:
            if applied:
                server.files[path] += base64.b64decode(body["content"])
            raise timeout_error()
    server.hooks.append(lose)
    transfer = make(server)
    transfer.prepare()
    record = transfer.upload(0, audio(tmp_path, size=CHUNK * 3))
    assert record.status is Status.STATE_UNCERTAIN and record.chunks_acknowledged == 2
    assert record.ownership is Own.OWNED
    before = len(server.calls)
    server.hash_supported = False
    assert transfer.reconcile(0).status is Status.STATE_UNCERTAIN
    server.hash_supported = True
    reconciled = transfer.reconcile(0)
    assert reconciled.status is (Status.VERIFIED if applied else Status.STATE_UNCERTAIN)
    assert reconciled.ownership is Own.OWNED
    assert all(c[0] == "GET" for c in server.calls[before:])
    assert len(server.puts(remote(0))) == 3


@pytest.mark.parametrize("rejected", [False, True])
def test_233_hash_unsupported_never_claims_verified(server, tmp_path, rejected):
    server.hash_supported = False
    def reject_hash(method, path, body, n):
        if rejected and method == "GET" and server.calls[-1][2] == "content=0&hash=1":
            return 400, None
    server.hooks.append(reject_hash)
    transfer = make(server)
    transfer.prepare()
    record = transfer.upload(0, audio(tmp_path, size=CHUNK * 3))
    assert record.status is Status.ACKNOWLEDGED
    assert record.integrity is IntegrityLevel.SIZE_CONFIRMED
    assert record.verification_error is (Code.RESPONSE_INVALID if rejected else None)


# #232 first-PUT ownership race ------------------------------------------------

FOREIGN = b"foreign writer content"


def deletes(server, path=None):
    return [c for c in server.calls if c[0] == "DELETE" and (path is None or c[1] == path)]


def foreign_wins_race(server, path, overwrite=False):
    """GET saw 404; another writer creates `path` before our first PUT lands.
    overwrite=False models a server that answers 200 without our bytes winning."""
    def race(method, p, body, n):
        if method == "PUT" and p == path and body.get("chunk") in (None, 1):
            server.files[path] = bytearray(FOREIGN)
            server.hooks.remove(race)
            if not overwrite:
                return 200, {"path": path, "type": "file", "size": len(FOREIGN)}
    server.hooks.append(race)


def test_232_first_put_200_conflict_never_deleted(server, tmp_path):
    foreign_wins_race(server, remote(0), overwrite=True)
    transfer = make(server)
    transfer.prepare()
    record = transfer.upload(0, audio(tmp_path))
    assert server.calls[-2][:2] == ("GET", remote(0))         # preflight saw 404
    assert record.status is Status.STATE_UNCERTAIN and not record.completed
    assert record.error_code is Code.REMOTE_EXISTS
    assert record.ownership is Own.CONFLICT
    assert record.integrity is IntegrityLevel.NONE
    report = transfer.cleanup()
    assert deletes(server, remote(0)) == []
    assert (remote(0), Code.REMOTE_EXISTS) in report.skipped_paths
    assert report.cleanup_required and remote(0) not in report.deleted_paths
    assert not {r.index: r for r in transfer.records()}[0].remote_deleted
    assert remote(0) in server.files


def test_232_foreign_content_preserved_and_no_further_writes(server, tmp_path):
    foreign_wins_race(server, remote(0))
    transfer = make(server)
    transfer.prepare()
    record = transfer.upload(0, audio(tmp_path, size=CHUNK * 3))
    assert record.ownership is Own.CONFLICT and record.chunks_acknowledged == 0
    assert len(server.puts(remote(0))) == 1                     # chunks 2.. never sent
    transfer.cleanup()
    transfer.cleanup()                                          # explicit retry, still safe
    assert bytes(server.files[remote(0)]) == FOREIGN
    assert deletes(server, remote(0)) == []
    assert all(c[1] in (REMOTE_ROOT, RUN_DIR, remote(0)) for c in server.calls)


def test_232_conflict_protects_run_directory(server, tmp_path):
    foreign_wins_race(server, remote(0))
    transfer = make(server)
    transfer.prepare()
    transfer.upload(0, audio(tmp_path))
    report = transfer.cleanup()
    assert deletes(server) == []
    assert not report.run_dir_deleted and RUN_DIR in server.dirs
    assert (RUN_DIR, Code.NOT_OWNED) in report.skipped_paths
    assert not report.runtime_cleanup_claimed


def test_232_first_put_201_owned_file_cleaned(server, tmp_path):
    transfer = make(server)
    transfer.prepare()
    record = transfer.upload(0, audio(tmp_path, size=CHUNK * 2))
    assert record.ownership is Own.OWNED and record.completed
    report = transfer.cleanup()
    assert report.deleted_paths == (remote(0), RUN_DIR)
    assert report.skipped_paths == () and not report.cleanup_required
    assert report.run_dir_deleted and remote(0) not in server.files
    listing = [c for c in server.calls if c[:3] == ("GET", RUN_DIR, "content=1")]
    assert len(listing) == 1                                     # emptiness proven first


@pytest.mark.parametrize("reply", ["timeout", 502, "foreign-model"])
def test_232_unproven_first_put_never_claims_ownership(server, tmp_path, reply):
    def first(method, path, body, n):
        if method == "PUT" and path == remote(0):
            server.files[path] = bytearray(base64.b64decode(body["content"]))
            if reply == "timeout":
                raise timeout_error()
            if reply == 502:
                return 502, None
            return 201, {"path": f"{RUN_DIR}/chunk-00009.mp3", "type": "file"}
    server.hooks.append(first)
    transfer = make(server)
    transfer.prepare()
    record = transfer.upload(0, audio(tmp_path))
    assert record.status is Status.STATE_UNCERTAIN and record.ownership is Own.UNCERTAIN
    assert record.remote_may_exist and not record.retryable
    server.hooks.clear()
    report = transfer.cleanup()
    assert deletes(server) == []
    assert (remote(0), Code.STATE_UNCERTAIN) in report.skipped_paths
    assert report.cleanup_required and not report.run_dir_deleted
    assert remote(0) in server.files


def test_232_reconcile_does_not_upgrade_ownership(server, tmp_path):
    def lose(method, path, body, n):
        if method == "PUT" and path == remote(0):
            server.files[path] = bytearray(base64.b64decode(body["content"]))
            raise timeout_error()
    server.hooks.append(lose)
    transfer = make(server)
    transfer.prepare()
    transfer.upload(0, audio(tmp_path))
    server.hooks.clear()
    promoted = transfer.reconcile(0)
    assert promoted.status is Status.VERIFIED                   # content matches ours...
    assert promoted.ownership is Own.UNCERTAIN                  # ...creation still unproven
    report = transfer.cleanup()
    assert deletes(server) == [] and report.cleanup_required


def test_232_owned_delete_failure_stays_unresolved(server, tmp_path):
    transfer = make(server)
    transfer.prepare()
    transfer.upload(0, audio(tmp_path))
    server.hooks.append(lambda m, p, b, n: (500, None) if m == "DELETE" else None)
    report = transfer.cleanup()
    assert report.failed_paths == ((remote(0), Code.DELETE_FAILED),
                                   (RUN_DIR, Code.DELETE_FAILED))
    assert report.deleted_paths == () and report.cleanup_required
    assert not transfer.records()[0].remote_deleted
    assert len(deletes(server)) == 1                            # run dir not attempted


def test_232_mixed_owned_and_conflict_cleanup(server, tmp_path):
    foreign_wins_race(server, remote(1))
    transfer = make(server)
    transfer.prepare()
    owned = transfer.upload(0, audio(tmp_path, seed=1))
    conflict = transfer.upload(1, audio(tmp_path, name="chunk-00001.mp3", seed=2))
    assert (owned.ownership, conflict.ownership) == (Own.OWNED, Own.CONFLICT)
    report = transfer.cleanup()
    assert report.deleted_paths == (remote(0),)
    assert [c[1] for c in deletes(server)] == [remote(0)]
    assert dict(report.skipped_paths) == {remote(1): Code.REMOTE_EXISTS,
                                          RUN_DIR: Code.NOT_OWNED}
    assert report.failed_paths == () and report.cleanup_required
    assert report.error_code is Code.REMOTE_EXISTS
    assert bytes(server.files[remote(1)]) == FOREIGN and RUN_DIR in server.dirs


def test_232_non_empty_run_dir_listing_blocks_delete(server, tmp_path):
    transfer = make(server)
    transfer.prepare()
    transfer.upload(0, audio(tmp_path))
    server.files[f"{RUN_DIR}/unrelated.txt"] = bytearray(b"not ours")
    report = transfer.cleanup()
    assert report.deleted_paths == (remote(0),)
    assert (RUN_DIR, Code.REMOTE_EXISTS) in report.skipped_paths
    assert deletes(server, RUN_DIR) == [] and RUN_DIR in server.dirs
    assert bytes(server.files[f"{RUN_DIR}/unrelated.txt"]) == b"not ours"


@pytest.mark.parametrize("listing", ["timeout", (500, None), (200, {"type": "directory"})])
def test_232_unverifiable_run_dir_listing_blocks_delete(server, tmp_path, listing):
    transfer = make(server)

    def hook(method, path, body, n):
        if method == "GET" and path == RUN_DIR and transfer._closed:
            if listing == "timeout":
                raise timeout_error()
            return listing
    server.hooks.append(hook)
    transfer.prepare()
    report = transfer.cleanup()
    assert deletes(server, RUN_DIR) == [] and not report.run_dir_deleted
    assert report.cleanup_required and report.skipped_paths[0][0] == RUN_DIR


def test_232_retry_and_duplicate_bypass_blocked_after_conflict(server, tmp_path):
    foreign_wins_race(server, remote(0))
    transfer = make(server)
    transfer.prepare()
    source = audio(tmp_path)
    transfer.upload(0, source)
    puts = len(server.puts())
    for index, path in ((0, source), (0, audio(tmp_path, name="chunk-00007.mp3")),
                        (1, source)):
        with pytest.raises(TransferError) as exc:
            transfer.upload(index, path)
        assert exc.value.code is Code.DUPLICATE_UPLOAD
    assert len(server.puts()) == puts
    assert transfer.reconcile(0).ownership is Own.CONFLICT
    assert transfer._delete_owned(remote(0)) is Code.NOT_OWNED
    assert transfer._delete_owned(RUN_DIR) is Code.NOT_OWNED
    assert deletes(server) == []
