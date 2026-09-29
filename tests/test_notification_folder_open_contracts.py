"""Issue #110 source contracts: actionable completion toast (Legacy
TrayToastWindow parity) without widening the native security boundary."""

import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND = REPO_ROOT / "frontend"
TAURI = FRONTEND / "src-tauri"


def read_repo(path):
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def block_after(source, marker, open_char="{", close_char="}"):
    start = source.index(marker)
    depth = 0
    for index in range(source.index(open_char, start), len(source)):
        if source[index] == open_char:
            depth += 1
        elif source[index] == close_char:
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(f"unterminated block after {marker!r}")


def test_completion_events_take_the_actionable_toast_path():
    hook = read_repo("frontend/src/hooks/useDesktopNotifications.ts")
    assert "'FILE_COMPLETED', 'JOB_COMPLETED'" in hook
    notify = block_after(hook, "async function notify(")
    assert "await showCompletionToast(" in notify
    toast_try, fallback = notify.split("} catch (error) {", 1)
    assert "return" in toast_try.split("await showCompletionToast(", 1)[1]
    # No OS notification on the normal toast path; only as degraded fallback.
    assert "sendNotification" not in toast_try
    assert fallback.count("sendNotification(") == 1
    assert "degraded OS notification without folder action" in fallback
    assert hook.count("sendNotification(") == 1


def test_dedup_and_initial_snapshot_ignore_are_preserved():
    hook = read_repo("frontend/src/hooks/useDesktopNotifications.ts")
    assert "function eventKey(" in hook
    assert "useRef<Set<string>>(new Set())" in hook
    assert "if (!initialized.current) {" in hook
    assert "seen.current.add(eventKey(event))" in hook
    assert "!seen.current.has(eventKey(event))" in hook
    assert "POLL_INTERVAL_MS = 4000" in hook


def test_mobile_only_notification_actions_are_not_used():
    mobile_action_api = re.compile(r"\bregisterActionTypes\b|\bonAction\b")
    for path in (FRONTEND / "src").rglob("*.ts*"):
        assert not mobile_action_api.search(path.read_text(encoding="utf-8")), path


def test_toast_payload_types_carry_opaque_identities_only():
    native = read_repo("frontend/src/lib/native.ts")
    request = block_after(native, "export interface CompletionToastRequest")
    fields = re.findall(r"^\s+(\w+)\??:", request, flags=re.MULTILINE)
    assert fields == ["desktop_intent", "job_id", "file_id", "message"]
    toast = block_after(native, "export interface CompletionToast extends")
    assert re.findall(r"^\s+(\w+)\??:", toast, flags=re.MULTILINE) == ["generation"]

    rust = read_repo("frontend/src-tauri/src/completion_toast.rs")
    for struct in ("pub struct CompletionToastRequest", "pub struct CompletionToastPayload"):
        body = block_after(rust, struct)
        assert "folder" not in body and "path" not in body, struct


def test_toast_view_has_legacy_actions_and_opens_by_job_id():
    view = read_repo("frontend/src/components/notification/CompletionToast.tsx")
    assert "폴더 열기" in view
    assert "확인" in view
    assert "openNotificationFolder(toast.job_id)" in view
    assert "dismissCompletionToast()" in view

    native = read_repo("frontend/src/lib/native.ts")
    assert "invoke('open_notification_folder', { jobId })" in native
    assert "invoke('show_completion_toast', { request })" in native


def test_toast_window_is_a_single_branch_of_the_existing_entry_point():
    main = read_repo("frontend/src/main.tsx")
    assert "isCompletionToastWindow() ? <CompletionToast /> : <App />" in main
    package = json.loads(read_repo("frontend/package.json"))
    assert set(package["dependencies"]) == {
        "@tauri-apps/api",
        "@tauri-apps/plugin-dialog",
        "@tauri-apps/plugin-notification",
        "@tauri-apps/plugin-opener",
        "lucide-react",
        "react",
        "react-dom",
    }


