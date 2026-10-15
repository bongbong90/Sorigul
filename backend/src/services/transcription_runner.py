import logging
import math
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from pathlib import Path
from typing import Callable, Dict, Optional

from src.domain.models import BundleStatus, FileStatus, JobEvent, JobModel, ScannedFile
from src.domain.transcription import (
    CancellationToken,
    CancelRequested,
    EngineError,
    ErrorCategory,
    StopRequested,
    TranscriptionEngine,
)
from src.engines.colab import (
    FFMPEG_PROCESS_CLEANUP_FAILED,
    ColabRecoveryCache,
    DirectColabEngine,
    DirectColabHttpClient,
    FFmpegAudioSplitter,
)
from src.engines.local_whisper import LocalWhisperEngine
from src.services.job_manager import JobManager
from src.services.colab_security import PairingRegistry, pairing_registry
from src.services.output_bundle import OutputBundleWriter
from src.services.scanner import FileScanner
from src.utils.paths import get_app_data_dir


logger = logging.getLogger(__name__)

IN_PROGRESS_STATES = frozenset(
    {FileStatus.PREPARING, FileStatus.TRANSCRIBING, FileStatus.SAVING, FileStatus.VERIFYING}
)

# Terminal Job event per terminal Job status; the event always matches the
# state the run actually persisted.
TERMINAL_JOB_EVENTS = {
    FileStatus.DONE: ("info", "Job 완료"),
    FileStatus.STOPPED: ("warning", "Job 중지됨"),
    FileStatus.CANCELLED: ("warning", "Job 취소됨"),
    FileStatus.FAILED: ("error", "Job 실패"),
}


class DefaultEngineResolver:
    def __init__(
        self,
        cache_root: Optional[Path] = None,
        registry: PairingRegistry = pairing_registry,
    ):
        self._local = LocalWhisperEngine()
        self._colab: Dict[str, DirectColabEngine] = {}
        self._lock = threading.Lock()
        self._cache_root = cache_root or (get_app_data_dir() / "cache" / "colab")
        self._registry = registry

    def __call__(self, job: JobModel) -> TranscriptionEngine:
        if job.engine == "local_whisper":
            return self._local
        if job.engine == "direct_colab":
            endpoint = str(job.engine_config.get("base_url", ""))
            if not endpoint:
                raise EngineError(
                    "COLAB_URL_MISSING",
                    ErrorCategory.CONFIGURATION,
                    "Colab 주소가 설정되지 않았습니다.",
                    fatal=True,
                )
            session = self._registry.lookup_verified_base_url(endpoint)
            if session is None:
                raise EngineError(
                    "COLAB_PAIRING_REQUIRED",
                    ErrorCategory.AUTHENTICATION,
                    "Colab에 다시 연결해 주세요.",
                    fatal=True,
                )
            cache_key = f"{endpoint}:{session.fingerprint}"
            with self._lock:
                if cache_key not in self._colab:
                    self._colab[cache_key] = DirectColabEngine(
                        client=DirectColabHttpClient(endpoint, session),
                        splitter=FFmpegAudioSplitter(),
                        cache=ColabRecoveryCache(self._cache_root),
                    )
                return self._colab[cache_key]
        raise EngineError(
            "ENGINE_UNSUPPORTED",
            ErrorCategory.CONFIGURATION,
            "지원하지 않는 전사 엔진입니다.",
            technical_detail=job.engine,
            fatal=True,
        )


