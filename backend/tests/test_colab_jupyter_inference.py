"""Socket-blocked PHASE 09 tests; actual trusted Worker with fake ML modules."""

import base64
import importlib.metadata
import json
import logging
import socket
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.services.colab_inference_worker import (
    MAX_RESULT_BYTES, MODEL_REVISION, PACKAGES, build_worker_code,
)
from src.services.colab_jupyter_client import VALIDATION_CODE
from src.services.colab_jupyter_files import IntegrityLevel, RemoteOwnership, TransferStatus
from src.services.colab_jupyter_inference import ColabJupyterInference, InferenceCode as Code, InferenceError
from src.services.colab_runtime_client import OwnedRuntime
from test_colab_jupyter_files import FakeContents, NOW, RUN, TOKEN, URL, audio, info, make, remote


@pytest.fixture(autouse=True)
def deny_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("External network forbidden in PHASE 09")
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


@pytest.fixture
def ml(monkeypatch):
    state = SimpleNamespace(cuda=1, load_fail=False, decode_fail=False, audio_fail=False,
        cublas=True, gpu_compute_fail=False, encodes=[], rows=[
        SimpleNamespace(start=0.2, end=1.2, text="가상 전사 내용")],
        loads=[], decodes=[], downloads=[], duration=2.0)

    class Model:
        def __init__(self, path, **kwargs):
            state.loads.append((path, kwargs))
            self.device = kwargs["device"]
            if state.load_fail is True or state.load_fail == self.device:
                raise RuntimeError(TOKEN + "가상 전사 내용")
            self.feature_extractor = SimpleNamespace(feature_size=128, nb_max_frames=3000)

            def encode(features, to_cpu):
                state.encodes.append((features.shape, to_cpu))
                if state.gpu_compute_fail:
                    raise RuntimeError("Library libcublas.so.12 is not found or cannot be loaded")
            self.model = SimpleNamespace(encode=encode)

        def transcribe(self, source, **kwargs):
            # Real libraries can emit progress or sensitive exception context.
            print(TOKEN + "가상 전사 내용")
            logging.getLogger("fake-model").error(TOKEN + "가상 전사 내용")
            state.decodes.append((source, kwargs))
            if state.decode_fail:
                def fail():
                    yield state.rows[0]
                    raise RuntimeError(TOKEN + "가상 전사 내용")
                return fail(), SimpleNamespace(duration=state.duration)
            return iter(state.rows), SimpleNamespace(duration=state.duration)

    def download(repository, **kwargs):
        state.downloads.append((repository, kwargs))
        return "fixed-model-cache"
    monkeypatch.setattr(importlib.metadata, "version", lambda p: PACKAGES[p])
    import numpy as np

    class Frame:  # PyAV-shaped stand-ins: s16 mono samples
        def __init__(self, samples):
            self.samples, self.pts = samples, 0

        def to_ndarray(self):
            return np.asarray([self.samples], dtype=np.int16)

    class Fifo:
        def __init__(self):
            self.buffer = []

        @property
        def samples(self):
            return len(self.buffer)

        def write(self, frame):
            self.buffer += frame.samples

        def read(self):
            frame, self.buffer = Frame(self.buffer), []
            return frame

    class Resampler:
        def __init__(self, format, layout, rate):
            assert (format, layout, rate) == ("s16", "mono", 16000)

        def resample(self, frame):
            return [] if frame is None else [frame]

    class Container:
        def __init__(self, handle, mode):
            assert mode == "r"
            if state.audio_fail:
                raise ValueError("Invalid data found when processing input " + TOKEN)
            self.data = handle.read()

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def decode(self, audio):
            yield Frame([int(b) * 64 for b in self.data[:256]])

    class InvalidDataError(Exception):
        pass

    av = SimpleNamespace(open=Container, error=SimpleNamespace(InvalidDataError=InvalidDataError),
                         audio=SimpleNamespace(resampler=SimpleNamespace(AudioResampler=Resampler),
                                               fifo=SimpleNamespace(AudioFifo=Fifo)))
    monkeypatch.setitem(sys.modules, "av", av)
    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=Model))
    monkeypatch.setitem(sys.modules, "ctranslate2", SimpleNamespace(
        get_cuda_device_count=lambda: state.cuda, StorageView=SimpleNamespace(from_array=lambda a: a)))
    import ctypes
    real_cdll = ctypes.CDLL

    def cdll(name, *args, **kwargs):
        # Stand-in for the pinned nvidia-cublas-cu12 wheel on a Colab runtime.
        if str(name).endswith("libcublas.so.12") and state.cublas:
            return SimpleNamespace()
        return real_cdll(name, *args, **kwargs)
    monkeypatch.setattr(ctypes, "CDLL", cdll)
    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(snapshot_download=download))
    return state


