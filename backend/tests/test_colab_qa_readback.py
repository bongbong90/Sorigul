"""Synthetic responses only; a network connection is a test failure."""
import base64
import binascii
from http.client import IncompleteRead
import io
import json
import socket
from urllib.error import HTTPError, URLError

import pytest

from qa.colab_readback import QADiagnostics, record_cleanup, verify_readback


DATA = bytes(range(256)) * 4
PATH = "sorigul-transfer/synthetic-test/sample.mp3"
SECRET = "SECRET_TOKEN_PROXY_ACCOUNT_HEADER_MEDIA"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("NETWORK_FORBIDDEN")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)


def model(data=DATA):
    return {"path": PATH, "type": "file", "format": "base64",
            "size": len(data), "content": base64.b64encode(data).decode("ascii"),
            "mimetype": "audio/mpeg", "hash_algorithm": "sha256"}


class Response(io.BytesIO):
    def __init__(self, raw, status=200, headers=None):
        super().__init__(raw)
        self.status = status
        self.headers = headers if headers is not None else {"Content-Length": str(len(raw))}
        self.requested_limit = None

    def read(self, limit=-1):
        self.requested_limit = limit
        return super().read(limit)


def check(payload=None, *, raw=None, status=200, expected=DATA, limit=2*1024*1024,
          headers=None):
    if raw is None:
        raw = json.dumps(model() if payload is None else payload).encode()
    response = Response(raw, status, headers)
    diagnostics = QADiagnostics(upload_verified=True, upload_content_sha256_verified=True)
    passed = verify_readback(lambda: response, expected=expected, expected_path=PATH,
                             diagnostics=diagnostics, max_response_bytes=limit)
    assert diagnostics.upload_verified is True
    assert diagnostics.upload_content_sha256_verified is True
    return passed, diagnostics, response


@pytest.mark.parametrize("wrapping", ["none", "lf", "crlf"])
def test_actual_full_byte_pass_including_wrapped_base64(wrapping):
    data = bytes(range(256)) * 2588 + b"synthetic" * 2  # binary, not a real MP3
    payload = model(data)
    if wrapping != "none":
        payload["content"] = base64.encodebytes(data).decode("ascii")
        if wrapping == "crlf":
            payload["content"] = payload["content"].replace("\n", "\r\n")
    passed, diagnostics, _ = check(payload, expected=data)
    assert passed
    receipt = diagnostics.snapshot()["readback"]
    assert receipt["outcome"] == "PASS"
    assert receipt["stage_id"] == "READBACK_COMPLETE"
    assert all(receipt[k] is True for k in (
        "request_attempted", "response_received", "json_valid", "path_valid", "type_valid",
        "format_valid", "content_valid", "base64_decoded", "size_equal", "sha256_equal", "bytes_equal"))
    assert diagnostics.jupyter_accessed is True


def test_old_strict_decode_reproduces_a_candidate_not_historical_proof():
    wrapped = base64.encodebytes(DATA).decode("ascii")
    with pytest.raises(binascii.Error):
        base64.b64decode(wrapped, validate=True)  # exact historical QA expression
    assert check({**model(), "content": wrapped})[0]


@pytest.mark.parametrize("field,value", [
    ("path", "unowned"), ("type", "directory"), ("format", "text"),
    ("content", None), ("content", 123),
])
def test_response_fields(field, value):
    passed, d, _ = check({**model(), field: value})
    assert not passed
    assert d.readback.stage_id == "READBACK_MODEL"
    assert d.readback.error_code == "MODEL_INVALID"
    assert d.readback.base64_decoded is None


def test_missing_content():
    payload = model()
    del payload["content"]
    passed, d, _ = check(payload)
    assert not passed and d.readback.content_valid is False


@pytest.mark.parametrize("value", ["%%%", "a", "Y Q==", "Y\tQ==", "한글"])
def test_invalid_base64_is_not_permissively_ignored(value):
    passed, d, _ = check({**model(), "content": value})
    assert not passed
    assert d.readback.stage_id == "READBACK_BASE64"
    assert d.readback.error_code == "BASE64_INVALID"
    assert d.readback.base64_decoded is False


@pytest.mark.parametrize("size", [True, len(DATA)+1, None, str(len(DATA))])
def test_file_size_mismatch(size):
    passed, d, _ = check({**model(), "size": size})
    assert not passed and d.readback.size_equal is False
    assert d.readback.error_code == "SIZE_MISMATCH"


def test_sha256_computed_from_decoded_bytes_not_server_hash_claim():
    payload = model(b"X" * len(DATA))
    payload["hash"] = "forged"
    passed, d, _ = check(payload)
    assert not passed and d.readback.sha256_equal is False
    assert d.readback.size_equal is True
    assert d.readback.bytes_equal is None
    assert d.readback.error_code == "SHA256_MISMATCH"


@pytest.mark.parametrize("status", [404, 401, 403, 429, 500])
def test_http_error_responses(status):
    passed, d, response = check(status=status)
    assert not passed and d.readback.http_status == status
    assert d.readback.error_code == "HTTP_ERROR"
    assert d.readback.stage_id == "READBACK_HTTP_STATUS"
    assert response.requested_limit is None
    assert d.jupyter_accessed is True


def test_urllib_http_error_has_no_sensitive_details():
    def open_response():
        raise HTTPError("https://"+SECRET, 404, SECRET, {"Authorization": SECRET}, None)
    d = QADiagnostics()
    assert not verify_readback(open_response, expected=DATA, expected_path=PATH, diagnostics=d)
    assert d.readback.http_status == 404
    assert d.readback.exception_type == "HTTPError"
    assert d.jupyter_request_attempted and d.jupyter_accessed
    assert SECRET not in json.dumps(d.snapshot())