def test_rust_folder_open_takes_job_id_and_uses_fixed_explorer_without_shell():
    rust = read_repo("frontend/src-tauri/src/lib.rs")
    assert "fn open_notification_folder(app: AppHandle, job_id: String)" in rust
    assert "/api/desktop/jobs/{job_id}/open-folder-intent" in rust
    assert "http://127.0.0.1:{BACKEND_PORT}" in rust
    assert "if !is_opaque_job_id(job_id)" in rust
    command = block_after(rust, "fn open_notification_folder(")
    assert "open_validated_folder(&url, open_in_explorer)" in command

    intent_command = block_after(rust, "fn open_folder_by_intent(")
    assert "open_in_explorer(&intent.folder, intent.item_filename.as_deref())" in intent_command

    opener = block_after(rust, "fn open_in_explorer(")
    assert "explorer_command(folder, item_filename)?.spawn()?" in opener

    # #122: Explorer by trusted absolute Windows-directory path, never PATH.
    explorer = block_after(rust, "fn explorer_command(")
    assert "windows_system::SystemUtility::Explorer" in explorer
    assert "std::process::Command::new(explorer)" in explorer
    assert ".arg(&target)" in explorer
    assert '"explorer.exe"' not in rust
    for forbidden in ("cmd.exe", '"cmd"', "powershell", '"/C"', "sh -c", "format!("):
        assert forbidden not in opener, forbidden
        assert forbidden not in explorer, forbidden


def test_backend_route_takes_only_the_job_id():
    routes = read_repo("backend/src/api/routes.py")
    assert '@router.post("/desktop/jobs/{job_id}/open-folder-intent"' in routes
    assert "def open_job_folder_intent(job_id: str):" in routes
    assert "job_folder_open_intent(job.folder)" in routes


def test_toast_window_is_declared_once_hidden_non_activating_and_off_taskbar():
    config = json.loads(read_repo("frontend/src-tauri/tauri.conf.json"))
    toasts = [w for w in config["app"]["windows"] if w["label"] == "completion-toast"]
    assert len(toasts) == 1
    toast = toasts[0]
    assert toast["visible"] is False
    assert toast["focus"] is False
    assert toast["focusable"] is False
    assert toast["decorations"] is False
    assert toast["resizable"] is False
    assert toast["alwaysOnTop"] is True
    assert toast["skipTaskbar"] is True

    rust = read_repo("frontend/src-tauri/src/completion_toast.rs")
    assert 'COMPLETION_TOAST_LABEL: &str = "completion-toast"' in rust
    assert "Duration::from_millis(7200)" in rust
    assert "COMPLETION_TOAST_MARGIN: f64 = 16.0" in rust
    # Never a second toast window, never a second tray icon.
    lib = read_repo("frontend/src-tauri/src/lib.rs")
    assert "WebviewWindowBuilder" not in lib
    assert lib.count("TrayIconBuilder::new()") == 1


def test_no_broad_opener_shell_or_filesystem_capability():
    forbidden = re.compile(r"opener:allow-open-path|opener:allow-reveal|opener:default|^shell:|^fs:")
    capability_files = sorted((TAURI / "capabilities").glob("*.json"))
    assert {path.name for path in capability_files} == {"default.json", "completion-toast.json"}
    for path in capability_files:
        capability = json.loads(path.read_text(encoding="utf-8"))
        for permission in capability["permissions"]:
            name = permission if isinstance(permission, str) else permission["identifier"]
            assert not forbidden.search(name), f"{path.name}: {name}"

    toast = json.loads((TAURI / "capabilities" / "completion-toast.json").read_text(encoding="utf-8"))
    assert toast["windows"] == ["completion-toast"]
    assert toast["permissions"] == ["core:event:allow-listen", "core:event:allow-unlisten"]

    cargo = read_repo("frontend/src-tauri/Cargo.toml")
    assert "tauri-plugin-shell" not in cargo
    assert "tauri-plugin-fs" not in cargo
