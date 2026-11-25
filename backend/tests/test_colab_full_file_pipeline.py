"""Full real-controller/transfer/worker/cache/merge flow; no external sockets."""

import ast
import json
import logging
import socket
import sys
from email.message import Message
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from src.domain.transcription import CancellationToken, CancelRequested, StopRequested
from src.engines.colab import AudioChunk, CHUNK_SECONDS, ColabRecoveryCache
from src.services.colab_account_verifier import GOOGLE_USERINFO_ENDPOINT, GoogleAccountVerifier
from src.services.colab_full_file_pipeline import ColabFullFilePipeline, PipelineError
from src.services.colab_inference_worker import MODEL_REVISION
from src.services.colab_jupyter_client import JupyterClientError, JupyterCode
from src.services.colab_runtime_client import ColabRuntimeClient
from src.services.colab_runtime_ownership import OwnershipStore, RuntimeOwnership
from test_colab_jupyter_files import FakeContents, TOKEN, URL
from test_colab_jupyter_inference import Server, ml
from test_colab_runtime_client import OAUTH, Server as RuntimeServer


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("PHASE 10 external socket forbidden")
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", denied)


class UserInfo:
    def __init__(self):
        self.subject = "account-a"
        self.calls = 0

    def open(self, request, timeout):
        assert request.full_url == GOOGLE_USERINFO_ENDPOINT
        assert request.get_header("Authorization") == "Bearer " + OAUTH
        self.calls += 1
        owner = self
        class Response:
            status = 200
            headers = Message()
            headers["Content-Type"] = "application/json"
            def geturl(self):
                return GOOGLE_USERINFO_ENDPOINT
            def read(self, limit):
                return json.dumps({"sub": owner.subject}).encode()
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
        return Response()


class Splitter:
    def __init__(self, root, durations):
        self.root, self.durations = root, durations
        self.calls, self.cleaned = [], False
        self.bad_plan = False

    def split(self, source, seconds, token):
        assert seconds == CHUNK_SECONDS == 300
        self.calls.append(source)
        self.root.mkdir(parents=True)
        chunks = []
        for index, duration in enumerate(self.durations):
            token.raise_if_requested()
            path = self.root / f"chunk-{index:05d}.mp3"
            path.write_bytes((f"synthetic MP3 {index} ".encode()) * 80)
            chunks.append(AudioChunk(index, path, index * 300.0, duration))
        if self.bad_plan:
            chunks[-1] = AudioChunk(0, chunks[-1].path, 0.0, chunks[-1].duration_seconds)
        return chunks

    def cleanup(self):
        self.cleaned = True
        if self.root.exists():
            for path in self.root.iterdir():
                path.unlink()
            self.root.rmdir()


class SharedWire:
    def __init__(self, server, model):
        self.server, self.model = server, model
        self.namespace, self.sent, self.frames = {}, [], []
        self.index = None
        self.closed = False

    def send(self, raw):
        message = json.loads(raw)
        self.sent.append(message)
        params = ast.literal_eval(ast.parse(message["content"]["code"]).body[-1].value.args[0])
        self.index = params.get("index")
        if self.index is not None:
            self.model.rows = ([] if self.index in self.server.silent else [
                SimpleNamespace(start=0.2, end=1.2, text=f"한국어 조각 {self.index}")])
            self.model.decode_fail = self.index == self.server.fail_decode
        exec(message["content"]["code"], self.namespace)
        receipt = self.namespace["_sorigul_receipt"]
        for kind, channel, content in (
            ("execute_reply", "shell", {"status": "ok", "user_expressions": {
                "receipt": {"status": "ok", "data": {"text/plain": repr(json.dumps(receipt))}}}}),
            ("status", "iopub", {"execution_state": "idle"}),
        ):
            self.frames.append(json.dumps({"header": {"msg_type": kind},
                "parent_header": {"msg_id": message["header"]["msg_id"]},
                "channel": channel, "content": content}))
        if self.server.after_send:
            self.server.after_send(self.index)

    def recv(self, timeout):
        if self.index is not None and self.index == self.server.lose_decode:
            raise OSError(TOKEN + "한국어 전사 내용")
        if not self.frames:
            raise TimeoutError()
        return self.frames.pop(0)

    def close(self):
        self.closed = True


