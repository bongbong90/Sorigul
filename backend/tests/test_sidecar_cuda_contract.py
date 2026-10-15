from pathlib import Path
from types import SimpleNamespace

import pytest
from packaging.requirements import Requirement

from src import local_runtime_main, sidecar_main


REPO_ROOT = Path(__file__).resolve().parents[2]


class FakeCuda:
    def __init__(self, available, device_count=0, device_name=""):
        self._available = available
        self._device_count = device_count
        self._device_name = device_name
        self.synchronized = False

    def is_available(self):
        return self._available

    def device_count(self):
        return self._device_count

    def get_device_name(self, index):
        assert index == 0
        return self._device_name

    def synchronize(self):
        self.synchronized = True


class FakeTensor:
    def __init__(self, value):
        self.value = value

    def cpu(self):
        return self

    def tolist(self):
        return self.value


def fake_torch(cuda_version, available, device_count=0, device_name=""):
    cuda = FakeCuda(available, device_count, device_name)
    return SimpleNamespace(
        __version__="2.13.0+cu130",
        version=SimpleNamespace(cuda=cuda_version),
        cuda=cuda,
        float32="float32",
        tensor=lambda value, **_kwargs: FakeTensor(value),
        matmul=lambda _left, _right: FakeTensor([[19.0, 22.0], [43.0, 50.0]]),
    )


def test_cuda_checks_belong_to_local_runtime_and_accept_available_cuda():
    torch = fake_torch("13.0", True, 1, "NVIDIA GeForce RTX 5060")
    assert local_runtime_main._cuda_build_detail(torch).startswith("torch=2.13.0+cu130")
    assert "device=NVIDIA GeForce RTX 5060" in local_runtime_main._cuda_available_detail(torch)
    assert local_runtime_main._cuda_compute_detail(torch) == "2x2 CUDA matrix multiply verified"
    assert torch.cuda.synchronized is True
    assert not hasattr(sidecar_main, "_cuda_build_detail")


@pytest.mark.parametrize(
    "torch",
    [fake_torch(None, False), fake_torch("13.0", False, 0), fake_torch("13.0", True, 0)],
)
def test_local_runtime_cuda_checks_reject_unusable_runtime(torch):
    if torch.version.cuda is None:
        with pytest.raises(RuntimeError, match="CPU-only"):
            local_runtime_main._cuda_build_detail(torch)
    else:
        assert local_runtime_main._cuda_build_detail(torch)
    with pytest.raises(RuntimeError):
        local_runtime_main._cuda_available_detail(torch)


def test_cuda_requirement_locks_local_version_variant():
    lines = (REPO_ROOT / "tools/requirements-torch-cuda.txt").read_text(encoding="utf-8").splitlines()
    torch_requirement = next(line for line in lines if line.startswith("torch=="))
    parsed = Requirement(torch_requirement)
    assert torch_requirement == "torch==2.13.0+cu130"
    assert parsed.specifier.contains("2.13.0+cu130")
    assert not parsed.specifier.contains("2.13.0+cpu")


def test_core_and_local_pyinstaller_specs_enforce_dependency_boundary():
    core = (REPO_ROOT / "backend/packaging/sorigul_backend.spec").read_text(encoding="utf-8")
    local = (REPO_ROOT / "backend/packaging/sorigul_local_runtime.spec").read_text(encoding="utf-8")
    assert 'collect_dynamic_libs("torch")' not in core
    assert 'collect_data_files("whisper")' not in core
    assert 'excludes=["torch", "whisper", "numba", "llvmlite"]' in core
    assert 'collect_dynamic_libs("torch")' in local
    assert 'collect_data_files("whisper")' in local
    assert "binaries=torch_binaries" in local
    assert 'name="sorigul-local-whisper"' in local
    assert "console=True" in local


def test_core_build_has_no_local_install_and_scans_archive():
    core = (REPO_ROOT / "scripts/build_backend_sidecar.ps1").read_text(encoding="utf-8")
    local = (REPO_ROOT / "scripts/build_local_whisper_runtime.ps1").read_text(encoding="utf-8")
    assert "requirements-torch-cuda.txt" not in core
    assert "requirements-whisper.txt" not in core
    assert "CUDA_RELEASE_RUNTIME_UNAVAILABLE" not in core
    assert "PyInstaller.utils.cliutils.archive_viewer" in core
    for pattern in (
        "torch",
        "cuda",
        "torch_cuda",
        "cublas",
        "cudnn",
        "cufft",
        "cusparse",
        "cusolver",
    ):
        assert f'"{pattern}"' in core
    assert '"(^|[\\\\/., ])whisper($|[\\\\/., ])"' in core
    assert "$CoreArtifactSizeLimitMiB = 250" in core
    assert "$CoreSidecarSizeLimitBytes = $CoreArtifactSizeLimitMiB * 1MB" in core
    install_order = [
        local.index(path)
        for path in (
            "requirements-torch-cuda.txt",
            "backend\\requirements.txt",
            "requirements-whisper.txt",
            "requirements-packaging.txt",
        )
    ]
    assert install_order == sorted(install_order)
    assert '"backend\\packaging\\sorigul_local_runtime.spec"' in local
    assert 'EXPECTED_TORCH' not in core
    assert '$ExpectedTorch = "torch==2.13.0+cu130"' in local
    assert '$ExpectedCuda = "13.0"' in local


def test_core_self_test_excludes_local_runtime_and_local_self_test_is_bounded():
    core_script = (REPO_ROOT / "scripts/build_backend_sidecar.ps1").read_text(encoding="utf-8")
    local_script = (REPO_ROOT / "scripts/build_local_whisper_runtime.ps1").read_text(encoding="utf-8")
    for check in ("whisper_import", "torch_import", "torch_cuda_build", "torch_cuda_available", "torch_cuda_compute"):
        assert check not in sidecar_main.REQUIRED_SELF_TEST_CHECKS
        assert f'"{check}"' not in core_script
    assert "bundled_ffmpeg_execution" in sidecar_main.REQUIRED_SELF_TEST_CHECKS
    assert "$SelfTestTimeoutSeconds = 300" in local_script
    assert '& $TaskkillPath /PID $SelfTestProcess.Id /T /F' in local_script
    assert "LOCAL_RUNTIME_SELFTEST_TIMEOUT_CLEANUP_FAILED" in local_script
    assert '-ArgumentList "--self-test"' in local_script
    assert "-WindowStyle Hidden" in local_script


def test_local_runtime_manifest_and_install_location_are_explicit():
    script = (REPO_ROOT / "scripts/build_local_whisper_runtime.ps1").read_text(encoding="utf-8")
    for field in (
        "runtime_type",
        "runtime_version",
        "protocol_version",
        "torch_requirement",
        "expected_cuda",
        "worker_sha256",
        "artifact_sha256",
        "source_head",
        "tracked_tree_clean",
        "release_input_sha256",
    ):
        assert f"{field} =" in script
    assert '"Sorigul\\runtime\\local-whisper\\v1"' in script
    assert "runtime-manifest.json" in script
    assert "sorigul-local-whisper.exe" in script
    assert "Invoke-WebRequest" not in script
    assert "Start-BitsTransfer" not in script
