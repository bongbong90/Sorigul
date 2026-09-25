"""Package B runtime contracts: stop/cancel acknowledgement, the output
commit boundary, Local Whisper's honest mid-call limitation, auto-Drive
isolation and bounded Drive I/O, and Job storage failure policy.

Every test uses temp fixtures and fakes only: no real Whisper model, no
real ffmpeg, no real Google API, no user MP3. Races are made deterministic
with injected callbacks and threading.Event -- never sleeps.
"""

import json
import socket
import threading
from pathlib import Path

import pytest
from fastapi import HTTPException

from src.domain.models import DriveAuthState, DriveStatus, FileStatus
from src.domain.transcription import CancellationToken, TranscriptionResult
from src.engines.local_whisper import LocalWhisperEngine
from src.services.desktop_state import ApplicationEventStore, DesktopCoordinator
from src.services.drive import (
    DRIVE_HTTP_TIMEOUT_SECONDS,
    DRIVE_NETWORK_FAILURE_MESSAGE,
    DriveError,
    DriveExecutionService,
    DriveUploadService,
    GoogleDriveClient,
    GoogleOAuthService,
    build_authorized_http,
)
from src.services.job_manager import JobManager, JobStorageError
from src.services.output_bundle import BundlePaths, OutputBundleValidator, OutputBundleWriter
from src.services.settings import SettingsManager
from src.services.transcription_runner import BackgroundExecutionService, TranscriptionRunner

WAIT = 5  # generous upper bound for Event waits; never used as a sleep


@pytest.fixture
def routes():
    # Imported at test time, after conftest redirected LOCALAPPDATA to a
    # pytest-owned temp root -- never at collection time.
    import src.api.routes as routes_module

    return routes_module


def result_for(name):
    return TranscriptionResult.from_engine_payload(
        {"text": f"{name} 새 결과", "segments": [{"start": 0, "end": 1, "text": f"{name} 새 결과"}]}
    )


class ImmediateEngine:
    def __init__(self):
        self.calls = []

    def transcribe(self, source_path, token, event_callback, progress_callback):
        self.calls.append(source_path.stem)
        return result_for(source_path.stem)


def make_folder(tmp_path, names, old_bundle_for=()):
    folder = tmp_path / "전사자료"
    folder.mkdir()
    for name in names:
        (folder / f"{name}.mp3").write_bytes(b"fake-mp3")
    for name in old_bundle_for:
        paths = BundlePaths.final_for(folder / f"{name}.mp3")
        paths.txt.write_text("old text", encoding="utf-8")
        paths.json.write_text('{"text":"old text","segments":[]}', encoding="utf-8")
        paths.srt.write_text("", encoding="utf-8")
    return folder


def staged_leftovers(folder):
    return [p.name for p in folder.iterdir() if p.name.endswith((".tmp", ".bak"))]


def terminal_job_events(job):
    return [e.message for e in job.events if e.category == "Job" and e.message.startswith("Job ")]


# -- Output commit boundary (AUD-RUN-001) --------------------------------------


class RequestOnStagedValidation(OutputBundleValidator):
    """Fires the request right after the staged bundle validated -- i.e. the
    last instant before promotion would start."""

    def __init__(self, request):
        self.request = request
        self.calls = 0

    def validate(self, paths):
        super().validate(paths)
        self.calls += 1
        if self.calls == 1:
            self.request()