class FullServer(Server):
    def __init__(self, model):
        super().__init__()
        self.contents = FakeContents()
        self.ws = SharedWire(self, model)
        self.silent = set()
        self.fail_decode = self.lose_decode = None
        self.after_send = self.after_http = None
        self.upload_failure = self.upload_foreign = None

    def http(self, method, url, headers, body, timeout):
        suffix = url[len(URL):]
        if not suffix.startswith("/api/contents/"):
            return super().http(method, url, headers, body, timeout)
        name, _, query = suffix[len("/api/contents/"):].partition("?")
        path = Path(name)
        if "/inference-" in name:
            response = super().http(method, url, headers, body, timeout)
        else:
            self.calls.append((method, suffix))
            if method == "PUT" and body.get("type") == "file":
                index = int(path.stem.split("-")[1])
                if index == self.upload_failure:
                    return 403, None
                if index == self.upload_foreign:
                    self.contents.files[name] = bytearray(b"foreign")
                    path.write_bytes(b"foreign")
                    return 200, {"path": name, "type": "file", "size": 7}
            if method == "GET" and path.is_dir():
                response = (200, {"path": name, "type": "directory", "content": [
                    {"path": p.as_posix(), "type": "directory" if p.is_dir() else "file"}
                    for p in path.iterdir()]})
            else:
                response = self.contents.http(method, url, headers, body, timeout)
            if method == "PUT" and response[0] in (200, 201):
                if body["type"] == "directory":
                    path.mkdir(exist_ok=True)
                else:
                    path.write_bytes(bytes(self.contents.files[name]))
            elif method == "DELETE" and response[0] in (204, 404) and path.exists():
                if path.is_dir():
                    path.rmdir()
                else:
                    path.unlink()
        if self.after_http:
            self.after_http(method, name, body)
        return response


@pytest.fixture
def setup(tmp_path, monkeypatch, ml):
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "강의.mp3"
    source.write_bytes(b"synthetic full MP3" * 100)
    outputs = {}
    for suffix in (".txt", ".json", ".srt"):
        path = source.with_suffix(suffix)
        path.write_bytes(b"preserve existing output")
        outputs[path] = path.read_bytes()
    original_download = sys.modules["huggingface_hub"].snapshot_download
    cache_dir = tmp_path / "model-cache" / MODEL_REVISION
    cache_dir.mkdir(parents=True)
    for name in ("model.bin", "config.json", "tokenizer.json", "preprocessor_config.json"):
        (cache_dir / name).write_bytes(b"fake model file")
    def cached_model(*args, **kwargs):
        original_download(*args, **kwargs)
        return str(cache_dir)
    monkeypatch.setattr(sys.modules["huggingface_hub"], "snapshot_download", cached_model)
    userinfo = UserInfo()
    runtime_server = RuntimeServer()
    original_runtime = runtime_server.runtime
    def runtime_payload():
        payload = original_runtime()
        payload["connectionInfo"]["url"] = URL
        return payload
    runtime_server.runtime = runtime_payload
    client = ColabRuntimeClient(OAUTH, transport=httpx.MockTransport(runtime_server.handle),
                                account_verifier=GoogleAccountVerifier(opener=userinfo),
                                sleep=lambda _: None)
    owner = RuntimeOwnership(OwnershipStore(tmp_path / "ownership"), client)
    owner.create()  # Mock only, explicit fixture setup; pipeline never creates a Runtime
    server = FullServer(ml)
    cache = ColabRecoveryCache(tmp_path / "recovery")
    splitters, pipelines = [], []
    def pipeline(durations=(300.0, 12.0)):
        splitter = Splitter(tmp_path / f"split-{len(splitters)}", durations)
        splitters.append(splitter)
        instance = ColabFullFilePipeline(owner, cache, splitter=splitter,
                                         http_request=server.http, ws_connect=server.connect)
        pipelines.append(instance)
        return instance
    yield SimpleNamespace(source=source, outputs=outputs, pipeline=pipeline, server=server,
                          owner=owner, runtime=runtime_server, userinfo=userinfo, ml=ml,
                          cache=cache, model_cache=cache_dir, splitters=splitters)
    owner.close()
    client.close()