class Wire:
    def __init__(self, server):
        self.server = server
        self.sent, self.frames = [], []
        self.closed = False
        self.reply_status = "ok"
        self.order = ["reply", "idle"]
        self.lose = self.send_error = self.close_error = False
        self.receipt_override = None

    def send(self, raw):
        message = json.loads(raw)
        self.sent.append(message)
        if self.send_error:
            raise OSError(TOKEN + URL)
        namespace = {}
        exec(message["content"]["code"], namespace)
        receipt = self.receipt_override or namespace["_sorigul_receipt"]
        for kind in self.order:
            content = ({"status": self.reply_status,
                        "traceback": [TOKEN + "가상 전사 내용"],
                        "user_expressions": {"receipt": {"status": "ok", "data": {
                            "text/plain": repr(json.dumps(receipt))}}}}
                       if kind == "reply" else {"execution_state": "idle"})
            self.frames.append(json.dumps({
                "header": {"msg_type": "execute_reply" if kind == "reply" else "status"},
                "parent_header": {"msg_id": message["header"]["msg_id"]},
                "channel": "shell" if kind == "reply" else "iopub", "content": content}))

    def recv(self, timeout):
        assert 0 < timeout <= 0.5
        if self.server.on_recv:
            self.server.on_recv()
        if self.lose:
            raise OSError(TOKEN + URL + "가상 전사 내용")
        if not self.frames:
            raise TimeoutError()
        return self.frames.pop(0)

    def close(self):
        if self.close_error:
            raise OSError(TOKEN)
        self.closed = True


class Server:
    def __init__(self):
        self.calls = []
        self.ws = Wire(self)
        self.download_status, self.delete_status = 200, 204
        self.file_delete_status = 204
        self.create_error = self.ws_error = False
        self.mutate = self.on_recv = None
        self.hash_supported = True
        self.clock_value = 0

    def clock(self):
        self.clock_value += 0.1
        return self.clock_value

    def connect(self, url, headers, timeout):
        assert url.startswith("wss://runtime.example.invalid/prefix/api/kernels/owned-kernel/channels?")
        assert headers == {"X-Colab-Runtime-Proxy-Token": TOKEN}
        if self.ws_error:
            raise OSError(TOKEN)
        return self.ws

    def http(self, method, url, headers, body, timeout):
        assert url.startswith(URL + "/api/") and timeout > 0
        assert headers["X-Colab-Runtime-Proxy-Token"] == TOKEN
        assert "Authorization" not in headers
        suffix = url[len(URL):]
        self.calls.append((method, suffix))
        if suffix == "/api/kernels":
            assert method == "POST" and body == {"name": "python3"}
            if self.create_error:
                raise TimeoutError(TOKEN)
            return 201, {"id": "owned-kernel"}
        if suffix == "/api/kernels/owned-kernel":
            assert method == "DELETE"
            return self.delete_status, None
        assert suffix.startswith("/api/contents/")
        name, _, query = suffix[len("/api/contents/"):].partition("?")
        path = Path(name)
        if method == "DELETE":
            assert "/inference-" in name  # never input/run root/foreign file
            if self.file_delete_status != 204:
                return self.file_delete_status, None
            if not path.exists():
                return 404, None
            if path.is_dir():
                # Like Jupyter: a dir holding only the checkpoints dir is empty.
                if {p.name for p in path.iterdir()} <= {".ipynb_checkpoints"}:
                    import shutil
                    shutil.rmtree(path)
                else:
                    path.rmdir()
            else:
                path.unlink()
            return 204, None
        assert method == "GET"
        if not path.exists():
            return 404, None
        if path.is_dir():
            return 200, {"path": name, "type": "directory", "content": [
                {"name": p.name, "type": "directory" if p.is_dir() else "file"} for p in path.iterdir()]}
        if "content=1" in query:
            if self.download_status != 200:
                return self.download_status, None
            raw = path.read_bytes()
            if self.mutate:
                raw = self.mutate(raw)
            # Real Jupyter Server uses encodebytes: newline-wrapped every 76 chars.
            return 200, {"path": name, "type": "file", "format": "base64",
                         "content": base64.encodebytes(raw).decode("ascii")}
        if not self.hash_supported and "hash=1" in query:
            return 400, None
        import hashlib
        return 200, {"path": name, "type": "file", "size": path.stat().st_size,
                     **({"hash": hashlib.sha256(path.read_bytes()).hexdigest(), "hash_algorithm": "sha256"}
                        if self.hash_supported else {})}


