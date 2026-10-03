from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def read_repo(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_113_preflight_owns_working_directories_and_reuses_canonical_regression():
    script = read_repo("scripts/run_113_preflight.ps1")

    assert "$Backend = Join-Path $RepoRoot 'backend'" in script
    assert "$CoreRegression = Join-Path $PSScriptRoot 'run_core_workflow_regression.ps1'" in script
    assert "Invoke-Checked -WorkingDirectory $Backend -Command $Python" in script
    assert "tests/test_release_packaging_contract.py" in script
    assert "tests/test_installer_powershell5_restricted_invocation.py" in script
    assert "tests/test_core_powershell5_process_observation.py" in script
    assert "Invoke-Checked -WorkingDirectory $RepoRoot -Command $TrustedPowerShell" in script


def test_113_preflight_locks_source_and_trusted_windows_boundaries():
    script = read_repo("scripts/run_113_preflight.ps1")

    for required in (
        "WindowsPowerShell\\v1.0\\powershell.exe",
        "taskkill.exe",
        "Get-AuthenticodeSignature",
        "rev-parse', 'HEAD'",
        "rev-parse', '@{u}'",
        "status --porcelain --untracked-files=no",
        "diff --check",
        "diff --cached --check",
        "Get-ExecutionPolicy -List",
    ):
        assert required in script

    assert "Set-ExecutionPolicy" not in script


def test_113_preflight_never_invokes_release_artifact_or_install_commands():
    script = read_repo("scripts/run_113_preflight.ps1").lower()

    for forbidden in (
        "build_local_whisper_runtime.ps1",
        "build_backend_sidecar.ps1",
        "build_windows_installer.ps1",
        "msiexec",
        "--bundles msi",
    ):
        assert forbidden not in script


def test_readme_exposes_one_canonical_113_preflight_entrypoint():
    readme = read_repo("README.md")

    assert "## #113 canonical preflight" in readme
    assert "scripts\\run_113_preflight.ps1" in readme
    assert "-ExecutionPolicy Bypass" in readme
    assert "child command를 직접 재구성하지 않는다" in readme


def test_development_rules_lock_preflight_first_and_checkpoint_retry_semantics():
    rules = read_repo("docs/project/DEVELOPMENT_RULES.md")

    for required in (
        "scripts/run_113_preflight.ps1",
        "preflight PASS 후에만 새 artifact run_id",
        "동일 HEAD + 동일 run_id + 동일 release-input identity",
        "harness/invocation failure",
        "source HEAD 또는 release input 변경",
        "artifact hash/provenance mismatch",
    ):
        assert required in rules
