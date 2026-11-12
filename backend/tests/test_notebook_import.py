import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace
import zipfile

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from colab.sorigul_notebook import load_model, transcribe_once
from src.domain.models import FileStatus, DriveStatus
from src.services.job_manager import JobManager
from src.services.notebook_bundle import build_archive, read_archive, MAX_ARCHIVE_BYTES
from src.services.notebook_import import NotebookImportService
from src.services.results import ResultsService
from src.services.settings import SettingsManager
from src.services.drive import DriveUploadService, DriveExecutionService
from test_drive_results_desktop import FakeAuth, FakeDriveClient

STEM = "개념완성_민법_1주차_1강"
RUNTIME = dict(engine="faster-whisper", model="large-v3", device="cuda", compute_type="float16")
PAYLOAD = dict(text="소리글 전사 확인입니다.", segments=[dict(start=0, end=0.8, text="소리글 전사 확인입니다.")])


@pytest.fixture(scope="module")
def mp3_bytes(tmp_path_factory):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("synthetic MP3 contract requires ffmpeg")
    path = tmp_path_factory.mktemp("notebook-audio") / "audio.mp3"
    subprocess.run([ffmpeg, "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=16000",
                    "-t", "2", "-codec:a", "libmp3lame", str(path)], check=True, timeout=30,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return path.read_bytes()


@pytest.fixture
def fixture(tmp_path, mp3_bytes):
    source = tmp_path / f"{STEM}.mp3"
    source.write_bytes(mp3_bytes)
    jobs = JobManager(str(tmp_path / "state" / "jobs.json"))
    return source, jobs, build_archive(source, PAYLOAD, RUNTIME)


def rewrite(data, change):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    change(files)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return output.getvalue()


def test_notebook_roundtrip_creates_job_and_existing_preview(fixture):
    source, jobs, data = fixture
    job = NotebookImportService(jobs).import_result(source, data)
    assert job.status == job.files[STEM] == FileStatus.DONE
    assert job.engine == "notebook_import" and not job.upload_to_drive and not job.batch_completed
    assert jobs.get_job(job.job_id).engine_config["notebook_runtime"] == RUNTIME
    results = ResultsService()
    scanned = results.scan(str(source.parent))
    assert scanned.counts["complete"] == 1 and scanned.counts["results"] == 3
    txt = next(item for item in scanned.items if item.kind == "TXT")
    assert results.read_text(scanned.scan_id, txt.id, full=True).text == PAYLOAD["text"]
    assert not list(source.parent.glob(".sorigul-import-*"))


@pytest.mark.parametrize("extension", ["txt", "json", "srt"])
def test_existing_partial_results_are_never_overwritten(fixture, extension):
    source, jobs, data = fixture
    target = source.with_suffix("." + extension)
    target.write_bytes(b"existing user result")
    with pytest.raises(FileExistsError):
        NotebookImportService(jobs).import_result(source, data)
    assert target.read_bytes() == b"existing user result"
    assert not jobs.list_jobs()
    assert len(list(source.parent.glob(STEM + ".*"))) == 2


@pytest.mark.parametrize("kind", ["wrong_source", "invalid_utf8", "wrong_srt", "traversal", "missing", "oversize", "runtime", "unordered", "beyond_duration"])
def test_invalid_archive_does_not_publish_results(fixture, kind):
    source, jobs, data = fixture
    def change(files):
        manifest = json.loads(files["manifest.json"])
        if kind == "wrong_source":
            manifest["source"]["sha256"] = "0" * 64
        elif kind == "runtime":
            manifest["runtime"]["model"] = "medium"
        elif kind == "invalid_utf8":
            files["result.txt"] = b"\xff"
        elif kind == "wrong_srt":
            files["result.srt"] = b"1\n00:00:09,000 --> 00:00:10,000\nwrong\n"
        elif kind == "traversal":
            files["../outside.txt"] = b"bad"
        elif kind == "missing":
            del files["result.srt"]
        elif kind in {"unordered", "beyond_duration"}:
            payload = dict(text="test", segments=[dict(start=1, end=1.5, text="one"), dict(start=0, end=0.5, text="zero")])
            if kind == "beyond_duration":
                payload["segments"] = [dict(start=0, end=20, text="bad")]
            files["result.json"] = json.dumps(payload).encode()
        if kind in {"wrong_srt", "unordered", "beyond_duration", "invalid_utf8"}:
            import hashlib
            for name in ("result.txt", "result.json", "result.srt"):
                manifest["files"][name] = {"size": len(files[name]), "sha256": hashlib.sha256(files[name]).hexdigest()}
        files["manifest.json"] = json.dumps(manifest).encode()
    data = b"x" * (MAX_ARCHIVE_BYTES + 1) if kind == "oversize" else rewrite(data, change)
    with pytest.raises((ValueError, UnicodeError)):
        NotebookImportService(jobs).import_result(source, data)
    assert not jobs.list_jobs() and not source.with_suffix(".txt").exists()


def test_job_persistence_failure_rolls_back_only_new_outputs(fixture, monkeypatch):
    source, jobs, data = fixture
    monkeypatch.setattr(jobs, "update_job", lambda _job: (_ for _ in ()).throw(OSError("fake disk failure")))
    with pytest.raises(OSError):
        NotebookImportService(jobs).import_result(source, data)
    assert not source.with_suffix(".txt").exists() and source.exists()


def test_racing_existing_file_survives_rollback(fixture, monkeypatch):
    import src.services.notebook_import as module
    source, jobs, data = fixture
    original = module.os.link
    def raced(candidate, target):
        if target.suffix == ".srt":
            target.write_bytes(b"concurrent user file")
        return original(candidate, target)
    monkeypatch.setattr(module.os, "link", raced)
    with pytest.raises(FileExistsError):
        NotebookImportService(jobs).import_result(source, data)
    assert source.with_suffix(".srt").read_bytes() == b"concurrent user file"
    assert not source.with_suffix(".txt").exists() and not jobs.list_jobs()


def test_lookup_skips_large_or_changed_results_and_original(fixture):
    source, jobs, data = fixture
    service = NotebookImportService(jobs)
    job = service.import_result(source, data)
    assert service.matching_job(source).job_id == job.job_id
    with source.with_suffix(".txt").open("wb") as handle:
        handle.truncate(MAX_ARCHIVE_BYTES + 1)
    assert service.matching_job(source) is None


def test_queued_upload_revalidates_and_generic_retry_cannot_bypass(fixture):
    import threading
    source, jobs, data = fixture
    job = NotebookImportService(jobs).import_result(source, data)
    remote = FakeDriveClient()
    service = DriveUploadService(jobs, FakeAuth(remote), SettingsManager(source.parent / "settings.json"))
    executor = DriveExecutionService(service)
    entered, release = threading.Event(), threading.Event()
    executor._executor.submit(lambda: (entered.set(), release.wait(5)))
    assert entered.wait(5)
    try:
        assert executor.submit(job.job_id, STEM, skip_done=True)
        source.with_suffix(".txt").write_text("changed after request", encoding="utf-8")
    finally:
        release.set()
        executor._executor.shutdown(wait=True)
    assert jobs.get_job(job.job_id).drive[STEM].status == DriveStatus.FAILED
    assert jobs.get_job(job.job_id).files[STEM] == FileStatus.DONE
    assert not remote.files and not remote.folders
    assert service.retry(job.job_id, STEM).status == DriveStatus.FAILED
    assert not remote.files and not remote.folders


def test_upload_uses_snapshot_even_if_source_result_is_edited_mid_network(fixture):
    source, jobs, data = fixture
    job = NotebookImportService(jobs).import_result(source, data)
    expected = source.with_suffix(".txt").read_bytes()
    class EditingClient(FakeDriveClient):
        uploaded = None
        def find_or_create_folder(self, parent, name):
            source.with_suffix(".txt").write_text("concurrent edit", encoding="utf-8")
            return super().find_or_create_folder(parent, name)
        def create_file(self, parent, name, path):
            if path.suffix == ".txt":
                self.uploaded = path.read_bytes()
            return super().create_file(parent, name, path)
    remote = EditingClient()
    service = DriveUploadService(jobs, FakeAuth(remote), SettingsManager(source.parent / "s.json"))
    assert service.upload(job.job_id, STEM).status == DriveStatus.DONE
    assert remote.uploaded == expected


def test_notebook_uses_real_runtime_identity_and_one_inference(fixture):
    source, _jobs, _data = fixture
    calls = []
    def factory(name, **kwargs):
        calls.append((name, kwargs))
        def transcribe(path, **options):
            calls.append((path, options))
            return iter([SimpleNamespace(start=0, end=0.8, text="소리글 전사 확인입니다.")]), SimpleNamespace(language="ko")
        return SimpleNamespace(model=SimpleNamespace(device="cuda", compute_type="float16"), transcribe=transcribe)
    torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: True))
    model, identity = load_model(torch, factory)
    output = source.parent / "result.zip"
    transcribe_once(source, model, identity, output)
    assert calls[0] == ("large-v3", dict(device="cuda", compute_type="float16"))
    assert calls[1][1] == dict(language="ko", beam_size=5, word_timestamps=False)
    assert len(calls) == 2
    assert read_archive(source, output.read_bytes())[1] == RUNTIME
    with pytest.raises(FileExistsError):
        transcribe_once(source, model, identity, output)
    assert len(calls) == 2, "existing output must prevent another inference"
    with pytest.raises(RuntimeError):
        load_model(SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False)), factory)