def run(setup, pipeline=None, token=None, progress=None):
    return (pipeline or setup.pipeline()).transcribe(setup.source, token or CancellationToken(),
                                                    lambda *args: None, progress or (lambda _: None))


def workers(setup):
    return [m for m in setup.server.ws.sent if "_sorigul_receipt = _sorigul_worker(" in m["content"]["code"]]


@pytest.mark.parametrize("durations", [(12.0,), (300.0, 12.0), (300.0, 300.0, 12.0)])
def test_full_file_real_mock_flow_single_kernel_merge_and_model_reuse(setup, durations):
    pipeline = setup.pipeline(durations)
    progress = []
    result = run(setup, pipeline, progress=progress.append)
    assert result.language == "ko"
    assert result.text == "\n".join(f"한국어 조각 {i}" for i in range(len(durations)))
    assert [s.start for s in result.segments] == [i * 300 + 0.2 for i in range(len(durations))]
    assert len(setup.ml.loads) == 1 and len(setup.ml.decodes) == len(durations)
    assert setup.server.calls.count(("POST", "/api/kernels")) == 1
    assert setup.server.calls.count(("DELETE", "/api/kernels/owned-kernel")) == 1
    assert len({m["header"]["msg_id"] for m in setup.server.ws.sent}) == len(durations) + 1
    ids = [ast.literal_eval(ast.parse(m["content"]["code"]).body[-1].value.args[0])["execution_id"] for m in workers(setup)]
    assert len(set(ids)) == len(durations)
    assert pipeline.last_report.status == "COMPLETED" and not pipeline.last_report.cleanup.cleanup_required
    assert progress == [i / len(durations) for i in range(len(durations))] + [1.0]
    assert setup.splitters[0].cleaned and not setup.cache._file_dir(setup.source).exists()
    assert all(request.method != "DELETE" for request in setup.runtime.calls)
    assert setup.userinfo.calls > len(durations) and pipeline.last_report.runtime_borrowed


def test_silent_chunk_is_complete_not_missing(setup):
    setup.server.silent = {0}
    result = run(setup)
    assert result.text == "한국어 조각 1" and result.segments[0].start == 300.2
    assert len(setup.ml.decodes) == 2


@pytest.mark.parametrize("failure", ["upload", "decode"])
def test_chunk_failure_keeps_only_verified_cache_no_full_completion(setup, failure):
    if failure == "upload":
        setup.server.upload_failure = 1
    else:
        setup.server.fail_decode = 1
    pipeline, progress = setup.pipeline(), []
    with pytest.raises(PipelineError):
        run(setup, pipeline, progress=progress.append)
    assert pipeline.last_report.status == "FAILED"
    assert pipeline.last_report.completed_indices == (0,)
    assert 1.0 not in progress
    assert setup.cache._file_dir(setup.source).joinpath("manifest.json").exists()
    assert len(workers(setup)) == (1 if failure == "upload" else 2)


def test_failed_cache_reused_with_matching_signature_only(setup):
    setup.server.upload_failure = 1
    with pytest.raises(PipelineError):
        run(setup)
    setup.server.upload_failure = None
    setup.server.ws.namespace = {}  # next file run's new kernel
    second = setup.pipeline()
    result = run(setup, second)
    assert second.last_report.cache_used and result.metadata["colab_recovery_cache_used"]
    assert result.text == "한국어 조각 0\n한국어 조각 1"
    assert len(setup.ml.decodes) == 2  # chunk 0 once + failed-upload chunk 1 once


