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


def test_cuda_preflight_uses_unique_temp_python_file_with_finally_cleanup():
    repo_root = Path(__file__).resolve().parents[2]
    build_script = (repo_root / "scripts/build_backend_sidecar.ps1").read_text(encoding="utf-8")

    assert "-c $CudaPreflight" not in build_script
    assert '$CudaPreflightId = [guid]::NewGuid().ToString("N")' in build_script
    assert '"Sorigul_CudaPreflight_$CudaPreflightId.py"' in build_script
    write_position = build_script.index("[System.IO.File]::WriteAllText(")
    execute_position = build_script.index("& $VenvPython $CudaPreflightPath")
    finally_position = build_script.index("} finally {", execute_position)
    cleanup_guard_position = build_script.index(
        "Test-Path -LiteralPath $CudaPreflightPath", finally_position
    )
    cleanup_position = build_script.index(
        "Remove-Item -LiteralPath $CudaPreflightPath -Force", finally_position
    )

    assert write_position < execute_position < finally_position
    assert finally_position < cleanup_guard_position < cleanup_position
    assert 'EXPECTED_TORCH = "2.13.0+cu130"' in build_script
    assert 'EXPECTED_CUDA = "13.0"' in build_script
    assert "$CudaPreflightExit -eq 41" in build_script
    assert "$CudaPreflightExit -eq 42" in build_script


def test_ffmpeg_resolver_uses_utf8_temp_result_without_stdout_capture():
    repo_root = Path(__file__).resolve().parents[2]
    build_script = (repo_root / "scripts/build_backend_sidecar.ps1").read_text(encoding="utf-8")

    resolver_start = build_script.index('$FfmpegResolverScript = @\'')
    resolver_end = build_script.index('$StagedFfmpeg = Join-Path', resolver_start)
    resolver = build_script[resolver_start:resolver_end]

    assert "(& $VenvPython -c" not in resolver
    assert "print(imageio_ffmpeg.get_ffmpeg_exe())" not in resolver
    assert '$FfmpegResolverId = [guid]::NewGuid().ToString("N")' in resolver
    assert '"Sorigul_FfmpegResolver_$FfmpegResolverId.py"' in resolver
    assert '"Sorigul_FfmpegResolver_$FfmpegResolverId.txt"' in resolver
    assert 'os.environ["SORIGUL_FFMPEG_RESOLVER_RESULT"]' in resolver
    assert 'encoding="utf-8"' in resolver
    assert "[System.IO.File]::ReadAllText(" in resolver
    assert "[System.Text.Encoding]::UTF8" in resolver
    assert "Test-Path -LiteralPath $FfmpegResultPath -PathType Leaf" in resolver
    assert "Test-Path -LiteralPath $FfmpegSource -PathType Leaf" in resolver

    execute_position = resolver.index("& $VenvPython $FfmpegResolverPath")
    read_position = resolver.index("[System.IO.File]::ReadAllText(")
    finally_position = resolver.index("} finally {", execute_position)
    env_cleanup_position = resolver.index("$null,", finally_position)
    script_cleanup_position = resolver.index(
        "Remove-Item -LiteralPath $FfmpegResolverPath -Force", finally_position
    )
    result_cleanup_position = resolver.index(
        "Remove-Item -LiteralPath $FfmpegResultPath -Force", finally_position
    )

    assert execute_position < read_position < finally_position
    assert finally_position < env_cleanup_position
    assert finally_position < script_cleanup_position
    assert finally_position < result_cleanup_position


def test_packaged_self_test_uses_bounded_watchdog_and_complete_fresh_log():
    repo_root = Path(__file__).resolve().parents[2]
    build_script = (repo_root / "scripts/build_backend_sidecar.ps1").read_text(encoding="utf-8")
    spec = (repo_root / "backend/packaging/sorigul_backend.spec").read_text(encoding="utf-8")

    block_start = build_script.index("$SelfTestLog = Join-Path")
    block_end = build_script.index('Write-Host "Sidecar build + self-test PASSED."', block_start)
    self_test_block = build_script[block_start:block_end]

    remove_log_position = self_test_block.index(
        "Remove-Item -LiteralPath $SelfTestLog -Force"
    )
    start_process_position = self_test_block.index("$SelfTestProcess = Start-Process")
    deadline_position = self_test_block.index("$SelfTestDeadline")
    timeout_position = self_test_block.index("PACKAGED_SELFTEST_TIMEOUT")
    exit_code_position = self_test_block.index(
        "$SelfTestExit = $SelfTestProcess.ExitCode"
    )
    log_guard_position = self_test_block.index(
        "Test-Path -LiteralPath $SelfTestLog -PathType Leaf"
    )
    log_read_position = self_test_block.index("[System.IO.File]::ReadAllText(")
    completeness_position = self_test_block.index("PACKAGED_SELFTEST_INCOMPLETE")
    exit_gate_position = self_test_block.index("if ($SelfTestExit -ne 0)")

    assert '& ".\\sorigul-backend.exe" --self-test' not in self_test_block
    assert "$SelfTestExit = $LASTEXITCODE" not in self_test_block
    assert '-FilePath $CandidateExe' in self_test_block
    assert '-ArgumentList "--self-test"' in self_test_block
    assert '-WorkingDirectory $CandidateDir' in self_test_block
    assert "-Wait" not in self_test_block
    assert "-PassThru" in self_test_block
    assert "$SelfTestTimeoutSeconds = 300" in build_script
    assert "taskkill.exe /PID $SelfTestProcess.Id /T /F" in self_test_block
    assert "PACKAGED_SELFTEST_TIMEOUT_CLEANUP_FAILED" in self_test_block
    assert "PACKAGED_SELFTEST_LOG_MISSING" in self_test_block
    assert "[System.Text.Encoding]::UTF8" in self_test_block
    assert "    console=False," in spec

    required_checks = (
        "fastapi_app_import",
        "uvicorn_import",
        "google_drive_runtime_import",
        "whisper_import",
        "torch_import",
        "torch_cuda_build",
        "torch_cuda_available",
        "torch_cuda_compute",
        "bundled_ffmpeg_execution",
        "audio_metadata_service_import",
        "runtime_path_initialization",
    )
    for check in required_checks:
        assert f'"{check}"' in self_test_block

    assert remove_log_position < start_process_position < exit_code_position
    assert start_process_position < deadline_position < timeout_position
    assert exit_code_position < log_guard_position < log_read_position
    assert log_read_position < completeness_position < exit_gate_position


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
