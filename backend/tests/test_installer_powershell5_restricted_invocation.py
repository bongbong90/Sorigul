"""#161: canonical installer must run the nested Core build under Restricted PS5.

Actual Windows PowerShell 5.1 with an effective Restricted policy rejects
`& child.ps1`. The installer's nested-build helper must keep working without
changing the policy. Only synthetic `.ps1` children are used; the real build
script and any Core artifact are never touched.
"""

import base64
import os
import re
import subprocess
from pathlib import Path

import pytest

from src.services.windows_system import resolve_system32_executable


REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALLER = REPO_ROOT / "scripts/build_windows_installer.ps1"
HELPER_NAME = "Invoke-CanonicalSidecarBuild"


def _installer_text() -> str:
    return INSTALLER.read_text(encoding="utf-8")


def _helper_source() -> str:
    source = _installer_text()
    start = source.index(f"function {HELPER_NAME} {{")
    return source[start:source.index("\n$RepoRoot = ", start)]


# --- static contract -------------------------------------------------------


def test_installer_never_changes_or_overrides_execution_policy():
    installer = _installer_text()
    for forbidden in (
        "Set-ExecutionPolicy",
        "-ExecutionPolicy",
        "ExecutionPolicy Bypass",
        "ExecutionPolicy Unrestricted",
        "PSExecutionPolicyPreference",
    ):
        assert forbidden not in installer


def test_nested_core_helper_targets_only_canonical_script_and_trusted_ps5():
    helper = _helper_source()
    installer = _installer_text()

    assert "param(" not in helper.lower()
    assert 'Join-Path $PSScriptRoot "build_backend_sidecar.ps1"' in helper
    code = [line for line in helper.splitlines() if not line.lstrip().startswith("#")]
    assert [line for line in code if ".ps1" in line] == [
        '    $SidecarScript = Join-Path $PSScriptRoot "build_backend_sidecar.ps1"'
    ]
    assert "[System.Environment]::SystemDirectory" in helper
    assert "WindowsPowerShell\\v1.0\\powershell.exe" in helper
    assert "-NoProfile -NonInteractive -EncodedCommand" in helper
    assert "$env:" not in helper and "Get-Command" not in helper
    # Called with no arguments and never as a direct script invocation.
    assert re.findall(rf"{HELPER_NAME}(?!\s*\{{)", installer).count(HELPER_NAME) == 1
    assert 'build_backend_sidecar.ps1")\n' not in installer.replace(helper, "")
    assert "& (Join-Path $PSScriptRoot" not in installer


def test_installer_stops_before_frontend_on_exact_nested_exit_code():
    installer = _installer_text()
    call = installer.index(f"$SidecarExitCode = {HELPER_NAME}")
    stop = installer.index("exit $SidecarExitCode", call)
    assert "if ($SidecarExitCode -ne 0) {" in installer[call:stop]
    assert stop < installer.index("Building frontend production bundle")


# --- actual Windows PowerShell 5 under effective Restricted policy ---------


@pytest.fixture(scope="module")
def ps5():
    if os.name != "nt":
        pytest.skip("actual Windows PowerShell 5")
    powershell = (
        resolve_system32_executable("taskkill.exe").parent
        / "WindowsPowerShell/v1.0/powershell.exe"
    )
    if not powershell.is_file():
        pytest.skip("Windows PowerShell 5 is not installed")
    return powershell


