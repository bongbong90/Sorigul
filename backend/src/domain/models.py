from enum import Enum
from pydantic import BaseModel, Field
from typing import List, Literal, Optional, Dict, Any
from datetime import datetime

class FileStatus(str, Enum):
    WAITING = "WAITING"
    PREPARING = "PREPARING"
    TRANSCRIBING = "TRANSCRIBING"
    SAVING = "SAVING"
    VERIFYING = "VERIFYING"
    DONE = "DONE"
    FAILED = "FAILED"
    STOPPED = "STOPPED"
    CANCELLED = "CANCELLED"
    CRASHED = "CRASHED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"

class BundleStatus(str, Enum):
    DONE = "DONE"
    INCOMPLETE = "INCOMPLETE"
    INVALID_RESULT = "INVALID_RESULT"


class DriveStatus(str, Enum):
    DISABLED = "DISABLED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    CLASSIFICATION_FAILED = "CLASSIFICATION_FAILED"
    PENDING = "PENDING"
    UPLOADING = "UPLOADING"
    DONE = "DONE"
    FAILED = "FAILED"


class DriveAuthState(str, Enum):
    UNAUTHENTICATED = "UNAUTHENTICATED"
    AUTHORIZING = "AUTHORIZING"
    CONNECTED = "CONNECTED"
    REFRESH_FAILED = "REFRESH_FAILED"
    REAUTH_REQUIRED = "REAUTH_REQUIRED"

class ScannedFile(BaseModel):
    id: str
    filename: str
    source_path: str
    size: int
    modified_at: datetime
    completion_status: BundleStatus
    # True if rename is needed, False if unchanged, None if error in normalize
    needs_rename: Optional[bool] = None

class JobEvent(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.now)
    level: str
    category: str
    message: str
    file_id: Optional[str] = None
    filename: Optional[str] = None


class DriveFileState(BaseModel):
    status: DriveStatus = DriveStatus.DISABLED
    error: Optional[str] = None
    remote_file_ids: Dict[str, str] = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=datetime.now)


class FileMetadata(BaseModel):
    week: Optional[str] = None
    lesson: Optional[str] = None
    # Only set when, at the time this metadata was recorded, the file's
    # on-disk name was already the exact valid standard name for the
    # course/subject typed for this Job. None whenever normalization is
    # unresolved (mismatch, missing week/lesson, or the user chose to
    # continue with the original filename) -- see CORE_WORKFLOW_REFINEMENT_PLAN.md
    # Section 12/28.
    normalized_name: Optional[str] = None


class JobModel(BaseModel):
    job_id: str
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    status: FileStatus
    folder: str
    engine: str
    engine_config: Dict[str, Any] = Field(default_factory=dict)
    force_retranscribe: bool = False
    upload_to_drive: bool = False
    total_files: int
    done_files: int
    failed_files: int
    current_file: Optional[str] = None
    current_progress: Optional[float] = None
    eta_seconds: Optional[float] = None
    files: Dict[str, FileStatus] = Field(default_factory=dict)
    events: List[JobEvent] = Field(default_factory=list)
    drive: Dict[str, DriveFileState] = Field(default_factory=dict)
    error: Optional[str] = None
    # Job-level classification metadata (CORE_WORKFLOW_REFINEMENT_PLAN.md D12/D15/D16).
    # Optional so a Job persisted before this field existed still loads --
    # only newly-created Jobs are guaranteed to have these populated.
    course: Optional[str] = None
    subject: Optional[str] = None
    stage: Optional[Literal["1차", "2차"]] = None
    file_metadata: Dict[str, FileMetadata] = Field(default_factory=dict)
    # True only once the file-processing loop has run to its natural end
    # (every WAITING file reached a terminal state). Defaults to False: a
    # freshly created Job, a Job whose completion is not yet confirmed, and
    # legacy persisted Jobs written before this field existed must not be
    # treated as completed. False when a fatal error, stop or cancel cut the
    # loop short, leaving files unprocessed.
    batch_completed: bool = False
