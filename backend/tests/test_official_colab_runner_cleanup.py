"""PHASE 16A (#248): owned Runtime cleanup on every Runner exit path.

Mock E2E reuses the PHASE 16 harness (real launcher -> preflight ->
RuntimeOwnership/RuntimeClient -> pipeline -> Runner/Writer, Google/Jupyter/ML
faked, external sockets blocked). Unit cases use an in-process session engine.
"""

import json

import httpx
import pytest

import src.services.transcription_runner as runner_module
from src.domain.models import FileStatus
from src.domain.transcription import CancellationToken, TranscriptionResult
from src.services.colab_runtime_ownership import OwnershipState
from src.services.job_manager import JobManager, JobStorageError
from src.services.output_bundle import BundlePaths, OutputBundleValidator
from src.services.transcription_runner import (
    REMOTE_CLEANUP_UNCONFIRMED_MESSAGE, UNEXPECTED_RUNNER_ERROR_MESSAGE, TranscriptionRunner,
)
from test_official_colab_desktop_launch import (  # noqa: F401 (fixtures)
    add_source, create, deletes, env, failed_with, forged, ml, no_external_network, posts, records, run,
)

SECRET = "ya29.SECRET-token runtimes/sorigul-leak proxy-token"


class ExplodingScanner:
    def __init__(self, exc):
        self.exc = exc

    def __call__(self, folder):
        return self

    def scan(self):
        raise self.exc


def cleanup_failed_event(job):
    return any(e.message == REMOTE_CLEANUP_UNCONFIRMED_MESSAGE for e in job.events)


def jobs_json(env):
    return (env.root / "job-state" / "jobs.json").read_text(encoding="utf-8")


def delete_uncertain(env):
    """DELETE never answers (timeout): the cleanup result is unknown."""
    original = env.runtime.handle

    def handle(request):
        if request.method == "DELETE":
            env.runtime.calls.append(request)
            raise httpx.ReadTimeout("no answer", request=request)
        return original(request)
    env.runtime.handle = handle


# 1. Runtime created, then the scan fails -> cleanup -> sanitized FAILED --------

@pytest.mark.parametrize("exc", [ValueError(SECRET), RuntimeError(SECRET), KeyError(SECRET)])
def test_unexpected_scan_error_after_create_deletes_owned_runtime_and_fails_job(env, monkeypatch, exc):
    env.install()
    monkeypatch.setattr(runner_module, "FileScanner", ExplodingScanner(exc))
    token = CancellationToken()
    finished = run(env, create(env), token)
    assert len(posts(env)) == 1 and len(deletes(env)) == 1
    assert [r.state for r in records(env)] == [OwnershipState.CLEANED]
    assert finished.status is FileStatus.FAILED and not finished.batch_completed
    assert finished.error == UNEXPECTED_RUNNER_ERROR_MESSAGE
    assert not cleanup_failed_event(finished) and token.is_finished
    assert SECRET not in jobs_json(env) and "ya29" not in jobs_json(env)
    assert env.routes.official_colab_status()["available"] is True


def test_scan_oserror_keeps_existing_message_and_cleans_once(env, monkeypatch):
    env.install()
    monkeypatch.setattr(runner_module, "FileScanner", ExplodingScanner(PermissionError(SECRET)))
    finished = run(env, create(env))
    assert finished.status is FileStatus.FAILED and finished.error == "전사 폴더를 읽을 수 없습니다."
    assert len(posts(env)) == 1 and len(deletes(env)) == 1
    assert [r.state for r in records(env)] == [OwnershipState.CLEANED]


@pytest.mark.parametrize("fault", ["delete_500", "delete_timeout"])
def test_scan_error_with_failed_or_uncertain_delete_blocks_next_launch(env, monkeypatch, fault):
    env.install()
    if fault == "delete_500":
        env.faults.delete_status = 500
    else:
        delete_uncertain(env)
    real_scanner = runner_module.FileScanner
    monkeypatch.setattr(runner_module, "FileScanner", ExplodingScanner(RuntimeError(SECRET)))
    finished = run(env, create(env))
    assert finished.status is FileStatus.FAILED and cleanup_failed_event(finished)
    assert len(deletes(env)) >= 1 and len(posts(env)) == 1
    assert [r.state for r in records(env)] == [OwnershipState.CLEANUP_REQUIRED]
    assert [r["code"] for r in env.routes.official_colab_status()["reasons"]] == ["OWNERSHIP_UNRESOLVED"]
    calls_before = len(env.runtime.calls)
    monkeypatch.setattr(runner_module, "FileScanner", real_scanner)
    second = run(env, forged(env))
    assert failed_with(env, second) == "OFFICIAL_COLAB_OWNERSHIP_UNRESOLVED"
    assert len(posts(env)) == 1 and len(env.runtime.calls) == calls_before


# 2. Job state mutation / persistence failures ---------------------------------

