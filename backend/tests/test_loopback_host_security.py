"""Issue #125: the loopback API rejects untrusted Host headers.

The backend binds 127.0.0.1 only, but a browser page that DNS-rebinds its
own hostname to 127.0.0.1 still reaches that socket with its own name in the
Host header. CORS does not stop this (the page is same-origin with itself),
so the backend validates the destination Host before any route runs.

Scope: browser / DNS-rebinding boundary only. Another local process sending
`Host: 127.0.0.1:8000` directly is the #53 threat model and is not covered.
"""

import pytest
from fastapi.testclient import TestClient
from starlette.middleware.trustedhost import TrustedHostMiddleware


ALLOWED_BASE_URLS = [
    "http://127.0.0.1",
    "http://127.0.0.1:8000",
    "http://localhost",
    "http://localhost:8000",
    # sidecar_main.py accepts --port; the allowlist is hostname-only.
    "http://127.0.0.1:51234",
    "http://localhost:51234",
]

FOREIGN_HOSTS = [
    "attacker.example",
    "attacker.example:8000",
    "127.0.0.1.attacker.example",
    "127.0.0.1.attacker.example:8000",
    "localhost.attacker.example",
    "localhost.attacker.example:8000",
    "sorigul.localhost:8000",
    "0.0.0.0:8000",
    # IPv6 loopback is not bound (127.0.0.1 only), so it is not allowed.
    "[::1]:8000",
    "",
]


class Tripwire:
    """Stands in for a route's service; any use means a handler ran."""

    def __init__(self, name):
        self._name = name

    def __getattr__(self, attribute):
        raise AssertionError(f"handler reached {self._name}.{attribute}")


def _app(tmp_path, monkeypatch):
    import src.api.routes as routes
    from src.main import app
    from src.services.job_manager import JobManager

    monkeypatch.setattr(routes, "job_manager", JobManager(str(tmp_path / "jobs.json")))
    return app, routes


def _client(tmp_path, monkeypatch, base_url):
    app, _ = _app(tmp_path, monkeypatch)
    return TestClient(app, base_url=base_url)


def _arm_tripwires(routes, monkeypatch):
    for name in ("results_service", "settings_manager", "job_manager"):
        monkeypatch.setattr(routes, name, Tripwire(name))


def _assert_rejected(response):
    assert response.status_code == 400
    assert response.text == "Invalid host header"


def test_host_middleware_is_the_exact_hostname_allowlist(tmp_path, monkeypatch):
    app, _ = _app(tmp_path, monkeypatch)
    trusted = [m for m in app.user_middleware if m.cls is TrustedHostMiddleware]
    assert len(trusted) == 1
    assert trusted[0].kwargs["allowed_hosts"] == ["127.0.0.1", "localhost"]
    assert trusted[0].kwargs["www_redirect"] is False
    # Outermost user middleware: Host is checked before CORS and routing.
    assert app.user_middleware[0].cls is TrustedHostMiddleware


@pytest.mark.parametrize("base_url", ALLOWED_BASE_URLS)
def test_loopback_hosts_are_accepted(tmp_path, monkeypatch, base_url):
    client = _client(tmp_path, monkeypatch, base_url)
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/jobs").json() == []


@pytest.mark.parametrize("host", FOREIGN_HOSTS)
def test_foreign_hosts_are_rejected(tmp_path, monkeypatch, host):
    client = _client(tmp_path, monkeypatch, "http://127.0.0.1:8000")
    _assert_rejected(client.get("/api/health", headers={"host": host}))


def test_dns_rebinding_probe_is_rejected(tmp_path, monkeypatch):
    """The #123 (5F) probe: before this fix all three returned 200."""
    folder = tmp_path / "rebinding-target"
    folder.mkdir()
    (folder / "강의.txt").write_text("transcript", encoding="utf-8")

    client = _client(tmp_path, monkeypatch, "http://attacker.example:8000")
    _assert_rejected(client.get("/api/health"))
    _assert_rejected(client.get("/api/jobs"))
    _assert_rejected(client.post("/api/folders/scan", json={"folder": str(folder)}))


def test_foreign_host_never_reaches_mutating_handlers(tmp_path, monkeypatch):
    app, routes = _app(tmp_path, monkeypatch)
    _arm_tripwires(routes, monkeypatch)
    folder = tmp_path / "scan-target"
    folder.mkdir()

    client = TestClient(app, base_url="http://attacker.example:8000")
    _assert_rejected(client.post("/api/folders/scan", json={"folder": str(folder)}))
    _assert_rejected(client.put("/api/settings", json={}))
    _assert_rejected(
        client.post(
            "/api/jobs",
            json={"engine": "local_whisper", "files": [], "output_folder": str(folder)},
        )
    )
    _assert_rejected(client.post("/api/jobs/any/start"))

    # Control: the same tripwire does fire once the Host is trusted.
    trusted = TestClient(app, base_url="http://127.0.0.1:8000")
    with pytest.raises(AssertionError, match="results_service"):
        trusted.post("/api/folders/scan", json={"folder": str(folder)})


def test_trusted_host_folder_scan_still_works(tmp_path, monkeypatch):
    folder = tmp_path / "전사자료"
    folder.mkdir()
    client = _client(tmp_path, monkeypatch, "http://127.0.0.1:8000")
    response = client.post("/api/folders/scan", json={"folder": str(folder)})
    assert response.status_code == 200


def test_dev_origin_is_independent_of_backend_host(tmp_path, monkeypatch):
    """Origin (CORS) names the page; Host names the backend destination."""
    client = _client(tmp_path, monkeypatch, "http://127.0.0.1:8000")
    response = client.get("/api/health", headers={"origin": "http://localhost:5173"})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"

    # A trusted Origin does not make a foreign Host acceptable.
    _assert_rejected(
        client.get(
            "/api/health",
            headers={"origin": "http://localhost:5173", "host": "attacker.example:8000"},
        )
    )
