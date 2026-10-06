import hashlib
import os
import threading
from pathlib import Path

import pytest

from src.domain.models import BundleStatus, FileStatus
from src.domain.transcription import (
    CancellationToken,
    EngineError,
    ErrorCategory,
    TranscriptionResult,
)
from src.services.job_manager import JobManager
from src.services.output_bundle import BundlePaths, OutputBundleValidator, OutputBundleWriter
from src.services.scanner import FileScanner
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


class MonotonicClock:
    def __init__(self, values):
        self.values = iter(values)

    def monotonic(self):
        return next(self.values)


class EtaInspectingEngine(PerFileEngine):
    def __init__(self, manager, job_id, expected_eta):
        super().__init__()
        self.manager = manager
        self.job_id = job_id
        self.expected_eta = expected_eta

    def transcribe(self, source_path, token, event_callback, progress_callback):
        if source_path.stem in self.expected_eta:
            actual = self.manager.get_job(self.job_id).eta_seconds
            expected = self.expected_eta[source_path.stem]
            if expected is None:
                assert actual is None
            else:
                assert actual == pytest.approx(expected)
        return super().transcribe(source_path, token, event_callback, progress_callback)


class ColabProgressInspectingEngine:
    def __init__(
        self,
        manager,
        job_id,
        before_eta=None,
        progress_expectations=None,
        cached_files=None,
    ):
        self.manager = manager
        self.job_id = job_id
        self.before_eta = before_eta or {}
        self.progress_expectations = progress_expectations or {}
        self.cached_files = cached_files or set()
        self.calls = []

    @staticmethod
    def _assert_eta(actual, expected):
        if expected is None:
            assert actual is None
        else:
            assert actual == pytest.approx(expected)

    def transcribe(self, source_path, token, event_callback, progress_callback):
        stem = source_path.stem
        self.calls.append(stem)
        if stem in self.before_eta:
            self._assert_eta(self.manager.get_job(self.job_id).eta_seconds, self.before_eta[stem])

        for progress, expected_eta in self.progress_expectations.get(stem, []):
            progress_callback(progress)
            current = self.manager.get_job(self.job_id)
            assert current.current_progress == pytest.approx(progress * 100)
            self._assert_eta(current.eta_seconds, expected_eta)

        result = successful_result(stem)
        result.metadata["colab_recovery_cache_used"] = stem in self.cached_files
        return result


def patch_audio_durations(monkeypatch, durations):
    monkeypatch.setattr(
        "src.services.audio_metadata.AudioMetadataService.duration_seconds",
        lambda self, path: durations[path.stem],
    )


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
    assert finished.eta_seconds is None


def test_runner_clears_stale_eta_before_first_local_transcribe(tmp_path):
    folder = make_sources(tmp_path, ["A"])
    manager = JobManager(str(tmp_path / "runtime" / "jobs.json"))
    job = manager.create_job(str(folder), ["A"])
    job.eta_seconds = 999
    manager.update_job(job)
    engine = EtaInspectingEngine(manager, job.job_id, {"A": None})

    TranscriptionRunner(manager, lambda _job: engine).run(job.job_id, CancellationToken())

    assert manager.get_job(job.job_id).eta_seconds is None


def test_runner_uses_observed_local_speed_for_next_file_eta(tmp_path, monkeypatch):
    folder = make_sources(tmp_path, ["A", "B"])
    manager = JobManager(str(tmp_path / "runtime" / "jobs.json"))
    job = manager.create_job(str(folder), ["A", "B"])
    patch_audio_durations(monkeypatch, {"A": 100.0, "B": 200.0})
    monkeypatch.setattr(
        "src.services.transcription_runner.time",
        MonotonicClock([0.0, 50.0, 60.0, 70.0]),
    )
    engine = EtaInspectingEngine(manager, job.job_id, {"A": None, "B": 100.0})

    TranscriptionRunner(manager, lambda _job: engine).run(job.job_id, CancellationToken())

    assert manager.get_job(job.job_id).eta_seconds is None


def test_runner_omits_eta_when_remaining_duration_is_unknown(tmp_path, monkeypatch):
    folder = make_sources(tmp_path, ["A", "B"])
    manager = JobManager(str(tmp_path / "runtime" / "jobs.json"))
    job = manager.create_job(str(folder), ["A", "B"])
    patch_audio_durations(monkeypatch, {"A": 100.0, "B": None})
    monkeypatch.setattr(
        "src.services.transcription_runner.time",
        MonotonicClock([0.0, 50.0, 60.0, 70.0]),
    )
    engine = EtaInspectingEngine(manager, job.job_id, {"B": None})

    TranscriptionRunner(manager, lambda _job: engine).run(job.job_id, CancellationToken())

    assert manager.get_job(job.job_id).eta_seconds is None


