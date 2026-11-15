"""QA-only orchestration. All effects are explicitly injected; no live adapter.

An approved adapter must pin the existing account/ownership, exact HTTPS origin
and owned Contents path, disable redirects/proxies, enforce the passed timeout,
and permit only the authorized operation. Nothing in this module authorizes it.
"""
from dataclasses import dataclass
from typing import ContextManager, Protocol

from qa.colab_readback import QADiagnostics, record_cleanup, verify_readback


class ReadbackTransport(Protocol):
    def open_readback(self, *, timeout_seconds: float) -> ContextManager:
        """Single owned GET ?content=1&format=base64; no retries or redirects."""


@dataclass(frozen=True)
class UploadEvidence:
    verified: bool | None
    content_sha256_verified: bool | None
    size_equal: bool | None
    chunks_total: int | None
    chunks_acknowledged: int | None


@dataclass(frozen=True)
class FileCleanupEvidence:
    delete_confirmed: bool | None = None
    file_absent: bool | None = None
    run_directory_absent: bool | None = None


@dataclass(frozen=True)
class RuntimeCleanupEvidence:
    delete_confirmed: bool | None = None
    get_absent: bool | None = None
    list_absent: bool | None = None
    ownership_cleaned: bool | None = None


def _verdict(values):
    if all(value is True for value in values):
        return "PASS"
    if any(value is False for value in values):
        return "FAIL"
    return "NOT_VERIFIED"


def checks(snapshot):
    """Four independent decisions, derived only from sanitized snapshot fields."""
    total = snapshot["upload_chunks_total"]
    ack = snapshot["upload_chunks_acknowledged"]
    chunks_ok = None if total is None or ack is None else total > 0 and total == ack
    def cleanup(name):
        return {"PASS": "PASS", "FAIL": "FAIL"}.get(snapshot[name]["outcome"], "NOT_VERIFIED")
    return {
        "PRODUCT_UPLOAD_VERIFIED": _verdict((snapshot["upload_verified"],
            snapshot["upload_content_sha256_verified"], snapshot["upload_size_equal"], chunks_ok)),
        "QA_READBACK_PASSED": {"PASS": "PASS", "FAIL": "FAIL"}.get(
            snapshot["readback"]["outcome"], "NOT_VERIFIED"),
        "QA_FILE_CLEANUP_CONFIRMED": cleanup("file_cleanup"),
        "QA_RUNTIME_CLEANUP_CONFIRMED": cleanup("runtime_cleanup"),
    }


def _cleanup(diagnostics, callback, *, runtime):
    verdict = "NOT_VERIFIED"
    def confirmed():
        nonlocal verdict
        evidence = callback()
        expected_type = RuntimeCleanupEvidence if runtime else FileCleanupEvidence
        if type(evidence) is not expected_type:
            return False  # HTTP 200, True, None and arbitrary strings are not evidence
        values = ((evidence.delete_confirmed, evidence.get_absent,
                   evidence.list_absent, evidence.ownership_cleaned) if runtime else
                  (evidence.delete_confirmed, evidence.file_absent, evidence.run_directory_absent))
        verdict = _verdict(values)
        return verdict == "PASS"
    passed = record_cleanup(diagnostics, runtime=runtime, cleanup=confirmed)
    receipt = diagnostics.runtime_cleanup if runtime else diagnostics.file_cleanup
    if not passed and verdict == "NOT_VERIFIED" and receipt.exception_type == "CheckFailed":
        receipt.outcome = "UNCONFIRMED"


class QAResultSaveError(Exception):
    """Fixed error type/text; never chains the writer's sensitive exception."""


def run_qa(*, upload: UploadEvidence, expected: bytes, expected_path: str,
           transport: ReadbackTransport, file_cleanup, runtime_cleanup,
           save_snapshot, max_response_bytes=2 * 1024 * 1024) -> QADiagnostics:
    """One run, one readback attempt, independent cleanup then safe persistence.

    Cleanup callbacks must be bound to this run's ownership before injection.
    Runtime evidence requires DELETE + GET/list absence + durable CLEANED,
    not merely an HTTP success. No automatic retries or Runtime creation here.
    A fresh diagnostics instance prevents cross-run stale success/access flags.
    """
    diagnostics = QADiagnostics(run_outcome="RUNNING")
    try:
        if type(upload) is UploadEvidence:
            diagnostics.upload_verified = upload.verified
            diagnostics.upload_content_sha256_verified = upload.content_sha256_verified
            diagnostics.upload_size_equal = upload.size_equal
            diagnostics.upload_chunks_total = upload.chunks_total
            diagnostics.upload_chunks_acknowledged = upload.chunks_acknowledged
        if checks(diagnostics.snapshot())["PRODUCT_UPLOAD_VERIFIED"] == "PASS":
            verify_readback(lambda: transport.open_readback(timeout_seconds=20),
                expected=expected, expected_path=expected_path, diagnostics=diagnostics,
                max_response_bytes=max_response_bytes)
    finally:
        # Each helper captures its own failure; Runtime cleanup always follows.
        try:
            _cleanup(diagnostics, file_cleanup, runtime=False)
        finally:
            try:
                _cleanup(diagnostics, runtime_cleanup, runtime=True)
            finally:
                diagnostics.run_outcome = "PASS" if all(
                    value == "PASS" for value in checks(diagnostics.snapshot()).values()) else "FAIL"
                try:
                    save_snapshot(diagnostics.snapshot())
                except Exception:
                    raise QAResultSaveError("QA_RESULT_SAVE_FAILED") from None
    return diagnostics
