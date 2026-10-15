import json
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Protocol

from src.domain.models import (
    DriveAuthState,
    DriveFileState,
    DriveStatus,
    FileStatus,
    JobEvent,
    JobModel,
)
from src.services.job_manager import JobManager
from src.services.output_bundle import BundlePaths, OutputBundleValidator
from src.services.scanner import FileScanner


DRIVE_SCOPE = "https://www.googleapis.com/auth/drive"
DRIVE_ROOT_HIERARCHY = ("2026 제37회 공인중개사 자격시험", "전사자료")
COURSES = {"개념완성", "기본이론", "기초이론", "핵심이론"}
SUBJECT_ALIASES = {
    "민법": "민법",
    "부동산학개론": "부동산학개론",
    "학개론": "부동산학개론",
    "공인중개사법": "공인중개사법",
    "중개사법": "공인중개사법",
    "부동산공시법": "부동산공시법",
    "공시법": "부동산공시법",
    "부동산공법": "부동산공법",
    "공법": "부동산공법",
    "부동산세법": "부동산세법",
    "세법": "부동산세법",
}
FIRST_STAGE_SUBJECTS = {"민법", "부동산학개론"}


class DriveError(RuntimeError):
    def __init__(self, code: str, user_message: str):
        super().__init__(user_message)
        self.code = code
        self.user_message = user_message


@dataclass(frozen=True)
class DriveClassification:
    course: str
    subject: str
    week: int
    lesson: int
    folders: tuple[str, ...]


class DriveClassifier:
    _standard = re.compile(r"^(?P<course>[^_]+)_(?P<subject>[^_]+)_(?P<week>\d+)주차_(?P<lesson>\d+)강$")

    def classify(self, filename: str) -> DriveClassification:
        match = self._standard.fullmatch(Path(filename).stem)
        if not match:
            raise DriveError("DRIVE_CLASSIFICATION_FAILED", "표준 파일명에서 Drive 분류를 확인할 수 없습니다.")
        course = match.group("course")
        raw_subject = match.group("subject")
        subject = SUBJECT_ALIASES.get(raw_subject)
        if course not in COURSES or subject is None:
            raise DriveError("DRIVE_CLASSIFICATION_FAILED", "과정 또는 과목을 Google Drive에서 분류할 수 없습니다.")
        week = int(match.group("week"))
        lesson = int(match.group("lesson"))
        stage = "1차" if subject in FIRST_STAGE_SUBJECTS else "2차"
        subject_folder = f"[{stage}] {subject}"
        week_subject = "중개사법" if subject == "공인중개사법" else subject
        week_folder = f"{course}_{week_subject}_{week}주차"
        return DriveClassification(
            course=course,
            subject=subject,
            week=week,
            lesson=lesson,
            folders=(*DRIVE_ROOT_HIERARCHY, course, subject_folder, week_folder),
        )


class DriveClient(Protocol):
    def find_or_create_folder(self, parent_id: str, name: str) -> str: ...
    def find_file(self, parent_id: str, name: str) -> Optional[str]: ...
    def create_file(self, parent_id: str, name: str, local_path: Path) -> str: ...
    def update_file(self, file_id: str, name: str, local_path: Path) -> str: ...


class DriveAuth(Protocol):
    @property
    def state(self) -> DriveAuthState: ...
    def ensure_client(self) -> DriveClient: ...
    def start(self) -> dict: ...
    def complete(self, code: str) -> DriveAuthState: ...


