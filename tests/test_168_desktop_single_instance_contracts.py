"""Issue #168 source contracts: one Sorigul desktop process.

A second launch must only show/focus the existing main window (hidden-to-tray
included) through the official Tauri single-instance plugin. The second
process exits inside the plugin's setup, so it never builds a tray, starts the
backend sidecar or runs any shutdown/cleanup path. The backend #126 global
single-run guard is a separate contract (test_global_single_run_contracts.py).
"""

import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
LIB = "frontend/src-tauri/src/lib.rs"


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


def locked_version(lock, name):
    match = re.search(rf'\[\[package\]\]\nname = "{re.escape(name)}"\nversion = "([^"]+)"', lock)
    assert match, f"{name} missing from Cargo.lock"
    return match.group(1)


def test_official_plugin_dependency_is_pinned_to_the_repo_msrv_line():
    manifest = read_repo("frontend/src-tauri/Cargo.toml")
    assert 'rust-version = "1.77"' in manifest, "MSRV must not be raised for #168"
    assert 'tauri-plugin-single-instance = "~2.4.5"' in manifest
    lock = read_repo("frontend/src-tauri/Cargo.lock").replace("\r\n", "\n")
    assert locked_version(lock, "tauri-plugin-single-instance").startswith("2.4.")
    assert locked_version(lock, "tauri") == "2.11.5"


def test_product_identifier_that_names_the_instance_mutex_is_unchanged():
    config = json.loads(read_repo("frontend/src-tauri/tauri.conf.json"))
    assert config["identifier"] == "com.sorigul.desktop"


def test_single_instance_is_the_first_registered_plugin():
    builder = read_repo(LIB)
    builder = builder[builder.index("tauri::Builder::default()") :]
    builder = builder[: builder.index(".manage(AppState")]
    plugins = re.findall(r"\.plugin\((tauri_plugin_\w+)::init\(", builder)
    assert plugins == [
        "tauri_plugin_single_instance",
        "tauri_plugin_dialog",
        "tauri_plugin_notification",
        "tauri_plugin_opener",
    ]
    assert ".plugin(tauri_plugin_single_instance::init(handle_second_instance))" in builder


def test_second_launch_only_reuses_show_main_window():
    source = read_repo(LIB)
    callback = block_after(source, "fn handle_second_instance(")
    body = callback[callback.index("{") + 1 : -1]
    code = "\n".join(line for line in body.splitlines() if not line.strip().startswith("//"))
    assert code.strip() == "show_main_window(app);"
    assert source.count("handle_second_instance") == 2, "defined once, registered once"
    # argv/cwd are accepted but deliberately unused: focus existing instance only.
    assert "_argv: Vec<String>, _cwd: String" in callback


def test_second_launch_callback_never_starts_backend_tray_or_shutdown():
    callback = block_after(read_repo(LIB), "fn handle_second_instance(")
    for forbidden in (
        "start_backend",
        "build_tray",
        "TrayIconBuilder",
        "retry_sidecar_startup",
        "start_and_wait",
        ".cleanup()",
        "exit(",
        "shutdown",
        "close_behavior",
        "emit(",
    ):
        assert forbidden not in callback, forbidden


def test_show_main_window_keeps_close_guard_reopen_show_and_focus():
    show = block_after(read_repo(LIB), "fn show_main_window(")
    reopened = show.index("state.close_check.window_reopened()")
    shown = show.index("window.show()")
    focused = show.index("window.set_focus()")
    assert reopened < shown < focused


def test_main_setup_still_owns_the_only_tray_and_backend_start():
    source = read_repo(LIB)
    setup = block_after(source, ".setup(move |app|")
    assert setup.index("build_tray(app)?") < setup.index("start_backend(")
    assert source.count("build_tray(app)?") == 1
    assert source.count("TrayIconBuilder::with_id(TRAY_ID)") == 1
    # start_backend: definition, setup, and the explicit STARTUP_FAILED retry only.
    assert source.count("start_backend(") == 3
    exit_hook = block_after(source, "app.run(move |_app_handle, event|")
    assert "RunEvent::ExitRequested" in exit_hook and "sidecar_for_exit.cleanup()" in exit_hook
