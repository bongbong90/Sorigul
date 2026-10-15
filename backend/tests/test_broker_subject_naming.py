"""#192: exact aliases, safe previews, metadata/legacy Drive paths; offline."""
import pytest

from src.services.classification import StageRequiredError, resolve_stage
from src.services.drive import DriveClassifier, DriveError
from src.services.job_manager import JobManager
from src.services.normalizer import FilenameNormalizer
from src.services.output_bundle import BundlePaths


@pytest.mark.parametrize("subject", ["공인중개사법", "중개사법"])
def test_exact_broker_subject_filename_bundle_and_drive(subject, tmp_path, monkeypatch):
    from src.api import routes
    from src.services.settings import SettingsManager

    manager = JobManager(str(tmp_path / "jobs.json"))
    monkeypatch.setattr(routes, "job_manager", manager)
    monkeypatch.setattr(routes, "settings_manager", SettingsManager(tmp_path / "settings.json"))
    source = tmp_path / "synthetic_1주차_1강.mp3"
    source.write_bytes(b"synthetic")
    preview = FilenameNormalizer().normalize(source.name, "기초이론", subject, manual_week=1)
    assert preview.suggested_name == "기초이론_중개사법_1주차_1강.mp3"
    assert preview.can_apply
    # A preview never changes the original; the existing explicit rename API
    # remains the only write path and keeps its collision protection.
    assert source.read_bytes() == b"synthetic"
    assert not (tmp_path / preview.suggested_name).exists()
    assert resolve_stage(subject, "1차", {subject: "1차"}) == "2차"
    stem = "기초이론_중개사법_1주차_1강"
    (tmp_path / f"{stem}.mp3").write_bytes(b"synthetic")
    job = routes.create_job(routes.CreateJobRequest(
        folder=str(tmp_path), scope="selected", file_ids=[stem],
        course="기초이론", subject=subject, week=1,
    ))
    assert job.stage == "2차"
    assert job.file_metadata[stem].normalized_name == stem
    bundle = BundlePaths.final_for(tmp_path / f"{stem}.mp3")
    assert {bundle.txt.name, bundle.json.name, bundle.srt.name} == {f"{stem}{ext}" for ext in (".txt", ".json", ".srt")}
    classified = DriveClassifier().classify(job, stem, "2026 테스트 시험")
    assert classified.folders[-2:] == ("[2차] 공인중개사법", "기초이론_중개사법_1주차")


@pytest.mark.parametrize("subject", ["공인중개사법", "중개사법"])
def test_legacy_broker_subject_drive_fallback(subject, tmp_path):
    stem = f"기초이론_{subject}_1주차_1강"
    job = JobManager(str(tmp_path / "jobs.json")).create_job("synthetic", [stem])
    classified = DriveClassifier().classify(job, stem, "2026 테스트 시험")
    assert classified.subject == "공인중개사법"
    assert classified.folders[-2:] == ("[2차] 공인중개사법", "기초이론_중개사법_1주차")


@pytest.mark.parametrize("subject", ["공인중개사법", "중개사법"])
def test_existing_long_filename_is_preserved_and_valid_for_new_job(subject, tmp_path, monkeypatch):
    original = "기초이론_공인중개사법_1주차_1강.mp3"
    preview = FilenameNormalizer().normalize(original, "기초이론", subject, manual_week=1)
    assert preview.result_type == "UNCHANGED"
    assert not preview.can_apply
    assert preview.suggested_name == original
    assert preview.typed_target_name is None
    from src.api import routes
    from src.services.settings import SettingsManager
    monkeypatch.setattr(routes, "job_manager", JobManager(str(tmp_path / "jobs.json")))
    monkeypatch.setattr(routes, "settings_manager", SettingsManager(tmp_path / "settings.json"))
    (tmp_path / original).write_bytes(b"synthetic")
    stem = original[:-4]
    job = routes.create_job(routes.CreateJobRequest(folder=str(tmp_path), scope="selected", file_ids=[stem], course="기초이론", subject=subject, week=1))
    assert job.file_metadata[stem].normalized_name == stem
    assert DriveClassifier().classify(job, stem, "test").folders[-2:] == ("[2차] 공인중개사법", "기초이론_중개사법_1주차")
    assert (tmp_path / original).read_bytes() == b"synthetic"


def test_existing_long_standard_with_other_course_still_requires_review():
    preview = FilenameNormalizer().normalize("기초이론_공인중개사법_1주차_1강.mp3", "기본이론", "중개사법", manual_week=1)
    assert preview.result_type == "MISMATCH"
    assert preview.typed_target_name == "기본이론_중개사법_1주차_1강.mp3"


def test_existing_long_standard_week_mismatch_still_requires_review():
    preview = FilenameNormalizer().normalize("기초이론_공인중개사법_1주차_1강.mp3", "기초이론", "중개사법", manual_week=2)
    assert preview.result_type == "WEEK_MISMATCH"
    assert preview.typed_target_name == "기초이론_중개사법_2주차_1강.mp3"


@pytest.mark.parametrize("ext", [".mp3", ".txt", ".json", ".srt"])
def test_short_subject_collisions_respect_all_four_files(ext, tmp_path):
    (tmp_path / f"기초이론_중개사법_1주차_1강{ext}").touch()
    from src.services.normalizer import collect_existing_stems
    preview = FilenameNormalizer().normalize("synthetic_1주차_1강.mp3", "기초이론", "공인중개사법", collect_existing_stems(tmp_path), 1)
    assert preview.suggested_name == "기초이론_중개사법_1주차_2강.mp3"


@pytest.mark.parametrize("subject", ["학개론", "공시법", "공법", "세법", "중개사법 특강", "중개사 법"])
def test_no_additional_aliases(subject, tmp_path):
    with pytest.raises(StageRequiredError):
        resolve_stage(subject, None, {})
    stem = f"기초이론_{subject}_1주차_1강"
    job = JobManager(str(tmp_path / "jobs.json")).create_job("synthetic", [stem])
    with pytest.raises(DriveError):
        DriveClassifier().classify(job, stem, "test")
