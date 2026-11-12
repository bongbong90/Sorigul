import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from src import local_runtime_main, sidecar_main


REPO_ROOT = Path(__file__).resolve().parents[2]


class FakeCuda:
    def __init__(self):
        self.synchronized = False

    def synchronize(self):
        self.synchronized = True


class FakeResult:
    def __init__(self, value):
        self.value = value

    def cpu(self):
        return self

    def tolist(self):
        return self.value


class FakeTorch:
    float32 = "float32"

    def __init__(self, result):
        self.cuda = FakeCuda()
        self.result = result
        self.tensor_calls = []

    def tensor(self, value, **kwargs):
        self.tensor_calls.append((value, kwargs))
        return value

    def matmul(self, left, right):
        assert left == [[1.0, 2.0], [3.0, 4.0]]
        assert right == [[5.0, 6.0], [7.0, 8.0]]
        return FakeResult(self.result)


def test_cuda_compute_runs_on_cuda_synchronizes_and_validates_result():
    torch = FakeTorch([[19.0, 22.0], [43.0, 50.0]])

    detail = local_runtime_main._cuda_compute_detail(torch)

    assert detail == "2x2 CUDA matrix multiply verified"
    assert len(torch.tensor_calls) == 2
    assert all(call[1] == {"device": "cuda", "dtype": "float32"} for call in torch.tensor_calls)
    assert torch.cuda.synchronized is True


def test_cuda_compute_rejects_unexpected_result():
    torch = FakeTorch([[0.0, 0.0], [0.0, 0.0]])

    with pytest.raises(RuntimeError, match="unexpected CUDA matrix product"):
        local_runtime_main._cuda_compute_detail(torch)


def test_self_test_progress_records_start_then_pass_and_fail(monkeypatch):
    written = []

    class FakeStream:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def write(self, value):
            written.append(value)

        def flush(self):
            pass

        def fileno(self):
            return 123

    class FakeLogPath:
        def write_text(self, value, **kwargs):
            assert value == ""

        def open(self, *args, **kwargs):
            return FakeStream()

    monkeypatch.setattr(sidecar_main.os, "fsync", lambda descriptor: None)
    progress = sidecar_main._SelfTestProgress(FakeLogPath())

    def fail():
        raise RuntimeError("broken")

    ok = sidecar_main._run_self_test_checks(
        (("good", lambda: None), ("bad", fail)), progress
    )

    assert ok is False
    assert written == [
        "[self-test] good: START\n",
        "[self-test] good: PASS\n",
        "[self-test] bad: START\n",
        "[self-test] bad: FAIL (broken)\n",
    ]


def test_bundled_ffmpeg_executes_exact_sibling_with_timeout(monkeypatch):
    sidecar = Path("C:/candidate/sorigul-backend.exe")
    ffmpeg = sidecar.parent / "ffmpeg.exe"
    calls = []
    monkeypatch.setattr(Path, "is_file", lambda self: self == ffmpeg)

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout="ffmpeg version test", stderr="")

    detail = sidecar_main._bundled_ffmpeg_detail(sidecar, run=run)

    assert detail == "ffmpeg.exe -version"
    assert calls[0][0] == [str(ffmpeg), "-version"]
    assert calls[0][1]["timeout"] == 15
    assert calls[0][1]["creationflags"] == getattr(subprocess, "CREATE_NO_WINDOW", 0)


def test_bundled_ffmpeg_rejects_nonzero_exit(monkeypatch):
    sidecar = Path("C:/candidate/sorigul-backend.exe")
    monkeypatch.setattr(Path, "is_file", lambda self: self.name == "ffmpeg.exe")

    def run(*args, **kwargs):
        return SimpleNamespace(returncode=9, stdout="", stderr="failure")

    with pytest.raises(RuntimeError, match="exited with code 9"):
        sidecar_main._bundled_ffmpeg_detail(sidecar, run=run)


