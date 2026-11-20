"""Run production Drive picker callbacks with an in-memory API, no browser/account."""
import json
import shutil
import subprocess
from pathlib import Path


def test_drive_picker_offline_behavior():
    root = Path(__file__).resolve().parents[1]
    node = shutil.which("node")
    assert node, "Node is required for the production React picker harness"
    result = subprocess.run(
        [node, str(root / "tests/frontend/drive_destination_harness.cjs")],
        cwd=root, capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    assert result.returncode == 0, result.stderr
    cases = json.loads(result.stdout.strip().splitlines()[-1])
    assert len(cases) == 15
    assert all(value == "PASS" for value in cases.values())
