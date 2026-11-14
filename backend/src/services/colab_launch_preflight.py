"""Read-only, fail-closed preflight before an official Colab launch (#48).

Standalone: NOT wired into Job/Runtime execution or the Desktop UI, and the
`official_colab` engine stays DEFAULT OFF. Passing preflight is never launch
approval: while COST_GATE is CONDITIONAL or POLICY_GATE is NOT VERIFIED the
launch decision is BLOCKED, whatever FREE/T4/past-success evidence says.

Reuses GoogleAccountVerifier (UserInfo -> issuer+sub fingerprint) and
ColabRuntimeClient's classified GET path. Allowed remote reads, and only after
the caller passes network_approved=True for this user-initiated check:
  GET https://openidconnect.googleapis.com/v1/userinfo
  GET https://colaboratory.googleapis.com/v1beta/subscription
  GET https://colaboratory.googleapis.com/v1beta/runtimespecs
Any other method/host/path is refused by a guard transport BEFORE it reaches
the network: no Runtime POST/DELETE, kernels, files, models, billing, CU
purchase, undocumented usage endpoints (e.g. CLI /tun/m/ccu-info) or OAuth UI.

granted_scopes (the OAuth token response `scope` field) may only DOWNGRADE a
result; it is never evidence of authorization. Drive-scoped tokens are refused
locally so a Drive OAuth token is never reused for Colab.

No logging. Results carry enums only; the access token, Google `sub`, email,
profile fields and proxy tokens are never stored on results or exceptions.
The account fingerprint (sha256, same value RuntimeOwnership persists) is kept
out of repr and out of to_safe_dict().

Official references as recorded 2026-11-13 by the verifier/RuntimeClient and
PHASE 01 review (not re-fetched in PHASE 13; live behavior NOT VERIFIED):
https://developers.google.com/identity/openid-connect/openid-connect
https://developers.google.com/colab/api/reference/rest/v1beta/subscription/getSubscription
https://developers.google.com/colab/api/reference/rest/v1beta/runtimespecs/list
https://colaboratory.googleapis.com/$discovery/rest?version=v1beta
RFC 6750 s3.1 (WWW-Authenticate error="insufficient_scope").
"""

import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from enum import Enum

import httpx

from src.services import colab_account_verifier as _verifier_module
from src.services.colab_account_verifier import GOOGLE_USERINFO_ENDPOINT, GoogleAccountVerifier
from src.services.colab_runtime_client import (
    API_ROOT, T4_STANDARD, ColabRuntimeClient, RuntimeClientError, RuntimeErrorCode,
)


COLAB_HOST = "colaboratory.googleapis.com"
ALLOWED_COLAB_READS = frozenset({"/v1beta/subscription", "/v1beta/runtimespecs"})
SCOPE_OPENID = "openid"
SCOPE_COLAB = "https://www.googleapis.com/auth/colaboratory"
SCOPE_COLAB_READONLY = "https://www.googleapis.com/auth/colaboratory.readonly"
TIER_FREE = "SUBSCRIPTION_TIER_FREE"
PAID_TIERS = frozenset({"SUBSCRIPTION_TIER_PRO", "SUBSCRIPTION_TIER_PRO_PLUS"})

# What RuntimeOwnership/RuntimeClient need before any future create attempt.
OWNERSHIP_REQUIREMENTS = (
    "VERIFIED_ACCOUNT_BINDING_FROM_GOOGLE_USERINFO",
    "DURABLE_OWNERSHIP_RECORD_BEFORE_POST",
    "SINGLE_CLIENT_GENERATED_RUNTIME_ID",
    "SAME_ACCOUNT_REVERIFIED_ON_EVERY_RUNTIME_CALL",
)


class PreflightLabel(str, Enum):
    """Directive labels; a result exposes the subset that applies."""
    IDENTITY_VERIFIED = "IDENTITY_VERIFIED"
    AUTH_SCOPE_REQUIRED = "AUTH_SCOPE_REQUIRED"
    COLAB_ACCESS_VERIFIED = "COLAB_ACCESS_VERIFIED"
    FREE_TIER_VERIFIED = "FREE_TIER_VERIFIED"
    T4_ELIGIBLE = "T4_ELIGIBLE"
    TECHNICAL_PRECHECK_BLOCKED = "TECHNICAL_PRECHECK_BLOCKED"
    COST_GATE_CONDITIONAL = "COST_GATE_CONDITIONAL"
    POLICY_GATE_NOT_VERIFIED = "POLICY_GATE_NOT_VERIFIED"


