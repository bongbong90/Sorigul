from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Literal, Optional
from src.services.scanner import FileScanner
from src.services.normalizer import FilenameNormalizer, NormalizationPreview
from src.services.renamer import BundleRenamer
from src.services.job_manager import JobManager
from src.services.transcription_runner import (
    BackgroundExecutionService,
    DefaultEngineResolver,
    TranscriptionRunner,
)
from src.domain.models import (
    BundleStatus,
    DriveFileState,
    FileStatus,
    JobEvent,
    JobModel,
    ScannedFile,
)
from src.services.desktop_state import ApplicationEvent, ApplicationEventStore, DesktopCoordinator
from src.services.drive import DriveError, DriveUploadService, GoogleOAuthService, DRIVE_SCOPE
from src.services.results import FolderScanResult, OpenFolderIntent, ResultsService, TextContent
from src.services.settings import RuntimeSettings, SettingsManager, SettingsPatch
from src.utils.paths import get_app_data_dir

router = APIRouter()

# Simple dependency injection
def get_job_manager():
    data_dir = get_app_data_dir()
    # Let JobManager handle folder creation lazily
    return JobManager(str(data_dir / "jobs.json"))

app_data_dir = get_app_data_dir()
job_manager = get_job_manager()
settings_manager = SettingsManager(app_data_dir / "settings.json")
application_events = ApplicationEventStore()
desktop_coordinator = DesktopCoordinator(settings_manager, application_events)
results_service = ResultsService()
drive_auth = GoogleOAuthService(
    app_data_dir / "auth" / "google_oauth_client.json",
    app_data_dir / "auth" / "google_drive_token.json",
)
drive_service = DriveUploadService(job_manager, drive_auth)
engine_resolver = DefaultEngineResolver()


def handle_file_completed(job_id: str, file_id: str, filename: str):
    desktop_coordinator.file_completed(job_id, file_id, filename)
    completed_job = job_manager.get_job(job_id)
    if completed_job is not None and completed_job.upload_to_drive:
        drive_service.upload(job_id, file_id)


transcription_runner = TranscriptionRunner(
    job_manager,
    engine_resolver,
    file_completed_callback=handle_file_completed,
    job_finished_callback=desktop_coordinator.job_finished,
)
execution_service = BackgroundExecutionService(transcription_runner)

@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/events")
def list_events():
    events = []
    for job in job_manager.list_jobs():
        for event in job.events:
            payload = event.model_dump(mode="json")
            payload["job_id"] = job.job_id
            payload["source"] = "job"
            events.append(payload)
    for event in application_events.list():
        payload = event.model_dump(mode="json")
        payload["source"] = "application"
        events.append(payload)
    events.sort(key=lambda item: item["timestamp"], reverse=True)
    return events

class ScanRequest(BaseModel):
    folder: str

@router.post("/scan", response_model=List[ScannedFile])
def scan_folder(req: ScanRequest):
    scanner = FileScanner(req.folder)
    return scanner.scan()


class FolderScanRequest(BaseModel):
    folder: str
    filter: Literal["all", "complete", "incomplete", "results"] = "all"


@router.post("/folders/scan", response_model=FolderScanResult)
def scan_results(req: FolderScanRequest):
    try:
        return results_service.scan(req.folder, req.filter)
    except (FileNotFoundError, NotADirectoryError, OSError):
        raise HTTPException(status_code=400, detail="전사 폴더를 읽을 수 없습니다.")


@router.get("/folders/{scan_id}/items/{item_id}/preview", response_model=TextContent)
def preview_text(scan_id: str, item_id: str):
    return _read_result_text(scan_id, item_id, full=False)


@router.get("/folders/{scan_id}/items/{item_id}/text", response_model=TextContent)
def full_text(scan_id: str, item_id: str):
    return _read_result_text(scan_id, item_id, full=True)


def _read_result_text(scan_id: str, item_id: str, full: bool):
    try:
        return results_service.read_text(scan_id, item_id, full=full)
    except KeyError:
        raise HTTPException(status_code=404, detail="새로고침 후 파일을 다시 선택해 주세요.")
    except PermissionError:
        raise HTTPException(status_code=403, detail="허용되지 않은 파일 경로입니다.")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="TXT 파일이 존재하지 않습니다.")
    except ValueError as exc:
        message = {
            "TXT_TOO_LARGE": "TXT 파일이 전체 보기 제한보다 큽니다.",
            "TXT_NOT_UTF8": "TXT 파일이 UTF-8 형식이 아닙니다.",
            "UNEXPECTED_EXTENSION": "TXT 파일만 읽을 수 있습니다.",
        }.get(str(exc), "TXT 파일을 읽을 수 없습니다.")
        raise HTTPException(status_code=400, detail=message)
    except OSError:
        raise HTTPException(status_code=400, detail="TXT 파일을 읽을 수 없습니다.")


