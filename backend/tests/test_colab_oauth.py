"""PHASE 18: real OAuth/provider/store/routes with fake Google, no external sockets."""

import base64
from email.message import Message
import hashlib
import json
from pathlib import Path
import socket
import threading
import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
import pytest
from cryptography.fernet import Fernet

from src.services.colab_account_verifier import GOOGLE_ISSUER, GOOGLE_USERINFO_ENDPOINT
from src.services.colab_launch_preflight import run_launch_preflight
from src.services.colab_oauth import (
    AUTH_URL, TOKEN_URL, REVOKE_URL, CERT_URL, SCOPES, ColabOAuthError,
    ColabOAuthService, GoogleColabOAuthProvider, load_client,
)
from src.services.colab_oauth_callback import ColabLoopbackCallback
from src.services.colab_oauth_store import ColabSecretStore, WindowsUserProtector
from src.services.colab_runtime_ownership import OwnershipStore
from src.services.official_colab_launcher import OfficialColabLauncher, FailClosedLaunchAuthorizer
from test_colab_launch_preflight import Colab, TOKEN, SUBJECT


CLIENT = "mock-phase18.apps.googleusercontent.com"
SECRET = "MOCK_COLAB_CLIENT_SECRET"
REFRESH = "MOCK_COLAB_REFRESH_SECRET"
NOW = 1900000000


@pytest.fixture(autouse=True)
def no_external_network(monkeypatch):
    original = socket.socket.connect
    def only_loopback(sock, address):
        if isinstance(address, tuple) and address[0] == "127.0.0.1":
            return original(sock, address)
        raise AssertionError("PHASE18 external socket forbidden")
    def denied(*args, **kwargs):
        raise AssertionError("PHASE18 external network forbidden")
    monkeypatch.setattr(socket.socket, "connect", only_loopback)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", denied)


class Response:
    def __init__(self, url, payload, status=200):
        self.url, self.status = url, status
        self.headers = Message()
        self.headers["Content-Type"] = "application/json"
        self.raw = json.dumps(payload).encode()
    def geturl(self):
        return self.url
    def read(self, size):
        return self.raw[:size]
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass


class Google:
    def __init__(self):
        self.calls, self.forms = [], []
        self.subject, self.nonce = SUBJECT, ""
        self.claim_overrides = {}
        self.token_overrides = {}
        self.refresh_fail = self.revoke_fail = self.identity_fail = False
        self.token_hook = lambda: None
    def open(self, request, *, timeout):
        assert timeout <= 10
        self.calls.append((request.method, request.full_url))
        if request.full_url == GOOGLE_USERINFO_ENDPOINT:
            assert request.get_header("Authorization") == "Bearer " + TOKEN
            return Response(request.full_url, {"sub": self.subject}, 401 if self.identity_fail else 200)
        form = {k: v[0] for k, v in parse_qs(request.data.decode()).items()}
        self.forms.append(form)
        if request.full_url == REVOKE_URL:
            assert form == {"token": REFRESH}
            if self.revoke_fail:
                raise OSError("MOCK_COLAB_RAW_SECRET")
            return Response(request.full_url, {})
        assert request.full_url == TOKEN_URL and request.method == "POST"
        assert form["client_id"] == CLIENT and form["client_secret"] == SECRET
        if form["grant_type"] == "refresh_token":
            assert form["refresh_token"] == REFRESH
            if self.refresh_fail:
                raise OSError("MOCK_COLAB_RAW_SECRET")
        self.token_hook()
        payload = dict(access_token=TOKEN, refresh_token=REFRESH, expires_in=3600,
                       scope=" ".join(SCOPES), token_type="Bearer")
        if form["grant_type"] == "authorization_code":
            payload["id_token"] = "mock-signed-id-token"
        payload.update(self.token_overrides)
        return Response(TOKEN_URL, payload)
    def claims(self, token, client):
        assert token == "mock-signed-id-token" and client == CLIENT
        return dict(dict(iss=GOOGLE_ISSUER, aud=CLIENT, iat=NOW-10, exp=NOW+3600,
                         sub=self.subject, nonce=self.nonce), **self.claim_overrides)


class Callback:
    redirect_uri = "http://127.0.0.1:49152/oauth/colab/callback"
    def __init__(self, state):
        self.state, self.code = state, None
        self.event = threading.Event()
    def wait_for_code(self, timeout):
        self.event.wait(min(timeout, 3))
        return self.code
    def shutdown(self):
        self.event.set()
    def deliver(self, code="mock-authorization-code"):
        self.code = code
        self.event.set()


