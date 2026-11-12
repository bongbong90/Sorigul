# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the packaged Sorigul backend sidecar.

Produces a single standalone `sorigul-backend.exe` (one-file mode) that the
Tauri release runtime spawns from `resource_dir/binaries/`. Built via:

    pyinstaller --clean --noconfirm backend/packaging/sorigul_backend.spec

(see scripts/build_backend_sidecar.ps1 for the reproducible, full build +
self-test + staging flow).

Deliberately windowed (console=False): the packaged app must never show a
console window for the backend child. `sidecar_main.py`'s `--self-test`
mode compensates by also writing its result to a log file next to the exe,
since a windowed PyInstaller build has no attached stdio to print to.

The Whisper `medium` model weight is intentionally NOT bundled here -- it is
downloaded/cached by openai-whisper at first real use, same as the existing
dev-mode contract (see docs/runtime/INSTALLER_INSTALLED_RUNTIME_VALIDATION.md
-> Whisper Runtime).
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

BACKEND_ROOT = Path(SPECPATH).resolve().parent  # backend/packaging -> backend

hidden_imports = [
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "google.auth.transport.requests",
    "google_auth_oauthlib.flow",
    "googleapiclient.discovery",
    "googleapiclient.discovery_cache",
    "googleapiclient.http",
    "whisper",
    "tiktoken_ext",
    "tiktoken_ext.openai_public",
]

datas = collect_data_files("whisper") + collect_data_files("tiktoken_ext")
torch_binaries = collect_dynamic_libs("torch")

a = Analysis(
    [str(BACKEND_ROOT / "src" / "sidecar_main.py")],
    pathex=[str(BACKEND_ROOT)],
    binaries=torch_binaries,
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="sorigul-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windows_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
