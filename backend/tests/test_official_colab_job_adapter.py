"""Default-off API -> real resolver/runner/pipeline/writer, mocked Google/ML/WS."""

import json
import logging
import socket
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from src.domain.models import FileStatus
from src.domain.transcription import CancellationToken, EngineError, ErrorCategory, TranscriptionResult
from src.engines.colab import AudioChunk
from src.engines.official_colab import OfficialColabJobEngine
from src.services.job_manager import JobManager
from src.services.output_bundle import BundlePaths, OutputBundleValidator, OutputBundleWriter
from src.services.settings import SettingsManager
from src.services.transcription_runner import DefaultEngineResolver, TranscriptionRunner
from test_colab_full_file_pipeline import setup as full_setup, ml
from test_colab_jupyter_files import TOKEN, URL
from test_colab_runtime_client import OAUTH


@pytest.fixture(autouse=True)
def no_external_network(monkeypatch):
    real_connect = socket.socket.connect
    def denied(*args, **kwargs):
        raise AssertionError("PHASE 11 live network forbidden")
    def loopback_only(sock, address):
        # Windows asyncio's socketpair uses a loopback self-pipe for ASGI tests.
        if isinstance(address, tuple) and address[0] in ("127.0.0.1", "::1"):
            return real_connect(sock, address)
        return denied()
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket.socket, "connect", loopback_only)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", denied)


@pytest.fixture
def env(full_setup, tmp_path, monkeypatch):
    import src.api.routes as routes
    source = full_setup.source.with_name("개념완성_민법_1주차_1강.mp3")
    full_setup.source.rename(source)
    full_setup.source = source
    manager = JobManager(str(tmp_path / "job-state" / "jobs.json"))
    monkeypatch.setattr(routes, "job_manager", manager)
    monkeypatch.setattr(routes, "settings_manager", SettingsManager(tmp_path / "job-state" / "settings.json"))
    created = []
    original_http = full_setup.server.http
    def http(method, url, headers, body, timeout):
        if method == "POST" and url.endswith("/api/kernels"):
            full_setup.server.ws.namespace = {}
            full_setup.server.ws.frames = []
        return original_http(method, url, headers, body, timeout)
    def factory(ownership, cache):
        assert ownership is full_setup.owner
        pipeline = full_setup.pipeline()
        pipeline.cache = cache
        pipeline._http = http
        created.append(pipeline)
        return pipeline
    def resolver(enabled=True, owner=True):
        result = DefaultEngineResolver(
            cache_root=tmp_path / "job-cache", official_colab_enabled=enabled,
            official_colab_ownership=full_setup.owner if owner else None,
            official_colab_pipeline_factory=factory)
        monkeypatch.setattr(routes, "engine_resolver", result)
        return result
    yield SimpleNamespace(mock=full_setup, source=source, manager=manager, routes=routes,
                          resolver=resolver, created=created, root=tmp_path)


def create(env, **overrides):
    values = dict(folder=str(env.source.parent), engine="official_colab", scope="selected",
                  file_ids=[env.source.stem], course="개념완성", subject="민법", week=1)
    values.update(overrides)
    return env.routes.create_job(env.routes.CreateJobRequest(**values))


def execute(env, job, resolver=None, token=None, writer=None):
    resolver = resolver or env.routes.engine_resolver
    runner = TranscriptionRunner(env.manager, resolver, output_writer=writer)
    runner.run(job.job_id, token or CancellationToken())
    return env.manager.get_job(job.job_id)


def add_source(env, lesson):
    path = env.source.with_name(f"개념완성_민법_1주차_{lesson}강.mp3")
    path.write_bytes(b"mock MP3 source" * 100)
    return path


def valid_old_bundle(source):
    OutputBundleWriter().commit(source, TranscriptionResult.from_engine_payload({
        "text": "기존 정상 결과", "language": "ko",
        "segments": [{"start": 0, "end": 1, "text": "기존 정상 결과"}]}))
    return {path: path.read_bytes() for path in BundlePaths.final_for(source).as_dict().values()}