class CheckStatus(str, Enum):
    VERIFIED = "VERIFIED"
    AUTH_SCOPE_REQUIRED = "AUTH_SCOPE_REQUIRED"
    AUTH_EXPIRED = "AUTH_EXPIRED"
    ACCESS_DENIED = "ACCESS_DENIED"
    ACCOUNT_MISMATCH = "ACCOUNT_MISMATCH"
    SERVICE_RESTRICTED = "SERVICE_RESTRICTED"
    USAGE_LIMITED = "USAGE_LIMITED"
    NETWORK_ERROR = "NETWORK_ERROR"
    RESPONSE_INVALID = "RESPONSE_INVALID"
    DRIVE_TOKEN_REFUSED = "DRIVE_TOKEN_REFUSED"
    READ_ONLY_GUARD_VIOLATION = "READ_ONLY_GUARD_VIOLATION"
    NOT_VERIFIED = "NOT_VERIFIED"
    NOT_RUN = "NOT_RUN"


class TierStatus(str, Enum):
    FREE = "FREE"
    PAID = "PAID"  # PRO / PRO_PLUS: paid CU may be consumed -> blocked.
    UNKNOWN = "UNKNOWN"
    NOT_RUN = "NOT_RUN"


class T4Status(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"  # Missing from specs or eligible=false.
    UNKNOWN = "UNKNOWN"            # Duplicate/ill-typed spec entries.
    NOT_RUN = "NOT_RUN"


class CostGate(str, Enum):
    # No supported public API proves paid-CU non-consumption or enforces a
    # free-only create (PHASE 01). There is deliberately no VERIFIED member.
    CONDITIONAL = "COST_GATE_CONDITIONAL"


class PolicyGate(str, Enum):
    # Google has not confirmed the free-tier policy for this product scenario.
    NOT_VERIFIED = "POLICY_GATE_NOT_VERIFIED"


class LaunchApproval(str, Enum):
    BLOCKED = "BLOCKED"
    GO = "GO"  # Unreachable while CostGate/PolicyGate have no verified member.


COST_GATE = CostGate.CONDITIONAL
POLICY_GATE = PolicyGate.NOT_VERIFIED
PAID_CU_NON_CONSUMPTION_EVIDENCE = "NO_SUPPORTED_API"
_VERIFIED_COST_GATES = frozenset()
_VERIFIED_POLICY_GATES = frozenset()


@dataclass(frozen=True)
class PreflightResult:
    identity: CheckStatus
    colab_access: CheckStatus
    tier: TierStatus
    t4: T4Status
    launch_scope: CheckStatus  # Full colaboratory scope needed for a later create.
    ownership_preconditions: CheckStatus
    cost_gate: CostGate
    policy_gate: PolicyGate
    technical_blocking_reasons: tuple
    launch_blocking_reasons: tuple
    launch_approval: LaunchApproval
    remote_requests: int
    paid_cu_non_consumption_evidence: str = PAID_CU_NON_CONSUMPTION_EVIDENCE
    account_binding: str | None = field(default=None, repr=False)

    @property
    def technical_precheck_passed(self):
        return not self.technical_blocking_reasons

    @property
    def labels(self):
        out = []
        if self.identity is CheckStatus.VERIFIED:
            out.append(PreflightLabel.IDENTITY_VERIFIED)
        if CheckStatus.AUTH_SCOPE_REQUIRED in (self.identity, self.colab_access, self.launch_scope):
            out.append(PreflightLabel.AUTH_SCOPE_REQUIRED)
        if self.colab_access is CheckStatus.VERIFIED:
            out.append(PreflightLabel.COLAB_ACCESS_VERIFIED)
        if self.tier is TierStatus.FREE:
            out.append(PreflightLabel.FREE_TIER_VERIFIED)
        if self.t4 is T4Status.ELIGIBLE:
            out.append(PreflightLabel.T4_ELIGIBLE)
        if self.technical_blocking_reasons:
            out.append(PreflightLabel.TECHNICAL_PRECHECK_BLOCKED)
        out.append(PreflightLabel.COST_GATE_CONDITIONAL)
        out.append(PreflightLabel.POLICY_GATE_NOT_VERIFIED)
        return tuple(out)

    def to_safe_dict(self):
        """Enum/count-only view; safe to log or persist (no binding/token/PII)."""
        return {
            "identity": self.identity.value, "colab_access": self.colab_access.value,
            "tier": self.tier.value, "t4": self.t4.value,
            "launch_scope": self.launch_scope.value,
            "ownership_preconditions": self.ownership_preconditions.value,
            "cost_gate": self.cost_gate.value, "policy_gate": self.policy_gate.value,
            "paid_cu_non_consumption_evidence": self.paid_cu_non_consumption_evidence,
            "technical_blocking_reasons": list(self.technical_blocking_reasons),
            "launch_blocking_reasons": list(self.launch_blocking_reasons),
            "launch_approval": self.launch_approval.value,
            "remote_requests": self.remote_requests,
            "labels": [label.value for label in self.labels],
        }


class _GuardViolation(Exception):
    """Not an httpx error, so ColabRuntimeClient cannot reclassify it."""


def _insufficient_scope(www_authenticate):
    return isinstance(www_authenticate, str) and "insufficient_scope" in www_authenticate.lower()


class _ReadOnlyColabTransport(httpx.BaseTransport):
    """Allows only the two documented GETs; observes 401/403 scope signals."""

    def __init__(self, inner):
        self._inner = inner
        self.requests = 0
        self.violation = False
        self.scope_insufficient = False

    def handle_request(self, request):
        if (request.method != "GET" or request.url.scheme != "https"
                or request.url.host != COLAB_HOST or request.url.path not in ALLOWED_COLAB_READS
                or request.url.query):
            self.violation = True
            raise _GuardViolation()
        self.requests += 1
        response = self._inner.handle_request(request)
        if response.status_code in (401, 403):
            if _insufficient_scope(response.headers.get("WWW-Authenticate")):
                self.scope_insufficient = True
            else:
                try:
                    response.read()
                    details = response.json().get("error", {}).get("details", [])
                    self.scope_insufficient = any(
                        isinstance(item, dict) and item.get("reason") == "ACCESS_TOKEN_SCOPE_INSUFFICIENT"
                        for item in details)
                except Exception:
                    pass
        return response

    def close(self):
        self._inner.close()


class _ObservingUserInfoOpener:
    """Wraps the verifier's fixed-endpoint opener to keep only a status class."""

    def __init__(self, inner):
        self._inner = inner
        self.requests = 0
        self.outcome = None

    def open(self, request, *, timeout):
        if request.get_method() != "GET" or request.full_url != GOOGLE_USERINFO_ENDPOINT:
            self.outcome = CheckStatus.READ_ONLY_GUARD_VIOLATION
            raise _GuardViolation()
        self.requests += 1
        try:
            return self._inner.open(request, timeout=timeout)
        except urllib.error.HTTPError as error:
            header = error.headers.get("WWW-Authenticate") if error.headers is not None else None
            if _insufficient_scope(header):
                self.outcome = CheckStatus.AUTH_SCOPE_REQUIRED
            elif error.code == 401:
                self.outcome = CheckStatus.AUTH_EXPIRED
            elif error.code == 403:
                self.outcome = CheckStatus.ACCESS_DENIED
            else:
                self.outcome = CheckStatus.RESPONSE_INVALID
            raise
        except Exception:
            self.outcome = CheckStatus.NETWORK_ERROR
            raise


def _default_userinfo_opener():
    # Same hardening as GoogleAccountVerifier's default: TLS, no proxy, no redirect.
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({}), _verifier_module._NoRedirect(),
        urllib.request.HTTPSHandler(context=ssl.create_default_context()),
    )