@pytest.mark.parametrize("cancel", [False, True], ids=["stop", "cancel"])
def test_request_before_promotion_preserves_old_bundle_and_ends_job(tmp_path, cancel):
    folder = make_folder(tmp_path, ["A", "B"], old_bundle_for=["A"])
    manager = JobManager(str(tmp_path / "runtime" / "jobs.json"))
    job = manager.create_job(str(folder), ["A", "B"], force_retranscribe=True)
    token = CancellationToken()
    request = token.request_cancel if cancel else token.request_stop
    completed = []
    runner = TranscriptionRunner(
        manager,
        lambda _job: ImmediateEngine(),
        output_writer=OutputBundleWriter(validator=RequestOnStagedValidation(request)),
        file_completed_callback=lambda *args: completed.append(args),
    )

    runner.run(job.job_id, token)

    finished = manager.get_job(job.job_id)
    old = BundlePaths.final_for(folder / "A.mp3")
    assert old.txt.read_text(encoding="utf-8") == "old text"
    assert json.loads(old.json.read_text(encoding="utf-8"))["text"] == "old text"
    assert staged_leftovers(folder) == []
    assert not (folder / "B.txt").exists()
    assert completed == []
    if cancel:
        assert finished.status == FileStatus.CANCELLED
        assert finished.files == {"A": FileStatus.CANCELLED, "B": FileStatus.CANCELLED}
        assert terminal_job_events(finished) == ["Job 취소됨"]
    else:
        assert finished.status == FileStatus.STOPPED
        assert finished.files == {"A": FileStatus.STOPPED, "B": FileStatus.WAITING}
        assert terminal_job_events(finished) == ["Job 중지됨"]
    assert finished.batch_completed is False


class RequestAfterCommitWriter:
    """Delegates to the real writer, then fires the request after commit()
    returned -- the bundle is on disk before the runner sees the request."""

    def __init__(self, request):
        self.inner = OutputBundleWriter()
        self.request = request

    def commit(self, source_path, result, **kwargs):
        paths = self.inner.commit(source_path, result, **kwargs)
        self.request()
        return paths


def writer_requesting_during_promotion(request):
    fired = []

    def replace(src: Path, dst: Path):
        src.replace(dst)
        # First staged file installed: promotion is mid-flight.
        if src.name.endswith(".txt.tmp") and not fired:
            fired.append(True)
            request()

    return OutputBundleWriter(replace=replace)


@pytest.mark.parametrize("cancel", [False, True], ids=["stop", "cancel"])
@pytest.mark.parametrize("moment", ["during-promotion", "after-promotion"])
def test_request_during_or_after_promotion_keeps_committed_file_done(tmp_path, cancel, moment):
    folder = make_folder(tmp_path, ["A", "B"], old_bundle_for=["A"])
    manager = JobManager(str(tmp_path / "runtime" / "jobs.json"))
    job = manager.create_job(str(folder), ["A", "B"], force_retranscribe=True)
    token = CancellationToken()
    request = token.request_cancel if cancel else token.request_stop
    writer = (
        writer_requesting_during_promotion(request)
        if moment == "during-promotion"
        else RequestAfterCommitWriter(request)
    )
    engine = ImmediateEngine()
    completed = []
    runner = TranscriptionRunner(
        manager,
        lambda _job: engine,
        output_writer=writer,
        file_completed_callback=lambda *args: completed.append(args),
    )

    runner.run(job.job_id, token)

    finished = manager.get_job(job.job_id)
    new = BundlePaths.final_for(folder / "A.mp3")
    OutputBundleValidator().validate(new)
    assert new.txt.read_text(encoding="utf-8") == "A 새 결과"
    assert staged_leftovers(folder) == []
    assert engine.calls == ["A"], "no further file may start after the request"
    assert finished.files["A"] == FileStatus.DONE
    assert completed == [], "auto-Drive/completion callback must not start with a request pending"
    if cancel:
        assert finished.status == FileStatus.CANCELLED
        assert finished.files["B"] == FileStatus.CANCELLED
        assert terminal_job_events(finished) == ["Job 취소됨"]
    else:
        assert finished.status == FileStatus.STOPPED
        assert finished.files["B"] == FileStatus.WAITING
        assert terminal_job_events(finished) == ["Job 중지됨"]
    assert finished.done_files == 1


