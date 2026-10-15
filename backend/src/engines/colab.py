import hashlib
import json
import math
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Protocol

from src.domain.transcription import (
    CancellationToken,
    EngineError,
    ErrorCategory,
    EventCallback,
    ProgressCallback,
    TranscriptionResult,
    TranscriptionSegment,
)


CHUNK_SECONDS = 300
FATAL_TRANSCRIBE_HTTP_STATUSES = frozenset({401, 403, 404, 405})
# Hard ceiling for a single ffmpeg invocation while preparing Colab audio.
FFMPEG_SPLIT_TIMEOUT_SECONDS = 300
FFMPEG_POLL_INTERVAL_SECONDS = 0.2
# How long to wait for an ffmpeg child to be reaped after terminate/kill.
FFMPEG_REAP_TIMEOUT_SECONDS = 10
FFMPEG_PROCESS_CLEANUP_FAILED = "FFMPEG_PROCESS_CLEANUP_FAILED"
# Only the tail of ffmpeg's stderr is kept for diagnosis.
FFMPEG_STDERR_LIMIT_BYTES = 16 * 1024
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _audio_split_timeout_error(detail: str) -> EngineError:
    # Not fatal: a pathological source fails its own file and the batch
    # moves on; the split itself is never retried automatically.
    return EngineError(
        "AUDIO_SPLIT_TIMEOUT",
        ErrorCategory.RUNTIME,
        "Colab 전사를 위한 오디오 준비 시간이 초과되었습니다.",
        technical_detail=detail,
    )


def _process_cleanup_failed_error(detail: str) -> EngineError:
    # Fatal: a child that may still be running must stop the batch, and it
    # takes precedence over the timeout or Stop/Cancel that triggered cleanup.
    return EngineError(
        FFMPEG_PROCESS_CLEANUP_FAILED,
        ErrorCategory.RUNTIME,
        "Colab 오디오 준비 프로세스를 안전하게 종료하지 못했습니다.",
        technical_detail=detail,
        fatal=True,
    )


def _reap(process) -> None:
    """Terminates this exact child (never anything found by name) and waits
    for it, escalating to kill if terminate is not enough. Returns only once
    the child was waited on; otherwise raises FFMPEG_PROCESS_CLEANUP_FAILED --
    it never falls through silently."""
    steps = []
    for name, stop in (("terminate", process.terminate), ("kill", process.kill)):
        try:
            stop()
            steps.append(f"{name}=ok")
        except OSError as exc:
            steps.append(f"{name}=error:{exc}")
        try:
            process.wait(timeout=FFMPEG_REAP_TIMEOUT_SECONDS)
            return
        except subprocess.TimeoutExpired:
            steps.append(f"wait-after-{name}=timeout({FFMPEG_REAP_TIMEOUT_SECONDS}s)")
    pid = getattr(process, "pid", None)
    raise _process_cleanup_failed_error(f"ffmpeg pid={pid} not reaped: {'; '.join(steps)}")


