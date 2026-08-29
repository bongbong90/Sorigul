import pytest

from src.domain.models import FileMetadata, FileStatus
from src.services.job_manager import JobManager
from src.services.settings import SettingsManager


# ---------------------------------------------------------------------------
# F. retry preserves classification metadata
# ---------------------------------------------------------------------------

def test_retry_preserves_classification_metadata(tmp_path):
    jm = JobManager(str(tmp_path / "jobs.json"))
    job = jm.create_job(
        "folder",
        ["a"],
        course="개념완성",
        subject="민법",
        stage="1차",
        file_metadata={"a": FileMetadata(week="1", lesson="1", normalized_name="개념완성_민법_1주차_1강")},
    )
    job.files["a"] = FileStatus.FAILED
    jm.update_job(job)

    import src.api.routes
    src.api.routes.job_manager = jm
    from src.api.routes import JobActionRequest, job_action

    job_action(job.job_id, JobActionRequest(action="retry"))

    updated = jm.get_job(job.job_id)
    assert updated.course == "개념완성"
    assert updated.subject == "민법"
    assert updated.stage == "1차"
    assert updated.file_metadata["a"].normalized_name == "개념완성_민법_1주차_1강"


# ---------------------------------------------------------------------------
# M. rename endpoint response carries old_file_id/new_file_id
# ---------------------------------------------------------------------------

def test_rename_endpoint_response_carries_old_and_new_file_id(tmp_path):
    from src.api.routes import RenameRequest, apply_rename

    (tmp_path / "old.mp3").write_bytes(b"mp3")
    (tmp_path / "old.txt").write_text("hello", encoding="utf-8")

    response = apply_rename(RenameRequest(folder=str(tmp_path), old_stem="old", new_stem="new"))

    assert response.status == "success"
    assert response.old_file_id == "old"
    assert response.new_file_id == "new"
    assert (tmp_path / "new.mp3").exists()
    assert (tmp_path / "old.mp3").exists() is False


# ---------------------------------------------------------------------------
# N. bundle rename never overwrites an existing user file on collision
# ---------------------------------------------------------------------------

def test_rename_endpoint_rejects_when_target_exists(tmp_path):
    from fastapi import HTTPException
    from src.api.routes import RenameRequest, apply_rename

    (tmp_path / "old.mp3").write_bytes(b"mp3")
    (tmp_path / "new.mp3").write_bytes(b"existing user file")

    with pytest.raises(HTTPException):
        apply_rename(RenameRequest(folder=str(tmp_path), old_stem="old", new_stem="new"))

    # Neither file was touched.
    assert (tmp_path / "old.mp3").read_bytes() == b"mp3"
    assert (tmp_path / "new.mp3").read_bytes() == b"existing user file"


# ---------------------------------------------------------------------------
# I/J. Job-creation-time collision uses the real folder, and next-free-lesson
# ---------------------------------------------------------------------------

def test_job_creation_records_normalized_name_only_when_already_standard(tmp_path):
    from src.api.routes import CreateJobRequest, create_job
    import src.api.routes

    folder = tmp_path / "전사자료"
    folder.mkdir()
    # Already standard and matching typed course/subject -> normalized_name set.
    (folder / "개념완성_민법_1주차_1강.mp3").touch()
    # Not yet normalized (raw lecture title) -> normalized_name stays None,
    # even though week/lesson are still recorded.
    (folder / "1강_[2주차]_원본파일.mp3").touch()

    jm = JobManager(str(tmp_path / "jobs.json"))
    src.api.routes.job_manager = jm
    # Isolate from the real %LOCALAPPDATA%\Sorigul\settings.json -- create_job
    # now reads settings_manager for subject_stage_overrides.
    src.api.routes.settings_manager = SettingsManager(tmp_path / "settings.json")

    req = CreateJobRequest(
        folder=str(folder), file_ids=[], scope="all_incomplete", course="개념완성", subject="민법"
    )
    job = create_job(req)

    standard_id = "개념완성_민법_1주차_1강"
    raw_id = "1강_[2주차]_원본파일"

    assert job.file_metadata[standard_id].normalized_name == standard_id
    assert job.file_metadata[standard_id].week == "1"
    assert job.file_metadata[standard_id].lesson == "1"

    assert job.file_metadata[raw_id].normalized_name is None
    assert job.file_metadata[raw_id].week == "2"
    assert job.file_metadata[raw_id].lesson == "1"


def test_job_creation_rejects_unknown_subject_without_stage_or_override(tmp_path):
    from fastapi import HTTPException
    from src.api.routes import CreateJobRequest, create_job
    import src.api.routes

    folder = tmp_path / "전사자료"
    folder.mkdir()
    (folder / "1강_[1주차]_원본.mp3").touch()

    jm = JobManager(str(tmp_path / "jobs.json"))
    src.api.routes.job_manager = jm
    src.api.routes.settings_manager = SettingsManager(tmp_path / "settings.json")

    req = CreateJobRequest(
        folder=str(folder), file_ids=[], scope="all_incomplete", course="개념완성", subject="특강"
    )
    with pytest.raises(HTTPException):
        create_job(req)