@pytest.mark.parametrize("exception,code", [
    (TimeoutError(SECRET), "TIMEOUT"),
    (URLError(TimeoutError(SECRET)), "TIMEOUT"),
    (URLError(SECRET), "TRANSPORT_ERROR"),
    (RuntimeError(SECRET), "QA_UNEXPECTED_EXCEPTION"),
])
def test_open_exceptions_redacted_and_flags(exception, code):
    def open_response():
        raise exception
    d = QADiagnostics()
    assert not verify_readback(open_response, expected=DATA, expected_path=PATH, diagnostics=d)
    assert d.readback.stage_id == "READBACK_OPEN"
    assert d.readback.error_code == code
    assert d.readback.request_attempted and d.jupyter_request_attempted
    assert not d.jupyter_accessed and not d.readback.response_received
    assert SECRET not in json.dumps(d.snapshot())


@pytest.mark.parametrize("exception,code", [
    (TimeoutError(SECRET), "TIMEOUT"),
    (IncompleteRead(SECRET.encode(), 10), "INCOMPLETE_RESPONSE"),
])
def test_read_exceptions(exception, code):
    class BrokenResponse(Response):
        def read(self, limit=-1):
            raise exception
    d = QADiagnostics()
    assert not verify_readback(lambda: BrokenResponse(b""), expected=DATA, expected_path=PATH, diagnostics=d)
    assert d.readback.stage_id == "READBACK_BODY"
    assert d.readback.error_code == code
    assert d.jupyter_accessed
    assert SECRET not in json.dumps(d.snapshot())


def test_truncated_body_against_content_length():
    passed, d, _ = check(raw=b'{"path":', headers={"Content-Length": "100"})
    assert not passed and d.readback.error_code == "INCOMPLETE_RESPONSE"


@pytest.mark.parametrize("raw", [b"{", b"\xff", b"not json"])
def test_invalid_json_without_raw_body_in_receipt(raw):
    passed, d, _ = check(raw=raw)
    assert not passed and d.readback.error_code == "JSON_INVALID"
    assert d.readback.json_valid is False


@pytest.mark.parametrize("raw", [b"[]", b"null", b"123"])
def test_non_object_json(raw):
    passed, d, _ = check(raw=raw)
    assert not passed and d.readback.error_code == "MODEL_INVALID"


def test_bounded_read_and_exact_limit():
    raw = json.dumps(model()).encode()
    assert check(raw=raw, limit=len(raw))[0]
    passed, d, response = check(raw=raw, limit=len(raw)-1)
    assert not passed and d.readback.error_code == "RESPONSE_TOO_LARGE"
    assert response.requested_limit == len(raw)
    assert d.readback.json_valid is None


def test_no_content_or_arbitrary_response_keys_in_success_receipt():
    payload = {**model(), SECRET: SECRET, "hash": SECRET}
    passed, d, _ = check(payload)
    assert passed
    serialized = json.dumps(d.snapshot())
    assert SECRET not in serialized and PATH not in serialized
    assert payload["content"] not in serialized


def test_cleanup_cannot_mask_primary_failure_and_runtime_can_still_pass():
    _, d, _ = check({**model(), "content": "!"})
    original = d.snapshot()["readback"]
    def failed_cleanup():
        raise RuntimeError(SECRET)
    assert not record_cleanup(d, runtime=False, cleanup=failed_cleanup)
    assert record_cleanup(d, runtime=True, cleanup=lambda: True)
    assert d.snapshot()["readback"] == original
    assert d.file_cleanup.error_code == "FILE_CLEANUP_UNCONFIRMED"
    assert d.runtime_cleanup.outcome == "PASS"
    assert SECRET not in json.dumps(d.snapshot())


@pytest.mark.parametrize("returned", [False, None, 200, "CLEANED"])
def test_cleanup_requires_explicit_confirmation(returned):
    d = QADiagnostics()
    assert not record_cleanup(d, runtime=True, cleanup=lambda: returned)
    assert d.runtime_cleanup.error_code == "RUNTIME_CLEANUP_UNCONFIRMED"


def test_arbitrary_exception_class_name_is_redacted():
    exception_class = type(SECRET, (Exception,), {})
    def open_response():
        raise exception_class(SECRET)
    d = QADiagnostics()
    assert not verify_readback(open_response, expected=DATA, expected_path=PATH, diagnostics=d)
    assert d.readback.exception_type == "OtherException"
    assert SECRET not in json.dumps(d.snapshot())


def test_cleanup_http_error_retains_only_safe_status_and_stage():
    def cleanup():
        raise HTTPError("https://"+SECRET, 403, SECRET, {}, None)
    d = QADiagnostics()
    assert not record_cleanup(d, runtime=True, cleanup=cleanup)
    assert d.runtime_cleanup.stage_id == "RUNTIME_CLEANUP"
    assert d.runtime_cleanup.http_status == 403
    assert SECRET not in json.dumps(d.snapshot())


def test_access_flag_does_not_reset_after_an_observed_response():
    _, d, _ = check()
    def timeout():
        raise TimeoutError(SECRET)
    assert not verify_readback(timeout, expected=DATA, expected_path=PATH, diagnostics=d)
    assert d.jupyter_accessed is True  # session-level observed access
    assert d.readback.response_received is False  # this attempt has no response
    assert d.readback.bytes_equal is None  # no stale previous PASS
