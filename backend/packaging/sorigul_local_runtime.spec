# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the versioned Local Whisper runtime worker.

The Whisper model weights are not bundled. OpenAI Whisper keeps using its
existing default cache, preserving already-downloaded models.
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs


BACKEND_ROOT = Path(SPECPATH).resolve().parent

hidden_imports = [
    "whisper",
    "tiktoken_ext",
    "tiktoken_ext.openai_public",
]
datas = collect_data_files("whisper") + collect_data_files("tiktoken_ext")
torch_binaries = collect_dynamic_libs("torch")

a = Analysis(
    [str(BACKEND_ROOT / "src" / "local_runtime_main.py")],
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
    name="sorigul-local-whisper",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    # The parent starts this console executable with CREATE_NO_WINDOW so the
    # JSON stdout/stderr protocol remains available without flashing a window.
    console=True,
    disable_windows_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
