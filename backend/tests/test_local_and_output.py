import hashlib
import io
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from src import local_runtime_main
from src.engines import local_whisper
from src.domain.transcription import (
    CancellationToken,
    CancelRequested,
    EngineError,
    StopRequested,
    TranscriptionResult,
)
from src.engines.local_whisper import (
    EXPECTED_CUDA,
    PROTOCOL_VERSION,
    RUNTIME_TYPE,
    RUNTIME_VERSION,
    TORCH_REQUIREMENT,
    LocalWhisperEngine,
    verify_runtime,
)
from src.services.output_bundle import BundlePaths, OutputBundleValidator, OutputBundleWriter


def quiet_event(*_args):
    pass


def quiet_progress(_progress):
    pass


@pytest.fixture
def runtime_dir(tmp_path):
    root = tmp_path / "runtime" / "local-whisper" / "v1"
    root.mkdir(parents=True)
    executable = root / "sorigul-local-whisper.exe"
    executable.write_bytes(b"fake-worker")
    digest = hashlib.sha256(executable.read_bytes()).hexdigest()
    manifest = {
        "runtime_type": RUNTIME_TYPE,
        "runtime_version": RUNTIME_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "torch_requirement": TORCH_REQUIREMENT,
        "expected_cuda": EXPECTED_CUDA,
        "worker_sha256": digest,
        "artifact_sha256": digest,
        "source_head": "a" * 40,
        "tracked_tree_clean": True,
    }
    (root / "runtime-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


class FakeProcess:
    def __init__(self, returncode=0, *, on_first_wait=None, always_timeout=False):
        self.returncode = returncode
        self.pid = 1234
        self.on_first_wait = on_first_wait
        self.always_timeout = always_timeout
        self.waits = 0
        self.terminated = False
        self.killed = False

    def wait(self, timeout):
        self.waits += 1
        if self.waits == 1 and self.on_first_wait is not None:
            self.on_first_wait()
        if self.always_timeout or (self.on_first_wait is not None and not self.terminated):
            raise subprocess.TimeoutExpired("worker", timeout)
        return self.returncode

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True


def success_popen(captured, *, mutate_outputs=None, response_mutator=None, process=None):
    def factory(command, **kwargs):
        request = json.loads(Path(command[2]).read_text(encoding="utf-8"))
        captured.append(request)
        output_dir = Path(request["output_dir"])
        source = Path(request["input_path"])
        result = TranscriptionResult.from_engine_payload(
            {
                "text": "안녕하세요",
                "segments": [{"start": 0, "end": 1.25, "text": "안녕하세요"}],
                "language": "ko",
            }
        )
        paths = OutputBundleWriter().commit(output_dir / source.name, result)
        if mutate_outputs is not None:
            mutate_outputs(paths)
        response = {
            "protocol_version": PROTOCOL_VERSION,
            "ok": True,
            "status": "DONE",
            "device": "cuda",
            "outputs": {key: str(value) for key, value in paths.as_dict().items()},
            "error": None,
        }
        if response_mutator is not None:
            response_mutator(response)
        kwargs["stdout"].write(json.dumps(response).encode("utf-8"))
        return process or FakeProcess()

    return factory


def reap_fake(process):
    process.terminate()
    process.wait(timeout=10)


def test_runtime_manifest_missing_invalid_version_and_hash_fail_closed(tmp_path, runtime_dir):
    with pytest.raises(EngineError) as missing:
        verify_runtime(tmp_path / "missing")
    assert missing.value.code == "LOCAL_RUNTIME_MISSING"

    manifest_path = runtime_dir / "runtime-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["protocol_version"] = 2
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(EngineError) as version:
        verify_runtime(runtime_dir)
    assert version.value.code == "LOCAL_RUNTIME_VERSION_MISMATCH"

    manifest["protocol_version"] = PROTOCOL_VERSION
    manifest["worker_sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(EngineError) as invalid:
        verify_runtime(runtime_dir)
    assert invalid.value.code == "LOCAL_RUNTIME_INVALID"


def test_local_worker_protocol_preserves_fixed_options_and_result(runtime_dir, tmp_path):
    captured = []
    source = tmp_path / "전사자료" / "개념완성_민법_8주차_4강.mp3"
    source.parent.mkdir()
    source.touch()
    engine = LocalWhisperEngine(runtime_dir, popen=success_popen(captured))

    result = engine.transcribe(source, CancellationToken(), quiet_event, quiet_progress)

    assert result.text == "안녕하세요"
    assert captured == [
        {
            "protocol_version": 1,
            "action": "transcribe",
            "input_path": str(source),
            "output_dir": captured[0]["output_dir"],
            "model": "medium",
            "options": LocalWhisperEngine.TRANSCRIBE_OPTIONS,
        }
    ]
    assert not Path(captured[0]["output_dir"]).exists(), "temporary worker outputs are cleaned"


def test_worker_failure_and_malformed_response_are_normalized(runtime_dir, tmp_path):
    source = tmp_path / "lecture.mp3"
    source.touch()

    def failed_popen(_command, **kwargs):
        kwargs["stderr"].write(b"diagnostic only")
        return FakeProcess(returncode=7)

    with pytest.raises(EngineError) as failed:
        LocalWhisperEngine(runtime_dir, popen=failed_popen).transcribe(
            source, CancellationToken(), quiet_event, quiet_progress
        )
    assert failed.value.code == "LOCAL_RUNTIME_ERROR"
    assert "diagnostic only" in failed.value.technical_detail

    def malformed_popen(_command, **kwargs):
        kwargs["stdout"].write(b"not-json")
        return FakeProcess()

    with pytest.raises(EngineError) as malformed:
        LocalWhisperEngine(runtime_dir, popen=malformed_popen).transcribe(
            source, CancellationToken(), quiet_event, quiet_progress
        )
    assert malformed.value.code == "LOCAL_RUNTIME_RESPONSE_INVALID"


def test_worker_timeout_reaps_child(runtime_dir, tmp_path):
    process = FakeProcess(always_timeout=False, on_first_wait=lambda: None)
    clocks = iter((0.0, 2.0))

    def popen(_command, **_kwargs):
        return process

    with pytest.raises(EngineError) as caught:
        LocalWhisperEngine(
            runtime_dir,
            popen=popen,
            timeout_seconds=1,
            clock=lambda: next(clocks),
            reap=reap_fake,
        ).transcribe(tmp_path / "lecture.mp3", CancellationToken(), quiet_event, quiet_progress)
    assert caught.value.code == "LOCAL_RUNTIME_TIMEOUT"
    assert process.terminated is True


def test_worker_cleanup_failure_is_explicit_and_fatal(monkeypatch):
    process = FakeProcess(always_timeout=True)
    monkeypatch.setattr(
        local_whisper.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=1),
    )

    with pytest.raises(EngineError) as caught:
        local_whisper._reap(process)

    assert caught.value.code == "LOCAL_RUNTIME_PROCESS_CLEANUP_FAILED"
    assert caught.value.fatal is True
    assert process.terminated is True
    assert process.killed is True


@pytest.mark.parametrize("cancel", [False, True], ids=["stop", "cancel"])
def test_worker_stop_cancel_reaps_child_before_acknowledgement(runtime_dir, tmp_path, cancel):
    token = CancellationToken()
    request = token.request_cancel if cancel else token.request_stop
    process = FakeProcess(on_first_wait=request)

    with pytest.raises(CancelRequested if cancel else StopRequested):
        LocalWhisperEngine(
            runtime_dir,
            popen=lambda *_args, **_kwargs: process,
            reap=reap_fake,
        ).transcribe(
            tmp_path / "lecture.mp3", token, quiet_event, quiet_progress
        )
    assert process.terminated is True


def test_worker_output_verification_rejects_missing_txt(runtime_dir, tmp_path):
    source = tmp_path / "lecture.mp3"
    source.touch()
    popen = success_popen([], mutate_outputs=lambda paths: paths.txt.unlink())
    with pytest.raises(EngineError) as caught:
        LocalWhisperEngine(runtime_dir, popen=popen).transcribe(
            source, CancellationToken(), quiet_event, quiet_progress
        )
    assert caught.value.code == "TXT_INVALID"


class FakeCuda:
    def __init__(self, available):
        self.available = available

    def is_available(self):
        return self.available


class FakeModel:
    def __init__(self, failure=None):
        self.failure = failure
        self.calls = []

    def transcribe(self, path, **options):
        self.calls.append((path, options))
        if self.failure is not None:
            failure = self.failure
            self.failure = None
            raise failure
        return {"text": "안녕하세요", "segments": []}


class FakeWhisper:
    def __init__(self, model, fail_cuda=False):
        self.model = model
        self.fail_cuda = fail_cuda
        self.loads = []

    def load_model(self, name, device):
        self.loads.append((name, device))
        if device == "cuda" and self.fail_cuda:
            raise RuntimeError("CUDA initialization failed")
        return self.model


def test_runtime_worker_keeps_cuda_cpu_and_fp16_fallbacks(tmp_path, monkeypatch):
    source = tmp_path / "lecture.mp3"
    source.touch()
    output = tmp_path / "output"
    output.mkdir()
    model = FakeModel(failure=RuntimeError("float16 operation failed"))
    whisper = FakeWhisper(model)
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(cuda=FakeCuda(True)))
    monkeypatch.setitem(sys.modules, "whisper", whisper)
    request = {
        "input_path": str(source),
        "output_dir": str(output),
        "options": dict(LocalWhisperEngine.TRANSCRIBE_OPTIONS),
    }

    response = local_runtime_main._transcribe(request)

    assert response["device"] == "cuda"
    assert whisper.loads == [("medium", "cuda")]
    assert [call[1]["fp16"] for call in model.calls] == [True, False]

    cpu_output = tmp_path / "cpu-output"
    cpu_output.mkdir()
    cpu_model = FakeModel()
    cpu_whisper = FakeWhisper(cpu_model, fail_cuda=True)
    monkeypatch.setitem(sys.modules, "whisper", cpu_whisper)
    request["output_dir"] = str(cpu_output)
    cpu_response = local_runtime_main._transcribe(request)
    assert cpu_response["device"] == "cpu"
    assert cpu_whisper.loads == [("medium", "cuda"), ("medium", "cpu")]
    assert cpu_model.calls[0][1]["fp16"] is False


