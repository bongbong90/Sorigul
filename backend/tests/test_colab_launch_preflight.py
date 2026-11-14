import hashlib
import io
import json
import logging
import socket
import urllib.error
from email.message import Message

import httpx
import pytest

from src.services import colab_launch_preflight as module
from src.services.colab_account_verifier import GOOGLE_ISSUER, GOOGLE_USERINFO_ENDPOINT
from src.services.colab_launch_preflight import (
    CheckStatus, CostGate, LaunchApproval, PolicyGate, PreflightLabel as L, T4Status, TierStatus,
    SCOPE_COLAB, SCOPE_COLAB_READONLY, run_launch_preflight,
)
from src.services.colab_runtime_client import T4_STANDARD


TOKEN = "mock-preflight-oauth-secret"
SUBJECT = "MockPreflightSubject-42"
EMAIL = "preflight-person@example.invalid"
BINDING = hashlib.sha256((GOOGLE_ISSUER + "\0" + SUBJECT).encode()).hexdigest()
OTHER_BINDING = hashlib.sha256((GOOGLE_ISSUER + "\0other").encode()).hexdigest()
FULL_SCOPES = ["openid", "https://www.googleapis.com/auth/userinfo.profile", SCOPE_COLAB]


@pytest.fixture(autouse=True)
def block_external_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("External network is forbidden in preflight tests")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)


class UserInfoResponse:
    def __init__(self, payload):
        self.status = 200
        self.headers = Message()
        self.headers["Content-Type"] = "application/json"
        self.raw = json.dumps(payload).encode()

    def geturl(self):
        return GOOGLE_USERINFO_ENDPOINT

    def read(self, limit):
        return self.raw[:limit]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def http_error(status, www_authenticate=None):
    headers = Message()
    if www_authenticate:
        headers["WWW-Authenticate"] = www_authenticate
    return urllib.error.HTTPError(GOOGLE_USERINFO_ENDPOINT, status, "denied", headers,
                                  io.BytesIO(json.dumps({"error": EMAIL}).encode()))


class UserInfo:
    def __init__(self, outcome=None):
        self.outcome = outcome if outcome is not None else {
            "sub": SUBJECT, "email": EMAIL, "name": "Private Person"}
        self.calls = []

    def open(self, request, *, timeout):
        self.calls.append(request)
        assert request.full_url == GOOGLE_USERINFO_ENDPOINT
        assert request.get_header("Authorization") == "Bearer " + TOKEN
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return UserInfoResponse(self.outcome)


class Colab:
    def __init__(self):
        self.calls = []
        self.subscription = httpx.Response(200, json={"name": "subscription", "tier": "SUBSCRIPTION_TIER_FREE"})
        self.specs = httpx.Response(200, json={"runtimeSpecs": [
            {"key": {"variant": "VARIANT_CPU", "accelerator": "NONE", "shape": "SHAPE_STANDARD"}, "eligible": True},
            {"key": dict(T4_STANDARD), "eligible": True}]})

    def handle(self, request):
        self.calls.append((request.method, request.url.path))
        assert request.headers["Authorization"] == "Bearer " + TOKEN
        outcome = {"/v1beta/subscription": self.subscription,
                   "/v1beta/runtimespecs": self.specs}[request.url.path]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    @property
    def transport(self):
        return httpx.MockTransport(self.handle)


def run(userinfo=None, colab=None, **kwargs):
    userinfo = userinfo or UserInfo()
    colab = colab or Colab()
    kwargs.setdefault("network_approved", True)
    kwargs.setdefault("granted_scopes", FULL_SCOPES)
    result = run_launch_preflight(TOKEN, colab_transport=colab.transport,
                                  userinfo_opener=userinfo, **kwargs)
    return result, userinfo, colab


def assert_no_mutation(colab):
    assert all(method == "GET" for method, _ in colab.calls)
    assert {path for _, path in colab.calls} <= {"/v1beta/subscription", "/v1beta/runtimespecs"}


