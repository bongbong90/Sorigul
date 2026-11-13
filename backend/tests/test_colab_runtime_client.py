import json
import logging
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from src.services.colab_runtime_client import (
    API_ROOT,
    T4_STANDARD,
    ColabRuntimeClient,
    RuntimeClientError,
    RuntimeErrorCode as Code,
)


OAUTH = "mock-oauth-secret"
PROXY = "mock-proxy-secret"


class Server:
    def __init__(self):
        self.calls = []
        self.subscription = {"name": "subscription", "tier": "SUBSCRIPTION_TIER_FREE"}
        self.specs = {"runtimeSpecs": [{"key": dict(T4_STANDARD), "eligible": True}]}
        self.runtime_name = None
        self.overrides = {}
        self.pending = False

    def handle(self, request):
        self.calls.append(request)
        assert request.url.host == "colaboratory.googleapis.com"
        assert request.headers["Authorization"] == f"Bearer {OAUTH}"
        key = request.method, request.url.path
        if key in self.overrides:
            outcome = self.overrides[key]
            if isinstance(outcome, Exception):
                raise outcome
            if callable(outcome):
                return outcome(request)
            return outcome
        if key == ("GET", "/v1beta/subscription"):
            return httpx.Response(200, json=self.subscription)
        if key == ("GET", "/v1beta/runtimespecs"):
            return httpx.Response(200, json=self.specs)
        if key == ("POST", "/v1beta/runtimes"):
            self.runtime_name = "runtimes/" + request.url.params["runtimeId"]
            return httpx.Response(200, json=self.operation(not self.pending))
        if key == ("GET", "/v1/operations/mock-op"):
            return httpx.Response(200, json=self.operation(True))
        if key == ("GET", "/v1beta/" + str(self.runtime_name)):
            return httpx.Response(200, json=self.runtime())
        if key == ("DELETE", "/v1beta/" + str(self.runtime_name)):
            assert dict(request.url.params) == {"allowMissing": "true"}
            return httpx.Response(200, json={})
        raise AssertionError(f"Unexpected API call: {request.method} {request.url.path}")

    def operation(self, done):
        result = {"name": "operations/mock-op", "done": done}
        if done:
            result["response"] = {"name": self.runtime_name}
        return result

    def runtime(self):
        return {
            "name": self.runtime_name, "runtimeSpec": dict(T4_STANDARD),
            "connectionInfo": {"url": f"https://runtime.example.invalid/?token={PROXY}",
                               "token": PROXY, "expireTime": "2099-01-01T00:00:00Z"},
        }


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Live HTTP transport forbidden in PHASE 02 tests")
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", forbidden)


@pytest.fixture
def setup_client():
    server = Server()
    client = ColabRuntimeClient(OAUTH, transport=httpx.MockTransport(server.handle),
                                max_polls=2, sleep=lambda seconds: None)
    yield client, server
    client.close()


def fails(code, call):
    with pytest.raises(RuntimeClientError) as result:
        call()
    assert result.value.code == code
    assert result.value.retryable is False
    return result.value


def error_response(status, *, reason=None, grpc=None, canonical=None):
    error = {"message": f"untrusted {OAUTH} {PROXY}", "code": grpc or status}
    if canonical:
        error["status"] = canonical
    if reason:
        error["details"] = [{"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": reason}]
    return httpx.Response(status, json={"error": error})


def test_free_t4_lifecycle_and_official_request_contract(setup_client):
    client, server = setup_client
    server.pending = True
    runtime = client.create_runtime()
    assert runtime.name == server.runtime_name
    assert runtime.connection_info.token == PROXY
    assert client.cleanup_required
    post = [r for r in server.calls if r.method == "POST"]
    assert len(post) == 1
    assert uuid.UUID(post[0].url.params["requestId"]).version == 4
    assert post[0].url.params["requestId"] == client.request_id
    assert json.loads(post[0].content) == {"runtimeSpec": T4_STANDARD}
    assert str(post[0].url).startswith(API_ROOT + "/v1beta/runtimes?")
    assert client.get_owned_runtime().name == runtime.name
    client.delete_owned_runtime()
    assert not client.cleanup_required
    fails(Code.NOT_OWNED, client.get_owned_runtime)
    fails(Code.NOT_OWNED, client.delete_owned_runtime)
    fails(Code.DUPLICATE_CREATE, client.create_runtime)
    assert len([r for r in server.calls if r.method == "POST"]) == 1


