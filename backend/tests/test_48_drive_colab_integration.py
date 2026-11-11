"""#48: synthetic audio and local HTTP bootstrap; never Google/Colab accounts."""

import json
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from colab.sorigul_colab_bootstrap import ActivePairing, RuntimeIdentity, create_app
from src.domain.models import DriveStatus, FileStatus
from src.domain.transcription import CancellationToken, TranscriptionResult
from src.engines.colab import ColabRecoveryCache, DirectColabEngine, DirectColabHttpClient, FFmpegAudioSplitter
from src.services.colab_security import PairingRegistry, parse_request_id
from src.services.drive import DriveError, DriveExecutionService, DriveUploadService, GoogleDriveClient
from src.services.job_manager import JobManager
from src.services.output_bundle import BundlePaths, OutputBundleValidator
from src.services.settings import SettingsManager
from src.services.transcription_runner import TranscriptionRunner
from test_drive_results_desktop import FakeAuth, FakeDriveClient, make_done_job


STEM = "개념완성_민법_8주차_4강"


class ListAPI:
    def __init__(self, pages):
        self.pages = iter(pages)
        self.queries = []
        self.created = []

    def files(self):
        return self

    def list(self, **kwargs):
        self.queries.append(kwargs)
        return SimpleNamespace(execute=lambda: next(self.pages))

    def create(self, **kwargs):
        self.created.append(kwargs)
        return SimpleNamespace(execute=lambda: {"id": "new"})


@pytest.mark.parametrize("folder", [False, True])
@pytest.mark.parametrize("pages", [
    [{"files": [{"id": "a"}, {"id": "b"}]}],
    [{"files": [{"id": "a"}], "nextPageToken": "next"}, {"files": [{"id": "b"}]}],
    [{"files": [], "nextPageToken": "next"}, {"files": [{"id": "a"}, {"id": "b"}]}],
])
def test_duplicate_drive_targets_fail_closed(folder, pages):
    api = ListAPI(pages)
    client = GoogleDriveClient(api)
    lookup = client.find_or_create_folder if folder else client.find_file
    with pytest.raises(DriveError) as caught:
        lookup("parent", "same")
    assert caught.value.code == "DRIVE_TARGET_AMBIGUOUS"
    assert api.created == []


@pytest.mark.parametrize("folder", [False, True])
@pytest.mark.parametrize("present", [False, True])
def test_unique_drive_lookup_reads_all_pages_and_escapes(folder, present):
    api = ListAPI([
        {"files": [], "nextPageToken": "next"},
        {"files": [{"id": "existing"}] if present else []},
    ])
    client = GoogleDriveClient(api)
    lookup = client.find_or_create_folder if folder else client.find_file
    assert lookup("par'ent", "a\\b'c") == ("existing" if present else "new" if folder else None)
    assert api.queries[1]["pageToken"] == "next"
    query = api.queries[0]["q"]
    assert "par\\'ent" in query and "a\\\\b\\'c" in query
    assert "trashed = false" in query
    assert ("mimeType =" if folder else "mimeType !=") in query
    assert len(api.created) == int(folder and not present)


def test_ambiguous_upload_preserves_done_and_reports_actionable_error(tmp_path):
    _, manager, job = make_done_job(tmp_path)

    class AmbiguousClient(FakeDriveClient):
        def find_file(self, *_args):
            raise DriveError("DRIVE_TARGET_AMBIGUOUS", "duplicate target; resolve before retry")

    client = AmbiguousClient()
    service = DriveUploadService(manager, FakeAuth(client), SettingsManager(tmp_path / "s.json"))
    state = service.upload(job.job_id, STEM)
    assert state.status == DriveStatus.FAILED
    assert state.error == "duplicate target; resolve before retry"
    assert client.created == client.updated == []
    assert manager.get_job(job.job_id).files[STEM] == FileStatus.DONE


