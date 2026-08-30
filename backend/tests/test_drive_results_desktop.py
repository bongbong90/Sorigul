import json
from pathlib import Path

import pytest

from src.domain.models import DriveAuthState, DriveFileState, DriveStatus, FileStatus
from src.services.desktop_state import ApplicationEventStore, DesktopCoordinator, ShutdownPhase
from src.services.drive import DriveClassifier, DriveError, DriveUploadService
from src.services.job_manager import JobManager
from src.services.results import ResultsService
from src.services.settings import (
    RuntimeSettings,
    SettingsManager,
    SettingsPatch,
    ShutdownMode,
)


def make_bundle(folder: Path, stem: str, include_mp3: bool = True):
    if include_mp3:
        (folder / f"{stem}.mp3").write_bytes(b"mp3")
    (folder / f"{stem}.txt").write_text("한국어 전사 결과 " * 60, encoding="utf-8")
    (folder / f"{stem}.json").write_text(
        '{"text":"결과","segments":[{"start":0,"end":1,"text":"결과"}]}',
        encoding="utf-8",
    )
    (folder / f"{stem}.srt").touch()


class FakeDriveClient:
    def __init__(self, fail_name=None):
        self.folders = {}
        self.files = {}
        self.created = []
        self.updated = []
        self.fail_name = fail_name

    def find_or_create_folder(self, parent_id, name):
        key = (parent_id, name)
        if key not in self.folders:
            self.folders[key] = f"folder-{len(self.folders) + 1}"
        return self.folders[key]

    def find_file(self, parent_id, name):
        return self.files.get((parent_id, name))

    def create_file(self, parent_id, name, local_path):
        if name == self.fail_name:
            raise RuntimeError("fake failure")
        file_id = f"file-{len(self.files) + 1}"
        self.files[(parent_id, name)] = file_id
        self.created.append(name)
        return file_id

    def update_file(self, file_id, name, local_path):
        if name == self.fail_name:
            raise RuntimeError("fake failure")
        self.updated.append(name)
        return file_id


class FakeAuth:
    def __init__(self, client=None, state=DriveAuthState.CONNECTED, error=None):
        self.client = client
        self._state = state
        self.error = error

    @property
    def state(self):
        return self._state

    def ensure_client(self):
        if self.error:
            raise self.error
        return self.client

    def start(self):
        self._state = DriveAuthState.AUTHORIZING
        return {"authorization_url": "https://example.invalid", "state": "fake"}

    def complete(self, code):
        self._state = DriveAuthState.CONNECTED
        return self._state


def make_done_job(tmp_path, stem="개념완성_민법_8주차_4강"):
    folder = tmp_path / "전사자료"
    folder.mkdir()
    make_bundle(folder, stem)
    manager = JobManager(str(tmp_path / "runtime" / "jobs.json"))
    job = manager.create_job(str(folder), [stem])
    job.status = FileStatus.DONE
    job.files[stem] = FileStatus.DONE
    job.done_files = 1
    manager.update_job(job)
    return folder, manager, job


def test_drive_uploads_exact_three_then_updates_without_duplicates(tmp_path):
    _, manager, job = make_done_job(tmp_path)
    client = FakeDriveClient()
    settings = SettingsManager(tmp_path / "settings.json")
    service = DriveUploadService(manager, FakeAuth(client), settings)

    first = service.upload(job.job_id, next(iter(job.files)))
    second = service.retry(job.job_id, next(iter(job.files)))

    assert first.status == DriveStatus.DONE
    assert second.status == DriveStatus.DONE
    assert sorted(client.created) == sorted([
        "개념완성_민법_8주차_4강.txt",
        "개념완성_민법_8주차_4강.json",
        "개념완성_민법_8주차_4강.srt",
    ])
    assert len(client.files) == 3
    assert len(client.updated) == 3


