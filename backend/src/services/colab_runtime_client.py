"""Consumer Colab lifecycle only; no OAuth flow, Jupyter, Drive or Job wiring.

One instance represents one user-authorized attempt, bound to one Google account.
The caller supplies that account's access token; never reuse this instance for
another account. FREE/eligible are NOT proof of zero paid-CU consumption. There
is no invented freeOnly flag. Live use still needs a separate approval gate.

Contract checked 2026-11-13:
https://developers.google.com/colab/api/reference/rest/v1beta/runtimes
https://developers.google.com/colab/api/reference/rest/v1beta/runtimes/create
https://developers.google.com/colab/api/reference/rest/v1/operations/get
https://colaboratory.googleapis.com/$discovery/rest?version=v1beta
"""

import math
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Callable
from urllib.parse import urlsplit

import httpx


API_ROOT = "https://colaboratory.googleapis.com"
T4_STANDARD = {"variant": "VARIANT_GPU", "accelerator": "T4", "shape": "SHAPE_STANDARD"}


class RuntimeErrorCode(str, Enum):
    FREE_GPU_UNAVAILABLE = "COLAB_FREE_GPU_UNAVAILABLE"
    USAGE_LIMIT = "COLAB_USAGE_LIMIT"
    ACCESS_DENIED = "COLAB_ACCESS_DENIED"
    AUTH_EXPIRED = "COLAB_AUTH_EXPIRED"
    CREATE_FAILED = "COLAB_RUNTIME_CREATE_FAILED"
    NETWORK_TIMEOUT = "COLAB_NETWORK_TIMEOUT"
    NETWORK_ERROR = "COLAB_NETWORK_ERROR"
    STATE_UNCERTAIN = "COLAB_RUNTIME_STATE_UNCERTAIN"
    DELETE_FAILED = "COLAB_RUNTIME_DELETE_FAILED"
    SERVICE_RESTRICTED = "COLAB_SERVICE_RESTRICTED"
    PRECONDITION_UNVERIFIED = "COLAB_PRECONDITION_UNVERIFIED"
    DUPLICATE_CREATE = "COLAB_DUPLICATE_CREATE_BLOCKED"
    NOT_OWNED = "COLAB_RUNTIME_NOT_OWNED"


class RuntimeClientError(Exception):
    """Safe to log: no remote message, URL, token or arbitrary ErrorInfo text.

    A Job layer may consider Local only when local_fallback_allowed is true;
    it must resolve cleanup_required first. This module never changes engines.
    """

    def __init__(self, code: RuntimeErrorCode, *, cause_code=None, http_status=None,
                 cleanup_required=False):
        super().__init__(code.value)
        self.code = code
        self.cause_code = cause_code
        self.http_status = http_status
        self.cleanup_required = cleanup_required
        self.needs_reauthentication = (cause_code or code) == RuntimeErrorCode.AUTH_EXPIRED
        self.local_fallback_allowed = not cleanup_required and code not in {
            RuntimeErrorCode.DUPLICATE_CREATE, RuntimeErrorCode.NOT_OWNED,
        }
        self.retryable = False


@dataclass(frozen=True)
class ConnectionInfo:
    url: str = field(repr=False)
    token: str = field(repr=False)
    expire_time: datetime


@dataclass(frozen=True)
class OwnedRuntime:
    name: str
    connection_info: ConnectionInfo = field(repr=False)


