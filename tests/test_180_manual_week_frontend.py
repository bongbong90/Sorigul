"""#180 manual week regressions execute production page callbacks.

Uses the same Node hook host as #170/#171 (tests/frontend/folder_picker_harness.cjs)
with synthetic API responses; no install, desktop launch or backend data.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = (
    "start_requires_week", "start_all_requires_week_before_confirmation",
    "retranscribe_requires_week_at_execute", "invalid_week_inputs_are_rejected",
    "week_is_sent_snapshotted_and_input_locked",
    "week_mismatch_review_is_separate_from_classification_mismatch",
    "rename_to_typed_week_uses_manual_week_target", "classification_mismatch_rename_uses_manual_week",
    "rename_without_free_lesson_is_disabled", "edit_week_releases_preflight",
    "continue_original_forces_drive_off", "eduwill_batch_auto_renames_in_request_order",
    "folder_switch_clears_week_and_error", "rapid_abc_never_inherits_week",
    "same_folder_retry_keeps_week", "late_normalize_after_folder_switch_is_dropped",
    "week_never_persisted_to_settings", "drive_path_preview_shows_manual_week",
)


@pytest.fixture(scope="module")
def page_results():
    node = shutil.which("node")
    assert node, "#180 requires Node to execute frontend regressions"
    completed = subprocess.run(
        [node, str(ROOT / "tests/frontend/manual_week_harness.cjs")],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout.strip().splitlines()[-1])


def test_every_scenario_is_listed(page_results):
    assert set(page_results) == set(SCENARIOS)


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_manual_week_page_behavior(page_results, scenario):
    assert page_results[scenario] == "PASS", page_results[scenario]


def test_runtime_settings_have_no_week_field():
    settings = (ROOT / "backend/src/services/settings.py").read_text(encoding="utf-8")
    client = (ROOT / "frontend/src/api/client.ts").read_text(encoding="utf-8")
    assert "week" not in settings
    runtime_settings = client[client.index("export interface RuntimeSettings"):]
    runtime_settings = runtime_settings[:runtime_settings.index("}")]
    assert "week" not in runtime_settings