@pytest.mark.parametrize("change", ["source", "fingerprint", "timestamp", "duplicate-key"])
def test_invalid_failed_cache_not_reused(setup, change):
    setup.server.upload_failure = 1
    with pytest.raises(PipelineError):
        run(setup)
    manifest = setup.cache._file_dir(setup.source) / "manifest.json"
    value = json.loads(manifest.read_text(encoding="utf-8"))
    if change == "source":
        before = setup.source.stat()
        setup.source.write_bytes(b"x" * before.st_size)
        import os
        os.utime(setup.source, ns=(before.st_atime_ns, before.st_mtime_ns))
    elif change == "fingerprint":
        value["fingerprint"]["engine_signature"] = "foreign revision"
        manifest.write_text(json.dumps(value), encoding="utf-8")
    elif change == "timestamp":
        value["completed"]["0"]["segments"][0]["end"] = 301
        manifest.write_text(json.dumps(value), encoding="utf-8")
    else:
        raw = manifest.read_text(encoding="utf-8")
        manifest.write_text(raw.replace('"completed": {', '"completed": {}, "completed": {'), encoding="utf-8")
    setup.server.upload_failure = None
    setup.server.ws.namespace = {}
    second = setup.pipeline()
    run(setup, second)
    assert not second.last_report.cache_used
    assert len(setup.ml.decodes) == 3


@pytest.mark.parametrize("cancel", [False, True])
def test_stop_cancel_clear_cache_and_start_no_additional_put_or_decode(setup, cancel):
    token = CancellationToken()
    def progress(value):
        if value > 0:
            (token.request_cancel if cancel else token.request_stop)()
    pipeline = setup.pipeline()
    with pytest.raises(CancelRequested if cancel else StopRequested):
        run(setup, pipeline, token, progress)
    assert pipeline.last_report.status == ("CANCELLED" if cancel else "STOPPED")
    assert pipeline.last_report.completed_indices == (0,)
    assert len(workers(setup)) == 1
    assert not setup.cache._file_dir(setup.source).exists()
    file_puts = [p for m, p in setup.server.calls if m == "PUT" and p.endswith(".mp3")]
    assert len(file_puts) == 1
    setup.server.ws.namespace = {}
    second = setup.pipeline()
    run(setup, second)
    assert not second.last_report.cache_used and len(setup.ml.decodes) == 3


def test_cancel_during_uploaded_chunk_prevents_inference(setup):
    token = CancellationToken()
    def cancel(method, name, body):
        if method == "PUT" and name.endswith(".mp3"):
            token.request_cancel()
    setup.server.after_http = cancel
    with pytest.raises(CancelRequested):
        run(setup, token=token)
    assert workers(setup) == []
    assert len([p for m, p in setup.server.calls if m == "PUT" and p.endswith(".mp3")]) == 1


def test_cancel_during_inference_preserves_uncertain_cleanup_report(setup):
    token = CancellationToken()
    setup.server.after_send = lambda index: token.request_cancel() if index == 0 else None
    pipeline = setup.pipeline()
    with pytest.raises(PipelineError) as exc:
        run(setup, pipeline, token)
    assert exc.value.code == "CLEANUP_REQUIRED"
    assert pipeline.last_report.status == "CANCELLED"
    assert pipeline.last_report.cleanup.inference.cleanup_required
    assert len(workers(setup)) == 1 and not setup.cache._file_dir(setup.source).exists()


def test_first_put_conflict_never_executes_or_deletes_foreign_input(setup):
    setup.server.upload_foreign = 0
    pipeline = setup.pipeline()
    with pytest.raises(PipelineError):
        run(setup, pipeline)
    assert workers(setup) == []
    assert pipeline.last_report.cleanup.uploads.cleanup_required
    assert pipeline.last_report.cleanup.uploads.skipped_paths
    assert not any(m == "DELETE" and p.endswith(".mp3") for m, p in setup.server.calls)