def test_audio_changed_during_model_call_cannot_be_bound_to_old_transcript(fixture):
    source, _jobs, _data = fixture
    def changed(path):
        with Path(path).open("ab") as handle:
            handle.write(b"changed during inference")
        return PAYLOAD
    import colab.sorigul_notebook as notebook
    from colab.sorigul_colab_bootstrap import RuntimeIdentity
    original = notebook.transcribe_model
    notebook.transcribe_model = lambda _model, path: changed(path)
    try:
        with pytest.raises(ValueError):
            transcribe_once(source, object(), RuntimeIdentity(**RUNTIME), source.parent / "changed.zip")
        assert not (source.parent / "changed.zip").exists()
    finally:
        notebook.transcribe_model = original


@pytest.fixture
def api_fixture(fixture, monkeypatch):
    import src.api.routes as routes
    from src.main import app
    from src.services.transcription_runner import BackgroundExecutionService, TranscriptionRunner
    source, jobs, data = fixture
    drive_client = FakeDriveClient()
    drive = DriveUploadService(jobs, FakeAuth(drive_client), SettingsManager(source.parent / "settings.json"))
    execution = BackgroundExecutionService(TranscriptionRunner(jobs, lambda _job: None))
    uploads = DriveExecutionService(drive)
    for name, value in dict(job_manager=jobs, results_service=ResultsService(), drive_service=drive,
                            execution_service=execution, drive_execution_service=uploads).items():
        monkeypatch.setattr(routes, name, value)
    client = TestClient(app, base_url="http://127.0.0.1:8000")
    scan = client.post("/api/folders/scan", json={"folder": str(source.parent)}).json()
    item = next(item for item in scan["items"] if item["kind"] == "MP3")
    yield client, routes, data, scan, item, drive_client
    uploads._executor.shutdown(wait=True)
    execution._executor.shutdown(wait=True)


