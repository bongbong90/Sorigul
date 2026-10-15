"""Issue #128 contracts: the Windows X button never ends active transcription
or Drive work, even with close_behavior = "exit".

Decision logic, parsing and fail-safe fetch are unit-tested in
frontend/src-tauri/src/close_guard.rs; the backend snapshot in
backend/tests/test_close_guard.py. These source contracts pin the window
callback wiring: prevent first, never block on HTTP, one exit cleanup path.
"""

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TAURI = REPO_ROOT / "frontend" / "src-tauri"


def read(path):
    return path.read_text(encoding="utf-8")


def fn_body(source, signature):
    start = source.index(signature)
    depth = 0
    for index in range(source.index("{", start), len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(signature)


def main_window_close_handler(lib):
    events = lib[lib.index(".on_window_event(") : lib.index(".build(tauri::generate_context!())")]
    toast_return = events.index("return;\n", events.index("COMPLETION_TOAST_LABEL"))
    return events[events.index("WindowEvent::CloseRequested", toast_return) :]


def test_close_is_prevented_before_any_decision_and_never_blocks():
    lib = read(TAURI / "src" / "lib.rs")
    handler = main_window_close_handler(lib)
    assert handler.index("api.prevent_close();") < handler.index("on_close_requested(&behavior)")
    assert "CloseRequestAction::HideNow" in handler
    assert "spawn_close_check(app.clone(), generation)" in handler
    events = lib[lib.index(".on_window_event(") : lib.index(".build(tauri::generate_context!())")]
    for blocking in (".call()", "fetch_close_guard", "ureq::", "sleep("):
        assert blocking not in events, blocking


def test_background_check_exits_only_via_the_central_cleanup_path():
    lib = read(TAURI / "src" / "lib.rs")
    check = fn_body(lib, "fn spawn_close_check(")
    assert "std::thread::spawn(move ||" in check
    assert "fetch_close_guard(&close_guard_url())" in check
    assert "CloseOutcome::ConfirmedExit => app.exit(0)" in check
    assert "cleanup" not in check, "exit cleanup stays in RunEvent::ExitRequested"
    assert re.search(r"CloseOutcome::ProtectedHide\(_\) \| CloseOutcome::SafeHide => \{\s*if let Some\(window\)", check)
    hide = check[check.index("CloseOutcome::ProtectedHide(_)") :]
    assert hide.index("window.hide()") < hide.index(".notification()"), "hide is the primary safety action"
    assert "let _ = app" in hide, "a notice failure is ignored, never escalated to exit"
    run = lib[lib.index("app.run(move |_app_handle, event|") :]
    assert "RunEvent::ExitRequested" in run and "sidecar_for_exit.cleanup();" in run


def test_tray_quit_and_open_keep_their_meaning():
    lib = read(TAURI / "src" / "lib.rs")
    tray = fn_body(lib, "fn build_tray(")
    quit = tray[tray.index('"quit" =>') :]
    assert quit.index("state.sidecar.cleanup();") < quit.index("app.exit(0);")
    assert "close_check" not in tray, "explicit Quit is not the X-button policy"
    reopen = fn_body(lib, "fn show_main_window(")
    assert "close_check.window_reopened()" in reopen
    assert "window.show()" in reopen and "window.set_focus()" in reopen


def test_guard_request_is_fixed_loopback_and_short():
    guard = read(TAURI / "src" / "close_guard.rs")
    assert 'format!("http://127.0.0.1:{BACKEND_PORT}/api/desktop/close-guard")' in guard
    timeout = re.search(r"CLOSE_GUARD_TIMEOUT: Duration = Duration::from_millis\((\d+)\)", guard)
    assert timeout and 1000 <= int(timeout.group(1)) <= 2000
    assert "Err(_) => CloseOutcome::SafeHide" in guard


def test_no_new_dependencies_for_close_protection():
    cargo = read(TAURI / "Cargo.toml")
    deps = cargo[cargo.index("[dependencies]") : cargo.index("[target.")]
    assert 'tauri-plugin-notification = "2"' in deps
    assert "serde_json" not in deps


def test_settings_copy_matches_the_protected_close_semantics():
    page = read(REPO_ROOT / "frontend" / "src" / "pages" / "SettingsPage.tsx")
    assert "유휴 상태에서도 Tray로 이동" in page
    assert "전사 또는 Drive 작업 중에는 이 설정과 관계없이 안전을 위해 Tray로 이동합니다." in page
    assert "'항상 Tray로 숨김' : '유휴 시 앱 종료'" in page
    assert "실행 중 창을 닫으면 Tray로 이동" not in page
    assert "close_behavior: event.target.checked ? 'tray' : 'exit'" in page
    settings = read(REPO_ROOT / "backend" / "src" / "services" / "settings.py")
    enum = settings[settings.index("class CloseBehavior(str, Enum):") :].split("\n\n", 1)[0]
    assert re.findall(r'= "(\w+)"', enum) == ["tray", "exit"], "stored values unchanged"
