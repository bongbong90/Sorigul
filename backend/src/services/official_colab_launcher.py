"""Server-side one-click orchestration for official Colab Jobs (#245).

Order, all fail-closed and before any Runtime POST:
  1. static launch gates (COST / POLICY) -- no network while blocked
  2. server-injected credentials (never from a request, Job or settings)
  3. no unresolved durable ownership record (no network)
  4. read-only launch preflight: identity / Colab access / FREE / T4
  5. launch authorizer approval
  6. same verified account on the Runtime client, then one owned create
  7. the existing OfficialColabJobEngine -> FullFilePipeline -> Runner/Writer
  8. close_session(): delete only the owned Runtime; failure keeps the Job
     from being reported as a clean completion

The default authorizer follows the preflight verdict, which is BLOCKED while
COST_GATE is CONDITIONAL and POLICY_GATE is NOT VERIFIED. A future, separately
approved live path injects its own authorizer and credential provider here on
the server; nothing in this module reads a client request.

Credentials, tokens, account fingerprints and proxy URLs are never logged,
persisted or returned by status().
"""

from dataclasses import dataclass, field
from pathlib import Path
from functools import partial

from src.domain.transcription import ErrorCategory
from src.engines.colab import ColabRecoveryCache
from src.engines.official_colab import OfficialColabEngineError, OfficialColabJobEngine
from src.services import colab_launch_preflight as preflight_module
from src.services.colab_account_verifier import GoogleAccountVerifier
from src.services.colab_full_file_pipeline import ColabFullFilePipeline
from src.services.colab_launch_preflight import (
    CheckStatus, LaunchApproval, T4Status, TierStatus, run_launch_preflight,
)
from src.services.colab_runtime_client import ColabRuntimeClient, RuntimeClientError, RuntimeErrorCode
from src.services.colab_runtime_ownership import OwnershipState, OwnershipStore, RuntimeOwnership


REASON_MESSAGES = {
    "FEATURE_DISABLED": "공식 Colab 자동 연결이 아직 활성화되지 않았습니다.",
    "COST_GATE_CONDITIONAL": "유료 크레딧을 쓰지 않는다는 보장이 아직 확인되지 않았습니다.",
    "POLICY_GATE_NOT_VERIFIED": "Google 무료 이용 정책 적합성이 아직 확인되지 않았습니다.",
    "ACCOUNT_NOT_CONNECTED": "공식 Colab에 사용할 Google 계정이 연결되지 않았습니다.",
    "OWNERSHIP_UNRESOLVED": "이전 원격 작업의 정리 여부를 먼저 확인해야 합니다.",
}


def status_reasons(codes):
    return [{"code": code, "message": REASON_MESSAGES[code]} for code in dict.fromkeys(codes)]


def static_gate_blockers():
    """COST/POLICY blockers derived from the preflight module's gate sets."""
    blockers = []
    if preflight_module.COST_GATE not in preflight_module._VERIFIED_COST_GATES:
        blockers.append("COST_GATE_CONDITIONAL")
    if preflight_module.POLICY_GATE not in preflight_module._VERIFIED_POLICY_GATES:
        blockers.append("POLICY_GATE_NOT_VERIFIED")
    return blockers


def disabled_status():
    return {"state": "DISABLED", "available": False,
            "reasons": status_reasons(["FEATURE_DISABLED", *static_gate_blockers()])}


@dataclass(frozen=True)
class LaunchCredentials:
    access_token: str = field(repr=False)
    granted_scopes: tuple = ()
    expected_account_binding: str | None = field(default=None, repr=False)


class FailClosedLaunchAuthorizer:
    """Default: exactly the preflight verdict. No GO exists today."""

    def static_blockers(self):
        return static_gate_blockers()

    def authorize(self, preflight):
        return preflight.launch_approval is LaunchApproval.GO


def default_ownership_factory(store, credentials):
    client = ColabRuntimeClient(credentials.access_token, account_verifier=GoogleAccountVerifier())
    return RuntimeOwnership(store, client)


def _error(kind, message, *, category=ErrorCategory.RUNTIME, local=True, cleanup=False):
    return OfficialColabEngineError(kind, message, category=category, fatal=True,
                                    cleanup_required=cleanup, local_selection_possible=local and not cleanup)


