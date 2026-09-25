import http.server
import csv
import json
import logging
import os
import re
import secrets
import socket
import subprocess
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Optional, Protocol, Tuple
from urllib.parse import parse_qs, urlparse

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


logger = logging.getLogger(__name__)

DRIVE_SCOPE = "https://www.googleapis.com/auth/drive"
OAUTH_CALLBACK_TIMEOUT_SECONDS = 300.0
# Per-HTTP-request socket timeout for every Google Drive API call (list,
# create, update, media upload/download chunks), applied through the
# transport the API client is built with -- never process-wide.
DRIVE_HTTP_TIMEOUT_SECONDS = 60.0
# Overall deadline for a small media download (e.g. the Colab rendezvous
# metadata file). Checked between chunks, each of which is itself bounded
# by DRIVE_HTTP_TIMEOUT_SECONDS.
DRIVE_MEDIA_DOWNLOAD_DEADLINE_SECONDS = 120.0
DRIVE_NETWORK_FAILURE_MESSAGE = (
    "Google Drive 작업 시간이 초과되었거나 네트워크 작업을 완료하지 못했습니다."
)
DRIVE_NETWORK_ERRORS: Tuple[type, ...] = (TimeoutError, socket.timeout, ConnectionError)
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

    def classify(self, job: JobModel, file_id: str, exam_root: str) -> DriveClassification:
        file_metadata = job.file_metadata.get(file_id)
        has_full_metadata = (
            job.course is not None and
            job.subject is not None and
            job.stage is not None and
            file_metadata is not None and
            file_metadata.week is not None and
            file_metadata.lesson is not None and
            file_metadata.normalized_name is not None
        )

        has_partial_metadata = (
            job.course is not None or
            job.subject is not None or
            job.stage is not None or
            file_metadata is not None
        )

        if has_full_metadata:
            course = job.course
            subject = job.subject
            stage = job.stage
            week = int(file_metadata.week)
            lesson = int(file_metadata.lesson)

            subject_folder = f"[{stage}] {subject}"
            week_subject = "중개사법" if subject == "공인중개사법" else subject
            week_folder = f"{course}_{week_subject}_{week}주차"

            return DriveClassification(
                course=course,
                subject=subject,
                week=week,
                lesson=lesson,
                folders=(exam_root, "전사자료", course, subject_folder, week_folder),
            )

        if has_partial_metadata:
            raise DriveError("DRIVE_CLASSIFICATION_FAILED", "일부 메타데이터만 있는 Job은 Google Drive로 분류할 수 없습니다.")

        match = self._standard.fullmatch(file_id)
        if not match:
            raise DriveError("DRIVE_CLASSIFICATION_FAILED", "표준 파일명에서 Drive 분류를 확인할 수 없습니다.")
        course = match.group("course")
        raw_subject = match.group("subject")

        from src.services.classification import KNOWN_SUBJECT_STAGE
        stage = KNOWN_SUBJECT_STAGE.get(raw_subject)

        if course not in COURSES or not stage:
            raise DriveError("DRIVE_CLASSIFICATION_FAILED", "과정 또는 과목을 Google Drive에서 분류할 수 없습니다.")
        week = int(match.group("week"))
        lesson = int(match.group("lesson"))
        subject_folder = f"[{stage}] {raw_subject}"
        week_subject = "중개사법" if raw_subject == "공인중개사법" else raw_subject
        week_folder = f"{course}_{week_subject}_{week}주차"
        return DriveClassification(
            course=course,
            subject=raw_subject,
            week=week,
            lesson=lesson,
            folders=(exam_root, "전사자료", course, subject_folder, week_folder),
        )


class DriveClient(Protocol):
    def find_or_create_folder(self, parent_id: str, name: str) -> str: ...
    def find_file(self, parent_id: str, name: str) -> Optional[str]: ...
    def create_file(self, parent_id: str, name: str, local_path: Path) -> str: ...
    def update_file(self, file_id: str, name: str, local_path: Path) -> str: ...
    def create_text_file(self, parent_id: str, name: str, content: str) -> str: ...
    def update_text_file(self, file_id: str, name: str, content: str) -> str: ...
    def read_text_file(self, file_id: str) -> str: ...


class DriveAuth(Protocol):
    @property
    def state(self) -> DriveAuthState: ...
    def ensure_client(self) -> DriveClient: ...
    def start(self) -> dict: ...
    def complete(self, code: str) -> DriveAuthState: ...


