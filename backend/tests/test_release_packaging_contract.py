import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from src import sidecar_main


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

    detail = sidecar_main._cuda_compute_detail(torch)

    assert detail == "2x2 CUDA matrix multiply verified"
    assert len(torch.tensor_calls) == 2
    assert all(call[1] == {"device": "cuda", "dtype": "float32"} for call in torch.tensor_calls)
    assert torch.cuda.synchronized is True


def test_cuda_compute_rejects_unexpected_result():
    torch = FakeTorch([[0.0, 0.0], [0.0, 0.0]])

    with pytest.raises(RuntimeError, match="unexpected CUDA matrix product"):
        sidecar_main._cuda_compute_detail(torch)


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


def test_required_self_test_contract_has_exactly_eleven_checks():
    assert len(sidecar_main.REQUIRED_SELF_TEST_CHECKS) == 11
    assert "torch_cuda_compute" in sidecar_main.REQUIRED_SELF_TEST_CHECKS
    assert "bundled_ffmpeg_execution" in sidecar_main.REQUIRED_SELF_TEST_CHECKS


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
    config = (REPO_ROOT / "frontend/src-tauri/tauri.conf.json").read_text(encoding="utf-8")
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "Select-Object -First 1" not in installer
    assert "$PreBuildMsiInventory" in installer
    assert "$PostBuildMsiInventory" in installer
    assert "$TauriBuildStartUtc" in installer
    assert "MSI_CURRENT_RUN_ARTIFACT_MISSING" in installer
    assert "MSI_CURRENT_RUN_ARTIFACT_AMBIGUOUS" in installer
    assert "BUILD_MANIFEST_MISSING" in installer
    assert '"binaries/sorigul-build-manifest.json": "sorigul-build-manifest.json"' in config
    assert "frontend/src-tauri/binaries/sorigul-build-manifest.json" in gitignore.splitlines()


def test_manifest_contains_release_identity_without_personal_data_fields():
    script = (REPO_ROOT / "scripts/build_backend_sidecar.ps1").read_text(encoding="utf-8")
    required_fields = (
        "schema_version",
        "source_head",
        "generated_at_utc",
        "tracked_tree_clean",
        "torch_requirement",
        "expected_cuda",
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
