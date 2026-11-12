import logging
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Dict, Optional

from src.domain.models import BundleStatus, FileStatus, JobEvent, JobModel
from src.domain.transcription import (
    CancellationToken,
    CancelRequested,
    EngineError,
    ErrorCategory,
    StopRequested,
    TranscriptionEngine,
)
from src.engines.colab import (
    ColabRecoveryCache,
    DirectColabEngine,
    DirectColabHttpClient,
    FFmpegAudioSplitter,
)
from src.engines.local_whisper import LocalWhisperEngine
from src.services.job_manager import JobManager
from src.services.output_bundle import OutputBundleWriter
from src.services.scanner import FileScanner
from src.utils.paths import get_app_data_dir


logger = logging.getLogger(__name__)


class DefaultEngineResolver:
    def __init__(self, cache_root: Optional[Path] = None):
        self._local = LocalWhisperEngine()
        self._colab: Dict[str, DirectColabEngine] = {}
        self._lock = threading.Lock()
        self._cache_root = cache_root or (get_app_data_dir() / "cache" / "colab")

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
            with self._lock:
                if endpoint not in self._colab:
                    self._colab[endpoint] = DirectColabEngine(
                        client=DirectColabHttpClient(endpoint),
                        splitter=FFmpegAudioSplitter(),
                        cache=ColabRecoveryCache(self._cache_root),
                    )
                return self._colab[endpoint]
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
        try:
            engine = self.engine_resolver(job)
        except EngineError as exc:
            self._finish_fatal(job_id, exc)
            return

        try:
            scanned = {item.id: item for item in FileScanner(job.folder).scan()}
        except OSError as exc:
            self._finish_fatal(
                job_id,
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
                continue

            if not job.force_retranscribe and item.completion_status == BundleStatus.DONE:
                self._set_file_state(job_id, file_id, FileStatus.DONE, item.filename)
                self._event(job_id, "info", "File", "정상 결과가 있어 전사를 건너뜁니다.", file_id, item.filename)
                continue

            source_path = Path(item.source_path)
            try:
                self._set_file_state(job_id, file_id, FileStatus.PREPARING, item.filename)
                self._set_file_state(job_id, file_id, FileStatus.TRANSCRIBING, item.filename)
                result = engine.transcribe(
                    source_path,
                    token,
                    lambda level, category, message: self._event(
                        job_id, level, category, message, file_id, item.filename
                    ),
                    lambda progress: self._set_progress(job_id, progress),
                )
                token.raise_if_requested()
                self._set_file_state(job_id, file_id, FileStatus.SAVING, item.filename)

                def before_verify():
                    token.raise_if_requested()
                    self._set_file_state(job_id, file_id, FileStatus.VERIFYING, item.filename)

                self.output_writer.commit(
                    source_path,
                    result,
                    verification_callback=before_verify,
                )
                token.raise_if_requested()
                self._set_file_state(job_id, file_id, FileStatus.DONE, item.filename)
                self._event(job_id, "info", "File", "파일 전사 완료", file_id, item.filename)
                if self.file_completed_callback is not None:
                    self.file_completed_callback(job_id, file_id, item.filename)
            except StopRequested:
                self._set_file_state(job_id, file_id, FileStatus.STOPPED, item.filename)
                self._event(job_id, "warning", "Stop", "사용자가 전사를 중지함", file_id, item.filename)
                break
            except CancelRequested:
                self._acknowledge_cancel(job_id, file_id, item.filename)
                break
            except EngineError as exc:
                self._file_failed(job_id, file_id, item.filename, exc)
                if exc.fatal:
                    fatal_error = True
                    break
            except Exception as exc:
                logger.exception("Unexpected transcription error for %s", source_path)
                normalized = EngineError(
                    "TRANSCRIPTION_INTERNAL_ERROR",
                    ErrorCategory.RUNTIME,
                    "전사 처리 중 내부 오류가 발생했습니다.",
                    technical_detail=str(exc),
                )
                self._file_failed(job_id, file_id, item.filename, normalized)

        self._finalize(job_id, token, fatal_error)

    def _set_file_state(self, job_id: str, file_id: str, state: FileStatus, filename: str):
        def mutation(job: JobModel):
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

    def _finish_fatal(self, job_id: str, error: EngineError):
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

        self.job_manager.mutate_job(job_id, mutation)

    def _acknowledge_cancel(self, job_id: str, file_id: str, filename: str):
        def mutation(job: JobModel):
            job.files[file_id] = FileStatus.CANCELLED
            for pending_id, state in job.files.items():
                if state in {FileStatus.WAITING, FileStatus.CANCEL_REQUESTED}:
                    job.files[pending_id] = FileStatus.CANCELLED
            job.status = FileStatus.CANCELLED
            job.current_file = None
            job.current_progress = None
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

    def _finalize(self, job_id: str, token: CancellationToken, fatal_error: bool):
        def mutation(job: JobModel):
            self._update_counts(job)
            if token.is_cancel_requested or job.status == FileStatus.CANCEL_REQUESTED:
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
            self._update_counts(job)
            job.events.append(JobEvent(level="info", category="Job", message="Job 완료"))

        self.job_manager.mutate_job(job_id, mutation)
        finished = self.job_manager.get_job(job_id)
        if finished is not None and self.job_finished_callback is not None:
            self.job_finished_callback(finished)

    @staticmethod
    def _update_counts(job: JobModel):
        job.done_files = sum(state == FileStatus.DONE for state in job.files.values())
        job.failed_files = sum(state == FileStatus.FAILED for state in job.files.values())


class BackgroundExecutionService:
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

    def start(self, job_id: str) -> bool:
        job = self.runner.job_manager.get_job(job_id)
        if job is None or job.status != FileStatus.WAITING:
            return False
        with self._lock:
            existing = self._futures.get(job_id)
            if existing is not None and not existing.done():
                return False
            token = CancellationToken()
            self._tokens[job_id] = token
            future = self._executor.submit(self.runner.run, job_id, token)
            self._futures[job_id] = future
        future.add_done_callback(lambda _: self._cleanup(job_id))
        return True

    def request_stop(self, job_id: str) -> bool:
        with self._lock:
            token = self._tokens.get(job_id)
            if token is None:
                return False
            token.request_stop()
            return True

    def request_cancel(self, job_id: str) -> bool:
        with self._lock:
            token = self._tokens.get(job_id)
            if token is None:
                return False
            token.request_cancel()
            return True

    def _cleanup(self, job_id: str):
        with self._lock:
            self._tokens.pop(job_id, None)
            self._futures.pop(job_id, None)