def test_runner_excludes_failed_file_from_speed_observations(tmp_path, monkeypatch):
    folder = make_sources(tmp_path, ["A", "B", "C"])
    manager = JobManager(str(tmp_path / "runtime" / "jobs.json"))
    job = manager.create_job(str(folder), ["A", "B", "C"])
    patch_audio_durations(monkeypatch, {"A": 100.0, "B": 100.0, "C": 200.0})
    monkeypatch.setattr(
        "src.services.transcription_runner.time",
        MonotonicClock([0.0, 50.0, 60.0, 160.0, 170.0, 180.0]),
    )
    engine = EtaInspectingEngine(manager, job.job_id, {"B": 150.0, "C": 100.0})
    output_writer = OutputBundleWriter()

    class FailOnBWriter:
        def commit(self, source_path, result, **kwargs):
            if source_path.stem == "B":
                raise RuntimeError("output failed")
            return output_writer.commit(source_path, result, **kwargs)

    TranscriptionRunner(
        manager,
        lambda _job: engine,
        output_writer=FailOnBWriter(),
    ).run(job.job_id, CancellationToken())

    finished = manager.get_job(job.job_id)
    assert finished.files["B"] == FileStatus.FAILED
    assert finished.eta_seconds is None


def test_runner_first_colab_file_reports_progress_without_eta(tmp_path, monkeypatch):
    folder = make_sources(tmp_path, ["A"])
    manager = JobManager(str(tmp_path / "runtime" / "jobs.json"))
    job = manager.create_job(str(folder), ["A"], engine="direct_colab")
    patch_audio_durations(monkeypatch, {"A": 100.0})
    monkeypatch.setattr(
        "src.services.transcription_runner.time",
        MonotonicClock([0.0, 50.0]),
    )
    engine = ColabProgressInspectingEngine(
        manager,
        job.job_id,
        before_eta={"A": None},
        progress_expectations={"A": [(0.5, None)]},
    )

    TranscriptionRunner(manager, lambda _job: engine).run(job.job_id, CancellationToken())

    assert manager.get_job(job.job_id).eta_seconds is None


def test_runner_uses_clean_colab_observation_for_progress_aware_eta(tmp_path, monkeypatch):
    folder = make_sources(tmp_path, ["A", "B"])
    manager = JobManager(str(tmp_path / "runtime" / "jobs.json"))
    job = manager.create_job(str(folder), ["A", "B"], engine="direct_colab")
    patch_audio_durations(monkeypatch, {"A": 100.0, "B": 200.0})
    monkeypatch.setattr(
        "src.services.transcription_runner.time",
        MonotonicClock([0.0, 50.0, 60.0, 70.0]),
    )
    engine = ColabProgressInspectingEngine(
        manager,
        job.job_id,
        before_eta={"A": None, "B": 100.0},
        progress_expectations={"A": [(0.5, None)], "B": [(0.5, 50.0)]},
    )

    TranscriptionRunner(manager, lambda _job: engine).run(job.job_id, CancellationToken())

    assert manager.get_job(job.job_id).eta_seconds is None


def test_runner_excludes_recovery_cached_colab_file_from_observations(tmp_path, monkeypatch):
    folder = make_sources(tmp_path, ["A", "B"])
    manager = JobManager(str(tmp_path / "runtime" / "jobs.json"))
    job = manager.create_job(str(folder), ["A", "B"], engine="direct_colab")
    patch_audio_durations(monkeypatch, {"A": 100.0, "B": 200.0})
    monkeypatch.setattr(
        "src.services.transcription_runner.time",
        MonotonicClock([0.0, 1.0, 2.0, 3.0]),
    )
    engine = ColabProgressInspectingEngine(
        manager,
        job.job_id,
        before_eta={"B": None},
        progress_expectations={"B": [(0.5, None)]},
        cached_files={"A"},
    )

    TranscriptionRunner(manager, lambda _job: engine).run(job.job_id, CancellationToken())

    assert manager.get_job(job.job_id).eta_seconds is None


def test_runner_colab_progress_keeps_eta_none_for_unknown_duration(tmp_path, monkeypatch):
    folder = make_sources(tmp_path, ["A", "B"])
    manager = JobManager(str(tmp_path / "runtime" / "jobs.json"))
    job = manager.create_job(str(folder), ["A", "B"], engine="direct_colab")
    patch_audio_durations(monkeypatch, {"A": 100.0, "B": None})
    monkeypatch.setattr(
        "src.services.transcription_runner.time",
        MonotonicClock([0.0, 50.0, 60.0, 70.0]),
    )
    engine = ColabProgressInspectingEngine(
        manager,
        job.job_id,
        before_eta={"B": None},
        progress_expectations={"B": [(0.5, None)]},
    )

    TranscriptionRunner(manager, lambda _job: engine).run(job.job_id, CancellationToken())

    assert manager.get_job(job.job_id).eta_seconds is None


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
    assert finished.eta_seconds is None
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
    assert finished.eta_seconds is None
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


