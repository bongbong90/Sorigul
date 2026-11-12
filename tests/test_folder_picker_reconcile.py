"""#170 regressions execute production page callbacks and the #111 hook.

The Node hook host renders production TSX, supplies synthetic API responses,
and controls promise/timer ordering. It needs only the existing frontend
TypeScript toolchain; no install, desktop launch or backend data is involved.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = (
    "empty_to_a", "immediate_clear", "rows_counts", "confirmation_counts",
    "selection_shared_stem", "job_clear_and_match", "late_a", "late_error",
    "rapid_abc", "same_folder_generation", "generation_without_abort", "settings_failure", "settings_pending",
    "offline_reconnect", "settings_hydration", "preflight_reset",
    "watcher_add_remove", "watcher_pause_unpause", "unmount_abort",
)


@pytest.fixture(scope="module")
def page_results():
    node = shutil.which("node")
    assert node, "#170 requires Node to execute frontend regressions"
    completed = subprocess.run(
        [node, str(ROOT / "tests/frontend/folder_picker_harness.cjs")],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_folder_picker_page_behavior(page_results, scenario):
    assert page_results[scenario] == "PASS", page_results[scenario]