@pytest.fixture
def env(tmp_path):
    client = tmp_path / "google_colab_oauth_client.json"
    config = dict(client_id=CLIENT, client_secret=SECRET, project_id="mock-colab-project",
                  auth_uri=AUTH_URL, token_uri=TOKEN_URL)
    client.write_text(json.dumps({"installed": config}), encoding="utf-8")
    cipher = Fernet(Fernet.generate_key())
    protector = SimpleNamespace(protect=cipher.encrypt, unprotect=cipher.decrypt)
    store = ColabSecretStore(tmp_path / "colab.dpapi", protector=protector,
        writer=lambda path, value: path.write_text(value, encoding="ascii"))
    google, colab, callbacks = Google(), Colab(), []
    flags = {"unresolved": False, "now": NOW}
    provider = GoogleColabOAuthProvider(opener=google, id_token_verifier=google.claims)
    def callback(state):
        item = Callback(state)
        callbacks.append(item)
        return item
    def preflight(token, **kwargs):
        return run_launch_preflight(token, **kwargs, colab_transport=colab.transport, userinfo_opener=google)
    def make():
        return ColabOAuthService(client, store, provider=provider, callback_factory=callback,
            clock=lambda: flags["now"], ownership_unresolved=lambda: flags["unresolved"], preflight=preflight)
    service = make()
    yield SimpleNamespace(service=service, google=google, colab=colab, callbacks=callbacks,
                          flags=flags, store=store, client=client, config=config, make=make, root=tmp_path)
    service.cancel()


def finish(env, code="mock-authorization-code"):
    env.callbacks[-1].deliver(code)
    deadline = time.monotonic() + 3
    while env.service._attempt is not None or env.service._busy:
        assert time.monotonic() < deadline, "Mock OAuth worker did not finish"
        time.sleep(.005)
    return env.service.status()


def connect(env):
    result = env.service.start()
    params = parse_qs(urlsplit(result["authorization_url"]).query)
    env.google.nonce = params["nonce"][0]
    return params


def test_pkce_real_provider_identity_secure_store_restart_and_preflight(env):
    params = connect(env)
    assert params["scope"] == [" ".join(SCOPES)] and params["code_challenge_method"] == ["S256"]
    assert params["include_granted_scopes"] == ["false"]
    status = finish(env)
    assert status["auth_state"] == "CONNECTED" and status["scope_evidence"] == "TOKEN_RESPONSE_VERIFIED"
    form = env.google.forms[0]
    expected = base64.urlsafe_b64encode(hashlib.sha256(form["code_verifier"].encode()).digest()).decode().rstrip("=")
    assert expected == params["code_challenge"][0]
    assert form["redirect_uri"] == params["redirect_uri"][0]
    raw = env.store.path.read_bytes()
    assert all(secret.encode() not in raw for secret in (TOKEN, REFRESH, SUBJECT, SECRET))
    assert env.service().access_token == TOKEN
    before = list(env.google.calls)
    assert env.make().status()["auth_state"] == "CONNECTED"  # restart, local-only decrypt
    assert env.google.calls == before
    checked = env.service.check()
    assert checked["preflight"]["identity"] == "VERIFIED" and checked["preflight"]["tier"] == "FREE"
    assert checked["preflight"]["launch_scope"] == checked["runtime_create_permission"] == "NOT_VERIFIED"
    assert checked["preflight"]["launch_approval"] == checked["launch_approval"] == "BLOCKED"
    assert all(method == "GET" for method, path in env.colab.calls)


@pytest.mark.parametrize("claims", [
    {"nonce": "wrong"}, {"aud": "wrong-client"}, {"azp": "wrong-client"},
    {"iss": "https://evil.invalid"}, {"exp": NOW-1}, {"iat": NOW+100},
    {"sub": "different-account"}, {"at_hash": "wrong"},
])
def test_invalid_oidc_nonce_audience_issuer_expiry_subject_hash_rejected(env, claims):
    connect(env)
    # Subject mismatch needs the ID claims to diverge from exact-token UserInfo.
    env.google.claim_overrides = claims
    status = finish(env)
    assert status["auth_state"] == "IDENTITY_FAILED" and env.service() is None
    assert not env.store.path.exists()


