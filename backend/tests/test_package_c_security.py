import hashlib
import json
import os
import stat
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.domain.transcription import EngineError
from src.engines.colab import DirectColabHttpClient
from src.services.colab_rendezvous import ColabRendezvousService
from src.services.colab_security import EMPTY_SHA256, PairingRegistry, parse_request_id
from src.services.colab_url import ColabUrlError, normalize_colab_base_url
from src.services.drive import write_private_file


class FakeDriveClient:
    def __init__(self):
        self.payload = None

    def find_or_create_folder(self, parent_id, name):
        return "folder"

    def find_file(self, parent_id, name):
        return None

    def create_text_file(self, parent_id, name, content):
        self.payload = content
        return "file"


class FakeAuth:
    def __init__(self, client):
        self.client = client

    def ensure_client(self):
        return self.client


class FakeResponse:
    status = 200

    def __init__(self, payload=b'{"text":"ok","segments":[]}'):
        self.payload = payload

    def read(self):
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def _header_map(request):
    return {key.lower(): value for key, value in request.header_items()}


def test_rendezvous_metadata_contains_only_public_pairing_identifier():
    drive = FakeDriveClient()
    registry = PairingRegistry()
    result = ColabRendezvousService(FakeAuth(drive), registry).start()
    payload = json.loads(drive.payload)

    assert set(payload) == {
        "schema_version", "request_id", "url", "status", "updated_at", "expires_at"
    }
    nonce, public_key = parse_request_id(result.request_id)
    assert len(nonce) == 24
    assert len(public_key) == 32
    assert "private" not in drive.payload.lower()
    assert "token" not in drive.payload.lower()
    assert "secret" not in drive.payload.lower()


def test_new_desktop_pairing_revokes_previous_session():
    registry = PairingRegistry()
    old = registry.create()
    new = registry.create()
    assert registry.lookup(old.request_id) is None
    assert registry.lookup(new.request_id) is new


def test_direct_colab_client_requires_pairing():
    with pytest.raises(EngineError) as caught:
        DirectColabHttpClient("https://example.test")
    assert caught.value.code == "COLAB_PAIRING_REQUIRED"


def test_direct_client_signs_health_and_audio_hash(tmp_path, monkeypatch):
    registry = PairingRegistry()
    session = registry.create()
    registry.bind(session.request_id, "https://example.test")
    captured = []

    def urlopen(request, **_kwargs):
        captured.append(request)
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    client = DirectColabHttpClient("https://example.test", session)
    client.check_health()
    audio = tmp_path / "chunk.mp3"
    audio.write_bytes(b"test-owned-audio")
    client.transcribe(audio)

    health_headers = _header_map(captured[0])
    post_headers = _header_map(captured[1])
    assert health_headers["x-sorigul-content-sha256"] == EMPTY_SHA256
    assert post_headers["x-sorigul-content-sha256"] == hashlib.sha256(
        b"test-owned-audio"
    ).hexdigest()
    for name in (
        "x-sorigul-request-id", "x-sorigul-timestamp", "x-sorigul-nonce",
        "x-sorigul-content-sha256", "x-sorigul-signature",
    ):
        assert name in health_headers
        assert name in post_headers


@pytest.mark.parametrize(
    "url,expected",
    [
        ("http://localhost:8000", "http://localhost:8000"),
        ("http://127.0.0.1:8000/health", "http://127.0.0.1:8000"),
        ("http://[::1]:8000/transcribe", "http://[::1]:8000"),
        ("https://example.test", "https://example.test"),
    ],
)
def test_colab_url_secure_transport_policy_accepts(url, expected):
    assert normalize_colab_base_url(url) == expected


def test_colab_url_secure_transport_policy_rejects_remote_http():
    with pytest.raises(ColabUrlError):
        normalize_colab_base_url("http://example.test")


def test_private_file_posix_mode_is_0600(tmp_path):
    target = tmp_path / "token.json"
    chmod_calls = []
    original_chmod = os.chmod
    try:
        os.chmod = lambda path, mode: chmod_calls.append((Path(path), mode))
        write_private_file(target, '{"token":"test-only"}', platform_name="posix")
    finally:
        os.chmod = original_chmod
    assert chmod_calls and chmod_calls[-1][1] == 0o600
    assert target.exists()


def test_private_file_windows_acl_uses_exact_sid_before_publish(tmp_path):
    target = tmp_path / "token.json"
    calls = []

    def run(args, **kwargs):
        calls.append((list(args), target.exists(), dict(kwargs)))
        if args[0] == "whoami.exe":
            return SimpleNamespace(stdout='"desktop-user","S-1-5-21-123"\n')
        return SimpleNamespace(stdout="")

    write_private_file(target, "test-token", platform_name="nt", run=run)
    assert target.read_text(encoding="utf-8") == "test-token"
    assert calls[1][0][0] == "icacls.exe"
    assert calls[1][0][-3:] == ["/inheritance:r", "/grant:r", "*S-1-5-21-123:(F)"]
    assert calls[1][1] is False
    assert calls[1][2]["shell"] is False


def test_private_file_acl_failure_never_publishes_and_cleans_temp(tmp_path):
    target = tmp_path / "token.json"

    def run(args, **_kwargs):
        if args[0] == "whoami.exe":
            return SimpleNamespace(stdout='"desktop-user","S-1-5-21-123"\n')
        raise subprocess.CalledProcessError(5, args)

    with pytest.raises(subprocess.CalledProcessError):
        write_private_file(target, "test-token", platform_name="nt", run=run)
    assert not target.exists()
    assert list(tmp_path.iterdir()) == []