def test_worker_failure_protocol_uses_stdout_without_traceback(monkeypatch):
    stdout = local_runtime_main.sys.stdout
    stderr = local_runtime_main.sys.stderr
    fake_stdout = io.StringIO()
    fake_stderr = io.StringIO()
    fake_stdin = io.StringIO("not-json")
    monkeypatch.setattr(local_runtime_main.sys, "stdout", fake_stdout)
    monkeypatch.setattr(local_runtime_main.sys, "stderr", fake_stderr)
    monkeypatch.setattr(local_runtime_main.sys, "stdin", fake_stdin)
    try:
        assert local_runtime_main.main([]) == 1
    finally:
        local_runtime_main.sys.stdout = stdout
        local_runtime_main.sys.stderr = stderr

    response = json.loads(fake_stdout.getvalue())
    assert response["status"] == "FAILED"
    assert response["error"]["code"] == "LOCAL_RUNTIME_ERROR"
    assert "Traceback" not in fake_stdout.getvalue()
    assert fake_stderr.getvalue() == ""


@pytest.fixture
def canonical_result():
    return TranscriptionResult.from_engine_payload(
        {
            "text": "첫 문장 둘째 문장",
            "segments": [
                {"start": 0, "end": 1.234, "text": "첫 문장"},
                {"start": 61.005, "end": 62, "text": "둘째 문장"},
            ],
        }
    )


