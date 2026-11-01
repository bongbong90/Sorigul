import re
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


def _rust_matches(source, anchor):
    block = source[source.index(anchor) :]
    block = block[block.index("matches!(") :]
    block = block[: re.search(r'"\s*\)', block).end()]
    return set(re.findall(r'"([A-Z_]+)"', block))


def _py_enum(models, name):
    body = models[models.index(f"class {name}(str, Enum):") :].split("\n\n", 1)[0]
    return set(re.findall(r'= "([A-Z_]+)"', body))


def test_59_saved_job_parser_matches_backend_status_enums():
    # recovery.rs reads the backend's jobs.json; every terminal value it accepts
    # must exist in the backend enums, and every other value must hold.
    root = Path(__file__).resolve().parents[1]
    recovery = (root / "frontend/src-tauri/src/recovery.rs").read_text(encoding="utf-8")
    models = (root / "backend/src/domain/models.py").read_text(encoding="utf-8")
    file_terminal = _rust_matches(recovery, "let terminal =")
    drive_terminal = _rust_matches(recovery, "job.drive.values()")
    assert file_terminal == {"DONE", "FAILED", "STOPPED", "CANCELLED", "CRASHED"}
    assert file_terminal < _py_enum(models, "FileStatus")
    assert _py_enum(models, "FileStatus") - file_terminal == {
        "WAITING", "PREPARING", "TRANSCRIBING", "SAVING", "VERIFYING", "CANCEL_REQUESTED"
    }
    assert drive_terminal == {"DISABLED", "AUTH_REQUIRED", "CLASSIFICATION_FAILED", "DONE", "FAILED"}
    assert _py_enum(models, "DriveStatus") - drive_terminal == {"PENDING", "UPLOADING"}
    assert "deny_unknown_fields" not in recovery, "extra JobModel fields must not fail the read"
