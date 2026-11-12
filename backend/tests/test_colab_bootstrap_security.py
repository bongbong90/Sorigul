import hashlib
import asyncio
import io
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from colab.sorigul_colab_bootstrap import (  # noqa: E402
    ActivePairing,
    AuthenticationError,
    CLOUDFLARED_ASSET_URL,
    CLOUDFLARED_SHA256,
    CLOUDFLARED_VERSION,
    create_app,
    ensure_cloudflared,
    start_tunnel,
    stop_owned_tunnel,
    build_ready_metadata,
)
from src.services.colab_security import EMPTY_SHA256, PairingRegistry, parse_request_id  # noqa: E402


class FakeModel:
    def __init__(self):
        self.calls = 0

    def transcribe(self, _path, **_kwargs):
        self.calls += 1
        return {"text": "ok", "segments": []}


def paired():
    registry = PairingRegistry()
    session = registry.create()
    _nonce, public_key = parse_request_id(session.request_id)
    pairing = ActivePairing()
    pairing.activate(session.request_id, public_key)
    return session, pairing


def transcribe_endpoint(app):
    return next(route.endpoint for route in app.routes if route.path == "/transcribe")


class FakeUpload:
    def __init__(self, content):
        self.content = content

    async def read(self):
        return self.content


class FakeRequest:
    def __init__(self, headers, content):
        self.headers = headers
        self.content = content
        self.form_calls = 0

    async def form(self):
        self.form_calls += 1
        return {"file": FakeUpload(self.content)}


def test_signed_health_passes_and_unsigned_health_is_rejected():
    session, pairing = paired()
    client = TestClient(create_app(FakeModel(), "local-only", pairing))
    assert client.get("/health").status_code == 401
    headers = session.signed_headers("GET", "/health", EMPTY_SHA256)
    assert client.get("/health", headers=headers).status_code == 200


def test_local_bootstrap_secret_is_required_for_unsigned_readiness():
    _session, pairing = paired()
    client = TestClient(create_app(FakeModel(), "local-only", pairing))
    assert client.get(
        "/health", headers={"X-Sorigul-Local-Bootstrap": "wrong"}
    ).status_code == 401
    assert client.get(
        "/health", headers={"X-Sorigul-Local-Bootstrap": "local-only"}
    ).status_code == 200


def test_signed_transcribe_passes_and_unsigned_never_calls_model(tmp_path, monkeypatch):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    session, pairing = paired()
    model = FakeModel()
    endpoint = transcribe_endpoint(create_app(model, "local-only", pairing))
    audio = b"test-owned-audio"
    unsigned = FakeRequest({}, audio)
    assert asyncio.run(endpoint(unsigned)).status_code == 401
    assert unsigned.form_calls == 0
    assert model.calls == 0
    headers = session.signed_headers(
        "POST", "/transcribe", hashlib.sha256(audio).hexdigest()
    )
    signed = FakeRequest(headers, audio)
    result = asyncio.run(endpoint(signed))
    assert result["text"] == "ok"
    assert signed.form_calls == 1
    assert model.calls == 1


def test_wrong_content_hash_rejected_before_model_call():
    session, pairing = paired()
    model = FakeModel()
    endpoint = transcribe_endpoint(create_app(model, "local-only", pairing))
    headers = session.signed_headers("POST", "/transcribe", "0" * 64)
    response = asyncio.run(endpoint(FakeRequest(headers, b"different")))
    assert response.status_code == 400
    assert model.calls == 0


def test_verifier_rejects_wrong_id_malformed_id_tampering_and_time_bounds():
    session, pairing = paired()
    valid = session.signed_headers("GET", "/health", EMPTY_SHA256, now=1_000)

    wrong_session = PairingRegistry().create()
    wrong = wrong_session.signed_headers("GET", "/health", EMPTY_SHA256, now=1_000)
    with pytest.raises(AuthenticationError):
        pairing.verify_headers(wrong, "GET", "/health", now=1_000)

    malformed = dict(valid)
    malformed["X-Sorigul-Request-Id"] = "not-a-pairing"
    with pytest.raises(AuthenticationError):
        pairing.verify_headers(malformed, "GET", "/health", now=1_000)

    tampered = dict(valid)
    signature = tampered["X-Sorigul-Signature"]
    tampered["X-Sorigul-Signature"] = ("A" if signature[0] != "A" else "B") + signature[1:]
    with pytest.raises(AuthenticationError):
        pairing.verify_headers(tampered, "GET", "/health", now=1_000)

    expired = session.signed_headers("GET", "/health", EMPTY_SHA256, now=800)
    with pytest.raises(AuthenticationError):
        pairing.verify_headers(expired, "GET", "/health", now=1_000)
    future = session.signed_headers("GET", "/health", EMPTY_SHA256, now=1_200)
    with pytest.raises(AuthenticationError):
        pairing.verify_headers(future, "GET", "/health", now=1_000)


