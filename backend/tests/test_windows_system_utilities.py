"""#122: production Windows utilities resolve from the OS System32, never PATH."""

import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.engines import local_whisper
from src.services import drive, windows_system
from src.services.drive import DriveError, enforce_private_file_permissions, write_private_file
from src.services.windows_system import (
    SYSTEM32_UTILITIES,
    WindowsSystemUtilityError,
    resolve_system32_executable,
)

windows_only = pytest.mark.skipif(os.name != "nt", reason="needs the real Windows system directory")


@pytest.fixture
def fake_system32(tmp_path, monkeypatch):
    directory = tmp_path / "System32"
    directory.mkdir()
    for name in SYSTEM32_UTILITIES:
        (directory / name).write_bytes(b"")
    monkeypatch.setattr(windows_system, "_query_system_directory", lambda: str(directory))
    return directory


@pytest.fixture
def shadowed_path(tmp_path, monkeypatch):
    """Git Bash-style search path: a shadow directory wins every bare lookup."""
    shadow = tmp_path / "shadow-bin"
    shadow.mkdir()
    for name in SYSTEM32_UTILITIES:
        (shadow / name).write_bytes(b"")
    monkeypatch.setenv("PATH", f"{shadow}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("SystemRoot", str(shadow))
    monkeypatch.setenv("windir", str(shadow))
    return shadow


@windows_only
@pytest.mark.parametrize("name", sorted(SYSTEM32_UTILITIES))
def test_real_resolver_ignores_shadowed_path_and_environment(name, shadowed_path):
    assert Path(shutil.which(name)).parent == shadowed_path  # the poisoning is live

    resolved = resolve_system32_executable(name)

    assert resolved.is_absolute()
    assert resolved.is_file()
    assert resolved.name == name
    assert resolved.parent == Path(windows_system._query_system_directory())
    assert resolved.parent.name.lower() == "system32"
    assert shadowed_path not in resolved.parents


@windows_only
def test_drive_sid_lookup_runs_system32_whoami_under_shadowed_path(shadowed_path):
    calls = []

    def run(args, **kwargs):
        calls.append((list(args), dict(kwargs)))
        return SimpleNamespace(stdout='"desktop-user","S-1-5-21-123"\n')

    assert drive._resolve_current_windows_sid(run) == "S-1-5-21-123"

    argv, kwargs = calls[0]
    assert argv[0] == str(Path(windows_system._query_system_directory()) / "whoami.exe")
    assert argv[1:] == ["/user", "/fo", "csv", "/nh"]
    assert kwargs["shell"] is False


@pytest.mark.parametrize(
    "name",
    [
        "explorer.exe",
        "shutdown.exe",
        "cmd.exe",
        "powershell.exe",
        "WHOAMI.EXE",
        "whoami",
        r"..\whoami.exe",
        r"C:\shadow\whoami.exe",
        "",
    ],
)
def test_resolver_only_accepts_allowlisted_fixed_names(name, fake_system32):
    with pytest.raises(ValueError):
        resolve_system32_executable(name)


def test_resolver_fails_closed_when_system_directory_api_fails(monkeypatch):
    def unavailable():
        raise WindowsSystemUtilityError("GetSystemDirectoryW failed")

    monkeypatch.setattr(windows_system, "_query_system_directory", unavailable)
    with pytest.raises(WindowsSystemUtilityError):
        resolve_system32_executable("whoami.exe")


def test_resolver_rejects_relative_system_directory(monkeypatch):
    monkeypatch.setattr(windows_system, "_query_system_directory", lambda: "System32")
    with pytest.raises(WindowsSystemUtilityError):
        resolve_system32_executable("whoami.exe")


def test_resolver_fails_closed_when_trusted_executable_missing(fake_system32):
    (fake_system32 / "icacls.exe").unlink()
    with pytest.raises(WindowsSystemUtilityError):
        resolve_system32_executable("icacls.exe")


def test_existing_token_acl_blocks_when_trusted_utility_missing(tmp_path, fake_system32):
    (fake_system32 / "whoami.exe").unlink()
    token_path = tmp_path / "token.json"
    token_path.write_text("original", encoding="utf-8")
    calls = []

    with pytest.raises(DriveError) as caught:
        enforce_private_file_permissions(
            token_path, platform_name="nt", run=lambda args, **_: calls.append(args)
        )

    assert caught.value.code == "DRIVE_TOKEN_PERMISSIONS_FAILED"
    assert calls == []
    assert token_path.read_text(encoding="utf-8") == "original"


def test_new_token_never_published_when_trusted_icacls_missing(tmp_path, fake_system32):
    (fake_system32 / "icacls.exe").unlink()
    target_dir = tmp_path / "tokens"
    target = target_dir / "token.json"
    calls = []

    def run(args, **_kwargs):
        calls.append(list(args))
        return SimpleNamespace(stdout='"desktop-user","S-1-5-21-123"\n')

    with pytest.raises(WindowsSystemUtilityError):
        write_private_file(target, "test-token", platform_name="nt", run=run)

    assert [Path(argv[0]).name for argv in calls] == ["whoami.exe"]
    assert not target.exists()
    assert list(target_dir.iterdir()) == []


def test_enforce_acl_runs_both_utilities_by_trusted_absolute_path(tmp_path, fake_system32):
    token_path = tmp_path / "token.json"
    token_path.write_text("original", encoding="utf-8")
    calls = []

    def run(args, **kwargs):
        calls.append((list(args), dict(kwargs)))
        return SimpleNamespace(stdout='"desktop-user","S-1-5-21-123"\n')

    enforce_private_file_permissions(token_path, platform_name="nt", run=run)

    assert [argv[0] for argv, _ in calls] == [
        str(fake_system32 / "whoami.exe"),
        str(fake_system32 / "icacls.exe"),
    ]
    assert all(kwargs["shell"] is False for _, kwargs in calls)


class _ReapProcess:
    pid = 4242

    def __init__(self, exits_after_taskkill=True):
        self.exits_after_taskkill = exits_after_taskkill
        self.waits = 0
        self.terminated = False

    def wait(self, timeout=None):
        self.waits += 1
        if self.waits == 1 and not self.exits_after_taskkill:
            raise subprocess.TimeoutExpired("worker", timeout)
        return 0

    def terminate(self):
        self.terminated = True

    def kill(self):
        raise AssertionError("terminate already reaped the worker")


@windows_only
def test_local_reap_runs_trusted_taskkill_for_the_worker_tree(fake_system32, monkeypatch):
    calls = []

    def run(args, **kwargs):
        calls.append((list(args), dict(kwargs)))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(local_whisper.subprocess, "run", run)
    process = _ReapProcess()

    local_whisper._reap(process)

    argv, kwargs = calls[0]
    assert argv == [str(fake_system32 / "taskkill.exe"), "/PID", "4242", "/T", "/F"]
    assert kwargs.get("shell", False) is False
    assert process.terminated is False


@windows_only
def test_local_reap_without_trusted_taskkill_keeps_terminate_fallback(fake_system32, monkeypatch):
    (fake_system32 / "taskkill.exe").unlink()
    calls = []
    monkeypatch.setattr(local_whisper.subprocess, "run", lambda *args, **_: calls.append(args))
    process = _ReapProcess(exits_after_taskkill=False)

    local_whisper._reap(process)

    assert calls == []
    assert process.terminated is True