@pytest.mark.parametrize("scope", ["openid", "", "openid https://www.googleapis.com/auth/drive", "openid https://www.googleapis.com/auth/colaboratory.readonly", " ".join(SCOPES) + " email", None])
def test_missing_readonly_drive_or_unapproved_scope_is_refused(env, scope):
    connect(env)
    env.google.token_overrides["scope"] = scope
    status = finish(env)
    assert status["auth_state"] == "INSUFFICIENT_SCOPE" and env.service() is None
    assert not env.store.path.exists() and not env.colab.calls


@pytest.mark.parametrize("override", [
    {"token_type": "MAC"}, {"access_token": "bad\nheader"}, {"expires_in": 0},
    {"expires_in": True}, {"expires_in": "3600"}, {"refresh_token": ""}, {"id_token": None},
])
def test_incomplete_auth_is_not_published(env, override):
    connect(env)
    env.google.token_overrides.update(override)
    assert finish(env)["auth_state"] != "CONNECTED" and not env.store.path.exists()


def test_cancel_retry_single_flight_and_late_callback_cannot_publish(env):
    connect(env)
    old = env.callbacks[-1]
    with pytest.raises(ColabOAuthError, match="AUTH_IN_PROGRESS"):
        env.service.start()
    env.service.cancel()
    connect(env)
    old.deliver("stale-code")
    assert finish(env)["auth_state"] == "CONNECTED"
    assert len(env.google.forms) == 1


def test_cancel_during_token_exchange_discards_result(env):
    connect(env)
    entered, release = threading.Event(), threading.Event()
    def hook():
        entered.set()
        assert release.wait(2)
    env.google.token_hook = hook
    env.callbacks[-1].deliver()
    assert entered.wait(2)
    env.service.cancel()
    release.set()
    for _ in range(200):
        if not env.service._busy:
            break
        time.sleep(.005)
    assert not env.store.path.exists() and env.service() is None


def test_browser_abort_and_retry(env):
    connect(env)
    assert finish(env, None)["auth_state"] == "REFRESH_REQUIRED"
    connect(env)
    assert finish(env)["auth_state"] == "CONNECTED"


def test_expiry_is_local_status_only_refresh_uses_server_bound_token(env):
    connect(env); finish(env)
    env.flags["now"] += 3601
    before = list(env.google.calls)
    assert env.service.status()["auth_state"] == "REFRESH_REQUIRED" and env.service() is None
    assert env.google.calls == before
    status = env.service.check()
    assert status["auth_state"] == "CONNECTED" and env.google.forms[-1]["grant_type"] == "refresh_token"
    assert env.store.load()["expires_at"] > env.flags["now"]


@pytest.mark.parametrize("fault", ["refresh", "scope", "account", "identity"])
def test_refresh_failure_or_account_scope_mix_is_blocked(env, fault):
    connect(env); finish(env)
    original = env.store.path.read_bytes()
    env.flags["now"] += 3601
    if fault == "refresh": env.google.refresh_fail = True
    if fault == "scope": env.google.token_overrides["scope"] = "openid"
    if fault == "account": env.google.subject = "other-account"
    if fault == "identity": env.google.identity_fail = True
    with pytest.raises(ColabOAuthError): env.service.check()
    assert env.service() is None and env.store.path.read_bytes() == original


def test_account_change_requires_no_owned_runtime_and_disconnect_never_deletes_runtime(env):
    connect(env); finish(env)
    original = env.store.path.read_bytes()
    env.flags["unresolved"] = True
    for action in (env.service.start, env.service.disconnect):
        with pytest.raises(ColabOAuthError, match="OWNERSHIP_UNRESOLVED"): action()
    assert env.store.path.read_bytes() == original and not env.colab.calls
    env.flags["unresolved"] = False
    connect(env)
    env.google.subject = "new-account"
    assert finish(env)["auth_state"] == "CONNECTED"
    assert env.store.load()["binding"] == hashlib.sha256((GOOGLE_ISSUER+"\0new-account").encode()).hexdigest()


def test_ownership_appears_during_auth_prevents_credential_replacement(env):
    connect(env)
    env.flags["unresolved"] = True
    assert finish(env)["auth_state"] != "CONNECTED"
    assert not env.store.path.exists()


def test_revoke_success_and_failure_preserve_recovery_semantics(env):
    connect(env); finish(env)
    env.google.revoke_fail = True
    with pytest.raises(ColabOAuthError, match="REVOKE_FAILED"): env.service.disconnect()
    assert env.store.path.exists()
    env.google.revoke_fail = False
    assert env.service.disconnect()["auth_state"] == "DISCONNECTED"
    assert not env.store.path.exists() and not env.colab.calls


