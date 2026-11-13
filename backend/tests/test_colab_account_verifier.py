import hashlib
import io
import json
import logging
import socket
import ssl
import urllib.error
from email.message import Message

import httpx
import pytest

from src.services import colab_account_verifier as module
from src.services.colab_account_verifier import GoogleAccountVerifier, GOOGLE_ISSUER, GOOGLE_USERINFO_ENDPOINT
from src.services.colab_runtime_client import ColabRuntimeClient, RuntimeClientError, RuntimeErrorCode as Code
from src.services.colab_runtime_ownership import OwnershipStore, OwnershipState as State, RuntimeOwnership
from test_colab_runtime_client import Server, OAUTH, PROXY


SUBJECT = "MockStableSubject-a_123"
EMAIL = "private-person@example.invalid"
NAME = "Private Mock Person"


class Response:
    def __init__(self, payload=None, *, status=200, raw=None,
                 url=GOOGLE_USERINFO_ENDPOINT, content_type="application/json"):
        self.status, self.url = status, url
        self.headers = Message()
        self.headers["Content-Type"] = content_type
        self.raw = raw if raw is not None else json.dumps(payload).encode()
        self.closed = False
        self.requested_limit = None

    def geturl(self):
        return self.url

    def read(self, limit):
        self.requested_limit = limit
        return self.raw[:limit]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True


class Opener:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def open(self, request, *, timeout):
        self.calls.append((request, timeout))
        result = self.outcomes.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def fingerprint(subject=SUBJECT):
    return hashlib.sha256((GOOGLE_ISSUER + "\0" + subject).encode()).hexdigest()


@pytest.fixture(autouse=True)
def deny_external_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("External network forbidden in PHASE 05")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", forbidden)


def test_exact_access_token_fixed_endpoint_and_fingerprint_only():
    response = Response({"sub": SUBJECT, "name": NAME, "email": EMAIL})
    opener = Opener([response])
    verifier = GoogleAccountVerifier(opener=opener, timeout_seconds=2)
    assert verifier(OAUTH) == fingerprint()
    request, timeout = opener.calls[0]
    assert request.full_url == GOOGLE_USERINFO_ENDPOINT
    assert request.get_method() == "GET"
    assert request.get_header("Authorization") == "Bearer " + OAUTH
    assert request.data is None and timeout == 2
    assert response.closed and response.requested_limit == module.MAX_RESPONSE_BYTES + 1
    assert OAUTH not in repr(verifier) and SUBJECT not in repr(verifier)


def test_refreshed_token_same_subject_gives_same_identity_without_cache():
    opener = Opener([Response({"sub": SUBJECT}), Response({"sub": SUBJECT, "email": "changed@example.invalid"})])
    verifier = GoogleAccountVerifier(opener=opener)
    assert verifier(OAUTH) == verifier("mock-renewed-access-token") == fingerprint()
    assert [request.get_header("Authorization") for request, _ in opener.calls] == [
        "Bearer " + OAUTH, "Bearer mock-renewed-access-token"]


def test_subject_case_and_account_difference_are_preserved():
    opener = Opener([Response({"sub": "subjectA"}), Response({"sub": "subjecta"})])
    verifier = GoogleAccountVerifier(opener=opener)
    assert verifier(OAUTH) != verifier(OAUTH)


@pytest.mark.parametrize("subject", [None, "", 123, True, [], {}, "a" * 256,
    "contains space", "line\nbreak", "\x00", "\x7f", "한글"])
def test_invalid_subject_never_uses_email_or_name(subject):
    opener = Opener([Response({"sub": subject, "email": EMAIL, "name": NAME})])
    assert GoogleAccountVerifier(opener=opener)(OAUTH) is None
    assert len(opener.calls) == 1


@pytest.mark.parametrize("payload", [{}, {"email": EMAIL, "name": NAME}, [], None,
    {"sub": SUBJECT, "iss": "https://attacker.invalid"},
    {"sub": SUBJECT, "error": "insufficient_scope"}])
def test_missing_identity_or_untrusted_response_fails_closed(payload):
    assert GoogleAccountVerifier(opener=Opener([Response(payload)]))(OAUTH) is None


@pytest.mark.parametrize("token", [None, "", " ", "invalid token", "x\r\nHeader: y", PROXY + "\x00", 123])
def test_invalid_bearer_is_rejected_before_http(token):
    opener = Opener([])
    assert GoogleAccountVerifier(opener=opener)(token) is None
    assert opener.calls == []


@pytest.mark.parametrize("status", [301, 302, 307, 308, 400, 401, 403, 429, 500])
def test_denied_expired_revoked_or_scope_missing_never_retries(status):
    opener = Opener([Response({"error": "insufficient_scope", "error_description": OAUTH + SUBJECT}, status=status)])
    assert GoogleAccountVerifier(opener=opener)(OAUTH) is None
    assert len(opener.calls) == 1


@pytest.mark.parametrize("raw", [b"{broken", b'{}', b'null', b'{"sub":"a","sub":"b"}', b'\xff',
    b"x" * (module.MAX_RESPONSE_BYTES + 1)])
def test_malformed_duplicate_or_oversized_json_rejected(raw):
    assert GoogleAccountVerifier(opener=Opener([Response(raw=raw)]))(OAUTH) is None


@pytest.mark.parametrize("response", [Response({"sub": SUBJECT}, url="https://attacker.invalid"),
    Response({"sub": SUBJECT}, content_type="text/html")])
def test_unexpected_response_origin_or_content_type_rejected(response):
    assert GoogleAccountVerifier(opener=Opener([response]))(OAUTH) is None


