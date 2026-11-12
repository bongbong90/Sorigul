import json
import os
import urllib.error
from pathlib import Path

import pytest

from src.domain.transcription import (
    CancellationToken,
    CancelRequested,
    EngineError,
    ErrorCategory,
    StopRequested,
    TranscriptionResult,
)
from src.domain.models import FileStatus
from src.engines.colab import (
    CHUNK_SECONDS,
    AudioChunk,
    ColabRecoveryCache,
    DirectColabEngine,
    DirectColabHttpClient,
)
from src.services.job_manager import JobManager
from src.services.transcription_runner import TranscriptionRunner


class FakeSplitter:
    def __init__(self, root: Path, starts):
        self.root = root
        self.starts = starts
        self.requested_seconds = []
        self.cleaned = False

    def split(self, source_path, chunk_seconds, token=None):
        self.requested_seconds.append(chunk_seconds)
        chunks = []
        for index, start in enumerate(self.starts):
            path = self.root / f"chunk-{index}.mp3"
            path.write_bytes(b"fake")
            chunks.append(AudioChunk(index, path, start, CHUNK_SECONDS))
        return chunks

    def cleanup(self):
        self.cleaned = True


class FakeClient:
    signature = "fake-colab:v1"

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0
        self.health_calls = 0

    def check_health(self):
        self.health_calls += 1

    def transcribe(self, _chunk_path):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        if callable(outcome):
            return outcome()
        return outcome


def result(text, start=10, end=15):
    return TranscriptionResult.from_engine_payload(
        {"text": text, "segments": [{"start": start, "end": end, "text": text}]}
    )


def transient(code="TIMEOUT"):
    return EngineError(
        code,
        ErrorCategory.NETWORK,
        "temporary",
        retryable=True,
    )


def permanent():
    return EngineError(
        "HTTP_400",
        ErrorCategory.CONFIGURATION,
        "permanent",
        retryable=False,
    )


def make_engine(tmp_path, source, starts, outcomes, delay=0):
    splitter = FakeSplitter(tmp_path, starts)
    client = FakeClient(outcomes)
    cache = ColabRecoveryCache(tmp_path / "cache")
    engine = DirectColabEngine(client, splitter, cache, retry_delay_seconds=delay)
    return engine, client, splitter, cache


def test_colab_uses_fixed_300_seconds_and_merges_offsets(tmp_path):
    source = tmp_path / "긴_강의.mp3"
    source.write_bytes(b"source")
    engine, client, splitter, _ = make_engine(
        tmp_path,
        source,
        [0, 300],
        [result("첫째"), result("둘째")],
    )
    progress = []

    merged = engine.transcribe(source, CancellationToken(), lambda *_: None, progress.append)

    assert splitter.requested_seconds == [300]
    assert client.calls == 2
    assert merged.text == "첫째\n둘째"
    assert [(segment.start, segment.end) for segment in merged.segments] == [(10, 15), (310, 315)]
    assert progress == [0.5, 1.0]
    assert merged.metadata["colab_recovery_cache_used"] is False
    assert "colab_recovery_cache_used" not in merged.output_payload()
    assert splitter.cleaned


@pytest.mark.parametrize("first", [transient("TIMEOUT"), transient("HTTP_500")])
def test_colab_transient_retry_once_then_success(tmp_path, first):
    source = tmp_path / "lecture.mp3"
    source.write_bytes(b"source")
    engine, client, _, _ = make_engine(tmp_path, source, [0], [first, result("ok")])
    events = []
    merged = engine.transcribe(source, CancellationToken(), lambda *args: events.append(args), lambda _: None)
    assert merged.text == "ok"
    assert client.calls == 2
    assert any("다시 시도" in event[2] for event in events)


def test_colab_retry_exhaustion_fails(tmp_path):
    source = tmp_path / "lecture.mp3"
    source.write_bytes(b"source")
    engine, client, _, _ = make_engine(
        tmp_path, source, [0], [transient(), transient()]
    )
    with pytest.raises(EngineError):
        engine.transcribe(source, CancellationToken(), lambda *_: None, lambda _: None)
    assert client.calls == 2