def test_bundled_ffmpeg_timeout_is_a_check_failure(monkeypatch):
    sidecar = Path("C:/candidate/sorigul-backend.exe")
    ffmpeg = sidecar.parent / "ffmpeg.exe"
    monkeypatch.setattr(Path, "is_file", lambda self: self == ffmpeg)

    def run(*args, **kwargs):
        raise subprocess.TimeoutExpired(str(ffmpeg), kwargs["timeout"])

    with pytest.raises(subprocess.TimeoutExpired):
        sidecar_main._bundled_ffmpeg_detail(sidecar, run=run)


def test_required_core_self_test_contract_has_exactly_seven_checks():
    assert len(sidecar_main.REQUIRED_SELF_TEST_CHECKS) == 7
    assert sidecar_main.REQUIRED_SELF_TEST_CHECKS[0] == "self_test_app_data_isolation"
    assert "torch_cuda_compute" not in sidecar_main.REQUIRED_SELF_TEST_CHECKS
    assert "whisper_import" not in sidecar_main.REQUIRED_SELF_TEST_CHECKS
    assert "bundled_ffmpeg_execution" in sidecar_main.REQUIRED_SELF_TEST_CHECKS


def test_self_test_app_data_context_restores_present_and_absent_environment(
    tmp_path, monkeypatch
):
    owned = tmp_path / "Sorigul_SelfTest_fixed"
    original_local = "C:/original/local"
    original_home = "C:/original/home"
    monkeypatch.setenv("LOCALAPPDATA", original_local)
    monkeypatch.setenv("HOME", original_home)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    cleaned = []

    def create_temp_root(**kwargs):
        assert kwargs["prefix"] == "Sorigul_SelfTest_"
        owned.mkdir()
        return str(owned)

    def remove_tree(path):
        cleaned.append(Path(path))

    with sidecar_main._isolated_self_test_app_data(create_temp_root, remove_tree) as root:
        assert root == owned.resolve()
        assert Path(os.environ["LOCALAPPDATA"]).resolve() == (root / "LocalAppData")
        assert Path(os.environ["HOME"]).resolve() == (root / "Home")
        assert Path(os.environ["XDG_CONFIG_HOME"]).resolve() == (root / "XdgConfig")

        from src.utils.paths import get_app_data_dir

        resolved = get_app_data_dir()
        assert sidecar_main._is_path_within(resolved, root)
        assert not sidecar_main._is_path_within(resolved, Path(original_local))

    assert os.environ["LOCALAPPDATA"] == original_local
    assert os.environ["HOME"] == original_home
    assert "XDG_CONFIG_HOME" not in os.environ
    assert cleaned == [owned.resolve()]


