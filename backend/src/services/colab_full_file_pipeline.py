"""Explicit full-file pipeline. No Job/UI/Drive/Output Writer or live setup.

An existing RuntimeOwnership (the PHASE 04 ownership service) lends its active
Runtime/lease. Its ColabRuntimeClient must already have GoogleAccountVerifier
configured. This controller never creates/deletes a Runtime. An optional trusted
server provisioning authorizer enables fixed remote package/model preparation.
Only the kernel, uploads and splitter temporaries created here are cleaned.
"""

import hashlib
import json
import math
import re
import threading
import uuid
from dataclasses import dataclass, replace
from pathlib import Path

from src.domain.transcription import (
    CancelRequested, CancellationToken, EngineError, ErrorCategory, StopRequested,
    SILENCE_MARKER, TranscriptionResult, validate_silence_marker,
)
from src.engines.colab import CHUNK_SECONDS, ColabRecoveryCache, DirectColabEngine, FFmpegAudioSplitter
from src.services.colab_inference_worker import MODEL_REVISION, PACKAGES
from src.services.colab_jupyter_client import _connect_ws, _http_request
from src.services.colab_jupyter_files import (
    ColabJupyterFileTransfer, RemoteOwnership, TransferCode, TransferError, TransferStatus,
)
from src.services.colab_jupyter_inference import ColabJupyterInference, InferenceCode, InferenceError, _loads
from src.services.colab_runtime_client import RuntimeClientError, RuntimeErrorCode
from src.services.colab_runtime_ownership import OwnershipState, OwnershipStore, RuntimeOwnership, _no_links


@dataclass(frozen=True)
class PipelineCleanup:
    inference: object = None
    uploads: object = None
    splitter_failed: bool = False
    cache_failed: bool = False
    inference_failed: bool = False
    uploads_failed: bool = False
    lease_failed: bool = False
    checkpoint_failed: bool = False

    @property
    def cleanup_required(self):
        return (self.splitter_failed or self.cache_failed or self.inference_failed or self.uploads_failed
                or self.lease_failed or self.checkpoint_failed
                or bool(self.inference and self.inference.cleanup_required)
                or bool(self.uploads and self.uploads.cleanup_required))


@dataclass(frozen=True)
class PipelineReport:
    status: str
    error_code: str | None
    signals: tuple
    completed_indices: tuple
    cache_used: bool
    cleanup: PipelineCleanup
    runtime_borrowed: bool = True  # ownership service, not this pipeline, owns Runtime deletion

    @property
    def local_selection_possible(self):
        return (self.status == "FAILED" and not self.cleanup.cleanup_required
                and "REMOTE_STATE_UNCERTAIN" not in self.signals)


class PipelineError(EngineError):
    def __init__(self, code, signal="COLAB_UNAVAILABLE", *, report=None):
        super().__init__(code, ErrorCategory.RUNTIME, "Colab 전사를 완료하지 못했습니다.")
        self.signal, self.report = signal, report
        self.local_fallback_allowed = bool(report and report.local_selection_possible)


