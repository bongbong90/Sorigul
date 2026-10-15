"""Issue #131 source contracts for the honest tray progress tooltip."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest


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


def test_frontend_uses_app_lifetime_global_truth_and_one_terminal_lookup():
    hook = read_repo("frontend/src/hooks/useTrayProgress.ts")
    assert "api.activeJob(signal)" in hook
    assert "export function useTrayProgress(): void" in hook
    assert hook.count("api.job(lookupId, signal)") == 1
    assert "if (!observedJobId)" in hook and "status: 'IDLE'" in hook
    assert "new AbortController()" in hook and "controller?.abort()" in hook
    assert "clearTimeout(timer)" in hook
    assert "}, [])" in hook, "observer effect must not depend on page state"


def test_tray_writer_is_single_app_owner_not_page_owned():
    app = read_repo("frontend/src/App.tsx")
    assert app.count("useTrayProgress()") == 1
    sources = [p for p in (REPO_ROOT / "frontend/src").rglob("*.ts*")]
    owners = [p.name for p in sources if "useTrayProgress(" in p.read_text(encoding="utf-8")
              and p.name not in ("useTrayProgress.ts",)]
    assert owners == ["App.tsx"]
    writers = [p.name for p in sources if "setTrayProgress(" in p.read_text(encoding="utf-8")
               and p.name != "native.ts"]
    assert writers == ["useTrayProgress.ts"]
    assert "useTrayProgress" not in read_repo("frontend/src/pages/TranscriptionPage.tsx")


TRAY_SCENARIOS = (
    "cold_idle", "active_and_progress", "route_survives", "terminal_DONE",
    "terminal_FAILED", "terminal_STOPPED", "terminal_CANCELLED", "terminal_CRASHED",
    "lookup_failure_keeps_state", "non_terminal_lookup_retries", "outage_no_fake_idle",
    "startup_unavailable", "new_job_after_terminal", "tray_failure_best_effort",
    "unmount_cleanup",
)


@pytest.fixture(scope="module")
def tray_results():
    node = shutil.which("node")
    assert node, "#173 requires Node to execute the tray lifecycle harness"
    completed = subprocess.run(
        [node, str(REPO_ROOT / "tests/frontend/tray_progress_harness.cjs")],
        cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("scenario", TRAY_SCENARIOS)
def test_tray_lifecycle_behavior(tray_results, scenario):
    assert tray_results[scenario] == "PASS", tray_results[scenario]


def test_browser_wrapper_is_noop_and_sends_structured_filename_only_payload():
    native = read_repo("frontend/src/lib/native.ts")
    function = native[native.index("export async function setTrayProgress") :]
    assert function.index("if (!isTauri()) return") < function.index("invoke('set_tray_progress'")
    assert "currentFile: filenameOnly(payload.currentFile)" in function
    assert "tooltip:" not in function


def test_no_backend_or_dependency_change_is_needed_for_tray_sync():
    hook = read_repo("frontend/src/hooks/useTrayProgress.ts")
    assert "../api/client" in hook
    assert "api.job(" in hook and "api.activeJob(" in hook
    assert "fetch(" not in hook
