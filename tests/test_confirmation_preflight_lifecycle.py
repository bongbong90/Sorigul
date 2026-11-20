"""#171 source regressions: confirmation is consumed before preflight starts."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = tuple(
    f"{kind}_{scenario}"
    for kind in ("start-all", "retranscribe")
    for scenario in (
        "confirmation", "cancel", "execute_consumes_before_normalize",
        "INVALID_TARGET_review_and_job", "CONFLICT_review_and_job", "MISMATCH_review_and_job",
        "no_issue_job", "early_rejection_global_run", "early_rejection_colab",
        "early_rejection_classification", "double_execute", "folder_switch",
    )
) + ("edit_apply_remaps_target", "use_file_classification")


@pytest.fixture(scope="module")
def page_results():
    node = shutil.which("node")
    assert node, "#171 requires Node to execute production frontend callbacks"
    completed = subprocess.run(
        [node, str(ROOT / "tests/frontend/confirmation_preflight_harness.cjs")],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_confirmation_preflight_page_behavior(page_results, scenario):
    assert page_results[scenario] == "PASS", page_results[scenario]