@pytest.fixture
def setup(tmp_path, monkeypatch, ml):
    monkeypatch.chdir(tmp_path)
    contents = FakeContents()
    transfer = make(contents)
    transfer.prepare()
    source = audio(tmp_path)
    transfer.upload(0, source)
    target = Path(remote(0))
    target.parent.mkdir(parents=True)
    target.write_bytes(source.read_bytes())
    runtime = SimpleNamespace(get_owned_runtime=lambda: OwnedRuntime("runtimes/sorigul-" + RUN, info()))
    server = Server()
    def adapter(**kwargs):
        return ColabJupyterInference(runtime, transfer, http_request=server.http,
                                     ws_connect=server.connect, utcnow=lambda: NOW,
                                     clock=server.clock, execution_timeout=3, **kwargs)
    return SimpleNamespace(server=server, transfer=transfer, adapter=adapter, runtime=runtime, ml=ml)


@pytest.mark.parametrize("cuda,load_fail,device,gpu_error", [
    (1, False, "cuda", None), (0, False, "cpu", Code.GPU_UNAVAILABLE),
    (1, "cuda", "cpu", Code.CUDA_FAILED)])
def test_single_chunk_real_worker_fake_models(setup, cuda, load_fail, device, gpu_error):
    setup.ml.cuda, setup.ml.load_fail = cuda, load_fail
    adapter = setup.adapter()
    report = adapter.run(0)
    assert report.status == "OK" and report.error_code is None
    assert report.result.text == "가상 전사 내용" and report.result.language == "ko"
    assert report.result.segments[0].start == 0.2  # no original-audio offset
    assert report.execute_reply_received and report.iopub_idle_received
    assert report.device == device and report.gpu_error is gpu_error
    assert report.compute_type == ("float16" if device == "cuda" else "int8")
    assert setup.ml.decodes[0][1] == dict(language="ko", task="transcribe", temperature=0,
                                        beam_size=5, best_of=5, patience=1.0,
                                        condition_on_previous_text=False)
    assert setup.ml.downloads[0][0] == "Systran/faster-whisper-large-v3"
    assert setup.ml.downloads[0][1]["revision"] == MODEL_REVISION
    assert setup.ml.downloads[0][1]["local_files_only"] is True
    assert report.cleanup.kernel.kernel_deleted and report.cleanup.kernel.connection_closed
    assert report.cleanup.files_deleted and not report.cleanup.cleanup_required
    assert Path(remote(0)).exists()
    assert len(setup.server.ws.sent) == 1 and VALIDATION_CODE == "assert 1 + 1 == 2"
    assert "allow_stdin" in setup.server.ws.sent[0]["content"]
    with pytest.raises(InferenceError):
        adapter.run(0)


def test_idle_before_reply_and_silence(setup):
    setup.server.ws.order = ["idle", "reply"]
    setup.ml.rows = []
    report = setup.adapter().run(0)
    assert report.status == "OK" and report.silence
    assert report.result.text == "" and report.result.segments == []