@pytest.mark.parametrize("payload", [{}, [], {"name": "subscription"},
    {"name": "subscription", "tier": "SUBSCRIPTION_TIER_PRO"},
    {"name": "subscription", "tier": None},
    {"name": "other", "tier": "SUBSCRIPTION_TIER_FREE"}])
def test_invalid_or_paid_subscription_fail_closed(setup_client, payload):
    client, server = setup_client
    server.subscription = payload
    with pytest.raises(RuntimeClientError):
        client.create_runtime()
    assert [r.method for r in server.calls] == ["GET"]
    assert not client.cleanup_required


@pytest.mark.parametrize("specs", [[], [{"key": T4_STANDARD, "eligible": False}],
    [{"key": T4_STANDARD, "eligible": "true"}],
    [{"key": {**T4_STANDARD, "accelerator": "A100"}, "eligible": True}],
    [{"key": T4_STANDARD, "eligible": True}] * 2])
def test_t4_unavailable_no_alternative_allocation(setup_client, specs):
    client, server = setup_client
    server.specs = {"runtimeSpecs": specs}
    error = fails(Code.FREE_GPU_UNAVAILABLE, client.create_runtime)
    assert error.local_fallback_allowed
    assert all(r.method == "GET" for r in server.calls)


@pytest.mark.parametrize("specs", [{}, {"runtimeSpecs": None}, {"runtimeSpecs": [None]}])
def test_malformed_specs_fail_closed(setup_client, specs):
    client, server = setup_client
    server.specs = specs
    fails(Code.PRECONDITION_UNVERIFIED, client.create_runtime)
    assert all(r.method == "GET" for r in server.calls)


def test_concurrent_duplicate_create_is_blocked(setup_client):
    client, server = setup_client
    def attempt():
        try:
            return client.create_runtime()
        except RuntimeClientError as error:
            return error.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt(), range(2)))
    assert results.count(Code.DUPLICATE_CREATE) == 1
    assert len([r for r in server.calls if r.method == "POST"]) == 1


@pytest.mark.parametrize("status,reason,expected", [
    (401, None, Code.AUTH_EXPIRED), (403, None, Code.ACCESS_DENIED),
    (429, None, Code.USAGE_LIMIT), (403, "SERVICE_DISABLED", Code.SERVICE_RESTRICTED),
    (403, "POLICY_VIOLATION", Code.SERVICE_RESTRICTED),
    (400, "GPU_UNAVAILABLE", Code.FREE_GPU_UNAVAILABLE),
    (400, None, Code.CREATE_FAILED),
])
def test_definitive_create_rejection_allows_local_no_retry(setup_client, status, reason, expected):
    client, server = setup_client
    server.overrides["POST", "/v1beta/runtimes"] = error_response(status, reason=reason)
    error = fails(expected, client.create_runtime)
    assert error.local_fallback_allowed
    assert error.needs_reauthentication == (status == 401)
    assert not client.cleanup_required
    fails(Code.DUPLICATE_CREATE, client.create_runtime)
    fails(Code.NOT_OWNED, client.delete_owned_runtime)
    assert len([r for r in server.calls if r.method == "POST"]) == 1


def test_operation_error_can_be_cleaned_without_false_success(setup_client):
    client, server = setup_client
    server.pending = True
    server.overrides["GET", "/v1/operations/mock-op"] = httpx.Response(200, json={
        "name": "operations/mock-op", "done": True,
        "error": {"code": 8, "status": "RESOURCE_EXHAUSTED", "message": PROXY},
    })
    error = fails(Code.USAGE_LIMIT, client.create_runtime)
    assert error.cleanup_required and not error.local_fallback_allowed
    client.delete_owned_runtime()
    assert not client.cleanup_required


@pytest.mark.parametrize("failure,expected", [
    (httpx.ReadTimeout(f"secret {OAUTH} {PROXY}"), Code.NETWORK_TIMEOUT),
    (httpx.ConnectError(f"secret {OAUTH}"), Code.NETWORK_ERROR),
    (httpx.Response(500, json={"error": {"message": PROXY}}), Code.NETWORK_ERROR),
])
def test_ambiguous_create_failure_never_reposts_or_claims_cleanup(setup_client, failure, expected):
    client, server = setup_client
    server.overrides["POST", "/v1beta/runtimes"] = failure
    error = fails(expected, client.create_runtime)
    assert error.cleanup_required and not error.local_fallback_allowed
    fails(Code.DUPLICATE_CREATE, client.create_runtime)
    fails(Code.STATE_UNCERTAIN, client.delete_owned_runtime)
    assert len([r for r in server.calls if r.method == "POST"]) == 1
    assert not any(r.method == "DELETE" for r in server.calls)