def test_drive_failure_does_not_change_local_done_and_can_retry(tmp_path):
    folder, manager, job = make_done_job(tmp_path)
    stem = next(iter(job.files))
    client = FakeDriveClient(fail_name=f"{stem}.json")
    settings = SettingsManager(tmp_path / "settings.json")
    service = DriveUploadService(manager, FakeAuth(client), settings)

    result = service.upload(job.job_id, stem)

    persisted = manager.get_job(job.job_id)
    assert result.status == DriveStatus.FAILED
    assert persisted.status == FileStatus.DONE
    assert persisted.files[stem] == FileStatus.DONE
    assert (folder / f"{stem}.txt").exists()
    assert (folder / f"{stem}.json").exists()
    assert (folder / f"{stem}.srt").exists()
    client.fail_name = None
    assert service.retry(job.job_id, stem).status == DriveStatus.DONE


from src.domain.models import FileMetadata

def test_drive_new_job_metadata_source_of_truth(tmp_path):
    classifier = DriveClassifier()
    manager = JobManager(str(tmp_path / "runtime" / "jobs.json"))
    job = manager.create_job("folder", ["개념완성_민법_8주차_4강"])
    job.course = "사용자과정"
    job.subject = "사용자과목"
    job.stage = "2차"
    job.file_metadata["개념완성_민법_8주차_4강"] = FileMetadata(
        week="3", lesson="7", normalized_name="사용자과정_사용자과목_3주차_7강.mp3"
    )
    classification = classifier.classify(job, "개념완성_민법_8주차_4강", "2026 테스트루트")
    assert classification.course == "사용자과정"
    assert classification.subject == "사용자과목"
    assert classification.week == 3
    assert classification.lesson == 7
    assert classification.folders == (
        "2026 테스트루트",
        "전사자료",
        "사용자과정",
        "[2차] 사용자과목",
        "사용자과정_사용자과목_3주차",
    )


def test_drive_arbitrary_freetext_new_job(tmp_path):
    classifier = DriveClassifier()
    manager = JobManager(str(tmp_path / "runtime" / "jobs.json"))
    job = manager.create_job("folder", ["test.mp3"])
    job.course = "NewCourse"
    job.subject = "NewSubject"
    job.stage = "1차"
    job.file_metadata["test.mp3"] = FileMetadata(
        week="1", lesson="1", normalized_name="NewCourse_NewSubject_1주차_1강.mp3"
    )
    classification = classifier.classify(job, "test.mp3", "2026")
    assert classification.course == "NewCourse"
    assert classification.subject == "NewSubject"
    assert classification.folders[-1] == "NewCourse_NewSubject_1주차"


def test_drive_partial_metadata_guard(tmp_path):
    classifier = DriveClassifier()
    manager = JobManager(str(tmp_path / "runtime" / "jobs.json"))
    job = manager.create_job("folder", ["개념완성_민법_8주차_4강"])
    job.course = "과정만있음"
    # missing subject, stage, file_metadata
    with pytest.raises(DriveError, match="일부 메타데이터만 있는 Job은"):
        classifier.classify(job, "개념완성_민법_8주차_4강", "2026")


def test_drive_true_legacy_fallback(tmp_path):
    classifier = DriveClassifier()
    manager = JobManager(str(tmp_path / "runtime" / "jobs.json"))
    # No metadata at all. True legacy job.
    job = manager.create_job("folder", ["기본이론_공인중개사법_3주차_5강"])
    classification = classifier.classify(job, "기본이론_공인중개사법_3주차_5강", "2026")
    assert classification.course == "기본이론"
    assert classification.subject == "공인중개사법"
    assert classification.folders[-1] == "기본이론_중개사법_3주차"


def test_drive_legacy_non_standard_failure(tmp_path):
    classifier = DriveClassifier()
    manager = JobManager(str(tmp_path / "runtime" / "jobs.json"))
    job = manager.create_job("folder", ["원래 이름"])
    with pytest.raises(DriveError, match="표준 파일명에서"):
        classifier.classify(job, "원래 이름", "2026")