@pytest.mark.parametrize("ownership,status", [
    (RemoteOwnership.UNCERTAIN, TransferStatus.VERIFIED),
    (RemoteOwnership.CONFLICT, TransferStatus.ACKNOWLEDGED),
    (RemoteOwnership.OWNED, TransferStatus.FAILED),
    (RemoteOwnership.OWNED, TransferStatus.STATE_UNCERTAIN)])
def test_unowned_or_incomplete_input_never_executes(setup, ownership, status):
    setup.transfer._records[0] = replace(setup.transfer.records()[0], ownership=ownership, status=status)
    report = setup.adapter().run(0)
    assert report.status == "NOT_RUN" and not report.execution_started
    assert setup.server.calls == [] and setup.ml.decodes == []
    assert setup.transfer.records()[0].ownership is ownership


@pytest.mark.parametrize("fault", ["hash", "size", "missing"])
def test_input_integrity_prevents_any_kernel_or_decode(setup, fault):
    path = Path(remote(0))
    if fault == "missing":
        path.unlink()
    else:
        path.write_bytes(b"x" * (path.stat().st_size + (fault == "size")))
    report = setup.adapter().run(0)
    assert report.error_code is (Code.INPUT_MISSING if fault == "missing" else Code.INPUT_INTEGRITY_MISMATCH)
    assert not report.execution_started and setup.ml.loads == []
    assert not any(m == "POST" for m, _ in setup.server.calls)


def test_hash_unsupported_worker_read_only_hash_blocks_changed_input(setup):
    setup.server.hash_supported = False
    Path(remote(0)).write_bytes(b"x" * 1000)
    report = setup.adapter().run(0)
    assert report.status == "ERROR" and report.error_code is Code.INPUT_INTEGRITY_MISMATCH
    assert setup.ml.loads == setup.ml.decodes == []
    assert setup.transfer.records()[0].ownership is RemoteOwnership.OWNED


def test_hash_unsupported_worker_can_verify_and_transcribe(setup):
    setup.server.hash_supported = False
    setup.transfer._records[0] = replace(setup.transfer.records()[0],
                                        status=TransferStatus.ACKNOWLEDGED,
                                        integrity=IntegrityLevel.SIZE_CONFIRMED)
    assert setup.adapter().run(0).status == "OK"
    assert setup.transfer.records()[0].status is TransferStatus.ACKNOWLEDGED


@pytest.mark.parametrize("fault,code", [("load", Code.MODEL_LOAD_FAILED),
                                      ("package", Code.MODEL_INSTALL_REQUIRED),
                                      ("decode", Code.CUDA_FAILED)])
def test_model_and_cuda_failure_no_decode_retry(setup, monkeypatch, fault, code):
    if fault == "load":
        setup.ml.load_fail = True
    elif fault == "package":
        monkeypatch.setattr(importlib.metadata, "version", lambda p: "wrong")
    else:
        setup.ml.decode_fail = True
    report = setup.adapter().run(0)
    assert report.status == "ERROR" and report.error_code is code
    assert report.local_fallback_possible and report.result is None
    assert len(setup.ml.decodes) <= 1
    assert not report.cleanup.cleanup_required


@pytest.mark.parametrize("fault", ["lost", "timeout", "send", "reply-error", "missing-idle"])
def test_execution_failure_never_restarts_even_with_new_adapter(setup, fault):
    wire = setup.server.ws
    if fault == "lost":
        wire.lose = True
    elif fault == "send":
        wire.send_error = True
    elif fault == "reply-error":
        wire.reply_status = "error"
    elif fault == "missing-idle":
        wire.order = ["reply"]
    else:
        wire.order = []
    report = setup.adapter().run(0)
    assert report.status == ("ERROR" if fault == "reply-error" else "STATE_UNCERTAIN")
    assert report.result is None and report.cleanup.cleanup_required
    if fault in ("timeout", "missing-idle"):
        assert report.error_code is Code.EXECUTION_TIMEOUT
    second = setup.adapter().run(0)
    assert second.error_code is Code.DUPLICATE_EXECUTION
    assert len(wire.sent) == 1
    assert not any(m == "DELETE" and "/contents/" in p for m, p in setup.server.calls)