def assert_blocked(result):
    assert result.launch_approval is LaunchApproval.BLOCKED
    assert result.cost_gate is CostGate.CONDITIONAL
    assert result.policy_gate is PolicyGate.NOT_VERIFIED
    assert "COST_GATE_CONDITIONAL" in result.launch_blocking_reasons
    assert "POLICY_GATE_NOT_VERIFIED" in result.launch_blocking_reasons


# 1, 5, 7, 11: everything technical passes, launch stays BLOCKED.
def test_same_account_full_scope_free_t4_passes_technical_but_launch_blocked():
    result, userinfo, colab = run(expected_account_binding=BINDING)
    assert result.identity is CheckStatus.VERIFIED
    assert result.colab_access is CheckStatus.VERIFIED
    assert result.tier is TierStatus.FREE
    assert result.t4 is T4Status.ELIGIBLE
    assert result.launch_scope is CheckStatus.VERIFIED
    assert result.ownership_preconditions is CheckStatus.VERIFIED
    assert result.technical_precheck_passed and result.technical_blocking_reasons == ()
    assert result.launch_blocking_reasons == ("COST_GATE_CONDITIONAL", "POLICY_GATE_NOT_VERIFIED")
    assert result.paid_cu_non_consumption_evidence == "NO_SUPPORTED_API"
    assert_blocked(result)
    assert result.labels == (L.IDENTITY_VERIFIED, L.COLAB_ACCESS_VERIFIED, L.FREE_TIER_VERIFIED,
                             L.T4_ELIGIBLE, L.COST_GATE_CONDITIONAL, L.POLICY_GATE_NOT_VERIFIED)
    assert result.account_binding == BINDING
    assert len(userinfo.calls) == 1
    assert colab.calls == [("GET", "/v1beta/subscription"), ("GET", "/v1beta/runtimespecs")]
    assert result.remote_requests == 3


def test_gates_have_no_verified_member_so_go_is_unreachable():
    assert [g.value for g in CostGate] == ["COST_GATE_CONDITIONAL"]
    assert [g.value for g in PolicyGate] == ["POLICY_GATE_NOT_VERIFIED"]
    assert module._VERIFIED_COST_GATES == frozenset() and module._VERIFIED_POLICY_GATES == frozenset()


def test_unbound_first_check_verifies_identity_from_google():
    result, _, _ = run()
    assert result.identity is CheckStatus.VERIFIED and result.account_binding == BINDING
    assert_blocked(result)


# 2: scope insufficient, declared and remote.
@pytest.mark.parametrize("scopes, identity, colab_status, launch", [
    ([SCOPE_COLAB], CheckStatus.AUTH_SCOPE_REQUIRED, CheckStatus.VERIFIED, CheckStatus.VERIFIED),
    (["openid"], CheckStatus.VERIFIED, CheckStatus.AUTH_SCOPE_REQUIRED, CheckStatus.AUTH_SCOPE_REQUIRED),
    # readonly suffices for the preflight GETs but never for a later create.
    ("openid " + SCOPE_COLAB_READONLY, CheckStatus.VERIFIED, CheckStatus.VERIFIED,
     CheckStatus.AUTH_SCOPE_REQUIRED),
])
def test_declared_scope_gaps_downgrade_only(scopes, identity, colab_status, launch):
    result, userinfo, colab = run(granted_scopes=scopes)
    assert result.identity is identity and result.colab_access is colab_status
    assert result.launch_scope is launch
    assert L.AUTH_SCOPE_REQUIRED in result.labels
    assert L.TECHNICAL_PRECHECK_BLOCKED in result.labels
    assert len(userinfo.calls) == (0 if identity is CheckStatus.AUTH_SCOPE_REQUIRED else 1)
    assert_no_mutation(colab)
    assert_blocked(result)


def test_unknown_declared_scopes_never_upgrade_launch_scope():
    result, _, _ = run(granted_scopes=None)
    assert result.launch_scope is CheckStatus.NOT_VERIFIED
    assert "LAUNCH_SCOPE_NOT_VERIFIED" in result.technical_blocking_reasons
    assert_blocked(result)


def test_remote_userinfo_insufficient_scope_header():
    result, _, _ = run(UserInfo(http_error(403, 'Bearer error="insufficient_scope"')))
    assert result.identity is CheckStatus.AUTH_SCOPE_REQUIRED
    assert result.account_binding is None
    assert_blocked(result)


