"""Issue #110: completion-notification "폴더 열기" intent boundary.

The toast frontend only ever holds an opaque job_id. The backend resolves the
folder from the stored Job and validates it before the Rust command opens
Explorer. Settings semantics for FILE_COMPLETED / JOB_COMPLETED are unchanged.
"""

from fastapi.testclient import TestClient

from src.domain.models import FileStatus
from src.services.desktop_state import ApplicationEventStore, DesktopCoordinator
from src.services.job_manager import JobManager
from src.services.settings import SettingsManager, SettingsPatch

ROUTE = "/api/desktop/jobs/{job_id}/open-folder-intent"


def _client(tmp_path, monkeypatch):
    import src.api.routes as routes
    from src.main import app

    manager = JobManager(str(tmp_path / "jobs.json"))
    monkeypatch.setattr(routes, "job_manager", manager)
    return TestClient(app), manager


def test_valid_job_returns_backend_resolved_folder_intent(tmp_path, monkeypatch):
    client, manager = _client(tmp_path, monkeypatch)
    folder = tmp_path / "전사자료" / "개념완성_민법"
    folder.mkdir(parents=True)
    job = manager.create_job(str(folder), ["one"])

    response = client.post(ROUTE.format(job_id=job.job_id))

    assert response.status_code == 200
    assert response.json() == {
        "action": "OPEN_FOLDER",
        "folder": str(folder.resolve()),
        "item_filename": None,
    }


def test_missing_job_is_404(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)

    response = client.post(ROUTE.format(job_id="00000000-0000-0000-0000-000000000000"))

    assert response.status_code == 404
    assert "folder" not in response.json()


def test_deleted_job_folder_is_explicit_4xx_without_path(tmp_path, monkeypatch):
    client, manager = _client(tmp_path, monkeypatch)
    folder = tmp_path / "moved-away"
    folder.mkdir()
    job = manager.create_job(str(folder), ["one"])
    folder.rmdir()

    response = client.post(ROUTE.format(job_id=job.job_id))

    assert response.status_code == 410
    assert str(tmp_path) not in response.text


def test_job_folder_replaced_by_file_is_rejected(tmp_path, monkeypatch):
    client, manager = _client(tmp_path, monkeypatch)
    folder = tmp_path / "was-a-folder"
    folder.mkdir()
    job = manager.create_job(str(folder), ["one"])
    folder.rmdir()
    folder.write_text("not a folder", encoding="utf-8")

    response = client.post(ROUTE.format(job_id=job.job_id))

    assert response.status_code == 410


def test_endpoint_accepts_no_caller_supplied_path(tmp_path, monkeypatch):
    """The only input is the job_id path parameter: no body, no query."""
    client, manager = _client(tmp_path, monkeypatch)
    from src.main import app

    operation = app.openapi()["paths"][ROUTE]["post"]
    assert "requestBody" not in operation
    assert [(p["name"], p["in"]) for p in operation["parameters"]] == [("job_id", "path")]

    job_folder = tmp_path / "job"
    job_folder.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    job = manager.create_job(str(job_folder), ["one"])
    response = client.post(
        ROUTE.format(job_id=job.job_id),
        params={"folder": str(other)},
        json={"folder": str(other)},
    )
    assert response.status_code == 200
    assert response.json()["folder"] == str(job_folder.resolve())


def _coordinator(tmp_path, file_complete, job_complete):
    settings = SettingsManager(tmp_path / "settings.json")
    settings.update(
        SettingsPatch.model_validate(
            {"notifications": {"file_complete": file_complete, "job_complete": job_complete}}
        )
    )
    events = ApplicationEventStore()
    return DesktopCoordinator(settings, events), events, JobManager(str(tmp_path / "jobs.json"))


def _finished(jobs):
    job = jobs.create_job("folder", ["one"])
    job.status = FileStatus.DONE
    job.files["one"] = FileStatus.DONE
    job.done_files = 1
    return job


def _intents(events):
    return [event.desktop_intent for event in events.list() if event.desktop_intent]


def test_notification_settings_both_enabled_emit_opaque_completion_events(tmp_path):
    coordinator, events, jobs = _coordinator(tmp_path, True, True)
    job = _finished(jobs)
    coordinator.file_completed(job.job_id, "one", "one.mp3")
    coordinator.job_finished(job)

    completion = [e for e in events.list() if e.desktop_intent in {"FILE_COMPLETED", "JOB_COMPLETED"}]
    assert [e.desktop_intent for e in completion] == ["FILE_COMPLETED", "JOB_COMPLETED"]
    assert all(e.job_id == job.job_id for e in completion)
    assert completion[0].file_id == "one"
    # The event carries identities only; the job folder is never in it.
    assert all("folder" not in e.model_dump() for e in completion)


def test_file_notification_setting_off_suppresses_file_completed(tmp_path):
    coordinator, events, jobs = _coordinator(tmp_path, False, True)
    job = _finished(jobs)
    coordinator.file_completed(job.job_id, "one", "one.mp3")
    coordinator.job_finished(job)
    assert _intents(events) == ["JOB_COMPLETED"]


def test_job_notification_setting_off_suppresses_job_completed(tmp_path):
    coordinator, events, jobs = _coordinator(tmp_path, True, False)
    job = _finished(jobs)
    coordinator.file_completed(job.job_id, "one", "one.mp3")
    coordinator.job_finished(job)
    assert _intents(events) == ["FILE_COMPLETED"]