def test_bounded_polling_then_explicit_resume_no_new_allocation(setup_client):
    client, server = setup_client
    server.pending = True
    server.overrides["GET", "/v1/operations/mock-op"] = lambda req: httpx.Response(200, json=server.operation(False))
    fails(Code.STATE_UNCERTAIN, client.create_runtime)
    assert len([r for r in server.calls if r.url.path.startswith("/v1/operations/")]) == 2
    fails(Code.STATE_UNCERTAIN, client.delete_owned_runtime)
    del server.overrides["GET", "/v1/operations/mock-op"]
    assert client.resume_operation().name == server.runtime_name
    client.delete_owned_runtime()
    assert len([r for r in server.calls if r.method == "POST"]) == 1


@pytest.mark.parametrize("status", [401, 403, 404, 429, 500])
def test_delete_failure_remains_pending_and_reports_cause(setup_client, status):
    client, server = setup_client
    client.create_runtime()
    server.overrides["DELETE", "/v1beta/" + server.runtime_name] = error_response(status)
    error = fails(Code.DELETE_FAILED, client.delete_owned_runtime)
    assert error.cause_code is not None
    assert error.cleanup_required and client.cleanup_required
    assert not error.local_fallback_allowed
    del server.overrides["DELETE", "/v1beta/" + server.runtime_name]
    client.delete_owned_runtime()  # Explicit cleanup retry; no allocation retry.
    assert not client.cleanup_required


def test_tokens_absent_from_repr_logs_and_traceback(setup_client, caplog):
    client, server = setup_client
    with caplog.at_level(logging.DEBUG):
        runtime = client.create_runtime()
        displayed = repr(runtime) + repr(runtime.connection_info) + repr(client)
        server.overrides["GET", "/v1beta/" + server.runtime_name] = error_response(403)
        error = fails(Code.ACCESS_DENIED, client.get_owned_runtime)
        displayed += repr(error) + str(vars(error)) + "".join(traceback.format_exception(error))
    assert OAUTH not in displayed + caplog.text
    assert PROXY not in displayed + caplog.text


def test_transport_exception_does_not_chain_secret(setup_client):
    client, server = setup_client
    server.overrides["GET", "/v1beta/subscription"] = httpx.ReadTimeout(OAUTH + PROXY)
    error = fails(Code.NETWORK_TIMEOUT, client.create_runtime)
    assert error.__context__ is None
    assert OAUTH not in "".join(traceback.format_exception(error))


@pytest.mark.parametrize("field,value", [("name", "runtimes/someone-else"),
    ("runtimeSpec", {**T4_STANDARD, "accelerator": "A100"}),
    ("connectionInfo", {"url": "http://bad.invalid", "token": PROXY, "expireTime": "2099-01-01T00:00:00Z"}),
    ("connectionInfo", {"url": "https://good.invalid", "token": PROXY, "expireTime": "2000-01-01T00:00:00Z"})])
def test_invalid_runtime_identity_or_connection_never_ready(setup_client, field, value):
    client, server = setup_client
    server.pending = True
    def response(req):
        server.overrides["GET", "/v1beta/" + server.runtime_name] = lambda r: httpx.Response(200, json={**server.runtime(), field: value})
        return httpx.Response(200, json=server.operation(True))
    server.overrides["GET", "/v1/operations/mock-op"] = response
    fails(Code.STATE_UNCERTAIN, client.create_runtime)
    client.delete_owned_runtime()
    deletes = [r.url.path for r in server.calls if r.method == "DELETE"]
    assert deletes == ["/v1beta/" + server.runtime_name]


def test_operation_url_injection_and_redirect_not_followed(setup_client):
    client, server = setup_client
    server.overrides["POST", "/v1beta/runtimes"] = httpx.Response(200, json={
        "name": "operations/../../billing?token=" + PROXY,
    })
    fails(Code.STATE_UNCERTAIN, client.create_runtime)
    assert len(server.calls) == 3