@pytest.fixture
def retry_context(tmp_path, monkeypatch):
    # Import routes only after conftest has isolated application state.
    from src.api import routes

    manager = JobManager(str(tmp_path / "runtime" / "jobs.json"))
    engine = PerFileEngine()
    runner = TranscriptionRunner(manager, lambda _job: engine)
    service = BackgroundExecutionService(runner)
    monkeypatch.setattr(routes, "job_manager", manager)
    monkeypatch.setattr(routes, "execution_service", service)
    return routes, manager, engine, runner


def bundle_hashes(source):
    return {
        key: hashlib.sha256(path.read_bytes()).hexdigest()
        for key, path in BundlePaths.final_for(source).as_dict().items()
    }


def seed_retry_job(manager, folder, states, *, force):
    job = manager.create_job(str(folder), list(states), force_retranscribe=force)
    job.files = states.copy()
    job.status = next(state for state in states.values() if state != FileStatus.DONE)
    # Deliberately stale counters reproduce the reported contradictory state.
    job.done_files = 0
    job.failed_files = len(states)
    job.error = "previous replacement error"
    job.batch_completed = True
    manager.update_job(job)
    return job


@pytest.mark.parametrize("force", [False, True], ids=["ordinary", "forced"])
@pytest.mark.parametrize(
    "state",
    [FileStatus.FAILED, FileStatus.STOPPED, FileStatus.CANCELLED, FileStatus.CRASHED],
)
def test_retry_existing_bundle_honors_force_and_reconciles_state(
    tmp_path, retry_context, force, state
):
    routes, manager, engine, runner = retry_context
    folder = make_sources(tmp_path, ["A"])
    source = folder / "A.mp3"
    OutputBundleWriter().commit(source, successful_result("protected old"))
    old_hashes = bundle_hashes(source)
    assert FileScanner(str(folder)).scan()[0].completion_status == BundleStatus.DONE
    job = seed_retry_job(manager, folder, {"A": state}, force=force)

    # Observe the real writer at staged verification and immediately before
    # promotion: old results must remain complete and byte-identical until then.
    observed_phases = []

    class InspectingValidator(OutputBundleValidator):
        def validate(self, paths):
            if paths.txt.name.endswith(".tmp"):
                assert manager.get_job(job.job_id).files["A"] == FileStatus.VERIFYING
                assert bundle_hashes(source) == old_hashes
                assert paths.txt.read_text(encoding="utf-8") == "A 결과"
                observed_phases.append("verify")
            return super().validate(paths)

    class InspectingWriter(OutputBundleWriter):
        def _replace_bundle(self, staged, final, backup):
            assert bundle_hashes(source) == old_hashes
            observed_phases.append("promote")
            return super()._replace_bundle(staged, final, backup)

    runner.output_writer = InspectingWriter(validator=InspectingValidator())
    retried = routes.job_action(job.job_id, routes.JobActionRequest(action="retry"))

    expected = FileStatus.WAITING if force else FileStatus.DONE
    assert retried.status == expected
    assert retried.files == {"A": expected}
    assert retried.done_files == (0 if force else 1)
    assert retried.failed_files == 0
    assert retried.error is None
    assert retried.force_retranscribe is force
    assert retried.events[-1].category == "Retry"
    assert retried.events[-1].message == (
        "재시도 시작" if force else "재시도할 미완료 파일 없음"
    )
    if force:
        assert retried.batch_completed is False
        assert not any(event.message == "재시도할 미완료 파일 없음" for event in retried.events)
    assert bundle_hashes(source) == old_hashes
    # The force flag, counts and error must survive a jobs.json round trip.
    assert JobManager(str(manager.storage_path)).get_job(job.job_id) == retried

    runner.run(job.job_id, CancellationToken())

    finished = manager.get_job(job.job_id)
    assert engine.calls == (["A"] if force else [])
    assert observed_phases == (["verify", "promote"] if force else [])
    assert finished.status == FileStatus.DONE
    assert finished.files == {"A": FileStatus.DONE}
    assert finished.done_files == 1 and finished.failed_files == 0
    assert finished.error is None
    assert finished.force_retranscribe is force
    assert finished.batch_completed is True
    OutputBundleValidator().validate(BundlePaths.final_for(source))
    if force:
        assert all(bundle_hashes(source)[key] != value for key, value in old_hashes.items())
        assert source.with_suffix(".txt").read_text(encoding="utf-8") == "A 결과"
    else:
        assert bundle_hashes(source) == old_hashes
    assert not list(folder.glob(".*.tmp"))
    assert not list(folder.glob(".*.bak"))


