import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _frontend_source_matches(pattern: re.Pattern[str]):
    matches = []
    source_root = ROOT / "frontend" / "src"
    for path in sorted((*source_root.rglob("*.ts"), *source_root.rglob("*.tsx"))):
        content = path.read_text(encoding="utf-8")
        for match in pattern.finditer(content):
            line = content.count("\n", 0, match.start()) + 1
            matches.append(f"{path.relative_to(ROOT)}:{line}")
    return matches


def test_frontend_source_has_no_runtime_inline_style_or_html_injection():
    assert _frontend_source_matches(re.compile(r"\bstyle\s*=\s*\{")) == []
    assert _frontend_source_matches(re.compile(r"\bdangerouslySetInnerHTML\s*=")) == []


def test_production_tauri_csp_is_explicit_and_restricted():
    config = json.loads((ROOT / "frontend" / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))
    csp = config["app"]["security"]["csp"]
    assert csp is not None
    directives = {
        part.strip().split(" ", 1)[0]: part.strip().split(" ", 1)[1]
        for part in csp.split(";")
        if part.strip()
    }
    assert directives["default-src"] == "'self'"
    assert directives["script-src"] == "'self'"
    assert directives["style-src"] == "'self'"
    assert "'unsafe-inline'" not in directives["style-src"]
    assert directives["object-src"] == "'none'"
    assert directives["base-uri"] == "'none'"
    assert directives["frame-ancestors"] == "'none'"
    assert "'unsafe-eval'" not in csp
    assert "script-src 'self' 'unsafe-inline'" not in csp
    assert "*" not in csp
    assert "https:" not in directives["connect-src"]
    assert "wss:" not in directives["connect-src"]
    assert "http://127.0.0.1:8000" in directives["connect-src"]


def test_dev_csp_scopes_hmr_allowance_to_local_vite_only():
    config = json.loads((ROOT / "frontend" / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))
    dev_csp = config["app"]["security"]["devCsp"]
    assert "ws://localhost:5173" in dev_csp
    assert "http://localhost:5173" in dev_csp
    assert "'unsafe-eval'" not in dev_csp
    assert "script-src 'self' 'unsafe-inline'" not in dev_csp
    assert "https:" not in dev_csp
    assert "wss:" not in dev_csp
    assert "*" not in dev_csp


def test_progress_uses_native_element_and_external_css_only():
    component = (ROOT / "frontend" / "src" / "components" / "ui" / "Progress.tsx").read_text(
        encoding="utf-8"
    )
    css = (ROOT / "frontend" / "src" / "styles" / "components.css").read_text(
        encoding="utf-8"
    )
    assert "<progress" in component
    assert "value={clamped}" in component
    assert "max={normalizedMax}" in component
    assert "style=" not in component
    assert ".progress::-webkit-progress-value" in css
    assert ".progress::-moz-progress-bar" in css