class TranscriptionRunner:
    def __init__(
        self,
        job_manager: JobManager,
        engine_resolver: Callable[[JobModel], TranscriptionEngine],
        output_writer: Optional[OutputBundleWriter] = None,
        file_completed_callback: Optional[Callable[[str, str, str], None]] = None,
        job_finished_callback: Optional[Callable[[JobModel], None]] = None,
    ):
        self.job_manager = job_manager
        self.engine_resolver = engine_resolver
        self.output_writer = output_writer or OutputBundleWriter()
        self.file_completed_callback = file_completed_callback
        self.job_finished_callback = job_finished_callback

    def run(self, job_id: str, token: CancellationToken):
        job = self.job_manager.get_job(job_id)
        if job is None:
            return
        self._clear_eta(job_id)
        local_observations: list[tuple[float, float]] = []
        colab_observations: list[tuple[float, float]] = []
        observes_local_speed = job.engine == "local_whisper"
        observes_colab_speed = job.engine == "direct_colab"
        try:
            engine = self.engine_resolver(job)
        except EngineError as exc:
            self._finish_fatal(job_id, token, exc)
            return

        try:
            scanned = {item.id: item for item in FileScanner(job.folder).scan()}
        except OSError as exc:
            self._finish_fatal(
                job_id,
                token,
                EngineError(
                    "SOURCE_FOLDER_UNREADABLE",
                    ErrorCategory.INPUT,
                    "전사 폴더를 읽을 수 없습니다.",
                    technical_detail=str(exc),
                    fatal=True,
                ),
            )
            return
        self._event(job_id, "info", "Job", "전사 시작")
        fatal_error = False
        process_cleanup_failed = False

        for file_id, initial_status in list(job.files.items()):
            if initial_status != FileStatus.WAITING:
                continue
            try:
                token.raise_if_requested()
            except (StopRequested, CancelRequested):
                break

            item = scanned.get(file_id)
            if item is None:
                self._file_failed(
                    job_id,
                    file_id,
                    file_id,
                    EngineError(
                        "SOURCE_MISSING",
                        ErrorCategory.INPUT,
                        "원본 MP3 파일을 찾을 수 없습니다.",
                    ),
                )
                if observes_local_speed:
                    self._update_local_eta(job_id, local_observations, scanned)
                if observes_colab_speed:
                    self._update_colab_eta(job_id, colab_observations, scanned)
                continue

            if not job.force_retranscribe and item.completion_status == BundleStatus.DONE:
                self._set_file_state(job_id, file_id, FileStatus.DONE, item.filename)
                self._event(job_id, "info", "File", "정상 결과가 있어 전사를 건너뜁니다.", file_id, item.filename)
                if observes_local_speed:
                    self._update_local_eta(job_id, local_observations, scanned)
                if observes_colab_speed:
                    self._update_colab_eta(job_id, colab_observations, scanned)
                continue

            source_path = Path(item.source_path)
            try:
                self._set_file_state(job_id, file_id, FileStatus.PREPARING, item.filename)
                self._set_file_state(job_id, file_id, FileStatus.TRANSCRIBING, item.filename)
                transcribe_started = time.monotonic()

                def on_progress(progress: Optional[float]):
                    self._set_progress(job_id, progress)
                    if observes_colab_speed:
                        self._update_colab_eta(
                            job_id,
                            colab_observations,
                            scanned,
                            current_file_id=file_id,
                            current_progress=progress,
                        )

                # Engines that cannot be interrupted mid-call (OpenAI Whisper's
                # model.transcribe has no safe cancellation hook) return here
                # only once the call ends. A Stop/Cancel requested meanwhile
                # stays a *request* -- the Job keeps its active state -- and is
                # acknowledged here or, at the latest, at the pre-promotion
                # gate below, so the requested run never commits output. A
                # truly hung native/GPU call is recovered only at process
                # level (owned backend cleanup / app exit, enforced by the
                # desktop shell's kill-on-close Job Object).
                result = engine.transcribe(
                    source_path,
                    token,
                    lambda level, category, message: self._event(
                        job_id, level, category, message, file_id, item.filename
                    ),
                    on_progress,
                )
                transcribe_elapsed = time.monotonic() - transcribe_started
                token.raise_if_requested()
                self._set_file_state(job_id, file_id, FileStatus.SAVING, item.filename)

                def before_verify():
                    token.raise_if_requested()
                    self._set_file_state(job_id, file_id, FileStatus.VERIFYING, item.filename)

                def before_promotion():
                    # Last point a Stop/Cancel can prevent this commit. Past
                    # this, promotion runs to completion (or rollback).
                    token.raise_if_requested()

                self.output_writer.commit(
                    source_path,
                    result,
                    verification_callback=before_verify,
                    before_promotion=before_promotion,
                )
                # The bundle is committed on disk: record that truth first.
                # A Stop/Cancel that arrived during/after promotion ends the
                # Job after this file; it never relabels a committed file.
                self._set_file_state(job_id, file_id, FileStatus.DONE, item.filename)
                self._event(job_id, "info", "File", "파일 전사 완료", file_id, item.filename)
                request_pending = token.is_stop_requested or token.is_cancel_requested
                if not request_pending:
                    self._notify_file_completed(job_id, file_id, item.filename)
                if observes_local_speed:
                    duration = item.duration_seconds
                    if (
                        duration is not None
                        and math.isfinite(duration)
                        and duration > 0
                        and math.isfinite(transcribe_elapsed)
                        and transcribe_elapsed > 0
                    ):
                        local_observations.append((transcribe_elapsed, duration))
                    self._update_local_eta(job_id, local_observations, scanned)
                if observes_colab_speed:
                    duration = item.duration_seconds
                    if (
                        result.metadata.get("colab_recovery_cache_used") is not True
                        and duration is not None
                        and math.isfinite(duration)
                        and duration > 0
                        and math.isfinite(transcribe_elapsed)
                        and transcribe_elapsed > 0
                    ):
                        colab_observations.append((transcribe_elapsed, duration))
                    self._update_colab_eta(job_id, colab_observations, scanned)
                if request_pending:
                    break
            except StopRequested:
                self._set_file_state(job_id, file_id, FileStatus.STOPPED, item.filename)
                self._event(job_id, "warning", "Stop", "사용자가 전사를 중지함", file_id, item.filename)
                break
            except CancelRequested:
                self._acknowledge_cancel(job_id, file_id, item.filename)
                break
            except EngineError as exc:
                self._file_failed(job_id, file_id, item.filename, exc)
                if exc.code == FFMPEG_PROCESS_CLEANUP_FAILED:
                    process_cleanup_failed = True
                if exc.fatal:
                    fatal_error = True
                    break
                if observes_local_speed:
                    self._update_local_eta(job_id, local_observations, scanned)
                if observes_colab_speed:
                    self._update_colab_eta(job_id, colab_observations, scanned)
            except Exception as exc:
                logger.exception("Unexpected transcription error for %s", source_path)
                normalized = EngineError(
                    "TRANSCRIPTION_INTERNAL_ERROR",
                    ErrorCategory.RUNTIME,
                    "전사 처리 중 내부 오류가 발생했습니다.",
                    technical_detail=str(exc),
                )
                self._file_failed(job_id, file_id, item.filename, normalized)
                if observes_local_speed:
                    self._update_local_eta(job_id, local_observations, scanned)
                if observes_colab_speed:
                    self._update_colab_eta(job_id, colab_observations, scanned)

        self._finalize(job_id, token, fatal_error, process_cleanup_failed)

    def _clear_eta(self, job_id: str):
        self.job_manager.mutate_job(job_id, lambda job: setattr(job, "eta_seconds", None))

    def _update_local_eta(
        self,
        job_id: str,
        observations: list[tuple[float, float]],
        scanned: Dict[str, ScannedFile],
    ):
        def mutation(job: JobModel):
            if job.engine != "local_whisper" or not observations:
                job.eta_seconds = None
                return

            observed_processing_seconds = sum(processing for processing, _ in observations)
            observed_audio_seconds = sum(duration for _, duration in observations)
            if (
                not math.isfinite(observed_processing_seconds)
                or observed_processing_seconds <= 0
                or not math.isfinite(observed_audio_seconds)
                or observed_audio_seconds <= 0
            ):
                job.eta_seconds = None
                return

            remaining_audio_seconds = 0.0
            for file_id, state in job.files.items():
                if state != FileStatus.WAITING:
                    continue
                item = scanned.get(file_id)
                duration = item.duration_seconds if item is not None else None
                if duration is None or not math.isfinite(duration) or duration <= 0:
                    job.eta_seconds = None
                    return
                remaining_audio_seconds += duration

            if remaining_audio_seconds <= 0:
                job.eta_seconds = None
                return

            eta_seconds = (
                observed_processing_seconds
                / observed_audio_seconds
                * remaining_audio_seconds
            )
            job.eta_seconds = eta_seconds if math.isfinite(eta_seconds) and eta_seconds > 0 else None

        self.job_manager.mutate_job(job_id, mutation)

    def _update_colab_eta(
        self,
        job_id: str,
        observations: list[tuple[float, float]],
        scanned: Dict[str, ScannedFile],
        current_file_id: Optional[str] = None,
        current_progress: Optional[float] = None,
    ):
        def mutation(job: JobModel):
            if job.engine != "direct_colab" or not observations:
                job.eta_seconds = None
                return

            observed_processing_seconds = sum(processing for processing, _ in observations)
            observed_audio_seconds = sum(duration for _, duration in observations)
            if (
                not math.isfinite(observed_processing_seconds)
                or observed_processing_seconds <= 0
                or not math.isfinite(observed_audio_seconds)
                or observed_audio_seconds <= 0
            ):
                job.eta_seconds = None
                return

            remaining_audio_seconds = 0.0
            if current_file_id is not None:
                if (
                    current_progress is None
                    or not math.isfinite(current_progress)
                    or current_progress < 0
                    or current_progress > 1
                ):
                    job.eta_seconds = None
                    return
                current_item = scanned.get(current_file_id)
                current_duration = current_item.duration_seconds if current_item is not None else None
                if (
                    current_duration is None
                    or not math.isfinite(current_duration)
                    or current_duration <= 0
                ):
                    job.eta_seconds = None
                    return
                remaining_audio_seconds += current_duration * (1 - current_progress)

            for file_id, state in job.files.items():
                if state != FileStatus.WAITING or file_id == current_file_id:
                    continue
                item = scanned.get(file_id)
                duration = item.duration_seconds if item is not None else None
                if duration is None or not math.isfinite(duration) or duration <= 0:
                    job.eta_seconds = None
                    return
                remaining_audio_seconds += duration

            if remaining_audio_seconds <= 0:
                job.eta_seconds = None
                return

            eta_seconds = (
                observed_processing_seconds
                / observed_audio_seconds
                * remaining_audio_seconds
            )
            job.eta_seconds = eta_seconds if math.isfinite(eta_seconds) and eta_seconds > 0 else None

        self.job_manager.mutate_job(job_id, mutation)

    def _notify_file_completed(self, job_id: str, file_id: str, filename: str):
        # A completion side effect (notification, Drive scheduling) must
        # never turn an already-committed DONE file into a failure.
        if self.file_completed_callback is None:
            return
        try:
            self.file_completed_callback(job_id, file_id, filename)
        except Exception:
            logger.exception("file_completed callback failed for %s/%s", job_id, file_id)

    def _set_file_state(self, job_id: str, file_id: str, state: FileStatus, filename: str):
        def mutation(job: JobModel):
            if state in IN_PROGRESS_STATES and job.status == FileStatus.CANCEL_REQUESTED:
                # A cancel was already acknowledged; keep reporting it until
                # this runner acknowledges the cancel itself.
                job.files[file_id] = FileStatus.CANCEL_REQUESTED
                job.current_file = filename
                return
            job.status = state
            job.files[file_id] = state
            job.current_file = filename if state not in {FileStatus.DONE, FileStatus.FAILED} else None
            if state in {FileStatus.DONE, FileStatus.FAILED}:
                job.current_progress = None
            self._update_counts(job)

        self.job_manager.mutate_job(job_id, mutation)

    def _set_progress(self, job_id: str, progress: Optional[float]):
        def mutation(job: JobModel):
            job.current_progress = None if progress is None else round(progress * 100, 2)

        self.job_manager.mutate_job(job_id, mutation)

    def _event(
        self,
        job_id: str,
        level: str,
        category: str,
        message: str,
        file_id: Optional[str] = None,
        filename: Optional[str] = None,
    ):
        def mutation(job: JobModel):
            job.events.append(
                JobEvent(
                    level=level,
                    category=category,
                    message=message,
                    file_id=file_id,
                    filename=filename,
                )
            )

        self.job_manager.mutate_job(job_id, mutation)

    def _file_failed(
        self,
        job_id: str,
        file_id: str,
        filename: str,
        error: EngineError,
    ):
        if error.technical_detail:
            logger.error(
                "Engine error %s (%s): %s",
                error.code,
                error.category.value,
                error.technical_detail,
            )

        def mutation(job: JobModel):
            job.status = FileStatus.FAILED
            job.files[file_id] = FileStatus.FAILED
            job.current_file = None
            job.current_progress = None
            job.error = error.user_message
            job.events.append(
                JobEvent(
                    level="error",
                    category=error.category.value,
                    message=error.user_message,
                    file_id=file_id,
                    filename=filename,
                )
            )
            self._update_counts(job)

        self.job_manager.mutate_job(job_id, mutation)

    @staticmethod
    def _append_terminal_event(job: JobModel):
        level, message = TERMINAL_JOB_EVENTS.get(job.status, ("info", "Job 종료"))
        last = job.events[-1] if job.events else None
        if last is not None and last.category == "Job" and last.message == message:
            return
        job.events.append(JobEvent(level=level, category="Job", message=message))

    def _finish_fatal(self, job_id: str, token: CancellationToken, error: EngineError):
        if error.technical_detail:
            logger.error(
                "Fatal engine error %s (%s): %s",
                error.code,
                error.category.value,
                error.technical_detail,
            )

        def mutation(job: JobModel):
            job.status = FileStatus.FAILED
            job.batch_completed = False
            job.eta_seconds = None
            first_waiting = next(
                (file_id for file_id, state in job.files.items() if state == FileStatus.WAITING),
                None,
            )
            if first_waiting is not None:
                job.files[first_waiting] = FileStatus.FAILED
            job.error = error.user_message
            job.events.append(
                JobEvent(level="error", category=error.category.value, message=error.user_message)
            )
            self._update_counts(job)
            self._append_terminal_event(job)

        # Finished only once the terminal state is persisted (same lock hold).
        self.job_manager.mutate_job(job_id, mutation, after_persist=token.mark_finished)

    def _acknowledge_cancel(self, job_id: str, file_id: str, filename: str):
        def mutation(job: JobModel):
            job.files[file_id] = FileStatus.CANCELLED
            for pending_id, state in job.files.items():
                if state in {FileStatus.WAITING, FileStatus.CANCEL_REQUESTED}:
                    job.files[pending_id] = FileStatus.CANCELLED
            job.status = FileStatus.CANCELLED
            job.current_file = None
            job.current_progress = None
            job.eta_seconds = None
            job.events.append(
                JobEvent(
                    level="warning",
                    category="Cancel",
                    message="작업 취소됨",
                    file_id=file_id,
                    filename=filename,
                )
            )
            self._update_counts(job)

        self.job_manager.mutate_job(job_id, mutation)

    def _finalize(
        self,
        job_id: str,
        token: CancellationToken,
        fatal_error: bool,
        process_cleanup_failed: bool = False,
    ):
        def mutation(job: JobModel):
            self._update_counts(job)
            if process_cleanup_failed:
                # A child process may still be alive: never report the run
                # as cleanly STOPPED/CANCELLED, even if one was requested.
                job.status = FileStatus.FAILED
                job.batch_completed = False
            elif token.is_cancel_requested or job.status == FileStatus.CANCEL_REQUESTED:
                for file_id, state in job.files.items():
                    if state in {FileStatus.WAITING, FileStatus.CANCEL_REQUESTED}:
                        job.files[file_id] = FileStatus.CANCELLED
                job.status = FileStatus.CANCELLED
                job.batch_completed = False
            elif token.is_stop_requested or job.status == FileStatus.STOPPED:
                job.status = FileStatus.STOPPED
                job.batch_completed = False
            elif fatal_error:
                job.status = FileStatus.FAILED
                job.batch_completed = False
            elif any(state == FileStatus.FAILED for state in job.files.values()):
                job.status = FileStatus.FAILED
                job.batch_completed = True
            elif all(state == FileStatus.DONE for state in job.files.values()):
                job.status = FileStatus.DONE
                job.batch_completed = True
            job.current_file = None
            job.current_progress = None
            job.eta_seconds = None
            self._update_counts(job)
            self._append_terminal_event(job)

        # mark_finished runs only after the terminal state is persisted, and
        # before the JobManager lock is released: from then on no new
        # Stop/Cancel can be acknowledged by this run. If persisting fails,
        # the token stays unfinished.
        self.job_manager.mutate_job(job_id, mutation, after_persist=token.mark_finished)
        finished = self.job_manager.get_job(job_id)
        if finished is not None and self.job_finished_callback is not None:
            self.job_finished_callback(finished)

    @staticmethod
    def _update_counts(job: JobModel):
        job.done_files = sum(state == FileStatus.DONE for state in job.files.values())
        job.failed_files = sum(state == FileStatus.FAILED for state in job.files.values())


