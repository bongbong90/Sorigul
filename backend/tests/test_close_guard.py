"""Issue #128 contracts: the desktop close guard reports critical work from
execution ownership -- the transcription runner Future (#126), the manual
Drive upload in flight, and queued/running automatic Drive Futures -- never
from persisted Job/Drive status alone.

Fakes only: no real Drive, no real engine. Event-driven, no sleeps.
"""

import threading

import pytest
from fastapi.testclient import TestClient

from src.domain.models import DriveFileState, FileStatus
from src.services.drive import DriveExecutionService, DriveUploadService
from test_global_single_run import WAIT, Harness

IDLE = {
    "protect_exit": False,
    "activity": "idle",
    "job_id": None,
    "current_file": None,
    "progress": None,
}


class BlockingDrive:
    """DriveUploadService whose real upload body is replaced by a gate."""

    def __init__(self, manager):
        self.service = DriveUploadService(manager, auth=None, settings=None)
        self.entered = threading.Event()
        self.release = threading.Event()
        self.service._upload = self._upload

    def _upload(self, job_id, file_id):
        self.entered.set()
        assert self.release.wait(WAIT)
        return DriveFileState()


@pytest.fixture
def guard(tmp_path, monkeypatch):
    import src.api.routes as routes
    from src.main import app

    h = Harness(tmp_path)
    drive = BlockingDrive(h.manager)
    drive_exec = DriveExecutionService(drive.service)
    monkeypatch.setattr(routes, "job_manager", h.manager)
    monkeypatch.setattr(routes, "execution_service", h.service)
    monkeypatch.setattr(routes, "drive_service", drive.service)
    monkeypatch.setattr(routes, "drive_execution_service", drive_exec)
    client = TestClient(app, base_url="http://127.0.0.1:8000")

    def read():
        response = client.get("/api/desktop/close-guard")
        assert response.status_code == 200
        return response.json()

    return read, h, drive, drive_exec, client, routes


def test_idle_is_not_protected(guard):
    read, *_ = guard
    assert read() == IDLE


def test_transcription_future_protects_even_while_job_is_still_waiting(guard):
    read, h, *_ = guard
    entered, gate = threading.Event(), threading.Event()
    real_run = h.runner.run

    def gated_run(job_id, token):
        entered.set()
        assert gate.wait(WAIT)
        return real_run(job_id, token)

    h.runner.run = gated_run
    a = h.job("폴더A")
    assert h.service.start(a.job_id) and entered.wait(WAIT)
    assert h.manager.get_job(a.job_id).status == FileStatus.WAITING
    body = read()
    assert body["protect_exit"] is True and body["activity"] == "transcription"
    assert body["job_id"] == a.job_id

    gate.set()
    assert h.engines[a.job_id].entered.wait(WAIT)
    body = read()
    assert body["protect_exit"] is True and body["current_file"] == "A.mp3"
    h.engines[a.job_id].release.set()
    h.future(a.job_id).result(timeout=WAIT)
    assert read() == IDLE


def test_terminal_persisted_but_runner_not_returned_is_protected(tmp_path, guard, monkeypatch):
    read, _, _, _, _, routes = guard
    persisted, hold = threading.Event(), threading.Event()

    def finished(_job):
        persisted.set()
        assert hold.wait(WAIT)

    (tmp_path / "late").mkdir()
    h = Harness(tmp_path / "late", job_finished_callback=finished)
    monkeypatch.setattr(routes, "job_manager", h.manager)
    monkeypatch.setattr(routes, "execution_service", h.service)
    a = h.job("폴더A")
    assert h.service.start(a.job_id)
    h.engines[a.job_id].release.set()
    assert persisted.wait(WAIT)
    assert h.manager.get_job(a.job_id).status == FileStatus.DONE
    assert read()["protect_exit"] is True

    hold.set()
    h.future(a.job_id).result(timeout=WAIT)
    assert read() == IDLE