def test_txt_json_srt_write_and_validation(tmp_path, canonical_result):
    source = tmp_path / "강의.mp3"
    source.touch()
    paths = OutputBundleWriter().commit(source, canonical_result)
    assert paths.txt.read_text(encoding="utf-8") == "첫 문장 둘째 문장"
    payload = json.loads(paths.json.read_text(encoding="utf-8"))
    assert payload["text"] == canonical_result.text
    assert len(payload["segments"]) == 2
    srt = paths.srt.read_text(encoding="utf-8")
    assert "00:00:00,000 --> 00:00:01,234" in srt
    assert "00:01:01,005 --> 00:01:02,000" in srt


def test_empty_srt_allowed(tmp_path):
    source = tmp_path / "silence.mp3"
    source.touch()
    paths = OutputBundleWriter().commit(source, TranscriptionResult(text="무음", segments=[]))
    assert paths.srt.exists()
    assert paths.srt.stat().st_size == 0


@pytest.mark.parametrize(
    "mutate,code",
    [
        (lambda paths: paths.txt.write_text("", encoding="utf-8"), "TXT_INVALID"),
        (lambda paths: paths.json.write_text("not-json", encoding="utf-8"), "JSON_INVALID"),
        (lambda paths: paths.json.write_text('{"text": "x"}', encoding="utf-8"), "JSON_SCHEMA_INVALID"),
        (lambda paths: paths.srt.unlink(), "SRT_MISSING"),
    ],
)
def test_output_validation_failures(tmp_path, canonical_result, mutate, code):
    source = tmp_path / "invalid.mp3"
    source.touch()
    paths = OutputBundleWriter().commit(source, canonical_result)
    mutate(paths)
    with pytest.raises(EngineError) as caught:
        OutputBundleValidator().validate(paths)
    assert caught.value.code == code


