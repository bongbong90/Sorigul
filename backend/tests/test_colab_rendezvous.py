import pytest
import json
from datetime import datetime, timezone, timedelta
from src.services.colab_rendezvous import ColabRendezvousService, COLAB_RUNTIME_FOLDER, COLAB_CONNECTION_FILENAME, COLAB_SCHEMA_VERSION

class FakeDriveClient:
    def __init__(self):
        self.files = {}
        self.folder_calls = []
        self.find_file_calls = []
        self.create_file_calls = []
        self.update_file_calls = []

    def find_or_create_folder(self, parent_id, name):
        self.folder_calls.append((parent_id, name))
        return f"folder_{name}"

    def find_file(self, parent_id, name):
        self.find_file_calls.append((parent_id, name))
        return "fake_file_id" if "fake_file_id" in self.files else None

    def create_text_file(self, parent_id, name, content):
        self.create_file_calls.append((parent_id, name))
        self.files["fake_file_id"] = content
        return "fake_file_id"

    def update_text_file(self, file_id, name, content):
        self.update_file_calls.append((file_id, name))
        self.files[file_id] = content
        return file_id

    def read_text_file(self, file_id):
        return self.files[file_id]

class FakeAuth:
    def __init__(self, client=None):
        self.client = client
    def ensure_client(self):
        if not self.client:
            raise Exception("Auth Error")
        return self.client

def test_start_success():
    client = FakeDriveClient()
    auth = FakeAuth(client)
    service = ColabRendezvousService(auth)

    res = service.start()
    assert res.state == "WAITING"
    assert res.request_id is not None

    content = client.files["fake_file_id"]
    data = json.loads(content)
    assert data["schema_version"] == COLAB_SCHEMA_VERSION
    assert data["request_id"] == res.request_id
    assert data["status"] == "REQUESTED"
    assert data["url"] == ""

def test_poll_ready_success():
    client = FakeDriveClient()
    auth = FakeAuth(client)
    service = ColabRendezvousService(auth)

    req_id = "test_req"
    now = datetime.now(timezone.utc)
    data = {
        "schema_version": COLAB_SCHEMA_VERSION,
        "request_id": req_id,
        "url": "https://example.trycloudflare.com",
        "status": "READY",
        "updated_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=3600)).isoformat()
    }
    client.files["fake_file_id"] = json.dumps(data)

    res = service.poll(req_id)
    assert res.state == "FOUND"
    assert res.base_url == "https://example.trycloudflare.com"
    assert res.request_id == req_id

def test_poll_wrong_request_id():
    client = FakeDriveClient()
    auth = FakeAuth(client)
    service = ColabRendezvousService(auth)

    now = datetime.now(timezone.utc)
    data = {
        "schema_version": COLAB_SCHEMA_VERSION,
        "request_id": "wrong_id",
        "url": "https://example.trycloudflare.com",
        "status": "READY",
        "updated_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=3600)).isoformat()
    }
    client.files["fake_file_id"] = json.dumps(data)

    res = service.poll("test_req")
    assert res.state == "WAITING" # Not found because mismatch

def test_poll_stale():
    client = FakeDriveClient()
    auth = FakeAuth(client)
    service = ColabRendezvousService(auth)

    req_id = "test_req"
    now = datetime.now(timezone.utc)
    data = {
        "schema_version": COLAB_SCHEMA_VERSION,
        "request_id": req_id,
        "url": "https://example.trycloudflare.com",
        "status": "READY",
        "updated_at": (now - timedelta(seconds=7200)).isoformat(),
        "expires_at": (now - timedelta(seconds=3600)).isoformat()
    }
    client.files["fake_file_id"] = json.dumps(data)

    res = service.poll(req_id)
    assert res.state == "EXPIRED"

def test_poll_malformed_json():
    client = FakeDriveClient()
    auth = FakeAuth(client)
    service = ColabRendezvousService(auth)

    client.files["fake_file_id"] = "{ broken json"
    res = service.poll("test_req")
    assert res.state == "WAITING"

def test_poll_wrong_schema():
    client = FakeDriveClient()
    auth = FakeAuth(client)
    service = ColabRendezvousService(auth)

    req_id = "test_req"
    now = datetime.now(timezone.utc)
    data = {
        "schema_version": 999,
        "request_id": req_id,
        "url": "https://example.trycloudflare.com",
        "status": "READY",
        "updated_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=3600)).isoformat()
    }
    client.files["fake_file_id"] = json.dumps(data)

    res = service.poll(req_id)
    assert res.state == "WAITING"