def test_unexpected_job_event_error_after_create_is_cleaned_and_recorded(env, monkeypatch):
    env.install()
    original = TranscriptionRunner._event

    def failing_event(self, job_id, level, category, message, *args, **kwargs):
        if message == "전사 시작":
            raise RuntimeError(SECRET)
        return original(self, job_id, level, category, message, *args, **kwargs)
    monkeypatch.setattr(TranscriptionRunner, "_event", failing_event)
    finished = run(env, create(env))
    assert finished.status is FileStatus.FAILED and finished.error == UNEXPECTED_RUNNER_ERROR_MESSAGE
    assert finished.files[env.source.stem] is FileStatus.WAITING
    assert len(posts(env)) == 1 and len(deletes(env)) == 1
    assert [r.state for r in records(env)] == [OwnershipState.CLEANED]
    assert SECRET not in jobs_json(env)


def test_job_store_unwritable_after_create_still_deletes_runtime_and_never_shows_success(env, monkeypatch):
    resolver = env.install()
    job = create(env)

    def resolve_then_break_store(model):
        engine = resolver(model)

        def unwritable():
            raise JobStorageError("JOB_STORAGE_WRITE_FAILED", "disk gone")
        monkeypatch.setattr(env.manager, "_save_jobs_unlocked", unwritable)
        return engine
    token = CancellationToken()
    with pytest.raises(JobStorageError):
        TranscriptionRunner(env.manager, resolve_then_break_store).run(job.job_id, token)
    # Cleanup ran before the state write was attempted; nothing claims success.
    assert len(posts(env)) == 1 and len(deletes(env)) == 1
    assert [r.state for r in records(env)] == [OwnershipState.CLEANED]
    assert not token.is_finished
    persisted = json.loads(jobs_json(env))[job.job_id]
    assert persisted["status"] == "WAITING" and persisted["files"][env.source.stem] == "WAITING"
    assert env.manager.get_job(job.job_id).status is FileStatus.WAITING
    assert not BundlePaths.final_for(env.source).txt.exists()


def test_job_store_unwritable_and_cleanup_failed_keeps_ownership_blocking(env, monkeypatch):
    resolver = env.install()
    env.faults.delete_status = 500
    job = create(env)

    def resolve_then_break_store(model):
        engine = resolver(model)
        monkeypatch.setattr(env.manager, "_save_jobs_unlocked",
                            lambda: (_ for _ in ()).throw(JobStorageError("JOB_STORAGE_WRITE_FAILED", "disk gone")))
        return engine
    with pytest.raises(JobStorageError):
        TranscriptionRunner(env.manager, resolve_then_break_store).run(job.job_id, CancellationToken())
    # The ownership store (separate durable file) is the fail-closed record.
    assert [r.state for r in records(env)] == [OwnershipState.CLEANUP_REQUIRED]
    assert [r["code"] for r in env.routes.official_colab_status()["reasons"]] == ["OWNERSHIP_UNRESOLVED"]


# 3. Already committed files are preserved ---------------------------------------

def test_error_after_committed_file_keeps_bundle_and_done_state(env, monkeypatch):
    env.install()
    second = add_source(env, 2)
    job = env.routes.create_job(env.routes.CreateJobRequest(
        folder=str(env.study), engine="official_colab", scope="selected",
        file_ids=[env.source.stem, second.stem], course="개념완성", subject="민법", week=1))
    original = TranscriptionRunner._set_file_state
    seen = {"done": 0}

    def fail_on_second_file(self, job_id, file_id, state, filename):
        if state is FileStatus.DONE:
            seen["done"] += 1
        if file_id == second.stem and state is FileStatus.PREPARING:
            raise RuntimeError(SECRET)
        return original(self, job_id, file_id, state, filename)
    monkeypatch.setattr(TranscriptionRunner, "_set_file_state", fail_on_second_file)
    original_finalize = TranscriptionRunner._finalize
    monkeypatch.setattr(TranscriptionRunner, "_finalize",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError(SECRET)))
    finished = run(env, job)
    monkeypatch.setattr(TranscriptionRunner, "_finalize", original_finalize)
    assert seen["done"] == 1
    assert finished.files[env.source.stem] is FileStatus.DONE
    assert finished.files[second.stem] is FileStatus.FAILED
    assert finished.status is FileStatus.FAILED and finished.done_files == 1
    OutputBundleValidator().validate(BundlePaths.final_for(env.source))
    assert len(posts(env)) == 1 and len(deletes(env)) == 1
    assert [r.state for r in records(env)] == [OwnershipState.CLEANED]


def test_cleanup_failure_after_done_never_deletes_saved_bundle(env):
    env.install()
    env.faults.delete_status = 500
    finished = run(env, create(env))
    assert finished.status is FileStatus.FAILED and cleanup_failed_event(finished)
    assert finished.files[env.source.stem] is FileStatus.DONE
    OutputBundleValidator().validate(BundlePaths.final_for(env.source))


# 4. STOP / CANCEL with failed cleanup is never shown as clean ------------------

