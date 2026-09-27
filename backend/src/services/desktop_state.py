import threading
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from src.domain.models import FileStatus, JobModel
from src.services.settings import SettingsManager


class ApplicationEvent(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.now)
    level: Literal["info", "warning", "error"]
    category: str
    message: str
    job_id: Optional[str] = None
    file_id: Optional[str] = None
    desktop_intent: Optional[str] = None


class ApplicationEventStore:
    def __init__(self, max_events: int = 500):
        self.max_events = max_events
        self._events: List[ApplicationEvent] = []
        self._lock = threading.Lock()

    def append(self, event: ApplicationEvent):
        with self._lock:
            self._events.append(event)
            if len(self._events) > self.max_events:
                del self._events[: len(self._events) - self.max_events]

    def list(self) -> List[ApplicationEvent]:
        with self._lock:
            return [event.model_copy(deep=True) for event in self._events]


class ShutdownPhase(str, Enum):
    INACTIVE = "inactive"
    COUNTING_DOWN = "counting_down"
    CANCELLED = "cancelled"
    READY_TO_SHUTDOWN = "ready_to_shutdown"


class ShutdownState(BaseModel):
    phase: ShutdownPhase = ShutdownPhase.INACTIVE
    job_id: Optional[str] = None
    deadline: Optional[datetime] = None
    remaining_seconds: Optional[int] = None


class DesktopCoordinator:
    def __init__(self, settings: SettingsManager, events: ApplicationEventStore):
        self.settings = settings
        self.events = events
        self._state = ShutdownState()
        self._lock = threading.Lock()

    def file_completed(self, job_id: str, file_id: str, filename: str):
        if self.settings.get().notifications.file_complete:
            self.events.append(
                ApplicationEvent(
                    level="info",
                    category="Notification",
                    message=f"파일 전사 완료: {filename}",
                    job_id=job_id,
                    file_id=file_id,
                    desktop_intent="FILE_COMPLETED",
                )
            )

    def job_finished(self, job: JobModel):
        settings = self.settings.get()
        if settings.notifications.job_complete:
            self.events.append(
                ApplicationEvent(
                    level="info" if job.status == FileStatus.DONE else "warning",
                    category="Notification",
                    message=f"작업 종료: 성공 {job.done_files}개, 실패 {job.failed_files}개",
                    job_id=job.job_id,
                    desktop_intent="JOB_COMPLETED",
                )
            )

        delay = settings.shutdown.delay_seconds
        # A locally FAILED job still qualifies when the batch ran through to
        # its natural end (per-file failures are normal batch outcomes);
        # STOPPED/CANCELLED and fatal-error early exits keep batch_completed
        # False and are excluded. Drive state is intentionally not consulted.
        batch_finished = job.status in (FileStatus.DONE, FileStatus.FAILED) and job.batch_completed
        if not batch_finished or delay is None:
            return
        with self._lock:
            deadline = datetime.now() + timedelta(seconds=delay)
            phase = ShutdownPhase.READY_TO_SHUTDOWN if delay == 0 else ShutdownPhase.COUNTING_DOWN
            self._state = ShutdownState(
                phase=phase,
                job_id=job.job_id,
                deadline=deadline,
                remaining_seconds=delay,
            )
        self.events.append(
            ApplicationEvent(
                level="warning",
                category="Shutdown",
                message="PC 종료 요청이 준비되었습니다.",
                job_id=job.job_id,
                desktop_intent="SHUTDOWN_COUNTDOWN_STARTED",
            )
        )

    def state(self) -> ShutdownState:
        with self._lock:
            state = self._state.model_copy(deep=True)
            if state.phase == ShutdownPhase.COUNTING_DOWN and state.deadline is not None:
                remaining = max(0, int((state.deadline - datetime.now()).total_seconds() + 0.999))
                state.remaining_seconds = remaining
                if remaining == 0:
                    state.phase = ShutdownPhase.READY_TO_SHUTDOWN
                    self._state = state.model_copy(deep=True)
            return state

    def cancel_shutdown(self) -> ShutdownState:
        with self._lock:
            if self._state.phase in {
                ShutdownPhase.COUNTING_DOWN,
                ShutdownPhase.READY_TO_SHUTDOWN,
            }:
                job_id = self._state.job_id
                self._state = ShutdownState(phase=ShutdownPhase.CANCELLED, job_id=job_id)
                self.events.append(
                    ApplicationEvent(
                        level="info",
                        category="Shutdown",
                        message="사용자가 PC 종료를 취소했습니다.",
                        job_id=job_id,
                        desktop_intent="SHUTDOWN_CANCELLED",
                    )
                )
            return self._state.model_copy(deep=True)
