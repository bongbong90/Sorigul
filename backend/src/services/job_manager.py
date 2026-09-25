import json
import uuid
import shutil
import threading
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from pydantic import ValidationError
from src.domain.models import FileMetadata, JobModel, FileStatus, JobEvent


class JobStorageError(RuntimeError):
    """jobs.json could not be read, quarantined or written. Raised instead of
    silently resetting or silently dropping Job state; the existing file is
    left in place untouched."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


class JobManager:
    def __init__(self, storage_path: str):
        self.storage_path = Path(storage_path)
        self.jobs: Dict[str, JobModel] = {}
        self._lock = threading.RLock()
        self.load_jobs()

    def load_jobs(self):
        if not self.storage_path.exists():
            return

        # An OS-level read failure (permissions, I/O) says nothing about the
        # file's content: never quarantine or reset on it.
        try:
            raw = self.storage_path.read_bytes()
        except OSError as exc:
            raise JobStorageError(
                "JOB_STORAGE_READ_FAILED", f"작업 기록을 읽을 수 없습니다: {exc}"
            ) from exc

        try:
            data = json.loads(raw.decode('utf-8'))
            if not isinstance(data, dict):
                raise TypeError("Data root is not a dictionary")
            loaded: Dict[str, JobModel] = {}
            needs_save = False
            for k, v in data.items():
                job = JobModel(**v)
                recovered_job, was_recovered = self._recover_job(job)
                loaded[k] = recovered_job
                if was_recovered:
                    needs_save = True
        except (json.JSONDecodeError, UnicodeDecodeError, ValidationError, TypeError, AttributeError):
            self._quarantine_corrupt_file()
            self.jobs = {}
            return

        self.jobs = loaded
        if needs_save:
            self.save_jobs()

    def _quarantine_corrupt_file(self):
        # Quarantine corrupt file (rename instead of copy to clear it)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        quarantine_path = self.storage_path.with_name(f"jobs.corrupt.{timestamp}.json")
        # If for some reason quarantine path exists, append to avoid crash
        if quarantine_path.exists():
            quarantine_path = self.storage_path.with_name(f"jobs.corrupt.{timestamp}_{uuid.uuid4().hex[:4]}.json")
        try:
            self.storage_path.rename(quarantine_path)
        except OSError as exc:
            # The corrupt file stays exactly where it was; starting over with
            # an empty Job list on top of it would be a silent reset.
            raise JobStorageError(
                "JOB_STORAGE_QUARANTINE_FAILED", f"손상된 작업 기록을 격리하지 못했습니다: {exc}"
            ) from exc

    def _recover_job(self, job: JobModel) -> tuple[JobModel, bool]:
        # Convert active states to CRASHED on load
        active_states = {
            FileStatus.PREPARING,
            FileStatus.TRANSCRIBING,
            FileStatus.SAVING,
            FileStatus.VERIFYING,
            FileStatus.CANCEL_REQUESTED
        }

        needs_recovery = False
        if job.status in active_states:
            job.status = FileStatus.CRASHED
            needs_recovery = True

        for file_id, file_status in job.files.items():
            if file_status in active_states:
                job.files[file_id] = FileStatus.CRASHED
                needs_recovery = True

        if needs_recovery:
            # Avoid duplicate CRASHED events
            last_msg = job.events[-1].message if job.events else ""
            if last_msg != "이전 작업이 비정상 종료되어 복구되었습니다.":
                job.events.append(JobEvent(
                    level="warning",
                    category="CRASHED",
                    message="이전 작업이 비정상 종료되어 복구되었습니다.",
                ))

        return job, needs_recovery

    def save_jobs(self):
        with self._lock:
            self._save_jobs_unlocked()

    def _save_jobs_unlocked(self):
        data = {k: v.model_dump(mode='json') for k, v in self.jobs.items()}
        # Unique per invocation, so a failed save only ever cleans up its own temp.
        temp_path = self.storage_path.with_name(f".{self.storage_path.name}.{uuid.uuid4().hex}.tmp")
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            # Atomic replace: the previous jobs.json stays intact on failure.
            temp_path.replace(self.storage_path)
        except OSError as exc:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise JobStorageError(
                "JOB_STORAGE_WRITE_FAILED", f"작업 기록을 저장하지 못했습니다: {exc}"
            ) from exc

    def create_job(
        self,
        folder: str,
        file_ids: List[str],
        engine: str = "local_whisper",
        engine_config: Optional[dict] = None,
        force_retranscribe: bool = False,
        upload_to_drive: bool = False,
        course: Optional[str] = None,
        subject: Optional[str] = None,
        stage: Optional[str] = None,
        file_metadata: Optional[Dict[str, FileMetadata]] = None,
    ) -> JobModel:
        job_id = str(uuid.uuid4())
        job = JobModel(
            job_id=job_id,
            status=FileStatus.WAITING,
            folder=folder,
            engine=engine,
            engine_config=engine_config or {},
            force_retranscribe=force_retranscribe,
            upload_to_drive=upload_to_drive,
            total_files=len(file_ids),
            done_files=0,
            failed_files=0,
            files={fid: FileStatus.WAITING for fid in file_ids},
            course=course,
            subject=subject,
            stage=stage,
            file_metadata=file_metadata or {},
        )
        job.events.append(JobEvent(
            level="info", category="Job", message=f"작업 생성됨 ({len(file_ids)}개 파일)"
        ))

        with self._lock:
            self.jobs[job_id] = job
            try:
                self._save_jobs_unlocked()
            except JobStorageError:
                del self.jobs[job_id]
                raise
            return job

    def get_job(self, job_id: str) -> Optional[JobModel]:
        with self._lock:
            job = self.jobs.get(job_id)
            return job.model_copy(deep=True) if job else None

    def list_jobs(self) -> List[JobModel]:
        with self._lock:
            return [job.model_copy(deep=True) for job in self.jobs.values()]

    def update_job(self, job: JobModel):
        with self._lock:
            previous = self.jobs.get(job.job_id)
            job.updated_at = datetime.now()
            self.jobs[job.job_id] = job
            try:
                self._save_jobs_unlocked()
            except JobStorageError:
                if previous is None:
                    del self.jobs[job.job_id]
                else:
                    self.jobs[job.job_id] = previous
                raise

    def mutate_job(self, job_id: str, mutation) -> Optional[JobModel]:
        """Apply a mutation and persist it while holding the process lock.

        If the mutation raises or persisting fails, the in-memory Job is
        restored, so memory never claims a state jobs.json does not hold; the
        error (e.g. JobStorageError) propagates.
        """
        with self._lock:
            job = self.jobs.get(job_id)
            if job is None:
                return None
            snapshot = job.model_copy(deep=True)
            try:
                mutation(job)
                job.updated_at = datetime.now()
                self._save_jobs_unlocked()
            except BaseException:
                self.jobs[job_id] = snapshot
                raise
            return job.model_copy(deep=True)
