"""#274: native Git checkout must survive Tauri's observed LF manifest write.

This replays the exact line-ending transformation observed in the stopped MSI
run. It does not execute Tauri, build artifacts, or touch a user installation.
"""
import hashlib
from pathlib import Path
import subprocess


REPO = Path(__file__).resolve().parents[1]


def git(root, *args):
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True,
        text=True, encoding="utf-8",
    ).stdout.strip()


def test_windows_checkout_preserves_freeze_identity_after_tauri_lf_write(tmp_path):
    root = tmp_path / "owned checkout 한글 with spaces"
    root.mkdir()
    git(root, "init")
    git(root, "config", "core.autocrlf", "true")
    git(root, "config", "user.name", "Owned source identity fixture")
    git(root, "config", "user.email", "fixture@example.invalid")
    (root / ".gitattributes").write_bytes((REPO / ".gitattributes").read_bytes())
    relative = "frontend/src-tauri/Cargo.toml"
    manifest = root / relative
    manifest.parent.mkdir(parents=True)
    lf_manifest = (REPO / relative).read_bytes().replace(b"\r\n", b"\n")
    manifest.write_bytes(lf_manifest)
    powershell = root / "owned.ps1"
    powershell.write_bytes(b"Write-Output 'synthetic'\n")
    git(root, "add", "--", ".gitattributes", relative, "owned.ps1")
    git(root, "commit", "-qm", "Owned synthetic source identity fixture")
    # Exercise Git's real Windows-style working-tree conversion, not a
    # source-text assertion about an attribute declaration.
    manifest.unlink()
    powershell.unlink()
    git(root, "checkout", "--", relative, "owned.ps1")
    assert git(root, "status", "--porcelain", "--untracked-files=no") == ""
    frozen = manifest.read_bytes()
    before_sha256 = hashlib.sha256(frozen).hexdigest()
    # Tauri wrote exactly the LF Git blob in the real #269 failure. Replay
    # those output bytes without another compiler/package execution.
    manifest.write_bytes(lf_manifest)
    assert hashlib.sha256(manifest.read_bytes()).hexdigest() == before_sha256
    assert frozen == lf_manifest
    assert git(root, "status", "--porcelain", "--untracked-files=no") == ""
    # Keep the existing native PS5 CRLF contract while changing Cargo policy.
    assert powershell.read_bytes() == b"Write-Output 'synthetic'\r\n"