def test_poll_extra_field():
    client = FakeDriveClient()
    auth = FakeAuth(client)
    service = ColabRendezvousService(auth)

    req_id = "test_req"
    now = datetime.now(timezone.utc)
    data = {
        "schema_version": COLAB_SCHEMA_VERSION,
        "request_id": req_id,
        "url": "https://example.trycloudflare.com",
        "status": "READY",
        "updated_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=3600)).isoformat(),
        "unknown_field": "123"
    }
    client.files["fake_file_id"] = json.dumps(data)

    res = service.poll(req_id)
    assert res.state == "WAITING"

def test_poll_failed():
    client = FakeDriveClient()
    auth = FakeAuth(client)
    service = ColabRendezvousService(auth)

    req_id = "test_req"
    now = datetime.now(timezone.utc)
    data = {
        "schema_version": COLAB_SCHEMA_VERSION,
        "request_id": req_id,
        "url": "",
        "status": "FAILED",
        "updated_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=3600)).isoformat()
    }
    client.files["fake_file_id"] = json.dumps(data)

    res = service.poll(req_id)
    assert res.state == "FAILED"

def test_poll_arbitrary_url_path_rejected():
    client = FakeDriveClient()
    auth = FakeAuth(client)
    service = ColabRendezvousService(auth)

    req_id = "test_req"
    now = datetime.now(timezone.utc)
    data = {
        "schema_version": COLAB_SCHEMA_VERSION,
        "request_id": req_id,
        "url": "https://example.trycloudflare.com/some/path",
        "status": "READY",
        "updated_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=3600)).isoformat()
    }
    client.files["fake_file_id"] = json.dumps(data)

    res = service.poll(req_id)
    assert res.state == "WAITING" # Because normalization throws ColabUrlError for paths

def test_health_verify(monkeypatch):
    client = FakeDriveClient()
    auth = FakeAuth(client)
    service = ColabRendezvousService(auth)

    monkeypatch.setattr('src.engines.colab.DirectColabHttpClient.check_health', lambda self: None)
    res = service.verify_url("https://example.trycloudflare.com")
    assert res.state == "CONNECTED"
    assert res.base_url == "https://example.trycloudflare.com"

def test_health_verify_failure(monkeypatch):
    client = FakeDriveClient()
    auth = FakeAuth(client)
    service = ColabRendezvousService(auth)

    def fail(self): raise Exception('failed')
    monkeypatch.setattr('src.engines.colab.DirectColabHttpClient.check_health', fail)
    res = service.verify_url("https://example.trycloudflare.com")
    assert res.state == "FAILED"

def test_naive_timestamp():
    client = FakeDriveClient()
    auth = FakeAuth(client)
    service = ColabRendezvousService(auth)
    req_id = "test_req"
    now = datetime.now() # naive
    data = {
        "schema_version": COLAB_SCHEMA_VERSION,
        "request_id": req_id,
        "url": "https://example.trycloudflare.com",
        "status": "READY",
        "updated_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=3600)).isoformat()
    }
    client.files["fake_file_id"] = json.dumps(data)
    res = service.poll(req_id)
    assert res.state == "WAITING"

def test_future_updated_at():
    client = FakeDriveClient()
    auth = FakeAuth(client)
    service = ColabRendezvousService(auth)
    req_id = "test_req"
    now = datetime.now(timezone.utc)
    data = {
        "schema_version": COLAB_SCHEMA_VERSION,
        "request_id": req_id,
        "url": "https://example.trycloudflare.com",
        "status": "READY",
        "updated_at": (now + timedelta(seconds=120)).isoformat(),
        "expires_at": (now + timedelta(seconds=3600)).isoformat()
    }
    client.files["fake_file_id"] = json.dumps(data)
    res = service.poll(req_id)
    assert res.state == "WAITING"

