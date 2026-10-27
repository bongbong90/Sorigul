"""#164: actual PS5 lifecycle in disposable Git repositories, never a #113 run."""
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts/run_113_session_bootstrap.ps1"
PS5 = Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
WINDOWS = pytest.mark.skipif(os.name != "nt", reason="actual Windows PS5 required")


def test_repository_owns_one_guard_and_activation_boundary():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "'Probe', 'Start', 'Guard', 'Status', 'Stop'" in source
    assert source.count("if ($Mode -eq 'Guard') {") == 1
    assert "Security.Cryptography.SHA256" in source
    assert "Get-FileHash" not in source
    assert "EnvironmentVariables.Clear" not in source
    assert "$env:PSModulePath =" not in source
    assert "SESSION_BOOTSTRAPPING.json" in source
    assert "SESSION_ACTIVE.json" in source
    assert "SESSION_STOPPED.json" in source
    assert "BOOTSTRAP FAILED / ARTIFACT SESSION NOT STARTED" in source
    assert "HARD_STOP" in source
    for forbidden in ("Set-ExecutionPolicy", "build_local_whisper_runtime.ps1",
                      "build_backend_sidecar.ps1", "build_windows_installer.ps1",
                      "git reset", "git clean", "git rebase", "msiexec.exe"):
        assert forbidden not in source
    preflight = (REPO / "scripts/run_113_preflight.ps1").read_text(encoding="utf-8")
    assert "'-Mode', 'Probe'" in preflight
    assert preflight.index("'-Mode', 'Probe'") < preflight.index("PRE-BUILD REHEARSAL: PASS")
    rules = (REPO / "docs/project/DEVELOPMENT_RULES.md").read_text(encoding="utf-8")
    assert "SESSION_ACTIVE.json" in rules
    assert "inline/ad-hoc guard" in rules


def read_json_function(source):
    start = source.index("function Read-Json(")
    return source[start:source.index("\nfunction ", start + 1)]


def test_read_json_missing_retry_is_opt_in_for_heartbeat_only():
    source = SCRIPT.read_text(encoding="utf-8")
    body = read_json_function(source)
    # [switch] defaults to OFF: missing evidence keeps fail-fast semantics.
    assert body.startswith("function Read-Json([string]$Path, [switch]$RetryMissing) {")
    assert "$NativeCode = $_.Exception.HResult -band 65535" in body
    assert "$NativeCode -in @(32, 33)" in body
    assert "($RetryMissing -and $NativeCode -eq 2)" in body
    assert "@(2" not in body and "2, 32" not in body
    # Bounded: the pre-existing 10 attempts x 20ms, then the original exception.
    assert "for ($Attempt = 0; $Attempt -lt 10; $Attempt++)" in body
    assert "[Threading.Thread]::Sleep(20)" in body
    assert "if (-not $Retryable -or $Attempt -eq 9) { throw }" in body
    assert body.count("catch") == 1 and "catch [IO.IOException]" in body
    for fallback in ("return $null", "'{}'", '"{}"', "@{}", "SilentlyContinue"):
        assert fallback not in body
    calls = [line.strip() for line in source.splitlines()
             if "Read-Json " in line and "function Read-Json" not in line]
    opted = [line for line in calls if "-RetryMissing" in line]
    assert opted == ["$Heartbeat = Read-Json (Join-Path $Config.session 'LOCK_HEARTBEAT.json') -RetryMissing"]
    assert source.count("-RetryMissing") == 1
    for name in ("$FreezeFile", "SESSION_BOOTSTRAPPING.json", "GUARD_OWNER.json", "$Stop",
                 "$Request", "$BaselinePath", "SESSION_STOPPED.json", "$Settings"):
        assert any(name in line for line in calls), name
        assert not any(name in line and "-RetryMissing" in line for line in calls), name
    # The writer, staleness and stabilization contracts are unchanged.
    assert "[IO.File]::Replace($Temporary, $Path, [System.Management.Automation.Language.NullString]::Value)" in source
    assert "-notin @(32, 33) -or $Attempt -eq 9) { throw }" in source
    assert ".TotalSeconds -gt 10 -or" in source
    assert "[ValidateRange(3, 120)][int]$StableSeconds = 6" in source


def git(cwd, *args):
    return subprocess.check_output(["git", "-C", str(cwd), *args], text=True, encoding="utf-8").strip()