@pytest.mark.parametrize(
    ("auth_state", "error_code"),
    [
        (DriveAuthState.UNAUTHENTICATED, "DRIVE_AUTH_REQUIRED"),
        (DriveAuthState.REFRESH_FAILED, "DRIVE_TOKEN_REFRESH_FAILED"),
        (DriveAuthState.REAUTH_REQUIRED, "DRIVE_REAUTH_REQUIRED"),
    ],
)
def test_drive_auth_failure_states_are_isolated(tmp_path, auth_state, error_code):
    _, manager, job = make_done_job(tmp_path)
    stem = next(iter(job.files))
    auth = FakeAuth(
        state=auth_state,
        error=DriveError(error_code, "다시 연결해 주세요."),
    )
    settings = SettingsManager(tmp_path / "settings.json")
    result = DriveUploadService(manager, auth, settings).upload(job.job_id, stem)
    assert result.status == DriveStatus.AUTH_REQUIRED
    assert manager.get_job(job.job_id).status == FileStatus.DONE


def test_folders_refresh_filters_preview_full_and_unicode(tmp_path):
    folder = tmp_path / "전사자료"
    folder.mkdir()
    make_bundle(folder, "개념완성_민법_8주차_4강")
    (folder / "미완료.mp3").touch()
    make_bundle(folder, "결과만", include_mp3=False)
    service = ResultsService(preview_chars=20)

    all_result = service.scan(str(folder), "all")
    assert all_result.counts == {"all": 8, "complete": 1, "incomplete": 1, "results": 6}
    assert len(service.scan(str(folder), "complete").items) == 1
    assert len(service.scan(str(folder), "incomplete").items) == 1
    results = service.scan(str(folder), "results")
    assert len(results.items) == 6
    txt = next(item for item in results.items if item.filename == "개념완성_민법_8주차_4강.txt")
    preview = service.read_text(results.scan_id, txt.id)
    full = service.read_text(results.scan_id, txt.id, full=True)
    assert preview.truncated is True
    assert len(preview.text) == 20
    assert len(full.text) > len(preview.text)

    (folder / "외부추가.mp3").touch()
    assert service.scan(str(folder), "incomplete").counts["incomplete"] == 2
    (folder / "개념완성_민법_8주차_4강.txt").unlink()
    assert service.scan(str(folder), "complete").counts["complete"] == 0


def test_settings_corruption_atomic_save_and_shutdown_cancel(tmp_path):
    path = tmp_path / "runtime" / "settings.json"
    path.parent.mkdir()
    path.write_text("{bad", encoding="utf-8")
    manager = SettingsManager(path)
    assert manager.get() == RuntimeSettings()
    assert len(list(path.parent.glob("settings.corrupt.*.json"))) == 1

    settings = manager.update(SettingsPatch(shutdown=ShutdownMode.DELAY_15))
    assert settings.shutdown == ShutdownMode.DELAY_15
    events = ApplicationEventStore()
    coordinator = DesktopCoordinator(manager, events)
    jobs = JobManager(str(tmp_path / "jobs.json"))
    job = jobs.create_job("folder", ["one"])
    job.status = FileStatus.DONE
    job.batch_completed = True
    job.files["one"] = FileStatus.DONE
    job.done_files = 1
    coordinator.job_finished(job)
    assert coordinator.state().phase == ShutdownPhase.COUNTING_DOWN
    assert coordinator.cancel_shutdown().phase == ShutdownPhase.CANCELLED
    assert any(event.desktop_intent == "SHUTDOWN_CANCELLED" for event in events.list())


def _shutdown_env(tmp_path, shutdown_mode=ShutdownMode.DELAY_15):
    manager = SettingsManager(tmp_path / "settings.json")
    manager.update(SettingsPatch(shutdown=shutdown_mode))
    events = ApplicationEventStore()
    coordinator = DesktopCoordinator(manager, events)
    jobs = JobManager(str(tmp_path / "jobs.json"))
    return coordinator, jobs, events


