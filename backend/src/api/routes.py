from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
from src.services.scanner import FileScanner
from src.services.normalizer import FilenameNormalizer, NormalizationPreview
from src.services.renamer import BundleRenamer
from src.services.job_manager import JobManager
from src.services.transcription_runner import (
    BackgroundExecutionService,
    DefaultEngineResolver,
    TranscriptionRunner,
)
from src.domain.models import ScannedFile, JobModel, FileStatus, BundleStatus, JobEvent

router = APIRouter()

# Simple dependency injection
def get_job_manager():
    from src.utils.paths import get_app_data_dir
    data_dir = get_app_data_dir()
    # Let JobManager handle folder creation lazily
    return JobManager(str(data_dir / "jobs.json"))

job_manager = get_job_manager()
engine_resolver = DefaultEngineResolver()
transcription_runner = TranscriptionRunner(job_manager, engine_resolver)
execution_service = BackgroundExecutionService(transcription_runner)

@router.get("/health")
def health():
    return {"status": "ok"}

class ScanRequest(BaseModel):
    folder: str

@router.post("/scan", response_model=List[ScannedFile])
def scan_folder(req: ScanRequest):
    scanner = FileScanner(req.folder)
    return scanner.scan()

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