def test_before_promotion_failure_discards_staged_files_only(tmp_path):
    source = tmp_path / "lecture.mp3"
    source.write_bytes(b"fake")
    old = BundlePaths.final_for(source)
    old.txt.write_text("old text", encoding="utf-8")
    old.json.write_text('{"text":"old text","segments":[]}', encoding="utf-8")
    old.srt.write_text("", encoding="utf-8")

    from src.domain.transcription import StopRequested

    def refuse():
        raise StopRequested()

    with pytest.raises(StopRequested):
        OutputBundleWriter().commit(source, result_for("x"), before_promotion=refuse)

    assert old.txt.read_text(encoding="utf-8") == "old text"
    assert staged_leftovers(tmp_path) == []


# -- Terminal Job events (AUD-JOB-002) -------------------------------------------


def test_terminal_events_match_done_and_failed(tmp_path):
    folder = make_folder(tmp_path, ["A", "B"])
    manager = JobManager(str(tmp_path / "runtime" / "jobs.json"))
    done_job = manager.create_job(str(folder), ["A"])
    TranscriptionRunner(manager, lambda _job: ImmediateEngine()).run(done_job.job_id, CancellationToken())
    assert terminal_job_events(manager.get_job(done_job.job_id)) == ["Job 완료"]

    from src.domain.transcription import EngineError, ErrorCategory

    class FailingEngine:
        def transcribe(self, *args):
            raise EngineError("X", ErrorCategory.INPUT, "실패")

    failed_job = manager.create_job(str(folder), ["B"])
    TranscriptionRunner(manager, lambda _job: FailingEngine()).run(failed_job.job_id, CancellationToken())
    finished = manager.get_job(failed_job.job_id)
    assert finished.status == FileStatus.FAILED
    assert terminal_job_events(finished) == ["Job 실패"]


def test_completion_callback_failure_never_fails_a_committed_file(tmp_path):
    folder = make_folder(tmp_path, ["A"])
    manager = JobManager(str(tmp_path / "runtime" / "jobs.json"))
    job = manager.create_job(str(folder), ["A"])

    def exploding_callback(*_args):
        raise RuntimeError("drive scheduling exploded")

    TranscriptionRunner(
        manager, lambda _job: ImmediateEngine(), file_completed_callback=exploding_callback
    ).run(job.job_id, CancellationToken())

    finished = manager.get_job(job.job_id)
    assert finished.files["A"] == FileStatus.DONE
    assert finished.status == FileStatus.DONE


# -- Stop/Cancel acknowledgement + Local Whisper blocking call (AUD-LOC-001) -----


class BlockingModel:
    """Fake Whisper model whose transcribe() blocks like a long native call."""

    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event()

    def transcribe(self, path, **options):
        self.entered.set()
        assert self.release.wait(WAIT), "test never released the blocking call"
        return {"text": "늦게 끝난 결과", "segments": [{"start": 0, "end": 1, "text": "늦게 끝난 결과"}]}


class FakeCuda:
    def is_available(self):
        return False


class FakeTorch:
    cuda = FakeCuda()


class FakeWhisper:
    def __init__(self, model):
        self.model = model

    def load_model(self, name, device):
        return self.model


@pytest.fixture
def blocking_local_setup(tmp_path, monkeypatch, routes):
    folder = make_folder(tmp_path, ["A", "B"])
    manager = JobManager(str(tmp_path / "runtime" / "jobs.json"))
    model = BlockingModel()
    engine = LocalWhisperEngine(
        whisper_loader=lambda: FakeWhisper(model),
        torch_loader=lambda: FakeTorch(),
    )
    service = BackgroundExecutionService(TranscriptionRunner(manager, lambda _job: engine), max_workers=1)
    monkeypatch.setattr(routes, "job_manager", manager)
    monkeypatch.setattr(routes, "execution_service", service)
    job = manager.create_job(str(folder), ["A", "B"])
    assert service.start(job.job_id)
    future = service._futures[job.job_id]
    assert model.entered.wait(WAIT)
    return folder, manager, service, model, job, future