def test_nonce_replay_is_rejected_and_new_pairing_revokes_old():
    old, pairing = paired()
    headers = old.signed_headers("GET", "/health", EMPTY_SHA256, now=1_000)
    pairing.verify_headers(headers, "GET", "/health", now=1_000)
    with pytest.raises(AuthenticationError):
        pairing.verify_headers(headers, "GET", "/health", now=1_000)

    new = PairingRegistry().create()
    _nonce, public_key = parse_request_id(new.request_id)
    pairing.activate(new.request_id, public_key)
    old_headers = old.signed_headers("GET", "/health", EMPTY_SHA256, now=1_000)
    with pytest.raises(AuthenticationError):
        pairing.verify_headers(old_headers, "GET", "/health", now=1_000)
    new_headers = new.signed_headers("GET", "/health", EMPTY_SHA256, now=1_000)
    pairing.verify_headers(new_headers, "GET", "/health", now=1_000)


def test_cloudflared_pin_is_exact_official_release_asset():
    assert CLOUDFLARED_VERSION == "2026.9.3"
    assert CLOUDFLARED_ASSET_URL.endswith(
        "/releases/download/2026.9.3/cloudflared-linux-amd64"
    )
    assert CLOUDFLARED_SHA256 == "77e26d8d900e0b8469f416239d14b5f296525fdf79fee6f511ef55609e3fbac2"


def test_rendezvous_rejects_malformed_request_id_before_ready_publish():
    payload = {
        "schema_version": 1,
        "request_id": "malformed",
        "url": "",
        "status": "REQUESTED",
        "updated_at": "2026-09-25T00:00:00+00:00",
        "expires_at": "2026-09-25T00:10:00+00:00",
    }
    from datetime import datetime, timezone

    assert build_ready_metadata(
        payload, "https://example.trycloudflare.com",
        now=datetime(2026, 9, 25, tzinfo=timezone.utc),
    ) is None


def test_cloudflared_hash_match_promotes_and_existing_valid_reuses(tmp_path):
    binary = tmp_path / "cloudflared"
    content = b"test-cloudflared"
    expected = hashlib.sha256(content).hexdigest()
    calls = []

    def download(url, destination, timeout):
        calls.append((url, timeout))
        Path(destination).write_bytes(content)

    ensure_cloudflared(
        str(binary), asset_url="https://example.test/pinned", expected_sha256=expected,
        timeout=7, downloader=download,
    )
    assert binary.read_bytes() == content
    ensure_cloudflared(
        str(binary), asset_url="https://example.test/pinned", expected_sha256=expected,
        timeout=7, downloader=lambda *_: pytest.fail("valid binary must be reused"),
    )
    assert calls == [("https://example.test/pinned", 7)]


def test_cloudflared_hash_mismatch_and_timeout_never_promote(tmp_path):
    binary = tmp_path / "cloudflared"
    binary.write_bytes(b"old-unverified")

    def mismatch(_url, destination, _timeout):
        Path(destination).write_bytes(b"wrong")

    with pytest.raises(RuntimeError, match="SHA-256"):
        ensure_cloudflared(str(binary), expected_sha256="0" * 64, downloader=mismatch)
    assert binary.read_bytes() == b"old-unverified"

    with pytest.raises(TimeoutError):
        ensure_cloudflared(
            str(binary), expected_sha256="0" * 64,
            downloader=lambda *_: (_ for _ in ()).throw(TimeoutError("bounded timeout")),
        )
    assert binary.read_bytes() == b"old-unverified"


def test_tunnel_uses_argument_list_and_shell_false(tmp_path):
    captured = {}

    class Process:
        pass

    def popen(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return Process()

    tunnel = start_tunnel("/verified/cloudflared", str(tmp_path / "tunnel.log"), popen=popen)
    tunnel.log_handle.close()
    assert captured["command"][0] == "/verified/cloudflared"
    assert captured["kwargs"]["shell"] is False
    assert isinstance(captured["command"], list)


def test_tunnel_cleanup_targets_and_waits_for_owned_process_only():
    calls = []

    class Process:
        def terminate(self):
            calls.append("terminate")

        def wait(self, timeout):
            calls.append(("wait", timeout))

    from colab.sorigul_colab_bootstrap import TunnelProcess

    log_handle = io.StringIO()
    stop_owned_tunnel(TunnelProcess(Process(), log_handle))
    assert calls == ["terminate", ("wait", 10)]
    assert log_handle.closed


def test_bootstrap_source_has_no_latest_wget_or_shell_true():
    source = (Path(__file__).resolve().parents[2] / "colab" / "sorigul_colab_bootstrap.py").read_text(
        encoding="utf-8"
    )
    assert "releases/latest" not in source
    assert "wget" not in source
    assert "shell=True" not in source
