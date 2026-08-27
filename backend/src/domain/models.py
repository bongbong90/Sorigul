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

class JobModel(BaseModel):
    job_id: str
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    status: FileStatus
    folder: str
    engine: str
    total_files: int
    done_files: int
    failed_files: int
    current_file: Optional[str] = None
    files: Dict[str, FileStatus] = Field(default_factory=dict)
    events: List[JobEvent] = Field(default_factory=list)
    error: Optional[str] = None