def _run(ps5, command, *, extra_env=None):
    env = dict(os.environ)
    # A per-process preference (not a policy change) can mask the real
    # effective policy; the test must observe the machine's Restricted default.
    env.pop("PSExecutionPolicyPreference", None)
    env.update(extra_env or {})
    encoded = base64.b64encode(command.encode("utf-16-le")).decode("ascii")
    return subprocess.run(
        [str(ps5), "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=120,
    )


def _policy_snapshot(ps5):
    result = _run(
        ps5,
        "[Console]::OutputEncoding=[Text.Encoding]::UTF8;"
        "$PSVersionTable.PSEdition;$PSVersionTable.PSVersion.ToString();"
        "Get-ExecutionPolicy;"
        "Get-ExecutionPolicy -List | ForEach-Object { \"$($_.Scope)=$($_.ExecutionPolicy)\" }",
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.split()


@pytest.fixture
def restricted(ps5):
    before = _policy_snapshot(ps5)
    assert before[0] == "Desktop" and before[1].startswith("5.1")
    assert before[2] == "Restricted", "effective policy must be Restricted"
    yield before
    assert _policy_snapshot(ps5) == before, "execution policy must not change"


@pytest.fixture
def scripts_dir(tmp_path):
    path = tmp_path / "스크립트 폴더 with spaces" / "scripts"
    path.mkdir(parents=True)
    return path


def _invoke_helper(ps5, scripts_dir, child_source):
    child = scripts_dir / "build_backend_sidecar.ps1"
    child.write_text(child_source, encoding="utf-8-sig")
    quoted_dir = "'" + str(scripts_dir).replace("'", "''") + "'"
    helper = _helper_source().replace("$PSScriptRoot", quoted_dir)
    return child, _run(
        ps5,
        "[Console]::OutputEncoding=[Text.Encoding]::UTF8\n"
        "$ErrorActionPreference = 'Stop'\n"
        f"{helper}\n"
        f"$Code = {HELPER_NAME}\n"
        "Write-Host \"HELPER_EXIT=$Code\"\n"
        "exit $Code\n",
    )


def test_direct_child_ps1_invocation_is_blocked_under_restricted(ps5, restricted, scripts_dir):
    child = scripts_dir / "build_backend_sidecar.ps1"
    child.write_text("exit 0\n", encoding="utf-8-sig")
    quoted = "'" + str(child).replace("'", "''") + "'"
    result = _run(ps5, f"$ErrorActionPreference='Stop'; & {quoted}; exit 0")
    assert result.returncode != 0
    assert "UnauthorizedAccess" in result.stderr or "running scripts is disabled" in result.stderr


def test_nested_invocation_preserves_file_identity_and_exit_zero(ps5, restricted, scripts_dir):
    child, result = _invoke_helper(
        ps5,
        scripts_dir,
        'Write-Output "ROOT=$PSScriptRoot"\n'
        'Write-Output "CMD=$PSCommandPath"\n'
        'Write-Output "REPOROOT=$(Split-Path -Parent $PSScriptRoot)"\n'
        "exit 0\n",
    )
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert f"ROOT={scripts_dir}" in lines
    assert f"CMD={child}" in lines
    assert f"REPOROOT={scripts_dir.parent}" in lines
    assert "HELPER_EXIT=0" in lines


def test_normal_completion_without_explicit_exit_is_success(ps5, restricted, scripts_dir):
    _, result = _invoke_helper(ps5, scripts_dir, 'Write-Output "DONE"\n')
    assert result.returncode == 0, result.stderr
    assert "HELPER_EXIT=0" in result.stdout


def test_nested_invocation_propagates_exact_nonzero_exit(ps5, restricted, scripts_dir):
    _, result = _invoke_helper(ps5, scripts_dir, 'Write-Output "BEFORE"\nexit 23\nWrite-Output "AFTER"\n')
    assert result.returncode == 23, result.stderr
    assert "HELPER_EXIT=23" in result.stdout
    assert "BEFORE" in result.stdout and "AFTER" not in result.stdout


def test_nested_exception_fails_closed(ps5, restricted, scripts_dir):
    _, result = _invoke_helper(ps5, scripts_dir, '$ErrorActionPreference = "Stop"\nthrow "SYNTHETIC_FAILURE"\n')
    assert result.returncode != 0
    assert "HELPER_EXIT=0" not in result.stdout
    assert "SYNTHETIC_FAILURE" in result.stderr


def test_nested_parse_failure_fails_closed_without_executing(ps5, restricted, scripts_dir):
    marker = scripts_dir / "executed.marker"
    quoted_marker = "'" + str(marker).replace("'", "''") + "'"
    _, result = _invoke_helper(
        ps5,
        scripts_dir,
        f"Set-Content -LiteralPath {quoted_marker} -Value ran\nif ($true {{\n",
    )
    assert result.returncode != 0
    assert "SIDECAR_BUILD_SCRIPT_PARSE_FAILED" in result.stderr
    assert not marker.exists()


def test_nested_invocation_leaves_no_powershell_residue(ps5, restricted, scripts_dir):
    _invoke_helper(ps5, scripts_dir, "exit 0\n")
    needle = str(scripts_dir.parent.name).replace("'", "''")
    probe = _run(
        ps5,
        "[Console]::OutputEncoding=[Text.Encoding]::UTF8;"
        "$n = 0; foreach ($p in Get-CimInstance Win32_Process -Filter \"Name='powershell.exe'\") {"
        f" if ($p.ProcessId -ne $PID -and $p.CommandLine -like '*{needle}*') {{ $n++ }} }}; $n",
    )
    assert probe.returncode == 0, probe.stderr
    assert probe.stdout.strip() == "0"
    assert not [p for p in scripts_dir.iterdir() if p.name != "build_backend_sidecar.ps1"]