def test_import_http_and_drive_failure_retry_idempotence(api_fixture):
    client, routes, data, scan, item, remote = api_fixture
    response = client.post("/api/results/notebook-import", data={"scan_id": scan["scan_id"], "item_id": item["id"]}, files={"archive": ("result.zip", data)})
    assert response.status_code == 200, response.text
    job = response.json()
    assert job["status"] == "DONE" and not remote.files
    lookup = f"/api/results/notebook-import?scan_id={scan['scan_id']}&item_id={item['id']}"
    assert client.get(lookup).json()["job_id"] == job["job_id"]
    remote.fail_name = f"{STEM}.json"
    url = f"/api/jobs/{job['job_id']}/notebook-drive"
    assert client.post(url).status_code == 200
    # Wait only for the already-scheduled Future; never invoke another upload.
    routes.drive_execution_service._executor.submit(lambda: None).result(timeout=5)
    state = client.get(f"/api/jobs/{job['job_id']}").json()
    assert state["status"] == "DONE" and state["drive"][STEM]["status"] == "FAILED"
    remote.fail_name = None
    assert client.post(url).status_code == 200
    routes.drive_execution_service._executor.submit(lambda: None).result(timeout=5)
    assert client.get(f"/api/jobs/{job['job_id']}").json()["drive"][STEM]["status"] == "DONE"
    counts = (len(remote.created), len(remote.updated))
    assert client.post(url).status_code == 200
    routes.drive_execution_service._executor.submit(lambda: None).result(timeout=5)
    assert counts == (len(remote.created), len(remote.updated)) and len(remote.files) == 3


def test_http_rejects_active_run_bad_scan_and_large_body(api_fixture, monkeypatch):
    from src.services.transcription_runner import ExecutionInvariantError
    client, routes, data, scan, item, _remote = api_fixture
    fields = {"scan_id": scan["scan_id"], "item_id": item["id"]}
    monkeypatch.setattr(routes.execution_service, "run_when_idle", lambda _call: (_ for _ in ()).throw(ExecutionInvariantError("active")))
    assert client.post("/api/results/notebook-import", data=fields, files={"archive": ("result.zip", data)}).status_code == 409
    assert client.post("/api/results/notebook-import", content=b"x" * (MAX_ARCHIVE_BYTES + 65537)).status_code == 413
