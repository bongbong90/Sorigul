"""Single fixed Jupyter validation command; no Runtime API, files or Job wiring.

Protocol references checked 2026-11-13:
https://jupyter-client.readthedocs.io/en/stable/messaging.html
https://jupyter-server.readthedocs.io/en/latest/developers/rest-api.html
https://github.com/googlecolab/jupyter-kernel-client

Accept only PHASE 02's owned-runtime ConnectionInfo. Its ownership still lasts
only for that instance: process-loss recovery MUST be solved before live GPU
use. A lost kernel-create response is unresolved, never permission to list or
delete other kernels. This module never receives a Google REST OAuth token.
"""

import json
import logging
import math
import re
import socket
import ssl
import threading
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Callable
from urllib.parse import urlencode, urlsplit

from websockets.exceptions import InvalidStatus
from websockets.sync.client import reconnect

from src.services.colab_runtime_client import ConnectionInfo


VALIDATION_CODE = "assert 1 + 1 == 2"
MAX_MESSAGE_BYTES = 64 * 1024


class JupyterCode(str, Enum):
    INVALID_CONNECTION = "INVALID_CONNECTION"
    TOKEN_REFRESH_REQUIRED = "TOKEN_REFRESH_REQUIRED"
    AUTH_REJECTED = "AUTH_REJECTED"
    CONNECTION_REJECTED = "CONNECTION_REJECTED"
    NETWORK_TIMEOUT = "NETWORK_TIMEOUT"
    STATE_UNCERTAIN = "STATE_UNCERTAIN"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    KERNEL_CREATE_FAILED = "KERNEL_CREATE_FAILED"
    KERNEL_DELETE_FAILED = "KERNEL_DELETE_FAILED"
    CONNECTION_CLOSE_FAILED = "CONNECTION_CLOSE_FAILED"
    DUPLICATE_EXECUTION = "DUPLICATE_EXECUTION"


class JupyterClientError(Exception):
    def __init__(self, code):
        super().__init__(code.value)
        self.code = code


@dataclass(frozen=True)
class CleanupResult:
    kernel_deleted: bool
    connection_closed: bool
    cleanup_required: bool
    error_code: JupyterCode | None = None


@dataclass(frozen=True)
class ValidationResult:
    execution_status: str  # NOT_RUN / OK / ERROR / STATE_UNCERTAIN
    error_code: JupyterCode | None
    execute_reply_received: bool
    iopub_idle_received: bool
    cleanup: CleanupResult


class _NoRedirectHTTP(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _http_request(method, url, headers, body, timeout):
    """urllib has no request logging; disable proxies and all redirects."""
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), _NoRedirectHTTP(),
        urllib.request.HTTPSHandler(context=ssl.create_default_context()),
    )
    request = urllib.request.Request(
        url, data=None if body is None else json.dumps(body).encode(),
        headers=headers, method=method,
    )
    failure = None
    status, payload = None, None
    try:
        with opener.open(request, timeout=timeout) as response:
            status = response.status
            raw = response.read(MAX_MESSAGE_BYTES + 1)
            if len(raw) > MAX_MESSAGE_BYTES:
                failure = JupyterCode.STATE_UNCERTAIN
            elif raw:
                try:
                    payload = json.loads(raw)
                except (ValueError, UnicodeError):
                    failure = JupyterCode.STATE_UNCERTAIN
    except urllib.error.HTTPError as exc:
        status = exc.code
        exc.close()
    except (TimeoutError, socket.timeout):
        failure = JupyterCode.NETWORK_TIMEOUT
    except urllib.error.URLError as exc:
        failure = (JupyterCode.NETWORK_TIMEOUT if isinstance(exc.reason, TimeoutError)
                   else JupyterCode.CONNECTION_REJECTED)
    except OSError:
        failure = JupyterCode.CONNECTION_REJECTED
    # Never chain raw URL-bearing transport exceptions.
    if failure:
        raise JupyterClientError(failure)
    return status, payload


class _NoRedirectWS(reconnect):
    # websockets 17.4 connect() follows redirects, including cross-host ones.
    # Use its extension point to reject them before a second handshake.
    def process_redirect(self, exc):
        return exc


def _connect_ws(url, headers, timeout):
    # A private, disabled logger prevents raw handshake URL/header/frame logs,
    # even when application-wide DEBUG logging is enabled.
    private_logger = logging.Logger("sorigul-jupyter-wire", level=logging.CRITICAL + 1)
    private_logger.disabled = True
    connection = _NoRedirectWS(
        url, additional_headers=headers, proxy=None,
        ssl=ssl.create_default_context(), open_timeout=timeout,
        close_timeout=timeout, ping_interval=None, compression=None,
        max_size=MAX_MESSAGE_BYTES, max_queue=8, logger=private_logger,
    ).connect()  # Exactly one connection attempt; never iterate reconnect().
    # The library removes socket timeouts after handshake. Bound sendall as
    # well as its background reader; recv() also has an explicit deadline.
    connection.socket.settimeout(timeout)
    return connection