@pytest.mark.parametrize("owner,enabled", [(False, False), (True, False), (False, True)])
def test_official_default_off_cannot_be_enabled_by_request(env, owner, enabled):
    from fastapi import HTTPException
    env.resolver(enabled=enabled, owner=owner)
    before = len(env.mock.runtime.calls)
    with pytest.raises(HTTPException) as exc:
        create(env, engine_config={"enabled": True, "token": TOKEN}, official_colab_enabled=True)
    assert exc.value.status_code == 400
    assert env.manager.list_jobs() == [] and env.created == []
    assert len(env.mock.runtime.calls) == before and env.mock.server.calls == []


def test_default_resolver_refuses_internal_forged_official_job(env):
    resolver = DefaultEngineResolver(cache_root=env.root / "off-cache")
    job = env.manager.create_job(str(env.source.parent), [env.source.stem], engine="official_colab")
    finished = execute(env, job, resolver)
    assert finished.status is FileStatus.FAILED and not finished.batch_completed
    assert env.mock.server.calls == []


def test_enabled_job_api_runner_real_worker_bundle_e2e(env):
    resolver = env.resolver()
    job = create(env)
    assert job.engine_config == {} and job.upload_to_drive is False and job.drive == {}
    states, progress = [], []
    original_mutate = env.manager.mutate_job
    def mutate(*args, **kwargs):
        result = original_mutate(*args, **kwargs)
        current = env.manager.get_job(job.job_id)
        states.append(current.files[env.source.stem])
        progress.append((current.files[env.source.stem], current.current_progress))
        return result
    env.manager.mutate_job = mutate
    finished = execute(env, job, resolver)
    assert finished.status is FileStatus.DONE and finished.batch_completed and finished.done_files == 1
    assert set((FileStatus.PREPARING, FileStatus.TRANSCRIBING, FileStatus.SAVING, FileStatus.VERIFYING, FileStatus.DONE)) <= set(states)
    assert all(value is None or value < 100 for state, value in progress if state is not FileStatus.DONE)
    paths = BundlePaths.final_for(env.source)
    OutputBundleValidator().validate(paths)
    assert paths.txt.read_text(encoding="utf-8") == "한국어 조각 0\n한국어 조각 1"
    payload = json.loads(paths.json.read_text(encoding="utf-8"))
    assert payload["segments"][1]["start"] == 300.2
    assert "00:05:00,200" in paths.srt.read_text(encoding="utf-8")
    assert len(env.mock.ml.loads) == 1 and len(env.mock.ml.decodes) == 2
    assert all(request.method != "DELETE" for request in env.mock.runtime.calls)
    assert finished.eta_seconds is None


def test_existing_bundle_excluded_by_creation_and_skipped_by_runner(env):
    from fastapi import HTTPException
    resolver = env.resolver()
    before = valid_old_bundle(env.source)
    with pytest.raises(HTTPException, match="400"):
        create(env)
    # A pre-existing waiting Job must also re-scan and skip the now-complete bundle.
    job = env.manager.create_job(str(env.source.parent), [env.source.stem], engine="official_colab")
    finished = execute(env, job, resolver)
    assert finished.status is FileStatus.DONE and env.mock.server.calls == []
    assert all(path.read_bytes() == value for path, value in before.items())


@pytest.mark.parametrize("failure", [False, True])
def test_forced_retranscription_preserves_prior_bundle_until_valid_promotion(env, failure):
    resolver = env.resolver()
    before = valid_old_bundle(env.source)
    job = create(env, force_retranscribe=True)
    if failure:
        env.mock.server.fail_decode = 0
    class InspectWriter(OutputBundleWriter):
        def commit(self, source, result, **kwargs):
            assert all(path.read_bytes() == value for path, value in before.items())
            return super().commit(source, result, **kwargs)
    finished = execute(env, job, resolver, writer=InspectWriter())
    if failure:
        assert finished.status is FileStatus.FAILED
        assert all(path.read_bytes() == value for path, value in before.items())
    else:
        assert finished.status is FileStatus.DONE
        assert BundlePaths.final_for(env.source).txt.read_text(encoding="utf-8").startswith("한국어 조각")


