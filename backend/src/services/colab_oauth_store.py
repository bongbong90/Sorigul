"""Colab-only, current-Windows-user DPAPI secret storage. No plaintext fallback."""

import base64
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path

from src.services.colab_runtime_ownership import _no_links
from src.services.drive import write_private_file


class WindowsUserProtector:
    ENTROPY = b"Sorigul.OfficialColab.OAuth.v1"

    def _crypt(self, data, decrypt=False):
        if os.name != "nt":
            raise ValueError("SECURE_STORE_UNAVAILABLE")
        class Blob(ctypes.Structure):
            _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]
        def blob(raw):
            buffer = ctypes.create_string_buffer(raw)
            return Blob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))), buffer
        source, source_buffer = blob(data)
        entropy, entropy_buffer = blob(self.ENTROPY)
        output = Blob()
        crypt = ctypes.WinDLL("crypt32", use_last_error=True)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree.restype = ctypes.c_void_p
        func = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
        func.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.POINTER(Blob),
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        func.restype = wintypes.BOOL
        # UI_FORBIDDEN only; LOCAL_MACHINE is deliberately never used.
        if not func(ctypes.byref(source), None, ctypes.byref(entropy), None, None, 1, ctypes.byref(output)):
            raise ValueError("SECURE_STORE_UNAVAILABLE")
        try:
            return ctypes.string_at(output.data, output.size)
        finally:
            kernel.LocalFree(ctypes.cast(output.data, ctypes.c_void_p))

    def protect(self, data):
        return self._crypt(data)

    def unprotect(self, data):
        return self._crypt(data, decrypt=True)


class ColabSecretStore:
    def __init__(self, path: Path, *, protector=None, writer=write_private_file):
        self.path = Path(path)
        self._protector = protector if protector is not None else WindowsUserProtector()
        self._writer = writer

    def load(self):
        _no_links(self.path, must_exist=False)
        if not self.path.exists():
            return None
        raw = self.path.read_bytes()
        if len(raw) > 65536:
            raise ValueError("SECURE_STORE_INVALID")
        payload = json.loads(self._protector.unprotect(base64.b64decode(raw, validate=True)))
        if not isinstance(payload, dict):
            raise ValueError("SECURE_STORE_INVALID")
        return payload

    def save(self, payload):
        _no_links(self.path, must_exist=False)
        encrypted = self._protector.protect(json.dumps(payload, allow_nan=False).encode("utf-8"))
        self._writer(self.path, base64.b64encode(encrypted).decode("ascii"))

    def delete(self):
        _no_links(self.path, must_exist=False)
        self.path.unlink(missing_ok=True)
