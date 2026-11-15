"""Redacted, bounded Contents readback checks for a separately approved QA run.

No network client, credential loader, runtime creator or URL is provided here.
The caller injects an already restricted response factory. Receipts contain only
fixed identifiers, booleans, counts and allowlisted exception categories.
"""
from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass, field
from enum import Enum
import hashlib
from http.client import IncompleteRead
import json
from typing import Callable
from urllib.error import HTTPError, URLError


class Stage(str, Enum):
    CONFIG = "READBACK_CONFIG"
    OPEN = "READBACK_OPEN"
    STATUS = "READBACK_HTTP_STATUS"
    READ = "READBACK_BODY"
    JSON = "READBACK_JSON"
    MODEL = "READBACK_MODEL"
    BASE64 = "READBACK_BASE64"
    SIZE = "READBACK_SIZE"
    HASH = "READBACK_SHA256"
    BYTES = "READBACK_BYTES"
    COMPLETE = "READBACK_COMPLETE"


class Code(str, Enum):
    CONFIG_INVALID = "CONFIG_INVALID"
    HTTP_ERROR = "HTTP_ERROR"
    TIMEOUT = "TIMEOUT"
    TRANSPORT = "TRANSPORT_ERROR"
    INCOMPLETE = "INCOMPLETE_RESPONSE"
    TOO_LARGE = "RESPONSE_TOO_LARGE"
    JSON_INVALID = "JSON_INVALID"
    MODEL_INVALID = "MODEL_INVALID"
    BASE64_INVALID = "BASE64_INVALID"
    SIZE_MISMATCH = "SIZE_MISMATCH"
    HASH_MISMATCH = "SHA256_MISMATCH"
    BYTES_MISMATCH = "BYTES_MISMATCH"
    UNEXPECTED = "QA_UNEXPECTED_EXCEPTION"


class CheckFailed(Exception):
    def __init__(self, code: Code):
        self.code = code
        super().__init__(code.value)


def _exception_type(exc: Exception) -> str:
    # Never use str/repr/traceback, arbitrary class names, args or HTTP headers.
    for kind, name in (
        (CheckFailed, "CheckFailed"), (HTTPError, "HTTPError"),
        (TimeoutError, "TimeoutError"), (IncompleteRead, "IncompleteRead"),
        (json.JSONDecodeError, "JSONDecodeError"), (binascii.Error, "Base64Error"),
        (UnicodeError, "UnicodeError"), (URLError, "URLError"),
        (KeyError, "KeyError"), (TypeError, "TypeError"),
        (ValueError, "ValueError"), (OSError, "OSError"),
    ):
        if isinstance(exc, kind):
            return name
    return "OtherException"


def _status(value):
    return value if type(value) is int and 100 <= value <= 599 else None


@dataclass
class ReadbackReceipt:
    stage_id: str = Stage.OPEN.value
    outcome: str = "NOT_RUN"
    exception_type: str | None = None
    error_code: str | None = None
    request_attempted: bool = False
    response_received: bool = False
    http_status: int | None = None
    response_bytes: int | None = None
    json_valid: bool | None = None
    path_valid: bool | None = None
    type_valid: bool | None = None
    format_valid: bool | None = None
    content_valid: bool | None = None
    base64_decoded: bool | None = None
    size_equal: bool | None = None
    sha256_equal: bool | None = None
    bytes_equal: bool | None = None
    response_close_failed: bool = False


@dataclass
class CleanupReceipt:
    stage_id: str = "NOT_RUN"
    attempted: bool = False
    outcome: str = "NOT_RUN"
    exception_type: str | None = None
    error_code: str | None = None
    http_status: int | None = None
    response_close_failed: bool = False


_EXCEPTION_TYPES = {
    "CheckFailed", "HTTPError", "TimeoutError", "IncompleteRead", "JSONDecodeError",
    "Base64Error", "UnicodeError", "URLError", "KeyError", "TypeError", "ValueError",
    "OSError", "OtherException",
}


def _choice(value, choices, default=None):
    return value if type(value) is str and value in choices else default


def _boolean(value):
    return value if type(value) is bool else None


def _count(value):
    return value if type(value) is int and value >= 0 else None


def _close_error(exc):
    try:
        exc.close()
        return False
    except Exception:
        # Preserve the primary HTTP failure, never expose close error text.
        return True


