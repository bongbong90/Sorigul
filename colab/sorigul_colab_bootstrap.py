import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


COLAB_RUNTIME_FOLDER = "Sorigul Runtime"
COLAB_CONNECTION_FILENAME = "colab_connection.json"
COLAB_SCHEMA_VERSION = 1
COLAB_READY_TTL_SECONDS = 3600
COLAB_REQUEST_TTL_SECONDS = 600
COLAB_CLOCK_SKEW_SECONDS = 60

SIGNATURE_VERSION = "SORIGUL-COLAB-V1"
SIGNED_REQUEST_SKEW_SECONDS = 120
REPLAY_NONCE_TTL_SECONDS = 300
REPLAY_NONCE_LIMIT = 4096
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()

CLOUDFLARED_VERSION = "2026.9.3"
CLOUDFLARED_ASSET_URL = (
    "https://github.com/cloudflare/cloudflared/releases/download/"
    f"{CLOUDFLARED_VERSION}/cloudflared-linux-amd64"
)
CLOUDFLARED_SHA256 = "77e26d8d900e0b8469f416239d14b5f296525fdf79fee6f511ef55609e3fbac2"
CLOUDFLARED_DOWNLOAD_TIMEOUT_SECONDS = 30


def _b64url_decode(value: str, expected_length: int) -> bytes:
    if not isinstance(value, str) or not value or re.fullmatch(r"[A-Za-z0-9_-]+", value) is None:
        raise ValueError("invalid base64url")
    try:
        decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except Exception as exc:
        raise ValueError("invalid base64url") from exc
    canonical = base64.urlsafe_b64encode(decoded).rstrip(b"=").decode("ascii")
    if len(decoded) != expected_length or canonical != value:
        raise ValueError("invalid base64url")
    return decoded


def parse_request_id(request_id: str) -> bytes:
    if not isinstance(request_id, str):
        raise ValueError("invalid request id")
    parts = request_id.split(".")
    if len(parts) != 3 or parts[0] != "srg2":
        raise ValueError("invalid request id")
    _b64url_decode(parts[1], 24)
    return _b64url_decode(parts[2], 32)


def canonical_request(
    method: str,
    path: str,
    request_id: str,
    timestamp: str,
    nonce: str,
    content_sha256: str,
) -> bytes:
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


class AuthenticationError(ValueError):
    pass


class ActivePairing:
    def __init__(self):
        self._lock = threading.RLock()
        self._request_id: Optional[str] = None
        self._public_key: Optional[Ed25519PublicKey] = None
        self._replay_nonces: dict[str, float] = {}

    def activate(self, request_id: str, public_key_bytes: bytes) -> None:
        public_key = Ed25519PublicKey.from_public_bytes(public_key_bytes)
        with self._lock:
            self._request_id = request_id
            self._public_key = public_key
            self._replay_nonces.clear()

    def verify_headers(
        self,
        headers,
        method: str,
        path: str,
        *,
        now: Optional[float] = None,
    ) -> str:
        current_time = time.time() if now is None else now
        request_id = headers.get("X-Sorigul-Request-Id", "")
        timestamp = headers.get("X-Sorigul-Timestamp", "")
        nonce = headers.get("X-Sorigul-Nonce", "")
        content_sha256 = headers.get("X-Sorigul-Content-SHA256", "")
        signature_text = headers.get("X-Sorigul-Signature", "")
        try:
            parse_request_id(request_id)
            parsed_timestamp = int(timestamp)
            if str(parsed_timestamp) != timestamp:
                raise ValueError("non-canonical timestamp")
            if abs(current_time - parsed_timestamp) > SIGNED_REQUEST_SKEW_SECONDS:
                raise ValueError("expired timestamp")
            if re.fullmatch(r"[A-Za-z0-9_-]{16,128}", nonce) is None:
                raise ValueError("invalid nonce")
            if re.fullmatch(r"[0-9a-f]{64}", content_sha256) is None:
                raise ValueError("invalid content hash")
            signature = _b64url_decode(signature_text, 64)
        except (TypeError, ValueError) as exc:
            raise AuthenticationError("invalid signed request") from exc

        with self._lock:
            self._expire_nonces_locked(current_time)
            if request_id != self._request_id or self._public_key is None:
                raise AuthenticationError("inactive pairing")
            if nonce in self._replay_nonces:
                raise AuthenticationError("replayed nonce")
            public_key = self._public_key
        message = canonical_request(method, path, request_id, timestamp, nonce, content_sha256)
        try:
            public_key.verify(signature, message)
        except InvalidSignature as exc:
            raise AuthenticationError("invalid signature") from exc
        with self._lock:
            if request_id != self._request_id:
                raise AuthenticationError("pairing replaced")
            self._expire_nonces_locked(current_time)
            if nonce in self._replay_nonces:
                raise AuthenticationError("replayed nonce")
            if len(self._replay_nonces) >= REPLAY_NONCE_LIMIT:
                oldest = min(self._replay_nonces, key=self._replay_nonces.get)
                del self._replay_nonces[oldest]
            self._replay_nonces[nonce] = current_time + REPLAY_NONCE_TTL_SECONDS
        return content_sha256

    def _expire_nonces_locked(self, now: float) -> None:
        for nonce, expires_at in list(self._replay_nonces.items()):
            if expires_at <= now:
                del self._replay_nonces[nonce]