def test_upload_refuses_non_done_without_remote_calls(tmp_path):
    _, manager, job = make_done_job(tmp_path)
    manager.mutate_job(job.job_id, lambda item: item.files.update({STEM: FileStatus.FAILED}))
    client = FakeDriveClient()
    service = DriveUploadService(manager, FakeAuth(client), SettingsManager(tmp_path / "s.json"))
    with pytest.raises(DriveError) as caught:
        service.upload(job.job_id, STEM)
    assert caught.value.code == "LOCAL_RESULT_NOT_DONE"
    assert client.folders == client.files == {}


def test_cross_job_lookup_create_is_serialized(tmp_path):
    _, manager, first = make_done_job(tmp_path)
    second = manager.create_job(first.folder, [STEM])
    manager.mutate_job(second.job_id, lambda item: item.files.update({STEM: FileStatus.DONE}))
    entered, release, second_waiting = threading.Event(), threading.Event(), threading.Event()

    class BlockingClient(FakeDriveClient):
        def create_file(self, *args):
            entered.set()
            assert release.wait(5)
            return super().create_file(*args)

    client = BlockingClient()
    service = DriveUploadService(manager, FakeAuth(client), SettingsManager(tmp_path / "s.json"))
    upload_lock = service._upload_lock

    class ObservedLock:
        attempts = 0
        counter_lock = threading.Lock()

        def __enter__(self):
            with self.counter_lock:
                self.attempts += 1
                if self.attempts == 2:
                    second_waiting.set()
            upload_lock.acquire()

        def __exit__(self, *_args):
            upload_lock.release()

    service._upload_lock = ObservedLock()
    executor = DriveExecutionService(service, max_workers=2)
    try:
        assert executor.submit(first.job_id, STEM)
        assert entered.wait(5)
        assert not executor.submit(first.job_id, STEM)
        assert executor.submit(second.job_id, STEM)
        assert second_waiting.wait(5), "second Job reached the shared destination lock"
        assert client.created == client.updated == []
        assert service.has_in_flight()
    finally:
        release.set()
        executor._executor.shutdown(wait=True)
    assert len(client.created) == 3 and len(client.updated) == 3
    assert len(client.files) == 3
    assert all(manager.get_job(job.job_id).drive[STEM].status == DriveStatus.DONE for job in (first, second))


class SyntheticModel:
    def __init__(self):
        self.paths = []
        self.failures = 0
        self.on_transcribe = lambda: None

    def transcribe(self, path, **_kwargs):
        self.paths.append(Path(path))
        self.on_transcribe()
        if self.failures:
            self.failures -= 1
            raise RuntimeError("injected local endpoint failure")
        # The model is deliberately fake: this proves transport and lifecycle,
        # not Whisper recognition or account-backed large-v3 execution.
        segment = SimpleNamespace(start=0.0, end=0.2, text="합성 전사 결과 " * 30)
        return iter([segment]), SimpleNamespace(language="ko")


@pytest.fixture
def fake_endpoint():
    session = PairingRegistry().create()
    _, key = parse_request_id(session.request_id)
    pairing = ActivePairing()
    pairing.activate(session.request_id, key)
    model = SyntheticModel()
    app = create_app(model, "test-local-secret", pairing, RuntimeIdentity("faster-whisper", "large-v3", "cpu", "int8"))
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", lifespan="off", ws="none"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 5
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started
        yield f"http://127.0.0.1:{port}", session, model
    finally:
        server.should_exit = True
        thread.join(5)
        listener.close()
        assert not thread.is_alive(), "owned local HTTP server must exit"
        assert all(not path.exists() for path in model.paths)


