"""Full QA flow using injected synthetic responses and cleanup evidence only."""
import base64
from http.client import IncompleteRead
import io
import json
import socket
from urllib.error import HTTPError

import pytest

from qa.colab_readback import QADiagnostics, record_cleanup, verify_readback
from qa.colab_qa_run import (
    FileCleanupEvidence, RuntimeCleanupEvidence, UploadEvidence, QAResultSaveError,
    checks, run_qa,
)

DATA = (bytes(range(256)) * 2588)[:662508]
PATH = "sorigul-transfer/synthetic-run/synthetic.bin"
SECRET = "PRIVATE_PROXY_TOKEN_ACCOUNT_URL_HEADER_MEDIA"
UPLOAD = UploadEvidence(True, True, True, 11, 11)
FILE_CLEAN = FileCleanupEvidence(True, True, True)
RUNTIME_CLEAN = RuntimeCleanupEvidence(True, True, True, True)


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    def forbidden(*a, **k):
        pytest.fail("ACTUAL_NETWORK_FORBIDDEN")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)


def model():
    return {"path": PATH, "type": "file", "format": "base64", "size": len(DATA),
            "content": base64.b64encode(DATA).decode()}


class Response(io.BytesIO):
    status = 200
    def __init__(self, payload=None, *, raw=None, status=200, length=None, read_error=None):
        raw = json.dumps(model() if payload is None else payload).encode() if raw is None else raw
        super().__init__(raw)
        self.status = status
        self.headers = {"Content-Length": str(len(raw) if length is None else length)}
        self.read_error = read_error
    def read(self, limit=-1):
        if self.read_error:
            raise self.read_error
        return super().read(limit)


class Transport:
    def __init__(self, events, *, response=None, error=None):
        self.events = events
        self.response = response
        self.error = error
    def open_readback(self, *, timeout_seconds):
        assert timeout_seconds == 20
        self.events.append("readback")
        if self.error:
            raise self.error
        return self.response if self.response is not None else Response()


def execute(*, response=None, error=None, upload=UPLOAD, file=FILE_CLEAN,
            runtime=RUNTIME_CLEAN, limit=2*1024*1024):
    events, saved = [], []
    def cleanup(name, evidence):
        events.append(name)
        if isinstance(evidence, Exception):
            raise evidence
        return evidence
    def save(snapshot):
        events.append("save")
        # Force an actual serialization round-trip, not an in-memory alias.
        saved.append(json.loads(json.dumps(snapshot)))
    result = run_qa(upload=upload, expected=DATA, expected_path=PATH,
        transport=Transport(events, response=response, error=error),
        file_cleanup=lambda: cleanup("file_cleanup", file),
        runtime_cleanup=lambda: cleanup("runtime_cleanup", runtime),
        save_snapshot=save, max_response_bytes=limit)
    assert events[-3:] == ["file_cleanup", "runtime_cleanup", "save"]
    assert len(saved) == 1 and saved[0] == result.snapshot()
    assert SECRET not in json.dumps(saved)
    assert PATH not in json.dumps(saved)
    return result, events, saved[0]


@pytest.mark.parametrize("wrap", ["none", "lf", "crlf"])
def test_end_to_end_success_saved_receipt(wrap):
    payload = model()
    if wrap != "none":
        payload["content"] = base64.encodebytes(DATA).decode()
        if wrap == "crlf":
            payload["content"] = payload["content"].replace("\n", "\r\n")
    result, events, saved = execute(response=Response(payload))
    assert events == ["readback", "file_cleanup", "runtime_cleanup", "save"]
    assert result.run_outcome == "PASS"
    assert saved["upload_chunks_total"] == saved["upload_chunks_acknowledged"] == 11
    assert saved["readback"]["sha256_equal"] is saved["readback"]["bytes_equal"] is True
    assert checks(saved) == {"PRODUCT_UPLOAD_VERIFIED": "PASS", "QA_READBACK_PASSED": "PASS",
        "QA_FILE_CLEANUP_CONFIRMED": "PASS", "QA_RUNTIME_CLEANUP_CONFIRMED": "PASS"}


@pytest.mark.parametrize("status", [401, 403, 404, 429, 500])
def test_http_failure_still_cleans_runtime_and_keeps_upload_pass(status):
    result, events, saved = execute(response=Response(status=status))
    assert result.run_outcome == "FAIL"
    assert saved["readback"]["http_status"] == status
    assert saved["jupyter_accessed"] is True
    assert checks(saved) == {"PRODUCT_UPLOAD_VERIFIED": "PASS", "QA_READBACK_PASSED": "FAIL",
        "QA_FILE_CLEANUP_CONFIRMED": "PASS", "QA_RUNTIME_CLEANUP_CONFIRMED": "PASS"}
    assert events.count("readback") == 1