active_pairing = ActivePairing()


def build_ready_metadata(request_payload: dict, base_url: str, now: Optional[datetime] = None) -> Optional[dict]:
    if not isinstance(request_payload, dict):
        return None
    expected_keys = {"schema_version", "request_id", "url", "status", "updated_at", "expires_at"}
    if set(request_payload.keys()) != expected_keys:
        return None
    if request_payload.get("schema_version") != COLAB_SCHEMA_VERSION:
        return None
    if request_payload.get("status") != "REQUESTED" or request_payload.get("url") != "":
        return None
    request_id = request_payload.get("request_id")
    try:
        parse_request_id(request_id)
    except ValueError:
        return None
    if now is None:
        now = datetime.now(timezone.utc)
    try:
        updated_at = datetime.fromisoformat(request_payload["updated_at"])
        expires_at = datetime.fromisoformat(request_payload["expires_at"])
    except (ValueError, TypeError):
        return None
    if updated_at.tzinfo is None or updated_at.utcoffset() is None:
        return None
    if expires_at.tzinfo is None or expires_at.utcoffset() is None:
        return None
    if expires_at <= now or updated_at > now + timedelta(seconds=COLAB_CLOCK_SKEW_SECONDS):
        return None
    lifetime = (expires_at - updated_at).total_seconds()
    if lifetime <= 0 or lifetime > COLAB_REQUEST_TTL_SECONDS:
        return None
    ready_expires = datetime.fromtimestamp(now.timestamp() + COLAB_READY_TTL_SECONDS, timezone.utc)
    return {
        "schema_version": COLAB_SCHEMA_VERSION,
        "request_id": request_id,
        "url": base_url,
        "status": "READY",
        "updated_at": now.isoformat(),
        "expires_at": ready_expires.isoformat(),
    }


def parse_cloudflare_url(log_path: str) -> str:
    if not os.path.exists(log_path):
        return ""
    with open(log_path, "r", encoding="utf-8") as handle:
        for line in handle:
            match = re.search(r"https://([a-z0-9-]+\.trycloudflare\.com)(?:\s|$)", line)
            if match:
                return f"https://{match.group(1)}"
    return ""


def rendezvous_loop(base_url: str, pairing: ActivePairing = active_pairing):
    import google.colab.drive  # noqa: F401
    runtime_dir = os.path.join("/content/drive/MyDrive", COLAB_RUNTIME_FOLDER)
    os.makedirs(runtime_dir, exist_ok=True)
    conn_file = os.path.join(runtime_dir, COLAB_CONNECTION_FILENAME)
    last_request_id = None
    while True:
        try:
            if os.path.exists(conn_file):
                with open(conn_file, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
                request_id = data.get("request_id")
                if request_id and request_id != last_request_id:
                    ready_meta = build_ready_metadata(data, base_url)
                    if ready_meta:
                        pairing.activate(request_id, parse_request_id(request_id))
                        temp_file = conn_file + ".tmp"
                        with open(temp_file, "w", encoding="utf-8") as output:
                            json.dump(ready_meta, output)
                            output.flush()
                            os.fsync(output.fileno())
                        os.replace(temp_file, conn_file)
                        last_request_id = request_id
                        fingerprint = hashlib.sha256(request_id.encode("utf-8")).hexdigest()[:12]
                        print(f"Rendezvous successful ({fingerprint})")
        except Exception:
            pass
        time.sleep(3)


def create_app(model, bootstrap_secret: str, pairing: ActivePairing = active_pairing):
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
    import torch

    app = FastAPI()

    def unauthorized():
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})

    @app.get("/health")
    async def health(request: Request):
        local_secret = request.headers.get("X-Sorigul-Local-Bootstrap", "")
        if local_secret and hmac.compare_digest(local_secret, bootstrap_secret):
            authenticated = True
        else:
            try:
                pairing.verify_headers(request.headers, "GET", "/health")
                authenticated = True
            except AuthenticationError:
                authenticated = False
        if not authenticated:
            return unauthorized()
        if model is None:
            return JSONResponse(status_code=503, content={"error": "Model not loaded"})
        return {"status": "ok"}

    @app.post("/transcribe")
    async def transcribe(request: Request):
        try:
            expected_hash = pairing.verify_headers(request.headers, "POST", "/transcribe")
        except AuthenticationError:
            return unauthorized()
        if model is None:
            return JSONResponse(status_code=503, content={"error": "Model not loaded"})
        temp_audio_path = None
        try:
            form = await request.form()
            uploaded = form.get("file")
            if uploaded is None or not hasattr(uploaded, "read"):
                return JSONResponse(status_code=400, content={"error": "Missing file"})
            content = await uploaded.read()
            actual_hash = hashlib.sha256(content).hexdigest()
            if not hmac.compare_digest(actual_hash, expected_hash):
                return JSONResponse(status_code=400, content={"error": "Content hash mismatch"})
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_audio:
                temp_audio.write(content)
                temp_audio_path = temp_audio.name
            result = model.transcribe(
                temp_audio_path,
                language="ko",
                task="transcribe",
                temperature=0.0,
                beam_size=5,
                best_of=5,
                patience=1,
                condition_on_previous_text=False,
                fp16=torch.cuda.is_available(),
            )
            return {
                "text": result["text"],
                "segments": [
                    {"start": item["start"], "end": item["end"], "text": item["text"]}
                    for item in result["segments"]
                ],
                "language": "ko",
            }
        except Exception:
            return JSONResponse(status_code=500, content={"error": "Transcription failed"})
        finally:
            if temp_audio_path:
                try:
                    os.remove(temp_audio_path)
                except OSError:
                    pass
    return app


