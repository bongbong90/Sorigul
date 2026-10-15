from datetime import datetime, timezone, timedelta
import uuid
import json
from pydantic import BaseModel, ConfigDict, field_validator
from typing import Optional, Literal

from src.services.drive import DriveAuth
from src.services.colab_url import normalize_colab_base_url, ColabUrlError
from src.engines.colab import DirectColabHttpClient, EngineError

COLAB_RUNTIME_FOLDER = "Sorigul Runtime"
COLAB_CONNECTION_FILENAME = "colab_connection.json"
COLAB_SCHEMA_VERSION = 1
COLAB_REQUEST_TTL_SECONDS = 600
COLAB_READY_TTL_SECONDS = 3600

class ColabConnectionMetadata(BaseModel):
    model_config = ConfigDict(extra='forbid')
    
    schema_version: int
    request_id: str
    url: str
    status: Literal["REQUESTED", "READY", "FAILED"]
    updated_at: datetime
    expires_at: datetime

    @field_validator("updated_at", "expires_at")
    @classmethod
    def ensure_timezone_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.utcoffset() is None:
            raise ValueError("datetime must be timezone-aware")
        return v

class RendezvousState(BaseModel):
    state: Literal["WAITING", "FOUND", "CONNECTED", "FAILED", "EXPIRED", "AUTH_REQUIRED"]
    base_url: Optional[str] = None
    request_id: Optional[str] = None

def _validate_metadata_freshness(metadata: ColabConnectionMetadata, now: datetime) -> Literal["VALID", "EXPIRED", "INVALID"]:
    lifetime = (metadata.expires_at - metadata.updated_at).total_seconds()
    if metadata.status == "REQUESTED":
        if not (0 < lifetime <= COLAB_REQUEST_TTL_SECONDS):
            return "INVALID"
    elif metadata.status == "READY":
        if not (0 < lifetime <= COLAB_READY_TTL_SECONDS):
            return "INVALID"
    elif metadata.status == "FAILED":
        if lifetime <= 0 or lifetime > COLAB_READY_TTL_SECONDS:
            return "INVALID"

    if metadata.expires_at <= now:
        return "EXPIRED"

    if metadata.updated_at > now + timedelta(seconds=60):
        return "INVALID"

    return "VALID"

class ColabRendezvousService:
    def __init__(self, auth: DriveAuth):
        self.auth = auth
        
    def start(self) -> RendezvousState:
        try:
            client = self.auth.ensure_client()
        except Exception:
            return RendezvousState(state="AUTH_REQUIRED")
            
        request_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc)
        expires_at = datetime.fromtimestamp(now.timestamp() + COLAB_REQUEST_TTL_SECONDS, timezone.utc)
        
        metadata = ColabConnectionMetadata(
            schema_version=COLAB_SCHEMA_VERSION,
            request_id=request_id,
            url="",
            status="REQUESTED",
            updated_at=now,
            expires_at=expires_at,
        )
        
        try:
            folder_id = client.find_or_create_folder("root", COLAB_RUNTIME_FOLDER)
            file_id = client.find_file(folder_id, COLAB_CONNECTION_FILENAME)
            payload = metadata.model_dump_json()
            if file_id:
                client.update_text_file(file_id, COLAB_CONNECTION_FILENAME, payload)
            else:
                client.create_text_file(folder_id, COLAB_CONNECTION_FILENAME, payload)
        except Exception:
            return RendezvousState(state="FAILED", request_id=request_id)
            
        return RendezvousState(state="WAITING", request_id=request_id)

    def poll(self, request_id: str) -> RendezvousState:
        try:
            client = self.auth.ensure_client()
        except Exception:
            return RendezvousState(state="AUTH_REQUIRED")
            
        try:
            folder_id = client.find_or_create_folder("root", COLAB_RUNTIME_FOLDER)
            file_id = client.find_file(folder_id, COLAB_CONNECTION_FILENAME)
            if not file_id:
                return RendezvousState(state="WAITING", request_id=request_id)
                
            content = client.read_text_file(file_id)
        except Exception:
            return RendezvousState(state="WAITING", request_id=request_id)
            
        try:
            data = json.loads(content)
            metadata = ColabConnectionMetadata(**data)
        except Exception:
            # Malformed JSON or invalid schema/extra fields -> ignore
            return RendezvousState(state="WAITING", request_id=request_id)
            
        if metadata.schema_version != COLAB_SCHEMA_VERSION:
            return RendezvousState(state="WAITING", request_id=request_id)
            
        if metadata.request_id != request_id:
            return RendezvousState(state="WAITING", request_id=request_id)
            
        now = datetime.now(timezone.utc)
        freshness = _validate_metadata_freshness(metadata, now)
        if freshness == "EXPIRED":
            return RendezvousState(state="EXPIRED", request_id=request_id)
        elif freshness == "INVALID":
            return RendezvousState(state="WAITING", request_id=request_id)
            
        if metadata.status == "FAILED":
            return RendezvousState(state="FAILED", request_id=request_id)
            
        if metadata.status == "READY":
            if not metadata.url:
                return RendezvousState(state="WAITING", request_id=request_id)
            try:
                normalized = normalize_colab_base_url(metadata.url)
                return RendezvousState(state="FOUND", base_url=normalized, request_id=request_id)
            except ColabUrlError:
                return RendezvousState(state="WAITING", request_id=request_id)
                
        return RendezvousState(state="WAITING", request_id=request_id)

    def verify_url(self, url: str) -> RendezvousState:
        try:
            normalized = normalize_colab_base_url(url)
            client = DirectColabHttpClient(normalized)
            client.check_health()
            return RendezvousState(state="CONNECTED", base_url=normalized)
        except (ColabUrlError, EngineError, Exception):
            return RendezvousState(state="FAILED")
