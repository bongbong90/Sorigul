from pathlib import Path

import pytest

from src.domain.models import FileMetadata, FileStatus
from src.services.job_manager import JobManager
from src.services.normalizer import FilenameNormalizer
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

    assert job.file_metadata[standard_id].normalized_name == standard_id
    assert job.file_metadata[standard_id].week == "1"
    assert job.file_metadata[standard_id].lesson == "1"


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


# ---------------------------------------------------------------------------
# C. /rename rejects path traversal in old_stem/new_stem
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad_stem", ["../x", "..\\x", "subdir/x", "subdir\\x", ".."])
def test_rename_endpoint_rejects_path_traversal(tmp_path, bad_stem):
    from fastapi import HTTPException
    from src.api.routes import RenameRequest, apply_rename

    (tmp_path / "old.mp3").write_bytes(b"mp3")

    with pytest.raises(HTTPException):
        apply_rename(RenameRequest(folder=str(tmp_path), old_stem="old", new_stem=bad_stem))
    with pytest.raises(HTTPException):
        apply_rename(RenameRequest(folder=str(tmp_path), old_stem=bad_stem, new_stem="new"))

    # Nothing was touched by either rejected attempt.
    assert (tmp_path / "old.mp3").exists()


# ---------------------------------------------------------------------------
# D. /rename rejects forbidden/control chars and trailing dot/space, plus
# an empty stem
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("char", list('<>:"|?*'))
def test_rename_endpoint_rejects_forbidden_characters(tmp_path, char):
    from fastapi import HTTPException
    from src.api.routes import RenameRequest, apply_rename

    (tmp_path / "old.mp3").write_bytes(b"mp3")
    with pytest.raises(HTTPException):
        apply_rename(RenameRequest(folder=str(tmp_path), old_stem="old", new_stem=f"bad{char}name"))


def test_rename_endpoint_rejects_control_character(tmp_path):
    from fastapi import HTTPException
    from src.api.routes import RenameRequest, apply_rename

    (tmp_path / "old.mp3").write_bytes(b"mp3")
    with pytest.raises(HTTPException):
        apply_rename(RenameRequest(folder=str(tmp_path), old_stem="old", new_stem="bad\x07name"))


@pytest.mark.parametrize("bad_stem", ["trailing.", "trailing ", ""])
def test_rename_endpoint_rejects_trailing_dot_space_and_empty(tmp_path, bad_stem):
    from fastapi import HTTPException
    from src.api.routes import RenameRequest, apply_rename

    (tmp_path / "old.mp3").write_bytes(b"mp3")
    with pytest.raises(HTTPException):
        apply_rename(RenameRequest(folder=str(tmp_path), old_stem="old", new_stem=bad_stem))


# ---------------------------------------------------------------------------
# E. a legitimate standard stem containing underscores still renames --
# validate_safe_stem must not overreach into the classification-text rule
# ---------------------------------------------------------------------------

def test_rename_endpoint_accepts_standard_stem_with_underscores(tmp_path):
    from src.api.routes import RenameRequest, apply_rename

    (tmp_path / "개념완성_민법_1주차_1강.mp3").write_bytes(b"mp3")

    response = apply_rename(RenameRequest(
        folder=str(tmp_path), old_stem="개념완성_민법_1주차_1강", new_stem="개념완성_민법_1주차_2강",
    ))

    assert response.status == "success"
    assert (tmp_path / "개념완성_민법_1주차_2강.mp3").exists()


# ---------------------------------------------------------------------------
# F. raw temp MP3 -> normalize -> rename -> create Job -> normalized_name
# populated (pre-job metadata integration)
# ---------------------------------------------------------------------------

