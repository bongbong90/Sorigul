"""Google UserInfo adapter for RuntimeClient.account_verifier(access_token).

Usage: ColabRuntimeClient(token, account_verifier=GoogleAccountVerifier()).
Ownership storage/format stays unchanged. No OAuth UI, scope changes, refresh,
Runtime calls, proxy credentials, token cache or persistence are implemented.

Official references checked 2026-11-13:
https://accounts.google.com/.well-known/openid-configuration
https://developers.google.com/identity/openid-connect/reference
https://developers.google.com/identity/openid-connect/openid-connect

Google's UserInfo guide documents openid profile. The existing Colab-only
scope doesn't establish UserInfo access. An insufficient/expired/revoked token
fails closed; caller-supplied scope labels aren't evidence of authorization.
New consent, if needed, must be separately approved for Colab, never Drive.

Trust comes from a 200 JSON response over certificate-verified HTTPS to the
fixed Google endpoint, using the exact token passed by RuntimeClient. This is
not local JWT/ID-token validation: no unverified JWT claims or email fallback.
"""

import hashlib
import json
import math
import ssl
import urllib.error
import urllib.request


GOOGLE_ISSUER = "https://accounts.google.com"
GOOGLE_USERINFO_ENDPOINT = "https://openidconnect.googleapis.com/v1/userinfo"
MAX_RESPONSE_BYTES = 16 * 1024


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _unique_object(pairs):
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError("Duplicate JSON field")
    return result


class GoogleAccountVerifier:
    """Callable returning only an issuer+sub fingerprint or None.

    No caching: every invocation checks that exact access token with Google.
    opener injection is a trusted test seam, not a configurable remote URL.
    urllib's default wire debugging is off; no URL, headers or bodies are logged.
    """

    def __init__(self, *, timeout_seconds=5.0, opener=None):
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("Timeout must be positive and finite")
        self._timeout = timeout_seconds
        self._opener = opener if opener is not None else urllib.request.build_opener(
            urllib.request.ProxyHandler({}), _NoRedirect(),
            urllib.request.HTTPSHandler(context=ssl.create_default_context()),
        )

    def __call__(self, access_token: str) -> str | None:
        if not isinstance(access_token, str) or not access_token or any(
                ord(char) < 33 or ord(char) > 126 for char in access_token):
            return None
        # Header only: never place credentials in URL, query, cookies or files.
        request = urllib.request.Request(
            GOOGLE_USERINFO_ENDPOINT, method="GET",
            headers={"Authorization": "Bearer " + access_token, "Accept": "application/json"},
        )
        try:
            with self._opener.open(request, timeout=self._timeout) as response:
                if (response.status != 200 or response.geturl() != GOOGLE_USERINFO_ENDPOINT
                        or response.headers.get_content_type() != "application/json"):
                    return None
                raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                return None
            payload = json.loads(raw, object_pairs_hook=_unique_object)
            if not isinstance(payload, dict) or "error" in payload:
                return None
            if "iss" in payload and payload["iss"] != GOOGLE_ISSUER:
                return None
            subject = payload.get("sub")
            if (not isinstance(subject, str) or not 1 <= len(subject) <= 255
                    or any(ord(char) < 33 or ord(char) > 126 for char in subject)):
                return None
            # Canonical issuer is pinned above, never taken from an arbitrary
            # response field. Preserve subject case; ignore all profile fields.
            return hashlib.sha256((GOOGLE_ISSUER + "\0" + subject).encode("ascii")).hexdigest()
        except urllib.error.HTTPError as error:
            # HTTPError owns a response stream even when authentication fails.
            try:
                error.close()
            except Exception:
                pass
            return None
        except Exception:
            # Includes denial/missing scope, redirect HTTPError, TLS/transport,
            # timeout and malformed JSON. Never expose or chain PII-bearing
            # errors; RuntimeClient converts None to PRECONDITION_UNVERIFIED.
            return None
