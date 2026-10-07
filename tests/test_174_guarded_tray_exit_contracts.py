"""Issue #174 source contracts: tray "종료" never kills active work.

Tray Exit used to run `sidecar.cleanup()` + `app.exit(0)` directly, so an
active Local Job was killed and recovered as CRASHED on the next launch. It now
uses the same #128 close guard as an `exit` X close: one pending check, idle
exits through RunEvent::ExitRequested, active work or any doubt hides to tray.

Decision logic (coalescing, outcomes, fail-safe, reopen race) is unit-tested
in frontend/src-tauri/src/close_guard.rs; these pin the native wiring.
"""

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
LIB = REPO_ROOT / "frontend" / "src-tauri" / "src" / "lib.rs"
GUARD = REPO_ROOT / "frontend" / "src-tauri" / "src" / "close_guard.rs"


def read(path):
    return path.read_text(encoding="utf-8")


def block_after(source, marker):
    start = source.index(marker)
    depth = 0
    for index in range(source.index("{", start), len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(marker)


def code_only(block):
    return "\n".join(line for line in block.splitlines() if not line.strip().startswith("//"))


def menu_handler(lib):
    tray = block_after(lib, "fn build_tray(")
    return tray[tray.index(".on_menu_event(") : tray.index(".build(app)?")]


def test_tray_quit_routes_only_through_the_guarded_exit():
    handler = menu_handler(read(LIB))
    assert '"quit" => request_guarded_exit(app),' in handler


def test_tray_menu_never_cleans_up_or_exits_directly():
    handler = menu_handler(read(LIB))
    for forbidden in ("cleanup", ".exit(", "sidecar", "fetch_close_guard", ".call()", "sleep("):
        assert forbidden not in handler, forbidden


def test_guarded_exit_helper_reuses_the_single_pending_close_check():
    helper = code_only(block_after(read(LIB), "fn request_guarded_exit("))
    assert "state.close_check.on_exit_requested()" in helper
    assert "spawn_close_check(app.clone(), generation)" in helper
    for forbidden in ("cleanup", ".exit(", "close_behavior", "fetch_close_guard", "hide()"):
        assert forbidden not in helper, forbidden


def test_tray_exit_ignores_close_behavior_and_shares_the_x_gate():
    method = code_only(block_after(read(GUARD), "pub fn on_exit_requested("))
    assert 'self.on_close_requested("exit")' in method
    assert "CloseRequestAction::CheckCriticalWork" in method
    assert "in_progress" not in method, "no second pending flag"


def test_only_confirmed_idle_exits_and_cleanup_stays_centralized():
    lib = code_only(read(LIB))
    assert lib.count(".exit(") == 1
    check = block_after(lib, "fn spawn_close_check(")
    assert "CloseOutcome::ConfirmedExit => app.exit(0)" in check
    assert "fetch_close_guard(&close_guard_url())" in check
    assert re.findall(r"\.cleanup\(\)", lib) == [".cleanup()"]
    run = block_after(lib, "app.run(move |_app_handle, event|")
    assert "RunEvent::ExitRequested" in run and "sidecar_for_exit.cleanup();" in run


def test_no_new_backend_route_or_confirmation_ux():
    lib = read(LIB)
    assert "/api/desktop/close-guard" not in lib, "the URL stays in close_guard.rs"
    assert lib.count("MenuItem::with_id(") == 2, "no extra tray items"
    assert "정말 종료" not in lib and "dialog()" not in lib


def test_x_button_policy_is_unchanged():
    lib = read(LIB)
    events = lib[lib.index(".on_window_event(") : lib.index(".build(tauri::generate_context!())")]
    handler = events[events.index("let behavior = state.close_behavior") :]
    assert handler.index("api.prevent_close();") < handler.index("on_close_requested(&behavior)")
    assert "(CloseRequestAction::HideNow, _) => {\n                        let _ = window.hide();" in handler
    assert "(CloseRequestAction::CheckCriticalWork, generation) => {" in handler
    assert "(CloseRequestAction::AlreadyChecking, _) => {}" in handler


def test_single_instance_stays_first_and_second_launch_only_shows():
    lib = read(LIB)
    builder = lib[lib.index("tauri::Builder::default()") : lib.index(".manage(AppState")]
    plugins = re.findall(r"\.plugin\((tauri_plugin_\w+)::init\(", builder)
    assert plugins[0] == "tauri_plugin_single_instance"
    callback = block_after(lib, "fn handle_second_instance(")
    assert code_only(callback[callback.index("{") + 1 : -1]).strip() == "show_main_window(app);"