class ColabRuntimeClient:
    """At most one POST, even after failure/delete or concurrent duplicate calls.

    This low-level client doesn't persist itself. RuntimeOwnership supplies
    durable checkpoints and verified-account recovery. Keep this object until
    cleanup is confirmed. Only its generated runtimeId is managed;
    arbitrary runtime names and existing account runtimes cannot be deleted.
    If the POST response is lost before an operation name is received, cleanup
    remains unresolved; the caller must surface that state, not create again
    or claim deletion. Known pending operations can be explicitly resumed.
    """

    def __init__(self, access_token: str, *, transport=None, timeout_seconds=10.0,
                 max_polls=30, poll_interval_seconds=1.0,
                 sleep: Callable[[float], None] = time.sleep,
                 account_verifier: Callable[[str], str | None] | None = None):
        if not isinstance(access_token, str) or not access_token.strip() or any(
            ord(char) < 33 or ord(char) > 126 for char in access_token
        ):
            raise RuntimeClientError(RuntimeErrorCode.AUTH_EXPIRED)
        if (not math.isfinite(timeout_seconds) or timeout_seconds <= 0
                or not math.isfinite(poll_interval_seconds) or poll_interval_seconds <= 0
                or type(max_polls) is not int or not 1 <= max_polls <= 120):
            raise ValueError("Invalid bounded request/poll configuration")
        self._http = httpx.Client(
            headers={"Authorization": f"Bearer {access_token}"},
            transport=transport, timeout=timeout_seconds, follow_redirects=False,
            trust_env=False,
        )
        self._max_polls = max_polls
        self._interval = poll_interval_seconds
        self._sleep = sleep
        self._lock = threading.RLock()
        self._attempted = False
        self._runtime_name = None
        self._operation_name = None
        self._pending_operation = False
        self._cleanup_required = False
        self._request_id = str(uuid.uuid4())
        self._candidate_name = f"runtimes/sorigul-{uuid.uuid4().hex}"
        self._account_verifier = account_verifier
        self._account_binding = None
        self._checkpoint = None

    @property
    def cleanup_required(self):
        return self._cleanup_required

    @property
    def request_id(self):
        return self._request_id

    @property
    def candidate_runtime_name(self):
        return self._candidate_name

    @property
    def creation_available(self):
        with self._lock:
            return not self._attempted

    def verified_account_binding(self):
        """Trusted adapter must verify issuer/subject for THIS access token and
        return its SHA256 fingerprint (never email/token). No verifier is
        supplied by default; a user-entered account label is not verification.
        This method does not implement an OAuth flow or call Google itself.
        """
        binding = None
        if self._account_verifier is not None:
            try:
                binding = self._account_verifier(self._http.headers["Authorization"][7:])
            except Exception:
                pass
        if not isinstance(binding, str) or not re.fullmatch(r"[0-9a-f]{64}", binding):
            raise RuntimeClientError(RuntimeErrorCode.PRECONDITION_UNVERIFIED,
                                     cleanup_required=self._cleanup_required)
        return binding

    def _emit_checkpoint(self, phase):
        if self._checkpoint is not None:
            # Strictly identifiers/status only: never pass a raw API response.
            self._checkpoint(phase, self._operation_name)

    def close(self):
        """Close HTTP only. Never claim remote cleanup merely on local close."""
        self._http.close()

    @staticmethod
    def _classify(error, http_status=None):
        # Only structured, recognized codes are inspected. Never keep messages,
        # arbitrary reasons, metadata or error bodies on public exceptions.
        status = error.get("status")
        grpc = error.get("code")
        details = error.get("details", [])
        reasons = {
            item.get("reason") for item in details
            if isinstance(item, dict)
            and item.get("@type") == "type.googleapis.com/google.rpc.ErrorInfo"
            and isinstance(item.get("reason"), str)
        } if isinstance(details, list) else set()
        if http_status == 401 or status == "UNAUTHENTICATED" or grpc == 16:
            return RuntimeErrorCode.AUTH_EXPIRED
        if reasons & {"POLICY_VIOLATION", "SERVICE_DISABLED", "ACCOUNT_RESTRICTED"}:
            return RuntimeErrorCode.SERVICE_RESTRICTED
        if reasons & {"GPU_UNAVAILABLE", "ACCELERATOR_UNAVAILABLE", "NO_AVAILABLE_RESOURCES"}:
            return RuntimeErrorCode.FREE_GPU_UNAVAILABLE
        if http_status == 429 or status == "RESOURCE_EXHAUSTED" or grpc == 8:
            return RuntimeErrorCode.USAGE_LIMIT
        if http_status == 403 or status == "PERMISSION_DENIED" or grpc == 7:
            return RuntimeErrorCode.ACCESS_DENIED
        if status == "FAILED_PRECONDITION" or grpc == 9:
            return RuntimeErrorCode.SERVICE_RESTRICTED
        if http_status is not None and 500 <= http_status <= 599:
            return RuntimeErrorCode.NETWORK_ERROR
        return RuntimeErrorCode.CREATE_FAILED

    def _request(self, method, path, *, body=None, params=None):
        # All call sites use constant API paths or validated operation/owned IDs.
        if self._account_binding is not None and self.verified_account_binding() != self._account_binding:
            raise RuntimeClientError(RuntimeErrorCode.NOT_OWNED,
                                     cleanup_required=self._cleanup_required)
        code = None
        payload = None
        status = None
        try:
            response = self._http.request(method, API_ROOT + path, json=body, params=params)
            status = response.status_code
            try:
                payload = response.json()
            except ValueError:
                pass
            if not 200 <= status < 300:
                error = payload.get("error", {}) if isinstance(payload, dict) else {}
                code = self._classify(error if isinstance(error, dict) else {}, status)
                if code == RuntimeErrorCode.CREATE_FAILED and method != "POST":
                    code = RuntimeErrorCode.STATE_UNCERTAIN
            elif not isinstance(payload, dict):
                code = RuntimeErrorCode.STATE_UNCERTAIN
        except httpx.TimeoutException:
            code = RuntimeErrorCode.NETWORK_TIMEOUT
        except httpx.HTTPError:
            code = RuntimeErrorCode.NETWORK_ERROR
        # Raise outside handlers, so raw httpx exceptions/headers are not chained.
        if code is not None:
            raise RuntimeClientError(code, http_status=status,
                                     cleanup_required=self._cleanup_required)
        return payload

    def get_subscription(self):
        payload = self._request("GET", "/v1beta/subscription")
        if payload.get("name") != "subscription" or payload.get("tier") != "SUBSCRIPTION_TIER_FREE":
            raise RuntimeClientError(RuntimeErrorCode.PRECONDITION_UNVERIFIED,
                                     cleanup_required=self._cleanup_required)
        return "SUBSCRIPTION_TIER_FREE"

    def list_runtime_specs(self):
        """Read specs without exposing arbitrary remote metadata in results."""
        payload = self._request("GET", "/v1beta/runtimespecs")
        specs = payload.get("runtimeSpecs")
        if not isinstance(specs, list) or any(not isinstance(item, dict) for item in specs):
            raise RuntimeClientError(RuntimeErrorCode.PRECONDITION_UNVERIFIED,
                                     cleanup_required=self._cleanup_required)
        # Return a copy of only the documented fields; never retain raw bodies.
        return [{"key": item.get("key"), "eligible": item.get("eligible", False)} for item in specs]

    def check_t4_eligibility(self):
        specs = self.list_runtime_specs()
        matches = [item for item in specs if item.get("key") == T4_STANDARD]
        if len(matches) != 1 or matches[0].get("eligible") is not True:
            raise RuntimeClientError(RuntimeErrorCode.FREE_GPU_UNAVAILABLE,
                                     cleanup_required=self._cleanup_required)
        return dict(T4_STANDARD)

    def create_runtime(self, *, checkpoint=None, account_binding=None):
        with self._lock:
            if self._attempted:
                raise RuntimeClientError(RuntimeErrorCode.DUPLICATE_CREATE,
                                         cleanup_required=self._cleanup_required)
            self._attempted = True
            if checkpoint is not None:
                if account_binding is None or self.verified_account_binding() != account_binding:
                    raise RuntimeClientError(RuntimeErrorCode.NOT_OWNED)
                self._account_binding, self._checkpoint = account_binding, checkpoint
            self.get_subscription()
            spec = self.check_t4_eligibility()
            self._emit_checkpoint("CREATE_STARTED")  # Durable before POST.
            # Own only our random, client-specified ID, never a name from a list.
            # Set before POST: a timeout may still have created this resource.
            self._runtime_name = self._candidate_name
            self._cleanup_required = True
            self._pending_operation = True
            try:
                operation = self._request(
                    "POST", "/v1beta/runtimes", body={"runtimeSpec": spec},
                    params={"requestId": self._request_id,
                            "runtimeId": self._runtime_name.split("/")[1]},
                )
            except RuntimeClientError as exc:
                if exc.http_status in {400, 401, 403, 404, 409, 429}:
                    # Definitive rejection, including collisions: do not delete
                    # an existing assignment that this attempt did not create.
                    self._pending_operation = False
                    self._cleanup_required = False
                    self._runtime_name = None
                    self._emit_checkpoint("CREATE_REJECTED")
                    raise RuntimeClientError(exc.code, http_status=exc.http_status) from None
                raise
            return self._finish_operation(operation)

    def _finish_operation(self, operation):
        name = operation.get("name")
        if not isinstance(name, str) or not re.fullmatch(r"operations/[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*", name):
            raise RuntimeClientError(RuntimeErrorCode.STATE_UNCERTAIN, cleanup_required=True)
        if self._operation_name is not None and name != self._operation_name:
            raise RuntimeClientError(RuntimeErrorCode.STATE_UNCERTAIN, cleanup_required=True)
        self._operation_name = name
        for poll in range(self._max_polls + 1):
            self._emit_checkpoint("OPERATION_OBSERVED")
            done = operation.get("done", False)
            if type(done) is not bool or (not done and ("error" in operation or "response" in operation)):
                break
            if done:
                if "error" in operation and "response" not in operation and isinstance(operation["error"], dict):
                    self._pending_operation = False
                    if (operation["error"].get("code") == 6
                            or operation["error"].get("status") == "ALREADY_EXISTS"):
                        self._runtime_name = None
                        self._cleanup_required = False
                        self._emit_checkpoint("CREATE_REJECTED")
                        raise RuntimeClientError(RuntimeErrorCode.CREATE_FAILED,
                                                 cause_code=RuntimeErrorCode.NOT_OWNED)
                    # Failure can be ambiguous; keep cleanup obligation until a
                    # successful DELETE or a definitive not-found verification.
                    raise RuntimeClientError(self._classify(operation["error"]), cleanup_required=True)
                response = operation.get("response")
                if "error" in operation or not isinstance(response, dict) or response.get("name") != self._runtime_name:
                    break
                self._pending_operation = False
                return self.get_owned_runtime()
            if poll == self._max_polls:
                break
            self._sleep(self._interval)
            operation = self._request("GET", "/v1/" + name)
            if operation.get("name") != name:
                break
        raise RuntimeClientError(RuntimeErrorCode.STATE_UNCERTAIN, cleanup_required=True)

    def resume_operation(self):
        """Explicit bounded reconciliation; never issues another create POST."""
        with self._lock:
            if not self._pending_operation or self._operation_name is None:
                raise RuntimeClientError(RuntimeErrorCode.STATE_UNCERTAIN,
                                         cleanup_required=self._cleanup_required)
            return self._finish_operation(self._request("GET", "/v1/" + self._operation_name))

    def get_owned_runtime(self):
        with self._lock:
            return self._get_owned_runtime()

    def _get_owned_runtime(self):
        if self._runtime_name is None:
            raise RuntimeClientError(RuntimeErrorCode.NOT_OWNED)
        payload = self._request("GET", "/v1beta/" + self._runtime_name)
        connection = payload.get("connectionInfo")
        try:
            if payload.get("name") != self._runtime_name or payload.get("runtimeSpec") != T4_STANDARD:
                raise ValueError
            if not isinstance(connection, dict):
                raise ValueError
            url, token = connection.get("url"), connection.get("token")
            if not isinstance(url, str) or not isinstance(token, str) or not token:
                raise ValueError
            parsed = urlsplit(url)
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
                raise ValueError
            expiry = datetime.fromisoformat(connection["expireTime"].replace("Z", "+00:00"))
            if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
                raise ValueError
        except (ValueError, TypeError, KeyError, AttributeError):
            raise RuntimeClientError(RuntimeErrorCode.STATE_UNCERTAIN, cleanup_required=True) from None
        self._emit_checkpoint("RUNTIME_CONFIRMED")
        return OwnedRuntime(self._runtime_name, ConnectionInfo(url, token, expiry))

    def recover_attempt(self, *, request_id, runtime_name, operation_name,
                        account_binding, checkpoint):
        """Reconcile ONE persisted attempt through its Operation, never POST.
        No operation evidence means no adoption. The coordinator validates
        durable records and must hold its storage lock for this whole call.
        """
        with self._lock:
            if self._attempted:
                raise RuntimeClientError(RuntimeErrorCode.DUPLICATE_CREATE)
            try:
                valid = (str(uuid.UUID(request_id, version=4)) == request_id
                         and uuid.UUID(request_id).version == 4
                         and re.fullmatch(r"runtimes/sorigul-[0-9a-f]{32}", runtime_name)
                         and re.fullmatch(r"operations/[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*", operation_name))
            except (ValueError, TypeError, AttributeError):
                valid = False
            if not valid or self.verified_account_binding() != account_binding:
                raise RuntimeClientError(RuntimeErrorCode.NOT_OWNED, cleanup_required=True)
            self._attempted = True
            self._request_id, self._candidate_name = request_id, runtime_name
            self._runtime_name, self._operation_name = runtime_name, operation_name
            self._account_binding, self._checkpoint = account_binding, checkpoint
            self._pending_operation = self._cleanup_required = True
            try:
                return self._finish_operation(self._request("GET", "/v1/" + operation_name))
            except RuntimeClientError as exc:
                # A matching, completed create Operation was confirmed BEFORE
                # this exact Runtime GET reported absence. An Operation 404 is
                # not absence proof and never reaches this branch.
                if exc.http_status != 404 or self._pending_operation:
                    raise
                self._emit_checkpoint("ABSENCE_CONFIRMED")
                self._cleanup_required = False
                self._runtime_name = None
                return None

    def delete_owned_runtime(self):
        with self._lock:
            if self._runtime_name is None:
                raise RuntimeClientError(RuntimeErrorCode.NOT_OWNED)
            # Do not delete a still-pending assignment: it might appear AFTER a
            # successful DELETE. Reconcile known operations first, never guess.
            if self._pending_operation:
                raise RuntimeClientError(RuntimeErrorCode.STATE_UNCERTAIN, cleanup_required=True)
            failure = None
            failure_status = None
            try:
                payload = self._request("DELETE", "/v1beta/" + self._runtime_name,
                                        params={"allowMissing": "true"})
                if payload != {}:
                    failure = RuntimeErrorCode.STATE_UNCERTAIN
            except RuntimeClientError as exc:
                failure = exc.code
                failure_status = exc.http_status
            if failure is not None:
                raise RuntimeClientError(RuntimeErrorCode.DELETE_FAILED, cause_code=failure,
                                         http_status=failure_status, cleanup_required=True)
            self._cleanup_required = False
            self._runtime_name = None
            self._emit_checkpoint("DELETED")
