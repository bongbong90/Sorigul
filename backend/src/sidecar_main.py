"""Packaged backend entrypoint.

Supports:
  sorigul-backend.exe --port 8000        (normal run, same FastAPI app as dev)
  sorigul-backend.exe --self-test        (import/runtime checks only, no server,
                                           no model download, no Google login,
                                           no Drive upload, no transcription)

`--self-test` exists so a build script can verify a freshly produced
executable actually carries a working runtime (FastAPI, uvicorn, Google Drive
client libraries, whisper, torch, ffmpeg) without paying the cost, or the
side effects, of really starting the server or touching a network/model.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable, Iterable


BUNDLED_FFMPEG_TIMEOUT_SECONDS = 15
JOB_STORAGE_EXIT_CODES = {
    "JOB_STORAGE_READ_FAILED": 20,
    "JOB_STORAGE_QUARANTINE_FAILED": 21,
    "JOB_STORAGE_WRITE_FAILED": 22,
}
REQUIRED_SELF_TEST_CHECKS = (
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


def _cuda_build_detail(torch_module) -> str:
    cuda_version = torch_module.version.cuda
    if cuda_version is None:
        raise RuntimeError(f"CPU-only torch build: {torch_module.__version__}")
    return f"torch={torch_module.__version__}, cuda={cuda_version}"


def _cuda_available_detail(torch_module) -> str:
    device_count = torch_module.cuda.device_count()
    if not torch_module.cuda.is_available() or device_count < 1:
        raise RuntimeError(
            "CUDA runtime unavailable"
            f" (torch={torch_module.__version__}, cuda={torch_module.version.cuda},"
            f" devices={device_count})"
        )
    device_name = torch_module.cuda.get_device_name(0)
    if not device_name:
        raise RuntimeError("CUDA device name unavailable")
    return f"torch={torch_module.__version__}, cuda={torch_module.version.cuda}, device={device_name}"


def _cuda_compute_detail(torch_module) -> str:
    """Run a tiny real CUDA kernel and verify its result on the host."""
    left = torch_module.tensor(
        [[1.0, 2.0], [3.0, 4.0]], device="cuda", dtype=torch_module.float32
    )
    right = torch_module.tensor(
        [[5.0, 6.0], [7.0, 8.0]], device="cuda", dtype=torch_module.float32
    )
    result = torch_module.matmul(left, right)
    torch_module.cuda.synchronize()
    actual = result.cpu().tolist()
    expected = [[19.0, 22.0], [43.0, 50.0]]
    if actual != expected:
        raise RuntimeError(f"unexpected CUDA matrix product: {actual!r}")
    return "2x2 CUDA matrix multiply verified"


def _bundled_ffmpeg_detail(
    executable: Path | None = None,
    run: Callable = subprocess.run,
) -> str:
    """Execute the exact ffmpeg sibling shipped beside the frozen sidecar."""
    sidecar_executable = Path(executable or sys.executable)
    ffmpeg_path = sidecar_executable.parent / "ffmpeg.exe"
    if not ffmpeg_path.is_file():
        raise RuntimeError(f"bundled ffmpeg sibling missing: {ffmpeg_path.name}")

    completed = run(
        [str(ffmpeg_path), "-version"],
        capture_output=True,
        text=True,
        errors="replace",
        timeout=BUNDLED_FFMPEG_TIMEOUT_SECONDS,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        check=False,
    )
    output = f"{completed.stdout or ''}\n{completed.stderr or ''}".lower()
    if completed.returncode != 0:
        raise RuntimeError(f"bundled ffmpeg exited with code {completed.returncode}")
    if "ffmpeg version" not in output:
        raise RuntimeError("bundled ffmpeg output did not identify ffmpeg")
    return f"{ffmpeg_path.name} -version"


class _SelfTestProgress:
    """Emit self-test transitions and durably append them for frozen builds."""

    def __init__(self, log_path: Path | None = None):
        self.log_path = log_path
        if self.log_path is not None:
            self.log_path.write_text("", encoding="utf-8")

    def emit(self, line: str) -> None:
        if sys.stdout is not None:
            print(line, flush=True)
        if self.log_path is None:
            return
        with self.log_path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(line + "\n")
            stream.flush()
            os.fsync(stream.fileno())


def _run_self_test_checks(
    checks: Iterable[tuple[str, Callable[[], object]]],
    progress: _SelfTestProgress,
) -> bool:
    ok = True
    for name, check in checks:
        progress.emit(f"[self-test] {name}: START")
        try:
            check()
        except Exception as exc:  # noqa: BLE001 - each failure is release evidence
            progress.emit(f"[self-test] {name}: FAIL ({exc})")
            ok = False
        else:
            progress.emit(f"[self-test] {name}: PASS")
    return ok


def job_storage_exit_code(code: str) -> int:
    """Stable desktop boundary for startup-time jobs.json failures."""
    return JOB_STORAGE_EXIT_CODES.get(code, 1)


def _self_test() -> int:

    def check_fastapi_app() -> None:
        from src.main import app

        assert app.title == "Sorigul Core Backend"

    def check_uvicorn() -> None:
        import uvicorn  # noqa: F401

    def check_google_drive_runtime() -> None:
        import google.auth.transport.requests  # noqa: F401
        import google_auth_oauthlib.flow  # noqa: F401
        import googleapiclient.discovery  # noqa: F401

    def check_whisper() -> None:
        import whisper  # noqa: F401

    def check_torch() -> None:
        import torch  # noqa: F401

    def check_torch_cuda_build() -> None:
        import torch

        _cuda_build_detail(torch)

    def check_torch_cuda_available() -> None:
        import torch

        _cuda_available_detail(torch)

    def check_torch_cuda_compute() -> None:
        import torch

        _cuda_compute_detail(torch)

    def check_bundled_ffmpeg() -> None:
        _bundled_ffmpeg_detail()

    def check_audio_metadata() -> None:
        import mutagen  # noqa: F401
        from mutagen.mp3 import MP3  # noqa: F401
        from src.services.audio_metadata import AudioMetadataService  # noqa: F401

    def check_runtime_paths() -> None:
        from src.utils.paths import get_app_data_dir

        get_app_data_dir()

    checks = (
        ("fastapi_app_import", check_fastapi_app),
        ("uvicorn_import", check_uvicorn),
        ("google_drive_runtime_import", check_google_drive_runtime),
        ("whisper_import", check_whisper),
        ("torch_import", check_torch),
        ("torch_cuda_build", check_torch_cuda_build),
        ("torch_cuda_available", check_torch_cuda_available),
        ("torch_cuda_compute", check_torch_cuda_compute),
        ("bundled_ffmpeg_execution", check_bundled_ffmpeg),
        ("audio_metadata_service_import", check_audio_metadata),
        ("runtime_path_initialization", check_runtime_paths),
    )
    assert tuple(name for name, _ in checks) == REQUIRED_SELF_TEST_CHECKS

    # The windowed frozen build has no useful console. Creating and appending
    # this file is part of the release gate, so an I/O failure must fail the
    # self-test instead of being silently ignored.
    log_path = None
    if getattr(sys, "frozen", False):
        log_path = Path(sys.executable).parent / "sorigul-backend-selftest.log"
    try:
        progress = _SelfTestProgress(log_path)
        ok = _run_self_test_checks(checks, progress)
    except OSError as exc:
        if sys.stderr is not None:
            print(f"[self-test] progress_log: FAIL ({exc})", file=sys.stderr, flush=True)
        return 1

    return 0 if ok else 1


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(prog="sorigul-backend")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return _self_test()

    import uvicorn

    try:
        from src.main import app
    except Exception as exc:
        # Importing routes constructs JobManager. Expose only a stable process
        # code to the windowed parent, never a local path or traceback.
        from src.services.job_manager import JobStorageError

        if isinstance(exc, JobStorageError):
            return job_storage_exit_code(exc.code)
        raise

    uvicorn.run(app, host="127.0.0.1", port=args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