@dataclass
class QADiagnostics:
    # Upload evidence is kept separately; a QA readback failure cannot change it.
    upload_verified: bool | None = None
    upload_content_sha256_verified: bool | None = None
    jupyter_request_attempted: bool = False
    jupyter_accessed: bool = False
    readback: ReadbackReceipt = field(default_factory=ReadbackReceipt)
    file_cleanup: CleanupReceipt = field(default_factory=CleanupReceipt)
    runtime_cleanup: CleanupReceipt = field(default_factory=CleanupReceipt)
    upload_chunks_total: int | None = None
    upload_chunks_acknowledged: int | None = None
    upload_size_equal: bool | None = None
    run_outcome: str = "NOT_RUN"

    def snapshot(self):
        # An accidental callback assignment must not turn a safe receipt into
        # a vehicle for raw response/header/exception data. No deepcopy/str/repr.
        r = self.readback if type(self.readback) is ReadbackReceipt else ReadbackReceipt()
        readback = {
            "stage_id": _choice(r.stage_id, {s.value for s in Stage}, Stage.CONFIG.value),
            "outcome": _choice(r.outcome, {"NOT_RUN", "RUNNING", "PASS", "FAIL"}, "FAIL"),
            "exception_type": _choice(r.exception_type, _EXCEPTION_TYPES),
            "error_code": _choice(r.error_code, {c.value for c in Code}),
            "http_status": _status(r.http_status), "response_bytes": _count(r.response_bytes),
        }
        for name in ("request_attempted", "response_received", "json_valid", "path_valid",
                     "type_valid", "format_valid", "content_valid", "base64_decoded",
                     "size_equal", "sha256_equal", "bytes_equal", "response_close_failed"):
            readback[name] = _boolean(getattr(r, name))
        result = {
            "upload_verified": _boolean(self.upload_verified),
            "upload_content_sha256_verified": _boolean(self.upload_content_sha256_verified),
            "upload_chunks_total": _count(self.upload_chunks_total),
            "upload_chunks_acknowledged": _count(self.upload_chunks_acknowledged),
            "upload_size_equal": _boolean(self.upload_size_equal),
            "jupyter_request_attempted": _boolean(self.jupyter_request_attempted),
            "jupyter_accessed": _boolean(self.jupyter_accessed), "readback": readback,
            "run_outcome": _choice(self.run_outcome, {"NOT_RUN", "RUNNING", "PASS", "FAIL"}, "FAIL"),
        }
        for name in ("file_cleanup", "runtime_cleanup"):
            c = getattr(self, name)
            if type(c) is not CleanupReceipt:
                c = CleanupReceipt()
            result[name] = {
                "stage_id": _choice(c.stage_id, {"NOT_RUN", "FILE_CLEANUP", "RUNTIME_CLEANUP"}, "NOT_RUN"),
                "attempted": _boolean(c.attempted),
                "outcome": _choice(c.outcome, {"NOT_RUN", "RUNNING", "PASS", "FAIL", "UNCONFIRMED"}, "FAIL"),
                "exception_type": _choice(c.exception_type, _EXCEPTION_TYPES),
                "error_code": _choice(c.error_code, {"FILE_CLEANUP_UNCONFIRMED", "RUNTIME_CLEANUP_UNCONFIRMED"}),
                "http_status": _status(c.http_status),
                "response_close_failed": _boolean(c.response_close_failed),
            }
        return result


