"""Issue #125 source contracts: the loopback backend keeps its exact Host
allowlist and 127.0.0.1-only bind. Behavior is proven in
backend/tests/test_loopback_host_security.py; these guard against accidental
removal or widening."""

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_SRC = REPO_ROOT / "backend" / "src"
TAURI_LIB = REPO_ROOT / "frontend" / "src-tauri" / "src" / "lib.rs"

ALLOWED_HOSTS = re.compile(r"allowed_hosts=\[([^\]]*)\]")


def test_backend_app_installs_exact_trusted_host_allowlist():
    main = (BACKEND_SRC / "main.py").read_text(encoding="utf-8")
    assert "from starlette.middleware.trustedhost import TrustedHostMiddleware" in main
    assert "app.add_middleware(\n    TrustedHostMiddleware," in main
    found = ALLOWED_HOSTS.findall(main)
    assert found == ['"127.0.0.1", "localhost"']
    assert "*" not in found[0]
    assert "www_redirect=False" in main
    # Added after CORS, so it wraps it (outermost).
    assert main.index("TrustedHostMiddleware,") > main.index("CORSMiddleware,")


def test_backend_binds_loopback_only():
    sidecar = (BACKEND_SRC / "sidecar_main.py").read_text(encoding="utf-8")
    assert 'uvicorn.run(app, host="127.0.0.1", port=args.port)' in sidecar
    lib = TAURI_LIB.read_text(encoding="utf-8")
    assert '"--host".into(),\n            "127.0.0.1".into(),' in lib
    for path in sorted(BACKEND_SRC.rglob("*.py")):
        assert "0.0.0.0" not in path.read_text(encoding="utf-8"), path.name