def test_uncertain_decode_never_restarts_or_advances(setup):
    setup.server.lose_decode = 0
    pipeline = setup.pipeline()
    with pytest.raises(PipelineError):
        run(setup, pipeline)
    assert "REMOTE_STATE_UNCERTAIN" in pipeline.last_report.signals
    assert len(workers(setup)) == len(setup.ml.decodes) == 1
    assert pipeline.last_report.completed_indices == ()


@pytest.mark.parametrize("fault", ["kernel", "files"])
def test_cleanup_failure_is_not_normal_completion_and_has_separate_reports(setup, fault):
    if fault == "kernel":
        setup.server.delete_status = 500
    else:
        setup.server.file_delete_status = 500
    pipeline, progress = setup.pipeline(), []
    with pytest.raises(PipelineError) as exc:
        run(setup, pipeline, progress=progress.append)
    assert exc.value.code == "CLEANUP_REQUIRED" and pipeline.last_report.status == "FAILED"
    assert pipeline.last_report.cleanup.inference.cleanup_required
    assert 1.0 not in progress
    if fault == "kernel":
        assert pipeline.last_report.cleanup.inference.kernel.cleanup_required
        assert not pipeline.last_report.cleanup.uploads.cleanup_required
    else:
        assert pipeline.last_report.cleanup.inference.error_code is not None


@pytest.mark.parametrize("fault", ["package", "cache", "revision", "cpu"])
def test_preparation_is_read_only_and_blocks_before_upload_decode(setup, monkeypatch, fault):
    if fault == "package":
        import importlib.metadata
        monkeypatch.setattr(importlib.metadata, "version", lambda p: "wrong")
    elif fault == "cache":
        (setup.model_cache / "model.bin").unlink()
    elif fault == "revision":
        import sys
        monkeypatch.setattr(sys.modules["huggingface_hub"], "snapshot_download", lambda *a, **k: str(setup.model_cache.parent))
    else:
        setup.ml.cuda = 0
    pipeline = setup.pipeline()
    if fault == "cpu":
        run(setup, pipeline)
        assert "GPU_CPU_PATH" in pipeline.last_report.signals
        assert setup.ml.loads[0][1]["compute_type"] == "int8"
    else:
        with pytest.raises(PipelineError):
            run(setup, pipeline)
        assert "MODEL_PREPARATION_REQUIRED" in pipeline.last_report.signals
        assert workers(setup) == [] and setup.ml.decodes == []
        assert not any(m == "PUT" for m, p in setup.server.calls)
    assert all(kwargs["local_files_only"] is True for _, kwargs in setup.ml.downloads)


def test_account_change_during_file_blocks_next_upload(setup):
    def progress(value):
        if value > 0:
            setup.userinfo.subject = "different-account"
    pipeline = setup.pipeline()
    with pytest.raises(PipelineError):
        run(setup, pipeline, progress=progress)
    assert "AUTH_ACCESS_REQUIRED" in pipeline.last_report.signals
    assert len(workers(setup)) == 1


def test_bad_chunk_plan_rejected_before_remote_commands(setup):
    pipeline = setup.pipeline()
    pipeline.splitter.bad_plan = True
    with pytest.raises(PipelineError) as exc:
        run(setup, pipeline)
    assert exc.value.code == "CHUNK_PLAN_INVALID" and setup.server.ws.sent == []


def test_original_and_existing_outputs_preserved_and_no_sensitive_logs(setup, caplog, capsys):
    original = setup.source.read_bytes(), setup.source.stat().st_mtime_ns
    caplog.set_level(logging.DEBUG)
    pipeline = setup.pipeline()
    run(setup, pipeline)
    assert (setup.source.read_bytes(), setup.source.stat().st_mtime_ns) == original
    for path, data in setup.outputs.items():
        assert path.read_bytes() == data
    captured = capsys.readouterr()
    for text in (caplog.text, captured.out, captured.err, repr(pipeline.last_report)):
        assert TOKEN not in text and OAUTH not in text and "한국어 조각" not in text