def test_colab_permanent_error_has_no_retry(tmp_path):
    source = tmp_path / "lecture.mp3"
    source.write_bytes(b"source")
    engine, client, _, _ = make_engine(tmp_path, source, [0], [permanent()])
    with pytest.raises(EngineError):
        engine.transcribe(source, CancellationToken(), lambda *_: None, lambda _: None)
    assert client.calls == 1


def test_failed_retry_reuses_completed_chunks(tmp_path):
    source = tmp_path / "lecture.mp3"
    source.write_bytes(b"source")
    cache = ColabRecoveryCache(tmp_path / "cache")
    first_client = FakeClient([result("zero"), result("one"), transient(), transient()])
    first = DirectColabEngine(
        first_client,
        FakeSplitter(tmp_path, [0, 300, 600]),
        cache,
        retry_delay_seconds=0,
    )
    with pytest.raises(EngineError):
        first.transcribe(source, CancellationToken(), lambda *_: None, lambda _: None)

    retry_client = FakeClient([result("two")])
    retry = DirectColabEngine(
        retry_client,
        FakeSplitter(tmp_path, [0, 300, 600]),
        cache,
        retry_delay_seconds=0,
    )
    merged = retry.transcribe(source, CancellationToken(), lambda *_: None, lambda _: None)

    assert first_client.calls == 4
    assert retry_client.calls == 1
    assert merged.text == "zero\none\ntwo"
    assert merged.metadata["colab_recovery_cache_used"] is True
    assert "colab_recovery_cache_used" not in merged.output_payload()


def test_source_change_invalidates_failed_cache(tmp_path):
    source = tmp_path / "lecture.mp3"
    source.write_bytes(b"source")
    cache = ColabRecoveryCache(tmp_path / "cache")
    cache.save(source, FakeClient.signature, {0: result("cached")})
    source.write_bytes(b"changed-source-size")
    os.utime(source, None)

    client = FakeClient([result("fresh")])
    engine = DirectColabEngine(
        client,
        FakeSplitter(tmp_path, [0]),
        cache,
        retry_delay_seconds=0,
    )
    merged = engine.transcribe(source, CancellationToken(), lambda *_: None, lambda _: None)
    assert client.calls == 1
    assert merged.text == "fresh"


@pytest.mark.parametrize("cancel", [False, True])
def test_stop_cancel_discards_cache_and_next_run_starts_at_first_chunk(tmp_path, cancel):
    source = tmp_path / "lecture.mp3"
    source.write_bytes(b"source")
    cache = ColabRecoveryCache(tmp_path / "cache")
    token = CancellationToken()

    def request_action():
        if cancel:
            token.request_cancel()
        else:
            token.request_stop()
        return result("first")

    first_client = FakeClient([request_action])
    first = DirectColabEngine(
        first_client,
        FakeSplitter(tmp_path, [0, 300]),
        cache,
        retry_delay_seconds=0,
    )
    expected = CancelRequested if cancel else StopRequested
    with pytest.raises(expected):
        first.transcribe(source, token, lambda *_: None, lambda _: None)

    retry_client = FakeClient([result("new-zero"), result("new-one")])
    retry = DirectColabEngine(
        retry_client,
        FakeSplitter(tmp_path, [0, 300]),
        cache,
        retry_delay_seconds=0,
    )
    retry.transcribe(source, CancellationToken(), lambda *_: None, lambda _: None)
    assert retry_client.calls == 2


def test_colab_cancel_wins_over_network_failure(tmp_path):
    source = tmp_path / "lecture.mp3"
    source.write_bytes(b"source")
    token = CancellationToken()

    def cancel_then_fail():
        token.request_cancel()
        raise transient()

    engine, _, _, _ = make_engine(tmp_path, source, [0], [cancel_then_fail])
    with pytest.raises(CancelRequested):
        engine.transcribe(source, token, lambda *_: None, lambda _: None)


