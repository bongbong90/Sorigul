import pytest
import json
from datetime import datetime, timezone, timedelta
from src.services.colab_rendezvous import ColabRendezvousService, COLAB_RUNTIME_FOLDER, COLAB_CONNECTION_FILENAME, COLAB_SCHEMA_VERSION

class FakeDriveClient:
    def __init__(self):
        self.files = {}
        
    def find_or_create_folder(self, parent_id, name):
        return f"folder_{name}"
        
    def find_file(self, parent_id, name):
        return "fake_file_id" if "fake_file_id" in self.files else None
        
    def create_text_file(self, parent_id, name, content):
        self.files["fake_file_id"] = content
        return "fake_file_id"
        
    def update_text_file(self, file_id, name, content):
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