def test_real_health_verifier(monkeypatch):
    import urllib.request

    client = FakeDriveClient()
    auth = FakeAuth(client)
    service = ColabRendezvousService(auth)

    called_url = None

    class FakeResponse:
        def __init__(self):
            self.status = 200
        def read(self):
            return b"{\"status\":\"ok\"}"
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    def mock_urlopen(req, *args, **kwargs):
        nonlocal called_url
        called_url = req.full_url
        return FakeResponse()

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    res = service.verify_url("https://example.trycloudflare.com/health")
    assert res.state == "CONNECTED"
    assert res.base_url == "https://example.trycloudflare.com"
    assert called_url == "https://example.trycloudflare.com/health"

def test_artifact_roundtrip():
    import sys
    import os
    # Add project root to path
    sys.path.insert(0, os.path.abspath(".."))
    from colab.sorigul_colab_bootstrap import build_ready_metadata

    req_id = "test_req"
    now = datetime.now(timezone.utc)
    request_data = {
        "schema_version": COLAB_SCHEMA_VERSION,
        "request_id": req_id,
        "url": "",
        "status": "REQUESTED",
        "updated_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=600)).isoformat()
    }

    ready_data = build_ready_metadata(request_data, "https://example.trycloudflare.com", now=now)
    assert ready_data is not None
    assert ready_data["status"] == "READY"

    client = FakeDriveClient()
    auth = FakeAuth(client)
    service = ColabRendezvousService(auth)

    client.files["fake_file_id"] = json.dumps(ready_data)
    res = service.poll(req_id)
    assert res.state == "FOUND"
    assert res.base_url == "https://example.trycloudflare.com"

def test_start_payload_exact_keys():
    client = FakeDriveClient()
    auth = FakeAuth(client)
    service = ColabRendezvousService(auth)

    res = service.start()
    content = client.files["fake_file_id"]
    data = json.loads(content)

    expected_keys = {"schema_version", "request_id", "url", "status", "updated_at", "expires_at"}
    assert set(data.keys()) == expected_keys

def test_artifact_pure_helper_future_updated_at():
    import sys
    import os
    sys.path.insert(0, os.path.abspath(".."))
    from colab.sorigul_colab_bootstrap import build_ready_metadata

    now = datetime.now(timezone.utc)
    updated_at = now + timedelta(seconds=120)
    expires_at = updated_at + timedelta(seconds=600)

    request_data = {
        "schema_version": COLAB_SCHEMA_VERSION,
        "request_id": "test_future_req",
        "url": "",
        "status": "REQUESTED",
        "updated_at": updated_at.isoformat(),
        "expires_at": expires_at.isoformat()
    }

    ready_data = build_ready_metadata(request_data, "https://example.trycloudflare.com", now=now)
    assert ready_data is None

def test_start_contract_lock():
    client = FakeDriveClient()
    auth = FakeAuth(client)
    service = ColabRendezvousService(auth)

    res = service.start()

    assert client.folder_calls == [("root", COLAB_RUNTIME_FOLDER)]
    assert client.find_file_calls == [("folder_" + COLAB_RUNTIME_FOLDER, COLAB_CONNECTION_FILENAME)]
    assert client.create_file_calls == [("folder_" + COLAB_RUNTIME_FOLDER, COLAB_CONNECTION_FILENAME)]
    assert res.state == "WAITING"

    content = client.files.get("fake_file_id")
    assert content is not None

    data = json.loads(content)
    assert set(data.keys()) == {"schema_version", "request_id", "url", "status", "updated_at", "expires_at"}
    assert data["schema_version"] == 1
    assert data["request_id"] == res.request_id
    assert data["url"] == ""
    assert data["status"] == "REQUESTED"

    updated_at = datetime.fromisoformat(data["updated_at"])
    expires_at = datetime.fromisoformat(data["expires_at"])

    assert updated_at.tzinfo is not None
    assert expires_at.tzinfo is not None

    diff = (expires_at - updated_at).total_seconds()
    assert abs(diff - 600) < 1.0


def test_naive_updated_at_aware_expires_at():
    client = FakeDriveClient()
    auth = FakeAuth(client)
    service = ColabRendezvousService(auth)

    now = datetime.now() # naive
    expires = datetime.now(timezone.utc) + timedelta(seconds=600) # aware

    data = {
        "schema_version": COLAB_SCHEMA_VERSION,
        "request_id": "test_req",
        "url": "https://example.trycloudflare.com",
        "status": "READY",
        "updated_at": now.isoformat(),
        "expires_at": expires.isoformat()
    }
    client.files["fake_file_id"] = json.dumps(data)
    res = service.poll("test_req")
    assert res.state == "WAITING"

