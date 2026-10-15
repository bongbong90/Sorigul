import json
import uuid
import shutil
import threading
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from pydantic import ValidationError
from src.domain.models import FileMetadata, JobModel, FileStatus, JobEvent

class JobManager:
    def __init__(self, storage_path: str):
        self.storage_path = Path(storage_path)
        self.jobs: Dict[str, JobModel] = {}
        self._lock = threading.RLock()
        self.load_jobs()

    def load_jobs(self):
        if not self.storage_path.exists():
            return

        try:
            with open(self.storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if not isinstance(data, dict):
                raise TypeError("Data root is not a dictionary")

            needs_save = False
            for k, v in data.items():
                job = JobModel(**v)
                recovered_job, was_recovered = self._recover_job(job)
                self.jobs[k] = recovered_job
                if was_recovered:
                    needs_save = True

            if needs_save:
                self.save_jobs()

        except (json.JSONDecodeError, ValidationError, TypeError, AttributeError) as e:
            # Quarantine corrupt file (rename instead of copy to clear it)
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            quarantine_path = self.storage_path.with_name(f"jobs.corrupt.{timestamp}.json")
            # If for some reason quarantine path exists, append to avoid crash
            if quarantine_path.exists():
                quarantine_path = self.storage_path.with_name(f"jobs.corrupt.{timestamp}_{uuid.uuid4().hex[:4]}.json")
            self.storage_path.rename(quarantine_path)
            # Reset jobs
            self.jobs = {}

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
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.storage_path.with_suffix('.tmp')
        data = {k: v.model_dump(mode='json') for k, v in self.jobs.items()}

        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        # Atomic replace
        temp_path.replace(self.storage_path)

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
            self._save_jobs_unlocked()
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
            job.updated_at = datetime.now()
            self.jobs[job.job_id] = job
            self._save_jobs_unlocked()

    def mutate_job(self, job_id: str, mutation) -> Optional[JobModel]:
        """Apply a mutation and persist it while holding the process lock."""
        with self._lock:
            job = self.jobs.get(job_id)
            if job is None:
                return None
            mutation(job)
            job.updated_at = datetime.now()
            self._save_jobs_unlocked()
            return job.model_copy(deep=True)