@pytest.fixture
def sandbox(tmp_path):
    if os.name != "nt":
        pytest.skip("actual Windows PS5 required")
    root = tmp_path / "bootstrap 한글 with spaces"
    root.mkdir()
    remote = tmp_path / "origin.git"
    git(tmp_path, "init", "--bare", str(remote))
    git(root, "init", "-b", "fixture")
    git(root, "config", "user.name", "Bootstrap contract fixture")
    git(root, "config", "user.email", "fixture@example.invalid")
    (root / "scripts").mkdir()
    script = root / "scripts" / SCRIPT.name
    shutil.copyfile(SCRIPT, script)
    (root / "input.txt").write_text("synthetic release input\n", encoding="utf-8")
    git(root, "add", "scripts/" + SCRIPT.name, "input.txt")
    git(root, "commit", "-m", "Synthetic #164 bootstrap fixture")
    git(root, "remote", "add", "origin", str(remote))
    git(root, "push", "-u", "origin", "fixture")
    environment = os.environ.copy()
    # Deliberately preserve a PS7/unresolvable module search environment. The
    # real guard imports native PS5 capabilities explicitly and hashes in .NET.
    environment["PSModulePath"] = str(tmp_path / "unresolvable PS7 module path")
    for key in ("LOCALAPPDATA", "APPDATA", "USERPROFILE"):
        value = tmp_path / key
        value.mkdir()
        environment[key] = str(value)
    environment["TEMP"] = str(tmp_path)
    environment["TMP"] = str(tmp_path)
    sandbox_data = root, script, environment, tmp_path
    yield sandbox_data
    # Even an assertion/parent timeout must not strand a synthetic ACTIVE guard.
    for owner_path in tmp_path.rglob("GUARD_OWNER.json"):
        session = owner_path.parent
        if (session / "SESSION_STOPPED.json").exists():
            continue
        owner = json.loads(owner_path.read_text(encoding="utf-8-sig"))
        stopped = run_ps5(command(sandbox_data, "Stop", "-SessionPath", session),
                          cwd=root, environment=environment, timeout=35)
        if stopped.returncode != 0:
            # Identity is verified by PS5 before terminating this fixture's PID.
            import base64
            check = f"try {{$p=[Diagnostics.Process]::GetProcessById({owner['pid']}); if($p.StartTime.ToUniversalTime().Ticks.ToString() -ceq '{owner['start_ticks']}') {{$p.Kill(); $null=$p.WaitForExit(10000)}}}} catch [ArgumentException] {{}}; exit 0"
            cleanup = run_ps5([str(PS5), "-NoProfile", "-NonInteractive", "-EncodedCommand", base64.b64encode(check.encode("utf-16-le")).decode()], timeout=20)
            assert cleanup.returncode == 0, cleanup.stdout + cleanup.stderr


def freeze(sandbox):
    import hashlib
    root, _, _, temp = sandbox
    path = temp / "fixture_freeze.json"
    path.write_text(json.dumps({
        "head": git(root, "rev-parse", "HEAD"), "branch": "fixture",
        "release_input_sha256": {
            name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in git(root, "ls-files").splitlines()
        },
    }), encoding="utf-8")
    return path


def command(sandbox, mode="Probe", *args):
    _, script, _, _ = sandbox
    return [str(PS5), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
            "-File", str(script), "-Mode", mode, *map(str, args)]


def run_ps5(arguments, environment=None, cwd=None, timeout=100, capture=False):
    # The Windows host intermittently terminates before any script instruction.
    # Retry ONLY empty-output native access violations without new session state;
    # never retry a guard/bootstrap result or a timeout. Every attempt is reported.
    import tempfile
    import warnings

    def session_markers():
        if environment is None or "TEMP" not in environment:
            return set()  # these calls are read/lock/PID helpers only
        return {str(path) for path in Path(environment["TEMP"]).rglob("*.json")
                if path.name.startswith("SESSION_") or path.name in
                {"GUARD_OWNER.json", "STOP_REQUEST.json", "ACTIVATE_REQUEST.json"}}

    for attempt in range(3):
        before = session_markers()
        if capture:
            result = subprocess.run(arguments, cwd=cwd, env=environment,
                                    text=True, encoding="utf-8", capture_output=True, timeout=timeout)
        else:
            with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
                process = subprocess.run(arguments, cwd=cwd, env=environment,
                                         stdout=output, stderr=errors, timeout=timeout)
                output.seek(0)
                errors.seek(0)
                result = subprocess.CompletedProcess(arguments, process.returncode,
                                                     output.read().decode("utf-8", errors="replace"),
                                                     errors.read().decode("utf-8", errors="replace"))
        if (result.returncode & 0xFFFFFFFF != 0xC0000005 or result.stdout or result.stderr
                or session_markers() != before or attempt == 2):
            return result
        warnings.warn(f"PS5 host startup 0xC0000005; no new session state; retry {attempt + 1}/2",
                      RuntimeWarning)