def test_self_test_app_data_context_restores_environment_after_check_exception(
    tmp_path, monkeypatch
):
    owned = tmp_path / "Sorigul_SelfTest_exception"
    monkeypatch.setenv("LOCALAPPDATA", "original-local")
    monkeypatch.delenv("HOME", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    cleaned = []

    def create_temp_root(**kwargs):
        owned.mkdir()
        return str(owned)

    with pytest.raises(RuntimeError, match="check failed"):
        with sidecar_main._isolated_self_test_app_data(
            create_temp_root, lambda path: cleaned.append(Path(path))
        ):
            raise RuntimeError("check failed")

    assert os.environ["LOCALAPPDATA"] == "original-local"
    assert "HOME" not in os.environ
    assert "XDG_CONFIG_HOME" not in os.environ
    assert cleaned == [owned.resolve()]


def test_self_test_app_data_cleanup_failure_is_explicit_and_never_expands_target(
    tmp_path, monkeypatch
):
    owned = tmp_path / "Sorigul_SelfTest_cleanup"
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.delenv("HOME", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    cleanup_targets = []

    def create_temp_root(**kwargs):
        owned.mkdir()
        return str(owned)

    def fail_cleanup(path):
        cleanup_targets.append(Path(path))
        raise OSError("locked")

    with pytest.raises(
        sidecar_main.SelfTestAppDataCleanupError,
        match="SELF_TEST_APP_DATA_CLEANUP_FAILED",
    ):
        with sidecar_main._isolated_self_test_app_data(create_temp_root, fail_cleanup):
            pass

    assert cleanup_targets == [owned.resolve()]
    assert "LOCALAPPDATA" not in os.environ
    assert "HOME" not in os.environ
    assert "XDG_CONFIG_HOME" not in os.environ


def test_self_test_establishes_isolation_before_application_import(monkeypatch):
    observed = {}

    def run_checks(checks, progress):
        check_map = dict(checks)
        observed["local"] = os.environ["LOCALAPPDATA"]
        observed["home"] = os.environ["HOME"]
        observed["xdg"] = os.environ["XDG_CONFIG_HOME"]
        check_map["self_test_app_data_isolation"]()
        check_map["fastapi_app_import"]()
        return True

    monkeypatch.setattr(sidecar_main, "_run_self_test_checks", run_checks)

    assert sidecar_main._self_test() == 0
    assert "Sorigul_SelfTest_" in observed["local"]
    assert "Sorigul_SelfTest_" in observed["home"]
    assert "Sorigul_SelfTest_" in observed["xdg"]


def test_candidate_validation_precedes_transactional_promotion():
    script = (REPO_ROOT / "scripts/build_backend_sidecar.ps1").read_text(encoding="utf-8")

    candidate = script.index('$CandidateDir = Join-Path $TempRoot "candidate"')
    self_test = script.index("$SelfTestProcess = Start-Process")
    completeness = script.index("PACKAGED_SELFTEST_INCOMPLETE")
    manifest = script.index('$CandidateManifest = Join-Path $CandidateDir')
    promotion = script.rindex("Publish-StagedArtifacts")
    final_target = script.index('$StagedExe = Join-Path $BinariesDir')

    assert candidate < self_test < completeness < manifest < final_target
    assert self_test < promotion
    assert "CANDIDATE_PROMOTION_ROLLBACK_FAILED" in script
    assert "finally {" in script
    assert "Remove-Item -LiteralPath $TempRoot -Recurse -Force" in script


def test_installer_requires_one_current_run_msi_and_manifest_resource():
    installer = (REPO_ROOT / "scripts/build_windows_installer.ps1").read_text(encoding="utf-8")
    release_config = (
        REPO_ROOT / "frontend/src-tauri/tauri.release.conf.json"
    ).read_text(encoding="utf-8")
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "Select-Object -First 1" not in installer
    assert "$PreBuildMsiInventory" in installer
    assert "$PostBuildMsiInventory" in installer
    assert "$TauriBuildStartUtc" in installer
    assert "MSI_CURRENT_RUN_ARTIFACT_MISSING" in installer
    assert "MSI_CURRENT_RUN_ARTIFACT_AMBIGUOUS" in installer
    assert "BUILD_MANIFEST_MISSING" in installer
    assert (
        '"binaries/sorigul-build-manifest.json": "sorigul-build-manifest.json"'
        in release_config
    )
    assert "tauri.release.conf.json" in installer
    assert "frontend/src-tauri/binaries/sorigul-build-manifest.json" in gitignore.splitlines()


def test_manifest_contains_release_identity_without_personal_data_fields():
    script = (REPO_ROOT / "scripts/build_backend_sidecar.ps1").read_text(encoding="utf-8")
    required_fields = (
        "schema_version",
        "source_head",
        "generated_at_utc",
        "tracked_tree_clean",
        "core_sidecar_size_limit_mib",
        "sidecar_size",
        "sidecar_sha256",
        "ffmpeg_size",
        "ffmpeg_sha256",
        "release_input_sha256",
    )

    for field in required_fields:
        assert f"{field} =" in script
    for forbidden in ("username =", "user_home =", "credential =", "token =", "mp3_path ="):
        assert forbidden not in script.lower()


def test_local_manifest_requirement_is_a_scalar_string_and_round_trip_validated():
    script = (REPO_ROOT / "scripts/build_local_whisper_runtime.ps1").read_text(encoding="utf-8")

    assert '$ExpectedTorch = "torch==2.13.0+cu130"' in script
    assert '$ExpectedCuda = "13.0"' in script
    assert "$ManifestJson | ConvertFrom-Json" in script
    assert "$RoundTrippedManifest.torch_requirement -is [string]" in script
    assert "$RoundTrippedManifest.torch_requirement -cne $ExpectedTorch" in script
    assert "$RoundTrippedManifest.expected_cuda -cne $ExpectedCuda" in script
    assert "LOCAL_RUNTIME_MANIFEST_INVALID" in script


def test_installer_rejects_malformed_or_stale_manifest_before_frontend_build():
    installer = (REPO_ROOT / "scripts/build_windows_installer.ps1").read_text(encoding="utf-8")

    validation = installer.index("BUILD_MANIFEST_CORE_SIZE_POLICY_INVALID")
    frontend = installer.index('Write-Step "Building frontend production bundle"')
    tauri = installer.index('Write-Step "Building Windows MSI')

    assert validation < frontend < tauri
    assert "$Manifest.core_sidecar_size_limit_mib -is [int]" in installer
    assert "$Manifest.core_sidecar_size_limit_mib -le 0" in installer
    assert (
        "$CoreMsiSizeLimitBytes = [long]$Manifest.core_sidecar_size_limit_mib * 1MB"
        in installer
    )
    assert "BUILD_MANIFEST_CORE_SIZE_POLICY_INVALID" in installer
    assert "CORE_MSI_SIZE_REGRESSION" in installer
    assert "$CurrentSourceHeadOutput = @(& git rev-parse HEAD)" in installer
    assert "$CurrentSourceHeadOutput.Count -ne 1" in installer
    assert "$Manifest.source_head -cne $CurrentSourceHead" in installer
    assert "BUILD_MANIFEST_SOURCE_HEAD_MISMATCH" in installer
    assert "$Manifest.tracked_tree_clean -is [bool]" in installer


def test_windows_powershell_manifest_requirement_serializes_as_scalar_string(tmp_path):
    if os.name != "nt":
        pytest.skip("Windows PowerShell regression")

    powershell = (
        Path(os.environ["SystemRoot"])
        / "System32"
        / "WindowsPowerShell"
        / "v1.0"
        / "powershell.exe"
    )
    if not powershell.is_file():
        pytest.skip("Windows PowerShell is not installed")

    requirements = tmp_path / "requirements-torch-cuda.txt"
    requirements.write_text(
        "# release CUDA runtime\ntorch==2.13.0+cu130\n", encoding="utf-8"
    )
    environment = os.environ.copy()
    environment["SORIGUL_TEST_TORCH_REQUIREMENTS"] = str(requirements)
    regression = r"""
$TorchRequirementLines = @(
    foreach ($Line in [System.IO.File]::ReadAllLines($env:SORIGUL_TEST_TORCH_REQUIREMENTS)) {
        $TrimmedLine = [string]$Line.Trim()
        if ($TrimmedLine -match '^torch==[^\s]+$') {
            $TrimmedLine
        }
    }
)
if ($TorchRequirementLines.Count -ne 1) { exit 21 }
$TorchRequirement = [string]$TorchRequirementLines[0]
$ManifestJson = ([ordered]@{
    torch_requirement = $TorchRequirement
    expected_cuda = "13.0"
    source_head = "test-head"
} | ConvertTo-Json -Depth 4) + "`n"
$RoundTrippedManifest = $ManifestJson | ConvertFrom-Json
if (-not ($RoundTrippedManifest.torch_requirement -is [string])) { exit 22 }
if ($RoundTrippedManifest.torch_requirement -cne "torch==2.13.0+cu130") { exit 23 }
[Console]::Out.Write($ManifestJson)
"""

    completed = subprocess.run(
        [str(powershell), "-NoProfile", "-NonInteractive", "-Command", regression],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=environment,
    )

    assert completed.returncode == 0, completed.stderr
    manifest = json.loads(completed.stdout)
    assert type(manifest["torch_requirement"]) is str
    assert manifest["torch_requirement"] == "torch==2.13.0+cu130"
