"""#246: offline Drive folder tree, account binding and immutable Job routing.

All API calls below are TestClient requests or an in-memory Google SDK double.
No token/credential or real user directory is read and no cloud call is made.
"""
import copy
import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.domain.models import DriveDestination, DriveParentFolder, DriveStatus, FileStatus
from src.services.drive import DriveAuthState, DriveError, DriveUploadService, GoogleDriveClient
from src.services.drive_destination import DriveDestinationService, DriveFolderSelection, FOLDER_MIME
from src.services.job_manager import JobManager
from src.services.settings import SettingsManager, SettingsPatch


class Request:
    def __init__(self, action):
        self.action = action

    def execute(self):
        return copy.deepcopy(self.action())


class MockGoogle:
    """Exercise production GoogleDriveClient queries and upload-or-update too."""
    def __init__(self):
        self.identity = "account-A"
        self.nodes = {}
        self.calls = []
        self.created = []
        self.updated = []
        self.denied = set()
        self.fail_upload = False
        self.add("my-root", "My Drive", None)
        self.add("alpha", "공부 자료 📚", "my-root")
        self.add("duplicate", "공부 자료 📚", "my-root")
        self.add("nested", "한글 Δ 子", "alpha")
        self.add("readonly", "읽기 전용", "my-root", writable=False)
        self.add("trash", "휴지통 폴더", "my-root", trashed=True)
        self.add("mp3", "audio.mp3", "my-root", mime="audio/mpeg")

    def add(self, node_id, name, parent, *, writable=True, trashed=False, mime=FOLDER_MIME):
        self.nodes[node_id] = dict(id=node_id, name=name, mimeType=mime, trashed=trashed,
                                   parents=[parent] if parent else [], capabilities={"canAddChildren": writable})

    def files(self):
        return self

    def about(self):
        sdk = self
        class About:
            def get(self, **kwargs):
                assert kwargs == {"fields": "user(permissionId)"}
                return Request(lambda: {"user": {"permissionId": sdk.identity}})
        return About()

    def get(self, fileId, **kwargs):
        self.calls.append(("get", fileId, kwargs))
        def execute():
            key = "my-root" if fileId == "root" else fileId
            if key in self.denied:
                raise PermissionError("secret OAuth_token_should_never_escape")
            return self.nodes[key]
        return Request(execute)

    def list(self, **kwargs):
        self.calls.append(("list", kwargs))
        def execute():
            query = kwargs["q"]
            parent = re.search(r"^'([^']+)' in parents", query).group(1)
            if parent == "root":
                parent = "my-root"
            match = re.search(r"name = '([^']+)'", query)
            folder_only = "mimeType = " in query
            nodes = [value for value in self.nodes.values()
                     if value["parents"] == [parent] and not value["trashed"]
                     and (value["mimeType"] == FOLDER_MIME) == folder_only
                     and (match is None or value["name"] == match.group(1))]
            return {"files": nodes}
        return Request(execute)

    def create(self, body, fields, media_body=None):
        assert fields == "id"
        def execute():
            if self.fail_upload and media_body is not None:
                raise ConnectionError("secret remote error")
            key = f"new-{len(self.nodes)}"
            parent = "my-root" if body["parents"][0] == "root" else body["parents"][0]
            self.add(key, body["name"], parent,
                     mime=body.get("mimeType", "text/plain"))
            self.created.append((key, copy.deepcopy(body)))
            return {"id": key}
        return Request(execute)

    def update(self, fileId, body, media_body, fields):
        def execute():
            self.updated.append(fileId)
            return {"id": fileId}
        return Request(execute)


class Auth:
    state = DriveAuthState.CONNECTED

    def __init__(self, sdk):
        self.sdk = sdk
        self.error = None

    def ensure_client(self):
        if self.error:
            raise self.error
        return GoogleDriveClient(self.sdk)


