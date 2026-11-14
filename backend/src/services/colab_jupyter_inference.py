"""Trusted worker: one-shot default, opt-in file-scoped kernel reuse.

Uses PHASE 03 HTTPS/WSS transports and owned-kernel cleanup unchanged. No
arbitrary execute API, Runtime create/delete, token logging or automatic retry.
Caller supplies the existing owned Runtime client and file transfer instance.
Process-loss recovery and lost kernel-create receipts remain unresolved.
"""

import ast
import base64
import json
import math
import re
import threading
import time
import uuid
import weakref
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from urllib.parse import urlencode

from src.domain.transcription import TranscriptionResult
from src.services.colab_inference_worker import (
    MAX_RESULT_BYTES, MODEL_REVISION, build_preparation_code, build_worker_code,
)
from src.services.colab_jupyter_client import (
    MAX_MESSAGE_BYTES, CleanupResult, ColabJupyterClient, _connect_ws, _http_request,
)
from src.services.colab_jupyter_files import RemoteOwnership, TransferError, TransferStatus


class InferenceCode(str, Enum):
    INVALID_INPUT = "INVALID_INPUT"
    INPUT_NOT_OWNED = "INPUT_NOT_OWNED"
    INPUT_MISSING = "INPUT_MISSING"
    INPUT_INTEGRITY_MISMATCH = "INPUT_INTEGRITY_MISMATCH"
    CONNECTION_FAILED = "CONNECTION_FAILED"
    AUTH_REJECTED = "AUTH_REJECTED"
    POLICY_REJECTED = "POLICY_REJECTED"
    RATE_LIMITED = "RATE_LIMITED"
    KERNEL_CREATE_FAILED = "KERNEL_CREATE_FAILED"
    KERNEL_EXECUTION_FAILED = "KERNEL_EXECUTION_FAILED"
    MODEL_INSTALL_REQUIRED = "MODEL_INSTALL_REQUIRED"
    MODEL_LOAD_FAILED = "MODEL_LOAD_FAILED"
    GPU_UNAVAILABLE = "GPU_UNAVAILABLE"
    CUDA_FAILED = "CUDA_FAILED"
    EXECUTION_TIMEOUT = "EXECUTION_TIMEOUT"
    STATE_UNCERTAIN = "STATE_UNCERTAIN"
    CANCELLED = "CANCELLED"
    DUPLICATE_EXECUTION = "DUPLICATE_EXECUTION"
    RESULT_INVALID = "RESULT_INVALID"
    RESULT_DOWNLOAD_FAILED = "RESULT_DOWNLOAD_FAILED"
    FILE_CLEANUP_FAILED = "FILE_CLEANUP_FAILED"


class InferenceError(Exception):
    def __init__(self, code):
        super().__init__(code.value)
        self.code = code


@dataclass(frozen=True)
class InferenceCleanup:
    kernel: CleanupResult
    files_deleted: bool
    cleanup_required: bool
    error_code: InferenceCode | None = None
    kernel_retained: bool = False


@dataclass(frozen=True)
class InferenceReport:
    status: str  # OK / NOT_RUN / ERROR / CANCELLED / STATE_UNCERTAIN
    error_code: InferenceCode | None
    execution_id: str
    execution_started: bool
    execute_reply_received: bool
    iopub_idle_received: bool
    cleanup: InferenceCleanup
    result: TranscriptionResult | None = field(default=None, repr=False)
    device: str | None = None
    compute_type: str | None = None
    gpu_error: InferenceCode | None = None
    silence: bool = False

    @property
    def local_fallback_possible(self):
        # Signal only. The upper Job layer owns any Local decision.
        return self.status == "ERROR" and self.error_code in {
            InferenceCode.MODEL_INSTALL_REQUIRED, InferenceCode.MODEL_LOAD_FAILED,
            InferenceCode.GPU_UNAVAILABLE, InferenceCode.CUDA_FAILED,
        }


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("RESULT_INVALID")
        value[key] = item
    return value