def test_kernel_create_loss_does_not_list_or_delete_unknown_kernel(setup):
    setup.server.create_error = True
    report = setup.adapter().run(0)
    assert report.status == "STATE_UNCERTAIN" and not report.execution_started
    assert report.cleanup.kernel.cleanup_required
    assert setup.server.calls[-1] == ("POST", "/api/kernels")
    assert setup.server.ws.sent == []


def test_runtime_binding_mismatch_blocks_before_jupyter(setup):
    setup.runtime.get_owned_runtime = lambda: OwnedRuntime("foreign", info(url="https://other.invalid"))
    report = setup.adapter().run(0)
    assert report.error_code is Code.CONNECTION_FAILED
    assert setup.server.calls == []


@pytest.mark.parametrize("when", ["before", "during"])
def test_cancel_cleans_only_own_kernel_and_never_resends(setup, when):
    adapter = setup.adapter()
    if when == "before":
        adapter.cancel()
    else:
        setup.server.on_recv = adapter.cancel
    report = adapter.run(0)
    assert report.status == "CANCELLED" and report.error_code is Code.CANCELLED
    assert len(setup.server.ws.sent) == (when == "during")
    assert not report.local_fallback_possible


@pytest.mark.parametrize("fault", ["json", "duplicate", "missing", "timestamp", "nan", "bool-time",
                                   "empty", "incomplete", "path", "oversized", "language"])
def test_invalid_results_are_never_completed(setup, fault):
    def mutate(raw):
        if fault == "json":
            return b"{broken"
        if fault == "duplicate":
            return raw.replace(b'"complete": true', b'"complete": false, "complete": true')
        if fault == "oversized":
            return b"x" * (MAX_RESULT_BYTES + 1)
        value = json.loads(raw)
        if fault == "missing":
            del value["payload"]["segments"]
        elif fault in ("timestamp", "nan", "bool-time"):
            value["payload"]["segments"][0]["start"] = {"timestamp": -1, "nan": float("nan"), "bool-time": True}[fault]
        elif fault == "empty":
            value["payload"].update(text="", segments=[])
        elif fault == "incomplete":
            value["complete"] = False
        elif fault == "language":
            value["payload"]["language"] = None
        else:
            value["execution_id"] = "../foreign"
        return json.dumps(value).encode()
    setup.server.mutate = mutate
    report = setup.adapter().run(0)
    assert report.status == "ERROR" and report.error_code is Code.RESULT_INVALID
    assert report.result is None and not report.cleanup.cleanup_required


def test_download_failure_separate_from_execution(setup):
    setup.server.download_status = 502
    report = setup.adapter().run(0)
    assert report.error_code is Code.RESULT_DOWNLOAD_FAILED
    assert report.execute_reply_received and report.iopub_idle_received
    assert report.result is None and not report.cleanup.cleanup_required


@pytest.mark.parametrize("fault", ["kernel", "connection", "file"])
def test_cleanup_failure_preserves_success_and_explicit_retry(setup, fault):
    if fault == "kernel":
        setup.server.delete_status = 500
    elif fault == "connection":
        setup.server.ws.close_error = True
    else:
        setup.server.file_delete_status = 500
    adapter = setup.adapter()
    report = adapter.run(0)
    assert report.status == "OK" and report.error_code is None
    assert report.cleanup.cleanup_required
    setup.server.delete_status = setup.server.file_delete_status = 204
    setup.server.ws.close_error = False
    assert not adapter.cleanup().cleanup_required
    assert len(setup.server.ws.sent) == 1


@pytest.mark.parametrize("failure", [False, True])
def test_no_tokens_or_transcript_in_logs_or_report_repr(setup, caplog, capsys, failure):
    caplog.set_level(logging.DEBUG)
    setup.ml.decode_fail = failure
    report = setup.adapter().run(0)
    assert (report.result is None) is failure
    captured = capsys.readouterr()
    for value in (repr(report), caplog.text, captured.out, captured.err):
        assert TOKEN not in value and URL not in value and "가상 전사 내용" not in value
    assert caplog.records == []


