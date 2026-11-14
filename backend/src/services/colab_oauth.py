"""Separate installed-desktop Colab OAuth. No Drive token or launch approval.

Only explicit start/check/disconnect actions use Google. status() and the
launcher credential callable are local reads. Code+S256 PKCE, signed OIDC
nonce/audience/expiry, and exact-token UserInfo are required before publishing.
"""

import base64
import hashlib
import json
import math
from pathlib import Path
import re
import secrets
import ssl
import threading
import time
from types import SimpleNamespace
from urllib.parse import urlencode, urlsplit
import urllib.request
import urllib.error

from src.services.colab_account_verifier import GoogleAccountVerifier, GOOGLE_ISSUER, _NoRedirect, _unique_object
from src.services.colab_launch_preflight import CheckStatus, SCOPE_COLAB, run_launch_preflight
from src.services.colab_oauth_callback import ColabLoopbackCallback
from src.services.colab_runtime_ownership import _no_links
from src.services.official_colab_launcher import LaunchCredentials, static_gate_blockers


SCOPES = ("openid", SCOPE_COLAB)
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
CERT_URL = "https://www.googleapis.com/oauth2/v1/certs"
MESSAGES = {
    "DISCONNECTED": "연결 안 됨",
    "AUTHORIZING": "인증 진행 중",
    "CONNECTED": "연결됨",
    "INSUFFICIENT_SCOPE": "권한 부족",
    "REFRESH_REQUIRED": "인증 갱신 필요",
    "IDENTITY_FAILED": "계정 확인 실패",
}
ERROR_MESSAGES = {
    "CONFIG_REQUIRED": "Colab 전용 Google Cloud Desktop OAuth 클라이언트 설정이 필요합니다.",
    "CONFIG_INVALID": "Colab 전용 OAuth 클라이언트 설정을 확인해 주세요.",
    "AUTH_IN_PROGRESS": "인증 작업이 진행 중입니다. 완료하거나 취소한 뒤 다시 시도해 주세요.",
    "AUTH_FAILED": "Google Colab 인증을 완료하지 못했습니다. 다시 인증해 주세요.",
    "SCOPE_REQUIRED": "Colab에 필요한 권한이 승인되지 않았습니다. 다시 인증해 주세요.",
    "IDENTITY_FAILED": "Google 계정을 확인하지 못했습니다. 다시 인증해 주세요.",
    "REFRESH_REQUIRED": "인증을 갱신하지 못했습니다. Google Colab을 다시 연결해 주세요.",
    "OWNERSHIP_UNRESOLVED": "이전 원격 작업의 소유권과 정리 상태를 먼저 확인해 주세요.",
    "SECURE_STORE_FAILED": "인증정보를 안전하게 저장하거나 읽지 못했습니다. 다시 연결해 주세요.",
    "NOT_CONNECTED": "Google Colab 계정을 연결해 주세요.",
    "REVOKE_FAILED": "Google 연결 해제를 확인하지 못했습니다. 연결 해제를 다시 시도해 주세요.",
}


class ColabOAuthError(Exception):
    def __init__(self, code):
        self.code = code
        self.user_message = ERROR_MESSAGES[code]
        super().__init__(code)


def load_client(path, drive_client_path=None):
    """Dedicated server-side installed config, never request/settings/Drive defaults."""
    path = Path(path)
    if not path.exists():
        raise ColabOAuthError("CONFIG_REQUIRED")
    try:
        _no_links(path)
        if path.stat().st_size > 32768:
            raise ValueError
        data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
        config = data["installed"]
        if ("web" in data or not isinstance(config, dict)
                or not re.fullmatch(r"[A-Za-z0-9_-]+\.apps\.googleusercontent\.com", config["client_id"])
                or not isinstance(config.get("project_id"), str) or not config["project_id"]
                or config.get("auth_uri") != AUTH_URL or config.get("token_uri") != TOKEN_URL
                or not isinstance(config.get("client_secret"), str) or not config["client_secret"]):
            raise ValueError
        # Google revocation can affect a project's grants: require a distinct
        # project/client when the Drive app's public client config is provisioned.
        if drive_client_path is not None and Path(drive_client_path).exists():
            drive = json.loads(Path(drive_client_path).read_text(encoding="utf-8"))["installed"]
            if config["client_id"] == drive.get("client_id") or config["project_id"] == drive.get("project_id"):
                raise ValueError
        return {key: config[key] for key in ("client_id", "client_secret", "project_id")}
    except Exception:
        raise ColabOAuthError("CONFIG_INVALID") from None