class GoogleDriveClient:
    def __init__(self, service):
        self.service = service

    @staticmethod
    def _escape(value: str) -> str:
        return value.replace("\\", "\\\\").replace("'", "\\'")

    def find_or_create_folder(self, parent_id: str, name: str) -> str:
        query = (
            f"'{self._escape(parent_id)}' in parents and "
            f"name = '{self._escape(name)}' and "
            "mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        )
        files = self.service.files().list(q=query, fields="files(id,name)", pageSize=10).execute().get("files", [])
        if files:
            return files[0]["id"]
        created = self.service.files().create(
            body={
                "name": name,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [parent_id],
            },
            fields="id",
        ).execute()
        return created["id"]

    def find_file(self, parent_id: str, name: str) -> Optional[str]:
        query = (
            f"'{self._escape(parent_id)}' in parents and "
            f"name = '{self._escape(name)}' and trashed = false"
        )
        files = self.service.files().list(q=query, fields="files(id,name)", pageSize=10).execute().get("files", [])
        return files[0]["id"] if files else None

    def create_file(self, parent_id: str, name: str, local_path: Path) -> str:
        from googleapiclient.http import MediaFileUpload

        created = self.service.files().create(
            body={"name": name, "parents": [parent_id]},
            media_body=MediaFileUpload(str(local_path), resumable=False),
            fields="id",
        ).execute()
        return created["id"]

    def update_file(self, file_id: str, name: str, local_path: Path) -> str:
        from googleapiclient.http import MediaFileUpload

        updated = self.service.files().update(
            fileId=file_id,
            body={"name": name},
            media_body=MediaFileUpload(str(local_path), resumable=False),
            fields="id",
        ).execute()
        return updated["id"]


class GoogleOAuthService:
    def __init__(self, credential_path: Path, token_path: Path):
        self.credential_path = credential_path
        self.token_path = token_path
        self._state = DriveAuthState.UNAUTHENTICATED
        self._flow = None

    @property
    def state(self) -> DriveAuthState:
        return self._state

    def ensure_client(self) -> DriveClient:
        if not self.token_path.exists():
            self._state = DriveAuthState.UNAUTHENTICATED
            raise DriveError("DRIVE_AUTH_REQUIRED", "Google Drive 연결이 필요합니다.")
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build

            credentials = Credentials.from_authorized_user_file(str(self.token_path), [DRIVE_SCOPE])
            if credentials.expired and credentials.refresh_token:
                try:
                    credentials.refresh(Request())
                    self._write_token(credentials.to_json())
                except Exception as exc:
                    self._state = DriveAuthState.REFRESH_FAILED
                    raise DriveError("DRIVE_TOKEN_REFRESH_FAILED", "Google Drive 인증 갱신에 실패했습니다. 다시 연결해 주세요.") from exc
            if not credentials.valid:
                self._state = DriveAuthState.REAUTH_REQUIRED
                raise DriveError("DRIVE_REAUTH_REQUIRED", "Google Drive를 다시 연결해 주세요.")
            self._state = DriveAuthState.CONNECTED
            return GoogleDriveClient(build("drive", "v3", credentials=credentials, cache_discovery=False))
        except DriveError:
            raise
        except ImportError as exc:
            raise DriveError("DRIVE_LIBRARY_MISSING", "Google Drive runtime dependency가 설치되지 않았습니다.") from exc
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            self._state = DriveAuthState.REAUTH_REQUIRED
            raise DriveError("DRIVE_TOKEN_INVALID", "Google Drive 인증 정보가 손상되었습니다. 다시 연결해 주세요.") from exc

    def start(self) -> dict:
        if not self.credential_path.exists():
            self._state = DriveAuthState.REAUTH_REQUIRED
            raise DriveError(
                "DRIVE_CREDENTIAL_PROVISIONING_REQUIRED",
                "배포용 Google OAuth credential provisioning이 필요합니다.",
            )
        try:
            from google_auth_oauthlib.flow import Flow

            self._flow = Flow.from_client_secrets_file(
                str(self.credential_path),
                scopes=[DRIVE_SCOPE],
                redirect_uri="http://127.0.0.1",
            )
            authorization_url, state = self._flow.authorization_url(
                access_type="offline",
                include_granted_scopes="true",
                prompt="consent",
            )
            self._state = DriveAuthState.AUTHORIZING
            return {"state": state, "authorization_url": authorization_url, "scope": DRIVE_SCOPE}
        except ImportError as exc:
            raise DriveError("DRIVE_LIBRARY_MISSING", "Google Drive runtime dependency가 설치되지 않았습니다.") from exc

    def complete(self, code: str) -> DriveAuthState:
        if self._flow is None or not code:
            raise DriveError("DRIVE_AUTH_FLOW_MISSING", "진행 중인 Google Drive 인증이 없습니다.")
        try:
            self._flow.fetch_token(code=code)
            self._write_token(self._flow.credentials.to_json())
            self._flow = None
            self._state = DriveAuthState.CONNECTED
            return self._state
        except Exception as exc:
            self._state = DriveAuthState.REAUTH_REQUIRED
            raise DriveError("DRIVE_AUTH_COMPLETE_FAILED", "Google Drive 인증을 완료하지 못했습니다.") from exc

    def _write_token(self, payload: str):
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.token_path.with_name(f".{self.token_path.name}.{uuid.uuid4().hex}.tmp")
        temp_path.write_text(payload, encoding="utf-8")
        temp_path.replace(self.token_path)


class DriveUploadService:
    def __init__(
        self,
        jobs: JobManager,
        auth: DriveAuth,
        classifier: Optional[DriveClassifier] = None,
        validator: Optional[OutputBundleValidator] = None,
        event_callback: Optional[Callable[[str, str, str], None]] = None,
    ):
        self.jobs = jobs
        self.auth = auth
        self.classifier = classifier or DriveClassifier()
        self.validator = validator or OutputBundleValidator()
        self.event_callback = event_callback

    def upload(self, job_id: str, file_id: str) -> DriveFileState:
        job = self.jobs.get_job(job_id)
        if job is None:
            raise KeyError("JOB_NOT_FOUND")
        if job.files.get(file_id) != FileStatus.DONE:
            raise DriveError("LOCAL_RESULT_NOT_DONE", "로컬 전사가 완료된 파일만 Drive에 업로드할 수 있습니다.")
        source_item = next((item for item in FileScanner(job.folder).scan() if item.id == file_id), None)
        if source_item is None:
            raise DriveError("LOCAL_SOURCE_MISSING", "원본 MP3 파일을 찾을 수 없습니다.")
        source = Path(source_item.source_path)
        self._set_state(job_id, file_id, DriveStatus.PENDING)

        try:
            client = self.auth.ensure_client()
        except DriveError as exc:
            self._set_state(job_id, file_id, DriveStatus.AUTH_REQUIRED, exc.user_message)
            self._event(job_id, "error", "Drive", exc.user_message, file_id)
            return self._current(job_id, file_id)

        try:
            classification = self.classifier.classify(source.name)
        except DriveError as exc:
            self._set_state(job_id, file_id, DriveStatus.CLASSIFICATION_FAILED, exc.user_message)
            self._event(job_id, "error", "Drive", "Drive 분류 실패", file_id)
            return self._current(job_id, file_id)

        try:
            bundle = BundlePaths.final_for(source)
            self.validator.validate(bundle)
            paths = [source, bundle.txt, bundle.json, bundle.srt]
            for path in paths:
                if not path.exists() or not path.is_file():
                    raise DriveError("DRIVE_PREFLIGHT_MISSING", f"업로드 파일이 없습니다: {path.name}")
                with path.open("rb") as handle:
                    handle.read(1)

            parent_id = "root"
            for folder_name in classification.folders:
                parent_id = client.find_or_create_folder(parent_id, folder_name)
        except DriveError as exc:
            self._set_state(job_id, file_id, DriveStatus.FAILED, exc.user_message)
            self._event(job_id, "error", "Drive", "Drive preflight 실패", file_id)
            return self._current(job_id, file_id)
        except Exception:
            self._set_state(job_id, file_id, DriveStatus.FAILED, "Google Drive preflight를 완료하지 못했습니다.")
            self._event(job_id, "error", "Drive", "Drive preflight 실패", file_id)
            return self._current(job_id, file_id)

        self._set_state(job_id, file_id, DriveStatus.UPLOADING)
        self._event(job_id, "info", "Drive", "Drive upload 시작", file_id)
        remote_ids: dict[str, str] = {}
        try:
            for path in paths:
                existing_id = client.find_file(parent_id, path.name)
                if existing_id:
                    remote_id = client.update_file(existing_id, path.name, path)
                else:
                    remote_id = client.create_file(parent_id, path.name, path)
                remote_ids[path.name] = remote_id
                self._event(job_id, "info", "Drive", f"Drive 파일 upload 완료: {path.name}", file_id)
        except Exception:
            self._set_state(
                job_id,
                file_id,
                DriveStatus.FAILED,
                "Google Drive 파일 업로드에 실패했습니다.",
                remote_ids,
            )
            self._event(job_id, "error", "Drive", "Drive upload 실패", file_id)
            return self._current(job_id, file_id)

        self._set_state(job_id, file_id, DriveStatus.DONE, remote_ids=remote_ids)
        self._event(job_id, "info", "Drive", "Drive bundle 완료", file_id)
        return self._current(job_id, file_id)

    def retry(self, job_id: str, file_id: str) -> DriveFileState:
        self._event(job_id, "info", "Drive", "Drive retry", file_id)
        return self.upload(job_id, file_id)

    def _set_state(
        self,
        job_id: str,
        file_id: str,
        status: DriveStatus,
        error: Optional[str] = None,
        remote_ids: Optional[dict[str, str]] = None,
    ):
        def mutation(job: JobModel):
            previous = job.drive.get(file_id, DriveFileState())
            job.drive[file_id] = DriveFileState(
                status=status,
                error=error,
                remote_file_ids=remote_ids if remote_ids is not None else previous.remote_file_ids,
            )

        self.jobs.mutate_job(job_id, mutation)

    def _event(self, job_id: str, level: str, category: str, message: str, file_id: str):
        def mutation(job: JobModel):
            job.events.append(
                JobEvent(level=level, category=category, message=message, file_id=file_id, filename=f"{file_id}.mp3")
            )

        self.jobs.mutate_job(job_id, mutation)
        if self.event_callback:
            self.event_callback(level, category, message)

    def _current(self, job_id: str, file_id: str) -> DriveFileState:
        job = self.jobs.get_job(job_id)
        if job is None:
            raise KeyError("JOB_NOT_FOUND")
        return job.drive[file_id]
