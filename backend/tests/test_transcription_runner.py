import threading
from pathlib import Path

from src.domain.models import FileStatus
from src.domain.transcription import (
    CancellationToken,
    EngineError,
    ErrorCategory,
    TranscriptionResult,
)
from src.services.job_manager import JobManager
from src.services.transcription_runner import BackgroundExecutionService, TranscriptionRunner


def successful_result(name):
    return TranscriptionResult.from_engine_payload(
        {
            "text": f"{name} 결과",
            "segments": [{"start": 0, "end": 1, "text": f"{name} 결과"}],
        }
    )


class PerFileEngine:
    def __init__(self, failures=None, action=None):
        self.failures = failures or set()
        self.action = action
        self.calls = []

    def transcribe(self, source_path, token, event_callback, progress_callback):
        self.calls.append(source_path.stem)
        progress_callback(None)
        if self.action:
            self.action(token)
        if source_path.stem in self.failures:
            raise EngineError(
                "FILE_DECODE_FAILED",
                ErrorCategory.INPUT,
                "파일 전사 실패",
            )
        return successful_result(source_path.stem)


def make_sources(tmp_path, names):
    folder = tmp_path / "전사자료"
    folder.mkdir()
    for name in names:
        (folder / f"{name}.mp3").touch()
    return folder


def test_runner_is_sequential_and_continues_after_partial_failure(tmp_path):
    folder = make_sources(tmp_path, ["A", "B", "C"])
    manager = JobManager(str(tmp_path / "runtime" / "jobs.json"))
    job = manager.create_job(str(folder), ["A", "B", "C"])
    engine = PerFileEngine(failures={"B"})
    runner = TranscriptionRunner(manager, lambda _job: engine)

    runner.run(job.job_id, CancellationToken())

    finished = manager.get_job(job.job_id)
    assert engine.calls == ["A", "B", "C"]
    assert finished.files == {
        "A": FileStatus.DONE,
        "B": FileStatus.FAILED,
        "C": FileStatus.DONE,
    }
    assert finished.status == FileStatus.FAILED
    assert finished.done_files == 2
    assert finished.failed_files == 1
    assert finished.batch_completed is True
    assert (folder / "A.txt").exists()
    assert not (folder / "B.txt").exists()
    assert (folder / "C.txt").exists()


def test_runner_full_success_marks_batch_completed_true(tmp_path):
    folder = make_sources(tmp_path, ["A", "B"])
    manager = JobManager(str(tmp_path / "runtime" / "jobs.json"))
    job = manager.create_job(str(folder), ["A", "B"])
    engine = PerFileEngine()
    TranscriptionRunner(manager, lambda _job: engine).run(job.job_id, CancellationToken())

    finished = manager.get_job(job.job_id)
    assert finished.status == FileStatus.DONE
    assert finished.batch_completed is True


def test_runner_fatal_error_mid_batch_stops_early_and_marks_batch_incomplete(tmp_path):
    folder = make_sources(tmp_path, ["A", "B", "C"])
    manager = JobManager(str(tmp_path / "runtime" / "jobs.json"))
    job = manager.create_job(str(folder), ["A", "B", "C"])

    class FatalOnFileEngine(PerFileEngine):
        def transcribe(self, source_path, token, event_callback, progress_callback):
            self.calls.append(source_path.stem)
            progress_callback(None)
            if source_path.stem == "B":
                raise EngineError(
                    "ENGINE_CRASHED",
                    ErrorCategory.RUNTIME,
                    "엔진 치명적 오류",
                    fatal=True,
                )
            return successful_result(source_path.stem)

    engine = FatalOnFileEngine()
    runner = TranscriptionRunner(manager, lambda _job: engine)

    runner.run(job.job_id, CancellationToken())

    finished = manager.get_job(job.job_id)
    assert engine.calls == ["A", "B"]
    assert finished.files["A"] == FileStatus.DONE
    assert finished.files["B"] == FileStatus.FAILED
    assert finished.files["C"] == FileStatus.WAITING
    assert finished.status == FileStatus.FAILED
    assert finished.batch_completed is False


def test_runner_engine_resolution_fatal_error_marks_batch_incomplete_and_skips_finish_callback(tmp_path):
    folder = make_sources(tmp_path, ["A"])
    manager = JobManager(str(tmp_path / "runtime" / "jobs.json"))
    job = manager.create_job(str(folder), ["A"])
    finished_calls = []

    def failing_resolver(_job):
        raise EngineError(
            "COLAB_URL_MISSING",
            ErrorCategory.CONFIGURATION,
            "Colab 주소가 설정되지 않았습니다.",
            fatal=True,
        )

    runner = TranscriptionRunner(
        manager,
        failing_resolver,
        job_finished_callback=lambda finished_job: finished_calls.append(finished_job),
    )

    runner.run(job.job_id, CancellationToken())

    finished = manager.get_job(job.job_id)
    assert finished.status == FileStatus.FAILED
    assert finished.batch_completed is False
    assert finished_calls == []