def test_drive_files_are_distinct_and_never_read_as_colab_tokens(env):
    drive = env.root / "google_drive_token.json"
    drive.write_bytes(b"MOCK_PRIVATE_DRIVE_TOKEN")
    connect(env); finish(env)
    assert drive.read_bytes() == b"MOCK_PRIVATE_DRIVE_TOKEN"
    env.service.disconnect()
    assert drive.read_bytes() == b"MOCK_PRIVATE_DRIVE_TOKEN"


@pytest.mark.parametrize("same", ["client_id", "project_id"])
def test_shared_drive_client_or_project_is_refused_before_listener(env, same):
    drive = env.root / "google_oauth_client.json"
    config = dict(env.config, client_id="other.apps.googleusercontent.com", project_id="other-project")
    config[same] = env.config[same]
    drive.write_text(json.dumps({"installed": config}))
    with pytest.raises(ColabOAuthError, match="CONFIG_INVALID"):
        load_client(env.client, drive)
    assert not env.google.calls


def test_launcher_gets_real_flow_credentials_but_default_gates_send_zero_requests(env):
    connect(env); finish(env)
    launcher = OfficialColabLauncher(credential_provider=env.service,
        ownership_store=OwnershipStore(env.root/"ownership"), cache_root=env.root/"cache")
    before = list(env.google.calls)
    assert launcher._load_credentials().expected_account_binding == env.store.load()["binding"]
    assert launcher.status()["state"] == "BLOCKED"
    with pytest.raises(Exception) as exc: launcher.launch()
    assert exc.value.code == "OFFICIAL_COLAB_LAUNCH_BLOCKED"
    assert env.google.calls == before and not env.colab.calls


def test_api_refuses_client_token_scope_toggle_and_cross_origin(env, caplog):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.api.colab_oauth_routes import account_router
    app = FastAPI()
    app.include_router(account_router(env.service))
    with TestClient(app) as client:
        assert client.get('/colab/auth/status').json()['auth_state'] == 'DISCONNECTED'
        for body in ({'access_token': TOKEN}, {'scopes': SCOPES}, {'approved': True}, {'redirect_uri': 'http://evil.invalid'}):
            assert client.post('/colab/auth/start', json=body).status_code == 422
        assert client.post('/colab/auth/start', json={}, headers={'Origin': 'https://evil.invalid'}).status_code == 403
        assert client.post('/colab/auth/start', content='x', headers={'Content-Type':'application/x-www-form-urlencoded'}).status_code == 422
        result = client.post('/colab/auth/start', json={})
        env.google.nonce = parse_qs(urlsplit(result.json()['authorization_url']).query)['nonce'][0]
        finish(env)
        status = client.get('/colab/auth/status').json()
        assert status['auth_state'] == 'CONNECTED'
        assert client.post('/colab/auth/check', json={}).status_code == 200
        assert client.post('/colab/auth/disconnect', json={}).status_code == 200
        text = json.dumps(status) + caplog.text
        assert all(secret not in text for secret in (TOKEN, REFRESH, SUBJECT, SECRET, CLIENT))


@pytest.mark.parametrize("target,host,peer", [
    ('/oauth/colab/callback?code=x&state=wrong', None, '127.0.0.1'),
    ('/wrong?code=x&state=expected', None, '127.0.0.1'),
    ('/oauth/colab/callback?code=x&state=expected', 'evil.invalid', '127.0.0.1'),
    ('/oauth/colab/callback?code=x&state=expected', None, '192.0.2.1'),
    ('http://evil.invalid/oauth/colab/callback?code=x&state=expected', None, '127.0.0.1'),
    ('/oauth/colab/callback?code=x&state=expected&state=expected', None, '127.0.0.1'),
    ('/oauth/colab/callback?code=x&error=x&state=expected', None, '127.0.0.1'),
])
def test_callback_state_redirect_host_peer_duplicates_rejected(target, host, peer):
    callback = ColabLoopbackCallback('expected')
    try:
        assert not callback.accept(target, host or f'127.0.0.1:{callback.port}', peer, 'expected')
        assert not callback._event.is_set()
        valid = '/oauth/colab/callback?code=ok&state=expected&scope=forged'
        assert callback.accept(valid, f'127.0.0.1:{callback.port}', '127.0.0.1', 'expected')
        assert not callback.accept(valid, f'127.0.0.1:{callback.port}', '127.0.0.1', 'expected')
        assert callback._result == 'ok'
    finally:
        callback.shutdown()