@pytest.mark.parametrize("bad", ["../x", "a'\nprint('bad')", "https://other.invalid/x"])
def test_worker_builder_rejects_untrusted_path_or_code(bad):
    with pytest.raises(ValueError, match="INVALID_INPUT"):
        build_worker_code(run_id=bad, execution_id="a" * 32, index=0, size=1000, sha256="0" * 64)


def test_worker_model_is_reusable_in_same_kernel(setup):
    record = setup.transfer.records()[0]
    namespace = {}
    for execution in ("a" * 32, "b" * 32):
        exec(build_worker_code(run_id=RUN, execution_id=execution, index=0,
                               size=record.size, sha256=record.sha256), namespace)
    assert len(setup.ml.loads) == 1 and len(setup.ml.decodes) == 2


@pytest.mark.parametrize("fault", ["foreign", "numeric-owned", "extra-field"])
def test_unproven_output_receipt_never_allows_delete(setup, fault):
    adapter = setup.adapter()
    receipt = {"execution_id": adapter.execution_id, "owned": True}
    if fault == "foreign":
        receipt["execution_id"] = "someone-else"
    elif fault == "numeric-owned":
        receipt["owned"] = 1
    else:
        receipt["path"] = "../foreign"
    setup.server.ws.receipt_override = receipt
    report = adapter.run(0)
    assert report.status == "STATE_UNCERTAIN" and report.error_code is Code.STATE_UNCERTAIN
    assert report.cleanup.cleanup_required
    assert not any(m == "DELETE" and "/contents/" in p for m, p in setup.server.calls)


def test_worker_input_changed_after_preflight_is_hashed_before_decode(setup):
    real_connect = setup.server.connect
    def change(*args):
        Path(remote(0)).write_bytes(b"x" * 1000)
        return real_connect(*args)
    setup.server.connect = change
    report = setup.adapter().run(0)
    assert report.error_code is Code.INPUT_INTEGRITY_MISMATCH
    assert setup.ml.loads == setup.ml.decodes == []


def test_input_changed_while_decoding_never_returns_result(setup):
    original = setup.ml.rows[0]
    class MutatingRows:
        def __iter__(self):
            Path(remote(0)).write_bytes(b"x" * 1000)
            yield original
    setup.ml.rows = MutatingRows()
    report = setup.adapter().run(0)
    assert report.error_code is Code.INPUT_INTEGRITY_MISMATCH
    assert report.result is None and len(setup.ml.decodes) == 1


def test_foreign_file_blocks_output_directory_cleanup(setup):
    def add_file(raw):
        for path in Path("sorigul-transfer").glob("*/inference-*"):
            (path / "foreign.txt").write_text("preserve")
        return raw
    setup.server.mutate = add_file
    adapter = setup.adapter()
    report = adapter.run(0)
    assert report.status == "OK" and report.cleanup.error_code is Code.FILE_CLEANUP_FAILED
    assert report.cleanup.cleanup_required
    assert Path(adapter._output_dir, "foreign.txt").read_text() == "preserve"
    assert ("DELETE", "/api/contents/" + adapter._output_dir) not in setup.server.calls


def test_colab_checkpoints_dir_does_not_block_output_directory_cleanup(setup):
    # Live run 5: Colab lists the server-made hidden `.ipynb_checkpoints` dir.
    def add_checkpoints(raw):
        for path in Path("sorigul-transfer").glob("*/inference-*"):
            (path / ".ipynb_checkpoints").mkdir(exist_ok=True)
        return raw
    setup.server.mutate = add_checkpoints
    adapter = setup.adapter()
    report = adapter.run(0)
    assert report.status == "OK" and report.cleanup.files_deleted
    assert not report.cleanup.cleanup_required and not Path(adapter._output_dir).exists()


@pytest.mark.parametrize("content,empty", [
    ([], True), ([{"name": ".ipynb_checkpoints", "type": "directory"}], True),
    ([{"name": ".ipynb_checkpoints", "type": "file"}], False),
    ([{"name": "result.json", "type": "file"}], False),
    ([{"name": ".ipynb_checkpoints", "type": "directory"}, {"name": "x", "type": "file"}], False),
    ([".ipynb_checkpoints"], False), (None, False)])
def test_listing_is_empty_matches_jupyter_checkpoint_rule(content, empty):
    from src.services.colab_jupyter_files import listing_is_empty
    assert listing_is_empty(content) is empty