def test_runner_stop_does_not_commit_result_or_start_next_file(tmp_path):
    folder = make_sources(tmp_path, ["A", "B"])
    manager = JobManager(str(tmp_path / "runtime" / "jobs.json"))
    job = manager.create_job(str(folder), ["A", "B"])
    engine = PerFileEngine(action=lambda token: token.request_stop())
    runner = TranscriptionRunner(manager, lambda _job: engine)

    runner.run(job.job_id, CancellationToken())

    finished = manager.get_job(job.job_id)
    assert engine.calls == ["A"]
    assert finished.files["A"] == FileStatus.STOPPED
    assert finished.files["B"] == FileStatus.WAITING
    assert finished.status == FileStatus.STOPPED
    assert finished.batch_completed is False
    assert not (folder / "A.txt").exists()


def test_runner_cancel_acknowledges_cancelled_not_failed(tmp_path):
    folder = make_sources(tmp_path, ["A", "B"])
    manager = JobManager(str(tmp_path / "runtime" / "jobs.json"))
    job = manager.create_job(str(folder), ["A", "B"])
    engine = PerFileEngine(action=lambda token: token.request_cancel())
    runner = TranscriptionRunner(manager, lambda _job: engine)

    runner.run(job.job_id, CancellationToken())

    finished = manager.get_job(job.job_id)
    assert finished.status == FileStatus.CANCELLED
    assert finished.files["A"] == FileStatus.CANCELLED
    assert finished.files["B"] == FileStatus.CANCELLED
    assert FileStatus.FAILED not in finished.files.values()
    assert finished.batch_completed is False
    assert not (folder / "A.txt").exists()


def test_runner_preserves_done_file_on_retry_scope(tmp_path):
    folder = make_sources(tmp_path, ["done", "retry"])
    (folder / "done.txt").write_text("old", encoding="utf-8")
    (folder / "done.json").write_text('{"text":"old","segments":[]}', encoding="utf-8")
    (folder / "done.srt").touch()
    manager = JobManager(str(tmp_path / "runtime" / "jobs.json"))
    job = manager.create_job(str(folder), ["done", "retry"])
    job.files["done"] = FileStatus.DONE
    manager.update_job(job)
    engine = PerFileEngine()

    TranscriptionRunner(manager, lambda _job: engine).run(job.job_id, CancellationToken())

    assert engine.calls == ["retry"]
    assert (folder / "done.txt").read_text(encoding="utf-8") == "old"
    assert manager.get_job(job.job_id).status == FileStatus.DONE


def test_background_start_is_non_blocking(tmp_path):
    folder = make_sources(tmp_path, ["A"])
    manager = JobManager(str(tmp_path / "runtime" / "jobs.json"))
    job = manager.create_job(str(folder), ["A"])
    entered = threading.Event()
    release = threading.Event()

    class BlockingEngine(PerFileEngine):
        def transcribe(self, source_path, token, event_callback, progress_callback):
            entered.set()
            release.wait(timeout=5)
            return successful_result("A")

    service = BackgroundExecutionService(
        TranscriptionRunner(manager, lambda _job: BlockingEngine()),
        max_workers=1,
    )
    assert service.start(job.job_id) is True
    assert entered.wait(timeout=2)
    assert manager.get_job(job.job_id).status == FileStatus.TRANSCRIBING
    release.set()


def test_state_transitions_are_persisted_before_done(tmp_path):
    folder = make_sources(tmp_path, ["A"])
    manager = JobManager(str(tmp_path / "runtime" / "jobs.json"))
    job = manager.create_job(str(folder), ["A"])
    observed = []
    original_mutate = manager.mutate_job

    def recording_mutate(job_id, mutation):
        result = original_mutate(job_id, mutation)
        if result:
            observed.append(result.files["A"])
        return result

    manager.mutate_job = recording_mutate
    TranscriptionRunner(manager, lambda _job: PerFileEngine()).run(job.job_id, CancellationToken())

    ordered = [
        FileStatus.PREPARING,
        FileStatus.TRANSCRIBING,
        FileStatus.SAVING,
        FileStatus.VERIFYING,
        FileStatus.DONE,
    ]
    positions = [observed.index(state) for state in ordered]
    assert positions == sorted(positions)
