"""Windows-only fixture probes. No accounts are created or credentials loaded."""
import ctypes
from ctypes import wintypes as w
import os
from pathlib import Path
import uuid

from observer_v2 import ObservationError, require_fixture


def api():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    security = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel.GetCurrentProcess.restype = w.HANDLE
    kernel.CloseHandle.argtypes = [w.HANDLE]
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, ctypes.c_void_p, w.DWORD, w.DWORD, w.HANDLE]
    kernel.CreateFileW.restype = w.HANDLE
    security.OpenProcessToken.argtypes = [w.HANDLE, w.DWORD, ctypes.POINTER(w.HANDLE)]
    security.GetTokenInformation.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.POINTER(w.DWORD)]
    security.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(w.LPWSTR)]
    security.ConvertStringSidToSidW.argtypes = [w.LPCWSTR, ctypes.POINTER(ctypes.c_void_p)]
    security.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [w.LPCWSTR, w.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(w.DWORD)]
    security.SetFileSecurityW.argtypes = [w.LPCWSTR, w.DWORD, ctypes.c_void_p]
    security.CreateRestrictedToken.argtypes = [w.HANDLE, w.DWORD, w.DWORD, ctypes.c_void_p, w.DWORD, ctypes.c_void_p, w.DWORD, ctypes.c_void_p, ctypes.POINTER(w.HANDLE)]
    security.ImpersonateLoggedOnUser.argtypes = [w.HANDLE]
    return kernel, security


def checked(value):
    if not value:
        raise ctypes.WinError(ctypes.get_last_error())
    return value


def restricted_write_probe(fixture, run_id):
    root = require_fixture(fixture, run_id)
    if os.name != "nt":
        raise ObservationError("WINDOWS_TOKEN_TEST_REQUIRED")
    directory = root / "acl-probe"
    directory.mkdir()
    existing = directory / "existing.txt"
    existing.write_bytes(b"synthetic-only")
    kernel, security = api()
    original, restricted = w.HANDLE(), w.HANDLE()
    restricted_sid, descriptor = ctypes.c_void_p(), ctypes.c_void_p()
    sid_text = w.LPWSTR()
    impersonated = False
    try:
        checked(security.OpenProcessToken(kernel.GetCurrentProcess(), 0x000E, ctypes.byref(original)))
        needed = w.DWORD()
        security.GetTokenInformation(original, 1, None, 0, ctypes.byref(needed))
        buffer = ctypes.create_string_buffer(needed.value)
        checked(security.GetTokenInformation(original, 1, buffer, len(buffer), ctypes.byref(needed)))
        user_sid = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p))[0]
        checked(security.ConvertSidToStringSidW(user_sid, ctypes.byref(sid_text)))
        # This SID exists only as a restricting SID in a derived token, not an account.
        synthetic_sid = "S-1-5-21-" + "-".join(str(int.from_bytes(uuid.uuid4().bytes[:4], "little")) for _ in range(3)) + "-40001"
        checked(security.ConvertStringSidToSidW(synthetic_sid, ctypes.byref(restricted_sid)))
        sddl = f"D:P(A;OICI;FA;;;{sid_text.value})(A;OICI;GRGX;;;{synthetic_sid})"
        checked(security.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, ctypes.byref(descriptor), None))
        for path in (directory, existing):
            checked(security.SetFileSecurityW(str(path), 0x80000004, descriptor))

        class SidAndAttributes(ctypes.Structure):
            _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", w.DWORD)]

        restriction = SidAndAttributes(restricted_sid, 0)
        checked(security.CreateRestrictedToken(original, 1, 0, None, 0, None, 1, ctypes.byref(restriction), ctypes.byref(restricted)))
        checked(security.ImpersonateLoggedOnUser(restricted))
        impersonated = True
        results = {}
        for label, path, access, disposition, flags in (
            ("existing_write", existing, 0x40000000, 3, 0),
            ("directory_add_file", directory, 2, 3, 0x02000000),
            ("new_file_create", directory / "denied.txt", 0x40000000, 1, 0),
        ):
            handle = kernel.CreateFileW(str(path), access, 7, None, disposition, flags, None)
            if handle == ctypes.c_void_p(-1).value:
                results[label] = ctypes.get_last_error()
            else:
                kernel.CloseHandle(handle)
                results[label] = 0
        return results
    finally:
        if impersonated:
            checked(security.RevertToSelf())
        for handle in (restricted, original):
            if handle:
                kernel.CloseHandle(handle)
        for pointer in (restricted_sid, descriptor, sid_text):
            if pointer:
                kernel.LocalFree(pointer)


class ExclusiveReadLock:
    def __init__(self, path):
        self.path = Path(path)

    def __enter__(self):
        self.kernel, _ = api()
        self.handle = self.kernel.CreateFileW(str(self.path), 0x80000000, 0, None, 3, 0, None)
        if self.handle == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        return self

    def __exit__(self, *args):
        self.kernel.CloseHandle(self.handle)