@pytest.mark.parametrize("response,error,code,accessed", [
    (None, TimeoutError(SECRET), "TIMEOUT", False),
    (Response(read_error=TimeoutError(SECRET)), None, "TIMEOUT", True),
    (Response(read_error=IncompleteRead(SECRET.encode(), 12)), None, "INCOMPLETE_RESPONSE", True),
    (Response(raw=b"{}", length=20), None, "INCOMPLETE_RESPONSE", True),
    (Response(raw=b"{"), None, "JSON_INVALID", True),
])
def test_transport_and_parse_errors(response, error, code, accessed):
    _, _, saved = execute(response=response, error=error)
    assert saved["readback"]["error_code"] == code
    assert saved["jupyter_request_attempted"] is True
    assert saved["jupyter_accessed"] is accessed
    assert checks(saved)["QA_RUNTIME_CLEANUP_CONFIRMED"] == "PASS"


@pytest.mark.parametrize("change,code", [
    ({"content": None}, "MODEL_INVALID"),
    ({"format": "text"}, "MODEL_INVALID"),
    ({"content": "!"}, "BASE64_INVALID"),
    ({"size": len(DATA)+1}, "SIZE_MISMATCH"),
    ({"content": base64.b64encode(b"X"*len(DATA)).decode()}, "SHA256_MISMATCH"),
])
def test_field_decode_size_hash_failures(change, code):
    _, _, saved = execute(response=Response({**model(), **change}))
    assert saved["readback"]["error_code"] == code
    assert checks(saved)["PRODUCT_UPLOAD_VERIFIED"] == "PASS"
    assert checks(saved)["QA_READBACK_PASSED"] == "FAIL"


def test_missing_content_and_response_limit():
    payload = model()
    del payload["content"]
    assert execute(response=Response(payload))[2]["readback"]["content_valid"] is False
    assert execute(limit=64)[2]["readback"]["error_code"] == "RESPONSE_TOO_LARGE"


def test_lone_carriage_return_is_not_an_allowed_lf_or_crlf_wrap():
    payload = {**model(), "content": model()["content"] + "\r"}
    _, _, saved = execute(response=Response(payload))
    assert saved["readback"]["error_code"] == "BASE64_INVALID"
    assert checks(saved)["QA_RUNTIME_CLEANUP_CONFIRMED"] == "PASS"


def test_exact_bytes_comparison_catches_even_a_hash_collision(monkeypatch):
    # Force equal digests solely to exercise the independent final comparison.
    # This does NOT claim a real SHA256 collision or bypass production checks.
    class Collision:
        def digest(self):
            return b"same-mock-digest"
    monkeypatch.setattr("qa.colab_readback.hashlib.sha256", lambda value: Collision())
    payload = {**model(), "content": base64.b64encode(b"X"*len(DATA)).decode()}
    _, _, saved = execute(response=Response(payload))
    assert saved["readback"]["sha256_equal"] is True
    assert saved["readback"]["bytes_equal"] is False
    assert saved["readback"]["error_code"] == "BYTES_MISMATCH"


@pytest.mark.parametrize("which", ["file", "runtime"])
@pytest.mark.parametrize("evidence", [200, True, None, "CLEANED"])
def test_http_success_and_bare_true_are_not_cleanup_proof(which, evidence):
    _, _, saved = execute(**{which: evidence})
    name = "QA_FILE_CLEANUP_CONFIRMED" if which == "file" else "QA_RUNTIME_CLEANUP_CONFIRMED"
    assert checks(saved)[name] == "NOT_VERIFIED"
    assert saved["run_outcome"] == "FAIL"
    assert checks(saved)["QA_READBACK_PASSED"] == "PASS"


@pytest.mark.parametrize("file,runtime,name,expected", [
    (FileCleanupEvidence(True, False, True), RUNTIME_CLEAN, "QA_FILE_CLEANUP_CONFIRMED", "FAIL"),
    (FileCleanupEvidence(True, True, None), RUNTIME_CLEAN, "QA_FILE_CLEANUP_CONFIRMED", "NOT_VERIFIED"),
    (FILE_CLEAN, RuntimeCleanupEvidence(True, True, True, None), "QA_RUNTIME_CLEANUP_CONFIRMED", "NOT_VERIFIED"),
    (FILE_CLEAN, RuntimeCleanupEvidence(True, True, False, True), "QA_RUNTIME_CLEANUP_CONFIRMED", "FAIL"),
    (RuntimeError(SECRET), RUNTIME_CLEAN, "QA_FILE_CLEANUP_CONFIRMED", "FAIL"),
    (FILE_CLEAN, RuntimeError(SECRET), "QA_RUNTIME_CLEANUP_CONFIRMED", "FAIL"),
])
def test_cleanup_failures_and_unknowns_independent(file, runtime, name, expected):
    _, _, saved = execute(file=file, runtime=runtime)
    assert checks(saved)[name] == expected
    assert saved["run_outcome"] == "FAIL"