def run_ffmpeg(
    command: List[str],
    token: Optional[CancellationToken],
    *,
    timeout_seconds: float = FFMPEG_SPLIT_TIMEOUT_SECONDS,
    poll_interval_seconds: float = FFMPEG_POLL_INTERVAL_SECONDS,
    popen=None,
    clock=time.monotonic,
) -> int:
    """Runs one ffmpeg invocation with a hard deadline, honouring Stop/Cancel
    while it runs. On timeout or Stop/Cancel the exact child is terminated
    and reaped before AUDIO_SPLIT_TIMEOUT / StopRequested / CancelRequested
    propagates; if it cannot be reaped, FFMPEG_PROCESS_CLEANUP_FAILED is
    raised instead. Returns the exit code; raises AUDIO_SPLIT_FAILED on nonzero.
    """
    popen = popen or subprocess.Popen
    with tempfile.TemporaryFile() as stderr_file:
        process = popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=stderr_file,
            creationflags=_CREATE_NO_WINDOW,
        )
        deadline = clock() + timeout_seconds
        # False once the child exited on its own or a reap was attempted, so
        # the safety net below never reaps twice or masks a reap failure.
        needs_reap = True
        try:
            while True:
                try:
                    returncode = process.wait(timeout=poll_interval_seconds)
                    needs_reap = False
                    break
                except subprocess.TimeoutExpired:
                    pass
                if token is not None and (token.is_cancel_requested or token.is_stop_requested):
                    needs_reap = False
                    _reap(process)  # a reap failure wins over Stop/Cancel
                    token.raise_if_requested()
                if clock() >= deadline:
                    needs_reap = False
                    _reap(process)  # a reap failure wins over the timeout
                    raise _audio_split_timeout_error(
                        f"ffmpeg exceeded {timeout_seconds}s: {_stderr_tail(stderr_file)}"
                    )
        finally:
            if needs_reap:
                _reap(process)
        if returncode != 0:
            raise EngineError(
                "AUDIO_SPLIT_FAILED",
                ErrorCategory.INPUT,
                "Colab 전사를 위한 오디오 준비에 실패했습니다.",
                technical_detail=_stderr_tail(stderr_file),
            )
        return returncode


def _stderr_tail(stderr_file) -> str:
    try:
        stderr_file.flush()
        size = stderr_file.seek(0, 2)
        stderr_file.seek(max(0, size - FFMPEG_STDERR_LIMIT_BYTES))
        return stderr_file.read().decode("utf-8", errors="replace")
    except (OSError, ValueError):
        return ""


@dataclass(frozen=True)
class AudioChunk:
    index: int
    path: Path
    start_seconds: float
    duration_seconds: float


class AudioSplitter(Protocol):
    def split(
        self,
        source_path: Path,
        chunk_seconds: int,
        token: Optional[CancellationToken] = None,
    ) -> List[AudioChunk]:
        ...

    def cleanup(self):
        ...