def _finished_job(jobs, status, batch_completed, files, drive=None):
    job = jobs.create_job("folder", list(files.keys()))
    job.status = status
    job.batch_completed = batch_completed
    job.files.update(files)
    job.done_files = sum(state == FileStatus.DONE for state in job.files.values())
    job.failed_files = sum(state == FileStatus.FAILED for state in job.files.values())
    if drive:
        job.drive.update(drive)
    jobs.update_job(job)
    return job


def test_shutdown_countdown_allowed_for_full_success(tmp_path):
    coordinator, jobs, _ = _shutdown_env(tmp_path)
    job = _finished_job(
        jobs, FileStatus.DONE, True, {"a": FileStatus.DONE, "b": FileStatus.DONE}
    )

    coordinator.job_finished(job)

    assert coordinator.state().phase == ShutdownPhase.COUNTING_DOWN


def test_shutdown_countdown_allowed_after_partial_failure_batch_completed(tmp_path):
    coordinator, jobs, _ = _shutdown_env(tmp_path)
    job = _finished_job(
        jobs,
        FileStatus.FAILED,
        True,
        {"a": FileStatus.DONE, "b": FileStatus.FAILED, "c": FileStatus.DONE},
    )

    coordinator.job_finished(job)

    assert coordinator.state().phase == ShutdownPhase.COUNTING_DOWN


def test_shutdown_countdown_allowed_when_drive_failed_independent_of_local(tmp_path):
    coordinator, jobs, _ = _shutdown_env(tmp_path)
    job = _finished_job(
        jobs,
        FileStatus.DONE,
        True,
        {"a": FileStatus.DONE},
        drive={"a": DriveFileState(status=DriveStatus.FAILED, error="fake failure")},
    )

    coordinator.job_finished(job)

    assert coordinator.state().phase == ShutdownPhase.COUNTING_DOWN


@pytest.mark.parametrize("status", [FileStatus.STOPPED, FileStatus.CANCELLED, FileStatus.CRASHED])
def test_shutdown_countdown_blocked_for_stopped_cancelled_crashed(tmp_path, status):
    coordinator, jobs, _ = _shutdown_env(tmp_path)
    job = _finished_job(
        jobs, status, False, {"a": FileStatus.DONE, "b": FileStatus.WAITING}
    )

    coordinator.job_finished(job)

    assert coordinator.state().phase == ShutdownPhase.INACTIVE


def test_shutdown_countdown_blocked_for_fatal_error_mid_batch(tmp_path):
    coordinator, jobs, _ = _shutdown_env(tmp_path)
    job = _finished_job(
        jobs,
        FileStatus.FAILED,
        False,
        {"a": FileStatus.FAILED, "b": FileStatus.WAITING},
    )

    coordinator.job_finished(job)

    assert coordinator.state().phase == ShutdownPhase.INACTIVE


def test_shutdown_countdown_cancel_after_partial_failure_batch(tmp_path):
    coordinator, jobs, events = _shutdown_env(tmp_path)
    job = _finished_job(
        jobs,
        FileStatus.FAILED,
        True,
        {"a": FileStatus.DONE, "b": FileStatus.FAILED},
    )

    coordinator.job_finished(job)
    assert coordinator.state().phase == ShutdownPhase.COUNTING_DOWN
    assert coordinator.cancel_shutdown().phase == ShutdownPhase.CANCELLED


def test_new_job_batch_completed_defaults_to_false(tmp_path):
    manager = JobManager(str(tmp_path / "jobs.json"))

    job = manager.create_job("folder", ["a"])

    assert job.batch_completed is False