def run_uvicorn(app):
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def download_file(url: str, destination: str, timeout: float) -> None:
    request = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        with open(destination, "wb") as output:
            shutil.copyfileobj(response, output)


def ensure_cloudflared(
    binary_path: str,
    *,
    asset_url: str = CLOUDFLARED_ASSET_URL,
    expected_sha256: str = CLOUDFLARED_SHA256,
    timeout: float = CLOUDFLARED_DOWNLOAD_TIMEOUT_SECONDS,
    downloader=download_file,
) -> str:
    binary_path = os.path.abspath(binary_path)
    parent = os.path.dirname(binary_path) or os.curdir
    os.makedirs(parent, exist_ok=True)
    if os.path.isfile(binary_path) and hmac.compare_digest(sha256_file(binary_path), expected_sha256):
        os.chmod(binary_path, 0o755)
        return binary_path
    fd, temp_path = tempfile.mkstemp(prefix=".cloudflared-", dir=parent)
    os.close(fd)
    try:
        downloader(asset_url, temp_path, timeout)
        if not hmac.compare_digest(sha256_file(temp_path), expected_sha256):
            raise RuntimeError("cloudflared SHA-256 verification failed")
        os.chmod(temp_path, 0o755)
        os.replace(temp_path, binary_path)
        return binary_path
    finally:
        try:
            os.remove(temp_path)
        except FileNotFoundError:
            pass


@dataclass
class TunnelProcess:
    process: object
    log_handle: object


def start_tunnel(binary_path: str, log_path: str, popen=subprocess.Popen) -> TunnelProcess:
    # No token/account/name is supplied: this is Cloudflare's free anonymous
    # Quick Tunnel mode and cannot provision an account-owned tunnel resource.
    log_handle = open(log_path, "w", encoding="utf-8")
    try:
        process = popen(
            [binary_path, "tunnel", "--url", "http://127.0.0.1:8000", "--no-autoupdate"],
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=log_handle,
            shell=False,
        )
        return TunnelProcess(process, log_handle)
    except Exception:
        log_handle.close()
        raise


def stop_owned_tunnel(tunnel: TunnelProcess) -> None:
    try:
        tunnel.process.terminate()
        try:
            tunnel.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            tunnel.process.kill()
            tunnel.process.wait(timeout=10)
    finally:
        tunnel.log_handle.close()


def main():
    print("Starting Sorigul Colab Bootstrap...")
    try:
        from google.colab import drive
        drive.mount("/content/drive")
    except ImportError:
        print("Not running in Google Colab. Drive mount skipped.")
        return
    print("Loading Whisper Medium model...")
    import whisper
    model = whisper.load_model("medium")
    print("Model loaded.")
    bootstrap_secret = secrets.token_urlsafe(32)
    app = create_app(model, bootstrap_secret)
    threading.Thread(target=run_uvicorn, args=(app,), daemon=True).start()
    health_ok = False
    for _ in range(10):
        try:
            request = urllib.request.Request(
                "http://127.0.0.1:8000/health",
                headers={"X-Sorigul-Local-Bootstrap": bootstrap_secret},
                method="GET",
            )
            with urllib.request.urlopen(request, timeout=2) as response:
                if response.status == 200:
                    health_ok = True
                    break
        except (urllib.error.URLError, TimeoutError):
            pass
        time.sleep(2)
    if not health_ok:
        print("Error: Local server did not become healthy. Tunnel will not start.")
        return
    binary_path = ensure_cloudflared(os.path.join(os.getcwd(), "cloudflared"))
    tunnel_log = os.path.join(os.getcwd(), "tunnel.log")
    tunnel = start_tunnel(binary_path, tunnel_log)
    time.sleep(5)
    base_url = parse_cloudflare_url(tunnel_log)
    if not base_url:
        stop_owned_tunnel(tunnel)
        print("Failed to start tunnel.")
        return
    print(f"Tunnel URL: {base_url}")
    try:
        rendezvous_loop(base_url)
    finally:
        stop_owned_tunnel(tunnel)


if __name__ == "__main__":
    main()