def build_authorized_http(credentials, timeout_seconds: float = DRIVE_HTTP_TIMEOUT_SECONDS):
    """The google-api-python-client transport with an explicit per-request
    socket timeout, so no Drive call relies on an OS/default indefinite wait."""
    import google_auth_httplib2
    import httplib2

    return google_auth_httplib2.AuthorizedHttp(
        credentials, http=httplib2.Http(timeout=timeout_seconds)
    )


def _is_network_failure(exc: BaseException) -> bool:
    if isinstance(exc, DriveError):
        return exc.code == "DRIVE_TIMEOUT"
    if isinstance(exc, DRIVE_NETWORK_ERRORS):
        return True
    try:
        import httplib2

        return isinstance(exc, httplib2.HttpLib2Error)
    except ImportError:
        return False


class GoogleDriveClient:
    def __init__(
        self,
        service,
        download_deadline_seconds: float = DRIVE_MEDIA_DOWNLOAD_DEADLINE_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.service = service
        self.download_deadline_seconds = download_deadline_seconds
        self._clock = clock

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

    def create_text_file(self, parent_id: str, name: str, content: str) -> str:
        from googleapiclient.http import MediaIoBaseUpload
        import io
        media = MediaIoBaseUpload(io.BytesIO(content.encode("utf-8")), mimetype="application/json", resumable=False)
        created = self.service.files().create(
            body={"name": name, "parents": [parent_id]},
            media_body=media,
            fields="id",
        ).execute()
        return created["id"]

    def update_text_file(self, file_id: str, name: str, content: str) -> str:
        from googleapiclient.http import MediaIoBaseUpload
        import io
        media = MediaIoBaseUpload(io.BytesIO(content.encode("utf-8")), mimetype="application/json", resumable=False)
        updated = self.service.files().update(
            fileId=file_id,
            body={"name": name},
            media_body=media,
            fields="id",
        ).execute()
        return updated["id"]

    def read_text_file(self, file_id: str) -> str:
        from googleapiclient.http import MediaIoBaseDownload
        import io
        request = self.service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        deadline = self._clock() + self.download_deadline_seconds
        done = False
        while not done:
            if self._clock() >= deadline:
                raise DriveError("DRIVE_TIMEOUT", DRIVE_NETWORK_FAILURE_MESSAGE)
            _status, done = downloader.next_chunk()
        return fh.getvalue().decode("utf-8")


_CALLBACK_SUCCESS_HTML = (
    "<html><body><p>Google Drive 연결이 완료되었습니다.<br>"
    "이 창을 닫고 소리글로 돌아가세요.</p></body></html>"
)
_CALLBACK_ERROR_HTML = (
    "<html><body><p>Google Drive 연결에 실패했습니다.<br>"
    "이 창을 닫고 소리글에서 다시 시도해 주세요.</p></body></html>"
)


class _CallbackOutcome:
    """Captures at most one result from the loopback listener.

    `resolve()` is safe to call from concurrent requests (only the first
    call wins); everything after is a strict no-op so a duplicate/replayed
    callback can never re-trigger a token exchange.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.consumed = False
        self.code: Optional[str] = None
        self.error: Optional[str] = None
        self.event = threading.Event()

    def resolve(self, code: Optional[str], error: Optional[str]) -> bool:
        with self._lock:
            if self.consumed:
                return False
            self.consumed = True
            self.code = code
            self.error = error
            self.event.set()
            return True


def _make_callback_handler(expected_state: str, outcome: _CallbackOutcome):
    class _Handler(http.server.BaseHTTPRequestHandler):
        # Silence BaseHTTPRequestHandler's default per-request stderr log,
        # which would otherwise print the full request line -- including
        # the `code`/`state` query parameters -- to the process's logs.
        def log_message(self, format: str, *args) -> None:  # noqa: A002
            pass

        def do_GET(self) -> None:  # noqa: N802 - stdlib-mandated name
            query = parse_qs(urlparse(self.path).query)
            state_values = query.get("state", [])
            code_values = query.get("code", [])
            error_values = query.get("error", [])

            if error_values:
                outcome.resolve(None, error_values[0])
                self._respond(_CALLBACK_ERROR_HTML)
                return

            if not state_values or state_values[0] != expected_state:
                # Wrong/missing state: reject this request only, without
                # consuming the outcome -- keep listening for the
                # legitimate callback.
                self.send_response(400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(_CALLBACK_ERROR_HTML.encode("utf-8"))
                return

            if not code_values:
                outcome.resolve(None, "MISSING_CODE")
                self._respond(_CALLBACK_ERROR_HTML)
                return

            outcome.resolve(code_values[0], None)
            self._respond(_CALLBACK_SUCCESS_HTML)

        def _respond(self, html: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))

    return _Handler


class LoopbackCallbackServer:
    """Temporary 127.0.0.1 HTTP listener for the Google OAuth desktop
    redirect. Binds an OS-assigned ephemeral port (never a fixed port such
    as 80, which would require elevation), validates the `state` query
    parameter this flow generated, and captures at most one authorization
    `code`. Never logs the code, the state, or any token.
    """

    def __init__(self, expected_state: str):
        self._outcome = _CallbackOutcome()
        handler = _make_callback_handler(expected_state, self._outcome)
        self._httpd = http.server.HTTPServer(("127.0.0.1", 0), handler)
        self._httpd.timeout = 1.0
        self.port: int = self._httpd.server_address[1]
        self._thread: Optional[threading.Thread] = None

    @property
    def redirect_uri(self) -> str:
        return f"http://127.0.0.1:{self.port}/"

    def start(self) -> None:
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        while not self._outcome.event.is_set():
            try:
                self._httpd.handle_request()
            except (OSError, ValueError):
                # The listener socket was closed from another thread (e.g.
                # `wait_for_code()` timing out and calling `shutdown()`
                # while this thread was blocked in `select()` -- closing a
                # socket registered with a selector on another thread
                # surfaces as ValueError("Invalid file descriptor") here).
                # Nothing left to serve.
                break

    def wait_for_code(self, timeout: float = OAUTH_CALLBACK_TIMEOUT_SECONDS) -> Optional[str]:
        """Blocks (from a background thread, not the request thread) until
        a callback arrives or `timeout` elapses, then shuts the listener
        down either way. Returns the authorization code, or None on
        timeout, state mismatch exhaustion, or an explicit error callback.
        """
        got_result = self._outcome.event.wait(timeout)
        self.shutdown()
        if not got_result or self._outcome.error:
            return None
        return self._outcome.code

    def shutdown(self) -> None:
        try:
            self._httpd.server_close()
        except OSError:
            pass


@dataclass
class OAuthAttempt:
    attempt_id: str
    expected_state: str
    flow: object
    callback_server: LoopbackCallbackServer
    completing: bool = False
    consumed: bool = False


def _resolve_current_windows_sid(run=None) -> str:
    runner = run or subprocess.run
    result = runner(
        ["whoami.exe", "/user", "/fo", "csv", "/nh"],
        capture_output=True,
        text=True,
        check=True,
        shell=False,
    )
    rows = list(csv.reader(result.stdout.splitlines()))
    if len(rows) != 1 or len(rows[0]) < 2 or not rows[0][1].startswith("S-"):
        raise OSError("Could not resolve the current Windows user SID")
    return rows[0][1]


def write_private_file(
    path: Path,
    payload: str,
    *,
    platform_name: Optional[str] = None,
    run=None,
) -> None:
    """Durably publishes UTF-8 data only after private permissions succeed."""
    platform_name = os.name if platform_name is None else platform_name
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    fd: Optional[int] = None
    try:
        fd = os.open(str(temp_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            fd = None
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())

        if platform_name == "nt":
            runner = run or subprocess.run
            sid = _resolve_current_windows_sid(runner)
            runner(
                [
                    "icacls.exe",
                    str(temp_path),
                    "/inheritance:r",
                    "/grant:r",
                    f"*{sid}:(F)",
                ],
                capture_output=True,
                text=True,
                check=True,
                shell=False,
            )
        else:
            os.chmod(temp_path, 0o600)

        os.replace(temp_path, path)
    except Exception:
        if fd is not None:
            os.close(fd)
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


class GoogleOAuthService:
    def __init__(self, credential_path: Path, token_path: Path):
        self.credential_path = credential_path
        self.token_path = token_path
        self._state = DriveAuthState.UNAUTHENTICATED
        self._attempt: Optional[OAuthAttempt] = None
        self._attempt_lock = threading.RLock()

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
            return GoogleDriveClient(
                build(
                    "drive",
                    "v3",
                    http=build_authorized_http(credentials),
                    cache_discovery=False,
                )
            )
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
        except ImportError as exc:
            raise DriveError("DRIVE_LIBRARY_MISSING", "Google Drive runtime dependency가 설치되지 않았습니다.") from exc

        with self._attempt_lock:
            if self._attempt is not None and not self._attempt.consumed:
                raise DriveError(
                    "DRIVE_AUTH_IN_PROGRESS", "Google Drive 인증이 이미 진행 중입니다."
                )
            expected_state = secrets.token_urlsafe(24)
            callback_server = LoopbackCallbackServer(expected_state)
            try:
                flow = Flow.from_client_secrets_file(
                    str(self.credential_path),
                    scopes=[DRIVE_SCOPE],
                    redirect_uri=callback_server.redirect_uri,
                )
                authorization_url, state = flow.authorization_url(
                    access_type="offline",
                    include_granted_scopes="true",
                    prompt="consent",
                    state=expected_state,
                )
                if state != expected_state:
                    raise DriveError(
                        "DRIVE_AUTH_STATE_INVALID", "Google Drive 인증 상태를 만들지 못했습니다."
                    )
                attempt = OAuthAttempt(
                    attempt_id=uuid.uuid4().hex,
                    expected_state=expected_state,
                    flow=flow,
                    callback_server=callback_server,
                )
                self._attempt = attempt
                self._state = DriveAuthState.AUTHORIZING
            except Exception:
                callback_server.shutdown()
                raise

        callback_server.start()
        threading.Thread(
            target=self._await_callback,
            args=(attempt,),
            daemon=True,
        ).start()
        return {"state": state, "authorization_url": authorization_url, "scope": DRIVE_SCOPE}

    def _await_callback(self, attempt: OAuthAttempt) -> None:
        """Runs on a background thread started by `start()`. Waits for the
        system-browser redirect to hit the loopback listener, then
        completes the flow automatically -- the user never pastes a code.
        """
        code = attempt.callback_server.wait_for_code()
        if code is None:
            with self._attempt_lock:
                if self._attempt is attempt and not attempt.completing and not attempt.consumed:
                    attempt.consumed = True
                    self._attempt = None
                    self._state = DriveAuthState.REAUTH_REQUIRED
            return
        try:
            self._complete_attempt(attempt, code)
        except DriveError:
            pass  # complete() already updated self._state on failure

    def complete(self, code: str) -> DriveAuthState:
        with self._attempt_lock:
            attempt = self._attempt
        if attempt is None or not code:
            raise DriveError("DRIVE_AUTH_FLOW_MISSING", "진행 중인 Google Drive 인증이 없습니다.")
        return self._complete_attempt(attempt, code)

    def _complete_attempt(self, attempt: OAuthAttempt, code: str) -> DriveAuthState:
        with self._attempt_lock:
            if (
                self._attempt is not attempt
                or attempt.completing
                or attempt.consumed
                or not code
            ):
                raise DriveError("DRIVE_AUTH_FLOW_MISSING", "진행 중인 Google Drive 인증이 없습니다.")
            attempt.completing = True
        try:
            attempt.flow.fetch_token(code=code)
            self._write_token(attempt.flow.credentials.to_json())
        except Exception as exc:
            with self._attempt_lock:
                attempt.consumed = True
                if self._attempt is attempt:
                    self._attempt = None
                    self._state = DriveAuthState.REAUTH_REQUIRED
            raise DriveError("DRIVE_AUTH_COMPLETE_FAILED", "Google Drive 인증을 완료하지 못했습니다.") from exc
        with self._attempt_lock:
            attempt.consumed = True
            if self._attempt is not attempt:
                raise DriveError("DRIVE_AUTH_FLOW_MISSING", "진행 중인 Google Drive 인증이 없습니다.")
            self._attempt = None
            self._state = DriveAuthState.CONNECTED
            return self._state

    def _write_token(self, payload: str):
        write_private_file(self.token_path, payload)


class DriveUploadService:
    def __init__(
        self,
        jobs: JobManager,
        auth: DriveAuth,
        settings: 'SettingsManager',
        classifier: Optional[DriveClassifier] = None,
        validator: Optional[OutputBundleValidator] = None,
        event_callback: Optional[Callable[[str, str, str], None]] = None,
    ):
        self.jobs = jobs
        self.auth = auth
        self.settings = settings
        self.classifier = classifier or DriveClassifier()
        self.validator = validator or OutputBundleValidator()
        self.event_callback = event_callback
        self._in_flight: set[Tuple[str, str]] = set()
        self._in_flight_lock = threading.Lock()

    def upload(self, job_id: str, file_id: str) -> DriveFileState:
        key = (job_id, file_id)
        with self._in_flight_lock:
            if key in self._in_flight:
                raise DriveError(
                    "DRIVE_UPLOAD_IN_PROGRESS", "이 파일의 Google Drive 업로드가 이미 진행 중입니다."
                )
            self._in_flight.add(key)
        try:
            return self._upload(job_id, file_id)
        finally:
            with self._in_flight_lock:
                self._in_flight.discard(key)

    def mark_failed(self, job_id: str, file_id: str, message: str):
        """Best-effort Drive FAILED marker for an upload that ended with an
        unexpected error. Never touches the Local transcription state."""
        self._set_state(job_id, file_id, DriveStatus.FAILED, message)
        self._event(job_id, "error", "Drive", "Drive upload 실패", file_id)

    def _upload(self, job_id: str, file_id: str) -> DriveFileState:
        job = self.jobs.get_job(job_id)
        if job is None:
            raise KeyError("JOB_NOT_FOUND")
        if job.files.get(file_id) != FileStatus.DONE:
            raise DriveError("LOCAL_RESULT_NOT_DONE", "로컬 전사가 완료된 파일만 Drive에 업로드할 수 있습니다.")

        self._set_state(job_id, file_id, DriveStatus.PENDING)

        try:
            client = self.auth.ensure_client()
        except DriveError as exc:
            self._set_state(job_id, file_id, DriveStatus.AUTH_REQUIRED, exc.user_message)
            self._event(job_id, "error", "Drive", exc.user_message, file_id)
            return self._current(job_id, file_id)

        try:
            exam_root = self.settings.get().drive_exam_root
            classification = self.classifier.classify(job, file_id, exam_root)
        except DriveError as exc:
            self._set_state(job_id, file_id, DriveStatus.CLASSIFICATION_FAILED, exc.user_message)
            self._event(job_id, "error", "Drive", "Drive 분류 실패", file_id)
            return self._current(job_id, file_id)

        try:
            from src.services.renamer import validate_safe_stem
            safe_stem = validate_safe_stem(file_id, "file_id")
            dummy_mp3 = Path(job.folder) / f"{safe_stem}.mp3"
            bundle = BundlePaths.final_for(dummy_mp3)
            self.validator.validate(bundle)
            paths = [bundle.txt, bundle.json, bundle.srt]
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
        except Exception as exc:
            message = (
                DRIVE_NETWORK_FAILURE_MESSAGE
                if _is_network_failure(exc)
                else "Google Drive preflight를 완료하지 못했습니다."
            )
            self._set_state(job_id, file_id, DriveStatus.FAILED, message)
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
        except Exception as exc:
            self._set_state(
                job_id,
                file_id,
                DriveStatus.FAILED,
                DRIVE_NETWORK_FAILURE_MESSAGE
                if _is_network_failure(exc)
                else "Google Drive 파일 업로드에 실패했습니다.",
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


class DriveExecutionService:
    """Runs automatic Drive uploads on their own worker, outside the
    transcription runner, so Drive network I/O can never hold a
    transcription completion. One task per (job, file) at a time; every
    task's failure is contained here and only ever recorded as Drive state.
    A single worker keeps tasks FIFO, which `after_pending_uploads` relies on.
    """

    def __init__(self, upload_service: DriveUploadService, max_workers: int = 1):
        self.upload_service = upload_service
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="sorigul-drive")
        self._futures: Dict[Tuple[str, str], Future] = {}
        self._lock = threading.Lock()

    def submit(self, job_id: str, file_id: str) -> bool:
        key = (job_id, file_id)
        with self._lock:
            existing = self._futures.get(key)
            if existing is not None and not existing.done():
                return False
            future = self._executor.submit(self._run, job_id, file_id)
            self._futures[key] = future
        future.add_done_callback(lambda done: self._forget(key, done))
        return True

    def in_flight(self, job_id: str, file_id: str) -> bool:
        with self._lock:
            future = self._futures.get((job_id, file_id))
            return future is not None and not future.done()

    def after_pending_uploads(self, job_id: str, callback: Callable[[], None]):
        """Runs ``callback`` once every upload already scheduled for this Job
        has finished (inline when there is none)."""
        with self._lock:
            pending = any(
                key[0] == job_id and not future.done() for key, future in self._futures.items()
            )
            if pending:
                self._executor.submit(self._contain, callback)
                return
        self._contain(callback)

    def _run(self, job_id: str, file_id: str):
        try:
            self.upload_service.upload(job_id, file_id)
        except Exception as exc:
            logger.exception("Automatic Drive upload failed for %s/%s", job_id, file_id)
            if isinstance(exc, DriveError) and exc.code == "DRIVE_UPLOAD_IN_PROGRESS":
                return
            message = (
                DRIVE_NETWORK_FAILURE_MESSAGE
                if _is_network_failure(exc)
                else "Google Drive 업로드를 완료하지 못했습니다."
            )
            try:
                self.upload_service.mark_failed(job_id, file_id, message)
            except Exception:
                logger.exception("Could not record Drive failure for %s/%s", job_id, file_id)

    @staticmethod
    def _contain(callback: Callable[[], None]):
        try:
            callback()
        except Exception:
            logger.exception("Post-upload callback failed")

    def _forget(self, key: Tuple[str, str], future: Future):
        with self._lock:
            if self._futures.get(key) is future:
                del self._futures[key]
