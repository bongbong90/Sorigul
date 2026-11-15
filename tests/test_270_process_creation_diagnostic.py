"""Unit contracts for #270 diagnostic; never launch Windows or touch user data."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts/diagnose_270_process_creation.py"


def load_diagnostic():
    spec = importlib.util.spec_from_file_location("sorigul_issue_270", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_270_diagnostic_preserves_status_and_expected_exit(tmp_path):
    module = load_diagnostic()
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(returncode=23)

    row = module.attempt(
        "synthetic_child", ["synthetic.exe", "exit(23)"],
        ("owned_fixture", tmp_path), ("inherited", {}),
        "pipes", 23, tmp_path, runner=fake_run,
    )
    assert row["outcome"] == "PASS"
    assert row["exit_code"] == 23
    assert calls[0][1]["timeout"] == 20
    assert row["expected_exit"] == 23
    assert "release_gate" not in row


def test_270_diagnostic_reports_winerror5_without_private_path(tmp_path):
    module = load_diagnostic()
    sensitive = "C:/Users/private_person/ProtectedSecret.txt"
    failure = PermissionError(13, "denied", sensitive)
    failure.winerror = 5

    def blocked(*args, **kwargs):
        raise failure

    row = module.attempt(
        "ps5", ["powershell.exe"], ("synthetic_fixture", tmp_path),
        ("synthetic_fixture", {"SECRET": "private-value"}),
        "files", 0, tmp_path, runner=blocked,
    )
    serialized = json.dumps(row)
    assert row["outcome"] == "LAUNCH_ERROR"
    assert row["winerror"] == 5
    assert sensitive not in serialized
    assert "private-value" not in serialized


def test_270_probe_matrix_never_bypasses_security_or_mutates_user(tmp_path):
    module = load_diagnostic()
    probes = module.build_probes(
        Path("C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"),
        Path("C:/Windows/System32/cmd.exe"),
        Path("C:/python/python.exe"),
    )
    assert len(probes) == 4
    assert [expected for _, _, expected in probes] == [0, 0, 0, 23]
    assert all("-ExecutionPolicy" not in argv for _, argv, _ in probes)
    source = SCRIPT.read_text(encoding="utf-8")
    for prohibited in ("Set-ExecutionPolicy", "msiexec", "taskkill",
                       "build_windows_installer", "build_local_whisper_runtime"):
        assert prohibited not in source
    assert '"release_gate": "NOT_TESTED"' in source