@pytest.mark.parametrize("failure", ["engine", "verification", "promotion", "final_validation"])
def test_forced_retry_failure_preserves_bundle_and_stays_retriable(
    tmp_path, retry_context, failure
):
    routes, manager, engine, runner = retry_context
    folder = make_sources(tmp_path, ["A"])
    source = folder / "A.mp3"
    OutputBundleWriter().commit(source, successful_result("protected old"))
    old_hashes = bundle_hashes(source)
    job = seed_retry_job(manager, folder, {"A": FileStatus.FAILED}, force=True)
    expected_error = "파일 전사 실패"
    if failure == "engine":
        engine.failures = {"A"}
    elif failure in {"verification", "final_validation"}:
        expected_error = "replacement verification failed"

        class FailingValidator(OutputBundleValidator):
            def validate(self, paths):
                if failure == "final_validation" or paths.txt.name.endswith(".tmp"):
                    if failure == "verification":
                        assert bundle_hashes(source) == old_hashes
                    raise EngineError("REPLACEMENT_INVALID", ErrorCategory.OUTPUT, expected_error)
                return super().validate(paths)

        runner.output_writer = OutputBundleWriter(validator=FailingValidator())
    else:
        expected_error = "결과 파일을 안전하게 교체하지 못했습니다."

        def failing_replace(src, dst):
            # Fail after TXT promotion so rollback must restore all three files.
            if src.name.endswith(".json.tmp"):
                raise OSError("injected replacement failure")
            os.replace(src, dst)

        runner.output_writer = OutputBundleWriter(replace=failing_replace)

    retried = routes.job_action(job.job_id, routes.JobActionRequest(action="retry"))
    assert retried.status == FileStatus.WAITING
    assert bundle_hashes(source) == old_hashes
    runner.run(job.job_id, CancellationToken())

    failed = manager.get_job(job.job_id)
    assert engine.calls == ["A"]
    assert failed.status == FileStatus.FAILED
    assert failed.files == {"A": FileStatus.FAILED}
    assert failed.done_files == 0 and failed.failed_files == 1
    assert failed.error == expected_error
    assert failed.force_retranscribe is True
    assert bundle_hashes(source) == old_hashes
    OutputBundleValidator().validate(BundlePaths.final_for(source))
    assert not list(folder.glob(".*.tmp"))
    assert not list(folder.glob(".*.bak"))

    retried_again = routes.job_action(job.job_id, routes.JobActionRequest(action="retry"))
    assert retried_again.files == {"A": FileStatus.WAITING}
    assert retried_again.status == FileStatus.WAITING
    assert retried_again.failed_files == 0 and retried_again.done_files == 0
    assert retried_again.error is None
    assert retried_again.batch_completed is False
    assert retried_again.events[-1].message == "재시도 시작"
    assert bundle_hashes(source) == old_hashes


def test_forced_retry_mixed_batch_preserves_done_and_reruns_only_terminal_files(
    tmp_path, retry_context
):
    routes, manager, engine, runner = retry_context
    folder = make_sources(tmp_path, ["A", "B", "C"])
    for name in ("A", "B", "C"):
        OutputBundleWriter().commit(folder / f"{name}.mp3", successful_result(f"old {name}"))
    old_hashes = {name: bundle_hashes(folder / f"{name}.mp3") for name in ("A", "B", "C")}
    job = seed_retry_job(
        manager, folder,
        {"A": FileStatus.DONE, "B": FileStatus.FAILED, "C": FileStatus.CANCELLED},
        force=True,
    )

    retried = routes.job_action(job.job_id, routes.JobActionRequest(action="retry"))

    assert retried.files == {"A": FileStatus.DONE, "B": FileStatus.WAITING, "C": FileStatus.WAITING}
    assert retried.status == FileStatus.WAITING
    assert retried.done_files == 1 and retried.failed_files == 0
    assert retried.error is None
    assert retried.force_retranscribe is True
    assert retried.batch_completed is False
    assert retried.events[-1].message == "재시도 시작"
    assert old_hashes == {name: bundle_hashes(folder / f"{name}.mp3") for name in old_hashes}

    runner.run(job.job_id, CancellationToken())

    finished = manager.get_job(job.job_id)
    assert engine.calls == ["B", "C"]
    assert finished.files == {name: FileStatus.DONE for name in ("A", "B", "C")}
    assert finished.status == FileStatus.DONE
    assert finished.done_files == 3 and finished.failed_files == 0
    assert finished.error is None
    assert bundle_hashes(folder / "A.mp3") == old_hashes["A"]
    for name in ("B", "C"):
        assert bundle_hashes(folder / f"{name}.mp3") != old_hashes[name]


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

    def recording_mutate(job_id, mutation, **kwargs):
        result = original_mutate(job_id, mutation, **kwargs)
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