def test_stop_during_blocking_local_call_is_only_a_request_until_observed(blocking_local_setup, routes):
    folder, manager, service, model, job, future = blocking_local_setup

    response = routes.job_action(job.job_id, routes.JobActionRequest(action="stop"))
    again = routes.job_action(job.job_id, routes.JobActionRequest(action="stop"))

    # Acknowledged, but the Job still reports the truth: still transcribing.
    assert response.status == FileStatus.TRANSCRIBING
    assert response.files["A"] == FileStatus.TRANSCRIBING
    assert [e.message for e in again.events].count("중지 요청됨") == 1
    assert FileStatus.STOPPED not in again.files.values()
    # Retry cannot start a new run before the stop is actually persisted.
    with pytest.raises(HTTPException) as caught:
        routes.job_action(job.job_id, routes.JobActionRequest(action="retry"))
    assert caught.value.status_code == 409

    model.release.set()
    future.result(timeout=WAIT)

    finished = manager.get_job(job.job_id)
    assert finished.status == FileStatus.STOPPED
    assert finished.files == {"A": FileStatus.STOPPED, "B": FileStatus.WAITING}
    assert not (folder / "A.txt").exists(), "a requested run must never commit output"
    assert staged_leftovers(folder) == []
    assert terminal_job_events(finished) == ["Job 중지됨"]
    assert not service.is_active(job.job_id)
    retried = routes.job_action(job.job_id, routes.JobActionRequest(action="retry"))
    assert retried.status == FileStatus.WAITING


def test_cancel_during_blocking_local_call_is_only_a_request_until_observed(blocking_local_setup, routes):
    folder, manager, service, model, job, future = blocking_local_setup

    response = routes.job_action(job.job_id, routes.JobActionRequest(action="cancel"))

    assert response.status == FileStatus.CANCEL_REQUESTED
    assert response.files == {"A": FileStatus.CANCEL_REQUESTED, "B": FileStatus.WAITING}
    assert FileStatus.CANCELLED not in response.files.values()
    with pytest.raises(HTTPException) as caught:
        routes.job_action(job.job_id, routes.JobActionRequest(action="retry"))
    assert caught.value.status_code == 409

    model.release.set()
    future.result(timeout=WAIT)

    finished = manager.get_job(job.job_id)
    assert finished.status == FileStatus.CANCELLED
    assert finished.files == {"A": FileStatus.CANCELLED, "B": FileStatus.CANCELLED}
    assert not (folder / "A.txt").exists()
    assert staged_leftovers(folder) == []
    assert terminal_job_events(finished) == ["Job 취소됨"]


def test_request_after_terminal_persisted_is_not_acknowledged(tmp_path):
    folder = make_folder(tmp_path, ["A"])
    manager = JobManager(str(tmp_path / "runtime" / "jobs.json"))
    service = BackgroundExecutionService(TranscriptionRunner(manager, lambda _job: ImmediateEngine()))
    job = manager.create_job(str(folder), ["A"])
    token = CancellationToken()
    service._tokens[job.job_id] = token  # a run that is still registered...
    TranscriptionRunner(manager, lambda _job: ImmediateEngine()).run(job.job_id, token)  # ...but finished

    assert service.request_stop(job.job_id) is False
    assert service.request_cancel(job.job_id) is False
    assert manager.get_job(job.job_id).status == FileStatus.DONE


# -- Drive: isolation from the transcription worker (AUD-DRV-001) ----------------


class HangingDriveClient:
    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event()
        self.created = []

    def find_or_create_folder(self, parent_id, name):
        return f"{parent_id}/{name}"

    def find_file(self, parent_id, name):
        return None

    def create_file(self, parent_id, name, local_path):
        self.entered.set()
        assert self.release.wait(WAIT)
        self.created.append(name)
        return f"id-{name}"

    def update_file(self, file_id, name, local_path):
        return file_id