class BackgroundExecutionService:
    """Owns the running execution (token + future) per Job.

    Lock order is always service lock -> JobManager lock; the runner itself
    only ever takes the JobManager lock. A Stop/Cancel is *acknowledged*
    only if it reached a run that has not yet persisted its terminal state
    (the runner marks the token finished inside that same mutation), so an
    acknowledgement always means "this run will observe the request".
    """

    def __init__(
        self,
        runner: TranscriptionRunner,
        max_workers: int = 2,
    ):
        self.runner = runner
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="sorigul")
        self._tokens: Dict[str, CancellationToken] = {}
        self._futures: Dict[str, Future] = {}
        self._lock = threading.Lock()

    QUIESCENCE_TIMEOUT_SECONDS = 2.0

    def wait_for_quiescence(self, job_id: str, timeout: Optional[float] = None) -> bool:
        """Wait for a previously registered runner to truly return."""
        with self._lock:
            previous = self._futures.get(job_id)
        if previous is None or previous.done():
            return True
        try:
            previous.result(
                timeout=self.QUIESCENCE_TIMEOUT_SECONDS if timeout is None else timeout
            )
        except FutureTimeoutError:
            return False
        except Exception:
            # An ended runner is quiescent even if it ended exceptionally.
            return True
        return True

    def start(self, job_id: str) -> bool:
        if not self.wait_for_quiescence(job_id):
            return False
        with self._lock:
            job = self.runner.job_manager.get_job(job_id)
            if job is None or job.status != FileStatus.WAITING:
                return False
            existing = self._futures.get(job_id)
            if existing is not None and not existing.done():
                return False
            token = CancellationToken()
            self._tokens[job_id] = token
            future = self._executor.submit(self.runner.run, job_id, token)
            self._futures[job_id] = future
        future.add_done_callback(lambda done: self._cleanup(job_id, done))
        return True

    def is_active(self, job_id: str) -> bool:
        """True while a run for this Job has not yet persisted its terminal state."""
        with self._lock:
            token = self._tokens.get(job_id)
            return token is not None and not token.is_finished

    def request_stop(
        self,
        job_id: str,
        on_accepted: Optional[Callable[[JobModel], None]] = None,
    ) -> bool:
        return self._request(job_id, CancellationToken.request_stop, on_accepted)

    def request_cancel(
        self,
        job_id: str,
        on_accepted: Optional[Callable[[JobModel], None]] = None,
    ) -> bool:
        return self._request(job_id, CancellationToken.request_cancel, on_accepted)

    def _request(
        self,
        job_id: str,
        signal: Callable[[CancellationToken], None],
        on_accepted: Optional[Callable[[JobModel], None]],
    ) -> bool:
        with self._lock:
            token = self._tokens.get(job_id)
            if token is None or token.is_finished:
                return False
            eligible = False
            accepted = False

            def mutation(job: JobModel):
                nonlocal eligible
                # Checked under the JobManager lock, the same lock the
                # runner holds while persisting its terminal state and
                # marking the token finished.
                if token.is_finished:
                    return
                eligible = True
                if on_accepted is not None:
                    on_accepted(job)

            def signal_after_persist():
                # Runs only once the request's Job state/event is persisted,
                # still under the JobManager lock. If persisting fails the
                # token is left untouched and the request is not acknowledged.
                nonlocal accepted
                if eligible:
                    signal(token)
                    accepted = True

            self.runner.job_manager.mutate_job(
                job_id, mutation, after_persist=signal_after_persist
            )
            return accepted

    def run_if_not_started(
        self,
        job_id: str,
        mutation: Callable[[JobModel], None],
    ) -> tuple[bool, Optional[JobModel]]:
        """Applies ``mutation`` only if no run is active for this Job, holding
        the start lock so ``start`` cannot race it. Returns (applied, job)."""
        with self._lock:
            token = self._tokens.get(job_id)
            if token is not None and not token.is_finished:
                return False, None
            return True, self.runner.job_manager.mutate_job(job_id, mutation)

    def _cleanup(self, job_id: str, future: Future):
        if not future.cancelled() and future.exception() is not None:
            logger.error(
                "Transcription run for job %s ended with an unhandled error",
                job_id,
                exc_info=future.exception(),
            )
        with self._lock:
            if self._futures.get(job_id) is future:
                self._tokens.pop(job_id, None)
                self._futures.pop(job_id, None)