def test_multiple_mp3_are_sequential_with_fresh_file_kernels(env):
    resolver = env.resolver()
    second = add_source(env, 2)
    third = add_source(env, 3)
    job = create(env, file_ids=[env.source.stem, second.stem, third.stem])
    finished = execute(env, job, resolver)
    assert finished.status is FileStatus.DONE and finished.done_files == 3
    assert len(env.mock.ml.loads) == 3 and len(env.mock.ml.decodes) == 6
    operations = [m for m, p in env.mock.server.calls if p in ("/api/kernels", "/api/kernels/owned-kernel")]
    assert operations == ["POST", "DELETE"] * 3


def test_bad_middle_mp3_remains_file_failure_and_next_mp3_runs(env):
    resolver = env.resolver()
    second, third = add_source(env, 2), add_source(env, 3)
    original = env.mock.pipeline
    def pipeline(*args, **kwargs):
        result = original(*args, **kwargs)
        split = result.splitter.split
        def checked(source, seconds, token):
            if source == second:
                raise EngineError("AUDIO_EMPTY", ErrorCategory.INPUT, "invalid mock audio")
            return split(source, seconds, token)
        result.splitter.split = checked
        return result
    env.mock.pipeline = pipeline
    job = create(env, file_ids=[env.source.stem, second.stem, third.stem])
    finished = execute(env, job, resolver)
    assert finished.files == {env.source.stem: FileStatus.DONE, second.stem: FileStatus.FAILED, third.stem: FileStatus.DONE}
    assert finished.status is FileStatus.FAILED and finished.batch_completed
    assert len(env.mock.ml.decodes) == 4


@pytest.mark.parametrize("fault", ["cleanup", "uncertain", "auth"])
def test_fatal_remote_failure_stops_next_mp3(env, fault):
    resolver = env.resolver()
    second = add_source(env, 2)
    if fault == "cleanup":
        env.mock.server.delete_status = 500
    elif fault == "uncertain":
        env.mock.server.lose_decode = 0
    else:
        env.mock.userinfo.subject = "different account"
    job = create(env, file_ids=[env.source.stem, second.stem])
    finished = execute(env, job, resolver)
    assert finished.status is FileStatus.FAILED and not finished.batch_completed
    assert finished.files[env.source.stem] is FileStatus.FAILED
    assert finished.files[second.stem] is FileStatus.WAITING
    assert not BundlePaths.final_for(env.source).txt.exists()
    assert len(env.mock.ml.decodes) == {"cleanup": 2, "uncertain": 1, "auth": 0}[fault]


@pytest.mark.parametrize("cancel", [False, True])
def test_stop_cancel_after_clean_file_halts_before_next_file(env, cancel):
    resolver = env.resolver()
    second = add_source(env, 2)
    job = create(env, file_ids=[env.source.stem, second.stem])
    token = CancellationToken()
    def completed(*args):
        (token.request_cancel if cancel else token.request_stop)()
    runner = TranscriptionRunner(env.manager, resolver, file_completed_callback=completed)
    runner.run(job.job_id, token)
    finished = env.manager.get_job(job.job_id)
    assert finished.status is (FileStatus.CANCELLED if cancel else FileStatus.STOPPED)
    assert finished.files[env.source.stem] is FileStatus.DONE
    assert BundlePaths.final_for(env.source).txt.exists()
    assert not BundlePaths.final_for(second).txt.exists()
    assert len(env.mock.ml.decodes) == 2


@pytest.mark.parametrize("cancel", [False, True])
def test_stop_cancel_inside_current_file_clears_cache_and_no_outputs(env, cancel):
    resolver = env.resolver()
    second = add_source(env, 2)
    token = CancellationToken()
    def after_http(method, name, body):
        if method == "PUT" and name.endswith(".mp3"):
            (token.request_cancel if cancel else token.request_stop)()
    env.mock.server.after_http = after_http
    job = create(env, file_ids=[env.source.stem, second.stem])
    finished = execute(env, job, resolver, token)
    assert finished.status is (FileStatus.CANCELLED if cancel else FileStatus.STOPPED)
    assert not BundlePaths.final_for(env.source).txt.exists()
    assert env.mock.ml.decodes == []
    assert not env.created[0].cache._file_dir(env.source).exists()