class FFmpegAudioSplitter:
    def __init__(
        self,
        timeout_seconds: float = FFMPEG_SPLIT_TIMEOUT_SECONDS,
        popen=None,
        clock=time.monotonic,
        poll_interval_seconds: float = FFMPEG_POLL_INTERVAL_SECONDS,
    ):
        self._temp_dir: Optional[Path] = None
        self.timeout_seconds = timeout_seconds
        self._popen = popen
        self._clock = clock
        self._poll_interval_seconds = poll_interval_seconds

    def _run(self, command: List[str], token: Optional[CancellationToken]):
        # Both split paths share this one bounded, token-aware policy.
        run_ffmpeg(
            command,
            token,
            timeout_seconds=self.timeout_seconds,
            poll_interval_seconds=self._poll_interval_seconds,
            popen=self._popen,
            clock=self._clock,
        )

    def split(
        self,
        source_path: Path,
        chunk_seconds: int,
        token: Optional[CancellationToken] = None,
    ) -> List[AudioChunk]:
        from src.utils.ffmpeg_runtime import resolve_ffmpeg_path
        ffmpeg = resolve_ffmpeg_path()
        if ffmpeg is None:
            raise EngineError(
                "FFMPEG_UNAVAILABLE",
                ErrorCategory.RUNTIME,
                "Colab 전사에 필요한 ffmpeg를 찾을 수 없습니다.",
                fatal=True,
            )
        from src.services.audio_metadata import AudioMetadataService
        duration = AudioMetadataService().duration_seconds(source_path)

        self._temp_dir = Path(tempfile.mkdtemp(prefix="sorigul-colab-"))
        if duration is not None:
            return self._split_with_duration(source_path, chunk_seconds, ffmpeg, duration, token)
        else:
            return self._split_fallback(source_path, chunk_seconds, ffmpeg, token)

    def _split_with_duration(
        self,
        source_path: Path,
        chunk_seconds: int,
        ffmpeg: Path,
        duration: float,
        token: Optional[CancellationToken] = None,
    ) -> List[AudioChunk]:
        chunks = []
        try:
            total = max(1, math.ceil(duration / chunk_seconds))
            for index in range(total):
                if token is not None:
                    token.raise_if_requested()
                start = index * chunk_seconds
                chunk_duration = min(chunk_seconds, max(0.0, duration - start))
                if chunk_duration < 1.0:
                    continue
                path = self._temp_dir / f"chunk-{index:05d}.mp3"
                command = [
                    str(ffmpeg),
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-ss",
                    str(start),
                    "-t",
                    str(chunk_duration),
                    "-i",
                    str(source_path),
                    "-vn",
                    "-codec:a",
                    "libmp3lame",
                    str(path),
                ]
                self._run(command, token)
                if path.stat().st_size < 2048:
                    path.unlink(missing_ok=True)
                    continue
                chunks.append(AudioChunk(index, path, float(start), chunk_duration))
            if not chunks:
                raise EngineError(
                    "AUDIO_EMPTY",
                    ErrorCategory.INPUT,
                    "전사할 수 있는 오디오 구간이 없습니다.",
                )
            return chunks
        except Exception:
            self.cleanup()
            raise

    def _split_fallback(
        self,
        source_path: Path,
        chunk_seconds: int,
        ffmpeg: Path,
        token: Optional[CancellationToken] = None,
    ) -> List[AudioChunk]:
        chunks = []
        try:
            pattern = str(self._temp_dir / "chunk-%05d.mp3")
            command = [
                str(ffmpeg),
                "-hide_banner",
                "-loglevel", "error",
                "-y",
                "-i", str(source_path),
                "-vn",
                "-codec:a", "libmp3lame",
                "-f", "segment",
                "-segment_time", str(chunk_seconds),
                "-reset_timestamps", "1",
                pattern,
            ]
            self._run(command, token)

            for path in sorted(self._temp_dir.glob("chunk-*.mp3")):
                if path.stat().st_size < 2048:
                    path.unlink(missing_ok=True)
                    continue

                stem = path.stem
                try:
                    index = int(stem.split("-")[-1])
                except ValueError:
                    continue

                start = float(index * chunk_seconds)
                chunks.append(AudioChunk(index, path, start, float(chunk_seconds)))

            if not chunks:
                raise EngineError(
                    "AUDIO_EMPTY",
                    ErrorCategory.INPUT,
                    "전사할 수 있는 오디오 구간이 없습니다.",
                )
            return chunks
        except Exception:
            self.cleanup()
            raise

    def cleanup(self):
        if self._temp_dir is not None:
            shutil.rmtree(self._temp_dir, ignore_errors=True)
            self._temp_dir = None


class ColabClient(Protocol):
    signature: str

    def check_health(self):
        ...

    def transcribe(self, chunk_path: Path) -> TranscriptionResult:
        ...