class FakeAuth:
    def __init__(self, client):
        self.client = client

    @property
    def state(self):
        return DriveAuthState.CONNECTED

    def ensure_client(self):
        return self.client


STEM = "개념완성_민법_8주차_4강"


def test_hanging_auto_drive_upload_does_not_hold_transcription_completion(tmp_path, monkeypatch, routes):
    folder = make_folder(tmp_path, [STEM])
    manager = JobManager(str(tmp_path / "runtime" / "jobs.json"))
    settings = SettingsManager(tmp_path / "settings.json")
    client = HangingDriveClient()
    drive_exec = DriveExecutionService(DriveUploadService(manager, FakeAuth(client), settings))
    coordinator = DesktopCoordinator(settings, ApplicationEventStore())
    finished_jobs = []
    monkeypatch.setattr(routes, "job_manager", manager)
    monkeypatch.setattr(routes, "drive_execution_service", drive_exec)
    monkeypatch.setattr(routes, "desktop_coordinator", coordinator)
    monkeypatch.setattr(coordinator, "job_finished", lambda job: finished_jobs.append(job.status))
    job = manager.create_job(str(folder), [STEM], upload_to_drive=True)

    runner = TranscriptionRunner(
        manager,
        lambda _job: ImmediateEngine(),
        file_completed_callback=routes.handle_file_completed,
        job_finished_callback=routes.handle_job_finished,
    )
    runner.run(job.job_id, CancellationToken())  # returns while Drive still hangs

    assert client.entered.wait(WAIT)
    mid = manager.get_job(job.job_id)
    assert mid.status == FileStatus.DONE
    assert mid.files[STEM] == FileStatus.DONE
    assert mid.drive[STEM].status == DriveStatus.UPLOADING
    assert drive_exec.submit(job.job_id, STEM) is False, "duplicate in-flight upload"
    assert finished_jobs == [], "job-finished handling waits for this Job's pending uploads"

    client.release.set()
    drive_exec._executor.shutdown(wait=True)

    done = manager.get_job(job.job_id)
    assert done.drive[STEM].status == DriveStatus.DONE
    assert sorted(client.created) == sorted([f"{STEM}.txt", f"{STEM}.json", f"{STEM}.srt"])
    assert finished_jobs == [FileStatus.DONE]


def test_drive_executor_contains_unexpected_upload_errors(tmp_path):
    folder = make_folder(tmp_path, [STEM])
    manager = JobManager(str(tmp_path / "runtime" / "jobs.json"))
    job = manager.create_job(str(folder), [STEM])
    job.files[STEM] = FileStatus.DONE
    job.status = FileStatus.DONE
    manager.update_job(job)

    class ExplodingUploadService(DriveUploadService):
        def _upload(self, job_id, file_id):
            raise RuntimeError("unexpected")

    service = ExplodingUploadService(manager, FakeAuth(None), SettingsManager(tmp_path / "s.json"))
    drive_exec = DriveExecutionService(service)
    assert drive_exec.submit(job.job_id, STEM)
    drive_exec._executor.shutdown(wait=True)

    persisted = manager.get_job(job.job_id)
    assert persisted.drive[STEM].status == DriveStatus.FAILED
    assert persisted.files[STEM] == FileStatus.DONE
    assert persisted.status == FileStatus.DONE
    assert not drive_exec.in_flight(job.job_id, STEM)


class TimingOutDriveClient(HangingDriveClient):
    def __init__(self):
        super().__init__()
        self.fail = True
        self.release.set()

    def create_file(self, parent_id, name, local_path):
        if self.fail:
            raise socket.timeout("timed out")
        return super().create_file(parent_id, name, local_path)


