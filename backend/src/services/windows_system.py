"""Trusted absolute paths for the fixed Windows system utilities Sorigul runs.

Production code must never launch a Windows utility by bare name: the
search path can resolve ``whoami.exe`` to Git for Windows'
``/usr/bin/whoami.exe`` (or any other shadow) instead of the system one.
The System32 directory is taken from the OS (``GetSystemDirectoryW``), not
from ``PATH`` or environment variables, and any failure is raised -- there
is deliberately no bare-name fallback.
"""

import ctypes
from pathlib import Path


# Only these fixed, code-chosen names can be resolved; callers never pass
# a name that originates from user, network, or frontend input.
SYSTEM32_UTILITIES = frozenset({"whoami.exe", "icacls.exe", "taskkill.exe"})

_MAX_PATH_BUFFER = 32768


class WindowsSystemUtilityError(OSError):
    """A trusted Windows system utility path could not be established."""


def _query_system_directory() -> str:
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    except (AttributeError, OSError) as exc:
        raise WindowsSystemUtilityError("Windows system directory API unavailable") from exc
    get_system_directory = kernel32.GetSystemDirectoryW
    get_system_directory.argtypes = (ctypes.c_wchar_p, ctypes.c_uint)
    get_system_directory.restype = ctypes.c_uint
    buffer = ctypes.create_unicode_buffer(_MAX_PATH_BUFFER)
    length = get_system_directory(buffer, len(buffer))
    if length == 0 or length >= len(buffer):
        raise WindowsSystemUtilityError(
            f"GetSystemDirectoryW failed (error {ctypes.get_last_error()})"
        )
    return buffer.value


def resolve_system32_executable(name: str) -> Path:
    """Returns the absolute System32 path of an allowlisted utility, or raises."""
    if name not in SYSTEM32_UTILITIES:
        raise ValueError(f"not an allowlisted Windows system utility: {name!r}")
    directory = Path(_query_system_directory())
    if not directory.is_absolute():
        raise WindowsSystemUtilityError(
            f"Windows system directory is not absolute: {directory}"
        )
    executable = directory / name
    if not executable.is_file():
        raise WindowsSystemUtilityError(f"trusted Windows utility missing: {executable}")
    return executable