class DirectColabHttpClient:
    def __init__(self, base_url: str, timeout_seconds: int = 600):
        from src.services.colab_url import normalize_colab_base_url, ColabUrlError
        try:
            normalized = normalize_colab_base_url(base_url)
        except ColabUrlError:
            raise EngineError(
                "COLAB_URL_INVALID",
                ErrorCategory.CONFIGURATION,
                "Colab 주소가 올바르지 않습니다.",
                fatal=True,
            )
        self.base_url = normalized
        self.timeout_seconds = timeout_seconds
        self.signature = f"direct-colab:{self.base_url}:v1"

    def check_health(self):
        request = urllib.request.Request(f"{self.base_url}/health", method="GET")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                if not 200 <= response.status < 300:
                    raise OSError(f"HTTP {response.status}")
        except Exception as exc:
            raise EngineError(
                "COLAB_UNAVAILABLE",
                ErrorCategory.NETWORK,
                "Colab 연결을 확인할 수 없습니다.",
                technical_detail=str(exc),
                retryable=False,
                fatal=True,
            ) from exc

    def transcribe(self, chunk_path: Path) -> TranscriptionResult:
        boundary = f"----Sorigul{uuid.uuid4().hex}"
        filename = chunk_path.name.encode("utf-8").decode("latin-1")
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            "Content-Type: audio/mpeg\r\n\r\n"
        ).encode("latin-1") + chunk_path.read_bytes() + f"\r\n--{boundary}--\r\n".encode("ascii")
        request = urllib.request.Request(
            f"{self.base_url}/transcribe",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            retryable = exc.code in {408, 429} or 500 <= exc.code <= 599
            category = ErrorCategory.AUTHENTICATION if exc.code in {401, 403} else ErrorCategory.NETWORK
            raise EngineError(
                f"COLAB_HTTP_{exc.code}",
                category,
                "Colab 전사 요청에 실패했습니다.",
                technical_detail=f"HTTP {exc.code}",
                retryable=retryable,
                fatal=exc.code in FATAL_TRANSCRIBE_HTTP_STATUSES,
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise EngineError(
                "COLAB_NETWORK_ERROR",
                ErrorCategory.NETWORK,
                "Colab 네트워크 요청에 실패했습니다.",
                technical_detail=str(exc),
                retryable=True,
            ) from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise EngineError(
                "COLAB_RESPONSE_INVALID",
                ErrorCategory.OUTPUT,
                "Colab 응답 형식이 올바르지 않습니다.",
                technical_detail=str(exc),
            ) from exc
        try:
            return TranscriptionResult.from_engine_payload(payload)
        except (TypeError, ValueError) as exc:
            raise EngineError(
                "COLAB_RESPONSE_INVALID",
                ErrorCategory.OUTPUT,
                "Colab 응답 형식이 올바르지 않습니다.",
                technical_detail=str(exc),
            ) from exc


class ColabRecoveryCache:
    def __init__(self, root: Path):
        self.root = root

    @staticmethod
    def source_fingerprint(source_path: Path, engine_signature: str) -> dict:
        stat = source_path.stat()
        return {
            "source_path": str(source_path.resolve()),
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "chunk_seconds": CHUNK_SECONDS,
            "engine_signature": engine_signature,
        }

    def _file_dir(self, source_path: Path) -> Path:
        identity = hashlib.sha256(str(source_path.resolve()).encode("utf-8")).hexdigest()
        return self.root / identity

    def load(self, source_path: Path, engine_signature: str) -> dict[int, TranscriptionResult]:
        file_dir = self._file_dir(source_path)
        manifest_path = file_dir / "manifest.json"
        expected = self.source_fingerprint(source_path, engine_signature)
        if not manifest_path.exists():
            return {}
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest.get("fingerprint") != expected:
                self.clear(source_path)
                return {}
            results = {}
            for index_text, payload in manifest.get("completed", {}).items():
                results[int(index_text)] = TranscriptionResult.from_engine_payload(payload)
            return results
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            self.clear(source_path)
            return {}

    def save(
        self,
        source_path: Path,
        engine_signature: str,
        completed: dict[int, TranscriptionResult],
    ):
        file_dir = self._file_dir(source_path)
        file_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = file_dir / "manifest.json"
        temp_path = file_dir / "manifest.json.tmp"
        payload = {
            "fingerprint": self.source_fingerprint(source_path, engine_signature),
            "completed": {
                str(index): result.output_payload()
                for index, result in sorted(completed.items())
            },
        }
        temp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp_path.replace(manifest_path)

    def clear(self, source_path: Path):
        shutil.rmtree(self._file_dir(source_path), ignore_errors=True)


class DirectColabEngine:
    def __init__(
        self,
        client: ColabClient,
        splitter: AudioSplitter,
        cache: ColabRecoveryCache,
        retry_delay_seconds: float = 1.0,
    ):
        self.client = client
        self.splitter = splitter
        self.cache = cache
        self.retry_delay_seconds = retry_delay_seconds
        self._health_checked = False
        self._health_lock = threading.Lock()
        self._transcribe_lock = threading.Lock()

    def _ensure_health(self, event_callback: EventCallback):
        if self._health_checked:
            return
        with self._health_lock:
            if not self._health_checked:
                event_callback("info", "Colab", "연결 중")
                self.client.check_health()
                self._health_checked = True
                event_callback("info", "Colab", "연결됨")

    def transcribe(
        self,
        source_path: Path,
        token: CancellationToken,
        event_callback: EventCallback,
        progress_callback: ProgressCallback,
    ) -> TranscriptionResult:
        with self._transcribe_lock:
            return self._transcribe_serial(source_path, token, event_callback, progress_callback)

    def _transcribe_serial(
        self,
        source_path: Path,
        token: CancellationToken,
        event_callback: EventCallback,
        progress_callback: ProgressCallback,
    ) -> TranscriptionResult:
        token.raise_if_requested()
        completed = {}
        chunks: List[AudioChunk] = []
        try:
            self._ensure_health(event_callback)
            token.raise_if_requested()
            completed = self.cache.load(source_path, self.client.signature)
            chunks = self.splitter.split(source_path, CHUNK_SECONDS, token)
            valid_indices = {chunk.index for chunk in chunks}
            completed = {index: result for index, result in completed.items() if index in valid_indices}
            recovery_cache_used = bool(completed)
            for position, chunk in enumerate(chunks):
                token.raise_if_requested()
                if chunk.index not in completed:
                    completed[chunk.index] = self._transcribe_with_retry(
                        chunk.path,
                        token,
                        event_callback,
                    )
                    self.cache.save(source_path, self.client.signature, completed)
                progress_callback((position + 1) / len(chunks))
            token.raise_if_requested()
            result = self._merge(chunks, completed)
            result.metadata["colab_recovery_cache_used"] = recovery_cache_used
            self.cache.clear(source_path)
            return result
        except EngineError as exc:
            # A child that could not be reaped must never be reported as a
            # clean Stop/Cancel.
            if exc.code != FFMPEG_PROCESS_CLEANUP_FAILED:
                token.raise_if_requested()
            if not exc.retryable:
                self.cache.clear(source_path)
            raise
        except Exception:
            self.cache.clear(source_path)
            raise
        finally:
            if token.is_stop_requested or token.is_cancel_requested:
                self.cache.clear(source_path)
            self.splitter.cleanup()

    def _transcribe_with_retry(
        self,
        chunk_path: Path,
        token: CancellationToken,
        event_callback: EventCallback,
    ) -> TranscriptionResult:
        for attempt in range(2):
            token.raise_if_requested()
            try:
                return self.client.transcribe(chunk_path)
            except EngineError as exc:
                token.raise_if_requested()
                if not exc.retryable or attempt == 1:
                    raise
                event_callback("warning", "Colab", "일시적인 오류로 다시 시도합니다.")
                if self.retry_delay_seconds:
                    time.sleep(self.retry_delay_seconds)
        raise AssertionError("unreachable")

    @staticmethod
    def _merge(
        chunks: List[AudioChunk],
        completed: dict[int, TranscriptionResult],
    ) -> TranscriptionResult:
        text_parts = []
        merged_segments = []
        language = None
        for chunk in sorted(chunks, key=lambda item: item.index):
            result = completed[chunk.index]
            if result.text:
                text_parts.append(result.text)
            language = language or result.language
            for segment in result.segments:
                merged_segments.append(
                    TranscriptionSegment(
                        start=segment.start + chunk.start_seconds,
                        end=segment.end + chunk.start_seconds,
                        text=segment.text,
                        metadata=segment.metadata,
                    )
                )
        merged_segments.sort(key=lambda segment: (segment.start, segment.end))
        return TranscriptionResult(
            text="\n".join(text_parts),
            segments=merged_segments,
            language=language,
        )