class GoogleColabOAuthProvider:
    def __init__(self, *, opener=None, id_token_verifier=None):
        self.opener = opener if opener is not None else urllib.request.build_opener(
            urllib.request.ProxyHandler({}), _NoRedirect(),
            urllib.request.HTTPSHandler(context=ssl.create_default_context()))
        self._id_token_verifier = id_token_verifier
        self.account_verifier = GoogleAccountVerifier(opener=self.opener)

    def _request(self, url, form=None):
        if url not in (TOKEN_URL, REVOKE_URL, CERT_URL):
            raise ValueError("ENDPOINT_REFUSED")
        data = None if form is None else urlencode(form).encode("ascii")
        request = urllib.request.Request(url, data=data,
            headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
            method="GET" if form is None else "POST")
        try:
            response = self.opener.open(request, timeout=10)
        except urllib.error.HTTPError as exc:
            exc.close()
            raise ValueError("OAUTH_REJECTED") from None
        with response:
            if response.status != 200 or response.geturl() != url:
                raise ValueError("OAUTH_REJECTED")
            raw = response.read(65537)
            if len(raw) > 65536:
                raise ValueError("RESPONSE_INVALID")
            if url != REVOKE_URL and response.headers.get_content_type() != "application/json":
                raise ValueError("RESPONSE_INVALID")
            return raw

    def token(self, config, form):
        raw = self._request(TOKEN_URL, dict(form, client_id=config["client_id"], client_secret=config["client_secret"]))
        data = json.loads(raw, object_pairs_hook=_unique_object)
        if not isinstance(data, dict) or "error" in data:
            raise ValueError("OAUTH_REJECTED")
        return data

    def claims(self, token, client_id):
        if self._id_token_verifier is not None:
            return self._id_token_verifier(token, client_id)
        from google.oauth2.id_token import verify_oauth2_token
        def certificate_request(url, method="GET", **kwargs):
            if url != CERT_URL or method != "GET":
                raise ValueError("ENDPOINT_REFUSED")
            return SimpleNamespace(status=200, data=self._request(CERT_URL), headers={})
        return verify_oauth2_token(token, certificate_request, audience=client_id)

    def revoke(self, token):
        self._request(REVOKE_URL, {"token": token})


