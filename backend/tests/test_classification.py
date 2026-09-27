import json

import pytest

from src.services.classification import StageRequiredError, resolve_stage
from src.services.job_manager import JobManager
from src.services.settings import RuntimeSettings, SettingsManager, SettingsPatch


# ---------------------------------------------------------------------------
# B. stage resolution (D16)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "subject,expected",
    [
        ("부동산학개론", "1차"),
        ("민법", "1차"),
        ("공인중개사법", "2차"),
        ("부동산공법", "2차"),
        ("부동산공시법", "2차"),
        ("부동산세법", "2차"),
    ],
)
def test_resolve_stage_known_subjects(subject, expected):
    assert resolve_stage(subject, None, {}) == expected


def test_resolve_stage_known_subject_ignores_conflicting_supplied_stage():
    # Server is authoritative for known subjects (Section 27).
    assert resolve_stage("민법", "2차", {}) == "1차"


def test_resolve_stage_unknown_subject_reuses_saved_override():
    assert resolve_stage("특강", None, {"특강": "1차"}) == "1차"


def test_resolve_stage_unknown_subject_with_supplied_stage_and_no_override():
    assert resolve_stage("특강", "2차", {}) == "2차"


def test_resolve_stage_unknown_subject_without_override_or_supplied_stage_rejected():
    with pytest.raises(StageRequiredError):
        resolve_stage("특강", None, {})


# ---------------------------------------------------------------------------
# C. settings backward compatibility
# ---------------------------------------------------------------------------

def test_legacy_settings_without_new_fields_load_with_defaults(tmp_path):
    path = tmp_path / "settings.json"
    legacy_payload = {
        "notifications": {"file_complete": False, "job_complete": True},
        "close_behavior": "exit",
        "shutdown": "15_seconds",
    }
    path.write_text(json.dumps(legacy_payload), encoding="utf-8")

    manager = SettingsManager(path)
    loaded = manager.get()

    # Existing values preserved.
    assert loaded.notifications.file_complete is False
    assert loaded.close_behavior.value == "exit"
    assert loaded.shutdown.value == "15_seconds"
    # New fields default safely.
    assert loaded.transcription_folder is None
    assert loaded.last_course is None
    assert loaded.last_subject is None
    assert loaded.subject_stage_overrides == {}
    # No quarantine occurred for a merely-missing-new-fields payload.
    assert not list(tmp_path.glob("settings.corrupt.*.json"))


def test_settings_persist_new_fields_round_trip(tmp_path):
    manager = SettingsManager(tmp_path / "settings.json")
    updated = manager.update(
        SettingsPatch(
            transcription_folder="C:/전사자료",
            last_course="개념완성",
            last_subject="민법",
            subject_stage_overrides={"특강": "1차"},
        )
    )
    assert updated.transcription_folder == "C:/전사자료"
    assert updated.last_course == "개념완성"
    assert updated.last_subject == "민법"
    assert updated.subject_stage_overrides == {"특강": "1차"}

    reloaded = SettingsManager(tmp_path / "settings.json").get()
    assert reloaded.subject_stage_overrides == {"특강": "1차"}


def test_settings_never_gains_drive_auto_upload_field():
    assert "drive_auto_upload" not in RuntimeSettings.model_fields


# ---------------------------------------------------------------------------
# D/E. Job metadata: legacy compatibility and new-Job population
# ---------------------------------------------------------------------------

def test_legacy_persisted_job_without_classification_metadata_loads(tmp_path):
    storage = tmp_path / "jobs.json"
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

    assert loaded is not None
    assert loaded.course is None
    assert loaded.subject is None
    assert loaded.stage is None
    assert loaded.file_metadata == {}


def test_new_job_stores_classification_and_file_metadata(tmp_path):
    from src.domain.models import FileMetadata

    manager = JobManager(str(tmp_path / "jobs.json"))
    job = manager.create_job(
        "folder",
        ["a", "b"],
        course="개념완성",
        subject="민법",
        stage="1차",
        file_metadata={
            "a": FileMetadata(week="1", lesson="1", normalized_name="개념완성_민법_1주차_1강"),
            "b": FileMetadata(week=None, lesson=None, normalized_name=None),
        },
    )

    assert job.course == "개념완성"
    assert job.subject == "민법"
    assert job.stage == "1차"
    assert job.file_metadata["a"].week == "1"
    assert job.file_metadata["a"].normalized_name == "개념완성_민법_1주차_1강"
    assert job.file_metadata["b"].normalized_name is None

    reloaded = JobManager(str(tmp_path / "jobs.json")).get_job(job.job_id)
    assert reloaded.course == "개념완성"
    assert reloaded.file_metadata["a"].lesson == "1"