def test_native_user_dpapi_roundtrip_and_tamper_refusal(tmp_path):
    import os
    if os.name != 'nt': pytest.skip('Windows current-user DPAPI')
    protector = WindowsUserProtector()
    encrypted = protector.protect(b'synthetic-phase18-secret')
    assert b'synthetic-phase18-secret' not in encrypted
    assert protector.unprotect(encrypted) == b'synthetic-phase18-secret'
    with pytest.raises(ValueError): protector.unprotect(encrypted[:-1] + bytes([encrypted[-1] ^ 1]))


def test_corrupt_store_and_storage_failure_are_fail_closed(env, monkeypatch):
    env.store.path.write_bytes(b'not-dpapi')
    assert env.service.status()['auth_state'] == 'REFRESH_REQUIRED'
    assert env.service() is None
    connect(env)
    def fail(*args): raise OSError('MOCK_PRIVATE_STORAGE_SECRET')
    monkeypatch.setattr(env.store, 'save', fail)
    assert finish(env)['error_code'] == 'SECURE_STORE_FAILED'
    assert env.service() is None


def test_desktop_status_contract_and_no_scope_or_token_in_settings():
    root = Path(__file__).resolve().parents[2]
    component = (root/'frontend/src/components/ColabAccountSettings.tsx').read_text(encoding='utf-8')
    for label in ('Google Colab 연결', '연결 상태 확인', '다시 인증', '연결 해제', '인증 취소', '실행 조건 미확인'):
        assert label in component
    assert 'openInBrowser(result.authorization_url)' in component
    assert 'api.cancelColabAuth()' in component and 'api.colabAuthStatus(controller.signal)' in component
    assert 'localStorage' not in component and 'access_token' not in component


def test_default_signature_verifier_with_fake_google_certificate_and_signed_nonce(env):
    from datetime import datetime, timedelta, timezone
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    from google.auth import crypt, jwt
    now = int(time.time())
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'phase18-mock-google')])
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(1).not_valid_before(datetime.now(timezone.utc)-timedelta(days=1))
        .not_valid_after(datetime.now(timezone.utc)+timedelta(days=1)).sign(key, hashes.SHA256()))
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    signer = crypt.RSASigner.from_string(pem, key_id='phase18-test-key')
    original_open = env.google.open
    def open_with_cert(request, *, timeout):
        if request.full_url == CERT_URL:
            env.google.calls.append((request.method, request.full_url))
            return Response(CERT_URL, {'phase18-test-key': cert.public_bytes(serialization.Encoding.PEM).decode()})
        return original_open(request, timeout=timeout)
    env.google.open = open_with_cert
    env.service._provider._id_token_verifier = None
    env.flags['now'] = now
    params = connect(env)
    payload = dict(iss=GOOGLE_ISSUER, aud=CLIENT, sub=SUBJECT, iat=now-1, exp=now+3600, nonce=params['nonce'][0])
    env.google.token_overrides['id_token'] = jwt.encode(signer, payload).decode()
    assert finish(env)['auth_state'] == 'CONNECTED'
    assert ('GET', CERT_URL) in env.google.calls
    for changed in ({'aud': 'wrong.apps.googleusercontent.com'}, {'exp': now-5}, {'iss': 'https://evil.invalid'}):
        token = jwt.encode(signer, dict(payload, **changed)).decode()
        with pytest.raises(Exception): env.service._provider.claims(token, CLIENT)
    token = jwt.encode(signer, payload).decode().split('.')
    token[2] = ('A' if token[2][0] != 'A' else 'B') + token[2][1:]
    with pytest.raises(Exception): env.service._provider.claims('.'.join(token), CLIENT)


def test_missing_client_and_config_endpoint_tamper_never_starts_flow(env):
    env.client.unlink()
    assert env.service.status()['error_code'] == 'CONFIG_REQUIRED'
    with pytest.raises(ColabOAuthError, match='CONFIG_REQUIRED'): env.service.start()
    config = dict(env.config, token_uri='https://evil.invalid/token')
    env.client.write_text(json.dumps({'installed':config}))
    with pytest.raises(ColabOAuthError, match='CONFIG_INVALID'): env.service.start()
    assert not env.callbacks and not env.google.calls