def _old_bundle(source):
    paths = BundlePaths.final_for(source)
    paths.txt.write_text("old text", encoding="utf-8")
    paths.json.write_text('{"text":"old text","segments":[]}', encoding="utf-8")
    paths.srt.write_text("", encoding="utf-8")
    return paths


def test_invalid_new_result_preserves_existing_bundle(tmp_path):
    source = tmp_path / "lecture.mp3"
    source.touch()
    old = _old_bundle(source)
    with pytest.raises(EngineError):
        OutputBundleWriter().commit(source, TranscriptionResult(text="", segments=[]))
    assert old.txt.read_text(encoding="utf-8") == "old text"
    assert json.loads(old.json.read_text(encoding="utf-8"))["text"] == "old text"


def test_invalid_new_json_preserves_existing_bundle(tmp_path, canonical_result):
    source = tmp_path / "lecture.mp3"
    source.touch()
    old = _old_bundle(source)

    class CorruptJsonWriter(OutputBundleWriter):
        def _write_staged(self, paths, result):
            super()._write_staged(paths, result)
            paths.json.write_text("not-json", encoding="utf-8")

    with pytest.raises(EngineError):
        CorruptJsonWriter().commit(source, canonical_result)
    OutputBundleValidator().validate(old)


def test_invalid_segment_is_rejected():
    with pytest.raises(ValueError):
        TranscriptionResult.from_engine_payload(
            {"text": "bad", "segments": [{"start": 2, "end": 1, "text": "bad"}]}
        )


def test_valid_new_result_replaces_existing_bundle(tmp_path, canonical_result):
    source = tmp_path / "lecture.mp3"
    source.touch()
    old = _old_bundle(source)
    OutputBundleWriter().commit(source, canonical_result)
    assert old.txt.read_text(encoding="utf-8") == canonical_result.text


def test_replace_failure_rolls_back_existing_bundle(tmp_path, canonical_result):
    source = tmp_path / "lecture.mp3"
    source.touch()
    old = _old_bundle(source)

    def failing_replace(src: Path, dst: Path):
        if src.name.endswith(".json.tmp"):
            raise OSError("injected replace failure")
        src.replace(dst)

    with pytest.raises(EngineError):
        OutputBundleWriter(replace=failing_replace).commit(source, canonical_result)
    OutputBundleValidator().validate(old)
    assert old.txt.read_text(encoding="utf-8") == "old text"