def test_bad_upload_never_requests_readback_but_still_cleans():
    _, events, saved = execute(upload=UploadEvidence(False, False, False, 11, 8))
    assert events == ["file_cleanup", "runtime_cleanup", "save"]
    assert checks(saved)["PRODUCT_UPLOAD_VERIFIED"] == "FAIL"
    assert checks(saved)["QA_READBACK_PASSED"] == "NOT_VERIFIED"
    assert checks(saved)["QA_RUNTIME_CLEANUP_CONFIRMED"] == "PASS"


def test_fresh_run_has_no_stale_success_flags():
    assert execute()[0].run_outcome == "PASS"
    _, _, saved = execute(error=TimeoutError(SECRET), runtime=None)
    assert saved["jupyter_accessed"] is False
    assert saved["readback"]["bytes_equal"] is None
    assert saved["runtime_cleanup"]["outcome"] == "UNCONFIRMED"
    assert saved["run_outcome"] == "FAIL"


@pytest.mark.parametrize("limit", [0, -1, True, SECRET])
def test_invalid_limit_resets_prior_readback_success(limit):
    diagnostics = QADiagnostics()
    assert verify_readback(lambda: Response(), expected=DATA, expected_path=PATH, diagnostics=diagnostics)
    assert not verify_readback(lambda: pytest.fail("MUST_NOT_OPEN"), expected=DATA,
        expected_path=PATH, diagnostics=diagnostics, max_response_bytes=limit)
    assert diagnostics.readback.outcome == "FAIL"
    assert diagnostics.readback.error_code == "CONFIG_INVALID"
    assert diagnostics.readback.request_attempted is False
    assert diagnostics.readback.bytes_equal is None


class BrokenClose:
    def close(self):
        raise RuntimeError(SECRET)


def test_http_error_close_cannot_escape_or_mask_primary_error():
    def open_response():
        raise HTTPError("https://"+SECRET, 403, SECRET, {}, BrokenClose())
    diagnostics = QADiagnostics()
    assert not verify_readback(open_response, expected=DATA, expected_path=PATH, diagnostics=diagnostics)
    assert diagnostics.readback.error_code == "HTTP_ERROR"
    assert diagnostics.readback.response_close_failed is True
    assert not record_cleanup(diagnostics, runtime=True, cleanup=open_response)
    assert diagnostics.runtime_cleanup.response_close_failed is True
    assert SECRET not in json.dumps(diagnostics.snapshot())


def test_snapshot_filters_accidental_tainted_field_assignments():
    diagnostics = QADiagnostics(upload_verified=SECRET, jupyter_accessed=SECRET)
    diagnostics.readback.stage_id = SECRET
    diagnostics.readback.exception_type = SECRET
    diagnostics.readback.response_bytes = SECRET
    diagnostics.runtime_cleanup.error_code = SECRET
    assert SECRET not in json.dumps(diagnostics.snapshot())


def test_result_writer_error_is_redacted_after_both_cleanups():
    events = []
    def file_cleanup():
        events.append("file")
        return FILE_CLEAN
    def runtime_cleanup():
        events.append("runtime")
        return RUNTIME_CLEAN
    def save(snapshot):
        events.append("save")
        raise RuntimeError(SECRET)
    with pytest.raises(QAResultSaveError, match="^QA_RESULT_SAVE_FAILED$"):
        run_qa(upload=UPLOAD, expected=DATA, expected_path=PATH, transport=Transport(events),
               file_cleanup=file_cleanup, runtime_cleanup=runtime_cleanup, save_snapshot=save)
    assert events[-3:] == ["file", "runtime", "save"]


def test_cancel_during_file_cleanup_still_runs_runtime_cleanup_and_saves():
    events, saved = [], []
    def file_cleanup():
        events.append("file")
        raise KeyboardInterrupt()
    def runtime_cleanup():
        events.append("runtime")
        return RUNTIME_CLEAN
    with pytest.raises(KeyboardInterrupt):
        run_qa(upload=UPLOAD, expected=DATA, expected_path=PATH, transport=Transport(events),
               file_cleanup=file_cleanup, runtime_cleanup=runtime_cleanup, save_snapshot=saved.append)
    assert events[-2:] == ["file", "runtime"]
    assert saved[0]["run_outcome"] == "FAIL"
    assert saved[0]["runtime_cleanup"]["outcome"] == "PASS"


def test_missing_upload_evidence_still_cleans_without_readback():
    _, events, saved = execute(upload=None)
    assert events == ["file_cleanup", "runtime_cleanup", "save"]
    assert checks(saved)["PRODUCT_UPLOAD_VERIFIED"] == "NOT_VERIFIED"


def test_json_result_file_contains_only_safe_snapshot(tmp_path):
    output = tmp_path / "synthetic-result.json"
    result = run_qa(upload=UPLOAD, expected=DATA, expected_path=PATH, transport=Transport([]),
        file_cleanup=lambda: FILE_CLEAN, runtime_cleanup=lambda: RUNTIME_CLEAN,
        save_snapshot=lambda snapshot: output.write_text(json.dumps(snapshot), encoding="utf-8"))
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved == result.snapshot()
    assert saved["run_outcome"] == "PASS"
    assert SECRET not in output.read_text(encoding="utf-8")