@pytest.fixture
def environment(tmp_path):
    sdk = MockGoogle()
    auth = Auth(sdk)
    settings = SettingsManager(tmp_path / "settings.json")
    return sdk, auth, settings, DriveDestinationService(auth, settings)


def select(service, folder="alpha", account="account-A"):
    return service.select(DriveFolderSelection(folder_id=folder, account_id=account))


def done_job(tmp_path, settings, *, parent=True):
    folder = tmp_path / "합성 결과"
    folder.mkdir(exist_ok=True)
    stem = "개념완성_민법_8주차_4강"
    (folder / f"{stem}.mp3").write_bytes(b"synthetic MP3 placeholder, never uploaded")
    (folder / f"{stem}.txt").write_text("한국어 합성 전사 결과 " * 60, encoding="utf-8")
    (folder / f"{stem}.json").write_text(json.dumps({"text": "합성", "segments": [{"start": 0, "end": 1, "text": "합성"}]}), encoding="utf-8")
    (folder / f"{stem}.srt").touch()
    manager = JobManager(str(tmp_path / "jobs.json"))
    current = settings.get()
    job = manager.create_job(str(folder), [stem], drive_destination=DriveDestination(
        parent=current.drive_parent if parent else None, exam_root=current.drive_exam_root,
    ))
    job.files[stem] = FileStatus.DONE
    job.status = FileStatus.DONE
    manager.update_job(job)
    return manager, job, stem, folder


def test_browse_folder_only_unicode_duplicate_names_and_parent(environment):
    sdk, _, _, service = environment
    page = service.browse()
    assert {child.folder_id for child in page.children} == {"alpha", "duplicate", "readonly"}
    assert sum(child.name == "공부 자료 📚" for child in page.children) == 2
    assert not next(child for child in page.children if child.folder_id == "readonly").can_select
    nested = service.browse("nested", page.account_id)
    assert [part.name for part in nested.breadcrumbs] == ["내 드라이브", "공부 자료 📚", "한글 Δ 子"]
    assert nested.breadcrumbs[-2].folder_id == "alpha"
    assert all(node[0] != "create" for node in sdk.calls)


def test_confirm_persists_verified_id_account_and_server_path_then_reset(environment):
    _, _, settings, service = environment
    assert settings.get().drive_parent is None
    result = select(service, "duplicate")
    parent = result.drive_parent
    assert parent.folder_id == "duplicate"
    assert parent.account_id == "account-A"
    assert parent.display_path == "내 드라이브 / 공부 자료 📚"
    assert SettingsManager(settings.storage_path).get().drive_parent == parent
    assert service.reset().drive_parent is None
    assert settings.get().drive_exam_root == "2026 제37회 공인중개사 자격시험"


@pytest.mark.parametrize("fault", ["deleted", "trashed", "revoked", "readonly", "file", "account", "unknown_account", "ambiguous", "cycle"])
def test_invalid_selection_preserves_saved_location(environment, fault):
    sdk, _, settings, service = environment
    original = select(service).drive_parent
    if fault == "deleted": del sdk.nodes["nested"]
    elif fault == "trashed": sdk.nodes["nested"]["trashed"] = True
    elif fault == "revoked": sdk.denied.add("nested")
    elif fault == "readonly": sdk.nodes["nested"]["capabilities"]["canAddChildren"] = False
    elif fault == "file": sdk.nodes["nested"]["mimeType"] = "text/plain"
    elif fault == "account": sdk.identity = "account-B"
    elif fault == "unknown_account": sdk.identity = ""
    elif fault == "ambiguous": sdk.nodes["nested"]["parents"] = ["alpha", "duplicate"]
    elif fault == "cycle": sdk.nodes["alpha"]["parents"] = ["nested"]
    with pytest.raises(DriveError) as error:
        select(service, "nested")
    assert "secret" not in str(error.value)
    assert settings.get().drive_parent == original