_COLAB_ERROR_MAP = {
    RuntimeErrorCode.AUTH_EXPIRED: CheckStatus.AUTH_EXPIRED,
    RuntimeErrorCode.ACCESS_DENIED: CheckStatus.ACCESS_DENIED,
    RuntimeErrorCode.SERVICE_RESTRICTED: CheckStatus.SERVICE_RESTRICTED,
    RuntimeErrorCode.USAGE_LIMIT: CheckStatus.USAGE_LIMITED,
    RuntimeErrorCode.NETWORK_TIMEOUT: CheckStatus.NETWORK_ERROR,
    RuntimeErrorCode.NETWORK_ERROR: CheckStatus.NETWORK_ERROR,
}


def _scope_set(granted_scopes):
    if granted_scopes is None:
        return None
    if isinstance(granted_scopes, str):
        granted_scopes = granted_scopes.split()
    try:
        return frozenset(s for s in granted_scopes if isinstance(s, str))
    except TypeError:
        return frozenset()


def run_launch_preflight(access_token, *, network_approved, expected_account_binding=None,
                         granted_scopes=None, colab_transport=None, userinfo_opener=None,
                         timeout_seconds=5.0):
    """Return a PreflightResult; never raises for remote/auth/data failures.

    network_approved must be literally True (a user-initiated check); anything
    else issues zero requests. expected_account_binding, when given, is the
    sha256 fingerprint of a previously verified account; a different verified
    account yields ACCOUNT_MISMATCH and stops before any Colab read.
    colab_transport / userinfo_opener are trusted test seams for the inner
    network layer; the read-only guards always wrap them.
    """
    identity = colab = CheckStatus.NOT_RUN
    tier, t4 = TierStatus.NOT_RUN, T4Status.NOT_RUN
    technical = []
    binding = None
    guard = opener = None
    scopes = _scope_set(granted_scopes)

    if scopes is None:
        launch_scope = CheckStatus.NOT_VERIFIED
    elif SCOPE_COLAB in scopes:
        launch_scope = CheckStatus.VERIFIED
    else:
        launch_scope = CheckStatus.AUTH_SCOPE_REQUIRED

    def finish():
        if identity is not CheckStatus.VERIFIED:
            technical.append("IDENTITY_" + identity.value)
        if colab is not CheckStatus.VERIFIED:
            technical.append("COLAB_ACCESS_" + colab.value)
        if tier is not TierStatus.FREE:
            technical.append("TIER_" + tier.value)
        if t4 is not T4Status.ELIGIBLE:
            technical.append("T4_" + t4.value)
        if launch_scope is not CheckStatus.VERIFIED:
            technical.append("LAUNCH_SCOPE_" + launch_scope.value)
        ownership = CheckStatus.VERIFIED if identity is CheckStatus.VERIFIED else CheckStatus.NOT_VERIFIED
        requests = (guard.requests if guard else 0) + (opener.requests if opener else 0)
        reasons = list(dict.fromkeys(technical))
        launch_reasons = list(reasons)
        if COST_GATE not in _VERIFIED_COST_GATES:
            launch_reasons.append(COST_GATE.value)
        if POLICY_GATE not in _VERIFIED_POLICY_GATES:
            launch_reasons.append(POLICY_GATE.value)
        return PreflightResult(
            identity=identity, colab_access=colab, tier=tier, t4=t4, launch_scope=launch_scope,
            ownership_preconditions=ownership, cost_gate=COST_GATE, policy_gate=POLICY_GATE,
            technical_blocking_reasons=tuple(reasons),
            launch_blocking_reasons=tuple(launch_reasons),
            launch_approval=LaunchApproval.GO if not launch_reasons else LaunchApproval.BLOCKED,
            remote_requests=requests, account_binding=binding,
        )

    if network_approved is not True:
        technical.append("NETWORK_NOT_APPROVED")
        return finish()
    if not isinstance(access_token, str) or not access_token or any(
            ord(c) < 33 or ord(c) > 126 for c in access_token):
        identity = colab = CheckStatus.AUTH_EXPIRED
        return finish()
    if expected_account_binding is not None and not (
            isinstance(expected_account_binding, str) and len(expected_account_binding) == 64
            and all(c in "0123456789abcdef" for c in expected_account_binding)):
        technical.append("EXPECTED_BINDING_INVALID")
        return finish()
    if scopes is not None:
        if any("/auth/drive" in s for s in scopes):
            identity = colab = launch_scope = CheckStatus.DRIVE_TOKEN_REFUSED
            return finish()
        if SCOPE_OPENID not in scopes:
            identity = CheckStatus.AUTH_SCOPE_REQUIRED
        if not scopes & {SCOPE_COLAB, SCOPE_COLAB_READONLY}:
            colab = CheckStatus.AUTH_SCOPE_REQUIRED

    opener = _ObservingUserInfoOpener(userinfo_opener or _default_userinfo_opener())
    guard = _ReadOnlyColabTransport(colab_transport or httpx.HTTPTransport(trust_env=False))
    verifier = GoogleAccountVerifier(timeout_seconds=timeout_seconds, opener=opener)
    client = None
    try:
        client = ColabRuntimeClient(access_token, transport=guard, timeout_seconds=timeout_seconds,
                                    max_polls=1, account_verifier=verifier)
        # 1. Identity (UserInfo), unless the declared scopes already lack openid.
        if identity is CheckStatus.NOT_RUN:
            try:
                binding = client.verified_account_binding()
            except RuntimeClientError:
                binding = None
            if binding is None:
                identity = opener.outcome or CheckStatus.RESPONSE_INVALID
            elif expected_account_binding is not None and binding != expected_account_binding:
                identity, binding = CheckStatus.ACCOUNT_MISMATCH, None
            else:
                identity = CheckStatus.VERIFIED
        if identity in (CheckStatus.AUTH_EXPIRED, CheckStatus.ACCOUNT_MISMATCH,
                        CheckStatus.NETWORK_ERROR, CheckStatus.READ_ONLY_GUARD_VIOLATION):
            return finish()  # Never read another/unknown account's Colab data.
        if colab is not CheckStatus.NOT_RUN:
            return finish()

        # 2. Colab access + subscription tier (one classified GET).
        try:
            # Reuses RuntimeClient's single classified request path, so the
            # tier enum is seen even when get_subscription() would reject it.
            payload = client._request("GET", "/v1beta/subscription")
        except RuntimeClientError as exc:
            colab = _COLAB_ERROR_MAP.get(exc.code, CheckStatus.RESPONSE_INVALID)
            if colab in (CheckStatus.AUTH_EXPIRED, CheckStatus.ACCESS_DENIED) and guard.scope_insufficient:
                colab = CheckStatus.AUTH_SCOPE_REQUIRED
            tier = TierStatus.UNKNOWN
            return finish()
        if payload.get("name") != "subscription":
            colab, tier = CheckStatus.RESPONSE_INVALID, TierStatus.UNKNOWN
            return finish()
        colab = CheckStatus.VERIFIED
        value = payload.get("tier")
        tier = (TierStatus.FREE if value == TIER_FREE
                else TierStatus.PAID if value in PAID_TIERS else TierStatus.UNKNOWN)
        if tier is not TierStatus.FREE:
            return finish()

        # 3. T4 STANDARD eligibility from runtimespecs.list (read only).
        try:
            specs = client.list_runtime_specs()
        except RuntimeClientError:
            t4 = T4Status.UNKNOWN
            technical.append("RUNTIME_SPECS_UNREADABLE")
            return finish()
        matches = [item for item in specs if item.get("key") == T4_STANDARD]
        if not matches:
            t4 = T4Status.NOT_ELIGIBLE
        elif len(matches) != 1 or type(matches[0].get("eligible")) is not bool:
            t4 = T4Status.UNKNOWN
        else:
            t4 = T4Status.ELIGIBLE if matches[0]["eligible"] else T4Status.NOT_ELIGIBLE
        return finish()
    except _GuardViolation:
        technical.append(CheckStatus.READ_ONLY_GUARD_VIOLATION.value)
        return finish()
    except Exception:
        # Never chain/expose private data; fail closed.
        technical.append("PREFLIGHT_INTERNAL_ERROR")
        return finish()
    finally:
        if client is not None:
            client.close()
