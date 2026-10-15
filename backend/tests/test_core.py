import os
import json
import pytest
from pathlib import Path
from src.domain.models import BundleStatus, FileStatus
from src.services.scanner import FileScanner
from src.services.normalizer import FilenameNormalizer
from src.services.renamer import BundleRenamer
from src.services.job_manager import JobManager

@pytest.fixture
def test_dir(tmp_path):
    # Setup some dummy files
    d = tmp_path / "test_data"
    d.mkdir()

    # 1. Normal DONE bundle
    (d / "done.mp3").touch()
    (d / "done.txt").write_text("Hello")
    (d / "done.srt").touch() # 0 byte allowed
    (d / "done.json").write_text('{"text": "Hello", "segments": []}')

    # 2. Incomplete (missing SRT)
    (d / "no_srt.mp3").touch()
    (d / "no_srt.txt").write_text("Hello")
    (d / "no_srt.json").write_text('{"text": "Hello", "segments": []}')

    # 3. Invalid JSON
    (d / "invalid_json.mp3").touch()
    (d / "invalid_json.txt").write_text("Hello")
    (d / "invalid_json.srt").touch()
    (d / "invalid_json.json").write_text('{"bad": "json"}')

    # 4. Korean path
    k_dir = tmp_path / "전사자료"
    k_dir.mkdir()
    (k_dir / "개념완성_민법_8주차_4강.mp3").touch()

    # 5. Non-mp3
    (d / "some_file.wav").touch()

    # 6. Recursive sub-folder (should be ignored)
    sub = d / "sub"
    sub.mkdir()
    (sub / "sub.mp3").touch()

    return d, k_dir

def test_file_scan_and_completion(test_dir):
    d, _ = test_dir
    scanner = FileScanner(str(d))
    files = scanner.scan()

    # Non-recursive, mp3 only -> done.mp3, no_srt.mp3, invalid_json.mp3
    assert len(files) == 3

    names = {f.filename: f for f in files}
    assert names["done.mp3"].completion_status == BundleStatus.DONE
    assert names["no_srt.mp3"].completion_status == BundleStatus.INCOMPLETE
    assert names["invalid_json.mp3"].completion_status == BundleStatus.INVALID_RESULT

def test_filename_normalization():
    norm = FilenameNormalizer()

    # Clean forbidden chars, + to space
    p1 = norm.normalize("기본이론_민법_<1주차>_1강.mp3", set())
    assert p1.suggested_name == "기본이론_민법_1주차_1강.mp3" # Course subject heuristically parsed

    # Standard name protected
    p2 = norm.normalize("개념완성_민법_8주차_4강.mp3", set())
    assert p2.suggested_name == "개념완성_민법_8주차_4강.mp3"
    assert p2.result_type == "UNCHANGED"

def test_next_lesson_batch_reservation():
    norm = FilenameNormalizer()
    # Batch test
    names = [
        "기본이론_민법_1주차_1강.mp3",
        "기본이론_민법_1주차_1강 copy.mp3",
        "기본이론_민법_1주차_2강.mp3"
    ]
    res = norm.normalize_batch(names, set())
    assert res[0].suggested_name == "기본이론_민법_1주차_1강.mp3"
    assert res[1].suggested_name == "기본이론_민법_1주차_2강.mp3" # auto incremented
    assert res[2].suggested_name == "기본이론_민법_1주차_3강.mp3" # incremented because 2강 was taken

def test_safe_bundle_rename(test_dir):
    d, _ = test_dir
    renamer = BundleRenamer()

    # Try to rename 'done' to 'done2'
    success = renamer.apply_rename(str(d), "done", "done2")
    assert success
    assert (d / "done2.mp3").exists()
    assert (d / "done2.txt").exists()
    assert not (d / "done.mp3").exists()

    # Try rename to existing -> fail
    (d / "done3.mp3").touch()
    success = renamer.apply_rename(str(d), "done2", "done3")
    assert not success
    assert (d / "done2.mp3").exists() # Should rollback/not execute

def test_job_persistence_and_crashed(tmp_path):
    storage = tmp_path / "jobs.json"
    jm = JobManager(str(storage))

    job = jm.create_job("some_folder", ["file1", "file2"])
    job.status = FileStatus.TRANSCRIBING
    job.files["file1"] = FileStatus.TRANSCRIBING
    job.files["file2"] = FileStatus.WAITING
    jm.update_job(job)

    # Reload 1
    jm2 = JobManager(str(storage))
    reloaded = jm2.get_job(job.job_id)

    assert reloaded.status == FileStatus.CRASHED
    assert reloaded.files["file1"] == FileStatus.CRASHED
    assert reloaded.files["file2"] == FileStatus.WAITING
    assert reloaded.events[-1].category == "CRASHED"
    event_count = len(reloaded.events)

    # Reload 2 (CRASHED was saved, shouldn't duplicate event)
    jm3 = JobManager(str(storage))
    reloaded2 = jm3.get_job(job.job_id)
    assert len(reloaded2.events) == event_count

