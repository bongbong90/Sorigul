"""ID-based destination selection. All remote access uses the existing Drive auth.

No folder is created here. Names/breadcrumbs are presentation data, never routing
keys. Selecting, browsing and uploading each verify the current account.
"""
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from src.domain.models import DriveParentFolder
from src.services.drive import DriveError


FOLDER_MIME = "application/vnd.google-apps.folder"
FolderId = Field(pattern=r"^[A-Za-z0-9_-]{1,256}$")


class DriveFolderSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    folder_id: str = FolderId
    account_id: str = Field(min_length=1, max_length=256)


class DriveFolderEntry(BaseModel):
    folder_id: str
    name: str
    can_select: bool


class DriveBreadcrumb(BaseModel):
    folder_id: str
    name: str


class DriveFolderPage(BaseModel):
    account_id: str
    folder: DriveFolderEntry
    breadcrumbs: list[DriveBreadcrumb]
    children: list[DriveFolderEntry]
    next_page_token: Optional[str] = None


def checked_folder(client, folder_id: str, *, writable: bool = False) -> dict:
    item = client.get_folder(folder_id)
    if (not isinstance(item, dict) or not isinstance(item.get("id"), str)
            or (folder_id != "root" and item["id"] != folder_id)
            or item.get("mimeType") != FOLDER_MIME
            or item.get("trashed") is not False
            or not isinstance(item.get("name"), str)
            or not item["name"]):
        raise DriveError("DRIVE_FOLDER_INVALID", "저장 폴더가 삭제되었거나 휴지통에 있습니다. 저장 위치를 다시 확인해 주세요.")
    parents = item.get("parents", [])
    if not isinstance(parents, list) or len(parents) > 1:
        raise DriveError("DRIVE_TARGET_AMBIGUOUS", "Google Drive 폴더 위치를 확인할 수 없습니다.")
    if writable and item.get("capabilities", {}).get("canAddChildren") is not True:
        raise DriveError("DRIVE_FOLDER_FORBIDDEN", "선택한 폴더에 저장할 권한이 없습니다. 저장 위치와 계정을 확인해 주세요.")
    return item


class DriveDestinationService:
    def __init__(self, auth, settings):
        self.auth = auth
        self.settings = settings

    @staticmethod
    def _account(client, expected: Optional[str] = None) -> str:
        identity = client.account_id()
        if not isinstance(identity, str) or not identity:
            raise DriveError("DRIVE_ACCOUNT_UNKNOWN", "Google Drive 계정을 확인할 수 없습니다. 다시 연결해 주세요.")
        if expected is not None and identity != expected:
            raise DriveError("DRIVE_ACCOUNT_CHANGED", "저장 위치를 선택한 Google 계정과 현재 계정이 다릅니다. 계정을 확인해 주세요.")
        return identity

    @staticmethod
    def validate_parent(client, parent: DriveParentFolder) -> str:
        DriveDestinationService._account(client, parent.account_id)
        item = checked_folder(client, parent.folder_id, writable=True)
        if not item.get("parents"):
            root = checked_folder(client, "root")
            if item["id"] != root["id"]:
                raise DriveError("DRIVE_TARGET_AMBIGUOUS", "Google Drive 폴더 위치를 확인할 수 없습니다.")
        return item["id"]

    def browse(self, folder_id: str = "root", account_id: Optional[str] = None,
               page_token: Optional[str] = None) -> DriveFolderPage:
        try:
            return self._browse(self.auth.ensure_client(), folder_id, account_id, page_token)
        except DriveError:
            raise
        except Exception as exc:
            raise DriveError("DRIVE_LOCATION_UNAVAILABLE", "Google Drive 폴더를 불러오지 못했습니다. 연결과 접근 권한을 확인해 주세요.") from exc

    def _browse(self, client, folder_id, expected_account, page_token):
        account = self._account(client, expected_account)
        root = checked_folder(client, "root")
        current = root if folder_id == "root" else checked_folder(client, folder_id)
        breadcrumbs = []
        node = current
        seen = set()
        for _ in range(64):
            if node["id"] in seen:
                break
            seen.add(node["id"])
            breadcrumbs.append(DriveBreadcrumb(
                folder_id=node["id"], name="내 드라이브" if node["id"] == root["id"] else node["name"],
            ))
            if node["id"] == root["id"]:
                break
            parents = node.get("parents", [])
            if len(parents) != 1:
                raise DriveError("DRIVE_TARGET_AMBIGUOUS", "내 드라이브에서 폴더 위치를 확인할 수 없습니다.")
            node = checked_folder(client, parents[0])
        else:
            raise DriveError("DRIVE_TARGET_AMBIGUOUS", "폴더 경로가 너무 깊어 확인할 수 없습니다.")
        if breadcrumbs[-1].folder_id != root["id"]:
            raise DriveError("DRIVE_TARGET_AMBIGUOUS", "Google Drive 폴더 경로를 확인할 수 없습니다.")
        page = client.list_folders(current["id"], page_token)
        children = []
        seen_children = set()
        for item in page.get("files", []):
            # Validate the list response too; never offer a file/shortcut or
            # an object returned for a different parent as a destination.
            if (item.get("mimeType") != FOLDER_MIME or item.get("trashed") is not False
                    or item.get("parents") != [current["id"]]):
                continue
            child_id = item.get("id")
            if not isinstance(child_id, str) or not item.get("name") or child_id in seen_children:
                raise DriveError("DRIVE_TARGET_AMBIGUOUS", "Google Drive 폴더 목록을 확인할 수 없습니다.")
            seen_children.add(child_id)
            children.append(self._entry(item))
        return DriveFolderPage(
            account_id=account, folder=self._entry(current),
            breadcrumbs=list(reversed(breadcrumbs)), children=children,
            next_page_token=page.get("nextPageToken"),
        )

    @staticmethod
    def _entry(item):
        return DriveFolderEntry(folder_id=item["id"], name=item["name"],
                                can_select=item.get("capabilities", {}).get("canAddChildren") is True)

    def select(self, request: DriveFolderSelection):
        # Re-read ID/path/account at confirmation; client display strings are
        # never accepted. No mutation if validation or persistence fails.
        page = self.browse(request.folder_id, request.account_id)
        if not page.folder.can_select:
            raise DriveError("DRIVE_FOLDER_FORBIDDEN", "선택한 폴더에 저장할 권한이 없습니다.")
        parent = DriveParentFolder(
            folder_id=page.folder.folder_id, account_id=page.account_id, layout="transcript_root",
            display_path=" / ".join(part.name for part in page.breadcrumbs),
        )
        try:
            return self.settings.set_drive_parent(parent)
        except OSError as exc:
            raise DriveError("DRIVE_LOCATION_SAVE_FAILED", "저장 위치를 저장하지 못했습니다. 다시 시도해 주세요.") from exc

    def reset(self):
        try:
            return self.settings.set_drive_parent(None)
        except OSError as exc:
            raise DriveError("DRIVE_LOCATION_SAVE_FAILED", "기본 저장 위치를 저장하지 못했습니다. 다시 시도해 주세요.") from exc