def test_drive_timeout_is_drive_failed_local_done_and_retryable_without_mp3(tmp_path):
    folder = make_folder(tmp_path, [STEM])
    runner_manager = JobManager(str(tmp_path / "runtime" / "jobs.json"))
    job = runner_manager.create_job(str(folder), [STEM])
    TranscriptionRunner(runner_manager, lambda _job: ImmediateEngine()).run(job.job_id, CancellationToken())
    client = TimingOutDriveClient()
    service = DriveUploadService(runner_manager, FakeAuth(client), SettingsManager(tmp_path / "s.json"))

    failed = service.upload(job.job_id, STEM)

    persisted = runner_manager.get_job(job.job_id)
    assert failed.status == DriveStatus.FAILED
    assert failed.error == DRIVE_NETWORK_FAILURE_MESSAGE
    assert persisted.files[STEM] == FileStatus.DONE
    assert persisted.status == FileStatus.DONE

    (folder / f"{STEM}.mp3").unlink()  # the temp fixture's MP3, not a user file
    client.fail = False
    assert service.retry(job.job_id, STEM).status == DriveStatus.DONE


def test_concurrent_upload_of_same_file_is_rejected(tmp_path):
    folder = make_folder(tmp_path, [STEM])
    manager = JobManager(str(tmp_path / "runtime" / "jobs.json"))
    job = manager.create_job(str(folder), [STEM])
    TranscriptionRunner(manager, lambda _job: ImmediateEngine()).run(job.job_id, CancellationToken())
    client = HangingDriveClient()
    service = DriveUploadService(manager, FakeAuth(client), SettingsManager(tmp_path / "s.json"))
    worker = threading.Thread(target=service.upload, args=(job.job_id, STEM))
    worker.start()
    assert client.entered.wait(WAIT)

    with pytest.raises(DriveError) as caught:
        service.upload(job.job_id, STEM)
    assert caught.value.code == "DRIVE_UPLOAD_IN_PROGRESS"

    client.release.set()
    worker.join(WAIT)
    assert manager.get_job(job.job_id).drive[STEM].status == DriveStatus.DONE


# -- Drive: bounded network I/O -------------------------------------------------


class FakeCredentials:
    def before_request(self, *_args, **_kwargs):
        pass


def test_drive_transport_has_explicit_per_request_timeout():
    http = build_authorized_http(FakeCredentials())
    assert DRIVE_HTTP_TIMEOUT_SECONDS == 60.0
    assert http.http.timeout == 60.0


def test_drive_transport_request_times_out_against_a_silent_server():
    # A local listener that completes the TCP handshake but never answers:
    # stands in for a hanging Google endpoint without touching the network.
    silent = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    silent.bind(("127.0.0.1", 0))
    silent.listen(1)
    port = silent.getsockname()[1]
    try:
        http = build_authorized_http(FakeCredentials(), timeout_seconds=0.3)
        with pytest.raises((TimeoutError, socket.timeout, OSError)):
            http.request(f"http://127.0.0.1:{port}/drive/v3/files")
    finally:
        silent.close()