def test_retry_before_put_only_once_and_never_retries_policy(setup):
    original = setup.server.http
    failures = []
    def timeout(method, url, headers, body, deadline):
        if method == "GET" and url.endswith("chunk-00000.mp3?content=0") and not failures:
            failures.append(True)
            raise JupyterClientError(JupyterCode.NETWORK_TIMEOUT)
        return original(method, url, headers, body, deadline)
    pipeline = setup.pipeline((12.0,))
    pipeline._http = timeout
    run(setup, pipeline)
    assert failures == [True] and len(workers(setup)) == 1


def test_file_execution_lease_blocks_competing_controller(setup):
    first, second = setup.pipeline(), setup.pipeline()
    blocked = []
    def progress(value):
        if value == 0.0:
            with pytest.raises(PipelineError) as exc:
                run(setup, second)
            blocked.append(exc.value.code)
    run(setup, first, progress=progress)
    assert blocked == ["FILE_EXECUTION_BUSY"]
    assert len(workers(setup)) == 2


def test_cancel_between_directory_get_and_put_starts_no_put(setup):
    token = CancellationToken()
    def cancel(method, name, body):
        if method == "GET" and name == "sorigul-transfer":
            token.request_cancel()
    setup.server.after_http = cancel
    pipeline = setup.pipeline()
    with pytest.raises(CancelRequested):
        run(setup, pipeline, token)
    assert pipeline.last_report.status == "CANCELLED"
    assert not any(m == "PUT" for m, _ in setup.server.calls)
    assert workers(setup) == []


def test_runtime_connection_switch_is_never_followed(setup):
    original = setup.runtime.runtime
    def progress(value):
        if value > 0:
            def foreign():
                payload = original()
                payload["connectionInfo"]["url"] = "https://foreign.invalid"
                return payload
            setup.runtime.runtime = foreign
    pipeline = setup.pipeline()
    with pytest.raises(PipelineError):
        run(setup, pipeline, progress=progress)
    assert "AUTH_ACCESS_REQUIRED" in pipeline.last_report.signals
    assert len(workers(setup)) == 1


@pytest.mark.parametrize("status,signal", [(401, "AUTH_ACCESS_REQUIRED"),
                                          (403, "AUTH_ACCESS_REQUIRED"),
                                          (429, "POLICY_USAGE_LIMIT")])
def test_kernel_access_errors_produce_upper_layer_signal_without_retry(setup, status, signal):
    original = setup.server.http
    def reject(method, url, headers, body, timeout):
        if method == "POST" and url.endswith("/api/kernels"):
            setup.server.calls.append((method, "/api/kernels"))
            return status, None
        return original(method, url, headers, body, timeout)
    pipeline = setup.pipeline()
    pipeline._http = reject
    with pytest.raises(PipelineError) as exc:
        run(setup, pipeline)
    assert signal in pipeline.last_report.signals
    assert exc.value.local_fallback_allowed
    assert setup.server.calls.count(("POST", "/api/kernels")) == 1
    assert workers(setup) == []


def test_upload_policy_is_not_retried(setup):
    setup.server.upload_failure = 0
    pipeline = setup.pipeline()
    with pytest.raises(PipelineError):
        run(setup, pipeline)
    assert "POLICY_USAGE_LIMIT" in pipeline.last_report.signals
    assert len([p for m, p in setup.server.calls if m == "PUT" and p.endswith(".mp3")]) == 1


def test_network_failure_before_put_is_retried_at_most_once(setup):
    original = setup.server.http
    attempts = []
    def timeout(method, url, headers, body, deadline):
        if method == "GET" and url.endswith("chunk-00000.mp3?content=0"):
            attempts.append(True)
            raise JupyterClientError(JupyterCode.NETWORK_TIMEOUT)
        return original(method, url, headers, body, deadline)
    pipeline = setup.pipeline()
    pipeline._http = timeout
    with pytest.raises(PipelineError):
        run(setup, pipeline)
    assert attempts == [True, True] and workers(setup) == []
    assert "NETWORK_ERROR" in pipeline.last_report.signals