def verify_readback(open_response: Callable, *, expected: bytes,
                    expected_path: str, diagnostics: QADiagnostics,
                    max_response_bytes: int = 2 * 1024 * 1024) -> bool:
    """Check one response; no retry. open_response returns a context manager.

    The approved transport must bind GET ?content=1&format=base64 to an owned
    path/origin and disable redirects. This helper never logs that path or URL.
    PASS requires matching size, locally computed SHA256 AND exact bytes.
    """
    receipt = diagnostics.readback = ReadbackReceipt(stage_id=Stage.CONFIG.value, outcome="RUNNING")
    try:
        if type(max_response_bytes) is not int or max_response_bytes < 1:
            raise CheckFailed(Code.CONFIG_INVALID)
        receipt.stage_id = Stage.OPEN.value
        receipt.request_attempted = diagnostics.jupyter_request_attempted = True
        with open_response() as response:
            receipt.response_received = diagnostics.jupyter_accessed = True
            receipt.stage_id = Stage.STATUS.value
            receipt.http_status = _status(response.status)
            if receipt.http_status != 200:
                raise CheckFailed(Code.HTTP_ERROR)
            receipt.stage_id = Stage.READ.value
            raw = response.read(max_response_bytes + 1)
            receipt.response_bytes = len(raw)
            if len(raw) > max_response_bytes:
                raise CheckFailed(Code.TOO_LARGE)
            length = response.headers.get("Content-Length")
            if length is not None and (
                not isinstance(length, str) or not length.isascii()
                or not length.isdigit() or len(length) > 12
                or int(length) != len(raw)
            ):
                raise CheckFailed(Code.INCOMPLETE)
        receipt.stage_id = Stage.JSON.value
        receipt.json_valid = False
        model = json.loads(raw)
        receipt.json_valid = True
        receipt.stage_id = Stage.MODEL.value
        if not isinstance(model, dict):
            raise CheckFailed(Code.MODEL_INVALID)
        receipt.path_valid = model.get("path") == expected_path
        receipt.type_valid = model.get("type") == "file"
        receipt.format_valid = model.get("format") == "base64"
        receipt.content_valid = isinstance(model.get("content"), str)
        if not all((receipt.path_valid, receipt.type_valid,
                    receipt.format_valid, receipt.content_valid)):
            raise CheckFailed(Code.MODEL_INVALID)
        receipt.stage_id = Stage.BASE64.value
        receipt.base64_decoded = False
        # MIME/Jupyter-style line wraps are permitted. Other non-alphabet
        # characters remain errors, rather than using permissive validate=False.
        encoded = model["content"].encode("ascii").replace(b"\r\n", b"\n").replace(b"\n", b"")
        actual = base64.b64decode(encoded, validate=True)
        receipt.base64_decoded = True
        receipt.stage_id = Stage.SIZE.value
        receipt.size_equal = (type(model.get("size")) is int
                              and model["size"] == len(actual) == len(expected))
        if not receipt.size_equal:
            raise CheckFailed(Code.SIZE_MISMATCH)
        receipt.stage_id = Stage.HASH.value
        receipt.sha256_equal = hashlib.sha256(actual).digest() == hashlib.sha256(expected).digest()
        if not receipt.sha256_equal:
            raise CheckFailed(Code.HASH_MISMATCH)
        receipt.stage_id = Stage.BYTES.value
        receipt.bytes_equal = actual == expected
        if not receipt.bytes_equal:
            raise CheckFailed(Code.BYTES_MISMATCH)
        receipt.stage_id = Stage.COMPLETE.value
        receipt.outcome = "PASS"
        return True
    except Exception as exc:
        receipt.outcome = "FAIL"
        receipt.exception_type = _exception_type(exc)
        if isinstance(exc, HTTPError):
            receipt.response_received = diagnostics.jupyter_accessed = True
            receipt.http_status = _status(exc.code)
            receipt.error_code = Code.HTTP_ERROR.value
            receipt.response_close_failed = _close_error(exc)
        elif isinstance(exc, CheckFailed):
            receipt.error_code = exc.code.value
        elif isinstance(exc, TimeoutError) or (isinstance(exc, URLError) and isinstance(exc.reason, TimeoutError)):
            receipt.error_code = Code.TIMEOUT.value
        elif isinstance(exc, IncompleteRead):
            receipt.error_code = Code.INCOMPLETE.value
        elif isinstance(exc, (json.JSONDecodeError, UnicodeDecodeError)) and receipt.stage_id == Stage.JSON.value:
            receipt.error_code = Code.JSON_INVALID.value
        elif isinstance(exc, (binascii.Error, UnicodeEncodeError)) and receipt.stage_id == Stage.BASE64.value:
            receipt.error_code = Code.BASE64_INVALID.value
        elif isinstance(exc, (URLError, OSError)):
            receipt.error_code = Code.TRANSPORT.value
        else:
            receipt.error_code = Code.UNEXPECTED.value
        return False


def record_cleanup(diagnostics: QADiagnostics, *, runtime: bool,
                   cleanup: Callable[[], bool]) -> bool:
    """Capture caller-owned cleanup without masking the primary readback receipt.

    Callback must return literal True only after the required confirmations.
    Runtime success means caller confirmed DELETE, absence and durable CLEANED;
    this helper cannot infer it from an HTTP success alone.
    """
    receipt = CleanupReceipt(stage_id="RUNTIME_CLEANUP" if runtime else "FILE_CLEANUP",
                             attempted=True, outcome="RUNNING")
    if runtime:
        diagnostics.runtime_cleanup = receipt
    else:
        diagnostics.file_cleanup = receipt
    try:
        if cleanup() is not True:
            raise CheckFailed(Code.UNEXPECTED)
        receipt.outcome = "PASS"
        return True
    except Exception as exc:
        receipt.outcome = "FAIL"
        receipt.exception_type = _exception_type(exc)
        receipt.error_code = "RUNTIME_CLEANUP_UNCONFIRMED" if runtime else "FILE_CLEANUP_UNCONFIRMED"
        if isinstance(exc, HTTPError):
            receipt.http_status = _status(exc.code)
            receipt.response_close_failed = _close_error(exc)
        return False