def test_prejob_rename_then_create_job_populates_normalized_name(tmp_path):
    from src.api.routes import CreateJobRequest, RenameRequest, apply_rename, create_job
    import src.api.routes

    folder = tmp_path / "전사자료"
    folder.mkdir()
    (folder / "1강_[1주차]_원본.mp3").touch()

    jm = JobManager(str(tmp_path / "jobs.json"))
    src.api.routes.job_manager = jm
    src.api.routes.settings_manager = SettingsManager(tmp_path / "settings.json")

    preview = FilenameNormalizer().normalize("1강_[1주차]_원본.mp3", "개념완성", "민법", set())
    assert preview.result_type == "NORMALIZED"
    new_stem = Path(preview.suggested_name).stem

    response = apply_rename(RenameRequest(folder=str(folder), old_stem="1강_[1주차]_원본", new_stem=new_stem))
    assert response.new_file_id == new_stem

    job = create_job(CreateJobRequest(
        folder=str(folder), file_ids=[], scope="all_incomplete", course="개념완성", subject="민법",
    ))

    assert job.file_metadata[new_stem].normalized_name == new_stem


# ---------------------------------------------------------------------------
# G. /normalize/batch gives colliding raw inputs distinct deterministic
# target stems (batch collision reservation)
# ---------------------------------------------------------------------------

def test_normalize_batch_endpoint_reserves_unique_stems(tmp_path):
    from src.api.routes import NormalizeBatchRequest, preview_normalization_batch

    folder = tmp_path / "전사자료"
    folder.mkdir()

    req = NormalizeBatchRequest(
        folder=str(folder),
        filenames=["1강_[1주차]_a.mp3", "1강_[1주차]_b.mp3"],
        course="개념완성",
        subject="민법",
    )
    results = preview_normalization_batch(req)

    stems = [Path(r.suggested_name).stem for r in results]
    assert len(set(stems)) == 2
    assert stems[0] == "개념완성_민법_1주차_1강"
    assert stems[1] == "개념완성_민법_1주차_2강"


# ---------------------------------------------------------------------------
# Extra: create_job's server-side backstop for unresolved MISMATCH/
# INVALID_TARGET/CONFLICT targets (Section 12)
# ---------------------------------------------------------------------------

def test_job_creation_rejects_unresolved_mismatch_without_continue_original(tmp_path):
    from fastapi import HTTPException
    from src.api.routes import CreateJobRequest, create_job
    import src.api.routes

    folder = tmp_path / "전사자료"
    folder.mkdir()
    # Standard-named, but embedded course/subject differ from typed -> MISMATCH.
    (folder / "기본이론_민법_1주차_1강.mp3").touch()

    jm = JobManager(str(tmp_path / "jobs.json"))
    src.api.routes.job_manager = jm
    src.api.routes.settings_manager = SettingsManager(tmp_path / "settings.json")

    req = CreateJobRequest(
        folder=str(folder), file_ids=[], scope="all_incomplete", course="개념완성", subject="부동산학개론",
    )
    with pytest.raises(HTTPException):
        create_job(req)


def test_job_creation_allows_explicit_continue_original_resolution(tmp_path):
    from src.api.routes import CreateJobRequest, create_job
    import src.api.routes

    folder = tmp_path / "전사자료"
    folder.mkdir()
    (folder / "기본이론_민법_1주차_1강.mp3").touch()

    jm = JobManager(str(tmp_path / "jobs.json"))
    src.api.routes.job_manager = jm
    src.api.routes.settings_manager = SettingsManager(tmp_path / "settings.json")

    req = CreateJobRequest(
        folder=str(folder), file_ids=[], scope="all_incomplete", course="개념완성", subject="부동산학개론",
        file_resolutions={"기본이론_민법_1주차_1강": "CONTINUE_ORIGINAL"},
    )
    job = create_job(req)

    assert job.file_metadata["기본이론_민법_1주차_1강"].normalized_name is None