def test_stale_browser_account_is_rejected_before_remote_listing(environment):
    sdk, _, _, service = environment
    initial = service.browse()
    sdk.identity = "account-B"
    sdk.calls.clear()
    with pytest.raises(DriveError, match="계정"):
        service.browse("alpha", initial.account_id)
    assert not sdk.calls


def test_save_failure_is_atomic_and_sanitized(environment, monkeypatch):
    _, _, settings, service = environment
    original = select(service).drive_parent
    def fail(*args): raise OSError("sensitive filesystem path")
    monkeypatch.setattr(settings, "_save", fail)
    for operation in (lambda: select(service, "nested"), service.reset):
        with pytest.raises(DriveError) as error: operation()
        assert "sensitive" not in str(error.value)
        assert settings.get().drive_parent == original


@pytest.mark.parametrize("custom", [False, True])
def test_mock_bundle_e2e_preserves_tree_three_files_and_update_or_create(environment, tmp_path, custom):
    sdk, auth, settings, service = environment
    if custom: select(service)
    settings.update(SettingsPatch(drive_exam_root="시험 이름"))
    manager, job, stem, folder = done_job(tmp_path, settings)
    before = {path.name: path.read_bytes() for path in folder.iterdir()}
    upload = DriveUploadService(manager, auth, settings)
    assert upload.upload(job.job_id, stem).status == DriveStatus.DONE
    assert sdk.created[0][1] == {"name": "시험 이름", "mimeType": FOLDER_MIME, "parents": ["alpha" if custom else "root"]}
    hierarchy = [body["name"] for _, body in sdk.created if body.get("mimeType") == FOLDER_MIME]
    assert hierarchy == ["시험 이름", "전사자료", "개념완성", "[1차] 민법", "개념완성_민법_8주차"]
    uploaded = [body["name"] for _, body in sdk.created if "mimeType" not in body]
    assert set(uploaded) == {f"{stem}.txt", f"{stem}.json", f"{stem}.srt"}
    assert upload.retry(job.job_id, stem).status == DriveStatus.DONE
    assert len(sdk.updated) == 3
    assert {path.name: path.read_bytes() for path in folder.iterdir()} == before
    assert manager.get_job(job.job_id).files[stem] == FileStatus.DONE


def test_job_destination_survives_settings_change_restart_and_retry(environment, tmp_path):
    sdk, auth, settings, selection = environment
    select(selection)
    settings.update(SettingsPatch(drive_exam_root="원래 시험"))
    manager, job, stem, _ = done_job(tmp_path, settings)
    original = job.drive_destination
    select(selection, "duplicate")
    settings.update(SettingsPatch(drive_exam_root="다른 시험"))
    reloaded = JobManager(str(tmp_path / "jobs.json"))
    sdk.fail_upload = True
    uploader = DriveUploadService(reloaded, auth, SettingsManager(settings.storage_path))
    assert uploader.upload(job.job_id, stem).status == DriveStatus.FAILED
    assert reloaded.get_job(job.job_id).status == FileStatus.DONE
    sdk.fail_upload = False
    assert uploader.retry(job.job_id, stem).status == DriveStatus.DONE
    assert sdk.created[0][1]["parents"] == ["alpha"]
    assert sdk.created[0][1]["name"] == "원래 시험"
    assert reloaded.get_job(job.job_id).drive_destination == original
    with pytest.raises(ValidationError): original.exam_root = "changed"
    with pytest.raises(ValidationError): original.parent.folder_id = "duplicate"
    with pytest.raises(ValidationError): job.drive_destination = None