def test_remote_colab_insufficient_scope_header_and_errorinfo():
    for response in (
        httpx.Response(403, headers={"WWW-Authenticate": 'Bearer error="insufficient_scope"'},
                       json={"error": {"code": 403, "status": "PERMISSION_DENIED"}}),
        httpx.Response(403, json={"error": {"code": 403, "status": "PERMISSION_DENIED", "details": [
            {"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": "ACCESS_TOKEN_SCOPE_INSUFFICIENT"}]}}),
    ):
        colab = Colab()
        colab.subscription = response
        result, _, _ = run(colab=colab)
        assert result.colab_access is CheckStatus.AUTH_SCOPE_REQUIRED
        assert result.tier is TierStatus.UNKNOWN and result.t4 is T4Status.NOT_RUN
        assert_blocked(result)


# 3: expired token distinguished from scope/denial.
def test_expired_userinfo_stops_before_colab():
    result, _, colab = run(UserInfo(http_error(401, 'Bearer error="invalid_token"')))
    assert result.identity is CheckStatus.AUTH_EXPIRED
    assert result.colab_access is CheckStatus.NOT_RUN and colab.calls == []
    assert_blocked(result)


def test_expired_colab_and_access_denied_are_distinct():
    colab = Colab()
    colab.subscription = httpx.Response(401, json={"error": {"code": 401, "status": "UNAUTHENTICATED"}})
    assert run(colab=colab)[0].colab_access is CheckStatus.AUTH_EXPIRED
    colab = Colab()
    colab.subscription = httpx.Response(403, json={"error": {"code": 403, "status": "PERMISSION_DENIED"}})
    assert run(colab=colab)[0].colab_access is CheckStatus.ACCESS_DENIED
    assert run(UserInfo(http_error(403)))[0].identity is CheckStatus.ACCESS_DENIED


def test_invalid_token_makes_no_requests():
    result = run_launch_preflight("bad token", network_approved=True,
                                  colab_transport=Colab().transport, userinfo_opener=UserInfo())
    assert result.identity is CheckStatus.AUTH_EXPIRED and result.remote_requests == 0
    assert_blocked(result)


# 4: different account.
def test_different_account_stops_before_colab_and_drops_binding():
    result, _, colab = run(expected_account_binding=OTHER_BINDING)
    assert result.identity is CheckStatus.ACCOUNT_MISMATCH
    assert result.account_binding is None and colab.calls == []
    assert result.ownership_preconditions is CheckStatus.NOT_VERIFIED
    assert_blocked(result)


def test_malformed_expected_binding_makes_no_requests():
    result, userinfo, colab = run(expected_account_binding="not-a-fingerprint")
    assert "EXPECTED_BINDING_INVALID" in result.technical_blocking_reasons
    assert userinfo.calls == [] and colab.calls == [] and result.remote_requests == 0


# 6: paid tiers.
@pytest.mark.parametrize("tier", ["SUBSCRIPTION_TIER_PRO", "SUBSCRIPTION_TIER_PRO_PLUS"])
def test_paid_tier_blocks_and_skips_spec_read(tier):
    colab = Colab()
    colab.subscription = httpx.Response(200, json={"name": "subscription", "tier": tier})
    result, _, _ = run(colab=colab)
    assert result.colab_access is CheckStatus.VERIFIED
    assert result.tier is TierStatus.PAID and result.t4 is T4Status.NOT_RUN
    assert "TIER_PAID" in result.technical_blocking_reasons
    assert colab.calls == [("GET", "/v1beta/subscription")]
    assert_blocked(result)


