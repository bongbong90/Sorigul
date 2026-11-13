import json
import logging
import socket
import ssl
import traceback
import urllib.error
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from websockets.datastructures import Headers
from websockets.exceptions import InvalidStatus
from websockets.http11 import Response

from src.services import colab_jupyter_client as module
from src.services.colab_jupyter_client import (
    ColabJupyterClient, JupyterClientError, JupyterCode as Code, VALIDATION_CODE,
)
from src.services.colab_runtime_client import ConnectionInfo


TOKEN = "mock-proxy-secret"
URL = "https://runtime.example.invalid/prefix"
NOW = datetime(2026, 11, 13, tzinfo=timezone.utc)


def info(token=TOKEN, url=URL, expiry=None):
    return ConnectionInfo(url, token, expiry or NOW + timedelta(hours=1))


class FakeWS:
    def __init__(self):
        self.sent = []
        self.frames = ["reply", "idle"]
        self.reply_status = "ok"
        self.timeouts = []
        self.closed = False
        self.close_error = False
        self.send_error = None

    def send(self, raw):
        self.sent.append(json.loads(raw))
        if self.send_error:
            raise self.send_error

    def recv(self, timeout):
        self.timeouts.append(timeout)
        if not self.frames:
            raise TimeoutError(TOKEN + URL)
        kind = self.frames.pop(0)
        if isinstance(kind, Exception):
            raise kind
        if callable(kind):
            return kind()
        if isinstance(kind, dict):
            return json.dumps(kind)
        parent = self.sent[0]["header"]["msg_id"]
        if kind == "unrelated":
            parent = "someone-else"
            kind = "reply"
        return json.dumps({
            "header": {"msg_type": "execute_reply" if kind == "reply" else "status"},
            "parent_header": {"msg_id": parent},
            "channel": "shell" if kind == "reply" else "iopub",
            "content": {"status": self.reply_status, "execution_state": "idle",
                        "traceback": [TOKEN + URL]},
        })

    def close(self):
        if self.close_error:
            raise OSError(TOKEN + URL)
        self.closed = True


class FakeServer:
    def __init__(self):
        self.calls = []
        self.connections = []
        self.ws = FakeWS()
        self.create_status = 201
        self.create_payload = {"id": "owned-kernel"}
        self.delete_status = 204
        self.create_error = None
        self.ws_error = None
        self.on_delete = None

    def http(self, method, url, headers, body, timeout):
        self.calls.append((method, url, headers, body, timeout))
        assert "Authorization" not in headers
        assert headers["X-Colab-Runtime-Proxy-Token"] in (TOKEN, "renewed-proxy")
        assert timeout > 0
        if method == "POST":
            assert url == URL + "/api/kernels"
            assert body == {"name": "python3"}
            if self.create_error:
                raise self.create_error
            return self.create_status, self.create_payload
        assert method == "DELETE" and url == URL + "/api/kernels/owned-kernel"
        if self.on_delete:
            self.on_delete()
        return self.delete_status, None

    def connect(self, url, headers, timeout):
        self.connections.append((url, headers, timeout))
        assert url.startswith("wss://runtime.example.invalid/prefix/api/kernels/owned-kernel/channels?")
        assert headers == {"X-Colab-Runtime-Proxy-Token": TOKEN}
        if self.ws_error:
            raise self.ws_error
        return self.ws


@pytest.fixture(autouse=True)
def deny_external_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("External network forbidden in PHASE 03 tests")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)


@pytest.fixture
def setup_client():
    server = FakeServer()
    client = ColabJupyterClient(info(), http_request=server.http, ws_connect=server.connect,
                                utcnow=lambda: NOW)
    return client, server


@pytest.mark.parametrize("frames", [["reply", "idle"], ["idle", "reply"],
                                   ["unrelated", "reply", "idle"]])
def test_fixed_single_command_correlated_completion_and_cleanup(setup_client, frames):
    client, server = setup_client
    server.ws.frames = frames
    result = client.run_validation()
    assert result.execution_status == "OK" and result.error_code is None
    assert result.execute_reply_received and result.iopub_idle_received
    assert result.cleanup.kernel_deleted and result.cleanup.connection_closed
    assert not result.cleanup.cleanup_required
    assert len(server.connections) == len(server.ws.sent) == 1
    request = server.ws.sent[0]
    assert uuid.UUID(request["header"]["msg_id"]).version == 4
    assert request["content"] == {
        "code": VALIDATION_CODE, "silent": True, "store_history": False,
        "user_expressions": {}, "allow_stdin": False, "stop_on_error": True,
    }
    assert all(0 < value <= 15 for value in server.ws.timeouts)
    assert server.ws.closed
    with pytest.raises(JupyterClientError) as error:
        client.run_validation()
    assert error.value.code == Code.DUPLICATE_EXECUTION
    assert len(server.ws.sent) == 1