def test_corrupt_quarantine(tmp_path):
    storage = tmp_path / "jobs.json"
    storage.parent.mkdir(parents=True, exist_ok=True)
    storage.write_text("{bad json")

    # Starting JobManager should not crash, should rename the file
    jm = JobManager(str(storage))
    assert not storage.exists() # The original corrupt file is removed
    quarantine_files = list(tmp_path.glob("jobs.corrupt.*.json"))
    assert len(quarantine_files) == 1
    assert len(jm.jobs) == 0

    # Can save new job
    jm.create_job("folder", ["f1"])
    assert storage.exists()

def test_corrupt_quarantine_wrong_schema(tmp_path):
    storage = tmp_path / "jobs2.json"
    storage.parent.mkdir(parents=True, exist_ok=True)
    storage.write_text("[]") # Valid JSON but wrong schema

    jm = JobManager(str(storage))
    assert not storage.exists()
    assert len(list(tmp_path.glob("jobs.corrupt.*.json"))) >= 1
    assert len(jm.jobs) == 0

def test_job_create_modes(tmp_path, test_dir):
    d, _ = test_dir
    jm = JobManager(str(tmp_path / "jobs.json"))
    from src.api.routes import CreateJobRequest, create_job
    import src.api.routes
    src.api.routes.job_manager = jm

    # all_incomplete mode: should skip "done"
    req1 = CreateJobRequest(folder=str(d), file_ids=[], scope="all_incomplete")
    job1 = create_job(req1)
    assert len(job1.files) == 2 # "no_srt", "invalid_json"

    # selected mode
    req2 = CreateJobRequest(folder=str(d), file_ids=["invalid_json"], scope="selected")
    job2 = create_job(req2)
    assert len(job2.files) == 1

def test_job_retry_logic(tmp_path, test_dir):
    d, _ = test_dir
    jm = JobManager(str(tmp_path / "jobs.json"))
    # We create job manually to bypass create_job restrictions on existing DONE files for this test
    job = jm.create_job(str(d), ["done", "no_srt", "some_file"])

    # Force some states
    job.files["done"] = FileStatus.CRASHED # Actually done on disk
    job.files["no_srt"] = FileStatus.STOPPED # Incomplete on disk
    job.files["some_file"] = FileStatus.FAILED # Doesn't exist on disk (WAV file)
    jm.update_job(job)

    from src.api.routes import JobActionRequest, job_action
    import src.api.routes
    src.api.routes.job_manager = jm

    job_action(job.job_id, JobActionRequest(action="retry"))

    updated_job = jm.get_job(job.job_id)
    assert updated_job.files["done"] == FileStatus.DONE # Reconciled from filesystem
    assert updated_job.files["no_srt"] == FileStatus.WAITING
    assert updated_job.files["some_file"] == FileStatus.WAITING

def test_job_retry_all_done(tmp_path, test_dir):
    d, _ = test_dir
    jm = JobManager(str(tmp_path / "jobs.json"))
    job = jm.create_job(str(d), ["done"])
    job.files["done"] = FileStatus.CRASHED
    jm.update_job(job)

    from src.api.routes import JobActionRequest, job_action
    import src.api.routes
    src.api.routes.job_manager = jm

    # Retry when all are DONE on disk
    job_action(job.job_id, JobActionRequest(action="retry"))

    updated_job = jm.get_job(job.job_id)
    assert updated_job.files["done"] == FileStatus.DONE
    assert updated_job.status == FileStatus.DONE

def test_stop_cancel_consistency(tmp_path):
    jm = JobManager(str(tmp_path / "jobs.json"))
    job = jm.create_job("folder", ["f1", "f2", "f3", "f4"])

    import src.api.routes
    src.api.routes.job_manager = jm
    from src.api.routes import JobActionRequest, job_action
    from fastapi import HTTPException
    import pytest

    # Test Stop on WAITING -> rejected
    with pytest.raises(HTTPException):
        job_action(job.job_id, JobActionRequest(action="stop"))

    job.status = FileStatus.TRANSCRIBING
    job.files["f1"] = FileStatus.DONE
    job.files["f2"] = FileStatus.TRANSCRIBING
    job.files["f3"] = FileStatus.WAITING
    job.files["f4"] = FileStatus.WAITING
    jm.update_job(job)

    # Test Stop
    job_action(job.job_id, JobActionRequest(action="stop"))
    assert job.status == FileStatus.STOPPED
    assert job.files["f1"] == FileStatus.DONE
    assert job.files["f2"] == FileStatus.STOPPED # Active becomes STOPPED
    assert job.files["f3"] == FileStatus.WAITING # WAITING stays WAITING

    # Reset for Cancel test
    job.status = FileStatus.TRANSCRIBING
    job.files["f2"] = FileStatus.TRANSCRIBING
    job.files["f3"] = FileStatus.WAITING
    job.files["f4"] = FileStatus.WAITING
    jm.update_job(job)

    # Test Cancel
    job_action(job.job_id, JobActionRequest(action="cancel"))
    assert job.status == FileStatus.CANCEL_REQUESTED
    assert job.files["f1"] == FileStatus.DONE
    assert job.files["f2"] == FileStatus.CANCEL_REQUESTED
    assert job.files["f3"] == FileStatus.CANCELLED
    assert job.files["f4"] == FileStatus.CANCELLED