@pytest.mark.parametrize("cancel", [False, True])
def test_stop_cancel_with_failed_cleanup_is_failed_not_clean(env, cancel):
    env.install()
    env.faults.delete_status = 500
    token = CancellationToken()

    def after_http(method, name, body):
        if method == "PUT" and name.endswith(".mp3"):
            (token.request_cancel if cancel else token.request_stop)()
    env.server.after_http = after_http
    finished = run(env, create(env), token)
    assert finished.status is FileStatus.FAILED and cleanup_failed_event(finished)
    assert [r.state for r in records(env)] == [OwnershipState.CLEANUP_REQUIRED]


# 5. Only the owned Runtime, exactly once ------------------------------------------

def test_only_the_owned_runtime_is_deleted_exactly_once(env, monkeypatch):
    env.install()
    monkeypatch.setattr(runner_module, "FileScanner", ExplodingScanner(ValueError("bad metadata")))
    run(env, create(env))
    [post] = posts(env)
    [delete] = deletes(env)
    [record] = records(env)
    assert post.url.params["runtimeId"] == record.runtime_name.split("/", 1)[1]
    assert delete.url.path == "/v1beta/" + record.runtime_name


# 6. Unit: session guard semantics (no network) ---------------------------------

class SessionEngine:
    def __init__(self, close_result=True, close_raises=False):
        self.close_calls = 0
        self.close_result = close_result
        self.close_raises = close_raises

    def transcribe(self, source_path, token, event_callback, progress_callback):
        return TranscriptionResult(text="", segments=[], language="ko", metadata={})

    def close_session(self):
        self.close_calls += 1
        if self.close_raises:
            raise RuntimeError(SECRET)
        return self.close_result


@pytest.fixture
def unit(tmp_path):
    folder = tmp_path / "study"
    folder.mkdir()
    (folder / "a.mp3").write_bytes(b"x")
    manager = JobManager(str(tmp_path / "jobs.json"))
    job = manager.create_job(str(folder), ["a"], engine="official_colab")
    return manager, job


@pytest.mark.parametrize("close_result, close_raises, clean", [
    (True, False, True), (False, False, False), (None, False, False), (True, True, False),
])
def test_unexpected_error_closes_session_once_with_honest_result(unit, monkeypatch, close_result,
                                                                 close_raises, clean):
    manager, job = unit
    engine = SessionEngine(close_result, close_raises)
    monkeypatch.setattr(runner_module, "FileScanner", ExplodingScanner(RuntimeError(SECRET)))
    token = CancellationToken()
    TranscriptionRunner(manager, lambda _: engine).run(job.job_id, token)
    finished = manager.get_job(job.job_id)
    assert engine.close_calls == 1 and token.is_finished
    assert finished.status is FileStatus.FAILED
    assert cleanup_failed_event(finished) is (not clean)
    assert SECRET not in manager.storage_path.read_text(encoding="utf-8")


def test_base_exception_still_closes_session_and_propagates(unit, monkeypatch):
    manager, job = unit
    engine = SessionEngine()

    class Abort(BaseException):
        pass
    monkeypatch.setattr(runner_module, "FileScanner", ExplodingScanner(Abort()))
    with pytest.raises(Abort):
        TranscriptionRunner(manager, lambda _: engine).run(job.job_id, CancellationToken())
    assert engine.close_calls == 1


def test_done_job_with_failing_finished_callback_stays_done_and_closes_once(unit, tmp_path, monkeypatch):
    manager, job = unit
    engine = SessionEngine()

    class Scanned:
        id = "a"
        filename = "a.mp3"
        source_path = str(tmp_path / "study" / "a.mp3")
        completion_status = None
        duration_seconds = 1.0

    class Scanner:
        def __init__(self, folder):
            pass

        def scan(self):
            return [Scanned()]

    class Writer:
        def commit(self, *args, **kwargs):
            return None
    monkeypatch.setattr(runner_module, "FileScanner", Scanner)

    def finished_callback(model):
        raise RuntimeError(SECRET)
    runner = TranscriptionRunner(manager, lambda _: engine, output_writer=Writer(),
                                 job_finished_callback=finished_callback)
    runner.run(job.job_id, CancellationToken())
    finished = manager.get_job(job.job_id)
    assert finished.status is FileStatus.DONE and engine.close_calls == 1


# 7. Local / DirectColab regression: no session, behaviour unchanged ---------------

class LocalEngine:
    def transcribe(self, *args):
        raise AssertionError("not reached")


@pytest.mark.parametrize("engine_name", ["local_whisper", "direct_colab"])
def test_engines_without_session_keep_propagating_unexpected_scan_errors(tmp_path, monkeypatch, engine_name):
    folder = tmp_path / "study"
    folder.mkdir()
    manager = JobManager(str(tmp_path / "jobs.json"))
    job = manager.create_job(str(folder), ["a"], engine=engine_name)
    monkeypatch.setattr(runner_module, "FileScanner", ExplodingScanner(ValueError("x")))
    token = CancellationToken()
    with pytest.raises(ValueError):
        TranscriptionRunner(manager, lambda _: LocalEngine()).run(job.job_id, token)
    assert not token.is_finished
