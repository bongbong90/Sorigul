"""PHASE 16 (#245) desktop UI contracts for automatic official Colab.

Follows the existing source-contract style (test_package_d_ux_integrity.py):
the frontend has no test runner, and lint/typecheck/build run separately.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "frontend/src"


def read(relative):
    return (SRC / relative).read_text(encoding="utf-8")


def test_engine_section_offers_three_engines_and_keeps_existing_two():
    component = read("components/transcription/EngineSection.tsx")
    values = re.findall(r'value="(local_whisper|direct_colab|official_colab)"', component)
    assert values == ["local_whisper", "direct_colab", "official_colab"]
    assert "<strong>Local</strong>" in component and "<strong>Colab</strong>" in component
    assert "<strong>Colab 자동 연결</strong>" in component
    # Existing manual Colab flow is untouched.
    for marker in ("handleStartRendezvous", "handleManualVerify", "직접 URL 입력", "COLAB_BOOTSTRAP_COMMANDS"):
        assert marker in component


def test_official_option_shows_readiness_and_every_block_reason():
    component = read("components/transcription/EngineSection.tsx")
    assert "useOfficialColabStatus(engine)" in component
    assert "officialStatus.available ? '사용 가능' : '현재 사용 불가'" in component
    assert "officialStatus.reasons.map((reason) => <li key={reason.code}>{reason.message}</li>)" in component
    assert "Local 전사는 그대로 사용할 수 있습니다." in component
    assert "style=" not in component
    css = read("styles/transcription-screen.css")
    for selector in (".engine-official-panel", ".engine-official-reasons", ".engine-official-local-hint"):
        assert selector in css


def test_internal_engine_name_is_never_user_visible_text():
    for relative in ("components/transcription/EngineSection.tsx",
                     "components/transcription/TranscriptionActions.tsx",
                     "pages/TranscriptionPage.tsx"):
        source = read(relative)
        # JSX text nodes and template/message strings must not show identifiers.
        for text in re.findall(r">([^<>{}]+)<", source) + re.findall(r"setMessage\(`([^`]*)`", source):
            assert "official_colab" not in text and "official" not in text.lower()
    actions = read("components/transcription/TranscriptionActions.tsx")
    assert "engine === 'official_colab' ? 'Google Colab 자동 연결'" in actions


def test_status_client_matches_backend_route_and_carries_no_secrets():
    client = read("api/client.ts")
    assert "export type EngineId = 'local_whisper' | 'direct_colab' | 'official_colab'" in client
    assert "request<OfficialColabStatus>('/engines/official-colab/status'" in client
    status_type = client.split("export interface OfficialColabStatus {", 1)[1].split("}\n", 1)[0]
    for forbidden in ("token", "url", "account", "runtime", "email", "binding"):
        assert forbidden not in status_type.lower().replace("reasons", "")
    assert "engine?: EngineId" in client
    # Persisted settings schema unchanged for backward compatibility.
    assert "last_engine: 'local_whisper' | 'direct_colab'\n" in client

    import src.api.routes as routes
    paths = {route.path for route in routes.router.routes}
    assert "/engines/official-colab/status" in paths


def test_status_hook_is_on_demand_never_polled_or_stored():
    hook = read("hooks/useOfficialColabStatus.ts")
    assert "setInterval" not in hook and "setTimeout" not in hook
    assert "localStorage" not in hook and "sessionStorage" not in hook
    assert "new AbortController()" in hook and "controller.abort()" in hook
    unknown = hook.split("const UNKNOWN_STATUS", 1)[1].split("}\n", 1)[0]
    assert "available: false" in unknown


def test_start_is_gated_by_fresh_server_status_and_sends_no_connection_settings():
    page = read("pages/TranscriptionPage.tsx")
    gate = page.split("if (engine === 'official_colab') {", 1)[1].split("startAttemptChecked(ids, force, scope)\n  }", 1)[0]
    assert "refreshOfficialColabStatus()" in gate
    assert "if (status.available) startAttemptChecked(ids, force, scope)" in gate
    assert "Local 전사를 선택할 수 있습니다." in gate
    assert "colab_url: engine === 'direct_colab' ? (connectedBaseUrl ?? undefined) : undefined" in page
    assert "const lastEngine = engine === 'official_colab' ? settings.last_engine : engine" in page
    assert "last_engine: lastEngine" in page
    # Hydration still only restores the two persisted engines.
    assert "setEngine(loaded.last_engine === 'direct_colab' ? 'direct_colab' : 'local_whisper')" in page
    assert "job?.engine === 'official_colab'" in page


def test_switching_away_from_manual_colab_clears_its_url():
    app = read("App.tsx")
    assert "if (value !== 'direct_colab') setConnectedBaseUrl(null)" in app
    page = read("pages/TranscriptionPage.tsx")
    assert "if (nextEngine !== 'direct_colab') {" in page
    # Manual Colab polling only runs while direct_colab is selected.
    component = read("components/transcription/EngineSection.tsx")
    assert "if (engine === 'direct_colab' && requestId && !manualModeActive" in component


def test_no_frontend_code_stores_tokens_or_runtime_urls():
    for path in list(SRC.rglob("*.ts")) + list(SRC.rglob("*.tsx")):
        source = path.read_text(encoding="utf-8")
        if "officialColab" in source or "OfficialColab" in source:
            assert "access_token" not in source and "proxy" not in source.lower()
            assert not re.search(r"localStorage\.setItem\([^)]*(?:engine|colab)", source, re.I)
