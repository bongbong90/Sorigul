"""Issue #122 source contracts: production code never launches a Windows
system utility by bare name (search-path lookup); it uses the trusted
absolute-path resolvers instead."""

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_SRC = REPO_ROOT / "backend" / "src"
TAURI_SRC = REPO_ROOT / "frontend" / "src-tauri" / "src"

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