@pytest.mark.parametrize("action", ["stop", "cancel"])
def test_requested_stop_or_cancel_stays_protected_until_runner_returns(guard, action):
    read, h, _, _, client, _ = guard
    a = h.job("폴더A")
    assert h.service.start(a.job_id) and h.engines[a.job_id].entered.wait(WAIT)
    assert client.post(f"/api/jobs/{a.job_id}/action", json={"action": action}).status_code == 200
    if action == "cancel":
        assert h.manager.get_job(a.job_id).status == FileStatus.CANCEL_REQUESTED
    assert read()["protect_exit"] is True

    h.engines[a.job_id].release.set()
    h.future(a.job_id).result(timeout=WAIT)
    assert read() == IDLE


def test_manual_drive_upload_in_flight_is_protected(guard):
    read, h, drive, *_ = guard
    a = h.job("폴더A")
    worker = threading.Thread(target=drive.service.upload, args=(a.job_id, "A"))
    worker.start()
    assert drive.entered.wait(WAIT)
    body = read()
    assert body == {
        "protect_exit": True,
        "activity": "drive",
        "job_id": a.job_id,
        "current_file": "A.mp3",
        "progress": None,
    }
    drive.release.set()
    worker.join(WAIT)
    assert read() == IDLE


def test_queued_background_drive_future_is_protected(guard):
    read, h, drive, drive_exec, *_ = guard
    a = h.job("폴더A")
    b = h.job("폴더B")
    assert drive_exec.submit(a.job_id, "A")
    assert drive.entered.wait(WAIT)
    assert drive_exec.submit(b.job_id, "A")  # queued behind the single worker
    assert read()["activity"] == "drive"

    finished = threading.Event()
    drive_exec.after_pending_uploads(b.job_id, finished.set)
    drive.release.set()
    assert finished.wait(WAIT)
    assert not drive_exec.has_pending_work()
    assert read() == IDLE


def test_background_drive_pending_before_upload_starts_is_protected(guard):
    read, h, drive, drive_exec, *_ = guard
    a = h.job("폴더A")
    blocker, release = threading.Event(), threading.Event()
    drive_exec._executor.submit(lambda: (blocker.set(), release.wait(WAIT)))
    assert blocker.wait(WAIT)
    assert drive_exec.submit(a.job_id, "A")
    assert not drive.service.has_in_flight()
    body = read()
    assert body["protect_exit"] is True and body["activity"] == "drive" and body["job_id"] is None
    release.set()
    assert drive.entered.wait(WAIT)
    drive.release.set()
    done = threading.Event()
    drive_exec.after_pending_uploads(a.job_id, done.set)
    assert done.wait(WAIT)
    assert read() == IDLE


def test_transcription_and_drive_together_stay_protected_until_both_end(guard):
    read, h, drive, drive_exec, *_ = guard
    a = h.job("폴더A")
    b = h.job("폴더B")
    assert h.service.start(a.job_id) and h.engines[a.job_id].entered.wait(WAIT)
    assert drive_exec.submit(b.job_id, "A") and drive.entered.wait(WAIT)
    assert read()["activity"] == "transcription", "transcription is the primary reason"

    h.engines[a.job_id].release.set()
    h.future(a.job_id).result(timeout=WAIT)
    assert read()["activity"] == "drive"

    done = threading.Event()
    drive_exec.after_pending_uploads(b.job_id, done.set)
    drive.release.set()
    assert done.wait(WAIT)
    assert read() == IDLE


def test_close_guard_discloses_no_path_token_or_remote_id(guard):
    read, h, drive, *_ = guard
    a = h.job("비밀폴더")
    job = h.manager.get_job(a.job_id)
    job.drive["A"] = DriveFileState(remote_file_ids={"txt": "REMOTE-SECRET-ID"})
    h.manager.update_job(job)
    assert h.service.start(a.job_id) and h.engines[a.job_id].entered.wait(WAIT)
    body = read()
    assert set(body) == set(IDLE)
    text = str(body)
    for secret in (a.folder, "비밀폴더", "REMOTE-SECRET-ID", "token", "base_url"):
        assert secret not in text, secret
    h.engines[a.job_id].release.set()
    h.future(a.job_id).result(timeout=WAIT)


def test_close_guard_is_read_only(guard):
    read, h, *_ = guard
    a = h.job("폴더A")
    before = h.manager.get_job(a.job_id).model_dump()
    read()
    assert h.manager.get_job(a.job_id).model_dump() == before
    assert a.job_id not in h.service._futures