def test_legacy_persisted_job_without_batch_completed_field_defaults_to_false(tmp_path):
    storage = tmp_path / "jobs.json"
    storage.parent.mkdir(parents=True, exist_ok=True)
    legacy_payload = {
        "legacy-job": {
            "job_id": "legacy-job",
            "status": "DONE",
            "folder": "folder",
            "engine": "local_whisper",
            "total_files": 1,
            "done_files": 1,
            "failed_files": 0,
            "files": {"a": "DONE"},
        }
    }
    storage.write_text(json.dumps(legacy_payload), encoding="utf-8")

    manager = JobManager(str(storage))
    loaded = manager.get_job("legacy-job")

    assert "batch_completed" not in legacy_payload["legacy-job"]
    assert loaded.batch_completed is False
def test_drive_mp3_less_upload_and_retry(tmp_path):
    folder, manager, job = make_done_job(tmp_path)
    stem = next(iter(job.files))
    (folder / f"{stem}.mp3").unlink()
    client = FakeDriveClient()
    settings = SettingsManager(tmp_path / "settings.json")
    service = DriveUploadService(manager, FakeAuth(client), settings)

    first = service.upload(job.job_id, stem)
    assert first.status == DriveStatus.DONE

    second = service.retry(job.job_id, stem)
    assert second.status == DriveStatus.DONE

    assert sorted(client.created) == sorted([
        f"{stem}.txt",
        f"{stem}.json",
        f"{stem}.srt",
    ])
    assert f"{stem}.mp3" not in client.created
    assert f"{stem}.mp3" not in client.updated

def test_drive_exam_root_roundtrip_and_usage(tmp_path):
    settings_manager = SettingsManager(tmp_path / "settings.json")
    assert settings_manager.get().drive_exam_root == "2026 제37회 공인중개사 자격시험"

    settings_manager.update(SettingsPatch(drive_exam_root="Custom Root"))
    assert settings_manager.get().drive_exam_root == "Custom Root"

    classifier = DriveClassifier()
    manager = JobManager(str(tmp_path / "runtime" / "jobs.json"))
    job = manager.create_job("folder", ["기본이론_민법_1주차_1강"])
    classification = classifier.classify(job, "기본이론_민법_1주차_1강", settings_manager.get().drive_exam_root)
    assert classification.folders[0] == "Custom Root"

def test_drive_auto_upload_persistence_absence(tmp_path):
    settings_manager = SettingsManager(tmp_path / "settings.json")
    dumped = settings_manager.get().model_dump()
    assert "drive_auto_upload" not in dumped

def test_drive_old_remote_state_compatibility(tmp_path):
    folder, manager, job = make_done_job(tmp_path)
    stem = next(iter(job.files))
    job.drive[stem] = DriveFileState(
        status=DriveStatus.DONE,
        remote_file_ids={
            f"{stem}.mp3": "old_mp3_id",
            f"{stem}.txt": "old_txt_id"
        }
    )
    manager.update_job(job)

    loaded_manager = JobManager(str(tmp_path / "runtime" / "jobs.json"))
    loaded_job = loaded_manager.get_job(job.job_id)
    assert loaded_job.drive[stem].remote_file_ids[f"{stem}.mp3"] == "old_mp3_id"

    client = FakeDriveClient()
    client.files[("root", f"{stem}.txt")] = "old_txt_id"
    settings = SettingsManager(tmp_path / "settings.json")
    service = DriveUploadService(loaded_manager, FakeAuth(client), settings)

    result = service.upload(loaded_job.job_id, stem)
    assert result.status == DriveStatus.DONE

def test_drive_output_invalid_isolation(tmp_path):
    folder, manager, job = make_done_job(tmp_path)
    stem = next(iter(job.files))
    (folder / f"{stem}.txt").write_bytes(b"")

    client = FakeDriveClient()
    settings = SettingsManager(tmp_path / "settings.json")
    service = DriveUploadService(manager, FakeAuth(client), settings)

    result = service.upload(job.job_id, stem)
    assert result.status == DriveStatus.FAILED

    persisted = manager.get_job(job.job_id)
    assert persisted.status == FileStatus.DONE
    assert persisted.files[stem] == FileStatus.DONE