def test_connection_failure_before_send_is_not_uncertain_execution(setup):
    setup.server.ws_error = True
    report = setup.adapter().run(0)
    assert report.status == "NOT_RUN" and report.error_code is Code.CONNECTION_FAILED
    assert not report.execution_started and report.cleanup.kernel.kernel_deleted


@pytest.mark.parametrize("index", [True, -1, 100000, "../file"])
def test_invalid_index_never_contacts_jupyter(setup, index):
    report = setup.adapter().run(index)
    assert report.error_code is Code.INVALID_INPUT and setup.server.calls == []


def test_transfer_connection_binding_tolerates_token_reissue_not_retargeting(setup):
    # runtimes.get reissues the short-lived proxy token on reads (#60 live run).
    assert setup.transfer.matches_connection(info())
    assert setup.transfer.matches_connection(info(token="reissued"))
    assert not setup.transfer.matches_connection(info(url="https://other-runtime.example.com"))
    assert not setup.transfer.matches_connection(None)


@pytest.mark.parametrize("value", [0, -1, float("inf"), float("nan"), True, 3601])
def test_execution_timeout_must_be_bounded_and_finite(setup, value):
    with pytest.raises(ValueError):
        ColabJupyterInference(setup.runtime, setup.transfer, execution_timeout=value)


def test_result_reuses_existing_merge_contract(setup):
    from src.engines.colab import AudioChunk, DirectColabEngine, CHUNK_SECONDS
    result = setup.adapter().run(0).result
    assert CHUNK_SECONDS == 300
    chunk = AudioChunk(index=0, path=Path(remote(0)), start_seconds=300, duration_seconds=2)
    merged = DirectColabEngine._merge([chunk], {0: result})
    assert result.segments[0].start == 0.2
    assert merged.segments[0].start == 300.2
    assert merged.text == result.text


def test_explicit_model_download_still_uses_immutable_revision(setup):
    assert setup.adapter(allow_model_download=True).run(0).status == "OK"
    assert setup.ml.downloads[0][1]["local_files_only"] is False
    assert setup.ml.downloads[0][1]["revision"] == MODEL_REVISION


@pytest.mark.parametrize("fault,code,stage,exception", [
    ("decode", Code.CUDA_FAILED, "inference", "RuntimeError"),
    ("audio", Code.KERNEL_EXECUTION_FAILED, "audio_decode", "ValueError"),
    ("load", Code.MODEL_LOAD_FAILED, "model_init", "RuntimeError")])
def test_failure_diagnostic_names_stage_and_exception_without_secrets(setup, caplog, fault, code, stage, exception):
    setup.ml.decode_fail = fault == "decode"
    setup.ml.audio_fail = fault == "audio"
    setup.ml.load_fail = fault == "load"
    report = setup.adapter().run(0)
    assert report.status == "ERROR" and report.error_code is code
    diagnostic = report.diagnostic
    assert diagnostic["stage"] == stage and diagnostic["exception"] == exception
    assert isinstance(diagnostic["runtime"]["libs"], dict) and "libcublas.so.12" in diagnostic["runtime"]["libs"]
    text = json.dumps(diagnostic, ensure_ascii=False)
    assert TOKEN not in text and "가상 전사 내용" not in text and "<redacted>" in text


def test_success_carries_no_diagnostic(setup):
    report = setup.adapter().run(0)
    assert report.status == "OK" and report.diagnostic is None


@pytest.mark.parametrize("bad", [
    {"stage": "nope", "exception": None, "message": None, "runtime": None},
    {"stage": "inference", "exception": None, "message": None},
    {"stage": "inference", "exception": 3, "message": None, "runtime": None},
    {"stage": "inference", "exception": None, "message": None, "runtime": {"libs": {"x": True}}},
    {"stage": "inference", "exception": None, "message": None, "runtime": {"Bad-Key": 1}}])
def test_diagnostic_shape_is_bounded(bad):
    from src.services.colab_jupyter_inference import sanitize_diagnostic
    with pytest.raises(ValueError):
        sanitize_diagnostic(bad)