def test_aware_updated_at_naive_expires_at():
    client = FakeDriveClient()
    auth = FakeAuth(client)
    service = ColabRendezvousService(auth)

    now = datetime.now(timezone.utc) # aware
    expires = datetime.now() + timedelta(seconds=600) # naive

    data = {
        "schema_version": COLAB_SCHEMA_VERSION,
        "request_id": "test_req",
        "url": "https://example.trycloudflare.com",
        "status": "READY",
        "updated_at": now.isoformat(),
        "expires_at": expires.isoformat()
    }
    client.files["fake_file_id"] = json.dumps(data)
    res = service.poll("test_req")
    assert res.state == "WAITING"


def test_oversized_requested():
    client = FakeDriveClient()
    auth = FakeAuth(client)
    service = ColabRendezvousService(auth)

    now = datetime.now(timezone.utc)
    data = {
        "schema_version": COLAB_SCHEMA_VERSION,
        "request_id": "test_req",
        "url": "",
        "status": "REQUESTED",
        "updated_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=601)).isoformat()
    }
    client.files["fake_file_id"] = json.dumps(data)
    res = service.poll("test_req")
    assert res.state == "WAITING"

def test_oversized_ready():
    client = FakeDriveClient()
    auth = FakeAuth(client)
    service = ColabRendezvousService(auth)

    now = datetime.now(timezone.utc)
    data = {
        "schema_version": COLAB_SCHEMA_VERSION,
        "request_id": "test_req",
        "url": "https://example.test",
        "status": "READY",
        "updated_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=3601)).isoformat()
    }
    client.files["fake_file_id"] = json.dumps(data)
    res = service.poll("test_req")
    assert res.state == "WAITING"

def test_valid_ready_boundary():
    client = FakeDriveClient()
    auth = FakeAuth(client)
    service = ColabRendezvousService(auth)

    now = datetime.now(timezone.utc)
    data = {
        "schema_version": COLAB_SCHEMA_VERSION,
        "request_id": "test_req",
        "url": "https://example.test",
        "status": "READY",
        "updated_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=3600)).isoformat()
    }
    client.files["fake_file_id"] = json.dumps(data)
    res = service.poll("test_req")
    assert res.state == "FOUND"
    assert res.base_url == "https://example.test"


@pytest.mark.parametrize("url", [
    "https://example.test",
    "https://example.test/",
    "https://example.test/health",
    "https://example.test/transcribe"
])
def test_poll_ready_url_suffix_normalization(url):
    client = FakeDriveClient()
    auth = FakeAuth(client)
    service = ColabRendezvousService(auth)

    now = datetime.now(timezone.utc)
    data = {
        "schema_version": COLAB_SCHEMA_VERSION,
        "request_id": "test_req",
        "url": url,
        "status": "READY",
        "updated_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=3600)).isoformat()
    }
    client.files["fake_file_id"] = json.dumps(data)
    res = service.poll("test_req")
    assert res.state == "FOUND"
    assert res.base_url == "https://example.test"

def test_poll_ready_arbitrary_url_rejected():
    client = FakeDriveClient()
    auth = FakeAuth(client)
    service = ColabRendezvousService(auth)

    now = datetime.now(timezone.utc)
    data = {
        "schema_version": COLAB_SCHEMA_VERSION,
        "request_id": "test_req",
        "url": "https://example.test/other",
        "status": "READY",
        "updated_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=3600)).isoformat()
    }
    client.files["fake_file_id"] = json.dumps(data)
    res = service.poll("test_req")
    assert res.state == "WAITING"


def test_artifact_expired_request_contract():
    import sys
    import os
    sys.path.insert(0, os.path.abspath(".."))
    from colab.sorigul_colab_bootstrap import build_ready_metadata

    now = datetime.now(timezone.utc)
    updated_at = now - timedelta(seconds=1000)
    expires_at = now - timedelta(seconds=400)

    request_data = {
        "schema_version": COLAB_SCHEMA_VERSION,
        "request_id": "test_req",
        "url": "",
        "status": "REQUESTED",
        "updated_at": updated_at.isoformat(),
        "expires_at": expires_at.isoformat()
    }

    ready_data = build_ready_metadata(request_data, "https://example.test", now=now)
    assert ready_data is None