_CREATE_ERRORS = {
    RuntimeErrorCode.AUTH_EXPIRED: ("AUTH_REQUIRED", "계정과 접근 권한을 확인해 주세요.", ErrorCategory.AUTHENTICATION),
    RuntimeErrorCode.ACCESS_DENIED: ("AUTH_REQUIRED", "계정과 접근 권한을 확인해 주세요.", ErrorCategory.AUTHENTICATION),
    RuntimeErrorCode.FREE_GPU_UNAVAILABLE: ("RESOURCE_UNAVAILABLE", "무료 전사 자원을 사용할 수 없습니다.", ErrorCategory.RUNTIME),
    RuntimeErrorCode.USAGE_LIMIT: ("LIMITED", "이용 정책 또는 사용량 제한으로 작업을 시작하지 않았습니다.", ErrorCategory.RUNTIME),
    RuntimeErrorCode.SERVICE_RESTRICTED: ("LIMITED", "이용 정책 또는 사용량 제한으로 작업을 시작하지 않았습니다.", ErrorCategory.RUNTIME),
    RuntimeErrorCode.NETWORK_TIMEOUT: ("NETWORK_ERROR", "전사 연결을 확인해 주세요.", ErrorCategory.NETWORK),
    RuntimeErrorCode.NETWORK_ERROR: ("NETWORK_ERROR", "전사 연결을 확인해 주세요.", ErrorCategory.NETWORK),
}


class LaunchedOfficialColabEngine:
    """The existing engine plus one owned Runtime that this launch created."""

    def __init__(self, engine, ownership):
        self._engine = engine
        self._ownership = ownership
        self._closed = None

    def transcribe(self, source_path, token, event_callback, progress_callback):
        return self._engine.transcribe(source_path, token, event_callback, progress_callback)

    def close_session(self):
        """Delete only this launch's owned Runtime. True only when confirmed."""
        if self._closed is not None:
            return self._closed
        clean = False
        try:
            result = self._ownership.cleanup()
            clean = result.state is OwnershipState.CLEANED and not result.cleanup_required
        except Exception:
            clean = False
        finally:
            try:
                self._ownership.close()
            finally:
                self._ownership.client.close()
        self._closed = clean
        return clean