# 8: T4 unsupported / unknown.
@pytest.mark.parametrize("specs, expected", [
    ({"runtimeSpecs": [{"key": dict(T4_STANDARD), "eligible": False}]}, T4Status.NOT_ELIGIBLE),
    # proto3 JSON omits false booleans; RuntimeClient already reads absent as False.
    ({"runtimeSpecs": [{"key": dict(T4_STANDARD)}]}, T4Status.NOT_ELIGIBLE),
    ({"runtimeSpecs": []}, T4Status.NOT_ELIGIBLE),
    ({"runtimeSpecs": [{"key": {**T4_STANDARD, "shape": "SHAPE_HIGHMEM"}, "eligible": True}]}, T4Status.NOT_ELIGIBLE),
    ({"runtimeSpecs": [{"key": dict(T4_STANDARD), "eligible": "true"}]}, T4Status.UNKNOWN),
    ({"runtimeSpecs": [{"key": dict(T4_STANDARD), "eligible": True}] * 2}, T4Status.UNKNOWN),
    ({"runtimeSpecs": "corrupt"}, T4Status.UNKNOWN),
    ({}, T4Status.UNKNOWN),
])
def test_t4_not_eligible_or_unknown_blocks(specs, expected):
    colab = Colab()
    colab.specs = httpx.Response(200, json=specs)
    result, _, _ = run(colab=colab)
    assert result.tier is TierStatus.FREE and result.t4 is expected
    assert L.T4_ELIGIBLE not in result.labels and L.TECHNICAL_PRECHECK_BLOCKED in result.labels
    assert_no_mutation(colab)
    assert_blocked(result)


# 9: network errors.
def test_network_errors_fail_closed():
    result, _, colab = run(UserInfo(urllib.error.URLError("dns failure for " + EMAIL)))
    assert result.identity is CheckStatus.NETWORK_ERROR and colab.calls == []
    colab = Colab()
    colab.subscription = httpx.ConnectError("refused")
    assert run(colab=colab)[0].colab_access is CheckStatus.NETWORK_ERROR
    colab = Colab()
    colab.specs = httpx.ReadTimeout("slow")
    result = run(colab=colab)[0]
    assert result.t4 is T4Status.UNKNOWN and "RUNTIME_SPECS_UNREADABLE" in result.technical_blocking_reasons
    assert_blocked(result)


# 10: corrupted responses.
@pytest.mark.parametrize("response", [
    httpx.Response(200, content=b"not json"),
    httpx.Response(200, json=["list"]),
    httpx.Response(200, json={"name": "other", "tier": "SUBSCRIPTION_TIER_FREE"}),
    httpx.Response(200, json={"name": "subscription", "tier": "SUBSCRIPTION_TIER_UNSPECIFIED"}),
    httpx.Response(200, json={"name": "subscription"}),
    httpx.Response(500, json={"error": {"code": 500}}),
])
def test_corrupt_subscription_never_counts_as_free(response):
    colab = Colab()
    colab.subscription = response
    result, _, _ = run(colab=colab)
    assert result.tier is not TierStatus.FREE and L.FREE_TIER_VERIFIED not in result.labels
    assert result.t4 is T4Status.NOT_RUN
    assert_blocked(result)


@pytest.mark.parametrize("payload", [{}, {"sub": ""}, {"sub": SUBJECT, "iss": "https://evil.invalid"}])
def test_corrupt_userinfo_is_not_identity(payload):
    result, _, _ = run(UserInfo(payload))
    assert result.identity is CheckStatus.RESPONSE_INVALID and result.account_binding is None
    assert_blocked(result)


# 12, 13: no mutation, no unapproved network, guard refuses everything else.
def test_network_not_approved_issues_zero_requests():
    for approval in (False, None, "yes", 1):
        result, userinfo, colab = run(network_approved=approval)
        assert userinfo.calls == [] and colab.calls == [] and result.remote_requests == 0
        assert "NETWORK_NOT_APPROVED" in result.technical_blocking_reasons
        assert_blocked(result)


def test_drive_token_is_refused_locally():
    result, userinfo, colab = run(granted_scopes=FULL_SCOPES + ["https://www.googleapis.com/auth/drive.file"])
    assert result.identity is CheckStatus.DRIVE_TOKEN_REFUSED
    assert userinfo.calls == [] and colab.calls == []
    assert_blocked(result)


