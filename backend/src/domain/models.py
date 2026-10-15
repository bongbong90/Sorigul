from enum import Enum
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
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
    # True only once the file-processing loop has run to its natural end
    # (every WAITING file reached a terminal state). Defaults to False: a
    # freshly created Job, a Job whose completion is not yet confirmed, and
    # legacy persisted Jobs written before this field existed must not be
    # treated as completed. False when a fatal error, stop or cancel cut the
    # loop short, leaving files unprocessed.
    batch_completed: bool = False
