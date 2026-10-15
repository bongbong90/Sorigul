"""Issue #130 source contracts for the current Colab-open convenience."""

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ENGINE_PATH = "frontend/src/components/transcription/EngineSection.tsx"
SETUP_PATH = "frontend/src/lib/colabSetup.ts"


def read_repo(path):
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def block_after(source, marker, open_char="{", close_char="}"):
    start = source.index(marker)
    depth = 0
    for index in range(source.index(open_char, start), len(source)):
        if source[index] == open_char:
            depth += 1
        elif source[index] == close_char:
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(f"unterminated block after {marker!r}")


def test_colab_open_action_uses_the_fixed_safe_browser_boundary():
    engine = read_repo(ENGINE_PATH)
    setup = read_repo(SETUP_PATH)

    assert "Colab 열기" in engine
    assert "https://colab.research.google.com/#create=true" in setup
    assert "openInBrowser(COLAB_NEW_NOTEBOOK_URL)" in engine
    assert "from '../../lib/native'" in engine
    assert "window.open" not in engine


def test_colab_open_handler_has_no_backend_or_connection_side_effects():
    engine = read_repo(ENGINE_PATH)
    handler = block_after(engine, "const handleOpenColab = async () =>")

    assert handler.count("openInBrowser(") == 1
    for forbidden in (
        "startColabRendezvous",
        "verifyColabUrl",
        "createJob",
        "saveSettings",
        "onBaseUrlChange",
        "setColabState",
        "setRequestId",
    ):
        assert forbidden not in handler


def test_ui_bootstrap_commands_match_the_canonical_readme():
    engine = read_repo(ENGINE_PATH)
    setup = read_repo(SETUP_PATH)
    readme = read_repo("colab/README.md")
    expected = (
        "!git clone https://github.com/bongbong90/Sorigul.git",
        "!cd Sorigul && pip install -r colab/requirements.txt",
        "!python Sorigul/colab/sorigul_colab_bootstrap.py",
    )

    assert "COLAB_BOOTSTRAP_COMMANDS" in engine
    assert len([line for line in setup.splitlines() if line.strip().startswith("'!")]) == 3
    for command in expected:
        assert command in setup
        assert command in readme


def test_current_flow_contains_no_legacy_notebook_identity():
    current_flow = "\n".join(
        read_repo(path)
        for path in (ENGINE_PATH, SETUP_PATH, "colab/README.md")
    )

    assert "jeonsa_doumi" not in current_flow
    assert "colab_transcribe.ipynb" not in current_flow
    assert "bongbong90/Sorigul" in current_flow


def test_existing_narrow_opener_permission_is_preserved():
    capability = json.loads(read_repo("frontend/src-tauri/capabilities/default.json"))
    permissions = capability["permissions"]

    assert "opener:allow-open-url" in permissions
    assert not any(
        permission.startswith(("shell:", "fs:"))
        or permission in {
            "opener:default",
            "opener:allow-open-path",
            "opener:allow-reveal-item-in-dir",
        }
        for permission in permissions
        if isinstance(permission, str)
    )


def test_existing_colab_connection_and_manual_fallback_remain_separate():
    engine = read_repo(ENGINE_PATH)

    assert "Colab 연결" in engine
    assert "직접 URL 입력" in engine
    assert "handleStartRendezvous" in engine
    assert "handleManualVerify" in engine
    assert "사용자가 직접 시작한 Colab 런타임에만 연결합니다." in engine
    assert "Whisper large-v3 · Colab GPU 우선" in engine
