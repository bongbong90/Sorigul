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

Local Whisper, torch and CUDA are deliberately excluded from this Core
artifact. They are built by `sorigul_local_runtime.spec` and installed into
the versioned per-user runtime directory. FFmpeg remains a Core resource.
"""

from pathlib import Path

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
]

a = Analysis(
    [str(BACKEND_ROOT / "src" / "sidecar_main.py")],
    pathex=[str(BACKEND_ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["torch", "whisper", "numba", "llvmlite"],
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