def test_ensure_client_builds_drive_service_on_the_bounded_transport(tmp_path, monkeypatch):
    token_path = tmp_path / "token.json"
    token_path.write_text("{}", encoding="utf-8")

    class ValidCredentials(FakeCredentials):
        expired = False
        refresh_token = None
        valid = True

    monkeypatch.setattr(
        "google.oauth2.credentials.Credentials.from_authorized_user_file",
        lambda *_args, **_kwargs: ValidCredentials(),
    )
    captured = {}

    def fake_build(service_name, version, **kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr("googleapiclient.discovery.build", fake_build)

    GoogleOAuthService(tmp_path / "client.json", token_path).ensure_client()

    assert "credentials" not in captured
    assert captured["http"].http.timeout == DRIVE_HTTP_TIMEOUT_SECONDS


def test_media_download_loop_has_an_overall_deadline(monkeypatch):
    class NeverDoneDownload:
        def __init__(self, fh, request):
            self.chunks = 0

        def next_chunk(self):
            self.chunks += 1
            return None, False

    monkeypatch.setattr("googleapiclient.http.MediaIoBaseDownload", NeverDoneDownload)

    class FakeFiles:
        def get_media(self, fileId):
            return object()

    class FakeService:
        def files(self):
            return FakeFiles()

    ticks = iter(range(0, 10_000, 10))
    client = GoogleDriveClient(FakeService(), download_deadline_seconds=100, clock=lambda: next(ticks))

    with pytest.raises(DriveError) as caught:
        client.read_text_file("metadata-file")
    assert caught.value.code == "DRIVE_TIMEOUT"
    assert caught.value.user_message == DRIVE_NETWORK_FAILURE_MESSAGE


# -- Job storage failure policy (AUD-JOB-003) -------------------------------------


def seeded_storage(tmp_path):
    storage = tmp_path / "runtime" / "jobs.json"
    manager = JobManager(str(storage))
    job = manager.create_job("folder", ["f1"])
    return storage, manager, job, storage.read_bytes()


def test_malformed_jobs_json_is_quarantined(tmp_path):
    storage = tmp_path / "jobs.json"
    storage.write_text("{not json", encoding="utf-8")

    manager = JobManager(str(storage))

    assert manager.jobs == {}
    quarantined = list(tmp_path.glob("jobs.corrupt.*.json"))
    assert len(quarantined) == 1
    assert quarantined[0].read_text(encoding="utf-8") == "{not json"


def test_read_oserror_is_explicit_and_never_quarantines_or_resets(tmp_path, monkeypatch):
    storage, _, _, original = seeded_storage(tmp_path)
    real_read_bytes = Path.read_bytes

    def denied(self):
        if self == storage:
            raise PermissionError("access denied")
        return real_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", denied)

    with pytest.raises(JobStorageError) as caught:
        JobManager(str(storage))
    assert caught.value.code == "JOB_STORAGE_READ_FAILED"
    monkeypatch.undo()
    assert storage.read_bytes() == original
    assert list(storage.parent.glob("jobs.corrupt.*.json")) == []


def test_quarantine_rename_failure_is_explicit_and_keeps_the_file(tmp_path, monkeypatch):
    storage = tmp_path / "jobs.json"
    storage.write_text("{not json", encoding="utf-8")

    def refuse_rename(self, target):
        raise PermissionError("locked")

    monkeypatch.setattr(Path, "rename", refuse_rename)

    with pytest.raises(JobStorageError) as caught:
        JobManager(str(storage))
    assert caught.value.code == "JOB_STORAGE_QUARANTINE_FAILED"
    assert storage.read_text(encoding="utf-8") == "{not json"


def test_temp_write_failure_is_explicit_and_preserves_jobs_json(tmp_path, monkeypatch):
    storage, manager, job, original = seeded_storage(tmp_path)

    def failing_dump(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("src.services.job_manager.json.dump", failing_dump)

    with pytest.raises(JobStorageError) as caught:
        manager.mutate_job(job.job_id, lambda j: setattr(j, "status", FileStatus.DONE))
    assert caught.value.code == "JOB_STORAGE_WRITE_FAILED"
    assert storage.read_bytes() == original
    assert manager.get_job(job.job_id).status == FileStatus.WAITING, "memory must match disk"
    assert list(storage.parent.glob("*.tmp")) == []


def test_atomic_replace_failure_is_explicit_and_preserves_jobs_json(tmp_path, monkeypatch):
    storage, manager, job, original = seeded_storage(tmp_path)

    def failing_replace(self, target):
        raise PermissionError("replace refused")

    monkeypatch.setattr(Path, "replace", failing_replace)

    with pytest.raises(JobStorageError) as caught:
        manager.create_job("folder", ["f2"])
    assert caught.value.code == "JOB_STORAGE_WRITE_FAILED"
    monkeypatch.undo()
    assert storage.read_bytes() == original
    assert list(manager.jobs) == [job.job_id]
    assert list(storage.parent.glob("*.tmp")) == []
