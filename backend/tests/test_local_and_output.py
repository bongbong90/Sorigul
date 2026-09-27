import json
from pathlib import Path

import pytest

from src.domain.transcription import (
    CancellationToken,
    EngineError,
    StopRequested,
    TranscriptionResult,
)
from src.engines.local_whisper import LocalWhisperEngine
from src.services.output_bundle import BundlePaths, OutputBundleValidator, OutputBundleWriter


def quiet_event(*_args):
    pass


def quiet_progress(_progress):
    pass


class FakeCuda:
    def __init__(self, available):
        self.available = available

    def is_available(self):
        return self.available


class FakeTorch:
    def __init__(self, available):
        self.cuda = FakeCuda(available)


class FakeModel:
    def __init__(self, payload=None, failure=None):
        self.payload = payload or {
            "text": "안녕하세요",
            "segments": [{"start": 0, "end": 1.25, "text": "안녕하세요"}],
            "language": "ko",
        }
        self.failure = failure
        self.calls = []

    def transcribe(self, path, **options):
        self.calls.append((path, options))
        if self.failure is not None:
            failure = self.failure
            self.failure = None
            raise failure
        return self.payload


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


def test_local_lazy_load_reuse_fixed_options_and_no_chunking(tmp_path):
    model = FakeModel()
    whisper = FakeWhisper(model)
    engine = LocalWhisperEngine(
        whisper_loader=lambda: whisper,
        torch_loader=lambda: FakeTorch(False),
    )
    source = tmp_path / "전사자료" / "개념완성_민법_8주차_4강.mp3"
    source.parent.mkdir()
    source.touch()

    assert whisper.loads == []
    first = engine.transcribe(source, CancellationToken(), quiet_event, quiet_progress)
    second = engine.transcribe(source, CancellationToken(), quiet_event, quiet_progress)

    assert first.text == second.text == "안녕하세요"
    assert whisper.loads == [("medium", "cpu")]
    assert len(model.calls) == 2
    assert all(call[0] == str(source) for call in model.calls)
    expected = {**LocalWhisperEngine.TRANSCRIBE_OPTIONS, "fp16": False}
    assert model.calls[0][1] == expected


def test_local_cuda_preferred_and_cpu_load_fallback(tmp_path):
    model = FakeModel()
    whisper = FakeWhisper(model, fail_cuda=True)
    events = []
    engine = LocalWhisperEngine(
        whisper_loader=lambda: whisper,
        torch_loader=lambda: FakeTorch(True),
    )

    engine.transcribe(
        tmp_path / "lecture.mp3",
        CancellationToken(),
        lambda *event: events.append(event),
        quiet_progress,
    )

    assert whisper.loads == [("medium", "cuda"), ("medium", "cpu")]
    assert model.calls[0][1]["fp16"] is False
    assert any("CPU" in event[2] for event in events)


def test_local_fp16_fallback(tmp_path):
    model = FakeModel(failure=RuntimeError("float16 operation failed"))
    whisper = FakeWhisper(model)
    events = []
    engine = LocalWhisperEngine(
        whisper_loader=lambda: whisper,
        torch_loader=lambda: FakeTorch(True),
    )

    engine.transcribe(
        tmp_path / "lecture.mp3",
        CancellationToken(),
        lambda *event: events.append(event),
        quiet_progress,
    )

    assert [call[1]["fp16"] for call in model.calls] == [True, False]
    assert any(event[2] == "fp16 fallback" for event in events)


def test_local_stop_after_blocking_call_discards_result(tmp_path):
    token = CancellationToken()

    class StopModel(FakeModel):
        def transcribe(self, path, **options):
            token.request_stop()
            return super().transcribe(path, **options)

    engine = LocalWhisperEngine(
        whisper_loader=lambda: FakeWhisper(StopModel()),
        torch_loader=lambda: FakeTorch(False),
    )

    with pytest.raises(StopRequested):
        engine.transcribe(tmp_path / "lecture.mp3", token, quiet_event, quiet_progress)


def test_local_cancel_wins_over_engine_failure(tmp_path):
    token = CancellationToken()

    class CancelFailureModel(FakeModel):
        def transcribe(self, path, **options):
            token.request_cancel()
            raise RuntimeError("decode failed after cancel")

    engine = LocalWhisperEngine(
        whisper_loader=lambda: FakeWhisper(CancelFailureModel()),
        torch_loader=lambda: FakeTorch(False),
    )

    from src.domain.transcription import CancelRequested

    with pytest.raises(CancelRequested):
        engine.transcribe(tmp_path / "lecture.mp3", token, quiet_event, quiet_progress)


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
    result = TranscriptionResult(text="무음", segments=[])
    paths = OutputBundleWriter().commit(source, result)
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
    invalid = TranscriptionResult(text="", segments=[])

    with pytest.raises(EngineError):
        OutputBundleWriter().commit(source, invalid)

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
    assert old.txt.read_text(encoding="utf-8") == "old text"


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