class _BoundRuntime:
    """Account/record/Runtime checks remain inside the existing store transaction.

    RuntimeClient emits its durable checkpoint during GET; using its owning
    service's transaction preserves the PHASE 04 CAS contract without changes.
    """
    def __init__(self, owner):
        self.owner = owner
        self.identity = None
        self.connection = None

    def get_owned_runtime(self):
        owner = self.owner
        with owner.store.transaction():
            if owner._record is None or owner._lease is None:
                raise PipelineError("RUNTIME_NOT_OWNED", "AUTH_ACCESS_REQUIRED")
            record = owner.store._read(owner.store._path(owner._record.execution_id))
            identity = (record.execution_id, record.runtime_name, record.account_binding)
            if (record.state is not OwnershipState.ACTIVE_OWNED
                    or owner.client.verified_account_binding() != record.account_binding
                    or self.identity is not None and identity != self.identity):
                raise PipelineError("RUNTIME_BINDING_CHANGED", "AUTH_ACCESS_REQUIRED")
            runtime = owner.client.get_owned_runtime()
            if runtime.name != record.runtime_name:
                raise PipelineError("RUNTIME_BINDING_CHANGED", "AUTH_ACCESS_REQUIRED")
            info = runtime.connection_info
            connection = (info.url, info.token)
            if self.connection is not None and connection != self.connection:
                raise PipelineError("RUNTIME_BINDING_CHANGED", "AUTH_ACCESS_REQUIRED")
            self.identity, self.connection = identity, connection
            return runtime


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class ColabFullFilePipeline:
    def __init__(self, ownership: RuntimeOwnership, cache: ColabRecoveryCache, *,
                 splitter=None, http_request=_http_request, ws_connect=_connect_ws,
                 transfer_factory=ColabJupyterFileTransfer, inference_factory=ColabJupyterInference,
                 provisioning_authorizer=None, provisioning_event=lambda event: None):
        self.ownership, self.cache = ownership, cache
        self.splitter = splitter if splitter is not None else FFmpegAudioSplitter()
        self._http, self._ws = http_request, ws_connect
        self._transfer_factory, self._inference_factory = transfer_factory, inference_factory
        self._lock = threading.Lock()
        self.last_report = None
        self._provisioning_authorizer = provisioning_authorizer
        self._provisioning_event = provisioning_event
        self.provisioning_report = None

    @staticmethod
    def _checkpoint(path, execution_id, status):
        _no_links(path, must_exist=False)
        temporary = path.with_name("." + uuid.uuid4().hex + ".tmp")
        try:
            with temporary.open("x", encoding="utf-8") as handle:
                json.dump(dict(version=1, execution_id=execution_id, status=status), handle)
                handle.flush()
                import os
                os.fsync(handle.fileno())
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _check_prior(path):
        _no_links(path, must_exist=False)
        if not path.exists():
            return
        try:
            with path.open("rb") as handle:
                raw = handle.read(2049)
            if len(raw) > 2048:
                raise ValueError
            value = _loads(raw)
            if (not isinstance(value, dict) or set(value) != {"version", "execution_id", "status"}
                    or type(value["version"]) is not int or value["version"] != 1
                    or not isinstance(value["execution_id"], str)
                    or not re.fullmatch(r"[0-9a-f]{32}", value["execution_id"])
                    or value["status"] not in {"ACTIVE", "STATE_UNCERTAIN", "CLEANUP_REQUIRED",
                                               "FAILED", "STOPPED", "CANCELLED", "COMPLETED"}):
                raise ValueError
        except (ValueError, TypeError):
            raise PipelineError("PRIOR_EXECUTION_STATE_INVALID", "REMOTE_STATE_UNCERTAIN") from None
        if value["status"] in {"ACTIVE", "STATE_UNCERTAIN", "CLEANUP_REQUIRED"}:
            raise PipelineError("PRIOR_EXECUTION_UNRESOLVED", "REMOTE_STATE_UNCERTAIN")

    @staticmethod
    def _plan(chunks, source):
        if not chunks or len(chunks) > 100000:
            raise PipelineError("CHUNK_PLAN_INVALID", "INPUT_INVALID")
        paths, proof = set(), []
        for position, chunk in enumerate(chunks):
            path = Path(chunk.path).resolve(strict=True)
            if (type(chunk.index) is not int or chunk.index != position
                    or type(chunk.start_seconds) not in (int, float)
                    or type(chunk.duration_seconds) not in (int, float)
                    or not math.isfinite(chunk.start_seconds)
                    or not math.isfinite(chunk.duration_seconds)
                    or not math.isclose(chunk.start_seconds, position * CHUNK_SECONDS, abs_tol=1e-6)
                    or not 0 < chunk.duration_seconds <= CHUNK_SECONDS
                    or (position < len(chunks) - 1 and chunk.duration_seconds != CHUNK_SECONDS)
                    or path == source or path in paths or path.suffix.lower() != ".mp3"):
                raise PipelineError("CHUNK_PLAN_INVALID", "INPUT_INVALID")
            paths.add(path)
            proof.append((chunk.index, chunk.start_seconds, chunk.duration_seconds, _sha256(path)))
        return proof

    @staticmethod
    def _validate_result(result, chunk, *, cached=False):
        if (not isinstance(result, TranscriptionResult) or result.language not in ((None, "ko") if cached else ("ko",))
                or result.text != "".join(s.text for s in result.segments)
                or len(result.text.encode("utf-8")) > 12000 or len(result.segments) > 2000):
            raise PipelineError("CHUNK_RESULT_INVALID", "RESULT_INVALID")
        for segment in result.segments:
            if (not math.isfinite(segment.start) or not math.isfinite(segment.end)
                    or not 0 <= segment.start <= segment.end <= chunk.duration_seconds + 0.1
                    or not segment.text.strip() or segment.metadata):
                raise PipelineError("CHUNK_RESULT_INVALID", "RESULT_INVALID")
        validated = TranscriptionResult.from_engine_payload({
            "text": result.text, "language": "ko", "segments": [
                {"start": s.start, "end": s.end, "text": s.text} for s in result.segments]})
        if result.text == "" and result.segments == []:
            marker = result.silence_proof
            validate_silence_marker(marker, "chunk")
            if (marker["index"] != chunk.index or marker["model_revision"] != MODEL_REVISION
                    or marker["duration_seconds"] > chunk.duration_seconds + 0.1):
                raise PipelineError("CHUNK_RESULT_INVALID", "RESULT_INVALID")
            validated._set_verified_silence(marker)
        elif result.silence_proof is not None:
            raise PipelineError("CHUNK_RESULT_INVALID", "RESULT_INVALID")
        return validated

    def _load_cache(self, source, signature, chunks, proof):
        directory = self.cache._file_dir(source)
        _no_links(directory, must_exist=False)
        path = directory / "manifest.json"
        if not path.exists():
            return {}
        _no_links(path)
        try:
            with path.open("rb") as handle:
                raw = handle.read(8 * 1024 * 1024 + 1)
            if len(raw) > 8 * 1024 * 1024:
                raise ValueError
            manifest = _loads(raw)
            if (not isinstance(manifest, dict) or set(manifest) != {"fingerprint", "completed"}
                    or manifest["fingerprint"] != self.cache.source_fingerprint(source, signature)
                    or not isinstance(manifest["completed"], dict)):
                raise ValueError
            for key, payload in manifest["completed"].items():
                if (not re.fullmatch(r"0|[1-9][0-9]*", key) or int(key) >= len(chunks)
                        or not isinstance(payload, dict)
                        or set(payload) not in ({"text", "segments"}, {"text", "segments", SILENCE_MARKER})
                        or not isinstance(payload["text"], str) or not isinstance(payload["segments"], list)):
                    raise ValueError
                for row in payload["segments"]:
                    if (not isinstance(row, dict) or set(row) != {"start", "end", "text"}
                            or any(type(row[k]) not in (int, float) for k in ("start", "end"))):
                        raise ValueError
            loaded = self.cache.load(source, signature)
            for index, result in loaded.items():
                raw = manifest["completed"][str(index)]
                if SILENCE_MARKER in raw:
                    marker = raw[SILENCE_MARKER]
                    validate_silence_marker(marker, "chunk")
                    if marker["input_sha256"] != proof[index][3]:
                        raise ValueError("Cached silence input mismatch")
                    result._set_verified_silence(marker)
            return {index: self._validate_result(result, chunks[index], cached=True)
                    for index, result in loaded.items()}
        except (ValueError, TypeError, KeyError, PipelineError):
            self.cache.clear(source)
            if directory.exists():
                raise PipelineError("CACHE_CLEAR_FAILED", "CLEANUP_REQUIRED") from None
            return {}

    @staticmethod
    def _signal(error):
        code = error.code
        if isinstance(error, PipelineError):
            return error.signal
        if code in (InferenceCode.MODEL_INSTALL_REQUIRED, InferenceCode.MODEL_LOAD_FAILED,
                    InferenceCode.PROVISIONING_NOT_APPROVED, InferenceCode.PYTHON_UNSUPPORTED,
                    InferenceCode.PACKAGE_INSTALL_FAILED, InferenceCode.PACKAGE_VERSION_MISMATCH,
                    InferenceCode.PACKAGE_IMPORT_FAILED, InferenceCode.MODEL_DOWNLOAD_FAILED,
                    InferenceCode.MODEL_REVISION_MISMATCH, InferenceCode.MODEL_CACHE_INCOMPLETE):
            return "MODEL_PREPARATION_REQUIRED"
        if code in (RuntimeErrorCode.AUTH_EXPIRED, RuntimeErrorCode.ACCESS_DENIED,
                    RuntimeErrorCode.NOT_OWNED, RuntimeErrorCode.PRECONDITION_UNVERIFIED,
                    TransferCode.AUTH_REJECTED, TransferCode.TOKEN_REFRESH_REQUIRED, InferenceCode.AUTH_REJECTED):
            return "AUTH_ACCESS_REQUIRED"
        if code is RuntimeErrorCode.FREE_GPU_UNAVAILABLE:
            return "FREE_RESOURCE_UNAVAILABLE"
        if code in (RuntimeErrorCode.USAGE_LIMIT, RuntimeErrorCode.SERVICE_RESTRICTED,
                    TransferCode.POLICY_REJECTED, TransferCode.RATE_LIMITED):
            return "POLICY_USAGE_LIMIT"
        if code in (InferenceCode.POLICY_REJECTED, InferenceCode.RATE_LIMITED):
            return "POLICY_USAGE_LIMIT"
        if code in (RuntimeErrorCode.STATE_UNCERTAIN, TransferCode.STATE_UNCERTAIN,
                    InferenceCode.STATE_UNCERTAIN, InferenceCode.EXECUTION_TIMEOUT):
            return "REMOTE_STATE_UNCERTAIN"
        if code in (InferenceCode.CUDA_FAILED, InferenceCode.GPU_UNAVAILABLE):
            return "GPU_CPU_PATH"
        if code in (RuntimeErrorCode.NETWORK_TIMEOUT, RuntimeErrorCode.NETWORK_ERROR,
                    TransferCode.NETWORK_TIMEOUT, TransferCode.CONNECTION_REJECTED,
                    InferenceCode.CONNECTION_FAILED):
            return "NETWORK_ERROR"
        return "COLAB_UNAVAILABLE"

    def transcribe(self, source_path, cancellation_token: CancellationToken,
                   event_callback, progress_callback) -> TranscriptionResult:
        if not self._lock.acquire(blocking=False):
            raise PipelineError("FILE_EXECUTION_BUSY")
        token = cancellation_token
        requested = lambda: token.is_stop_requested or token.is_cancel_requested
        transfer = inference = lease = source = None
        lease_held = False
        checkpoint = None
        checkpoint_started = False
        execution_id = uuid.uuid4().hex
        completed, signals, result, error = {}, set(), None, None
        state, used_cache, clear_cache, cache_failed = "FAILED", False, False, False
        try:
            token.raise_if_requested()
            source = Path(source_path).resolve(strict=True)
            if not source.is_file() or source.suffix.lower() != ".mp3" or source.stat().st_size <= 0:
                raise PipelineError("SOURCE_INVALID", "INPUT_INVALID")
            identity = hashlib.sha256(str(source).casefold().encode("utf-8")).hexdigest()
            lease = OwnershipStore(self.cache.root / ".pipeline-locks" / identity).transaction()
            try:
                lease.__enter__()
                lease_held = True
            except RuntimeClientError:
                raise PipelineError("FILE_EXECUTION_BUSY", "FILE_EXECUTION_BUSY") from None
            checkpoint = self.cache.root / ".pipeline-locks" / identity / "attempt.json"
            self._check_prior(checkpoint)
            self._checkpoint(checkpoint, execution_id, "ACTIVE")
            checkpoint_started = True
            fingerprint = (_sha256(source), source.stat().st_size, source.stat().st_mtime_ns)
            bound = _BoundRuntime(self.ownership)
            runtime = bound.get_owned_runtime()
            self.ownership.client.get_subscription()  # FREE is not proof of zero paid-CU usage
            token.raise_if_requested()
            chunks = self.splitter.split(source, CHUNK_SECONDS, token)
            token.raise_if_requested()
            proof = self._plan(chunks, source)
            signature = "official-jupyter-v1:" + hashlib.sha256(json.dumps({
                "source_sha256": fingerprint[0], "chunks": proof, "packages": PACKAGES,
                "revision": MODEL_REVISION, "account": bound.identity[2],
                "decoding": ["ko", "transcribe", 0, 5, 5, 1.0, False],
            }, sort_keys=True).encode()).hexdigest()
            if (_sha256(source), source.stat().st_size, source.stat().st_mtime_ns) != fingerprint:
                clear_cache = True
                raise PipelineError("SOURCE_CHANGED", "INPUT_INVALID")
            completed = self._load_cache(source, signature, chunks, proof)
            used_cache = bool(completed)
            progress_callback(len(completed) / len(chunks) if len(completed) < len(chunks) else 0.0)
            if len(completed) != len(chunks):
                transfer = self._transfer_factory(
                    runtime.connection_info, http_request=self._http, cancel_requested=requested)
                inference = self._inference_factory(
                    bound, transfer, http_request=self._http, ws_connect=self._ws,
                    reuse_kernel=True, cancel_requested=requested)
                if self._provisioning_authorizer is not None:
                    from src.services.colab_model_provisioner import ColabModelProvisioner
                    def provision_event(event):
                        self._provisioning_event(event)
                        event_callback("info", "ColabProvisioning:" + event["state"], event["message"])
                    provisioner = ColabModelProvisioner(
                        inference, authorizer=self._provisioning_authorizer, emit=provision_event)
                    try:
                        self.provisioning_report = provisioner.run()
                    finally:
                        if inference.provisioning_uncertain:
                            signals.add("REMOTE_STATE_UNCERTAIN")
                readiness = inference.prepare()
                signals.add("GPU_CPU_PATH" if readiness["device"] == "cpu" else "COLAB_AVAILABLE")
                token.raise_if_requested()
                transfer.prepare()
            for chunk in chunks:
                token.raise_if_requested()
                if chunk.index in completed:
                    continue
                bound.get_owned_runtime()  # recheck exact account/Runtime before each upload
                token.raise_if_requested()
                for attempt in range(2):
                    token.raise_if_requested()
                    upload = transfer.upload(chunk.index, chunk.path)
                    if upload.status is TransferStatus.STATE_UNCERTAIN:
                        signals.add("REMOTE_STATE_UNCERTAIN")
                    token.raise_if_requested()
                    if (upload.retryable and upload.error_code in (
                            TransferCode.NETWORK_TIMEOUT, TransferCode.CONNECTION_REJECTED)
                            and not upload.remote_may_exist and attempt == 0):
                        event_callback("warning", "Colab", "전송 전 연결을 한 번 다시 확인합니다.")
                        continue
                    break
                if (upload.ownership is not RemoteOwnership.OWNED or not upload.completed
                        or not upload.all_chunks_sent or upload.chunks_acknowledged != upload.chunks_total):
                    if upload.status is TransferStatus.STATE_UNCERTAIN:
                        signals.add("REMOTE_STATE_UNCERTAIN")
                    raise PipelineError((upload.error_code or TransferCode.NOT_OWNED).value,
                                        self._signal(TransferError(upload.error_code or TransferCode.NOT_OWNED)))
                if upload.sha256 != proof[chunk.index][3]:
                    raise PipelineError("CHUNK_CHANGED", "INPUT_INVALID")
                report = inference.run(chunk.index)
                if report.execution_started and not (report.execute_reply_received and report.iopub_idle_received):
                    signals.add("REMOTE_STATE_UNCERTAIN")
                token.raise_if_requested()
                if report.status != "OK":
                    if report.status == "STATE_UNCERTAIN":
                        signals.add("REMOTE_STATE_UNCERTAIN")
                    raise InferenceError(report.error_code or InferenceCode.STATE_UNCERTAIN)
                if not report.cleanup.files_deleted or not report.cleanup.kernel_retained:
                    raise PipelineError("INFERENCE_CLEANUP_REQUIRED", "CLEANUP_REQUIRED")
                if report.gpu_error:
                    signals.add("GPU_CPU_PATH")
                completed[chunk.index] = self._validate_result(report.result, chunk)
                self.cache.save(source, signature, completed)
                if len(completed) < len(chunks):
                    progress_callback(len(completed) / len(chunks))
            token.raise_if_requested()
            if (set(completed) != set(range(len(chunks)))
                    or (_sha256(source), source.stat().st_size, source.stat().st_mtime_ns) != fingerprint):
                clear_cache = True
                raise PipelineError("SOURCE_OR_CHUNKS_CHANGED", "INPUT_INVALID")
            result = DirectColabEngine._merge(chunks, completed)
            result.metadata["colab_recovery_cache_used"] = used_cache
            state, clear_cache = "COMPLETED", True
            signals.add("COLAB_AVAILABLE")
        except (StopRequested, CancelRequested) as exc:
            error, clear_cache = exc, True
            state = "CANCELLED" if isinstance(exc, CancelRequested) else "STOPPED"
        except Exception as exc:
            error = exc if isinstance(exc, (PipelineError, RuntimeClientError, TransferError, InferenceError, EngineError)) else PipelineError("PIPELINE_FAILED")
            signals.add(self._signal(error))
        finally:
            inference_cleanup = uploads_cleanup = None
            inference_failed = uploads_failed = False
            try:
                if inference is not None:
                    inference_cleanup = inference.cleanup()
            except Exception:
                inference_failed = True
            try:
                if transfer is not None:
                    uploads_cleanup = transfer.cleanup()
            except Exception:
                uploads_failed = True
            splitter_failed = False
            try:
                self.splitter.cleanup()
            except Exception:
                splitter_failed = True
            if requested() and getattr(error, "code", None) != "FFMPEG_PROCESS_CLEANUP_FAILED":
                error = CancelRequested() if token.is_cancel_requested else StopRequested()
                state = "CANCELLED" if token.is_cancel_requested else "STOPPED"
            preliminary = PipelineCleanup(inference_cleanup, uploads_cleanup, splitter_failed,
                                          False, inference_failed, uploads_failed)
            if state == "COMPLETED" and preliminary.cleanup_required:
                clear_cache = False  # preserve verified results for an explicit FAILED retry
            if source is not None and checkpoint_started and (clear_cache or requested()):
                try:
                    self.cache.clear(source)
                    cache_failed = self.cache._file_dir(source).exists()
                except Exception:
                    cache_failed = True
            cleanup = PipelineCleanup(inference_cleanup, uploads_cleanup, splitter_failed, cache_failed,
                                      inference_failed, uploads_failed)
            if checkpoint_started:
                checkpoint_status = ("CLEANUP_REQUIRED" if cleanup.cleanup_required else
                                     "STATE_UNCERTAIN" if "REMOTE_STATE_UNCERTAIN" in signals else state)
                try:
                    self._checkpoint(checkpoint, execution_id, checkpoint_status)
                except Exception:
                    cleanup = replace(cleanup, checkpoint_failed=True)
            if cleanup.cleanup_required:
                signals.add("CLEANUP_REQUIRED")
                if state == "COMPLETED":
                    state = "FAILED"
            code = getattr(error, "code", None) or ("CLEANUP_REQUIRED" if cleanup.cleanup_required else None)
            self.last_report = PipelineReport(state, code.value if hasattr(code, "value") else code,
                                              tuple(sorted(signals)), tuple(sorted(completed)), used_cache, cleanup)
            try:
                if lease_held:
                    lease.__exit__(None, None, None)
            except Exception:
                self.last_report = replace(self.last_report, status="FAILED", error_code="CLEANUP_REQUIRED",
                    cleanup=replace(cleanup, lease_failed=True),
                    signals=tuple(sorted(signals | {"CLEANUP_REQUIRED"})))
            finally:
                self._lock.release()
        if self.last_report.cleanup.cleanup_required:
            raise PipelineError("CLEANUP_REQUIRED", "CLEANUP_REQUIRED", report=self.last_report) from None
        if error is not None:
            if isinstance(error, (StopRequested, CancelRequested)):
                raise error from None
            code = error.code.value if hasattr(error.code, "value") else error.code
            raise PipelineError(code, self._signal(error), report=self.last_report) from None
        if result.text == "" and result.segments == []:
            # All entries already carry validated live/cached chunk evidence.
            # This file-level capability is issued only AFTER every cleanup and
            # terminal checkpoint/lease operation succeeded, never on failure.
            if any(completed[i].silence_proof is None for i in range(len(chunks))):
                raise PipelineError("SILENCE_NOT_VERIFIED", "RESULT_INVALID")
            result._set_verified_silence(dict(
                version=1, scope="file", engine="official_colab", model_revision=MODEL_REVISION,
                status="complete", duration_seconds=sum(completed[i].silence_proof["duration_seconds"]
                                                       for i in range(len(chunks))),
                chunks_verified=len(chunks), source_sha256=fingerprint[0], source_size=fingerprint[1],
                cleanup_complete=True))
        progress_callback(1.0)  # only after merge and all owned cleanup succeeded
        return result