@router.post("/folders/{scan_id}/open-intent", response_model=OpenFolderIntent)
def open_folder_intent(scan_id: str, item_id: Optional[str] = Query(default=None)):
    try:
        return results_service.open_folder_intent(scan_id, item_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="새로고침 후 폴더를 다시 선택해 주세요.")
    except (PermissionError, ValueError, OSError):
        raise HTTPException(status_code=400, detail="폴더 열기 요청을 만들 수 없습니다.")


@router.get("/settings", response_model=RuntimeSettings)
def get_settings():
    return settings_manager.get()


@router.put("/settings", response_model=RuntimeSettings)
def update_settings(req: SettingsPatch):
    return settings_manager.update(req)


@router.get("/desktop/shutdown")
def get_shutdown_state():
    return desktop_coordinator.state()


@router.post("/desktop/shutdown/cancel")
def cancel_shutdown():
    return desktop_coordinator.cancel_shutdown()


@router.get("/drive/status")
def get_drive_status():
    return {"auth_state": drive_auth.state, "scope": DRIVE_SCOPE}


@router.post("/drive/auth/start")
def start_drive_auth():
    try:
        result = drive_auth.start()
        application_events.append(
            ApplicationEvent(level="info", category="Drive", message="Drive 인증 시작")
        )
        return result
    except DriveError as exc:
        raise HTTPException(status_code=409, detail=exc.user_message)


class DriveAuthCompleteRequest(BaseModel):
    code: str = Field(min_length=1)


@router.post("/drive/auth/complete")
def complete_drive_auth(req: DriveAuthCompleteRequest):
    try:
        state = drive_auth.complete(req.code)
        application_events.append(
            ApplicationEvent(level="info", category="Drive", message="Drive 인증 완료")
        )
        return {"auth_state": state}
    except DriveError as exc:
        raise HTTPException(status_code=400, detail=exc.user_message)

class NormalizeRequest(BaseModel):
    folder: str
    filename: str
    existing_basenames: List[str]

@router.post("/normalize/preview", response_model=NormalizationPreview)
def preview_normalization(req: NormalizeRequest):
    normalizer = FilenameNormalizer()
    return normalizer.normalize(req.filename, set(req.existing_basenames))

class RenameRequest(BaseModel):
    folder: str
    old_stem: str
    new_stem: str

@router.post("/rename")
def apply_rename(req: RenameRequest):
    renamer = BundleRenamer()
    success = renamer.apply_rename(req.folder, req.old_stem, req.new_stem)
    if not success:
        raise HTTPException(status_code=400, detail="Rename failed due to conflict or error.")
    return {"status": "success"}

class CreateJobRequest(BaseModel):
    folder: str
    file_ids: List[str] = Field(default_factory=list)
    force_retranscribe: bool = False
    scope: str = "selected" # "selected" or "all_incomplete"
    engine: str = "local_whisper"
    colab_url: Optional[str] = None
    upload_to_drive: bool = False

@router.post("/jobs", response_model=JobModel)
def create_job(req: CreateJobRequest):
    if req.engine not in {"local_whisper", "direct_colab"}:
        raise HTTPException(status_code=400, detail="Unsupported transcription engine.")
    if req.engine == "direct_colab" and not req.colab_url:
        raise HTTPException(status_code=400, detail="Colab URL is required.")
    scanner = FileScanner(req.folder)
    files = scanner.scan()

    # Filter files
    target_ids = []
    if req.scope == "all_incomplete":
        for f in files:
            if req.force_retranscribe or f.completion_status != BundleStatus.DONE:
                target_ids.append(f.id)
    else:
        for f in files:
            if f.id in req.file_ids:
                if req.force_retranscribe or f.completion_status != BundleStatus.DONE:
                    target_ids.append(f.id)

    if not target_ids:
        raise HTTPException(status_code=400, detail="No eligible files to transcribe.")

    engine_config = {"base_url": req.colab_url} if req.colab_url else {}
    job = job_manager.create_job(
        req.folder,
        target_ids,
        engine=req.engine,
        engine_config=engine_config,
        force_retranscribe=req.force_retranscribe,
        upload_to_drive=req.upload_to_drive,
    )
    return job