@pytest.mark.parametrize("fault", ["deleted", "trashed", "revoked", "readonly", "account", "ambiguous"])
def test_upload_rechecks_original_folder_and_never_falls_back(environment, tmp_path, fault):
    sdk, auth, settings, selection = environment
    select(selection)
    manager, job, stem, folder = done_job(tmp_path, settings)
    selection.reset()
    if fault == "deleted": del sdk.nodes["alpha"]
    elif fault == "trashed": sdk.nodes["alpha"]["trashed"] = True
    elif fault == "revoked": sdk.denied.add("alpha")
    elif fault == "readonly": sdk.nodes["alpha"]["capabilities"] = {}
    elif fault == "account": sdk.identity = "account-B"
    elif fault == "ambiguous": sdk.nodes["alpha"]["parents"] = ["my-root", "duplicate"]
    sdk.calls.clear()
    result = DriveUploadService(manager, auth, settings).retry(job.job_id, stem)
    assert result.status == DriveStatus.FAILED
    assert sdk.created == sdk.updated == []
    assert not any(call[0] == "list" for call in sdk.calls)
    assert manager.get_job(job.job_id).files[stem] == FileStatus.DONE
    assert (folder / f"{stem}.txt").exists()
    assert "secret" not in json.dumps(manager.get_job(job.job_id).model_dump(mode="json"))


def test_renamed_or_moved_folder_uses_same_id_not_same_name_sibling(environment, tmp_path):
    sdk, auth, settings, selection = environment
    select(selection)
    manager, job, stem, _ = done_job(tmp_path, settings)
    sdk.nodes["alpha"]["name"] = "이름 변경"
    sdk.nodes["alpha"]["parents"] = ["duplicate"]
    assert DriveUploadService(manager, auth, settings).retry(job.job_id, stem).status == DriveStatus.DONE
    assert sdk.created[0][1]["parents"] == ["alpha"]


def test_legacy_jobs_load_without_migration_or_automatic_reupload(environment, tmp_path):
    sdk, auth, settings, _ = environment
    manager, job, stem, _ = done_job(tmp_path, settings)
    payload = json.loads((tmp_path / "jobs.json").read_text(encoding="utf-8"))
    # JobManager storage is a list of serialized Jobs.
    values = payload.values() if isinstance(payload, dict) else payload
    for value in values:
        value.pop("drive_destination", None)
    path = tmp_path / "jobs.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    before = path.read_bytes()
    loaded = JobManager(str(path))
    assert path.read_bytes() == before
    assert loaded.get_job(job.job_id).drive_destination is None
    assert not sdk.created
    result = DriveUploadService(loaded, auth, settings).retry(job.job_id, stem)
    assert result.status == DriveStatus.FAILED
    assert "이전 버전" in result.error
    assert not sdk.created