def test_msg_ids_differ_between_independent_validation_attempts():
    ids = []
    for _ in range(2):
        server = FakeServer()
        ColabJupyterClient(info(), http_request=server.http, ws_connect=server.connect,
                           utcnow=lambda: NOW).run_validation()
        ids.append(server.ws.sent[0]["header"]["msg_id"])
    assert len(set(ids)) == 2


@pytest.mark.parametrize("status", ["error", "aborted"])
def test_execute_error_is_separate_from_successful_cleanup(setup_client, status):
    client, server = setup_client
    server.ws.reply_status = status
    result = client.run_validation()
    assert result.execution_status == "ERROR"
    assert result.error_code == Code.EXECUTION_FAILED
    assert result.cleanup.kernel_deleted and not result.cleanup.cleanup_required


@pytest.mark.parametrize("frames", [["reply"], ["idle"], ["unrelated", "idle"],
    ["reply", "reply", "idle"], [ConnectionError(TOKEN + URL)]])
def test_missing_or_ambiguous_completion_is_uncertain_never_reexecuted(setup_client, frames):
    client, server = setup_client
    server.ws.frames = frames
    result = client.run_validation()
    assert result.execution_status == "STATE_UNCERTAIN"
    assert result.error_code == Code.STATE_UNCERTAIN
    assert len(server.ws.sent) == 1 and len(server.connections) == 1
    assert result.cleanup.kernel_deleted


def test_wrong_channel_does_not_complete_current_command(setup_client):
    client, server = setup_client
    def wrong_channel():
        return json.dumps({"header": {"msg_type": "execute_reply"},
            "parent_header": {"msg_id": server.ws.sent[0]["header"]["msg_id"]},
            "channel": "iopub", "content": {"status": "ok"}})
    server.ws.frames = [wrong_channel, "idle"]
    result = client.run_validation()
    assert not result.execute_reply_received and result.execution_status == "STATE_UNCERTAIN"


@pytest.mark.parametrize("failure,expected", [(ConnectionError(TOKEN), Code.CONNECTION_REJECTED),
    (TimeoutError(URL), Code.NETWORK_TIMEOUT),
    (InvalidStatus(Response(403, "Forbidden", Headers())), Code.AUTH_REJECTED)])
def test_websocket_connect_refusal_cleans_kernel(setup_client, failure, expected):
    client, server = setup_client
    server.ws_error = failure
    result = client.run_validation()
    assert result.execution_status == "NOT_RUN" and result.error_code == expected
    assert result.cleanup.kernel_deleted
    assert not server.ws.sent and len(server.connections) == 1


def test_expired_proxy_token_never_used():
    server = FakeServer()
    client = ColabJupyterClient(info(expiry=NOW - timedelta(seconds=1)),
        http_request=server.http, ws_connect=server.connect, utcnow=lambda: NOW)
    result = client.run_validation()
    assert result.error_code == Code.TOKEN_REFRESH_REQUIRED
    assert server.calls == server.connections == []
    assert not result.cleanup.cleanup_required


def test_expiry_during_wait_requires_refresh_for_cleanup(setup_client):
    client, server = setup_client
    current = [NOW]
    client._utcnow = lambda: current[0]
    def expire():
        current[0] += timedelta(hours=2)
        return json.dumps({})
    server.ws.frames = [expire]
    result = client.run_validation()
    assert result.execution_status == "STATE_UNCERTAIN"
    assert result.error_code == Code.TOKEN_REFRESH_REQUIRED
    assert result.cleanup.cleanup_required and not result.cleanup.kernel_deleted
    assert len(server.calls) == 1  # Expired credential not sent for DELETE.
    client._refresh = lambda: info(token="renewed-proxy", expiry=current[0] + timedelta(hours=1))
    client.refresh_connection()
    assert client.cleanup().kernel_deleted
    assert len(server.ws.sent) == 1


@pytest.mark.parametrize("new_info", [info(url="https://other.example.invalid"),
    info(url=URL + "/other"), info(expiry=NOW - timedelta(seconds=1))])
def test_refresh_rejects_different_origin_path_or_expired_token(new_info):
    client = ColabJupyterClient(info(), refresh_connection=lambda: new_info, utcnow=lambda: NOW)
    with pytest.raises(JupyterClientError) as error:
        client.refresh_connection()
    assert error.value.code == Code.TOKEN_REFRESH_REQUIRED


