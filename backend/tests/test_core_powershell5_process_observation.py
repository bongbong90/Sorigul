"""#159: run Core's packaging observation/acceptance blocks in actual PS5.

Only synthetic children and pytest-owned logs are used; the build script is
never invoked. Unlike Local's redirected Start-Process path, the current Core
path retained exact exit codes in the PS5 diagnostic, so keep production intact.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from src.services.windows_system import resolve_system32_executable
from src.sidecar_main import REQUIRED_SELF_TEST_CHECKS


REPO_ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(os.name != "nt", reason="actual Windows PowerShell 5")


@pytest.fixture
def observe_core(tmp_path):
    taskkill = resolve_system32_executable("taskkill.exe")
    powershell = taskkill.parent / "WindowsPowerShell/v1.0/powershell.exe"
    if not powershell.is_file():
        pytest.skip("Windows PowerShell 5 is not installed")

    source = (REPO_ROOT / "scripts/build_backend_sidecar.ps1").read_text(encoding="utf-8")
    resolver_start = source.index("function Resolve-TrustedTaskkill {")
    resolver = source[resolver_start:source.index("\nfunction Write-Step", resolver_start)]
    process_start = source.index("    $SelfTestProcess = Start-Process")
    acceptance_start = source.index("    if (-not (Test-Path -LiteralPath $SelfTestLog", process_start)
    process = source[process_start:acceptance_start]
    # Substitute the synthetic command only; retain production poll/exit/cleanup.
    process = process.replace('-ArgumentList "--self-test"', "-ArgumentList $ChildArguments")
    process = process.replace("        -PassThru", "        -WindowStyle Hidden `\n        -PassThru")
    acceptance = source[acceptance_start:source.index("    $CandidateExeMetadata", acceptance_start)]

    child_script = tmp_path / "synthetic child.py"
    descendant_pid = tmp_path / "descendant.pid"
    child_script.write_text(
        "import os, subprocess, sys, time\n"
        "from pathlib import Path\n"
        "if sys.argv[1] == 'timeout':\n"
        "    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        "    Path(os.environ['SORIGUL_TEST_DESCENDANT_PID']).write_text(str(child.pid))\n"
        "    time.sleep(60)\n"
        "else:\n"
        "    sys.exit(int(sys.argv[1]))\n",
        encoding="utf-8",
    )
    log = tmp_path / "sorigul-backend-selftest.log"
    result_path = tmp_path / "observation.json"
    rows = []

    def run(exit_code=0, *, repeats=1, child_kind="python", log_case="complete", inject_null=False):
        lines = [f"[self-test] {check}: PASS" for check in REQUIRED_SELF_TEST_CHECKS]
        if log_case == "missing":
            log.unlink(missing_ok=True)
        else:
            if log_case == "incomplete":
                lines.pop()
            elif log_case == "duplicate":
                lines.append(lines[0])
            log.write_text("\n".join(lines) + "\n", encoding="utf-8")

        environment = os.environ.copy()
        environment.update(
            SORIGUL_TEST_PYTHON=sys.executable,
            SORIGUL_TEST_ROOT=str(tmp_path),
            SORIGUL_TEST_CHILD=str(child_script),
            SORIGUL_TEST_DESCENDANT_PID=str(descendant_pid),
            SORIGUL_TEST_RESULT=str(result_path),
            SORIGUL_TEST_EXIT=str(exit_code),
            SORIGUL_TEST_CHILD_KIND=child_kind,
            SORIGUL_TEST_REPEATS=str(repeats),
            SORIGUL_TEST_INJECT_NULL=str(int(inject_null)),
        )
        harness = r"""
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSEdition -ne 'Desktop') {
    throw 'ACTUAL_WINDOWS_POWERSHELL5_REQUIRED'
}
__RESOLVER__
$TaskkillPath = Resolve-TrustedTaskkill
$CandidateExe = $env:SORIGUL_TEST_PYTHON
$CandidateDir = $env:SORIGUL_TEST_ROOT
$SelfTestLog = Join-Path $CandidateDir 'sorigul-backend-selftest.log'
$ChildArguments = '"' + $env:SORIGUL_TEST_CHILD + '" ' + $env:SORIGUL_TEST_EXIT
if ($env:SORIGUL_TEST_CHILD_KIND -eq 'native-cmd') {
    $CandidateExe = Join-Path ([Environment]::SystemDirectory) 'cmd.exe'
    $ChildArguments = '/d /c exit ' + $env:SORIGUL_TEST_EXIT
}
$SelfTestTimeoutSeconds = if ($env:SORIGUL_TEST_EXIT -eq 'timeout') { 2 } else { 5 }
$Rows = @()
for ($Iteration = 1; $Iteration -le [int]$env:SORIGUL_TEST_REPEATS; $Iteration++) {
    $SelfTestProcess = $null
    $SelfTestExit = $null
    $SelfTestTimedOut = $false
    $Accepted = $false
    $Failure = $null
    $Clock = [Diagnostics.Stopwatch]::StartNew()
    try {
__PROCESS__
        if ($env:SORIGUL_TEST_INJECT_NULL -eq '1') { $SelfTestExit = $null }
__ACCEPTANCE__
        $Accepted = $true
    } catch {
        $Failure = $_.Exception.Message
    } finally {
        $Clock.Stop()
        $ProcessIds = @($SelfTestProcess.Id)
        if (Test-Path -LiteralPath $env:SORIGUL_TEST_DESCENDANT_PID) {
            $ProcessIds += [int][IO.File]::ReadAllText($env:SORIGUL_TEST_DESCENDANT_PID)
        }
        $Orphans = @(foreach ($ProcessId in $ProcessIds) {
            if ($null -ne (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)) { $ProcessId }
        })
        $Rows += [pscustomobject]@{
            ps_version = $PSVersionTable.PSVersion.ToString()
            ps_edition = $PSVersionTable.PSEdition
            pid = $SelfTestProcess.Id
            descendant_pid = if ($ProcessIds.Count -eq 2) { $ProcessIds[1] } else { $null }
            has_exited = $SelfTestProcess.HasExited
            exit_code = $SelfTestExit
            exit_type = if ($null -eq $SelfTestExit) { 'null' } else { $SelfTestExit.GetType().FullName }
            timed_out = $SelfTestTimedOut
            accepted = $Accepted
            failure = $Failure
            orphans = $Orphans
            elapsed_ms = $Clock.ElapsedMilliseconds
            taskkill = $TaskkillPath
            cleanup_exit = if ($SelfTestTimedOut) { $TaskKillExit } else { $null }
            cleanup_stopped = if ($SelfTestTimedOut) { $Stopped } else { $null }
        }
        # Emergency cleanup cannot turn an orphan observation into a PASS.
        foreach ($ProcessId in $Orphans) {
            & $TaskkillPath /PID $ProcessId /T /F | Out-Null
            if ($LASTEXITCODE -ne 0) { throw 'SYNTHETIC_EMERGENCY_CLEANUP_FAILED' }
        }
        $SelfTestProcess.Dispose()
    }
}
[IO.File]::WriteAllText($env:SORIGUL_TEST_RESULT, (ConvertTo-Json -InputObject $Rows -Depth 5))
"""
        harness = harness.replace("__RESOLVER__", resolver)
        harness = harness.replace("__PROCESS__", process).replace("__ACCEPTANCE__", acceptance)
        completed = subprocess.run(
            [str(powershell), "-NoProfile", "-NonInteractive", "-Command", harness],
            env=environment,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr
        observed = json.loads(result_path.read_text(encoding="utf-8-sig"))
        assert len(observed) == repeats
        for row in observed:
            assert row["ps_version"].startswith("5.1.")
            assert row["ps_edition"] == "Desktop"
            assert row["has_exited"] is True
            assert row["orphans"] == []
            assert Path(row["taskkill"]) == taskkill
        rows.extend(observed)
        return observed

    yield run
    # Printed only with pytest -s; useful for issue/PR evidence without new docs.
    print("CORE_PS5_EVIDENCE=" + json.dumps(rows))


@pytest.mark.parametrize("child_kind", ["python", "native-cmd"])
@pytest.mark.parametrize("exit_code", [0, 23])
def test_core_ps5_retains_exact_synthetic_child_exit_code(observe_core, exit_code, child_kind):
    for row in observe_core(exit_code, repeats=12, child_kind=child_kind):
        assert type(row["exit_code"]) is int
        assert row["exit_code"] == exit_code
        assert row["exit_type"] == "System.Int32"
        assert row["timed_out"] is False
        assert row["accepted"] is (exit_code == 0)
        assert row["failure"] == (None if exit_code == 0 else "PACKAGED_SELFTEST_FAILED: exit 23")


def test_core_ps5_bounded_timeout_reaps_synthetic_process_tree(observe_core):
    for row in observe_core("timeout", repeats=2):
        assert row["descendant_pid"] is not None
        assert row["timed_out"] is True
        assert row["accepted"] is False
        assert row["failure"] == "PACKAGED_SELFTEST_TIMEOUT"
        assert row["cleanup_exit"] == 0
        assert row["cleanup_stopped"] is True
        assert 2000 <= row["elapsed_ms"] < 15000


@pytest.mark.parametrize(
    "log_case,inject_null,expected_failure",
    [
        ("complete", True, "PACKAGED_SELFTEST_FAILED: exit "),
        ("missing", False, "PACKAGED_SELFTEST_LOG_MISSING"),
        ("incomplete", False, "PACKAGED_SELFTEST_INCOMPLETE:"),
        ("duplicate", False, "PACKAGED_SELFTEST_INCOMPLETE:"),
    ],
)
def test_core_ps5_acceptance_stays_fail_closed(
    observe_core, log_case, inject_null, expected_failure
):
    row = observe_core(log_case=log_case, inject_null=inject_null)[0]
    assert row["timed_out"] is False
    assert row["accepted"] is False
    assert row["failure"].startswith(expected_failure)
    if inject_null:
        assert row["exit_code"] is None
    else:
        assert row["exit_code"] == 0
