import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from src.domain.transcription import (
    CancellationToken,
    EngineError,
    ErrorCategory,
    EventCallback,
    ProgressCallback,
    TranscriptionResult,
)
from src.services.output_bundle import BundlePaths, OutputBundleValidator
from src.services.windows_system import resolve_system32_executable
from src.utils.paths import get_app_data_dir


PROTOCOL_VERSION = 1
RUNTIME_VERSION = 1
RUNTIME_TYPE = "sorigul-local-whisper"
TORCH_REQUIREMENT = "torch==2.13.0+cu130"
EXPECTED_CUDA = "13.0"
RUNTIME_EXECUTABLE = "sorigul-local-whisper.exe"
RUNTIME_MANIFEST = "runtime-manifest.json"
CORE_BUILD_MANIFEST = "sorigul-build-manifest.json"
LOCAL_RUNTIME_TIMEOUT_SECONDS = 6 * 60 * 60
LOCAL_RUNTIME_POLL_INTERVAL_SECONDS = 0.2
LOCAL_RUNTIME_REAP_TIMEOUT_SECONDS = 10
LOCAL_RUNTIME_STDERR_LIMIT_BYTES = 16 * 1024
LOCAL_RUNTIME_STDOUT_LIMIT_BYTES = 1024 * 1024
LOCAL_RUNTIME_PROCESS_CLEANUP_FAILED = "LOCAL_RUNTIME_PROCESS_CLEANUP_FAILED"
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)


@dataclass(frozen=True)
class VerifiedRuntime:
    executable: Path
    fingerprint: tuple[int, int, int, int, int, int]
    source_head: str


def default_runtime_dir() -> Path:
    return get_app_data_dir() / "runtime" / "local-whisper" / f"v{RUNTIME_VERSION}"