def test_original_mutation_during_execution_refuses_merge_and_cache(setup):
    def progress(value):
        if value > 0:
            setup.source.write_bytes(b"changed source")
    pipeline = setup.pipeline()
    with pytest.raises(PipelineError):
        run(setup, pipeline, progress=progress)
    assert pipeline.last_report.status == "FAILED"
    assert not setup.cache._file_dir(setup.source).exists()


def test_missing_runtime_lease_blocks_all_remote_work(setup):
    setup.owner.close()
    pipeline = setup.pipeline()
    with pytest.raises(PipelineError):
        run(setup, pipeline)
    assert setup.server.calls == [] and setup.server.ws.sent == []


def test_source_lease_released_after_failure_allows_explicit_retry(setup):
    setup.server.upload_failure = 0
    with pytest.raises(PipelineError):
        run(setup)
    setup.server.upload_failure = None
    setup.server.ws.namespace = {}
    run(setup)


def test_malformed_result_prevents_advancing_and_caching(setup):
    setup.server.mutate = lambda raw: raw.replace(b'"complete": true', b'"complete": false')
    pipeline = setup.pipeline()
    with pytest.raises(PipelineError):
        run(setup, pipeline)
    assert pipeline.last_report.completed_indices == () and len(workers(setup)) == 1
    assert not setup.cache._file_dir(setup.source).exists()


def test_unresolved_previous_attempt_blocks_even_new_controller(setup):
    setup.server.lose_decode = 0
    with pytest.raises(PipelineError):
        run(setup)
    before = len(setup.server.calls), len(workers(setup))
    setup.server.lose_decode = None
    second = setup.pipeline()
    with pytest.raises(PipelineError) as exc:
        run(setup, second)
    assert exc.value.code == "PRIOR_EXECUTION_UNRESOLVED"
    assert (len(setup.server.calls), len(workers(setup))) == before
    assert not second.last_report.local_selection_possible


def test_pending_checkpoint_blocks_crash_reexecution_without_runtime_record_changes(setup):
    run(setup)
    marker = next((setup.cache.root / ".pipeline-locks").glob("*/attempt.json"))
    value = json.loads(marker.read_text())
    value["status"] = "ACTIVE"
    marker.write_text(json.dumps(value))
    before = len(setup.server.calls)
    with pytest.raises(PipelineError) as exc:
        run(setup)
    assert exc.value.code == "PRIOR_EXECUTION_UNRESOLVED"
    assert len(setup.server.calls) == before


def test_cleanup_failure_cannot_be_hidden_by_reusing_all_completed_cache(setup):
    setup.server.delete_status = 500
    with pytest.raises(PipelineError):
        run(setup)
    setup.server.delete_status = 204
    before = len(setup.server.calls)
    with pytest.raises(PipelineError) as exc:
        run(setup)
    assert exc.value.code == "PRIOR_EXECUTION_UNRESOLVED"
    assert len(setup.server.calls) == before


def test_hash_unsupported_still_checks_worker_content_for_every_chunk(setup):
    setup.server.contents.hash_supported = False
    result = run(setup)
    assert result.text == "한국어 조각 0\n한국어 조각 1" and len(setup.ml.decodes) == 2


def test_incomplete_first_put_model_remains_unowned_without_delete(setup):
    def incomplete(method, path, body, number):
        if method == "PUT" and path.endswith(".mp3"):
            import base64
            setup.server.contents.files[path] = bytearray(base64.b64decode(body["content"]))
            return 201, {}
    setup.server.contents.hooks.append(incomplete)
    pipeline = setup.pipeline()
    with pytest.raises(PipelineError):
        run(setup, pipeline)
    assert workers(setup) == []
    assert pipeline.last_report.cleanup.uploads.skipped_paths
    assert not any(m == "DELETE" and p.endswith(".mp3") for m, p in setup.server.calls)


