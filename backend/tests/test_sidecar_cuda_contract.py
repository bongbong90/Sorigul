from pathlib import Path
from types import SimpleNamespace

import pytest
from packaging.requirements import Requirement

from src import sidecar_main


class FakeCuda:
    def __init__(self, available, device_count=0, device_name=""):
        self._available = available
        self._device_count = device_count
        self._device_name = device_name

    def is_available(self):
        return self._available

    def device_count(self):
        return self._device_count

    def get_device_name(self, index):
        assert index == 0
        return self._device_name


def fake_torch(cuda_version, available, device_count=0, device_name=""):
    return SimpleNamespace(
        __version__="2.13.0",
        version=SimpleNamespace(cuda=cuda_version),
        cuda=FakeCuda(available, device_count, device_name),
    )


def test_cuda_build_and_runtime_checks_accept_available_cuda():
    torch = fake_torch("13.0", True, 1, "NVIDIA GeForce RTX 5060")

    assert sidecar_main._cuda_build_detail(torch).startswith("torch=2.13.0")
    assert "device=NVIDIA GeForce RTX 5060" in sidecar_main._cuda_available_detail(torch)


@pytest.mark.parametrize(
    "torch",
    [
        fake_torch(None, False),
        fake_torch("13.0", False, 0),
        fake_torch("13.0", True, 0),
    ],
)
def test_cuda_release_checks_reject_unusable_runtime(torch):
    if torch.version.cuda is None:
        with pytest.raises(RuntimeError, match="CPU-only"):
            sidecar_main._cuda_build_detail(torch)
    else:
        assert sidecar_main._cuda_build_detail(torch)

    with pytest.raises(RuntimeError):
        sidecar_main._cuda_available_detail(torch)


def test_cuda_requirement_locks_local_version_variant():
    repo_root = Path(__file__).resolve().parents[2]
    requirement_lines = (
        repo_root / "tools/requirements-torch-cuda.txt"
    ).read_text(encoding="utf-8").splitlines()
    torch_requirement = next(line for line in requirement_lines if line.startswith("torch=="))
    parsed = Requirement(torch_requirement)

    assert torch_requirement == "torch==2.13.0+cu130"
    assert parsed.specifier.contains("2.13.0+cu130")
    assert not parsed.specifier.contains("2.13.0+cpu")


def test_cuda_contract_files_are_explicit():
    repo_root = Path(__file__).resolve().parents[2]
    requirement = (repo_root / "tools/requirements-torch-cuda.txt").read_text(encoding="utf-8")
    build_script = (repo_root / "scripts/build_backend_sidecar.ps1").read_text(encoding="utf-8")
    spec = (repo_root / "backend/packaging/sorigul_backend.spec").read_text(encoding="utf-8")

    assert "https://download.pytorch.org/whl/cu130" in requirement
    assert "torch==2.13.0+cu130" in requirement.splitlines()
    install_order = [
        build_script.index(path)
        for path in (
            "requirements-torch-cuda.txt",
            "backend\\requirements.txt",
            "requirements-whisper.txt",
            "requirements-packaging.txt",
        )
    ]
    assert install_order == sorted(install_order)
    pyinstaller_position = build_script.index("Running PyInstaller")
    assert build_script.index('EXPECTED_TORCH = "2.13.0+cu130"') < pyinstaller_position
    assert build_script.index('EXPECTED_CUDA = "13.0"') < pyinstaller_position
    assert build_script.index("CUDA_RELEASE_VARIANT_MISMATCH") < pyinstaller_position
    assert "CUDA_RELEASE_RUNTIME_UNAVAILABLE" in build_script
    assert build_script.index("CUDA_RELEASE_RUNTIME_UNAVAILABLE") < pyinstaller_position
    assert "torch.version.cuda" in build_script
    assert "torch.cuda.is_available" in build_script
    assert "torch.cuda.device_count" in build_script
    assert "collect_dynamic_libs(\"torch\")" in spec
    assert "binaries=torch_binaries" in spec
