import base64
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def read_repo(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_113_preflight_owns_working_directories_and_reuses_canonical_regression():
    script = read_repo("scripts/run_113_preflight.ps1")

    assert "$Backend = Join-Path $RepoRoot 'backend'" in script
    assert "$CoreRegression = Join-Path $PSScriptRoot 'run_core_workflow_regression.ps1'" in script
    assert "Invoke-Checked -WorkingDirectory $Backend -Command $Python" in script
    assert "tests/test_release_packaging_contract.py" in script
    assert "tests/test_installer_powershell5_restricted_invocation.py" in script
    assert "tests/test_core_powershell5_process_observation.py" in script
    assert "Invoke-Checked -WorkingDirectory $RepoRoot -Command $TrustedPowerShell" in script


def test_113_preflight_locks_source_and_trusted_windows_boundaries():
    script = read_repo("scripts/run_113_preflight.ps1")

    for required in (
        "WindowsPowerShell\\v1.0\\powershell.exe",
        "taskkill.exe",
        "Get-AuthenticodeSignature",
        "rev-parse', 'HEAD'",
        "rev-parse', '@{u}'",
        "status --porcelain --untracked-files=no",
        "diff --check",
        "diff --cached --check",
        "Get-ExecutionPolicy -List",
    ):
        assert required in script

    assert "Set-ExecutionPolicy" not in script


@pytest.mark.skipif(os.name != "nt", reason="actual Windows PowerShell 5")
def test_ps5_read_only_probes_preserve_quotes_across_native_boundary(tmp_path):
    script = read_repo("scripts/run_113_preflight.ps1")
    start = script.index("function Invoke-TrustedPowerShellReadOnly {")
    helper = script[start:script.index("\nfunction Assert-TrustedWindowsExecutable", start)]
    # Use the production probe expressions, including embedded format quotes.
    probes = {}
    for name in ("PsIdentity", "PolicySnapshot"):
        block = script.split(f"${name} = @(\n", 1)[1].split("\n)", 1)[0]
        probes[name] = block.strip()

    powershell = (
        Path(os.environ["SystemRoot"])
        / "System32/WindowsPowerShell/v1.0/powershell.exe"
    )
    harness = tmp_path / "read only probes 한글 with spaces.ps1"
    harness.write_text(
        "$ErrorActionPreference = 'Stop'\n"
        "$TrustedPowerShell = Join-Path ([Environment]::SystemDirectory) "
        "'WindowsPowerShell\\v1.0\\powershell.exe'\n"
        f"{helper}\n"
        f"{probes['PsIdentity']}\n"
        "if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }\n"
        f"{probes['PolicySnapshot']}\n"
        "exit $LASTEXITCODE\n",
        encoding="utf-8-sig",
    )
    # A real PS5 -File parent recreates the failing native child-call boundary.
    environment = os.environ.copy()
    # Python can inherit PS7-only module paths during source-level validation.
    # Restrict this isolated PS5 parent to its own native modules.
    environment["PSModulePath"] = str(powershell.parent / "Modules")
    result = subprocess.run(
        [str(powershell), "-NoProfile", "-NonInteractive", "-ExecutionPolicy",
         "Bypass", "-File", str(harness)],
        capture_output=True,
        text=True,
        env=environment,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    lines = result.stdout.splitlines()
    assert len(lines) == 6
    assert lines[0].startswith("5.1.") and lines[0].endswith("|Desktop")
    policies = dict(line.split("=", 1) for line in lines[1:])
    assert set(policies) == {
        "MachinePolicy", "UserPolicy", "Process", "CurrentUser", "LocalMachine",
    }
    assert policies["Process"] == "Bypass"


@pytest.mark.skipif(os.name != "nt", reason="actual Windows PowerShell 5")
@pytest.mark.parametrize("script_path", [
    "scripts/run_113_preflight.ps1",
    "scripts/run_core_workflow_regression.ps1",
])
@pytest.mark.parametrize("exit_code", [0, 23])
def test_python_child_observes_restricted_and_parent_preference_is_restored(
    tmp_path, script_path, exit_code
):
    script = read_repo(script_path)
    start = script.index("function Invoke-Checked {")
    helper = script[start:script.index("\n}\n", start) + 3]
    powershell = (
        Path(os.environ["SystemRoot"])
        / "System32/WindowsPowerShell/v1.0/powershell.exe"
    )
    encoded_policy = base64.b64encode(
        "Get-ExecutionPolicy".encode("utf-16-le")
    ).decode("ascii")
    child = tmp_path / "observe child environment.py"
    child.write_text(
        "import json, os, subprocess, sys\n"
        f"policy = subprocess.check_output([{str(powershell)!r}, "
        f"'-NoProfile', '-NonInteractive', '-EncodedCommand', {encoded_policy!r}], "
        "text=True).strip()\n"
        "print(json.dumps({'preference': os.environ.get('PSExecutionPolicyPreference'), "
        "'policy': policy}))\n"
        f"sys.exit({exit_code})\n",
        encoding="utf-8",
    )
    harness = tmp_path / "python invocation parent.ps1"
    harness.write_text(
        "$ErrorActionPreference = 'Stop'\n"
        "$Python = $env:SORIGUL_TEST_PYTHON\n"
        f"{helper}\n"
        "try {\n"
        "    Invoke-Checked -WorkingDirectory $PSScriptRoot -Command $Python "
        "-Arguments @($env:SORIGUL_TEST_CHILD)\n"
        "    Write-Output 'COMMAND_OK'\n"
        "} catch { Write-Output ('COMMAND_FAILED=' + $_.Exception.Message) }\n"
        "Write-Output ('RESTORED=' + $env:PSExecutionPolicyPreference)\n",
        encoding="utf-8-sig",
    )
    environment = os.environ.copy()
    environment.update(
        PSModulePath=str(powershell.parent / "Modules"),
        SORIGUL_TEST_PYTHON=sys.executable,
        SORIGUL_TEST_CHILD=str(child),
    )
    result = subprocess.run(
        [str(powershell), "-NoProfile", "-NonInteractive", "-ExecutionPolicy",
         "Bypass", "-File", str(harness)],
        capture_output=True,
        text=True,
        env=environment,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    lines = result.stdout.splitlines()
    assert json.loads(lines[0]) == {"preference": None, "policy": "Restricted"}
    if exit_code == 0:
        assert lines[1] == "COMMAND_OK"
    else:
        assert lines[1].startswith("COMMAND_FAILED=Command failed with exit code 23:")
    assert lines[2] == "RESTORED=Bypass"


def test_113_preflight_never_invokes_release_artifact_or_install_commands():
    script = read_repo("scripts/run_113_preflight.ps1").lower()

    for forbidden in (
        "build_local_whisper_runtime.ps1",
        "build_backend_sidecar.ps1",
        "build_windows_installer.ps1",
        "msiexec",
        "--bundles msi",
    ):
        assert forbidden not in script


def test_readme_exposes_one_canonical_113_preflight_entrypoint():
    readme = read_repo("README.md")

    assert "## #113 canonical preflight" in readme
    assert "scripts\\run_113_preflight.ps1" in readme
    assert "-ExecutionPolicy Bypass" in readme
    assert "child command를 직접 재구성하지 않는다" in readme


def test_development_rules_lock_preflight_first_and_checkpoint_retry_semantics():
    rules = read_repo("docs/project/DEVELOPMENT_RULES.md")

    for required in (
        "scripts/run_113_preflight.ps1",
        "preflight PASS 후에만 새 artifact run_id",
        "동일 HEAD + 동일 run_id + 동일 release-input identity",
        "harness/invocation failure",
        "source HEAD 또는 release input 변경",
        "artifact hash/provenance mismatch",
    ):
        assert required in rules
