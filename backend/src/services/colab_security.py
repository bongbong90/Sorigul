"""Memory-only authentication state for Desktop <-> Colab requests."""

from __future__ import annotations

import base64
import hashlib
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


REQUEST_ID_PREFIX = "srg2"
REQUEST_NONCE_BYTES = 24
REQUEST_ID_TTL_SECONDS = 3600
SIGNATURE_VERSION = "SORIGUL-COLAB-V1"
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str, expected_length: int) -> bytes:
    if not value or any(ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_" for ch in value):
        raise ValueError("invalid base64url")
    padding = "=" * (-len(value) % 4)
    try:
        decoded = base64.urlsafe_b64decode(value + padding)
    except Exception as exc:
        raise ValueError("invalid base64url") from exc
    if len(decoded) != expected_length or _b64url_encode(decoded) != value:
        raise ValueError("invalid base64url length")
    return decoded


def parse_request_id(request_id: str) -> tuple[bytes, bytes]:
    if not isinstance(request_id, str):
        raise ValueError("invalid request id")
    parts = request_id.split(".")
    if len(parts) != 3 or parts[0] != REQUEST_ID_PREFIX:
        raise ValueError("invalid request id")
    nonce = _b64url_decode(parts[1], REQUEST_NONCE_BYTES)
    public_key = _b64url_decode(parts[2], 32)
    return nonce, public_key


def canonical_request(
    method: str,
    path: str,
    request_id: str,
    timestamp: str,
    nonce: str,
    content_sha256: str,
) -> bytes:
    # The contract intentionally has no trailing newline.
    return "\n".join(
        (
            SIGNATURE_VERSION,
            method.upper(),
            path,
            request_id,
            timestamp,
            nonce,
            content_sha256,
        )
    ).encode("utf-8")


@dataclass
class PairingSession:
    request_id: str
    private_key: Ed25519PrivateKey
    created_at: float
    expires_at: float
    verified_base_url: Optional[str] = None

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(self.request_id.encode("utf-8")).hexdigest()[:16]

    def signed_headers(
        self,
        method: str,
        path: str,
        content_sha256: str,
        *,
        now: Optional[float] = None,
        nonce: Optional[str] = None,
    ) -> dict[str, str]:
        timestamp = str(int(time.time() if now is None else now))
        request_nonce = nonce or _b64url_encode(secrets.token_bytes(18))
        message = canonical_request(
            method, path, self.request_id, timestamp, request_nonce, content_sha256
        )
        signature = _b64url_encode(self.private_key.sign(message))
        return {
            "X-Sorigul-Request-Id": self.request_id,
            "X-Sorigul-Timestamp": timestamp,
            "X-Sorigul-Nonce": request_nonce,
            "X-Sorigul-Content-SHA256": content_sha256,
            "X-Sorigul-Signature": signature,
        }


class PairingRegistry:
    """Process-local signer registry. No object in this registry is serializable."""

    def __init__(self, clock: Callable[[], float] = time.time):
        self._clock = clock
        self._lock = threading.RLock()
        self._sessions: dict[str, PairingSession] = {}
        self._by_base_url: dict[str, str] = {}

    def create(self, ttl_seconds: int = REQUEST_ID_TTL_SECONDS) -> PairingSession:
        private_key = Ed25519PrivateKey.generate()
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        request_id = ".".join(
            (
                REQUEST_ID_PREFIX,
                _b64url_encode(secrets.token_bytes(REQUEST_NONCE_BYTES)),
                _b64url_encode(public_key),
            )
        )
        now = self._clock()
        session = PairingSession(request_id, private_key, now, now + ttl_seconds)
        with self._lock:
            self._cleanup_locked(now)
            # Drive exposes one rendezvous slot, so a new request replaces the
            # previous Desktop pairing just as it does in the Colab runtime.
            self._sessions.clear()
            self._by_base_url.clear()
            self._sessions[request_id] = session
        return session

    def lookup(self, request_id: str) -> Optional[PairingSession]:
        with self._lock:
            self._cleanup_locked(self._clock())
            return self._sessions.get(request_id)

    def bind(self, request_id: str, base_url: str) -> Optional[PairingSession]:
        with self._lock:
            self._cleanup_locked(self._clock())
            session = self._sessions.get(request_id)
            if session is None:
                return None
            if session.verified_base_url and session.verified_base_url != base_url:
                self._by_base_url.pop(session.verified_base_url, None)
            previous_id = self._by_base_url.get(base_url)
            if previous_id and previous_id != request_id:
                previous = self._sessions.get(previous_id)
                if previous is not None:
                    previous.verified_base_url = None
            session.verified_base_url = base_url
            self._by_base_url[base_url] = request_id
            return session

    def lookup_verified_base_url(self, base_url: str) -> Optional[PairingSession]:
        with self._lock:
            self._cleanup_locked(self._clock())
            request_id = self._by_base_url.get(base_url)
            return self._sessions.get(request_id) if request_id else None

    def revoke(self, request_id: str) -> None:
        with self._lock:
            session = self._sessions.pop(request_id, None)
            if session and session.verified_base_url:
                self._by_base_url.pop(session.verified_base_url, None)

    def _cleanup_locked(self, now: float) -> None:
        expired = [key for key, value in self._sessions.items() if value.expires_at <= now]
        for request_id in expired:
            session = self._sessions.pop(request_id)
            if session.verified_base_url:
                self._by_base_url.pop(session.verified_base_url, None)


pairing_registry = PairingRegistry()