@pytest.mark.parametrize(
    "status,retryable,fatal",
    [
        (500, True, False),
        (408, True, False),
        (429, True, False),
        (400, False, False),
        (401, False, True),
        (403, False, True),
        (404, False, True),
        (405, False, True),
    ],
)
def test_http_client_classifies_status_without_network(
    tmp_path, monkeypatch, status, retryable, fatal
):
    chunk = tmp_path / "chunk.mp3"
    chunk.write_bytes(b"audio")

    def fail_request(*_args, **_kwargs):
        raise urllib.error.HTTPError(
            url="https://example.invalid/transcribe",
            code=status,
            msg="failure",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr("urllib.request.urlopen", fail_request)
    client = DirectColabHttpClient("https://example.invalid")
    with pytest.raises(EngineError) as caught:
        client.transcribe(chunk)
    assert caught.value.retryable is retryable
    assert caught.value.fatal is fatal


class FakeHttpResponse:
    def __init__(self, payload=b"", status=200):
        self.payload = payload
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.payload


def http_error(status):
    return urllib.error.HTTPError(
        url="https://example.invalid/transcribe",
        code=status,
        msg="failure",
        hdrs=None,
        fp=None,
    )


def successful_http_response(text):
    payload = {
        "text": text,
        "segments": [{"start": 0, "end": 1, "text": text}],
    }
    return FakeHttpResponse(json.dumps(payload).encode("utf-8"))


def run_two_file_http_job(tmp_path, monkeypatch, transcribe_outcomes):
    folder = tmp_path / "sources"
    folder.mkdir()
    for name in ("A", "B"):
        (folder / f"{name}.mp3").write_bytes(b"source")

    outcomes = iter(transcribe_outcomes)
    transcribe_calls = []

    def urlopen(request, **_kwargs):
        if request.full_url.endswith("/health"):
            return FakeHttpResponse()
        transcribe_calls.append(request.full_url)
        outcome = next(outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    manager = JobManager(str(tmp_path / "runtime" / "jobs.json"))
    job = manager.create_job(str(folder), ["A", "B"])
    engine = DirectColabEngine(
        DirectColabHttpClient("https://example.invalid"),
        FakeSplitter(tmp_path, [0]),
        ColabRecoveryCache(tmp_path / "cache"),
        retry_delay_seconds=0,
    )
    TranscriptionRunner(manager, lambda _job: engine).run(job.job_id, CancellationToken())
    return manager.get_job(job.job_id), transcribe_calls


def test_http_400_fails_current_file_and_continues_batch(tmp_path, monkeypatch):
    finished, calls = run_two_file_http_job(
        tmp_path,
        monkeypatch,
        [http_error(400), successful_http_response("B")],
    )

    assert len(calls) == 2
    assert finished.files == {"A": FileStatus.FAILED, "B": FileStatus.DONE}
    assert finished.status == FileStatus.FAILED


@pytest.mark.parametrize("status", [401, 403])
def test_auth_http_error_is_fatal_and_stops_batch(tmp_path, monkeypatch, status):
    finished, calls = run_two_file_http_job(
        tmp_path,
        monkeypatch,
        [http_error(status)],
    )

    assert len(calls) == 1
    assert finished.files == {"A": FileStatus.FAILED, "B": FileStatus.WAITING}
    assert finished.status == FileStatus.FAILED


def test_transient_exhaustion_fails_current_file_and_continues_batch(tmp_path, monkeypatch):
    finished, calls = run_two_file_http_job(
        tmp_path,
        monkeypatch,
        [TimeoutError("first"), TimeoutError("retry"), successful_http_response("B")],
    )

    assert len(calls) == 3
    assert finished.files == {"A": FileStatus.FAILED, "B": FileStatus.DONE}
    assert finished.status == FileStatus.FAILED


@pytest.mark.parametrize(
    "invalid_payload",
    [
        b"not-json",
        json.dumps(
            {
                "text": "invalid segment",
                "segments": [{"start": "invalid", "end": 1, "text": "bad"}],
            }
        ).encode("utf-8"),
    ],
)
def test_invalid_response_fails_current_file_and_continues_batch(
    tmp_path, monkeypatch, invalid_payload
):
    finished, calls = run_two_file_http_job(
        tmp_path,
        monkeypatch,
        [FakeHttpResponse(invalid_payload), successful_http_response("B")],
    )

    assert len(calls) == 2
    assert finished.files == {"A": FileStatus.FAILED, "B": FileStatus.DONE}
    assert finished.status == FileStatus.FAILED

def test_colab_url_normalization():
    from src.services.colab_url import normalize_colab_base_url, ColabUrlError

    assert normalize_colab_base_url('https://example.test') == 'https://example.test'
    assert normalize_colab_base_url('https://example.test/') == 'https://example.test'
    assert normalize_colab_base_url('https://example.test/health') == 'https://example.test'
    assert normalize_colab_base_url('https://example.test/transcribe') == 'https://example.test'
    assert normalize_colab_base_url('  http://local:8080/health  ') == 'http://local:8080'

    with pytest.raises(ColabUrlError):
        normalize_colab_base_url('ftp://example.test')

    with pytest.raises(ColabUrlError):
        normalize_colab_base_url('https://')

    with pytest.raises(ColabUrlError):
        normalize_colab_base_url('https://example.test/?a=1')

    with pytest.raises(ColabUrlError):
        normalize_colab_base_url('https://example.test/#hash')

    with pytest.raises(ColabUrlError):
        normalize_colab_base_url('https://user:pass@example.test')

    with pytest.raises(ColabUrlError):
        normalize_colab_base_url('https://example.test/otherpath')

def test_http_client_url_construction(monkeypatch):
    calls = []
    def mock_urlopen(req, **kwargs):
        calls.append(req.full_url)
        return FakeHttpResponse()

    monkeypatch.setattr('urllib.request.urlopen', mock_urlopen)

    client = DirectColabHttpClient('https://example.test/health')
    assert client.base_url == 'https://example.test'

    client.check_health()
    assert calls[-1] == 'https://example.test/health'

    import tempfile
    import os
    fd, path_str = tempfile.mkstemp(suffix='.mp3')
    os.close(fd)
    path = Path(path_str)
    path.write_bytes(b'dummy')
    try:
        with pytest.raises(EngineError):
            client.transcribe(path)
        assert calls[-1] == 'https://example.test/transcribe'
    finally:
        path.unlink(missing_ok=True)

def test_ffmpeg_splitter_fallback_on_duration_none(tmp_path, monkeypatch):
    import shutil
    import subprocess
    from src.engines.colab import FFmpegAudioSplitter

    source = tmp_path / 'source.mp3'
    source.write_bytes(b'source')

    class FakeAudioMetadataService:
        def duration_seconds(self, path):
            return None
    monkeypatch.setattr('src.services.audio_metadata.AudioMetadataService', FakeAudioMetadataService)

    monkeypatch.setattr('src.utils.ffmpeg_runtime.resolve_ffmpeg_path', lambda: Path('dummy_ffmpeg'))

    def write_segments(cmd):
        temp_dir = Path(cmd[-1]).parent
        (temp_dir / 'chunk-00000.mp3').write_bytes(b'x' * 2048)
        (temp_dir / 'chunk-00001.mp3').write_bytes(b'x' * 2048)

    popen = FakePopen(on_start=write_segments)
    splitter = FFmpegAudioSplitter(popen=popen, poll_interval_seconds=0)
    chunks = splitter.split(source, 300)
    commands = popen.commands

    assert len(chunks) == 2
    assert chunks[0].index == 0
    assert chunks[0].start_seconds == 0.0
    assert chunks[1].index == 1
    assert chunks[1].start_seconds == 300.0

    assert '-f' in commands[0]
    assert 'segment' in commands[0]
    assert '-segment_time' in commands[0]

def test_ffmpeg_splitter_missing_ffmpeg(tmp_path, monkeypatch):
    from src.engines.colab import FFmpegAudioSplitter
    source = tmp_path / 'source.mp3'
    monkeypatch.setattr('src.utils.ffmpeg_runtime.resolve_ffmpeg_path', lambda: None)

    with pytest.raises(EngineError, match='ffmpeg를 찾을 수 없습니다'):
        FFmpegAudioSplitter().split(source, 300)


def test_malformed_port_url():
    from src.services.colab_url import normalize_colab_base_url, ColabUrlError
    with pytest.raises(ColabUrlError):
        normalize_colab_base_url('https://example.test:notaport')

def test_malformed_port_http_client():
    from src.engines.colab import DirectColabHttpClient, EngineError
    with pytest.raises(EngineError) as exc:
        DirectColabHttpClient('https://example.test:notaport')
    assert exc.value.code == 'COLAB_URL_INVALID'


def test_ffmpeg_splitter_known_duration_logic(tmp_path, monkeypatch):
    import subprocess
    from src.engines.colab import FFmpegAudioSplitter

    source = tmp_path / 'source.mp3'
    source.write_bytes(b'source')

    class FakeAudioMetadataService:
        def duration_seconds(self, path):
            return 650.0
    monkeypatch.setattr('src.services.audio_metadata.AudioMetadataService', FakeAudioMetadataService)
    monkeypatch.setattr('src.utils.ffmpeg_runtime.resolve_ffmpeg_path', lambda: Path('dummy_ffmpeg'))

    popen = FakePopen(on_start=lambda cmd: Path(cmd[-1]).write_bytes(b'x' * 2048))
    splitter = FFmpegAudioSplitter(popen=popen, poll_interval_seconds=0)
    chunks = splitter.split(source, 300)
    commands = popen.commands

    assert len(chunks) == 3

    assert chunks[0].start_seconds == 0.0
    assert chunks[0].duration_seconds == 300.0

    assert chunks[1].start_seconds == 300.0
    assert chunks[1].duration_seconds == 300.0

    assert chunks[2].start_seconds == 600.0
    assert chunks[2].duration_seconds == 50.0

    # Verify we are using -ss and -t
    for cmd in commands:
        assert '-ss' in cmd
        assert '-t' in cmd
        assert '-f' not in cmd
        assert 'segment' not in cmd


# -- Bounded, token-aware ffmpeg process (AUD-COL-001) ------------------------


class FakeProcess:
    """Stands in for one exact ffmpeg child. Never launches anything."""

    def __init__(self, command, kwargs, returncode=0, hang=False, on_wait=None, unreapable=False):
        self.command = command
        self.kwargs = kwargs
        self.returncode = returncode
        self.hang = hang
        self.on_wait = on_wait
        self.unreapable = unreapable
        self.pid = 4242
        self.wait_calls = 0
        self.terminated = False
        self.killed = False
        self.reaped = False
        self.waits_after_stop = []

    def wait(self, timeout=None):
        import subprocess

        self.wait_calls += 1
        if self.on_wait is not None:
            self.on_wait(self)
        if self.terminated or self.killed:
            self.waits_after_stop.append("kill" if self.killed else "terminate")
            if self.unreapable:
                raise subprocess.TimeoutExpired(self.command, timeout)
        if self.hang and not (self.terminated or self.killed):
            raise subprocess.TimeoutExpired(self.command, timeout)
        if self.terminated or self.killed:
            self.reaped = True
            return -15
        return self.returncode

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True


class FakePopen:
    def __init__(self, on_start=None, returncode=0, hang=False, stderr=b"", on_wait=None, unreapable=False):
        self.on_start = on_start
        self.returncode = returncode
        self.hang = hang
        self.stderr = stderr
        self.on_wait = on_wait
        self.unreapable = unreapable
        self.commands = []
        self.processes = []

    def __call__(self, command, **kwargs):
        assert "shell" not in kwargs, "ffmpeg must never run through a shell"
        self.commands.append(command)
        if self.stderr:
            kwargs["stderr"].write(self.stderr)
        if self.on_start is not None:
            self.on_start(command)
        process = FakeProcess(
            command, kwargs, self.returncode, self.hang, self.on_wait, self.unreapable
        )
        self.processes.append(process)
        return process


class SteppingClock:
    def __init__(self, step):
        self.now = 0.0
        self.step = step

    def __call__(self):
        self.now += self.step
        return self.now


@pytest.fixture(params=[650.0, None], ids=["duration-known", "fallback-segment"])
def split_source(request, tmp_path, monkeypatch):
    source = tmp_path / "source.mp3"
    source.write_bytes(b"source")

    class FakeAudioMetadataService:
        def duration_seconds(self, path):
            return request.param

    monkeypatch.setattr("src.services.audio_metadata.AudioMetadataService", FakeAudioMetadataService)
    monkeypatch.setattr("src.utils.ffmpeg_runtime.resolve_ffmpeg_path", lambda: Path("dummy_ffmpeg"))
    return source


def _temp_dir_of(popen):
    return Path(popen.commands[0][-1]).parent


def test_ffmpeg_split_timeout_constant_is_300_seconds():
    from src.engines.colab import FFMPEG_SPLIT_TIMEOUT_SECONDS, FFmpegAudioSplitter

    assert FFMPEG_SPLIT_TIMEOUT_SECONDS == 300
    assert FFmpegAudioSplitter().timeout_seconds == 300


def test_ffmpeg_nonzero_exit_fails_with_bounded_stderr_and_cleans_up(split_source):
    from src.engines.colab import FFmpegAudioSplitter

    popen = FakePopen(returncode=1, stderr=b"decode error")
    splitter = FFmpegAudioSplitter(popen=popen, poll_interval_seconds=0)

    with pytest.raises(EngineError) as caught:
        splitter.split(split_source, 300, CancellationToken())

    assert caught.value.code == "AUDIO_SPLIT_FAILED"
    assert "decode error" in caught.value.technical_detail
    assert len(popen.processes) == 1
    assert not _temp_dir_of(popen).exists()


def test_ffmpeg_timeout_kills_exact_child_reaps_and_cleans_up(split_source):
    from src.engines.colab import FFmpegAudioSplitter

    popen = FakePopen(hang=True, stderr=b"still encoding")
    splitter = FFmpegAudioSplitter(
        timeout_seconds=300,
        popen=popen,
        clock=SteppingClock(step=100),
        poll_interval_seconds=0,
    )

    with pytest.raises(EngineError) as caught:
        splitter.split(split_source, 300, CancellationToken())

    assert caught.value.code == "AUDIO_SPLIT_TIMEOUT"
    assert caught.value.user_message == "Colab 전사를 위한 오디오 준비 시간이 초과되었습니다."
    assert caught.value.fatal is False
    assert "still encoding" in caught.value.technical_detail
    process = popen.processes[0]
    assert process.terminated and process.reaped
    assert len(popen.processes) == 1, "a timed-out split must not be retried"
    assert not _temp_dir_of(popen).exists()


@pytest.mark.parametrize("cancel", [False, True], ids=["stop", "cancel"])
def test_ffmpeg_stop_or_cancel_kills_exact_child_reaps_and_cleans_up(split_source, cancel):
    from src.engines.colab import FFmpegAudioSplitter

    token = CancellationToken()

    def request_while_running(process):
        # Deterministic: the request lands while ffmpeg is still running.
        if process.wait_calls == 2:
            token.request_cancel() if cancel else token.request_stop()

    popen = FakePopen(hang=True, on_wait=request_while_running)
    splitter = FFmpegAudioSplitter(popen=popen, poll_interval_seconds=0)

    expected = CancelRequested if cancel else StopRequested
    with pytest.raises(expected):
        splitter.split(split_source, 300, token)

    process = popen.processes[0]
    assert process.terminated and process.reaped
    assert len(popen.processes) == 1
    assert not _temp_dir_of(popen).exists()


def test_reap_failure_is_explicit_after_terminate_and_kill():
    from src.engines.colab import FFMPEG_PROCESS_CLEANUP_FAILED, _reap

    process = FakeProcess(["ffmpeg"], {}, hang=True, unreapable=True)

    with pytest.raises(EngineError) as caught:
        _reap(process)

    assert process.terminated and process.killed
    assert process.waits_after_stop == ["terminate", "kill"], "both waits must be attempted"
    assert process.reaped is False
    assert caught.value.code == FFMPEG_PROCESS_CLEANUP_FAILED
    assert caught.value.category == ErrorCategory.RUNTIME
    assert caught.value.fatal is True
    assert caught.value.user_message == "Colab 오디오 준비 프로세스를 안전하게 종료하지 못했습니다."
    assert "wait-after-kill=timeout" in caught.value.technical_detail


def test_ffmpeg_timeout_with_unreapable_child_reports_cleanup_failure(split_source):
    from src.engines.colab import FFMPEG_PROCESS_CLEANUP_FAILED, FFmpegAudioSplitter

    popen = FakePopen(hang=True, unreapable=True)
    splitter = FFmpegAudioSplitter(
        timeout_seconds=300,
        popen=popen,
        clock=SteppingClock(step=100),
        poll_interval_seconds=0,
    )

    with pytest.raises(EngineError) as caught:
        splitter.split(split_source, 300, CancellationToken())

    assert caught.value.code == FFMPEG_PROCESS_CLEANUP_FAILED, "must not be masked as AUDIO_SPLIT_TIMEOUT"
    assert caught.value.fatal is True
    process = popen.processes[0]
    assert process.terminated and process.killed
    assert process.waits_after_stop == ["terminate", "kill"]


@pytest.mark.parametrize("cancel", [False, True], ids=["stop", "cancel"])
def test_ffmpeg_stop_or_cancel_with_unreapable_child_reports_cleanup_failure(split_source, cancel):
    from src.engines.colab import FFMPEG_PROCESS_CLEANUP_FAILED, FFmpegAudioSplitter

    token = CancellationToken()

    def request_while_running(process):
        if process.wait_calls == 1:
            token.request_cancel() if cancel else token.request_stop()

    popen = FakePopen(hang=True, unreapable=True, on_wait=request_while_running)
    splitter = FFmpegAudioSplitter(popen=popen, poll_interval_seconds=0)

    with pytest.raises(EngineError) as caught:
        splitter.split(split_source, 300, token)

    assert caught.value.code == FFMPEG_PROCESS_CLEANUP_FAILED
    process = popen.processes[0]
    assert process.terminated and process.killed
    assert process.waits_after_stop == ["terminate", "kill"]


class CleanupFailingSplitter(FakeSplitter):
    def __init__(self, root, token, cancel):
        super().__init__(root, [0])
        self.token = token
        self.cancel = cancel

    def split(self, source_path, chunk_seconds, token=None):
        from src.engines.colab import _process_cleanup_failed_error

        self.token.request_cancel() if self.cancel else self.token.request_stop()
        raise _process_cleanup_failed_error("ffmpeg pid=4242 not reaped")


@pytest.mark.parametrize("cancel", [False, True], ids=["stop", "cancel"])
def test_engine_does_not_turn_cleanup_failure_into_stop_or_cancel(tmp_path, cancel):
    from src.engines.colab import FFMPEG_PROCESS_CLEANUP_FAILED

    source = tmp_path / "lecture.mp3"
    source.write_bytes(b"source")
    token = CancellationToken()
    engine = DirectColabEngine(
        FakeClient([]),
        CleanupFailingSplitter(tmp_path, token, cancel),
        ColabRecoveryCache(tmp_path / "cache"),
        retry_delay_seconds=0,
    )

    with pytest.raises(EngineError) as caught:
        engine.transcribe(source, token, lambda *_: None, lambda _: None)
    assert caught.value.code == FFMPEG_PROCESS_CLEANUP_FAILED


@pytest.mark.parametrize("cancel", [False, True], ids=["stop", "cancel"])
def test_runner_never_reports_stopped_or_cancelled_when_cleanup_failed(tmp_path, cancel):
    folder = tmp_path / "sources"
    folder.mkdir()
    for name in ("A", "B"):
        (folder / f"{name}.mp3").write_bytes(b"source")
    manager = JobManager(str(tmp_path / "runtime" / "jobs.json"))
    job = manager.create_job(str(folder), ["A", "B"], engine="direct_colab")
    token = CancellationToken()
    engine = DirectColabEngine(
        FakeClient([]),
        CleanupFailingSplitter(tmp_path, token, cancel),
        ColabRecoveryCache(tmp_path / "cache"),
        retry_delay_seconds=0,
    )

    TranscriptionRunner(manager, lambda _job: engine).run(job.job_id, token)

    finished = manager.get_job(job.job_id)
    assert finished.status == FileStatus.FAILED
    assert finished.files["A"] == FileStatus.FAILED
    assert FileStatus.STOPPED not in finished.files.values()
    assert FileStatus.CANCELLED not in finished.files.values()
    assert finished.batch_completed is False
    job_events = [e.message for e in finished.events if e.category == "Job" and e.message.startswith("Job ")]
    assert job_events == ["Job 실패"]
    assert not (folder / "A.txt").exists()


def test_colab_engine_passes_token_to_splitter(tmp_path):
    source = tmp_path / "lecture.mp3"
    source.write_bytes(b"source")
    seen = []

    class RecordingSplitter(FakeSplitter):
        def split(self, source_path, chunk_seconds, token=None):
            seen.append(token)
            return super().split(source_path, chunk_seconds, token)

    token = CancellationToken()
    engine = DirectColabEngine(
        FakeClient([result("ok")]),
        RecordingSplitter(tmp_path, [0]),
        ColabRecoveryCache(tmp_path / "cache"),
        retry_delay_seconds=0,
    )
    engine.transcribe(source, token, lambda *_: None, lambda _: None)

    assert seen == [token]