@pytest.mark.parametrize("failure", [TimeoutError(OAUTH + SUBJECT + EMAIL),
    urllib.error.URLError(TimeoutError(OAUTH + SUBJECT)),
    ssl.SSLCertVerificationError(OAUTH + SUBJECT),
    urllib.error.HTTPError(GOOGLE_USERINFO_ENDPOINT, 403, EMAIL + OAUTH, {}, None)])
def test_transport_error_contains_no_credentials_or_pii_in_logs(failure, caplog):
    opener = Opener([failure])
    with caplog.at_level(logging.DEBUG):
        result = GoogleAccountVerifier(opener=opener)(OAUTH)
    assert result is None and len(opener.calls) == 1
    for private in (OAUTH, SUBJECT, EMAIL):
        assert private not in caplog.text


def test_runtime_client_contract_converts_verification_denial_to_existing_error():
    verifier = GoogleAccountVerifier(opener=Opener([Response({}, status=403)]))
    client = ColabRuntimeClient(OAUTH, transport=httpx.MockTransport(lambda request: pytest.fail("Runtime API forbidden")),
                                account_verifier=verifier)
    try:
        with pytest.raises(RuntimeClientError) as error:
            client.verified_account_binding()
        assert error.value.code == Code.PRECONDITION_UNVERIFIED
    finally:
        client.close()


@pytest.mark.parametrize("payload,status,expected", [
    ({"sub": "different-account"}, 200, Code.NOT_OWNED),
    ({"error": "invalid_token"}, 401, Code.PRECONDITION_UNVERIFIED),
    ({"error": "insufficient_scope"}, 403, Code.PRECONDITION_UNVERIFIED),
])
def test_wrong_or_unverifiable_account_at_recovery_blocks_runtime_calls(tmp_path, payload, status, expected):
    # Build a valid record using the actual callable adapter and Mock APIs, then
    # change only Google's UserInfo subject for the restarted client.
    server = Server()
    opener = Opener([Response({"sub": SUBJECT}) for _ in range(12)])
    verifier = GoogleAccountVerifier(opener=opener)
    store = OwnershipStore(tmp_path / "ownership")
    client = ColabRuntimeClient(OAUTH, transport=httpx.MockTransport(server.handle), account_verifier=verifier)
    owner = RuntimeOwnership(store, client)
    try:
        owner.create()
        record = store.load()[0]
    finally:
        owner.close()
        client.close()
    path = store.root / (record.execution_id + ".json")
    previous = path.read_bytes()
    assert record.account_binding == fingerprint()
    for private in (OAUTH, PROXY, SUBJECT, EMAIL):
        assert private.encode() not in previous
    recovered = ColabRuntimeClient(OAUTH, transport=httpx.MockTransport(lambda request: pytest.fail("Runtime query/delete forbidden")),
        account_verifier=GoogleAccountVerifier(opener=Opener([Response(payload, status=status)])))
    try:
        result = RuntimeOwnership(OwnershipStore(store.root), recovered).recover(record.execution_id)
        assert result.state == State.BLOCKED and result.error_code == expected
        assert path.read_bytes() == previous
    finally:
        recovered.close()


def test_revoked_previously_verified_token_is_not_served_from_cache():
    opener = Opener([Response({"sub": SUBJECT}), Response({}, status=401)])
    verifier = GoogleAccountVerifier(opener=opener)
    assert verifier(OAUTH) == fingerprint()
    assert verifier(OAUTH) is None
    assert len(opener.calls) == 2


def test_default_http_configuration_has_tls_no_proxy_no_redirect(monkeypatch):
    handlers = []
    opener = Opener([Response({"sub": SUBJECT})])
    def build(*args):
        handlers.extend(args)
        return opener
    monkeypatch.setattr(module.urllib.request, "build_opener", build)
    assert GoogleAccountVerifier()(OAUTH) == fingerprint()
    redirect = next(handler for handler in handlers if isinstance(handler, module._NoRedirect))
    assert redirect.redirect_request(None, None, 302, "", {}, "https://attacker.invalid") is None
    proxy = next(handler for handler in handlers if isinstance(handler, module.urllib.request.ProxyHandler))
    assert proxy.proxies == {}
    tls = next(handler for handler in handlers if isinstance(handler, module.urllib.request.HTTPSHandler))
    assert tls._context.check_hostname and tls._context.verify_mode == ssl.CERT_REQUIRED


def test_http_denial_closes_error_response_without_reading_or_logging_it():
    body = io.BytesIO((OAUTH + SUBJECT + EMAIL).encode())
    error = urllib.error.HTTPError(GOOGLE_USERINFO_ENDPOINT, 403, "Forbidden", {}, body)
    assert GoogleAccountVerifier(opener=Opener([error]))(OAUTH) is None
    assert body.closed


def test_success_does_not_log_or_retain_subject_token_or_profile(caplog):
    verifier = GoogleAccountVerifier(opener=Opener([Response({"sub": SUBJECT, "email": EMAIL, "name": NAME})]))
    with caplog.at_level(logging.DEBUG):
        result = verifier(OAUTH)
    assert result == fingerprint()
    text = caplog.text + repr(verifier)
    for private in (OAUTH, SUBJECT, EMAIL, NAME):
        assert private not in text


def test_error_stream_close_failure_does_not_escape_with_private_data():
    class BrokenError(urllib.error.HTTPError):
        def close(self):
            raise OSError(OAUTH + SUBJECT + EMAIL)
    error = BrokenError(GOOGLE_USERINFO_ENDPOINT, 401, "Unauthorized", {}, None)
    assert GoogleAccountVerifier(opener=Opener([error]))(OAUTH) is None