class OfficialColabLauncher:
    def __init__(self, *, credential_provider, ownership_store=None,
                 ownership_factory=default_ownership_factory, authorizer=None,
                 pipeline_factory=ColabFullFilePipeline, cache_root: Path,
                 preflight_options=None, provisioning_authorizer=None, provisioning_event=lambda event: None):
        self._credentials = credential_provider
        self._store = ownership_store if ownership_store is not None else OwnershipStore()
        self._ownership_factory = ownership_factory
        self._authorizer = authorizer if authorizer is not None else FailClosedLaunchAuthorizer()
        self._pipeline_factory = pipeline_factory
        # A separate trusted server capability; never populated from Job/settings/request.
        # Without it the existing read-only prepare path remains in use.
        if provisioning_authorizer is not None:
            self._pipeline_factory = partial(pipeline_factory,
                provisioning_authorizer=provisioning_authorizer, provisioning_event=provisioning_event)
        self._cache_root = Path(cache_root)
        # Trusted test seams for the preflight's inner network layer only.
        self._preflight_options = dict(preflight_options or {})

    def _load_credentials(self, *, refresh=False):
        try:
            provider = getattr(self._credentials, "for_launch", self._credentials) if refresh else self._credentials
            credentials = provider()
        except Exception:
            return None
        if (not isinstance(credentials, LaunchCredentials)
                or not isinstance(credentials.access_token, str) or not credentials.access_token):
            return None
        return credentials

    def _ownership_unresolved(self):
        try:
            return any(record.state is not OwnershipState.CLEANED for record in self._store.load())
        except Exception:
            return True  # Unreadable/corrupt ownership storage is never "clean".

    def status(self):
        """No network. Lists every reason a launch would be refused right now."""
        reasons = list(self._authorizer.static_blockers())
        if self._load_credentials() is None:
            reasons.append("ACCOUNT_NOT_CONNECTED")
        if self._ownership_unresolved():
            reasons.append("OWNERSHIP_UNRESOLVED")
        return {"state": "BLOCKED" if reasons else "READY", "available": not reasons,
                "reasons": status_reasons(reasons)}

    def launch(self):
        if self._authorizer.static_blockers():
            raise _error("LAUNCH_BLOCKED", "실행 조건이 확인되지 않아 공식 Colab 전사를 시작하지 않았습니다.",
                         category=ErrorCategory.CONFIGURATION)
        credentials = self._load_credentials(refresh=True)
        if credentials is None:
            raise _error("AUTH_REQUIRED", "공식 Colab에 사용할 Google 계정을 연결해 주세요.",
                         category=ErrorCategory.AUTHENTICATION)
        if self._ownership_unresolved():
            raise _error("OWNERSHIP_UNRESOLVED", "이전 원격 작업의 정리 여부를 먼저 확인해 주세요.", local=False)

        result = run_launch_preflight(
            credentials.access_token, network_approved=True,
            expected_account_binding=credentials.expected_account_binding,
            granted_scopes=credentials.granted_scopes, **self._preflight_options)
        if result.identity is CheckStatus.ACCOUNT_MISMATCH:
            raise _error("ACCOUNT_MISMATCH", "연결된 Google 계정이 이전에 확인한 계정과 다릅니다.",
                         category=ErrorCategory.AUTHENTICATION)
        if result.identity is CheckStatus.NETWORK_ERROR or result.colab_access is CheckStatus.NETWORK_ERROR:
            raise _error("NETWORK_ERROR", "전사 연결을 확인해 주세요.", category=ErrorCategory.NETWORK)
        if result.identity is not CheckStatus.VERIFIED or result.colab_access is not CheckStatus.VERIFIED:
            raise _error("AUTH_REQUIRED", "계정과 접근 권한을 확인해 주세요.", category=ErrorCategory.AUTHENTICATION)
        if result.tier is TierStatus.PAID:
            raise _error("PAID_TIER", "유료 구독 계정에서는 무료 전사를 보장할 수 없어 시작하지 않았습니다.")
        if result.tier is not TierStatus.FREE or result.t4 is not T4Status.ELIGIBLE:
            raise _error("RESOURCE_UNAVAILABLE", "무료 전사 자원을 사용할 수 없습니다.")
        if self._authorizer.authorize(result) is not True:
            raise _error("LAUNCH_BLOCKED", "실행 조건이 확인되지 않아 공식 Colab 전사를 시작하지 않았습니다.",
                         category=ErrorCategory.CONFIGURATION)

        try:
            ownership = self._ownership_factory(self._store, credentials)
        except Exception:
            raise _error("CONFIG_INVALID", "전사 환경 설정을 확인해 주세요.",
                         category=ErrorCategory.CONFIGURATION) from None
        try:
            if ownership.client.verified_account_binding() != result.account_binding:
                raise _error("ACCOUNT_MISMATCH", "연결된 Google 계정이 이전에 확인한 계정과 다릅니다.",
                             category=ErrorCategory.AUTHENTICATION)
            ownership.create()
        except OfficialColabEngineError:
            ownership.client.close()
            raise
        except RuntimeClientError as exc:
            ownership.client.close()
            if exc.cleanup_required:
                raise _error("CLEANUP_REQUIRED", "원격 작업 정리가 필요합니다.", cleanup=True) from None
            if exc.code is RuntimeErrorCode.PRECONDITION_UNVERIFIED:
                raise _error("AUTH_REQUIRED", "계정과 접근 권한을 확인해 주세요.",
                             category=ErrorCategory.AUTHENTICATION) from None
            if exc.code is RuntimeErrorCode.DUPLICATE_CREATE:
                raise _error("OWNERSHIP_UNRESOLVED", "이전 원격 작업의 정리 여부를 먼저 확인해 주세요.",
                             local=False) from None
            kind, message, category = _CREATE_ERRORS.get(
                exc.code, ("FAILED", "전사 작업을 안전하게 시작하지 못했습니다.", ErrorCategory.RUNTIME))
            raise _error(kind, message, category=category) from None
        except Exception:
            ownership.client.close()
            raise _error("STATE_UNCERTAIN", "원격 작업 상태를 확인할 수 없어 작업을 중단했습니다.",
                         local=False, cleanup=True) from None

        try:
            engine = OfficialColabJobEngine(ownership, ColabRecoveryCache(self._cache_root),
                                            pipeline_factory=self._pipeline_factory)
        except OfficialColabEngineError:
            launched = LaunchedOfficialColabEngine(None, ownership)
            if not launched.close_session():
                raise _error("CLEANUP_REQUIRED", "원격 작업 정리가 필요합니다.", cleanup=True) from None
            raise
        return LaunchedOfficialColabEngine(engine, ownership)