def test_destination_api_and_creation_snapshot_are_wired(environment, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from src.api import routes
    from src.main import app
    sdk, auth, settings, _ = environment
    manager = JobManager(str(tmp_path / "jobs.json"))
    monkeypatch.setattr(routes, "drive_auth", auth)
    monkeypatch.setattr(routes, "settings_manager", settings)
    monkeypatch.setattr(routes, "job_manager", manager)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert client.get("/api/drive/folders").status_code == 200
        result = client.put("/api/drive/destination", json={"folder_id": "nested", "account_id": "account-A"})
        assert result.status_code == 200
        assert result.json()["drive_parent"]["folder_id"] == "nested"
        assert client.put("/api/settings", json={"drive_parent": None}).status_code == 422
        assert client.put("/api/drive/destination", json={"folder_id": "../path", "account_id": "account-A"}).status_code == 422
        folder = tmp_path / "입력"
        folder.mkdir()
        (folder / "개념완성_민법_1주차_1강.mp3").touch()
        created = client.post("/api/jobs", json={"folder": str(folder), "file_ids": ["개념완성_민법_1주차_1강"], "scope": "selected", "course": "개념완성", "subject": "민법", "week": 1})
        assert created.status_code == 200, created.text
        value = created.json()
        assert value["drive_destination"]["parent"]["folder_id"] == "nested"
        assert value["upload_to_drive"] is False
        assert value["engine"] == "local_whisper"
        assert client.delete("/api/drive/destination").json()["drive_parent"] is None
        assert manager.get_job(value["job_id"]).drive_destination.parent.folder_id == "nested"
        sdk.identity = "account-B"
        assert client.put("/api/drive/destination", json={"folder_id": "alpha", "account_id": "account-A"}).status_code == 409


def test_corrupt_selected_location_never_resets_settings_to_root(environment):
    _, _, settings, selection = environment
    select(selection)
    payload = json.loads(settings.storage_path.read_text(encoding="utf-8"))
    payload["drive_parent"]["folder_id"] = "not/a/drive/id"
    settings.storage_path.write_text(json.dumps(payload), encoding="utf-8")
    original = settings.storage_path.read_bytes()
    with pytest.raises(RuntimeError, match="原本|원본"):
        SettingsManager(settings.storage_path)
    assert settings.storage_path.read_bytes() == original
    assert not list(settings.storage_path.parent.glob("settings.corrupt.*"))


def test_remote_pagination_is_forwarded_with_account_binding(environment, monkeypatch):
    sdk, _, _, service = environment
    original_list = sdk.list
    def list_page(**kwargs):
        result = original_list(**kwargs).execute()
        nodes = result["files"]
        if kwargs.get("pageToken") == "next":
            return Request(lambda: {"files": nodes[1:]})
        return Request(lambda: {"files": nodes[:1], "nextPageToken": "next"})
    monkeypatch.setattr(sdk, "list", list_page)
    first = service.browse()
    second = service.browse(first.folder.folder_id, first.account_id, first.next_page_token)
    assert first.next_page_token == "next"
    assert first.children[0].folder_id not in {node.folder_id for node in second.children}
    assert sdk.calls[-1][1]["pageToken"] == "next"


@pytest.mark.parametrize("error", [TimeoutError("private token"), ConnectionError("private token"), PermissionError("private token")])
def test_connection_errors_are_sanitized_without_mutating_settings(environment, error):
    _, auth, settings, service = environment
    select(service)
    before = settings.storage_path.read_bytes()
    auth.error = error
    with pytest.raises(DriveError) as result:
        select(service)
    assert "private" not in str(result.value)
    assert settings.storage_path.read_bytes() == before


def test_existing_automatic_folder_collision_remains_fail_closed(environment, tmp_path):
    sdk, auth, settings, selection = environment
    select(selection)
    manager, job, stem, _ = done_job(tmp_path, settings)
    sdk.add("exam1", settings.get().drive_exam_root, "alpha")
    sdk.add("exam2", settings.get().drive_exam_root, "alpha")
    result = DriveUploadService(manager, auth, settings).upload(job.job_id, stem)
    assert result.status == DriveStatus.FAILED
    assert "같은 이름" in result.error
    assert sdk.created == []


@pytest.mark.parametrize("state", [FileStatus.FAILED, FileStatus.STOPPED, FileStatus.CANCELLED, FileStatus.CRASHED])
def test_local_retry_after_restart_keeps_original_destination(environment, tmp_path, monkeypatch, state):
    from types import SimpleNamespace
    from src.api import routes
    _, _, settings, selection = environment
    select(selection)
    manager, job, stem, _ = done_job(tmp_path, settings)
    original = job.drive_destination
    job.status = state
    job.files[stem] = state
    job.force_retranscribe = True
    manager.update_job(job)
    select(selection, "duplicate")
    settings.update(SettingsPatch(drive_exam_root="다른 시험"))
    reloaded = JobManager(str(tmp_path / "jobs.json"))
    monkeypatch.setattr(routes, "job_manager", reloaded)
    monkeypatch.setattr(routes, "settings_manager", settings)
    monkeypatch.setattr(routes, "execution_service", SimpleNamespace(active_job_id=lambda: None, is_active=lambda _: False))
    result = routes.job_action(job.job_id, routes.JobActionRequest(action="retry"))
    assert result.status == FileStatus.WAITING
    assert result.files[stem] == FileStatus.WAITING
    assert result.drive_destination == original
    assert reloaded.get_job(job.job_id).drive_destination == original