def test_cancel_with_unresolved_cleanup_is_failed_not_clean_cancel(env):
    resolver = env.resolver()
    second = add_source(env, 2)
    token = CancellationToken()
    env.mock.server.after_send = lambda index: token.request_cancel() if index == 0 else None
    job = create(env, file_ids=[env.source.stem, second.stem])
    finished = execute(env, job, resolver, token)
    assert finished.status is FileStatus.FAILED and not finished.batch_completed
    assert finished.files[second.stem] is FileStatus.WAITING
    assert env.created[0].last_report.cleanup.cleanup_required


@pytest.mark.parametrize("fault", ["no-lease", "not-active", "account"])
def test_unverified_ownership_auth_executes_no_jupyter(env, fault):
    resolver = env.resolver()
    if fault == "no-lease":
        env.mock.owner.close()
    elif fault == "not-active":
        from src.services.colab_runtime_ownership import OwnershipState
        with env.mock.owner.store.transaction():
            env.mock.owner._update(state=OwnershipState.CLEANUP_REQUIRED)
    else:
        env.mock.userinfo.subject = "account-b"
    job = create(env)
    finished = execute(env, job, resolver)
    assert finished.status is FileStatus.FAILED and env.mock.server.calls == []
    assert len(env.mock.ml.decodes) == 0


def test_tokens_proxy_urls_never_persist_or_log_and_request_settings_cannot_activate(env, caplog, capsys):
    resolver = env.resolver()
    caplog.set_level(logging.DEBUG)
    job = create(env, engine_config={"enabled": True, "token": TOKEN, "base_url": URL, "oauth": OAUTH})
    assert job.engine_config == {}
    finished = execute(env, job, resolver)
    assert finished.status is FileStatus.DONE
    captured = capsys.readouterr()
    texts = [caplog.text, captured.out, captured.err, finished.model_dump_json(),
             Path(env.manager.storage_path).read_text(encoding="utf-8")]
    for text in texts:
        assert TOKEN not in text and OAUTH not in text and URL not in text
    assert "한국어 조각" not in caplog.text + captured.out + captured.err


def test_official_credentials_rejected_before_job_creation(env):
    from fastapi import HTTPException
    env.resolver()
    with pytest.raises(HTTPException):
        create(env, colab_url=URL)
    with pytest.raises(ValueError):
        env.manager.create_job(str(env.source.parent), [env.source.stem], engine="official_colab",
                               engine_config={"proxy_token": TOKEN})
    assert env.manager.list_jobs() == []


def test_whole_silence_preserves_existing_writer_rule_issue_238(env):
    resolver = env.resolver()
    before = valid_old_bundle(env.source)
    env.mock.server.silent = {0, 1}
    job = create(env, force_retranscribe=True)
    finished = execute(env, job, resolver)
    assert finished.status is FileStatus.FAILED and finished.failed_files == 1
    assert "TXT" in finished.error
    assert all(path.read_bytes() == data for path, data in before.items())


def test_local_job_still_uses_existing_local_resolver_branch(env):
    class FakeLocal:
        def transcribe(self, source, token, event, progress):
            return TranscriptionResult.from_engine_payload({"text": "로컬 결과", "segments": []})
    resolver = env.resolver(enabled=False)
    resolver._local = FakeLocal()
    job = create(env, engine="local_whisper")
    finished = execute(env, job, resolver)
    assert finished.status is FileStatus.DONE and env.mock.server.calls == []
    assert BundlePaths.final_for(env.source).txt.read_text(encoding="utf-8") == "로컬 결과"


