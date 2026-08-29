"""Google OAuth desktop loopback callback tests.

No real Google domain is ever contacted. `google_auth_oauthlib.flow.Flow` is
stubbed via `sys.modules` so `GoogleOAuthService.start()` can be exercised
end-to-end (redirect_uri wiring) without the real dependency installed.
`LoopbackCallbackServer` itself is exercised with real 127.0.0.1 sockets --
no external network is used, only loopback.
"""

import sys
import threading
import types
import urllib.error
import urllib.request

import pytest

from src.domain.models import DriveAuthState
from src.services.drive import GoogleOAuthService, LoopbackCallbackServer


def test_dynamic_port_allocation_never_uses_a_fixed_port():
    server_a = LoopbackCallbackServer("state-a")
    server_b = LoopbackCallbackServer("state-b")
    try:
        assert server_a.port != 0
        assert server_b.port != 0
        assert server_a.port != server_b.port
        assert server_a.redirect_uri == f"http://127.0.0.1:{server_a.port}/"
    finally:
        server_a.shutdown()
        server_b.shutdown()


def test_callback_listener_starts_serves_one_request_and_stops():
    server = LoopbackCallbackServer("expected-state")
    server.start()
    try:
        response = urllib.request.urlopen(
            f"http://127.0.0.1:{server.port}/?state=expected-state&code=auth-code-1", timeout=5
        )
        assert response.status == 200
        body = response.read().decode("utf-8")
        assert "연결이 완료" in body
        assert "auth-code-1" not in body  # code never echoed back to the browser

        code = server.wait_for_code(timeout=5)
        assert code == "auth-code-1"

        # Listener is shut down after a captured callback: a further
        # request must fail to connect rather than serve stale state.
        with pytest.raises(OSError):
            urllib.request.urlopen(f"http://127.0.0.1:{server.port}/", timeout=1)
    finally:
        server.shutdown()


def test_incorrect_state_is_rejected_without_consuming_the_outcome():
    server = LoopbackCallbackServer("expected-state")
    server.start()
    try:
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            urllib.request.urlopen(
                f"http://127.0.0.1:{server.port}/?state=wrong-state&code=attacker-code", timeout=5
            )
        assert excinfo.value.code == 400

        # The legitimate callback must still be accepted afterwards.
        urllib.request.urlopen(
            f"http://127.0.0.1:{server.port}/?state=expected-state&code=real-code", timeout=5
        )
        assert server.wait_for_code(timeout=5) == "real-code"
    finally:
        server.shutdown()


def test_missing_code_resolves_to_no_code():
    server = LoopbackCallbackServer("expected-state")
    server.start()
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{server.port}/?state=expected-state", timeout=5)
        assert server.wait_for_code(timeout=5) is None
    finally:
        server.shutdown()


def test_callback_timeout_returns_none_without_hanging():
    server = LoopbackCallbackServer("expected-state")
    server.start()
    try:
        assert server.wait_for_code(timeout=0.3) is None
    finally:
        server.shutdown()


def test_duplicate_callback_only_captures_the_first_code():
    server = LoopbackCallbackServer("expected-state")
    server.start()
    try:
        barrier_ready = threading.Event()

        def fire(code: str):
            barrier_ready.wait(2)
            try:
                urllib.request.urlopen(
                    f"http://127.0.0.1:{server.port}/?state=expected-state&code={code}", timeout=5
                )
            except OSError:
                pass  # the loser may find the socket already closing

        threads = [
            threading.Thread(target=fire, args=("first",)),
            threading.Thread(target=fire, args=("second",)),
        ]
        for thread in threads:
            thread.start()
        barrier_ready.set()
        for thread in threads:
            thread.join(timeout=5)

        code = server.wait_for_code(timeout=5)
        assert code in ("first", "second")  # exactly one was captured
    finally:
        server.shutdown()


def test_request_logging_is_silenced_so_the_code_never_reaches_stderr(capsys):
    server = LoopbackCallbackServer("expected-state")
    server.start()
    try:
        urllib.request.urlopen(
            f"http://127.0.0.1:{server.port}/?state=expected-state&code=must-not-be-logged", timeout=5
        )
        server.wait_for_code(timeout=5)
    finally:
        server.shutdown()
    captured = capsys.readouterr()
    assert "must-not-be-logged" not in captured.err
    assert "must-not-be-logged" not in captured.out


class _FakeCredentials:
    def to_json(self) -> str:
        return '{"token": "fake-token-never-logged"}'


class _FakeFlow:
    last_redirect_uri: "str | None" = None

    def __init__(self, redirect_uri: str):
        self.redirect_uri = redirect_uri
        self.credentials = None
        _FakeFlow.last_redirect_uri = redirect_uri

    @classmethod
    def from_client_secrets_file(cls, path, scopes, redirect_uri):
        return cls(redirect_uri=redirect_uri)

    def authorization_url(self, **kwargs):
        return (
            f"https://accounts.google.com/o/oauth2/auth?redirect_uri={self.redirect_uri}",
            kwargs["state"],
        )

    def fetch_token(self, code: str) -> None:
        self.credentials = _FakeCredentials()


@pytest.fixture
def fake_google_auth_oauthlib(monkeypatch):
    fake_pkg = types.ModuleType("google_auth_oauthlib")
    fake_flow_mod = types.ModuleType("google_auth_oauthlib.flow")
    fake_flow_mod.Flow = _FakeFlow
    monkeypatch.setitem(sys.modules, "google_auth_oauthlib", fake_pkg)
    monkeypatch.setitem(sys.modules, "google_auth_oauthlib.flow", fake_flow_mod)
    yield
    _FakeFlow.last_redirect_uri = None


def test_start_wires_the_loopback_redirect_uri_into_authorization_url(tmp_path, fake_google_auth_oauthlib):
    credential_path = tmp_path / "google_oauth_client.json"
    credential_path.write_text("{}", encoding="utf-8")
    token_path = tmp_path / "google_drive_token.json"

    service = GoogleOAuthService(credential_path, token_path)
    result = service.start()

    assert result["authorization_url"].startswith("https://accounts.google.com/")
    assert _FakeFlow.last_redirect_uri is not None
    assert _FakeFlow.last_redirect_uri.startswith("http://127.0.0.1:")
    assert _FakeFlow.last_redirect_uri.endswith("/")
    assert _FakeFlow.last_redirect_uri in result["authorization_url"]
    assert service.state == DriveAuthState.AUTHORIZING


def test_automatic_callback_completes_the_flow_without_manual_paste(tmp_path, fake_google_auth_oauthlib):
    credential_path = tmp_path / "google_oauth_client.json"
    credential_path.write_text("{}", encoding="utf-8")
    token_path = tmp_path / "google_drive_token.json"

    service = GoogleOAuthService(credential_path, token_path)
    result = service.start()

    port = _FakeFlow.last_redirect_uri.split(":")[2].rstrip("/")
    urllib.request.urlopen(
        f"http://127.0.0.1:{port}/?state={result['state']}&code=automatic-code", timeout=5
    )

    for _ in range(50):
        if service.state == DriveAuthState.CONNECTED:
            break
        threading.Event().wait(0.1)

    assert service.state == DriveAuthState.CONNECTED
    assert token_path.exists()
    assert "automatic-code" not in token_path.read_text(encoding="utf-8")
