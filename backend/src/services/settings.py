import json
import uuid
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class CloseBehavior(str, Enum):
    TRAY = "tray"
    EXIT = "exit"


class ShutdownMode(str, Enum):
    DISABLED = "disabled"
    IMMEDIATE = "immediate"
    DELAY_15 = "15_seconds"
    DELAY_30 = "30_seconds"

    @property
    def delay_seconds(self) -> Optional[int]:
        return {
            ShutdownMode.DISABLED: None,
            ShutdownMode.IMMEDIATE: 0,
            ShutdownMode.DELAY_15: 15,
            ShutdownMode.DELAY_30: 30,
        }[self]


class NotificationSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_complete: bool = True
    job_complete: bool = True


class RuntimeSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notifications: NotificationSettings = Field(default_factory=NotificationSettings)
    close_behavior: CloseBehavior = CloseBehavior.TRAY
    shutdown: ShutdownMode = ShutdownMode.DISABLED


class SettingsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notifications: Optional[NotificationSettings] = None
    close_behavior: Optional[CloseBehavior] = None
    shutdown: Optional[ShutdownMode] = None


class SettingsManager:
    def __init__(self, storage_path: Path):
        self.storage_path = storage_path
        self._settings = self._load()

    def get(self) -> RuntimeSettings:
        return self._settings.model_copy(deep=True)

    def update(self, patch: SettingsPatch) -> RuntimeSettings:
        payload = self._settings.model_dump(mode="json")
        payload.update(patch.model_dump(mode="json", exclude_none=True))
        self._settings = RuntimeSettings.model_validate(payload)
        self._save()
        return self.get()

    def _load(self) -> RuntimeSettings:
        if not self.storage_path.exists():
            return RuntimeSettings()
        try:
            payload = json.loads(self.storage_path.read_text(encoding="utf-8"))
            return RuntimeSettings.model_validate(payload)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValidationError, TypeError):
            self._quarantine()
            return RuntimeSettings()

    def _save(self):
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.storage_path.with_name(f".{self.storage_path.name}.{uuid.uuid4().hex}.tmp")
        temp_path.write_text(
            json.dumps(self._settings.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp_path.replace(self.storage_path)

    def _quarantine(self):
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        quarantine = self.storage_path.with_name(f"settings.corrupt.{timestamp}.json")
        if quarantine.exists():
            quarantine = self.storage_path.with_name(
                f"settings.corrupt.{timestamp}.{uuid.uuid4().hex[:6]}.json"
            )
        try:
            self.storage_path.replace(quarantine)
        except OSError:
            pass