def _loads(raw):
    def reject_constant(_):
        raise ValueError("RESULT_INVALID")
    return json.loads(raw, object_pairs_hook=_unique_object, parse_constant=reject_constant)


class ColabJupyterInference:
    # A second adapter around the same transfer cannot repeat an attempted index.
    # This in-memory guard deliberately makes no process-recovery claim.
    _claims = weakref.WeakKeyDictionary()
    _claims_lock = threading.Lock()

    def __init__(self, runtime_client, transfer, *, http_request=_http_request,
                 ws_connect=_connect_ws, execution_timeout=1800.0,
                 connect_timeout=10.0, cleanup_timeout=10.0,
                 allow_model_download=False, clock=time.monotonic,
                 utcnow=lambda: datetime.now(timezone.utc), reuse_kernel=False,
                 cancel_requested=lambda: False):
        for value in (execution_timeout, connect_timeout, cleanup_timeout):
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value) or not 0 < value <= 3600):
                raise ValueError("Invalid finite timeout")
        if type(allow_model_download) is not bool:
            raise ValueError("Invalid model download option")
        if type(reuse_kernel) is not bool:
            raise ValueError("Invalid kernel reuse option")
        self._runtime, self._transfer = runtime_client, transfer
        self._http_request, self._ws_connect = http_request, ws_connect
        self._execution_timeout = execution_timeout
        self._connect_timeout, self._cleanup_timeout = connect_timeout, cleanup_timeout
        self._allow_download, self._clock, self._utcnow = allow_model_download, clock, utcnow
        self._lock, self._cancel = threading.RLock(), threading.Event()
        self._attempted = self._sent = self._output_owned = self._output_uncertain = False
        self._client = None
        self.execution_id = uuid.uuid4().hex
        self._output_dir = self._output_path = None
        self._reuse_kernel, self._cancel_requested = reuse_kernel, cancel_requested
        self._closed = self._prepared = False
        self._runtime_name = None
        self._session_id = uuid.uuid4().hex

    def cancel(self):
        self._cancel.set()  # bounded recv polls; only our kernel is deleted

    def _check_cancel(self):
        if self._cancel.is_set() or self._cancel_requested():
            raise InferenceError(InferenceCode.CANCELLED)

    def run(self, index):
        with self._lock:
            if self._closed or (self._attempted and not self._reuse_kernel):
                raise InferenceError(InferenceCode.DUPLICATE_EXECUTION)
            if self._attempted:
                self.execution_id = uuid.uuid4().hex
            self._attempted = True
            self._sent = False
            self._reply = self._idle = False
            state, error, reply, idle = "NOT_RUN", None, False, False
            result, device, compute, gpu_error, silence = None, None, None, None, False
            try:
                self._check_cancel()
                try:
                    path = self._transfer.remote_path_for(index)
                except TransferError:
                    raise InferenceError(InferenceCode.INVALID_INPUT) from None
                records = {r.index: r for r in self._transfer.records()}
                record = records.get(index)
                if (record is None or record.ownership is not RemoteOwnership.OWNED
                        or record.remote_deleted):
                    raise InferenceError(InferenceCode.INPUT_NOT_OWNED)
                if (record.status not in (TransferStatus.ACKNOWLEDGED, TransferStatus.VERIFIED)
                        or not record.all_chunks_sent or record.chunks_acknowledged != record.chunks_total
                        or record.chunks_total < 1 or record.remote_path != path):
                    raise InferenceError(InferenceCode.INVALID_INPUT)
                owned = self._runtime.get_owned_runtime()  # read-only, never create
                if not self._transfer.matches_connection(owned.connection_info):
                    raise InferenceError(InferenceCode.CONNECTION_FAILED)
                if self._runtime_name is not None and owned.name != self._runtime_name:
                    raise InferenceError(InferenceCode.CONNECTION_FAILED)
                if self._client is None:
                    self._client = ColabJupyterClient(
                        owned.connection_info, http_request=self._http_request,
                        ws_connect=self._ws_connect, connect_timeout=self._connect_timeout,
                        cleanup_timeout=self._cleanup_timeout, utcnow=self._utcnow,
                    )
                    self._runtime_name = owned.name
                self._check_input(path, record)
                code = build_worker_code(
                    run_id=self._transfer.run_id, execution_id=self.execution_id,
                    index=index, size=record.size, sha256=record.sha256,
                    allow_model_download=self._allow_download,
                )
                self._output_dir = self._transfer.run_dir + "/inference-" + self.execution_id
                self._output_path = self._output_dir + "/result.json"
                with self._claims_lock:
                    claimed = self._claims.setdefault(self._transfer, set())
                    if index in claimed:
                        raise InferenceError(InferenceCode.DUPLICATE_EXECUTION)
                    claimed.add(index)
                self._check_cancel()
                client = self._client
                self._ensure_kernel()
                reply, idle = self._execute(code)
                self._check_cancel()
                envelope = self._download(record)
                self._check_cancel()
                if envelope["error_code"] is not None:
                    raise InferenceError(InferenceCode(envelope["error_code"]))
                result = TranscriptionResult.from_engine_payload(envelope["payload"])
                device, compute = envelope["device"], envelope["compute_type"]
                gpu_error = InferenceCode(envelope["gpu_error"]) if envelope["gpu_error"] else None
                silence, state = envelope["silence"], "OK"
                if silence:
                    result._set_verified_silence(dict(
                        version=1, scope="chunk", engine="official_colab", model_revision=MODEL_REVISION,
                        status="verified", duration_seconds=envelope["duration_seconds"],
                        index=index, input_sha256=record.sha256))
            except Exception as exc:
                # No raw exception, traceback, stream or transcript is retained.
                unknown_kernel = self._client is not None and self._client._unknown_kernel
                error = exc.code if isinstance(exc, InferenceError) else (
                    InferenceCode.STATE_UNCERTAIN if self._sent or unknown_kernel
                    else InferenceCode.CONNECTION_FAILED)
                reply = getattr(self, "_reply", reply)
                idle = getattr(self, "_idle", idle)
                if error is InferenceCode.CANCELLED:
                    state = "CANCELLED"
                elif (error is InferenceCode.STATE_UNCERTAIN or unknown_kernel
                      or (self._sent and not (reply and idle))):
                    state = "STATE_UNCERTAIN"
                else:
                    state = "ERROR" if self._sent else "NOT_RUN"
            if self._reuse_kernel and state == "OK":
                cleanup = self._cleanup_files(CleanupResult(False, False, True), retained=True)
                if not cleanup.files_deleted:
                    cleanup = self.cleanup()
            else:
                cleanup = self.cleanup()
            return InferenceReport(state, error, self.execution_id, self._sent, reply, idle,
                                   cleanup, result, device, compute, gpu_error, silence)

    def _ensure_kernel(self):
        self._check_cancel()
        client = self._client
        if client._kernel_id is not None:
            return
        client._unknown_kernel = True
        status, model = client._http("POST", "/api/kernels", {"name": "python3"})
        if status != 201:
            if status in (400, 401, 403, 404, 405, 429):
                client._unknown_kernel = False
            self._check_http_status(status)
            raise InferenceError(InferenceCode.KERNEL_CREATE_FAILED)
        kernel = model.get("id") if isinstance(model, dict) else None
        if not isinstance(kernel, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", kernel):
            raise InferenceError(InferenceCode.STATE_UNCERTAIN)
        client._kernel_id, client._unknown_kernel = kernel, False
        client._fresh()
        self._check_cancel()
        ws_url = ("wss://" + client._base_url[len("https://"):] +
                  f"/api/kernels/{kernel}/channels?" +
                  urlencode({"session_id": self._session_id, "token": client._info.token}))
        client._ws = client._ws_connect(
            ws_url, {"X-Colab-Runtime-Proxy-Token": client._info.token},
            min(self._connect_timeout, self._cleanup_timeout))

    def _execute(self, code, *, preparation=False):
        self._check_cancel()
        self._client._fresh()
        msg_id, session = uuid.uuid4().hex, self._session_id
        deadline = self._clock() + self._execution_timeout
        message = {
            "header": {"msg_id": msg_id, "session": session, "username": "sorigul",
                       "date": self._utcnow().isoformat(), "msg_type": "execute_request", "version": "5.3"},
            "parent_header": {}, "metadata": {}, "channel": "shell", "buffers": [],
            "content": {"code": code, "silent": True, "store_history": False,
                        "allow_stdin": False, "stop_on_error": True,
                        "user_expressions": {"receipt": "__import__('json').dumps(_sorigul_receipt)"}},
        }
        self._sent = True
        self._output_uncertain = not preparation
        self._client._ws.send(json.dumps(message))
        return self._wait(msg_id, deadline, preparation=preparation)

    def prepare(self):
        """Fixed read-only package/cache/revision/device check on the shared kernel.

        No install, model download or decode. Failures close this session and
        require explicit caller handling, never retry the command automatically.
        """
        with self._lock:
            if not self._reuse_kernel or self._prepared or self._attempted or self._closed:
                raise InferenceError(InferenceCode.DUPLICATE_EXECUTION)
            self._prepared = True
            try:
                self._check_cancel()
                owned = self._runtime.get_owned_runtime()
                if not self._transfer.matches_connection(owned.connection_info):
                    raise InferenceError(InferenceCode.CONNECTION_FAILED)
                self._runtime_name = owned.name
                self._client = ColabJupyterClient(
                    owned.connection_info, http_request=self._http_request,
                    ws_connect=self._ws_connect, connect_timeout=self._connect_timeout,
                    cleanup_timeout=self._cleanup_timeout, utcnow=self._utcnow)
                self._ensure_kernel()
                self._execute(build_preparation_code(self.execution_id), preparation=True)
                self._check_cancel()
                return dict(self._readiness)
            except Exception as exc:
                self.cleanup()
                if isinstance(exc, InferenceError):
                    raise InferenceError(exc.code) from None
                raise InferenceError(InferenceCode.STATE_UNCERTAIN if self._sent
                                     else InferenceCode.CONNECTION_FAILED) from None
            finally:
                self.execution_id = uuid.uuid4().hex

    def _check_input(self, path, record):
        suffix = "/api/contents/" + path
        status, model = self._client._http("GET", suffix + "?content=0&hash=1")
        if status in (400, 405, 501):  # hash option unsupported; Worker hashes read-only
            status, model = self._client._http("GET", suffix + "?content=0")
        self._check_http_status(status)
        if status == 404:
            raise InferenceError(InferenceCode.INPUT_MISSING)
        if (status != 200 or not isinstance(model, dict) or model.get("path") != path
                or model.get("type") != "file" or type(model.get("size")) is not int):
            raise InferenceError(InferenceCode.INVALID_INPUT)
        if model["size"] != record.size:
            raise InferenceError(InferenceCode.INPUT_INTEGRITY_MISMATCH)
        if model.get("hash_algorithm") == "sha256" and model.get("hash") != record.sha256:
            raise InferenceError(InferenceCode.INPUT_INTEGRITY_MISMATCH)

    @staticmethod
    def _check_http_status(status):
        if status in (401, 403):
            raise InferenceError(InferenceCode.AUTH_REJECTED)
        if status == 413:
            raise InferenceError(InferenceCode.POLICY_REJECTED)
        if status == 429:
            raise InferenceError(InferenceCode.RATE_LIMITED)

    def _wait(self, msg_id, deadline, *, preparation=False):
        self._reply = self._idle = False
        reply_status, receipt = None, None
        # Both time and message count bound streams that never become idle.
        for _ in range(10000):
            self._check_cancel()
            self._client._fresh()
            remaining = deadline - self._clock()
            if remaining <= 0:
                raise InferenceError(InferenceCode.EXECUTION_TIMEOUT)
            try:
                raw = self._client._ws.recv(timeout=min(remaining, 0.5))
            except TimeoutError:
                continue
            if self._clock() > deadline:
                raise InferenceError(InferenceCode.EXECUTION_TIMEOUT)
            if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_MESSAGE_BYTES:
                raise InferenceError(InferenceCode.STATE_UNCERTAIN)
            message = _loads(raw)
            if not isinstance(message, dict):
                raise InferenceError(InferenceCode.STATE_UNCERTAIN)
            if message.get("parent_header", {}).get("msg_id") != msg_id:
                continue
            kind, content, channel = message.get("header", {}).get("msg_type"), message.get("content"), message.get("channel")
            if not isinstance(content, dict):
                raise InferenceError(InferenceCode.STATE_UNCERTAIN)
            if kind == "execute_reply" and channel == "shell":
                if self._reply or content.get("status") not in ("ok", "error", "aborted"):
                    raise InferenceError(InferenceCode.STATE_UNCERTAIN)
                self._reply, reply_status = True, content["status"]
                if reply_status == "ok":
                    expression = content.get("user_expressions", {}).get("receipt", {})
                    if expression.get("status") == "ok":
                        receipt = _loads(ast.literal_eval(expression["data"]["text/plain"]))
            elif kind == "status" and channel == "iopub" and content.get("execution_state") == "idle":
                self._idle = True
            # Stream/error/display messages are discarded, never logged.
            if self._reply and self._idle:
                if reply_status != "ok":
                    raise InferenceError(InferenceCode.KERNEL_EXECUTION_FAILED)
                if preparation:
                    if (not isinstance(receipt, dict) or set(receipt) != {
                            "execution_id", "ready", "error_code", "device", "compute_type", "revision"}
                            or receipt["execution_id"] != self.execution_id
                            or receipt["revision"] != MODEL_REVISION or type(receipt["ready"]) is not bool):
                        raise InferenceError(InferenceCode.STATE_UNCERTAIN)
                    if not receipt["ready"]:
                        if receipt["error_code"] not in ("MODEL_INSTALL_REQUIRED", "MODEL_LOAD_FAILED"):
                            raise InferenceError(InferenceCode.STATE_UNCERTAIN)
                        raise InferenceError(InferenceCode(receipt["error_code"]))
                    if (receipt["error_code"] is not None or
                            (receipt["device"], receipt["compute_type"]) not in (("cuda", "float16"), ("cpu", "int8"))):
                        raise InferenceError(InferenceCode.STATE_UNCERTAIN)
                    self._readiness = receipt
                    return True, True
                if (not isinstance(receipt, dict) or set(receipt) != {"execution_id", "owned"}
                        or receipt["execution_id"] != self.execution_id or receipt["owned"] is not True):
                    raise InferenceError(InferenceCode.STATE_UNCERTAIN)
                self._output_owned, self._output_uncertain = True, False
                return True, True
        raise InferenceError(InferenceCode.STATE_UNCERTAIN)

    def _download(self, record):
        try:
            status, model = self._client._http(
                "GET", "/api/contents/" + self._output_path + "?content=1&format=base64")
        except Exception:
            raise InferenceError(InferenceCode.RESULT_DOWNLOAD_FAILED) from None
        self._check_http_status(status)
        if status != 200:
            raise InferenceError(InferenceCode.RESULT_DOWNLOAD_FAILED)
        try:
            if (not isinstance(model, dict) or model.get("path") != self._output_path
                    or model.get("type") != "file" or model.get("format") != "base64"
                    or not isinstance(model.get("content"), str)
                    or len(model["content"]) > 4 * ((MAX_RESULT_BYTES + 2) // 3)):
                raise ValueError
            raw = base64.b64decode(model["content"], validate=True)
            if len(raw) > MAX_RESULT_BYTES:
                raise ValueError
            value = _loads(raw.decode("utf-8"))
            keys = {"execution_id", "run_id", "index", "input_sha256", "complete", "error_code",
                    "device", "compute_type", "gpu_error", "silence", "payload", "duration_seconds"}
            if (not isinstance(value, dict) or set(value) != keys or value["complete"] is not True
                    or value["execution_id"] != self.execution_id or value["run_id"] != self._transfer.run_id
                    or type(value["index"]) is not int or value["index"] != record.index
                    or value["input_sha256"] != record.sha256 or type(value["silence"]) is not bool):
                raise ValueError
            if value["error_code"] is not None:
                allowed = {"INPUT_MISSING", "INPUT_INTEGRITY_MISMATCH", "MODEL_INSTALL_REQUIRED",
                           "MODEL_LOAD_FAILED", "CUDA_FAILED", "KERNEL_EXECUTION_FAILED", "RESULT_INVALID"}
                if value["error_code"] not in allowed or value["payload"] is not None:
                    raise ValueError
                return value
            if ((value["device"], value["compute_type"]) not in (("cuda", "float16"), ("cpu", "int8"))
                    or value["gpu_error"] not in (None, "GPU_UNAVAILABLE", "CUDA_FAILED")
                    or type(value["duration_seconds"]) not in (int, float)
                    or not math.isfinite(value["duration_seconds"])
                    or not 0 < value["duration_seconds"] <= 301):
                raise ValueError
            payload = value["payload"]
            if (not isinstance(payload, dict) or set(payload) != {"text", "language", "segments"}
                    or payload["language"] != "ko" or not isinstance(payload["text"], str)
                    or not isinstance(payload["segments"], list) or len(payload["segments"]) > 2000):
                raise ValueError
            for segment in payload["segments"]:
                if (not isinstance(segment, dict) or set(segment) != {"start", "end", "text"}
                        or any(type(segment[k]) not in (int, float) or not math.isfinite(segment[k])
                               for k in ("start", "end"))
                        or not 0 <= segment["start"] <= segment["end"] <= 301
                        or not isinstance(segment["text"], str) or not segment["text"].strip()):
                    raise ValueError
            if (payload["text"] != "".join(s["text"] for s in payload["segments"])
                    or value["silence"] != (not payload["segments"])):
                raise ValueError
            TranscriptionResult.from_engine_payload(payload)
            return value
        except Exception:
            raise InferenceError(InferenceCode.RESULT_INVALID) from None

    def cleanup(self):
        with self._lock:
            self._closed = True
            kernel = self._client.cleanup() if self._client else CleanupResult(False, True, False)
            return self._cleanup_files(kernel)

    def _cleanup_files(self, kernel, *, retained=False):
        files_deleted, error = not self._output_uncertain and not self._output_owned, None
        if self._output_owned:
            try:
                status, _ = self._client._http("DELETE", "/api/contents/" + self._output_path,
                                               timeout=self._cleanup_timeout)
                if status not in (204, 404):
                    raise ValueError
                status, model = self._client._http(
                    "GET", "/api/contents/" + self._output_dir + "?content=1",
                    timeout=self._cleanup_timeout)
                if status != 404:
                    if (status != 200 or not isinstance(model, dict)
                            or model.get("path") != self._output_dir
                            or model.get("type") != "directory" or model.get("content") != []):
                        raise ValueError
                    status, _ = self._client._http("DELETE", "/api/contents/" + self._output_dir,
                                                   timeout=self._cleanup_timeout)
                    if status not in (204, 404):
                        raise ValueError
                self._output_owned, files_deleted = False, True
            except Exception:
                error = InferenceCode.FILE_CLEANUP_FAILED
        required = kernel.cleanup_required or not files_deleted
        return InferenceCleanup(kernel, files_deleted, required, error, retained)