def test_direct_colab_job_still_uses_existing_resolver_and_engine(env, monkeypatch):
    import src.services.transcription_runner as module
    class FakeClient:
        signature = "paired-existing-direct"
        def __init__(self, *args):
            pass
        def check_health(self):
            pass
        def transcribe(self, path):
            return TranscriptionResult.from_engine_payload({"text": "기존 Colab 결과", "segments": []})
    class FakeSplit:
        def split(self, source, seconds, token):
            return [AudioChunk(0, source, 0.0, 1.0)]
        def cleanup(self):
            pass
    monkeypatch.setattr(module, "DirectColabHttpClient", FakeClient)
    monkeypatch.setattr(module, "FFmpegAudioSplitter", FakeSplit)
    resolver = env.resolver(enabled=False)
    resolver._registry = SimpleNamespace(lookup_verified_base_url=lambda _: SimpleNamespace(fingerprint="paired"))
    job = create(env, engine="direct_colab", colab_url="https://existing.trycloudflare.com")
    finished = execute(env, job, resolver)
    assert finished.status is FileStatus.DONE and env.mock.server.calls == []
    assert job.engine_config == {"base_url": "https://existing.trycloudflare.com"}


def test_http_default_off_and_enabled_creation_and_background_run(env, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.services.transcription_runner import BackgroundExecutionService
    resolver = env.resolver(enabled=False)
    app = FastAPI()
    app.include_router(env.routes.router)
    request = dict(folder=str(env.source.parent), file_ids=[env.source.stem],
                   engine="official_colab", course="개념완성", subject="민법", week=1,
                   engine_config={"enabled": True, "token": TOKEN})
    with TestClient(app) as client:
        assert client.post("/jobs", json=request).status_code == 400
        assert env.manager.list_jobs() == []
        resolver = env.resolver(enabled=True)
        runner = TranscriptionRunner(env.manager, resolver)
        service = BackgroundExecutionService(runner)
        monkeypatch.setattr(env.routes, "execution_service", service)
        monkeypatch.setattr(env.routes, "transcription_runner", runner)
        try:
            response = client.post("/jobs", json=request)
            assert response.status_code == 200
            payload = response.json()
            assert payload["engine_config"] == {} and payload["upload_to_drive"] is False
            job_id = payload["job_id"]
            assert client.post(f"/jobs/{job_id}/start").status_code == 202
            assert service.wait_for_quiescence(job_id, timeout=10)
            assert env.manager.get_job(job_id).status is FileStatus.DONE
            OutputBundleValidator().validate(BundlePaths.final_for(env.source))
        finally:
            service._executor.shutdown(wait=True)


def test_preparation_failure_gives_local_choice_but_never_automatically_calls_local(env):
    resolver = env.resolver()
    class ForbiddenLocal:
        def transcribe(self, *args):
            raise AssertionError("No automatic Local execution")
    resolver._local = ForbiddenLocal()
    (env.mock.model_cache / "model.bin").unlink()
    second = add_source(env, 2)
    job = create(env, file_ids=[env.source.stem, second.stem])
    finished = execute(env, job, resolver)
    assert finished.status is FileStatus.FAILED and not finished.batch_completed
    assert "PC 전사를 선택" in finished.error
    assert finished.engine == "official_colab" and finished.files[second.stem] is FileStatus.WAITING
    assert len(env.manager.list_jobs()) == 1 and env.mock.ml.decodes == []
    assert not any(m == "PUT" for m, p in env.mock.server.calls)


def test_unexpected_sensitive_exception_is_sanitized_before_runner_logging(env, caplog, capsys):
    resolver = env.resolver()
    original_factory = resolver._official_colab_pipeline_factory
    def factory(owner, cache):
        pipeline = original_factory(owner, cache)
        def fail(*args):
            raise RuntimeError(TOKEN + URL + OAUTH + "사용자 전사 비밀")
        pipeline.transcribe = fail
        return pipeline
    resolver._official_colab_pipeline_factory = factory
    job = create(env)
    caplog.set_level(logging.DEBUG)
    finished = execute(env, job, resolver)
    assert finished.status is FileStatus.FAILED and not finished.batch_completed
    captured = capsys.readouterr()
    text = caplog.text + captured.out + captured.err + finished.model_dump_json()
    for secret in (TOKEN, URL, OAUTH, "사용자 전사 비밀"):
        assert secret not in text


def test_crash_checkpoint_blocks_job_retry_without_resetting_unresolved_record(env):
    resolver = env.resolver()
    env.mock.server.lose_decode = 0
    job = create(env)
    first = execute(env, job, resolver)
    assert first.status is FileStatus.FAILED
    marker = next((env.created[0].cache.root / ".pipeline-locks").glob("*/attempt.json"))
    previous = marker.read_bytes()
    before = len(env.mock.server.calls)
    env.mock.server.lose_decode = None
    env.manager.mutate_job(job.job_id, lambda j: (
        setattr(j, "status", FileStatus.WAITING), j.files.update({env.source.stem: FileStatus.WAITING})))
    retried = execute(env, job, resolver)
    assert retried.status is FileStatus.FAILED and not retried.batch_completed
    assert len(env.mock.server.calls) == before and marker.read_bytes() == previous


def test_resolver_activation_is_not_persistent_or_shared_with_new_instances(env):
    assert env.resolver().official_colab_enabled
    fresh = DefaultEngineResolver(cache_root=env.root / "job-cache")
    assert not fresh.official_colab_enabled


def test_forged_job_config_is_rejected_by_resolver_without_remote_execution(env):
    resolver = env.resolver()
    job = create(env)
    job.engine_config = {"token": TOKEN, "url": URL}
    with pytest.raises(EngineError) as exc:
        resolver(job)
    assert exc.value.fatal and exc.value.technical_detail is None
    assert env.mock.server.calls == []


def test_server_dependency_creation_error_is_sanitized_at_resolver_boundary(env, caplog):
    resolver = env.resolver()
    def broken(*args):
        raise RuntimeError(TOKEN + URL + OAUTH)
    resolver._official_colab_pipeline_factory = broken
    job = create(env)
    caplog.set_level(logging.DEBUG)
    finished = execute(env, job, resolver)
    assert finished.status is FileStatus.FAILED and not finished.batch_completed
    assert env.mock.server.calls == []
    for secret in (TOKEN, URL, OAUTH):
        assert secret not in caplog.text + finished.model_dump_json()


@pytest.mark.parametrize("fault", ["conflict", "incomplete-model", 401, 403, 429])
def test_upload_ownership_auth_policy_limits_are_fatal_for_job(env, fault):
    resolver = env.resolver()
    second = add_source(env, 2)
    if fault == "conflict":
        env.mock.server.upload_foreign = 0
    else:
        def hook(method, path, body, number):
            if method == "PUT" and path.endswith(".mp3"):
                if fault == "incomplete-model":
                    import base64
                    env.mock.server.contents.files[path] = bytearray(base64.b64decode(body["content"]))
                    return 201, {}
                return fault, None
        env.mock.server.contents.hooks.append(hook)
    job = create(env, file_ids=[env.source.stem, second.stem])
    finished = execute(env, job, resolver)
    assert finished.status is FileStatus.FAILED and not finished.batch_completed
    assert finished.files[second.stem] is FileStatus.WAITING
    assert env.mock.ml.decodes == []
    assert not BundlePaths.final_for(env.source).txt.exists()
    if fault in ("conflict", "incomplete-model"):
        assert not any(m == "DELETE" and p.endswith(".mp3") for m, p in env.mock.server.calls)


def test_bad_middle_file_is_nonfatal_even_after_cpu_path_in_previous_file(env):
    resolver = env.resolver()
    env.mock.ml.cuda = 0
    second = add_source(env, 2)
    third = add_source(env, 3)
    original = env.mock.pipeline
    def pipeline(*args, **kwargs):
        result = original(*args, **kwargs)
        split = result.splitter.split
        def checked(source, seconds, token):
            if source == second:
                raise EngineError("AUDIO_EMPTY", ErrorCategory.INPUT, "bad audio")
            return split(source, seconds, token)
        result.splitter.split = checked
        return result
    env.mock.pipeline = pipeline
    job = create(env, file_ids=[env.source.stem, second.stem, third.stem])
    finished = execute(env, job, resolver)
    assert finished.files[env.source.stem] is FileStatus.DONE
    assert finished.files[second.stem] is FileStatus.FAILED
    assert finished.files[third.stem] is FileStatus.DONE
    assert finished.batch_completed
