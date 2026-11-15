"""#270 Windows CreateProcess/WinError5 read-only, synthetic-only diagnostic.

Runs a bounded matrix of harmless child-process launches. It never changes
security policy, user files, existing Sorigul installations, or release gates.
Output deliberately excludes local paths, command arguments and child stderr.
Running this successfully is NOT canonical regression/preflight acceptance.
"""
import argparse
import base64
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def attempt(label, argv, cwd, env, io_mode, expected, scratch, *, runner=subprocess.run):
    """Execute one synthetic child; report only safe categories, no raw paths."""
    row = {"probe": label, "cwd": cwd[0], "environment": env[0],
           "io": io_mode, "expected_exit": expected}
    options = {"cwd": cwd[1], "env": env[1], "timeout": 20}
    try:
        if io_mode == "files":
            # Transient streams reproduce the canonical bootstrap test's
            # non-pipe branch. Only the owned temporary directory is written.
            with tempfile.TemporaryFile(dir=scratch) as stdout:
                with tempfile.TemporaryFile(dir=scratch) as stderr:
                    result = runner(argv, stdout=stdout, stderr=stderr, **options)
        else:
            result = runner(argv, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, **options)
        row["exit_code"] = result.returncode
        row["outcome"] = "PASS" if result.returncode == expected else "EXIT_MISMATCH"
    except subprocess.TimeoutExpired:
        row["outcome"] = "TIMEOUT"
    except OSError as exc:
        row["outcome"] = "LAUNCH_ERROR"
        row["winerror"] = getattr(exc, "winerror", None)
        row["errno"] = getattr(exc, "errno", None)
        # NEVER include str(exc): it may contain private local paths.
    return row


def build_probes(powershell, cmd, python):
    encoded = lambda code: base64.b64encode(code.encode("utf-16-le")).decode("ascii")
    nested = ("$ErrorActionPreference='Stop'; "
              "$p=Start-Process -FilePath $env:SORIGUL_270_PYTHON "
              "-ArgumentList @('-c','exit(23)') -Wait -PassThru; "
              "if ($null -eq $p) { exit 90 }; exit $p.ExitCode")
    return [
        ("native_cmd", [str(cmd), "/d", "/c", "exit", "0"], 0),
        ("native_python", [str(python), "-c", "exit(0)"], 0),
        ("ps5_encoded", [str(powershell), "-NoProfile", "-NonInteractive",
                         "-EncodedCommand", encoded("exit 0")], 0),
        ("ps5_start_process_python", [str(powershell), "-NoProfile", "-NonInteractive",
                                      "-EncodedCommand", encoded(nested)], 23),
    ]


def run_matrix(repeats=1):
    if os.name != "nt":
        return {"status": "WINDOWS_REQUIRED", "release_gate": "NOT_TESTED", "rows": []}
    system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    powershell = system_root / "System32/WindowsPowerShell/v1.0/powershell.exe"
    cmd = system_root / "System32/cmd.exe"
    python = Path(sys.executable)
    if not all(path.is_file() for path in (powershell, cmd, python)):
        return {"status": "REQUIRED_EXECUTABLE_MISSING", "release_gate": "NOT_TESTED",
                "rows": []}
    with tempfile.TemporaryDirectory(prefix="sorigul-270-synthetic-") as dirname:
        scratch = Path(dirname)
        unicode_cwd = scratch / "한글 with spaces"
        unicode_cwd.mkdir()
        synthetic_local = scratch / "LOCALAPPDATA"
        synthetic_roaming = scratch / "APPDATA"
        synthetic_profile = scratch / "USERPROFILE"
        for path in (synthetic_local, synthetic_roaming, synthetic_profile):
            path.mkdir()
        inherited = dict(os.environ)
        inherited["SORIGUL_270_PYTHON"] = str(python)
        fixture = dict(inherited)
        # Mirrors #113 synthetic child ONLY. No persistent host changes.
        fixture.update(PSModulePath=str(scratch / "unresolvable PS7 module path"),
                       LOCALAPPDATA=str(synthetic_local), APPDATA=str(synthetic_roaming),
                       USERPROFILE=str(synthetic_profile),
                       TEMP=str(scratch), TMP=str(scratch))
        environments = [("inherited", inherited), ("synthetic_fixture", fixture)]
        locations = [("repository", Path(__file__).resolve().parents[1]),
                     ("unicode_temporary", unicode_cwd)]
        probes = build_probes(powershell, cmd, python)
        rows = []
        for index in range(repeats):
            for environment in environments:
                for location in locations:
                    for io_mode in ("pipes", "files"):
                        for label, argv, expected in probes:
                            row = attempt(label, argv, location, environment,
                                          io_mode, expected, scratch)
                            row["iteration"] = index + 1
                            rows.append(row)
        failures = sum(row["outcome"] != "PASS" for row in rows)
        return {"status": "DIAGNOSTIC_ONLY", "release_gate": "NOT_TESTED",
                "tests": len(rows), "failures": failures, "rows": rows}


def main():
    parser = argparse.ArgumentParser(description="Issue #270 synthetic launch diagnostic")
    parser.add_argument("--repeats", type=int, choices=(1, 2), default=1,
                        help="1 (default) or 2 passes; never retries release gates")
    args = parser.parse_args()
    result = run_matrix(args.repeats)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    # A passing matrix is only evidence. Canonical regression remains required.
    return 0 if result["status"] == "DIAGNOSTIC_ONLY" and result["failures"] == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