@pytest.mark.parametrize("method, url", [
    ("POST", "https://colaboratory.googleapis.com/v1beta/runtimes"),
    ("DELETE", "https://colaboratory.googleapis.com/v1beta/runtimes/sorigul-x"),
    ("GET", "https://colaboratory.googleapis.com/v1beta/runtimes"),
    ("GET", "https://colaboratory.googleapis.com/tun/m/ccu-info"),
    ("GET", "https://colab.research.google.com/v1beta/subscription"),
    ("GET", "https://colaboratory.googleapis.com/v1beta/subscription?x=1"),
    ("PUT", "https://runtime.example.invalid/api/contents/a.mp3"),
])
def test_read_only_guard_refuses_every_other_request(method, url):
    inner = Colab()
    guard = module._ReadOnlyColabTransport(inner.transport)
    with pytest.raises(module._GuardViolation):
        guard.handle_request(httpx.Request(method, url))
    assert inner.calls == [] and guard.requests == 0 and guard.violation


def test_create_path_is_never_reached_even_if_client_tried(monkeypatch):
    def try_create(self, *args, **kwargs):
        return self._request("POST", "/v1beta/runtimes", body={"runtimeSpec": dict(T4_STANDARD)})
    monkeypatch.setattr(module.ColabRuntimeClient, "list_runtime_specs", try_create)
    result, _, colab = run()
    assert "READ_ONLY_GUARD_VIOLATION" in result.technical_blocking_reasons
    assert_no_mutation(colab)
    assert_blocked(result)


@pytest.mark.parametrize("name", ["create_runtime", "delete_owned_runtime", "resume_operation",
                                  "recover_attempt", "get_owned_runtime", "check_t4_eligibility"])
def test_uncertain_states_never_invoke_lifecycle_methods(monkeypatch, name):
    def forbidden(*args, **kwargs):
        raise AssertionError(name + " must not be called by preflight")
    monkeypatch.setattr(module.ColabRuntimeClient, name, forbidden)
    for colab_case in ("ok", "paid", "uncertain"):
        colab = Colab()
        if colab_case == "paid":
            colab.subscription = httpx.Response(200, json={"name": "subscription", "tier": "SUBSCRIPTION_TIER_PRO"})
        if colab_case == "uncertain":
            colab.specs = httpx.Response(200, json={"runtimeSpecs": [{"key": dict(T4_STANDARD)}]})
        result, _, _ = run(colab=colab)
        assert "PREFLIGHT_INTERNAL_ERROR" not in result.technical_blocking_reasons
        assert_blocked(result)


def test_module_has_no_jupyter_upload_model_or_gpu_dependencies():
    source = open(module.__file__, encoding="utf-8").read()
    for forbidden in ("colab_jupyter", "faster_whisper", "websocket", "/api/contents",
                      "/api/kernels", "ccu-info\"", "drive"):
        if forbidden == "drive":
            assert "import drive" not in source and "services.drive" not in source
        else:
            assert forbidden not in source.split('"""', 2)[2]


# 14: secrets and PII never surface.
def test_token_subject_email_never_in_result_repr_dict_or_logs(caplog):
    caplog.set_level(logging.DEBUG)
    results = [run(expected_account_binding=BINDING)[0],
               run(UserInfo(http_error(401)))[0],
               run(UserInfo(urllib.error.URLError(EMAIL + TOKEN)))[0]]
    colab = Colab()
    colab.subscription = httpx.Response(403, json={"error": {"message": EMAIL + TOKEN, "code": 403}})
    results.append(run(colab=colab)[0])
    for result in results:
        text = repr(result) + json.dumps(result.to_safe_dict())
        for secret in (TOKEN, SUBJECT, EMAIL, BINDING, "Private Person"):
            assert secret not in text
    for secret in (TOKEN, SUBJECT, EMAIL, BINDING):
        assert secret not in caplog.text


def test_internal_failure_is_contained_without_chaining(monkeypatch):
    def explode(self, *args, **kwargs):
        raise RuntimeError(TOKEN + EMAIL)
    monkeypatch.setattr(module.ColabRuntimeClient, "list_runtime_specs", explode)
    result, _, _ = run()
    assert "PREFLIGHT_INTERNAL_ERROR" in result.technical_blocking_reasons
    assert TOKEN not in repr(result)
    assert_blocked(result)