def test_token_redirect_and_bad_content_type_refused(env, monkeypatch):
    response = Response('https://evil.invalid', {})
    monkeypatch.setattr(env.google, 'open', lambda *args, **kwargs: response)
    with pytest.raises(ValueError): env.service._provider.token(env.config, {})
    response.url = TOKEN_URL
    response.headers.replace_header('Content-Type', 'text/html')
    with pytest.raises(ValueError): env.service._provider.token(env.config, {})


def test_completed_check_never_overstates_scope_from_readonly_success(env):
    connect(env); finish(env)
    env.colab.specs = httpx.Response(200, json={'runtimeSpecs': []})
    status = env.service.check()
    assert status['preflight']['t4'] != 'ELIGIBLE'
    assert status['preflight']['launch_approval'] == status['launch_approval'] == 'BLOCKED'
    assert status['scope_evidence'] == 'TOKEN_RESPONSE_VERIFIED'
    assert status['runtime_create_permission'] == status['preflight']['launch_scope'] == 'NOT_VERIFIED'


def test_loopback_actual_http_handler_never_accepts_wrong_state_or_logs_code(capsys):
    callback = ColabLoopbackCallback('expected-state')
    result = []
    waiter = threading.Thread(target=lambda: result.append(callback.wait_for_code(timeout=2)))
    waiter.start()
    def send(query):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(2)
            sock.connect(('127.0.0.1', callback.port))
            sock.sendall((f'GET {callback.PATH}?{query} HTTP/1.0\r\nHost: 127.0.0.1:{callback.port}\r\n\r\n').encode())
            chunks = []
            while True:
                chunk = sock.recv(4096)
                if not chunk: break
                chunks.append(chunk)
            return b''.join(chunks)
    try:
        assert b'400' in send('code=MOCK_LOOPBACK_SECRET&state=wrong')
        assert b'200' in send('code=MOCK_LOOPBACK_SECRET&state=expected-state')
        waiter.join(timeout=3)
        assert not waiter.is_alive() and result == ['MOCK_LOOPBACK_SECRET']
        captured = capsys.readouterr()
        assert 'MOCK_LOOPBACK_SECRET' not in captured.out + captured.err
    finally:
        callback.shutdown()


def test_product_route_oauth_to_default_off_launcher_and_job_zero_runtime(env, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import src.api.routes as routes
    from src.services.job_manager import JobManager
    auth = routes.colab_auth
    for key, value in vars(env.service).items():
        monkeypatch.setattr(auth, key, value)
    env.service = auth
    monkeypatch.setattr(routes, 'job_manager', JobManager(str(env.root/'jobs.json')))
    app = FastAPI()
    app.include_router(routes.router)
    with TestClient(app) as client:
        started = client.post('/colab/auth/start', json={})
        env.google.nonce = parse_qs(urlsplit(started.json()['authorization_url']).query)['nonce'][0]
        assert finish(env)['auth_state'] == 'CONNECTED'
        assert client.get('/colab/auth/status').json()['auth_state'] == 'CONNECTED'
        assert routes.official_colab_launcher._credentials is auth
        assert routes.official_colab_launcher._load_credentials().access_token == TOKEN
        assert routes.engine_resolver.official_colab_enabled is False
        assert client.get('/engines/official-colab/status').json()['state'] == 'DISABLED'
        assert client.post('/jobs', json=dict(folder=str(env.root), engine='official_colab', scope='selected',
            file_ids=['mock'], course='mock', subject='mock', week=1)).status_code == 400
        assert routes.job_manager.list_jobs() == [] and not env.colab.calls


def test_distinct_project_guard_applies_at_disconnect_too(env):
    connect(env); finish(env)
    env.service._drive_client_path = env.root/'drive-client.json'
    env.service._drive_client_path.write_text(json.dumps({'installed': env.config}))
    before = list(env.google.calls)
    with pytest.raises(ColabOAuthError, match='CONFIG_INVALID'): env.service.disconnect()
    assert env.google.calls == before and env.store.path.exists()


def test_readonly_identity_change_is_not_reported_connected(env):
    connect(env); finish(env)
    original = env.service._preflight
    def switched(token, **kwargs):
        env.google.subject = 'changed-between-userinfo-requests'
        return original(token, **kwargs)
    env.service._preflight = switched
    with pytest.raises(ColabOAuthError, match='IDENTITY_FAILED'): env.service.check()
    assert env.service.status()['auth_state'] == 'IDENTITY_FAILED' and env.service() is None
