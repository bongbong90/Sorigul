import subprocess
from pathlib import Path


def test_manual_restart_component_behavior():
    root = Path(__file__).resolve().parents[1]
    subprocess.run(
        ["node", str(root / "tests/frontend/backend_restart_harness.cjs")],
        cwd=root,
        check=True,
        timeout=30,
    )