def synthesize_mp3(path, seconds):
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        pytest.skip("real synthetic MP3 regression requires ffmpeg")
    subprocess.run([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "lavfi",
        "-i", "sine=frequency=440:sample_rate=16000", "-t", str(seconds),
        "-codec:a", "libmp3lame", "-y", str(path),
    ], check=True, timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


@pytest.mark.parametrize("seconds,count", [(0.1, 1), (300, 1), (300.5, 2), (600, 2)])
@pytest.mark.parametrize("fallback", [False, True])
def test_real_split_preserves_short_audio_and_excludes_header_only_tail(tmp_path, monkeypatch, seconds, count, fallback):
    from src.services.audio_metadata import AudioMetadataService

    source = tmp_path / "source.mp3"
    synthesize_mp3(source, seconds)
    splitter = FFmpegAudioSplitter()
    duration = AudioMetadataService.duration_seconds
    if fallback:
        monkeypatch.setattr(AudioMetadataService, "duration_seconds", lambda self, path: None if path == source else duration(self, path))
    try:
        chunks = splitter.split(source, 300)
        # The segment muxer may emit a final decodable frame from encoder
        # padding; the seek-based path can instead produce an ID3-only file.
        assert count <= len(chunks) <= count + int(fallback)
        for chunk in chunks:
            # Decode every retained output: FakeModel alone cannot detect
            # an ID3-only MP3 generated from encoder padding at 300/600s.
            subprocess.run([
                shutil.which("ffmpeg"), "-v", "error", "-i", str(chunk.path),
                "-f", "null", "-",
            ], check=True, timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    finally:
        splitter.cleanup()
    assert splitter._temp_dir is None


class SyntheticLocalEngine:
    def transcribe(self, _source, _token, _event, progress):
        progress(1.0)
        return TranscriptionResult.from_engine_payload({
            "text": "합성 Local 결과 " * 30,
            "segments": [{"start": 0, "end": 1, "text": "합성 Local 결과"}],
        })


@pytest.mark.parametrize("engine_name,seconds,expected_chunks", [
    ("local_whisper", 2, 0), ("direct_colab", 2, 1), ("direct_colab", 300.5, 2),
])
@pytest.mark.parametrize("upload", [False, True])
@pytest.mark.parametrize("drive_failure", ["none", "partial", "auth"])
def test_transcription_to_drive_e2e(tmp_path, monkeypatch, fake_endpoint, engine_name, seconds, expected_chunks, upload, drive_failure):
    import src.api.routes as routes

    url, session, model = fake_endpoint
    folder = tmp_path / "audio"
    folder.mkdir()
    source = folder / f"{STEM}.mp3"
    synthesize_mp3(source, seconds)
    engine = SyntheticLocalEngine()
    splitter = FFmpegAudioSplitter()
    if engine_name == "direct_colab":
        engine = DirectColabEngine(DirectColabHttpClient(url, session), splitter, ColabRecoveryCache(tmp_path / "cache"), 0)
    manager = JobManager(str(tmp_path / "jobs.json"))
    client = FakeDriveClient(fail_name=f"{STEM}.json" if drive_failure == "partial" else None)
    settings = SettingsManager(tmp_path / "settings.json")
    auth = FakeAuth(client, error=DriveError("DRIVE_AUTH_REQUIRED", "test reauth required") if drive_failure == "auth" else None)
    drive = DriveUploadService(manager, auth, settings)
    executor = DriveExecutionService(drive)
    monkeypatch.setattr(routes, "job_manager", manager)
    monkeypatch.setattr(routes, "drive_execution_service", executor)
    job = manager.create_job(str(folder), [STEM], engine=engine_name, upload_to_drive=upload)
    runner = TranscriptionRunner(manager, lambda _job: engine, file_completed_callback=routes.handle_file_completed)
    try:
        runner.run(job.job_id, CancellationToken())
    finally:
        executor._executor.shutdown(wait=True)
    final = manager.get_job(job.job_id)
    assert final.status == final.files[STEM] == FileStatus.DONE
    bundle = BundlePaths.final_for(source)
    OutputBundleValidator().validate(bundle)
    assert bundle.srt.read_text(encoding="utf-8").strip()
    assert len(model.paths) == expected_chunks
    if engine_name == "direct_colab":
        payload = json.loads(bundle.json.read_text(encoding="utf-8"))
        assert [segment["start"] for segment in payload["segments"]] == [300.0 * index for index in range(expected_chunks)]
        assert splitter._temp_dir is None
    assert source.exists()
    if upload:
        expected = {"none": DriveStatus.DONE, "partial": DriveStatus.FAILED, "auth": DriveStatus.AUTH_REQUIRED}[drive_failure]
        assert final.drive[STEM].status == expected
        if drive_failure != "none":
            before = {ext: path.read_bytes() for ext, path in bundle.as_dict().items()}
            if drive_failure == "partial":
                assert list(final.drive[STEM].remote_file_ids) == [f"{STEM}.txt"]
            client.fail_name = None
            auth.error = None
            assert drive.retry(job.job_id, STEM).status == DriveStatus.DONE
            assert {ext: path.read_bytes() for ext, path in bundle.as_dict().items()} == before
            assert len(model.paths) == expected_chunks, "Drive retry must not repeat transcription"
        assert sorted(client.created) == sorted([f"{STEM}.{ext}" for ext in ("txt", "json", "srt")])
        assert list(client.folders)[-1][1] == "개념완성_민법_8주차"
    else:
        assert not final.drive and not client.files and not client.folders


@pytest.mark.parametrize("action", ["stop", "cancel", "fail", "retry"])
def test_http_failure_stop_retry_preserves_existing_bundle(tmp_path, fake_endpoint, action):
    from src.services.output_bundle import OutputBundleWriter

    url, session, model = fake_endpoint
    folder = tmp_path / "audio"
    folder.mkdir()
    source = folder / f"{STEM}.mp3"
    synthesize_mp3(source, 2)
    original = TranscriptionResult.from_engine_payload({
        "text": "기존 정상 결과 " * 30,
        "segments": [{"start": 0, "end": 1, "text": "기존 정상 결과"}],
    })
    bundle = OutputBundleWriter().commit(source, original)
    before = {ext: path.read_bytes() for ext, path in bundle.as_dict().items()}
    manager = JobManager(str(tmp_path / "jobs.json"))
    job = manager.create_job(str(folder), [STEM], engine="direct_colab", force_retranscribe=True)
    token = CancellationToken()
    if action in {"stop", "cancel"}:
        model.on_transcribe = token.request_stop if action == "stop" else token.request_cancel
    else:
        model.failures = 1 if action == "retry" else 2
    splitter = FFmpegAudioSplitter()
    cache = ColabRecoveryCache(tmp_path / "cache")
    engine = DirectColabEngine(DirectColabHttpClient(url, session), splitter, cache, 0)
    TranscriptionRunner(manager, lambda _job: engine).run(job.job_id, token)
    final = manager.get_job(job.job_id)
    expected = {"stop": FileStatus.STOPPED, "cancel": FileStatus.CANCELLED,
                "fail": FileStatus.FAILED, "retry": FileStatus.DONE}[action]
    assert final.status == final.files[STEM] == expected
    assert splitter._temp_dir is None
    assert not list(folder.glob(".*.tmp")) and not list(folder.glob(".*.bak"))
    assert len(model.paths) == (2 if action in {"fail", "retry"} else 1)
    if action != "retry":
        assert {ext: path.read_bytes() for ext, path in bundle.as_dict().items()} == before
    if action in {"stop", "cancel"}:
        assert cache.load(source, engine.client.signature) == {}


def test_job_finished_waits_for_upload_with_multiple_workers(tmp_path):
    entered, release, callback = threading.Event(), threading.Event(), threading.Event()

    class Upload:
        def upload(self, *_args):
            entered.set()
            assert release.wait(5)

    executor = DriveExecutionService(Upload(), max_workers=2)
    try:
        executor.submit("job", "file")
        assert entered.wait(5)
        executor.after_pending_uploads("job", callback.set)
        # Drain a task on the spare worker: an incorrectly queued FIFO
        # callback would already have executed by the time this completes.
        executor._executor.submit(lambda: None).result(timeout=5)
        assert not callback.is_set()
    finally:
        release.set()
        executor._executor.shutdown(wait=True)
    assert callback.is_set()


@pytest.mark.parametrize("activity", ["transcription", "manual_drive", "queued_drive", "unknown"])
def test_old_job_shutdown_is_cancelled_while_new_work_is_active(tmp_path, monkeypatch, activity):
    import src.api.routes as routes
    from src.services.desktop_state import ApplicationEventStore, DesktopCoordinator, ShutdownPhase
    from src.services.settings import SettingsPatch, ShutdownMode
    from src.services.transcription_runner import ExecutionInvariantError

    _, manager, job = make_done_job(tmp_path)
    job.batch_completed = True
    settings = SettingsManager(tmp_path / "s.json")
    settings.update(SettingsPatch(shutdown=ShutdownMode.IMMEDIATE))
    coordinator = DesktopCoordinator(settings, ApplicationEventStore())
    coordinator.job_finished(job)
    assert coordinator.state().phase == ShutdownPhase.READY_TO_SHUTDOWN

    def active():
        if activity == "unknown":
            raise ExecutionInvariantError("test unknown ownership")
        return "next-job" if activity == "transcription" else None

    monkeypatch.setattr(routes, "desktop_coordinator", coordinator)
    monkeypatch.setattr(routes, "job_manager", manager)
    monkeypatch.setattr(routes, "execution_service", SimpleNamespace(active_job_id=active))
    monkeypatch.setattr(routes, "drive_service", SimpleNamespace(active_upload=lambda: ("next-job", STEM) if activity == "manual_drive" else None))
    monkeypatch.setattr(routes, "drive_execution_service", SimpleNamespace(has_pending_work=lambda: activity == "queued_drive"))
    assert routes.get_shutdown_state().phase == ShutdownPhase.CANCELLED
    monkeypatch.setattr(routes.execution_service, "active_job_id", lambda: None)
    monkeypatch.setattr(routes.drive_service, "active_upload", lambda: None)
    monkeypatch.setattr(routes.drive_execution_service, "has_pending_work", lambda: False)
    assert routes.get_shutdown_state().phase == ShutdownPhase.CANCELLED
    coordinator.job_finished(job)
    assert routes.get_shutdown_state().phase == ShutdownPhase.READY_TO_SHUTDOWN


def test_same_job_terminal_callback_preserves_shutdown_until_future_returns(tmp_path, monkeypatch):
    import src.api.routes as routes
    from src.services.desktop_state import ApplicationEventStore, DesktopCoordinator, ShutdownPhase
    from src.services.settings import SettingsPatch, ShutdownMode

    _, manager, job = make_done_job(tmp_path)
    manager.mutate_job(job.job_id, lambda item: setattr(item, "batch_completed", True))
    settings = SettingsManager(tmp_path / "s.json")
    settings.update(SettingsPatch(shutdown=ShutdownMode.IMMEDIATE))
    coordinator = DesktopCoordinator(settings, ApplicationEventStore())
    coordinator.job_finished(manager.get_job(job.job_id))
    monkeypatch.setattr(routes, "desktop_coordinator", coordinator)
    monkeypatch.setattr(routes, "job_manager", manager)
    monkeypatch.setattr(routes, "execution_service", SimpleNamespace(active_job_id=lambda: job.job_id))
    monkeypatch.setattr(routes, "drive_service", SimpleNamespace(active_upload=lambda: None, has_in_flight=lambda: False))
    monkeypatch.setattr(routes, "drive_execution_service", SimpleNamespace(has_pending_work=lambda: False))
    assert routes.get_shutdown_state().phase == ShutdownPhase.INACTIVE
    assert coordinator.state().phase == ShutdownPhase.READY_TO_SHUTDOWN
    monkeypatch.setattr(routes.execution_service, "active_job_id", lambda: None)
    assert routes.get_shutdown_state().phase == ShutdownPhase.READY_TO_SHUTDOWN