def test_explicit_preexpiry_refresh_uses_owned_runtime_callback_once():
    lookups = []
    def lookup():
        lookups.append("get_owned_runtime")
        return info(token="renewed-proxy")
    client = ColabJupyterClient(info(), refresh_connection=lookup, utcnow=lambda: NOW)
    client.refresh_connection()
    assert lookups == ["get_owned_runtime"]
    assert client._info.token == "renewed-proxy"


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_kernel_delete_failure_kept_separate_and_explicit_retry(setup_client, status):
    client, server = setup_client
    server.delete_status = status
    result = client.run_validation()
    assert result.execution_status == "OK"
    assert result.cleanup.error_code == Code.KERNEL_DELETE_FAILED
    assert not result.cleanup.kernel_deleted and result.cleanup.cleanup_required
    server.delete_status = 204
    assert client.cleanup().kernel_deleted
    assert len(server.ws.sent) == 1


def test_websocket_close_failure_does_not_prevent_kernel_delete(setup_client):
    client, server = setup_client
    server.ws.close_error = True
    result = client.run_validation()
    assert result.execution_status == "OK" and result.cleanup.kernel_deleted
    assert not result.cleanup.connection_closed and result.cleanup.cleanup_required
    assert result.cleanup.error_code == Code.CONNECTION_CLOSE_FAILED
    server.ws.close_error = False
    assert not client.cleanup().cleanup_required


@pytest.mark.parametrize("failure", [TimeoutError(TOKEN + URL), OSError(TOKEN + URL)])
def test_kernel_create_response_loss_never_deletes_unknown_kernels(setup_client, failure):
    client, server = setup_client
    server.create_error = failure
    result = client.run_validation()
    assert result.execution_status == "STATE_UNCERTAIN" and result.cleanup.cleanup_required
    assert not result.cleanup.kernel_deleted and len(server.calls) == 1
    assert client.cleanup().cleanup_required


@pytest.mark.parametrize("url", ["http://runtime.example.invalid", "wss://runtime.example.invalid",
    "https://user:pass@runtime.example.invalid", URL + "?token=" + TOKEN,
    URL + "#secret", URL + "/../other", URL + "/%2e%2e", URL + "\n", URL + ":8080"])
def test_invalid_connection_urls_fail_closed(url):
    with pytest.raises(JupyterClientError) as error:
        ColabJupyterClient(info(url=url))
    assert error.value.code == Code.INVALID_CONNECTION
    assert TOKEN not in "".join(traceback.format_exception(error.value))


def test_tokens_and_connection_url_absent_from_logs_repr_and_traceback(setup_client, caplog):
    client, server = setup_client
    server.ws_error = RuntimeError(TOKEN + URL)
    with caplog.at_level(logging.DEBUG):
        result = client.run_validation()
    text = caplog.text + repr(result) + repr(client) + repr(info())
    assert TOKEN not in text and URL not in text


def test_message_limit_and_deadline_bound_wait(setup_client):
    client, server = setup_client
    client._max_messages = 2
    server.ws.frames = ["unrelated"] * 10
    result = client.run_validation()
    assert result.error_code == Code.STATE_UNCERTAIN
    assert len(server.ws.timeouts) == 2
    assert len(server.ws.sent) == 1


def test_slow_matching_response_cannot_pass_after_deadline(setup_client):
    client, server = setup_client
    ticks = iter([0, 0, 16])
    client._clock = lambda: next(ticks)
    result = client.run_validation()
    assert result.execution_status == "STATE_UNCERTAIN" and result.cleanup.kernel_deleted


def test_send_failure_never_resends(setup_client):
    client, server = setup_client
    server.ws.send_error = TimeoutError(TOKEN + URL)
    result = client.run_validation()
    assert result.execution_status == "STATE_UNCERTAIN"
    assert len(server.ws.sent) == 1 and result.cleanup.kernel_deleted


def test_production_ws_adapter_rejects_redirect_before_second_connection(monkeypatch):
    attempts = []
    def redirect(self, deadline):
        attempts.append(self.uri)
        raise InvalidStatus(Response(302, "Found", Headers({"Location": "wss://attacker.invalid/"})))
    monkeypatch.setattr(module._NoRedirectWS, "open_connection", redirect)
    with pytest.raises(InvalidStatus):
        module._connect_ws("wss://runtime.example.invalid/?token=" + TOKEN, {}, 1)
    assert len(attempts) == 1