def test_stale_previous_chunk_messages_do_not_complete_next_request(setup):
    def stale(index):
        if index == 1:
            setup.server.ws.frames.insert(0, json.dumps({
                "header": {"msg_type": "execute_reply"}, "parent_header": {"msg_id": "stale"},
                "channel": "shell", "content": {"status": "error", "traceback": [TOKEN]}}))
    setup.server.after_send = stale
    run(setup)
    sessions = {m["header"]["session"] for m in setup.server.ws.sent}
    assert len(sessions) == 1 and len(setup.ml.decodes) == 2


def test_free_resource_unavailable_signal_without_creation_or_paid_fallback(setup):
    from test_colab_runtime_client import error_response
    setup.runtime.overrides["GET", "/v1beta/subscription"] = error_response(503, reason="NO_AVAILABLE_RESOURCES")
    before = len([r for r in setup.runtime.calls if r.method == "POST"])
    pipeline = setup.pipeline()
    with pytest.raises(PipelineError):
        run(setup, pipeline)
    assert "FREE_RESOURCE_UNAVAILABLE" in pipeline.last_report.signals
    assert len([r for r in setup.runtime.calls if r.method == "POST"]) == before
    assert setup.server.ws.sent == []


def test_uploaded_chunk_must_match_hashed_split_plan_before_decode(setup):
    def mutate_after_plan(index):
        if index is None:  # readiness runs after plan hash, before the first upload
            path = setup.splitters[0].root / "chunk-00000.mp3"
            path.write_bytes(b"changed split bytes")
    setup.server.after_send = mutate_after_plan
    pipeline = setup.pipeline()
    with pytest.raises(PipelineError) as exc:
        run(setup, pipeline)
    assert exc.value.code == "CHUNK_CHANGED" and workers(setup) == []
    assert pipeline.last_report.completed_indices == ()


def test_input_upload_cleanup_failure_separate_from_successful_kernel_cleanup(setup):
    original = setup.server.http
    def refuse_delete(method, url, headers, body, timeout):
        if method == "DELETE" and url.endswith(".mp3"):
            return 500, None
        return original(method, url, headers, body, timeout)
    pipeline, progress = setup.pipeline(), []
    pipeline._http = refuse_delete
    with pytest.raises(PipelineError):
        run(setup, pipeline, progress=progress.append)
    assert pipeline.last_report.cleanup.uploads.cleanup_required
    assert not pipeline.last_report.cleanup.inference.cleanup_required
    assert pipeline.last_report.cleanup.uploads.failed_paths
    assert 1.0 not in progress


def test_splitter_cleanup_failure_is_reported_and_never_100_percent(setup):
    pipeline, progress = setup.pipeline(), []
    def fail():
        raise OSError("owned temporary cleanup failed")
    pipeline.splitter.cleanup = fail
    with pytest.raises(PipelineError):
        run(setup, pipeline, progress=progress.append)
    assert pipeline.last_report.cleanup.splitter_failed and 1.0 not in progress


def test_failed_silence_cache_is_reused_as_completed_chunk(setup):
    setup.server.silent = {0}
    setup.server.upload_failure = 1
    with pytest.raises(PipelineError):
        run(setup)
    setup.server.upload_failure = None
    setup.server.ws.namespace = {}
    pipeline = setup.pipeline()
    result = run(setup, pipeline)
    assert pipeline.last_report.cache_used and result.text == "한국어 조각 1"
    assert len(setup.ml.decodes) == 2


def test_checkpoint_publication_failure_keeps_crash_guard_pending(setup):
    pipeline = setup.pipeline()
    original = pipeline._checkpoint
    def fail_terminal(path, execution_id, status):
        if status != "ACTIVE":
            raise OSError("checkpoint unavailable")
        return original(path, execution_id, status)
    pipeline._checkpoint = fail_terminal
    with pytest.raises(PipelineError):
        run(setup, pipeline)
    assert pipeline.last_report.cleanup.checkpoint_failed
    with pytest.raises(PipelineError) as exc:
        run(setup)
    assert exc.value.code == "PRIOR_EXECUTION_UNRESOLVED"