def invoke(sandbox, mode="Probe", *args, capture=False):
    root, _, environment, _ = sandbox
    return run_ps5(command(sandbox, mode, *args), environment=environment, cwd=root, capture=capture)


def start_args(sandbox):
    root, _, _, temp = sandbox
    return ["-ExpectedBranch", "fixture", "-ExpectedHead", git(root, "rev-parse", "HEAD"),
            "-FreezeFile", freeze(sandbox), "-EvidenceRoot", temp / "evidence", "-StableSeconds", 3]


def marker(sandbox, name):
    return list((sandbox[3] / "evidence").glob("*/" + name))


def assert_no_activation(sandbox, result):
    assert result.returncode != 0, result.stdout + result.stderr
    assert "BOOTSTRAP FAILED / ARTIFACT SESSION NOT STARTED" in result.stdout
    assert not marker(sandbox, "SESSION_ACTIVE.json")


def assert_pid_gone(pid):
    encoded = __import__("base64").b64encode(
        f"try {{ $p=[Diagnostics.Process]::GetProcessById({pid}); if(-not $p.HasExited) {{ exit 9 }} }} catch [ArgumentException] {{ }}; exit 0".encode("utf-16-le")
    ).decode("ascii")
    result = run_ps5([str(PS5), "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded])
    assert result.returncode == 0, "owned guard residue"


def kill_owned_guard(pid):
    import base64
    command_text = f"$p=[Diagnostics.Process]::GetProcessById({pid}); $p.Kill(); if(-not $p.WaitForExit(10000)) {{exit 8}}; exit 0"
    encoded = base64.b64encode(command_text.encode("utf-16-le")).decode("ascii")
    result = run_ps5([str(PS5), "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded], timeout=20)
    assert result.returncode == 0, result.stderr


def assert_lock_reacquirable(sandbox, lock=None):
    root = sandbox[0]
    lock = lock or root / ".git/sorigul-113-single-writer.lock"
    harness = sandbox[3] / "lock reacquisition.ps1"
    harness.write_text(
        "param([string]$Path)\n$ErrorActionPreference='Stop'\n"
        "$s=[IO.File]::Open($Path,'OpenOrCreate','ReadWrite','None'); $s.Dispose()\n",
        encoding="utf-8-sig",
    )
    result = run_ps5([str(PS5), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                     "-File", str(harness), str(lock)])
    assert result.returncode == 0, result.stdout + result.stderr


@WINDOWS
def test_actual_probe_lifecycle_hashing_and_inherited_environment(sandbox):
    result = invoke(sandbox, "Probe", "-StableSeconds", 3)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "CANONICAL SINGLE WRITER BOOTSTRAP PROBE: PASS" in result.stdout
    data = json.JSONDecoder().raw_decode(result.stdout)[0]
    assert data["probe_only"] is True
    assert data["heartbeats"] >= 3
    assert data["competing_acquisition"] == "DENIED"
    assert data["monitored_source"] == "PASS"
    assert data["controlled_stop"] == data["lock_release"] == "PASS"
    assert data["orphan"] == 0
    assert data["hashing"]["hashing"] == ".NET SHA256"
    assert data["hashing"]["powershell"].startswith("5.1.")
    evidence = Path(data["evidence"])
    owner = json.loads((evidence / "GUARD_OWNER.json").read_text(encoding="utf-8-sig"))
    assert sandbox[2]["PSModulePath"] in owner["environment"]["PSModulePath"]
    assert owner["environment"]["PATH"] == sandbox[2]["PATH"]
    inherited_root = next(value for key, value in sandbox[2].items() if key.upper() == "SYSTEMROOT")
    assert owner["environment"]["SystemRoot"] == inherited_root
    assert not (evidence / "SESSION_ACTIVE.json").exists()
    assert_pid_gone(data["guard_pid"])


@WINDOWS
@pytest.mark.parametrize("fault", ["wrong_head", "dirty_tree", "release_hash", "wrong_branch"])
def test_start_identity_negatives_never_activate(sandbox, fault):
    args = start_args(sandbox)
    if fault == "wrong_head":
        args[args.index("-ExpectedHead") + 1] = "0" * 40
    elif fault == "wrong_branch":
        args[args.index("-ExpectedBranch") + 1] = "wrong"
    elif fault == "dirty_tree":
        (sandbox[0] / "input.txt").write_text("dirty\n", encoding="utf-8")
    else:
        path = Path(args[args.index("-FreezeFile") + 1])
        data = json.loads(path.read_text())
        data["release_input_sha256"]["input.txt"] = "0" * 64
        path.write_text(json.dumps(data))
    result = invoke(sandbox, "Start", *args)
    assert_no_activation(sandbox, result)
    assert_lock_reacquirable(sandbox)


@WINDOWS
def test_already_held_lock_denies_start_without_touching_owner(sandbox):
    args = start_args(sandbox)
    lock = sandbox[0] / ".git/sorigul-113-single-writer.lock"
    ready = sandbox[3] / "holder.ready"
    holder_script = sandbox[3] / "synthetic lock holder.ps1"
    holder_script.write_text(
        "param([string]$Path,[string]$Ready)\n"
        "$s=[IO.File]::Open($Path,'OpenOrCreate','ReadWrite','None')\n"
        "try {[IO.File]::WriteAllText($Ready,'READY'); [Threading.Thread]::Sleep(60000)} finally {$s.Dispose()}\n",
        encoding="utf-8-sig",
    )
    holder = subprocess.Popen([str(PS5), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                               str(holder_script), str(lock), str(ready)])
    try:
        deadline = time.monotonic() + 20
        while not ready.exists():
            assert time.monotonic() < deadline
            time.sleep(0.1)
        result = invoke(sandbox, "Start", *args)
        assert_no_activation(sandbox, result)
        assert "lock already held" in result.stderr
        assert holder.poll() is None
    finally:
        holder.terminate()
        holder.wait(timeout=15)
    assert_lock_reacquirable(sandbox)


@WINDOWS
def test_actual_guard_hash_capability_failure_is_cleaned_up(sandbox):
    root, script, _, _ = sandbox
    source = script.read_text(encoding="utf-8")
    source = source.replace("function Assert-Capabilities {", "function Assert-Capabilities {\n    if ($Mode -eq 'Guard') { throw 'Injected SHA256 capability failure' }")
    script.write_text(source, encoding="utf-8-sig")
    git(root, "add", "scripts/" + SCRIPT.name)
    git(root, "commit", "-m", "Synthetic #164 hashing capability fault")
    git(root, "push")
    result = invoke(sandbox, "Start", *start_args(sandbox))
    assert_no_activation(sandbox, result)
    invalid = json.loads(marker(sandbox, "SESSION_INVALID.json")[0].read_text())
    assert invalid["state"] == "BOOTSTRAP_FAILED"
    assert_lock_reacquirable(sandbox)


@WINDOWS
def test_early_guard_death_never_activates_and_releases_lock(sandbox):
    root, _, environment, _ = sandbox
    args = start_args(sandbox)
    args[-1] = 10
    parent = subprocess.Popen(command(sandbox, "Start", *args),
                              cwd=root, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
    try:
        deadline = time.monotonic() + 30
        while not marker(sandbox, "GUARD_OWNER.json"):
            assert parent.poll() is None
            assert time.monotonic() < deadline
            time.sleep(0.1)
        owner = json.loads(marker(sandbox, "GUARD_OWNER.json")[0].read_text())
        kill_owned_guard(owner["pid"])
        stdout, stderr = parent.communicate(timeout=40)
        assert_no_activation(sandbox, subprocess.CompletedProcess([], parent.returncode, stdout, stderr))
        assert_pid_gone(owner["pid"])
        assert_lock_reacquirable(sandbox)
    finally:
        if parent.poll() is None:
            parent.terminate()
            parent.wait(timeout=15)


@WINDOWS
def test_baseline_failure_does_not_activate_and_cleans_guard(sandbox):
    app = Path(sandbox[2]["LOCALAPPDATA"]) / "Sorigul"
    app.mkdir()
    (app / "settings.json").write_text("{broken json", encoding="utf-8")
    result = invoke(sandbox, "Start", *start_args(sandbox))
    assert_no_activation(sandbox, result)
    owner = json.loads(marker(sandbox, "GUARD_OWNER.json")[0].read_text())
    assert_pid_gone(owner["pid"])
    assert_lock_reacquirable(sandbox)


@WINDOWS
def test_active_guard_loss_is_hard_stop_in_synthetic_repository(sandbox):
    result = invoke(sandbox, "Start", *start_args(sandbox))
    assert result.returncode == 0, result.stdout + result.stderr
    session = marker(sandbox, "SESSION_ACTIVE.json")[0].parent
    owner = json.loads((session / "GUARD_OWNER.json").read_text())
    kill_owned_guard(owner["pid"])
    status = invoke(sandbox, "Status", "-SessionPath", session)
    assert status.returncode != 0
    invalid = json.loads((session / "SESSION_INVALID.json").read_text())
    assert invalid["state"] == "HARD_STOP"
    assert invalid["artifact_session_started"] is True
    assert_pid_gone(owner["pid"])
    assert_lock_reacquirable(sandbox)


@WINDOWS
def test_canonical_freeze_matches_actual_tracked_sha256(sandbox):
    path = sandbox[3] / "canonical_freeze.json"
    result = invoke(sandbox, "Freeze", "-FreezeFile", path)
    assert result.returncode == 0, result.stdout + result.stderr
    actual = json.loads(path.read_text())
    expected = json.loads(freeze(sandbox).read_text())
    for key in ("head", "branch", "release_input_sha256"):
        assert actual[key] == expected[key]
    assert not marker(sandbox, "SESSION_ACTIVE.json")
@WINDOWS
def test_synthetic_activation_baseline_status_and_controlled_stop(sandbox):
    # Disposable fixture only: proves the positive marker ordering without
    # starting a real #113 session or touching real protected user data.
    # Capture pipes deliberately reproduce the original Start-return boundary.
    result = invoke(sandbox, "Start", *start_args(sandbox), capture=True)
    assert result.returncode == 0, result.stdout + result.stderr
    active = marker(sandbox, "SESSION_ACTIVE.json")[0]
    session = active.parent
    owner = json.loads((session / "GUARD_OWNER.json").read_text())
    try:
        baseline = json.loads((session / "PROTECTED_USER_DATA_BASELINE.json").read_text())
        activation = json.loads(active.read_text())
        assert baseline["at_utc"] < activation["at_utc"]
        assert len(baseline["roots"]) == 9
        status = invoke(sandbox, "Status", "-SessionPath", session)
        assert status.returncode == 0, status.stdout + status.stderr
        assert "#113 ARTIFACT SESSION = ACTIVE" in status.stdout
    finally:
        stopped = invoke(sandbox, "Stop", "-SessionPath", session)
        assert stopped.returncode == 0, stopped.stdout + stopped.stderr
        assert_pid_gone(owner["pid"])
        assert_lock_reacquirable(sandbox)


HEARTBEAT_WRITE = "            Write-AtomicJson (Join-Path $SessionPath 'LOCK_HEARTBEAT.json') @{"
HEARTBEAT_READ = "        $Heartbeat = Read-Json (Join-Path $Config.session 'LOCK_HEARTBEAT.json') -RetryMissing"


def inject_heartbeat_missing_window(sandbox, opt_in=True):
    # Disposable fixture only: widen the File.Replace not-found gap into a
    # deterministic 60ms window, and make every parent heartbeat read land in it.
    root, script, _, _ = sandbox
    source = script.read_text(encoding="utf-8")
    assert source.count(HEARTBEAT_WRITE) == source.count(HEARTBEAT_READ) == 1
    source = source.replace(HEARTBEAT_WRITE, (
        "            $RaceHeartbeat = Join-Path $SessionPath 'LOCK_HEARTBEAT.json'\n"
        "            if ([IO.File]::Exists($RaceHeartbeat)) { [IO.File]::Delete($RaceHeartbeat); [Threading.Thread]::Sleep(60) }\n"
    ) + HEARTBEAT_WRITE)
    read = HEARTBEAT_READ if opt_in else HEARTBEAT_READ.replace(" -RetryMissing", "")
    source = source.replace(HEARTBEAT_READ, (
        "        $RaceHeartbeat = Join-Path $Config.session 'LOCK_HEARTBEAT.json'\n"
        "        $RaceTimer = [Diagnostics.Stopwatch]::StartNew()\n"
        "        while ([IO.File]::Exists($RaceHeartbeat) -and $RaceTimer.ElapsedMilliseconds -lt 3000) { [Threading.Thread]::Sleep(2) }\n"
        "        if (-not [IO.File]::Exists($RaceHeartbeat)) { [IO.File]::AppendAllText((Join-Path $Config.session 'RACE_WINDOW_HITS.log'), \"missing`n\") }\n"
    ) + read)
    script.write_text(source, encoding="utf-8-sig")
    git(root, "add", "scripts/" + SCRIPT.name)
    git(root, "commit", "-m", "Synthetic #164 heartbeat missing window")
    git(root, "push")


def race_hits(session):
    return (session / "RACE_WINDOW_HITS.log").read_text(encoding="utf-8").count("missing")


@WINDOWS
def test_parent_semantics_fail_on_transient_heartbeat_missing_window(sandbox):
    # Reproduces the Sorigul_20261007_035db13_94f463015bad failure mode: without
    # the heartbeat opt-in a transient Win32 2 is fatal during stabilization.
    inject_heartbeat_missing_window(sandbox, opt_in=False)
    result = invoke(sandbox, "Probe", "-StableSeconds", 3)
    assert result.returncode != 0, result.stdout + result.stderr
    assert "BOOTSTRAP FAILED / ARTIFACT SESSION NOT STARTED" in result.stdout
    session = next(sandbox[3].glob("Sorigul_113_Probe_*"))
    invalid = json.loads((session / "SESSION_INVALID.json").read_text(encoding="utf-8-sig"))
    assert invalid["state"] == "BOOTSTRAP_FAILED"
    assert "LOCK_HEARTBEAT.json" in invalid["reason"]
    assert race_hits(session) >= 1
    owner = json.loads((session / "GUARD_OWNER.json").read_text(encoding="utf-8-sig"))
    assert_pid_gone(owner["pid"])
    assert_lock_reacquirable(sandbox, session / "probe.lock")


@WINDOWS
def test_probe_recovers_from_transient_heartbeat_missing_window(sandbox):
    inject_heartbeat_missing_window(sandbox)
    result = invoke(sandbox, "Probe", "-StableSeconds", 3)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "CANONICAL SINGLE WRITER BOOTSTRAP PROBE: PASS" in result.stdout
    data = json.JSONDecoder().raw_decode(result.stdout)[0]
    assert data["heartbeats"] >= 3
    assert data["competing_acquisition"] == "DENIED"
    assert data["monitored_source"] == "PASS"
    assert data["controlled_stop"] == data["lock_release"] == "PASS"
    assert data["orphan"] == 0
    session = Path(data["evidence"])
    assert race_hits(session) >= 3
    assert not (session / "SESSION_INVALID.json").exists()
    assert_pid_gone(data["guard_pid"])
    assert_lock_reacquirable(sandbox, session / "probe.lock")


@WINDOWS
def test_start_status_stop_recover_from_transient_heartbeat_missing_window(sandbox):
    inject_heartbeat_missing_window(sandbox)
    result = invoke(sandbox, "Start", *start_args(sandbox))
    assert result.returncode == 0, result.stdout + result.stderr
    session = marker(sandbox, "SESSION_ACTIVE.json")[0].parent
    owner = json.loads((session / "GUARD_OWNER.json").read_text(encoding="utf-8-sig"))
    try:
        status = invoke(sandbox, "Status", "-SessionPath", session)
        assert status.returncode == 0, status.stdout + status.stderr
        assert "#113 ARTIFACT SESSION = ACTIVE" in status.stdout
    finally:
        stopped = invoke(sandbox, "Stop", "-SessionPath", session)
        assert stopped.returncode == 0, stopped.stdout + stopped.stderr
    assert "CONTROLLED STOP = PASS; LOCK RELEASE = PASS; ORPHAN = 0" in stopped.stdout
    assert race_hits(session) >= 3
    assert not (session / "SESSION_INVALID.json").exists()
    assert_pid_gone(owner["pid"])
    assert_lock_reacquirable(sandbox)


def protected_snapshots(tmp_path, fault):
    """Synthetic captured metadata only; never read the user's profile."""
    import copy
    root = str(tmp_path / "LOCALAPPDATA" / "com.sorigul.desktop")
    directory = dict(directory=True, reparse=False, attributes="Directory", write_ticks=100)
    file = dict(directory=False, reparse=False, attributes="Archive", write_ticks=100, size=8)
    before = [dict(root=root, exists=True, policy="synthetic", entries=[
        dict(path="EBWebView", **directory),
        dict(path="EBWebView\\Default", **directory),
        dict(path="EBWebView\\Default\\cache.bin", **file),
        dict(path="EBWebViewSibling", **directory),
    ]), dict(root=str(tmp_path / "LOCALAPPDATA" / "Sorigul"), exists=True,
             policy="synthetic", entries=[dict(path="auth", **directory),
                 dict(path="settings.json", sha256="a" * 64, **file),
                 dict(path="jobs.json", sha256="b" * 64, **file)])]
    after = copy.deepcopy(before)
    entries = after[0]["entries"]
    if fault in ("dir", "dir_child", "mixed", "attribute", "type", "reparse", "path", "unknown_field"):
        entries[0]["write_ticks"] += 432254
    if fault == "dir_child":
        entries[1]["write_ticks"] += 432254
    elif fault in ("file_mtime", "mixed"):
        entries[2]["write_ticks"] += 1
    elif fault == "file_size":
        entries[2]["size"] += 1
    elif fault == "add":
        entries.append(dict(path="EBWebView\\new.bin", **file))
    elif fault == "delete":
        entries.pop(2)
    elif fault == "other_dir":
        after[1]["entries"][0]["write_ticks"] += 1
    elif fault == "prefix_sibling":
        entries[3]["write_ticks"] += 1
    elif fault in ("settings_hash", "jobs_hash"):
        after[1]["entries"][1 if fault == "settings_hash" else 2]["sha256"] = "c" * 64
    elif fault == "attribute":
        entries[0]["attributes"] = "Directory, Hidden"
    elif fault == "type":
        entries[0]["directory"] = False
    elif fault == "reparse":
        entries[0]["reparse"] = True
    elif fault == "path":
        entries[0]["path"] = "EBWebView\\renamed"
    elif fault == "unknown_field":
        entries[0]["new_property"] = "unapproved"
    elif fault == "root_path":
        after[0]["root"] += "Sibling"
    elif fault == "root_delete":
        after.pop()
    elif fault == "root_exists":
        after[0]["exists"] = False
    elif fault in ("traversal", "reparse_mtime", "wrong_root"):
        if fault == "traversal":
            before[0]["entries"][0]["path"] = entries[0]["path"] = "EBWebView\\..\\auth"
        elif fault == "reparse_mtime":
            before[0]["entries"][0]["reparse"] = entries[0]["reparse"] = True
        else:
            before[0]["root"] = after[0]["root"] = str(tmp_path / "APPDATA" / "com.sorigul.desktop")
        entries[0]["write_ticks"] += 1
    return before, after


def protected_harness(tmp_path, before, after, stages):
    environment = os.environ.copy()
    environment["LOCALAPPDATA"] = str(tmp_path / "LOCALAPPDATA")
    environment["TEMP"] = environment["TMP"] = str(tmp_path)
    session = tmp_path / "synthetic evidence"
    session.mkdir(exist_ok=True)
    (session / "PROTECTED_USER_DATA_BASELINE.json").write_text(json.dumps({"roots": before}), encoding="utf-8")
    (session / "after.json").write_text(json.dumps({"roots": after}), encoding="utf-8")
    source = SCRIPT.read_text(encoding="utf-8")
    functions = source[source.index("function Write-AtomicJson("):source.index("\nif ($Mode -eq 'Freeze')")]
    harness = tmp_path / "protected comparison 한글.ps1"
    harness.write_text(
        "param([string]$Session)\nSet-StrictMode -Version Latest\n$ErrorActionPreference='Stop'\n"
        "$Utf8=New-Object Text.UTF8Encoding($false)\n" + functions +
        "\nfunction Get-ProtectedBaseline { return (Read-Json (Join-Path $Session 'after.json')).roots }\n"
        "$Config=[pscustomobject]@{session=$Session}\n" +
        "\n".join(f"$null=Assert-ProtectedBaseline $Config '{stage}'" for stage in stages) + "\n",
        encoding="utf-8-sig")
    result = run_ps5([str(PS5), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                      "-File", str(harness), str(session)], environment=environment)
    evidence = json.loads((session / "PROTECTED_DIFF.json").read_text(encoding="utf-8-sig"))
    return result, evidence


@WINDOWS
@pytest.mark.parametrize("stage", ["ACTIVATION", "STATUS"])
@pytest.mark.parametrize("fault", [
    "none", "dir", "dir_child", "file_mtime", "file_size", "add", "delete", "other_dir",
    "prefix_sibling", "settings_hash", "jobs_hash", "attribute", "type", "reparse", "path",
    "mixed", "root_path", "root_delete", "root_exists", "unknown_field", "traversal",
    "reparse_mtime", "wrong_root",
])
def test_189_protected_classification_and_exact_evidence(tmp_path, stage, fault):
    before, after = protected_snapshots(tmp_path, fault)
    result, evidence = protected_harness(tmp_path, before, after, [stage])
    expected = "NO_CHANGE" if fault == "none" else "DIR_MTIME_ONLY" if fault in ("dir", "dir_child") else "HARD_STOP"
    assert evidence["classification"] == expected
    assert (result.returncode == 0) == (expected != "HARD_STOP"), result.stdout + result.stderr
    comparison = evidence["comparisons"][0]
    assert comparison["stage"] == stage
    assert comparison["classification"] == expected
    assert "NOT VERIFIED" in evidence["acceptance"]
    assert "ZERO_CHANGE_PASS" not in json.dumps(evidence)
    if expected == "DIR_MTIME_ONLY":
        assert evidence["allowed_metadata_difference_observed"] is True
        assert "metadata difference observed" in evidence["acceptance"]
        assert {diff["field"] for diff in comparison["differences"]} == {"write_ticks"}
        first = comparison["differences"][0]
        assert first["root"] == before[0]["root"]
        assert first["entry"] == "EBWebView"
        assert first["before"] == 100 and first["after"] == 432354
        assert all(diff["allowed"] for diff in comparison["differences"])
    elif expected == "HARD_STOP":
        assert any(not diff["allowed"] for diff in comparison["differences"])


@WINDOWS
def test_189_exception_history_survives_no_change_and_later_stop(tmp_path):
    before, after = protected_snapshots(tmp_path, "dir")
    result, evidence = protected_harness(tmp_path, before, after, ["ACTIVATION"])
    assert result.returncode == 0, result.stdout + result.stderr
    result, evidence = protected_harness(tmp_path, before, before, ["STATUS"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert evidence["classification"] == "NO_CHANGE"
    assert evidence["allowed_metadata_difference_observed"] is True
    assert "metadata difference observed" in evidence["acceptance"]
    _, changed = protected_snapshots(tmp_path, "jobs_hash")
    result, evidence = protected_harness(tmp_path, before, changed, ["STATUS"])
    assert result.returncode != 0
    assert [item["classification"] for item in evidence["comparisons"]] == ["DIR_MTIME_ONLY", "NO_CHANGE", "HARD_STOP"]
    assert evidence["allowed_metadata_difference_observed"] is True


@WINDOWS
@pytest.mark.parametrize("fault", ["dir", "file"])
def test_189_native_activation_and_status_use_same_classifier(sandbox, fault):
    root, script, environment, _ = sandbox
    webview = Path(environment["LOCALAPPDATA"]) / "com.sorigul.desktop" / "EBWebView"
    webview.mkdir(parents=True)
    cache = webview / "cache.bin"
    cache.write_bytes(b"synthetic")
    target = webview if fault == "dir" else cache
    setter = "Directory" if fault == "dir" else "File"
    # Inject only in this disposable source, after baseline capture and before activation.
    source = script.read_text(encoding="utf-8")
    activation = "$Protected = Assert-ProtectedBaseline $Config 'ACTIVATION'"
    source = source.replace(activation,
        f"[IO.{setter}]::SetLastWriteTimeUtc('{str(target).replace(chr(39), chr(39) * 2)}', [DateTime]::UtcNow.AddMinutes(1))\n                " + activation)
    script.write_text(source, encoding="utf-8-sig")
    git(root, "add", "scripts/" + SCRIPT.name)
    git(root, "commit", "-m", "Synthetic #189 activation difference")
    git(root, "push")
    result = invoke(sandbox, "Start", *start_args(sandbox))
    session = marker(sandbox, "PROTECTED_DIFF.json")[0].parent
    evidence = json.loads((session / "PROTECTED_DIFF.json").read_text())
    if fault == "file":
        assert_no_activation(sandbox, result)
        assert evidence["classification"] == "HARD_STOP"
        assert_lock_reacquirable(sandbox)
        return
    assert result.returncode == 0, result.stdout + result.stderr
    assert evidence["classification"] == "DIR_MTIME_ONLY"
    try:
        status = invoke(sandbox, "Status", "-SessionPath", session)
        assert status.returncode == 0, status.stdout + status.stderr
        assert "PROTECTED DATA = DIR_MTIME_ONLY" in status.stdout
        assert "metadata difference observed" in status.stdout
        evidence = json.loads((session / "PROTECTED_DIFF.json").read_text())
        assert [item["stage"] for item in evidence["comparisons"]] == ["ACTIVATION", "STATUS"]
        # A real synthetic file change at a later stage is still HARD STOP.
        cache.write_bytes(b"changed synthetic file")
        status = invoke(sandbox, "Status", "-SessionPath", session)
        assert status.returncode != 0
        invalid = json.loads((session / "SESSION_INVALID.json").read_text())
        assert invalid["state"] == "HARD_STOP"
        evidence = json.loads((session / "PROTECTED_DIFF.json").read_text())
        assert evidence["classification"] == "HARD_STOP"
        assert evidence["allowed_metadata_difference_observed"] is True
    finally:
        # Invalidated synthetic sessions need the existing owned-guard cleanup helper.
        config = json.loads((session / "SESSION_BOOTSTRAPPING.json").read_text(encoding="utf-8-sig"))
        (session / "STOP_REQUEST.json").write_text(json.dumps({"token": config["token"]}), encoding="utf-8")
        owner = json.loads((session / "GUARD_OWNER.json").read_text(encoding="utf-8-sig"))
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                assert_pid_gone(owner["pid"])
                break
            except AssertionError:
                time.sleep(0.1)
        assert_pid_gone(owner["pid"])
        assert_lock_reacquirable(sandbox)