def test_redirect_does_not_send_oauth_to_another_host(setup_client):
    client, server = setup_client
    server.overrides["GET", "/v1beta/subscription"] = httpx.Response(
        302, headers={"Location": "https://attacker.invalid/"})
    with pytest.raises(RuntimeClientError):
        client.create_runtime()
    assert len(server.calls) == 1


def test_existing_runtime_cannot_be_adopted_or_deleted(setup_client):
    client, server = setup_client
    fails(Code.NOT_OWNED, client.get_owned_runtime)
    fails(Code.NOT_OWNED, client.delete_owned_runtime)
    assert server.calls == []


def test_operation_id_collision_never_deletes_preexisting_assignment(setup_client):
    client, server = setup_client
    server.pending = True
    server.overrides["GET", "/v1/operations/mock-op"] = httpx.Response(200, json={
        "name": "operations/mock-op", "done": True,
        "error": {"code": 6, "status": "ALREADY_EXISTS"},
    })
    error = fails(Code.CREATE_FAILED, client.create_runtime)
    assert error.cause_code == Code.NOT_OWNED
    assert not client.cleanup_required
    fails(Code.NOT_OWNED, client.delete_owned_runtime)
    assert not any(r.method == "DELETE" for r in server.calls)


@pytest.mark.parametrize("payload", [None, [], {"name": "operations/mock-op", "done": "true"},
    {"name": "operations/mock-op", "done": True, "response": {}, "error": {}},
    {"name": "operations/mock-op", "done": True}])
def test_malformed_create_response_never_assumed_ready(setup_client, payload):
    client, server = setup_client
    server.overrides["POST", "/v1beta/runtimes"] = httpx.Response(200, json=payload)
    error = fails(Code.STATE_UNCERTAIN, client.create_runtime)
    assert error.cleanup_required
    fails(Code.DUPLICATE_CREATE, client.create_runtime)
    assert len(server.calls) == 3


def test_delete_timeout_keeps_cleanup_obligation(setup_client):
    client, server = setup_client
    client.create_runtime()
    server.overrides["DELETE", "/v1beta/" + server.runtime_name] = httpx.ReadTimeout(PROXY)
    error = fails(Code.DELETE_FAILED, client.delete_owned_runtime)
    assert error.cause_code == Code.NETWORK_TIMEOUT
    assert client.cleanup_required
    assert PROXY not in "".join(traceback.format_exception(error))


def test_close_does_not_claim_runtime_was_deleted(setup_client):
    client, server = setup_client
    client.create_runtime()
    client.close()
    assert client.cleanup_required
    assert not any(r.method == "DELETE" for r in server.calls)


def test_operation_precondition_refusal_not_bypassed(setup_client):
    client, server = setup_client
    server.pending = True
    server.overrides["GET", "/v1/operations/mock-op"] = httpx.Response(200, json={
        "name": "operations/mock-op", "done": True,
        "error": {"code": 9, "status": "FAILED_PRECONDITION"},
    })
    error = fails(Code.SERVICE_RESTRICTED, client.create_runtime)
    assert error.cleanup_required
    fails(Code.DUPLICATE_CREATE, client.create_runtime)
    client.delete_owned_runtime()
    assert len([r for r in server.calls if r.method == "POST"]) == 1


def test_poll_auth_expiry_preserves_operation_for_explicit_resume(setup_client):
    client, server = setup_client
    server.pending = True
    server.overrides["GET", "/v1/operations/mock-op"] = error_response(401)
    error = fails(Code.AUTH_EXPIRED, client.create_runtime)
    assert error.needs_reauthentication and error.cleanup_required
    fails(Code.STATE_UNCERTAIN, client.delete_owned_runtime)
    del server.overrides["GET", "/v1/operations/mock-op"]
    client.resume_operation()
    client.delete_owned_runtime()
    assert len([r for r in server.calls if r.method == "POST"]) == 1


def test_nonempty_delete_response_not_reported_as_success(setup_client):
    client, server = setup_client
    client.create_runtime()
    server.overrides["DELETE", "/v1beta/" + server.runtime_name] = httpx.Response(
        200, json={"token": PROXY})
    error = fails(Code.DELETE_FAILED, client.delete_owned_runtime)
    assert client.cleanup_required
    assert PROXY not in repr(error)