def test_production_ws_adapter_security_and_private_logger(monkeypatch, caplog):
    options = {}
    class FakeSocket:
        def settimeout(self, timeout):
            options["socket_timeout"] = timeout
    class Connector:
        def __init__(self, url, **kwargs):
            options.update(kwargs)
            kwargs["logger"].critical(url + TOKEN)
        def connect(self):
            return type("Connection", (), {"socket": FakeSocket()})()
    monkeypatch.setattr(module, "_NoRedirectWS", Connector)
    with caplog.at_level(logging.DEBUG):
        module._connect_ws("wss://runtime.example.invalid/?token=" + TOKEN, {}, 2)
    assert options["proxy"] is None and options["compression"] is None
    assert options["ssl"].verify_mode == ssl.CERT_REQUIRED
    assert options["ssl"].check_hostname
    assert options["socket_timeout"] == options["open_timeout"] == options["close_timeout"] == 2
    assert TOKEN not in caplog.text and "runtime.example.invalid" not in caplog.text


def test_production_http_adapter_does_not_follow_or_log_redirect(monkeypatch, caplog):
    captured = []
    class Opener:
        def open(self, request, timeout):
            captured.append(request)
            raise urllib.error.HTTPError(request.full_url, 302, TOKEN, {}, None)
    def build(*handlers):
        assert any(isinstance(h, module._NoRedirectHTTP) for h in handlers)
        return Opener()
    monkeypatch.setattr(module.urllib.request, "build_opener", build)
    with caplog.at_level(logging.DEBUG):
        assert module._http_request("POST", URL, {"X-Colab-Runtime-Proxy-Token": TOKEN}, {}, 1) == (302, None)
    assert len(captured) == 1
    assert module._NoRedirectHTTP().redirect_request(None, None, 302, "", {}, "https://attacker.invalid") is None
    assert URL not in caplog.text and TOKEN not in caplog.text


def test_completed_cleanup_is_idempotent_and_keeps_deletion_evidence(setup_client):
    client, server = setup_client
    client.run_validation()
    result = client.cleanup()
    assert result.kernel_deleted and not result.cleanup_required
    assert len([call for call in server.calls if call[0] == "DELETE"]) == 1


@pytest.mark.parametrize("payload", [{}, {"id": "../other-kernel"}, None])
def test_invalid_create_id_never_used_for_deletion(setup_client, payload):
    client, server = setup_client
    server.create_payload = payload
    result = client.run_validation()
    assert result.error_code == Code.STATE_UNCERTAIN
    assert result.cleanup.cleanup_required and len(server.calls) == 1
    assert not server.connections


def test_create_auth_rejection_has_no_owned_kernel(setup_client):
    client, server = setup_client
    server.create_status = 401
    result = client.run_validation()
    assert result.execution_status == "NOT_RUN" and result.error_code == Code.AUTH_REJECTED
    assert not result.cleanup.cleanup_required and len(server.calls) == 1


def test_http_timeout_is_sanitized_without_exception_chain(monkeypatch):
    class Opener:
        def open(self, *args, **kwargs):
            raise urllib.error.URLError(TimeoutError(TOKEN + URL))
    monkeypatch.setattr(module.urllib.request, "build_opener", lambda *args: Opener())
    with pytest.raises(JupyterClientError) as error:
        module._http_request("POST", URL, {}, {}, 1)
    assert error.value.code == Code.NETWORK_TIMEOUT
    assert error.value.__context__ is None
    assert TOKEN not in "".join(traceback.format_exception(error.value))


def test_websocket_dependency_supports_existing_uvicorn_auto_configuration():
    # Installing websockets changes Uvicorn's auto discovery; check import/load
    # compatibility without opening a listener or importing product API routes.
    import uvicorn
    async def app(scope, receive, send):
        pass
    config = uvicorn.Config(app, ws="auto", log_config=None)
    config.load()
    assert config.loaded and config.ws_protocol_class is not None


def test_caller_interrupt_still_attempts_owned_kernel_cleanup(setup_client):
    client, server = setup_client
    server.ws.frames = [KeyboardInterrupt()]
    # FakeWS normally treats Exception outcomes specially; model an interrupt
    # from recv directly without converting it into a transport error.
    def interrupt(timeout):
        raise KeyboardInterrupt
    server.ws.recv = interrupt
    with pytest.raises(KeyboardInterrupt):
        client.run_validation()
    assert server.ws.closed
    assert [call[0] for call in server.calls] == ["POST", "DELETE"]