def _engine_error(code: str, message: str, detail: str, *, fatal: bool = True) -> EngineError:
    return EngineError(
        code,
        ErrorCategory.RUNTIME,
        message,
        technical_detail=detail,
        fatal=fatal,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _valid_source_head(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 40
        and all(character in "0123456789abcdef" for character in value)
    )


def _packaged_core_source_head() -> Optional[str]:
    if not getattr(sys, "frozen", False):
        return None
    manifest_path = Path(sys.executable).resolve().parent.parent / CORE_BUILD_MANIFEST
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _engine_error(
            "LOCAL_RUNTIME_PROVENANCE_UNAVAILABLE",
            "Local Whisper 실행 환경의 출처를 확인하지 못했습니다.",
            f"invalid Core build manifest {manifest_path}: {exc}",
        ) from exc
    if (
        not isinstance(manifest, dict)
        or not _valid_source_head(manifest.get("source_head"))
        or type(manifest.get("tracked_tree_clean")) is not bool
        or manifest["tracked_tree_clean"] is not True
    ):
        raise _engine_error(
            "LOCAL_RUNTIME_PROVENANCE_UNAVAILABLE",
            "Local Whisper 실행 환경의 출처를 확인하지 못했습니다.",
            f"invalid Core build provenance in {manifest_path}",
        )
    return manifest["source_head"]


def verify_runtime(
    runtime_dir: Path, *, expected_source_head: Optional[str] = None
) -> VerifiedRuntime:
    manifest_path = runtime_dir / RUNTIME_MANIFEST
    executable = runtime_dir / RUNTIME_EXECUTABLE
    if not manifest_path.is_file() or not executable.is_file():
        raise _engine_error(
            "LOCAL_RUNTIME_MISSING",
            "Local Whisper 실행 환경이 설치되어 있지 않습니다.",
            f"expected {manifest_path} and {executable}",
        )

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _engine_error(
            "LOCAL_RUNTIME_INVALID",
            "Local Whisper 실행 환경 정보가 올바르지 않습니다.",
            str(exc),
        ) from exc
    if not isinstance(manifest, dict):
        raise _engine_error(
            "LOCAL_RUNTIME_INVALID",
            "Local Whisper 실행 환경 정보가 올바르지 않습니다.",
            "runtime manifest must be a JSON object",
        )

    if (
        type(manifest.get("runtime_version")) is not int
        or type(manifest.get("protocol_version")) is not int
        or manifest.get("runtime_version") != RUNTIME_VERSION
        or manifest.get("protocol_version") != PROTOCOL_VERSION
    ):
        raise _engine_error(
            "LOCAL_RUNTIME_VERSION_MISMATCH",
            "Local Whisper 실행 환경 버전이 현재 앱과 맞지 않습니다.",
            "runtime/protocol version mismatch",
        )

    expected_scalars = {
        "runtime_type": RUNTIME_TYPE,
        "torch_requirement": TORCH_REQUIREMENT,
        "expected_cuda": EXPECTED_CUDA,
    }
    for key, expected in expected_scalars.items():
        if type(manifest.get(key)) is not str or manifest[key] != expected:
            raise _engine_error(
                "LOCAL_RUNTIME_INVALID",
                "Local Whisper 실행 환경 정보가 올바르지 않습니다.",
                f"invalid {key}",
            )

    source_head = manifest.get("source_head")
    if (
        not _valid_source_head(source_head)
        or type(manifest.get("tracked_tree_clean")) is not bool
        or manifest["tracked_tree_clean"] is not True
    ):
        raise _engine_error(
            "LOCAL_RUNTIME_INVALID",
            "Local Whisper 실행 환경 정보가 올바르지 않습니다.",
            "invalid runtime source provenance",
        )
    if expected_source_head is not None and source_head != expected_source_head:
        raise _engine_error(
            "LOCAL_RUNTIME_PROVENANCE_MISMATCH",
            "Local Whisper 실행 환경이 현재 앱 빌드와 맞지 않습니다.",
            f"runtime source_head={source_head}; Core source_head={expected_source_head}",
        )

    hashes = (manifest.get("worker_sha256"), manifest.get("artifact_sha256"))
    if any(
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
        for value in hashes
    ):
        raise _engine_error(
            "LOCAL_RUNTIME_INVALID",
            "Local Whisper 실행 환경 정보가 올바르지 않습니다.",
            "invalid runtime hashes",
        )
    try:
        actual_hash = _sha256(executable)
        manifest_stat = manifest_path.stat()
        executable_stat = executable.stat()
    except OSError as exc:
        raise _engine_error(
            "LOCAL_RUNTIME_INVALID",
            "Local Whisper 실행 환경을 확인하지 못했습니다.",
            str(exc),
        ) from exc
    if hashes[0] != actual_hash or hashes[1] != actual_hash:
        raise _engine_error(
            "LOCAL_RUNTIME_INVALID",
            "Local Whisper 실행 환경 무결성 확인에 실패했습니다.",
            "runtime executable hash mismatch",
        )
    return VerifiedRuntime(
        executable=executable,
        fingerprint=(
            manifest_stat.st_mtime_ns,
            manifest_stat.st_ctime_ns,
            manifest_stat.st_size,
            executable_stat.st_mtime_ns,
            executable_stat.st_ctime_ns,
            executable_stat.st_size,
        ),
        source_head=source_head,
    )


def _stderr_tail(stream) -> str:
    try:
        stream.flush()
        size = stream.seek(0, 2)
        stream.seek(max(0, size - LOCAL_RUNTIME_STDERR_LIMIT_BYTES))
        return stream.read().decode("utf-8", errors="replace")
    except (OSError, ValueError):
        return ""


def _stdout_text(stream) -> str:
    try:
        stream.flush()
        size = stream.seek(0, 2)
        if size > LOCAL_RUNTIME_STDOUT_LIMIT_BYTES:
            raise ValueError("worker stdout exceeded protocol limit")
        stream.seek(0)
        return stream.read().decode("utf-8", errors="strict")
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise _engine_error(
            "LOCAL_RUNTIME_RESPONSE_INVALID",
            "Local Whisper 실행 결과를 확인하지 못했습니다.",
            str(exc),
            fatal=False,
        ) from exc


def _reap(process) -> None:
    steps = []
    if os.name == "nt" and getattr(process, "pid", None) is not None:
        try:
            completed = subprocess.run(
                [
                    str(resolve_system32_executable("taskkill.exe")),
                    "/PID",
                    str(process.pid),
                    "/T",
                    "/F",
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=LOCAL_RUNTIME_REAP_TIMEOUT_SECONDS,
                check=False,
                creationflags=_CREATE_NO_WINDOW,
            )
            steps.append(f"taskkill-tree=exit-{completed.returncode}")
        except (OSError, subprocess.TimeoutExpired) as exc:
            steps.append(f"taskkill-tree=error:{exc}")
        try:
            process.wait(timeout=LOCAL_RUNTIME_REAP_TIMEOUT_SECONDS)
            return
        except subprocess.TimeoutExpired:
            steps.append("wait-after-taskkill=timeout")
    for name, stop in (("terminate", process.terminate), ("kill", process.kill)):
        try:
            stop()
            steps.append(f"{name}=ok")
        except OSError as exc:
            steps.append(f"{name}=error:{exc}")
        try:
            process.wait(timeout=LOCAL_RUNTIME_REAP_TIMEOUT_SECONDS)
            return
        except subprocess.TimeoutExpired:
            steps.append(f"wait-after-{name}=timeout({LOCAL_RUNTIME_REAP_TIMEOUT_SECONDS}s)")
    pid = getattr(process, "pid", None)
    raise _engine_error(
        LOCAL_RUNTIME_PROCESS_CLEANUP_FAILED,
        "Local Whisper 프로세스를 안전하게 종료하지 못했습니다.",
        f"worker pid={pid} not reaped: {'; '.join(steps)}",
    )


class LocalWhisperEngine:
    MODEL_NAME = "medium"
    TRANSCRIBE_OPTIONS = {
        "language": "ko",
        "task": "transcribe",
        "temperature": 0,
        "beam_size": 5,
        "best_of": 5,
        "patience": 1.0,
        "condition_on_previous_text": False,
    }

    def __init__(
        self,
        runtime_dir: Optional[Path] = None,
        *,
        timeout_seconds: float = LOCAL_RUNTIME_TIMEOUT_SECONDS,
        poll_interval_seconds: float = LOCAL_RUNTIME_POLL_INTERVAL_SECONDS,
        popen: Optional[Callable] = None,
        clock: Callable[[], float] = time.monotonic,
        reap: Callable = _reap,
        core_source_head: Optional[str] = None,
    ):
        self._runtime_dir = Path(runtime_dir) if runtime_dir is not None else default_runtime_dir()
        self._timeout_seconds = timeout_seconds
        self._poll_interval_seconds = poll_interval_seconds
        self._popen = popen or subprocess.Popen
        self._clock = clock
        self._reap = reap
        self._core_source_head = core_source_head
        self._runtime_lock = threading.Lock()
        self._verified_runtime: Optional[VerifiedRuntime] = None

    def _runtime(self) -> VerifiedRuntime:
        with self._runtime_lock:
            expected_source_head = self._core_source_head
            if expected_source_head is None:
                expected_source_head = _packaged_core_source_head()
            cached = self._verified_runtime
            if cached is not None:
                manifest = self._runtime_dir / RUNTIME_MANIFEST
                try:
                    manifest_stat = manifest.stat()
                    executable_stat = cached.executable.stat()
                    fingerprint = (
                        manifest_stat.st_mtime_ns,
                        manifest_stat.st_ctime_ns,
                        manifest_stat.st_size,
                        executable_stat.st_mtime_ns,
                        executable_stat.st_ctime_ns,
                        executable_stat.st_size,
                    )
                except OSError:
                    fingerprint = None
                if (
                    fingerprint == cached.fingerprint
                    and (
                        expected_source_head is None
                        or cached.source_head == expected_source_head
                    )
                ):
                    return cached
            verified = verify_runtime(
                self._runtime_dir, expected_source_head=expected_source_head
            )
            self._verified_runtime = verified
            return verified

    def transcribe(
        self,
        source_path: Path,
        token: CancellationToken,
        event_callback: EventCallback,
        progress_callback: ProgressCallback,
    ) -> TranscriptionResult:
        token.raise_if_requested()
        runtime = self._runtime()
        progress_callback(None)
        event_callback("info", "Local", "Local runtime 시작")

        with tempfile.TemporaryDirectory(prefix="Sorigul_LocalRuntime_") as temp_root_value:
            temp_root = Path(temp_root_value).resolve()
            output_dir = temp_root / "output"
            output_dir.mkdir()
            request_path = temp_root / "request.json"
            request = {
                "protocol_version": PROTOCOL_VERSION,
                "action": "transcribe",
                "input_path": str(source_path),
                "output_dir": str(output_dir),
                "model": self.MODEL_NAME,
                "options": dict(self.TRANSCRIBE_OPTIONS),
            }
            request_path.write_text(
                json.dumps(request, ensure_ascii=False), encoding="utf-8"
            )

            with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
                try:
                    process = self._popen(
                        [str(runtime.executable), "--request", str(request_path)],
                        stdin=subprocess.DEVNULL,
                        stdout=stdout_file,
                        stderr=stderr_file,
                        creationflags=_CREATE_NO_WINDOW | _CREATE_NEW_PROCESS_GROUP,
                    )
                except OSError as exc:
                    raise _engine_error(
                        "LOCAL_RUNTIME_ERROR",
                        "Local Whisper 실행을 시작하지 못했습니다.",
                        str(exc),
                        fatal=False,
                    ) from exc
                deadline = self._clock() + self._timeout_seconds
                needs_reap = True
                try:
                    while True:
                        try:
                            returncode = process.wait(timeout=self._poll_interval_seconds)
                            needs_reap = False
                            break
                        except subprocess.TimeoutExpired:
                            pass
                        if token.is_cancel_requested or token.is_stop_requested:
                            needs_reap = False
                            self._reap(process)
                            token.raise_if_requested()
                        if self._clock() >= deadline:
                            needs_reap = False
                            self._reap(process)
                            raise _engine_error(
                                "LOCAL_RUNTIME_TIMEOUT",
                                "Local Whisper 전사 시간이 초과되었습니다.",
                                f"worker exceeded {self._timeout_seconds}s; {_stderr_tail(stderr_file)}",
                                fatal=False,
                            )
                finally:
                    if needs_reap:
                        self._reap(process)

                token.raise_if_requested()
                stdout = _stdout_text(stdout_file)
                stderr = _stderr_tail(stderr_file)
                if returncode != 0:
                    try:
                        response = self._parse_response(stdout)
                    except EngineError:
                        raise _engine_error(
                            "LOCAL_RUNTIME_ERROR",
                            "Local Whisper 실행에 실패했습니다.",
                            f"worker exit={returncode}; {stderr}",
                            fatal=False,
                        ) from None
                    if response["ok"]:
                        raise _engine_error(
                            "LOCAL_RUNTIME_ERROR",
                            "Local Whisper 실행에 실패했습니다.",
                            f"worker exit={returncode}; {stderr}",
                            fatal=False,
                        )
                else:
                    response = self._parse_response(stdout)
                if not response["ok"]:
                    error = response.get("error")
                    detail = error.get("message", "") if isinstance(error, dict) else ""
                    raise _engine_error(
                        "LOCAL_RUNTIME_ERROR",
                        "Local Whisper 실행에 실패했습니다.",
                        detail[:LOCAL_RUNTIME_STDERR_LIMIT_BYTES],
                        fatal=False,
                    )
                result = self._result_from_outputs(response, output_dir, source_path.stem)
                device = response.get("device")
                if device == "cuda":
                    event_callback("info", "Local", "CUDA 사용")
                elif device == "cpu":
                    event_callback("warning", "Local", "CUDA 초기화 실패 또는 미지원으로 CPU를 사용합니다.")
                token.raise_if_requested()
                return result

    @staticmethod
    def _parse_response(stdout: str) -> dict:
        try:
            response = json.loads(stdout)
        except (json.JSONDecodeError, TypeError) as exc:
            raise _engine_error(
                "LOCAL_RUNTIME_RESPONSE_INVALID",
                "Local Whisper 실행 결과 형식이 올바르지 않습니다.",
                str(exc),
                fatal=False,
            ) from exc
        if (
            not isinstance(response, dict)
            or type(response.get("protocol_version")) is not int
            or response.get("protocol_version") != PROTOCOL_VERSION
            or type(response.get("ok")) is not bool
            or response.get("status") not in {"DONE", "FAILED"}
        ):
            raise _engine_error(
                "LOCAL_RUNTIME_RESPONSE_INVALID",
                "Local Whisper 실행 결과 형식이 올바르지 않습니다.",
                "response schema or protocol mismatch",
                fatal=False,
            )
        if response["ok"]:
            valid = response["status"] == "DONE" and response.get("device") in {"cuda", "cpu"}
        else:
            error = response.get("error")
            valid = (
                response["status"] == "FAILED"
                and isinstance(error, dict)
                and type(error.get("code")) is str
                and type(error.get("message")) is str
            )
        if not valid:
            raise _engine_error(
                "LOCAL_RUNTIME_RESPONSE_INVALID",
                "Local Whisper 실행 결과 형식이 올바르지 않습니다.",
                "response status fields are inconsistent",
                fatal=False,
            )
        return response

    @staticmethod
    def _result_from_outputs(response: dict, output_dir: Path, stem: str) -> TranscriptionResult:
        outputs = response.get("outputs")
        if not isinstance(outputs, dict) or set(outputs) != {"txt", "json", "srt"}:
            raise _engine_error(
                "LOCAL_RUNTIME_RESPONSE_INVALID",
                "Local Whisper 결과 파일 정보가 올바르지 않습니다.",
                "outputs must contain txt/json/srt",
                fatal=False,
            )
        expected = {
            "txt": (output_dir / f"{stem}.txt").resolve(),
            "json": (output_dir / f"{stem}.json").resolve(),
            "srt": (output_dir / f"{stem}.srt").resolve(),
        }
        try:
            resolved = {
                key: Path(value).resolve()
                for key, value in outputs.items()
                if type(value) is str
            }
        except (OSError, RuntimeError) as exc:
            raise _engine_error(
                "LOCAL_RUNTIME_RESPONSE_INVALID",
                "Local Whisper 결과 파일 정보가 올바르지 않습니다.",
                str(exc),
                fatal=False,
            ) from exc
        if resolved != expected:
            raise _engine_error(
                "LOCAL_RUNTIME_RESPONSE_INVALID",
                "Local Whisper 결과 파일 정보가 올바르지 않습니다.",
                "worker output paths escaped the requested output directory",
                fatal=False,
            )
        paths = BundlePaths(**resolved)
        OutputBundleValidator().validate(paths)
        try:
            payload = json.loads(paths.json.read_text(encoding="utf-8"))
            return TranscriptionResult.from_engine_payload(payload)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise _engine_error(
                "LOCAL_RESULT_INVALID",
                "Local Whisper 결과 형식이 올바르지 않습니다.",
                str(exc),
                fatal=False,
            ) from exc