def test_job_creation_rejects_normalized_without_rename(tmp_path):
    from fastapi import HTTPException
    from src.api.routes import CreateJobRequest, create_job
    import src.api.routes

    folder = tmp_path / "전사자료"
    folder.mkdir()
    (folder / "1강_[1주차]_원본.mp3").touch()

    jm = JobManager(str(tmp_path / "jobs.json"))
    src.api.routes.job_manager = jm
    src.api.routes.settings_manager = SettingsManager(tmp_path / "settings.json")

    # A: reject direct create_job
    req = CreateJobRequest(
        folder=str(folder), file_ids=[], scope="all_incomplete", course="개념완성", subject="민법",
    )
    with pytest.raises(HTTPException, match="파일명 정규화를 먼저 적용해 주세요"):
        create_job(req)

    # C: reject even with CONTINUE_ORIGINAL
    req_c = CreateJobRequest(
        folder=str(folder), file_ids=[], scope="all_incomplete", course="개념완성", subject="민법",
        file_resolutions={"1강_[1주차]_원본": "CONTINUE_ORIGINAL"}
    )
    with pytest.raises(HTTPException, match="파일명 정규화를 먼저 적용해 주세요"):
        create_job(req_c)

def test_create_job_direct_colab_normalization(tmp_path):
    from src.api.routes import create_job, CreateJobRequest
    from src.services.job_manager import JobManager
    from src.services.settings import SettingsManager
    import src.api.routes

    jm = JobManager(str(tmp_path / "jobs.json"))
    sm = SettingsManager(tmp_path)
    src.api.routes.job_manager = jm
    src.api.routes.settings_manager = sm

    test_mp3 = tmp_path / "test.mp3"
    import os; os.makedirs(str(tmp_path), exist_ok=True); open(str(test_mp3), "wb").write(b"dummy")

    req = CreateJobRequest(
        folder=str(tmp_path),
        file_ids=["test"],
        course="개념완성",
        subject="민법",
        engine="direct_colab", file_resolutions={"test": "CONTINUE_ORIGINAL"},
        colab_url="https://example.test/health"
    )

    res = create_job(req)
    job = jm.get_job(res.job_id)

    assert job.engine == "direct_colab"
    assert job.engine_config.get("base_url") == "https://example.test"

def test_create_job_invalid_colab_url(tmp_path):
    from src.api.routes import create_job, CreateJobRequest
    from src.services.job_manager import JobManager
    from src.services.settings import SettingsManager
    from fastapi import HTTPException
    import src.api.routes

    jm = JobManager(str(tmp_path / "jobs.json"))
    sm = SettingsManager(tmp_path)
    src.api.routes.job_manager = jm
    src.api.routes.settings_manager = sm

    test_mp3 = tmp_path / "test.mp3"
    import os; os.makedirs(str(tmp_path), exist_ok=True); open(str(test_mp3), "wb").write(b"dummy")

    req = CreateJobRequest(
        folder=str(tmp_path),
        file_ids=["test"],
        course="개념완성",
        subject="민법",
        engine="direct_colab", file_resolutions={"test": "CONTINUE_ORIGINAL"},
        colab_url="https://example.test/other"
    )

    try:
        create_job(req)
        assert False, "Should have raised HTTPException"
    except HTTPException as e:
        assert e.status_code == 400

def test_create_job_local_engine(tmp_path):
    from src.api.routes import create_job, CreateJobRequest
    from src.services.job_manager import JobManager
    from src.services.settings import SettingsManager
    import src.api.routes

    jm = JobManager(str(tmp_path / "jobs.json"))
    sm = SettingsManager(tmp_path)
    src.api.routes.job_manager = jm
    src.api.routes.settings_manager = sm

    test_mp3 = tmp_path / "test.mp3"
    import os; os.makedirs(str(tmp_path), exist_ok=True); open(str(test_mp3), "wb").write(b"dummy")

    req = CreateJobRequest(
        folder=str(tmp_path),
        file_ids=["test"],
        course="개념완성",
        subject="민법",
        engine="local_whisper", file_resolutions={"test": "CONTINUE_ORIGINAL"},
        colab_url="https://example.test"
    )

    res = create_job(req)
    job = jm.get_job(res.job_id)

    assert job.engine == "local_whisper"
    assert "base_url" not in job.engine_config
