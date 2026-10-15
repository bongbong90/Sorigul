"""Issue #122 source contracts: production code never launches a Windows
system utility by bare name (search-path lookup); it uses the trusted
absolute-path resolvers instead.

Issue #136 extends the contract to the Windows artifact build scripts'
self-test timeout cleanup."""

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_SRC = REPO_ROOT / "backend" / "src"
TAURI_SRC = REPO_ROOT / "frontend" / "src-tauri" / "src"
BUILD_SCRIPTS = (
    REPO_ROOT / "scripts" / "build_backend_sidecar.ps1",
    REPO_ROOT / "scripts" / "build_local_whisper_runtime.ps1",
)

# `Command::new("<literal>")` -- any literal program is a PATH lookup.
RUST_LITERAL_COMMAND = re.compile(r'Command::new\(\s*"([^"]+)"')
# An argv list whose first element is a bare `*.exe` literal.
PYTHON_BARE_EXE_ARGV = re.compile(r'\[\s*"([^"/\\]+\.exe)"\s*,')


def rust_production_source(path):
    """The file without its `#[cfg(test)] mod tests` block."""
    source = path.read_text(encoding="utf-8")
    marker = source.find("#[cfg(test)]\nmod tests")
    return source if marker == -1 else source[:marker]


def test_rust_production_launches_no_literal_windows_program():
    hits = {}
    for path in sorted(TAURI_SRC.glob("*.rs")):
        for program in RUST_LITERAL_COMMAND.findall(rust_production_source(path)):
            hits.setdefault(path.name, []).append(program)
    # Only the non-Windows opener remains (cfg(not(windows)) in lib.rs).
    assert hits == {"lib.rs": ["xdg-open"]}


def test_rust_utilities_resolve_through_the_closed_trusted_enum():
    resolver = (TAURI_SRC / "windows_system.rs").read_text(encoding="utf-8")
    assert "GetSystemDirectoryW" in resolver
    assert "GetSystemWindowsDirectoryW" in resolver
    for forbidden in ("std::env::var", "SystemRoot", '"PATH"', "which"):
        assert forbidden not in rust_production_source(TAURI_SRC / "windows_system.rs"), forbidden
    assert "pub enum SystemUtility" in resolver
    assert "fn path(self)" in resolver

    sidecar = rust_production_source(TAURI_SRC / "sidecar.rs")
    assert "SystemUtility::Taskkill.path()" in sidecar
    shutdown = rust_production_source(TAURI_SRC / "shutdown.rs")
    assert "SystemUtility::Shutdown" in shutdown
    assert '.args(["/s", "/t", "0"])' in shutdown
    lib = rust_production_source(TAURI_SRC / "lib.rs")
    assert "windows_system::SystemUtility::Explorer" in lib


def test_python_production_has_no_bare_exe_argv():
    hits = {
        str(path.relative_to(BACKEND_SRC)): PYTHON_BARE_EXE_ARGV.findall(
            path.read_text(encoding="utf-8")
        )
        for path in sorted(BACKEND_SRC.rglob("*.py"))
    }
    assert {name: found for name, found in hits.items() if found} == {}


def test_python_utilities_use_the_allowlisted_system32_resolver():
    resolver = (BACKEND_SRC / "services" / "windows_system.py").read_text(encoding="utf-8")
    assert "GetSystemDirectoryW" in resolver
    for forbidden in ("shutil", "which", "os.environ", "getenv", "SystemRoot"):
        assert forbidden not in resolver, forbidden

    drive = (BACKEND_SRC / "services" / "drive.py").read_text(encoding="utf-8")
    assert drive.count('resolve_system32_executable("whoami.exe")') == 1
    assert drive.count('resolve_system32_executable("icacls.exe")') == 2
    assert "shell=True" not in drive
    local = (BACKEND_SRC / "engines" / "local_whisper.py").read_text(encoding="utf-8")
    assert local.count('resolve_system32_executable("taskkill.exe")') == 1


def _resolver_body(script):
    start = script.index("function Resolve-TrustedTaskkill {")
    end = script.index("\n}\n", start)
    return script[start:end]


def test_build_scripts_never_launch_taskkill_by_bare_name():
    for path in BUILD_SCRIPTS:
        script = path.read_text(encoding="utf-8")
        assert not re.search(r"&\s*taskkill(\.exe)?\b", script, re.IGNORECASE), path.name
        assert script.count("& $TaskkillPath /PID $SelfTestProcess.Id /T /F") == 1, path.name
        assert script.count("taskkill.exe") == 1, path.name  # only the Join-Path leaf


def test_build_scripts_resolve_taskkill_from_the_os_system_directory():
    for path in BUILD_SCRIPTS:
        body = _resolver_body(path.read_text(encoding="utf-8"))
        assert "[System.Environment]::SystemDirectory" in body, path.name
        assert "IsNullOrWhiteSpace($SystemDirectory)" in body, path.name
        assert "[System.IO.Path]::IsPathRooted($SystemDirectory)" in body, path.name
        assert "Test-Path -LiteralPath $SystemDirectory -PathType Container" in body, path.name
        assert 'Join-Path $SystemDirectory "taskkill.exe"' in body, path.name
        assert "[System.IO.Path]::IsPathRooted($TaskkillPath)" in body, path.name
        assert "Test-Path -LiteralPath $TaskkillPath -PathType Leaf" in body, path.name
        assert 'throw "TRUSTED_TASKKILL_UNAVAILABLE"' in body, path.name


def test_build_scripts_resolve_cleanup_before_starting_the_self_test():
    for path in BUILD_SCRIPTS:
        script = path.read_text(encoding="utf-8")
        resolve = script.index("$TaskkillPath = Resolve-TrustedTaskkill")
        start = script.index("$SelfTestProcess = Start-Process")
        kill = script.index("& $TaskkillPath")
        assert resolve < start < kill, path.name


def test_build_scripts_have_no_path_or_environment_fallback():
    forbidden = re.compile(
        r"Get-Command|where\.exe|\$env:PATH|\$env:SystemRoot|\$env:windir|"
        r"GetEnvironmentVariable",
        re.IGNORECASE,
    )
    for path in BUILD_SCRIPTS:
        assert forbidden.findall(path.read_text(encoding="utf-8")) == [], path.name


def test_build_scripts_preserve_timeout_cleanup_verification():
    backend = BUILD_SCRIPTS[0].read_text(encoding="utf-8")
    assert "$SelfTestTimeoutSeconds = 300" in backend
    assert "$Stopped = $SelfTestProcess.WaitForExit(10000)" in backend
    assert "if ($TaskKillExit -ne 0 -or -not $Stopped)" in backend
    local = BUILD_SCRIPTS[1].read_text(encoding="utf-8")
    assert "$SelfTestTimeoutSeconds = 300" in local
    assert "if ($LASTEXITCODE -ne 0 -or -not $SelfTestProcess.WaitForExit(10000))" in local