@router.get("/jobs", response_model=List[JobModel])
def list_jobs():
    return job_manager.list_jobs()

@router.get("/jobs/{job_id}", response_model=JobModel)
def get_job(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

class JobActionRequest(BaseModel):
    action: str # retry, stop, cancel

@router.post("/jobs/{job_id}/action")
def job_action(job_id: str, req: JobActionRequest):
    active_states = {FileStatus.PREPARING, FileStatus.TRANSCRIBING, FileStatus.SAVING, FileStatus.VERIFYING}

    if req.action == "stop":
        execution_service.request_stop(job_id)

        def stop_mutation(job):
            if job.status not in active_states:
                raise HTTPException(status_code=400, detail="Cannot stop this job.")
            job.status = FileStatus.STOPPED
            for fid, fstatus in job.files.items():
                if fstatus in active_states:
                    job.files[fid] = FileStatus.STOPPED
            job.events.append(JobEvent(level="warning", category="Stop", message="사용자가 전사를 중지함"))

        updated = job_manager.mutate_job(job_id, stop_mutation)

    elif req.action == "cancel":
        execution_service.request_cancel(job_id)

        def cancel_mutation(job):
            is_active = job.status in active_states
            if job.status not in {FileStatus.WAITING, *active_states}:
                raise HTTPException(status_code=400, detail="Cannot cancel this job.")
            job.status = FileStatus.CANCEL_REQUESTED if is_active else FileStatus.CANCELLED
            for fid, fstatus in job.files.items():
                if fstatus in active_states:
                    job.files[fid] = FileStatus.CANCEL_REQUESTED
                elif fstatus == FileStatus.WAITING:
                    job.files[fid] = FileStatus.CANCELLED
            message = "작업 취소 요청됨" if is_active else "작업 취소됨"
            job.events.append(JobEvent(level="warning", category="Cancel", message=message))

        updated = job_manager.mutate_job(job_id, cancel_mutation)

    elif req.action == "retry":
        # Reset failed/stopped/cancelled/crashed to waiting, checking filesystem truth
        current = job_manager.get_job(job_id)
        if not current:
            raise HTTPException(status_code=404, detail="Job not found")
        scanner = FileScanner(current.folder)
        scanned_files = {f.id: f.completion_status for f in scanner.scan()}

        def retry_mutation(job):
            retried_any = False
            for fid, fstatus in job.files.items():
                if fstatus in {FileStatus.FAILED, FileStatus.STOPPED, FileStatus.CANCELLED, FileStatus.CRASHED}:
                    if scanned_files.get(fid) == BundleStatus.DONE:
                        job.files[fid] = FileStatus.DONE
                    else:
                        job.files[fid] = FileStatus.WAITING
                        retried_any = True
            if not retried_any:
                if all(state == FileStatus.DONE for state in job.files.values()):
                    job.status = FileStatus.DONE
                    job.events.append(JobEvent(level="info", category="Retry", message="재시도할 미완료 파일 없음"))
                    return
                raise HTTPException(status_code=400, detail="No eligible files to retry.")
            job.status = FileStatus.WAITING
            job.error = None
            job.events.append(JobEvent(level="info", category="Retry", message="재시도 시작"))

        updated = job_manager.mutate_job(job_id, retry_mutation)

    else:
        raise HTTPException(status_code=400, detail="Unknown job action.")

    if updated is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return updated


@router.post("/jobs/{job_id}/start", response_model=JobModel, status_code=202)
def start_job(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not execution_service.start(job_id):
        raise HTTPException(status_code=409, detail="Job cannot be started in its current state.")
    return job_manager.get_job(job_id)


@router.post(
    "/jobs/{job_id}/files/{file_id}/drive",
    response_model=DriveFileState,
)
def upload_drive(job_id: str, file_id: str):
    try:
        return drive_service.upload(job_id, file_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Job을 찾을 수 없습니다.")
    except DriveError as exc:
        raise HTTPException(status_code=400, detail=exc.user_message)


@router.post(
    "/jobs/{job_id}/files/{file_id}/drive/retry",
    response_model=DriveFileState,
)
def retry_drive(job_id: str, file_id: str):
    try:
        return drive_service.retry(job_id, file_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Job을 찾을 수 없습니다.")
    except DriveError as exc:
        raise HTTPException(status_code=400, detail=exc.user_message)