class ColabJupyterClient:
    """One validation attempt and only its POST-created kernel.

    refresh_connection is an explicit callback, for example:
      lambda: runtime_client.get_owned_runtime().connection_info
    It must refer to the SAME owned Runtime/account, never create a Runtime.
    Refresh is never automatic and may not move credentials to another origin.
    """

    def __init__(self, connection_info: ConnectionInfo, *,
                 refresh_connection: Callable[[], ConnectionInfo] | None = None,
                 http_request=_http_request, ws_connect=_connect_ws,
                 connect_timeout=5.0, execution_timeout=15.0, cleanup_timeout=5.0,
                 max_messages=256, clock=time.monotonic,
                 utcnow=lambda: datetime.now(timezone.utc)):
        if any(not math.isfinite(value) or value <= 0 for value in
               (connect_timeout, execution_timeout, cleanup_timeout)):
            raise ValueError("Timeouts must be positive and finite")
        if type(max_messages) is not int or not 1 <= max_messages <= 1024:
            raise ValueError("Invalid message bound")
        self._base_url = self._validate_info(connection_info)
        self._info = connection_info
        self._refresh = refresh_connection
        self._http_request, self._ws_connect = http_request, ws_connect
        self._connect_timeout, self._execution_timeout = connect_timeout, execution_timeout
        self._cleanup_timeout, self._max_messages = cleanup_timeout, max_messages
        self._clock, self._utcnow = clock, utcnow
        self._lock = threading.RLock()
        self._attempted = False
        self._kernel_id = None
        self._kernel_deleted = False
        self._unknown_kernel = False
        self._ws = None

    @staticmethod
    def _validate_info(info):
        valid = False
        base = None
        try:
            if not isinstance(info, ConnectionInfo):
                raise ValueError
            url = urlsplit(info.url)
            if (url.scheme != "https" or not url.hostname or url.username or url.password
                    or url.query or url.fragment or url.port not in (None, 443)
                    or not re.fullmatch(r"[A-Za-z0-9.-]+", url.hostname)
                    or not re.fullmatch(r"(?:/[A-Za-z0-9_-]+)*/?", url.path)
                    or any(ord(char) <= 32 or ord(char) >= 127 for char in info.url)):
                raise ValueError
            if not isinstance(info.token, str) or not info.token or any(
                    ord(char) < 33 or ord(char) > 126 for char in info.token):
                raise ValueError
            if not isinstance(info.expire_time, datetime) or info.expire_time.utcoffset() is None:
                raise ValueError
            base = "https://" + url.hostname + url.path.rstrip("/")
            valid = True
        except (ValueError, TypeError, AttributeError):
            pass
        if not valid:
            raise JupyterClientError(JupyterCode.INVALID_CONNECTION)
        return base

    def _fresh(self):
        if self._info.expire_time <= self._utcnow():
            raise JupyterClientError(JupyterCode.TOKEN_REFRESH_REQUIRED)

    def refresh_connection(self):
        """Caller-initiated owned-runtime lookup; never reconnect/re-execute."""
        with self._lock:
            if self._refresh is None or self._ws is not None:
                raise JupyterClientError(JupyterCode.TOKEN_REFRESH_REQUIRED)
            valid = False
            try:
                updated = self._refresh()
                valid = (self._validate_info(updated) == self._base_url
                         and updated.expire_time > self._utcnow())
            except Exception:
                pass
            if not valid:
                raise JupyterClientError(JupyterCode.TOKEN_REFRESH_REQUIRED)
            self._info = updated

    def _http(self, method, suffix, body=None, *, timeout=None):
        self._fresh()
        return self._http_request(
            method, self._base_url + suffix,
            {"X-Colab-Runtime-Proxy-Token": self._info.token,
             "Content-Type": "application/json"},
            body, timeout or self._connect_timeout,
        )

    def run_validation(self):
        with self._lock:
            if self._attempted:
                raise JupyterClientError(JupyterCode.DUPLICATE_EXECUTION)
            self._attempted = True
            state, error, reply, idle = "NOT_RUN", None, False, False
            sent = False
            try:
                self._fresh()
                self._unknown_kernel = True  # POST may succeed despite response loss.
                status, payload = self._http("POST", "/api/kernels", {"name": "python3"})
                if status != 201:
                    if status in (400, 401, 403, 404, 405, 429):
                        self._unknown_kernel = False
                    code = JupyterCode.AUTH_REJECTED if status in (401, 403) else JupyterCode.KERNEL_CREATE_FAILED
                    raise JupyterClientError(code)
                kernel = payload.get("id") if isinstance(payload, dict) else None
                if not isinstance(kernel, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", kernel):
                    raise JupyterClientError(JupyterCode.STATE_UNCERTAIN)
                self._kernel_id, self._unknown_kernel = kernel, False
                self._fresh()
                session_id, msg_id = str(uuid.uuid4()), str(uuid.uuid4())
                ws_url = ("wss://" + self._base_url[len("https://"):] +
                          f"/api/kernels/{kernel}/channels?" +
                          urlencode({"session_id": session_id, "token": self._info.token}))
                self._ws = self._ws_connect(
                    ws_url, {"X-Colab-Runtime-Proxy-Token": self._info.token},
                    min(self._connect_timeout, self._execution_timeout, self._cleanup_timeout),
                )
                self._fresh()
                deadline = self._clock() + self._execution_timeout
                request = {
                    "header": {"msg_id": msg_id, "username": "sorigul", "session": session_id,
                               "date": self._utcnow().isoformat(), "msg_type": "execute_request", "version": "5.3"},
                    "parent_header": {}, "metadata": {}, "channel": "shell",
                    "content": {"code": VALIDATION_CODE, "silent": True, "store_history": False,
                                "user_expressions": {}, "allow_stdin": False, "stop_on_error": True},
                    "buffers": [],
                }
                sent = True  # send failure may have delivered the request.
                self._ws.send(json.dumps(request))
                reply_status = None
                for _ in range(self._max_messages):
                    self._fresh()
                    remaining = deadline - self._clock()
                    if remaining <= 0:
                        raise JupyterClientError(JupyterCode.STATE_UNCERTAIN)
                    raw = self._ws.recv(timeout=remaining)
                    self._fresh()
                    if self._clock() > deadline:
                        raise JupyterClientError(JupyterCode.STATE_UNCERTAIN)
                    if not isinstance(raw, str) or len(raw.encode()) > MAX_MESSAGE_BYTES:
                        raise JupyterClientError(JupyterCode.STATE_UNCERTAIN)
                    message = json.loads(raw)
                    if not isinstance(message, dict):
                        raise JupyterClientError(JupyterCode.STATE_UNCERTAIN)
                    parent = message.get("parent_header")
                    if not isinstance(parent, dict) or parent.get("msg_id") != msg_id:
                        continue
                    header, content = message.get("header"), message.get("content")
                    if not isinstance(header, dict) or not isinstance(content, dict):
                        raise JupyterClientError(JupyterCode.STATE_UNCERTAIN)
                    kind, channel = header.get("msg_type"), message.get("channel")
                    if kind == "execute_reply" and channel == "shell":
                        if reply or content.get("status") not in ("ok", "error", "aborted"):
                            raise JupyterClientError(JupyterCode.STATE_UNCERTAIN)
                        reply, reply_status = True, content["status"]
                    elif kind == "status" and channel == "iopub" and content.get("execution_state") == "idle":
                        idle = True
                    if reply and idle:
                        state = "OK" if reply_status == "ok" else "ERROR"
                        error = None if state == "OK" else JupyterCode.EXECUTION_FAILED
                        break
                else:
                    raise JupyterClientError(JupyterCode.STATE_UNCERTAIN)
            except Exception as exc:
                # Never retain remote stdout/error text or raw transport errors.
                if isinstance(exc, JupyterClientError):
                    error = exc.code
                elif isinstance(exc, TimeoutError):
                    error = JupyterCode.STATE_UNCERTAIN if sent else JupyterCode.NETWORK_TIMEOUT
                elif isinstance(exc, InvalidStatus) and exc.response.status_code in (401, 403):
                    error = JupyterCode.AUTH_REJECTED
                else:
                    error = JupyterCode.STATE_UNCERTAIN if sent or self._unknown_kernel else JupyterCode.CONNECTION_REJECTED
                state = "STATE_UNCERTAIN" if sent or self._unknown_kernel else "NOT_RUN"
            finally:
                cleanup = self.cleanup()
            return ValidationResult(state, error, reply, idle, cleanup)

    def cleanup(self):
        """Explicit retry is allowed for cleanup only, never command execution."""
        with self._lock:
            closed = self._ws is None
            failure = JupyterCode.STATE_UNCERTAIN if self._unknown_kernel else None
            if self._ws is not None:
                try:
                    self._ws.close()
                    self._ws = None
                    closed = True
                except Exception:
                    failure = JupyterCode.CONNECTION_CLOSE_FAILED
            deleted = self._kernel_deleted
            if self._kernel_id is not None:
                try:
                    status, _ = self._http("DELETE", "/api/kernels/" + self._kernel_id,
                                           timeout=self._cleanup_timeout)
                    if status in (204, 404):
                        self._kernel_id = None
                        self._kernel_deleted = True
                        deleted = True
                    else:
                        failure = JupyterCode.KERNEL_DELETE_FAILED
                except Exception:
                    failure = JupyterCode.KERNEL_DELETE_FAILED
            required = self._unknown_kernel or self._kernel_id is not None or not closed
            return CleanupResult(deleted, closed, required, failure)