class ColabOAuthService:
    def __init__(self, client_path, store, *, drive_client_path=None, provider=None,
                 callback_factory=ColabLoopbackCallback, clock=time.time,
                 ownership_unresolved=lambda: True, preflight=run_launch_preflight):
        self._client_path, self._drive_client_path = client_path, drive_client_path
        self._store = store
        self._provider = provider if provider is not None else GoogleColabOAuthProvider()
        self._callbacks, self._clock = callback_factory, clock
        self._unresolved, self._preflight = ownership_unresolved, preflight
        self._lock = threading.RLock()
        self._record, self._loaded = None, False
        self._attempt, self._busy = None, False
        self._busy_owner = None
        self._state, self._error = "DISCONNECTED", None
        self._preflight_summary = None

    def _config(self):
        return load_client(self._client_path, self._drive_client_path)

    def _ownership_blocked(self):
        try:
            return self._unresolved() is not False
        except Exception:
            return True

    def _load(self):
        if self._loaded:
            return
        self._loaded = True
        try:
            record = self._store.load()
            if record is not None:
                if (set(record) != {"version", "client_id", "project_id", "access_token", "refresh_token", "expires_at", "scopes", "binding"}
                        or record["version"] != 1 or record["scopes"] != list(SCOPES)
                        or not re.fullmatch(r"[0-9a-f]{64}", record["binding"])
                        or any(not self._secret(record[k]) for k in ("access_token", "refresh_token"))
                        or type(record["expires_at"]) not in (float, int) or not math.isfinite(record["expires_at"])):
                    raise ValueError
                self._record, self._state = record, "CONNECTED"
        except Exception:
            self._state, self._error = "REFRESH_REQUIRED", "SECURE_STORE_FAILED"

    @staticmethod
    def _secret(value):
        return isinstance(value, str) and 1 <= len(value) <= 16384 and all(33 <= ord(c) <= 126 for c in value)

    def status(self):
        """Local-only; polling must never renew tokens or call Google."""
        with self._lock:
            self._load()
            configured, config_error = True, None
            try:
                config = self._config()
                if self._record and any(self._record[key] != config[key] for key in ("client_id", "project_id")):
                    self._state, self._error = "REFRESH_REQUIRED", "CONFIG_INVALID"
            except ColabOAuthError as exc:
                configured, config_error = False, exc.code
            if self._state == "CONNECTED" and self._record["expires_at"] <= self._clock() + 60:
                self._state = "REFRESH_REQUIRED"
            blocked = self._ownership_blocked()
            preflight_blockers = []
            if self._preflight_summary:
                if self._preflight_summary["tier"] != "FREE":
                    preflight_blockers.append("PAID_OR_UNKNOWN_TIER")
                if self._preflight_summary["t4"] != "ELIGIBLE":
                    preflight_blockers.append("GPU_UNAVAILABLE_OR_UNKNOWN")
                if self._preflight_summary["colab_access"] != "VERIFIED":
                    preflight_blockers.append("COLAB_ACCESS_UNVERIFIED")
            return dict(auth_state=self._state, message=MESSAGES[self._state], configured=configured,
                error_code=self._error or config_error,
                notice=ERROR_MESSAGES.get(self._error or config_error),
                scope_evidence="TOKEN_RESPONSE_VERIFIED" if self._record and self._state == "CONNECTED" else "NOT_VERIFIED",
                runtime_create_permission="NOT_VERIFIED", execution_state="UNVERIFIED",
                execution_message="실행 조건 미확인", launch_approval="BLOCKED",
                blocking_reasons=["FEATURE_DISABLED", *static_gate_blockers(),
                    *(["ACCOUNT_NOT_CONNECTED"] if self._state != "CONNECTED" else []),
                    *(["OWNERSHIP_UNRESOLVED"] if blocked else []), *preflight_blockers],
                disconnect_allowed=not blocked and not self._busy,
                preflight=self._preflight_summary)

    def __call__(self):
        """Server credential provider, safe for launcher's local status()."""
        with self._lock:
            status = self.status()
            if self._busy or not status["configured"] or status["auth_state"] != "CONNECTED":
                return None
            record = self._record
            return LaunchCredentials(record["access_token"], tuple(record["scopes"]), record["binding"])

    def start(self):
        with self._lock:
            self._load()
            if self._attempt is not None or self._busy:
                raise ColabOAuthError("AUTH_IN_PROGRESS")
            config = self._config()
            if self._ownership_blocked():
                # Keep the recovery credential stable until the owned work is resolved.
                raise ColabOAuthError("OWNERSHIP_UNRESOLVED")
            state, nonce, verifier = (secrets.token_urlsafe(48) for _ in range(3))
            callback = self._callbacks(state)
            redirect = callback.redirect_uri
            parsed = urlsplit(redirect)
            if (parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or not parsed.port
                    or parsed.path != ColabLoopbackCallback.PATH or parsed.query or parsed.fragment
                    or parsed.username or parsed.password):
                callback.shutdown()
                raise ColabOAuthError("AUTH_FAILED")
            attempt = SimpleNamespace(config=config, state=state, nonce=nonce, verifier=verifier,
                                      callback=callback, redirect=redirect)
            self._attempt, self._state, self._error = attempt, "AUTHORIZING", None
            self._preflight_summary = None
            challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).decode().rstrip("=")
            url = AUTH_URL + "?" + urlencode(dict(client_id=config["client_id"], redirect_uri=redirect,
                response_type="code", scope=" ".join(SCOPES), state=state, nonce=nonce,
                code_challenge=challenge, code_challenge_method="S256", access_type="offline",
                prompt="consent select_account", include_granted_scopes="false"))
            threading.Thread(target=self._await_callback, args=(attempt,), daemon=True).start()
            return {"authorization_url": url}

    def _await_callback(self, attempt):
        try:
            code = attempt.callback.wait_for_code(timeout=300)
            with self._lock:
                if self._attempt is not attempt:
                    return
                if not code:
                    raise ColabOAuthError("AUTH_FAILED")
                self._busy = True
                self._busy_owner = attempt
            response = self._provider.token(attempt.config, dict(grant_type="authorization_code", code=code,
                redirect_uri=attempt.redirect, code_verifier=attempt.verifier))
            with self._lock:
                if self._attempt is not attempt:
                    return
            record = self._validate(response, attempt.config, nonce=attempt.nonce)
            with self._lock:
                if self._attempt is not attempt:
                    return  # cancelled while token exchange was in flight
                if self._ownership_blocked():
                    raise ColabOAuthError("OWNERSHIP_UNRESOLVED")
                self._publish(record)
        except Exception as exc:
            with self._lock:
                if self._attempt is attempt:
                    self._fail(exc)
        finally:
            try:
                attempt.callback.shutdown()
            except Exception:
                pass
            with self._lock:
                if self._attempt is attempt:
                    self._attempt = None
                if self._busy_owner is attempt:
                    self._busy, self._busy_owner = False, None

    def _validate(self, response, config, *, nonce=None, previous=None):
        if (not isinstance(response, dict) or response.get("token_type") != "Bearer"
                or not self._secret(response.get("access_token"))
                or type(response.get("expires_in")) is not int or not 60 < response["expires_in"] <= 86400):
            raise ColabOAuthError("AUTH_FAILED")
        # Provenance: this is the direct TLS token endpoint response to OUR
        # code+PKCE exchange/refresh, never callback/request/Settings scope data.
        scopes = response.get("scope")
        if not isinstance(scopes, str) or set(scopes.split()) != set(SCOPES):
            raise ColabOAuthError("SCOPE_REQUIRED")
        access = response["access_token"]
        binding = self._provider.account_verifier(access)
        if binding is None or previous and binding != previous["binding"]:
            raise ColabOAuthError("IDENTITY_FAILED")
        if nonce is not None or "id_token" in response:
            try:
                claims = self._provider.claims(response["id_token"], config["client_id"])
                subject = claims["sub"]
                if (claims["aud"] != config["client_id"] or claims.get("azp", config["client_id"]) != config["client_id"]
                        or claims["iss"] not in (GOOGLE_ISSUER, "accounts.google.com")
                        or type(claims["exp"]) not in (int, float) or not math.isfinite(claims["exp"])
                        or claims["exp"] <= self._clock() + 60
                        or type(claims["iat"]) not in (int, float) or not math.isfinite(claims["iat"])
                        or claims["iat"] > self._clock() + 60
                        or not isinstance(subject, str) or not 1 <= len(subject) <= 255
                        or not subject.isascii() or not self._secret(subject)
                        or nonce is not None and (not isinstance(claims.get("nonce"), str)
                            or not secrets.compare_digest(claims["nonce"], nonce))
                        or hashlib.sha256((GOOGLE_ISSUER + "\0" + subject).encode("ascii")).hexdigest() != binding):
                    raise ValueError
                if "at_hash" in claims:
                    expected = base64.urlsafe_b64encode(hashlib.sha256(access.encode("ascii")).digest()[:16]).decode().rstrip("=")
                    if not secrets.compare_digest(claims["at_hash"], expected):
                        raise ValueError
            except Exception:
                raise ColabOAuthError("IDENTITY_FAILED") from None
        refresh = response.get("refresh_token", previous["refresh_token"] if previous else None)
        if not self._secret(refresh):
            raise ColabOAuthError("AUTH_FAILED")
        return dict(version=1, client_id=config["client_id"], project_id=config["project_id"], access_token=access, refresh_token=refresh,
                    expires_at=self._clock() + response["expires_in"], scopes=list(SCOPES), binding=binding)

    def _publish(self, record):
        try:
            self._store.save(record)
        except Exception:
            raise ColabOAuthError("SECURE_STORE_FAILED") from None
        self._record, self._state, self._error = record, "CONNECTED", None

    def _fail(self, exc):
        code = exc.code if isinstance(exc, ColabOAuthError) else "AUTH_FAILED"
        self._state = {"SCOPE_REQUIRED": "INSUFFICIENT_SCOPE", "IDENTITY_FAILED": "IDENTITY_FAILED"}.get(code, "REFRESH_REQUIRED")
        self._error, self._preflight_summary = code, None

    def cancel(self):
        with self._lock:
            if self._busy and self._attempt is None:
                raise ColabOAuthError("AUTH_IN_PROGRESS")
            attempt, self._attempt = self._attempt, None
            if attempt is not None:
                attempt.callback.shutdown()
            self._state = "REFRESH_REQUIRED" if self._record else "DISCONNECTED"
            self._error = None
            return self.status()

    def check(self, *, include_preflight=True):
        with self._lock:
            self._load()
            if self._busy or self._attempt is not None:
                raise ColabOAuthError("AUTH_IN_PROGRESS")
            if self._record is None:
                raise ColabOAuthError("NOT_CONNECTED")
            config = self._config()
            if any(self._record[key] != config[key] for key in ("client_id", "project_id")):
                raise ColabOAuthError("CONFIG_INVALID")
            previous = dict(self._record)
            self._busy = True
        try:
            if previous["expires_at"] <= self._clock() + 60:
                try:
                    response = self._provider.token(config, dict(grant_type="refresh_token", refresh_token=previous["refresh_token"]))
                    record = self._validate(response, config, previous=previous)
                except ColabOAuthError:
                    raise
                except Exception:
                    raise ColabOAuthError("REFRESH_REQUIRED") from None
            else:
                if self._provider.account_verifier(previous["access_token"]) != previous["binding"]:
                    raise ColabOAuthError("IDENTITY_FAILED")
                record = previous
            summary = None
            if include_preflight:
                result = self._preflight(record["access_token"], network_approved=True,
                    expected_account_binding=record["binding"], granted_scopes=tuple(record["scopes"]))
                if result.identity is not CheckStatus.VERIFIED:
                    raise ColabOAuthError("IDENTITY_FAILED")
                if result.colab_access is CheckStatus.AUTH_SCOPE_REQUIRED:
                    raise ColabOAuthError("SCOPE_REQUIRED")
                summary = {key: getattr(result, key).value for key in (
                    "identity", "colab_access", "tier", "t4", "launch_scope", "launch_approval")}
                summary["paid_cu_non_consumption_evidence"] = result.paid_cu_non_consumption_evidence
            with self._lock:
                self._publish(record)
                self._preflight_summary = summary
                return self.status()
        except Exception as exc:
            with self._lock:
                self._fail(exc)
            raise ColabOAuthError(exc.code if isinstance(exc, ColabOAuthError) else "AUTH_FAILED") from None
        finally:
            with self._lock:
                self._busy = False

    def for_launch(self):
        self.check(include_preflight=False)
        return self()

    def disconnect(self):
        with self._lock:
            self._load()
            if self._busy or self._attempt is not None:
                raise ColabOAuthError("AUTH_IN_PROGRESS")
            if self._ownership_blocked():
                raise ColabOAuthError("OWNERSHIP_UNRESOLVED")
            if self._record:
                config = self._config()
                if any(self._record[key] != config[key] for key in ("client_id", "project_id")):
                    raise ColabOAuthError("CONFIG_INVALID")
            self._busy = True
        try:
            if self._record is not None:
                try:
                    self._provider.revoke(self._record["refresh_token"])
                except Exception:
                    raise ColabOAuthError("REVOKE_FAILED") from None
            self._store.delete()
            with self._lock:
                self._record, self._state, self._error = None, "DISCONNECTED", None
                self._preflight_summary = None
                return self.status()
        except Exception as exc:
            raise ColabOAuthError(exc.code if isinstance(exc, ColabOAuthError) else "SECURE_STORE_FAILED") from None
        finally:
            with self._lock:
                self._busy = False
