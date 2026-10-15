"""Issue #131 source contracts for the honest tray progress tooltip."""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def read_repo(path):
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_native_formatter_owns_mapping_privacy_and_duplicate_suppression():
    source = read_repo("frontend/src-tauri/src/tray_tooltip.rs")
    for status in (
        "WAITING",
        "PREPARING",
        "TRANSCRIBING",
        "SAVING",
        "VERIFYING",
        "CANCEL_REQUESTED",
        "DONE",
        "FAILED",
        "CRASHED",
        "STOPPED",
        "CANCELLED",
    ):
        assert f'"{status}"' in source
    assert ".is_finite()" in source and "(0.0..=100.0).contains(progress)" in source
    assert ".rsplit(['/', '\\\\'])" in source
    assert "last_tooltip.as_deref() == Some(tooltip)" in source


def test_existing_tray_is_named_initialized_and_updated_in_place():
    source = read_repo("frontend/src-tauri/src/lib.rs")
    assert 'const TRAY_ID: &str = "sorigul-main-tray"' in source
    assert "TrayIconBuilder::with_id(TRAY_ID)" in source
    assert ".tooltip(IDLE_TRAY_TOOLTIP)" in source
    assert ".tray_by_id(TRAY_ID)" in source
    assert "set_tray_progress," in source
    assert source.count(".build(app)?") == 1, "the update path must not build another tray"


def test_frontend_uses_global_truth_and_only_one_shot_terminal_lookup():
    page = read_repo("frontend/src/pages/TranscriptionPage.tsx")
    hook = read_repo("frontend/src/hooks/useTrayProgress.ts")
    assert "useTrayProgress(globalActiveJob, job)" in page
    assert hook.index("if (globalActiveJob)") < hook.index("const observedJobId")
    assert "lastObservedActiveJobIdRef" in hook
    assert "if (!observedJobId)" in hook and "status: 'IDLE'" in hook
    assert "folderJob?.job_id === observedJobId" in hook
    assert hook.count("api.job(observedJobId") == 1
    assert "api.activeJob" not in hook
    assert "AbortController" not in hook
    assert "setTimeout" not in hook and "setInterval" not in hook


def test_browser_wrapper_is_noop_and_sends_structured_filename_only_payload():
    native = read_repo("frontend/src/lib/native.ts")
    function = native[native.index("export async function setTrayProgress") :]
    assert function.index("if (!isTauri()) return") < function.index("invoke('set_tray_progress'")
    assert "currentFile: filenameOnly(payload.currentFile)" in function
    assert "tooltip:" not in function


def test_no_backend_or_dependency_change_is_needed_for_tray_sync():
    hook = read_repo("frontend/src/hooks/useTrayProgress.ts")
    assert "../api/client" in hook
    assert "api.job(" in hook
    assert "fetch(" not in hook
