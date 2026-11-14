"""PHASE 16 (#245): one-click official Colab launch, Mock E2E only.

Real launcher -> real preflight -> real RuntimeOwnership/RuntimeClient ->
real FullFilePipeline/Runner/Writer, with Google REST, UserInfo, Jupyter and
ML replaced by in-process fakes. External sockets are blocked.
"""

import json
import logging
import socket
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from src.domain.models import FileStatus
from src.domain.transcription import CancellationToken
from src.services.colab_account_verifier import GOOGLE_ISSUER, GoogleAccountVerifier
from src.services.colab_full_file_pipeline import ColabFullFilePipeline
from src.services.colab_inference_worker import MODEL_REVISION
from src.services.colab_launch_preflight import SCOPE_COLAB
from src.services.colab_runtime_client import ColabRuntimeClient
from src.services.colab_runtime_ownership import OwnershipState, OwnershipStore, RuntimeOwnership
from src.services.job_manager import JobManager
from src.services.official_colab_launcher import (
    FailClosedLaunchAuthorizer, LaunchCredentials, OfficialColabLauncher,
)
from src.services.output_bundle import BundlePaths, OutputBundleValidator
from src.services.settings import SettingsManager
from src.services.transcription_runner import (
    BackgroundExecutionService, DefaultEngineResolver, TranscriptionRunner,
)
from test_colab_full_file_pipeline import FullServer, Splitter, UserInfo, ml  # noqa: F401 (fixture)
from test_colab_jupyter_files import TOKEN, URL
from test_colab_runtime_client import OAUTH, PROXY, Server as RuntimeServer

import hashlib


SCOPES = ("openid", SCOPE_COLAB)


def binding(subject):
    return hashlib.sha256((GOOGLE_ISSUER + "\0" + subject).encode()).hexdigest()


@pytest.fixture(autouse=True)
def no_external_network(monkeypatch):
    real_connect = socket.socket.connect

    def denied(*args, **kwargs):
        raise AssertionError("PHASE 16 live network forbidden")

    def loopback_only(sock, address):
        if isinstance(address, tuple) and address[0] in ("127.0.0.1", "::1"):
            return real_connect(sock, address)
        return denied()
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket.socket, "connect", loopback_only)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", denied)


class ApprovingAuthorizer:
    """Test-only stand-in for a future, separately approved live authorizer."""

    def __init__(self):
        self.seen = []

    def static_blockers(self):
        return []

    def authorize(self, preflight):
        self.seen.append(preflight)
        return True


@pytest.fixture
def env(tmp_path, monkeypatch, ml):
    import src.api.routes as routes
    study = tmp_path / "study"
    study.mkdir()
    source = study / "개념완성_민법_1주차_1강.mp3"
    source.write_bytes(b"synthetic full MP3" * 100)
    monkeypatch.chdir(tmp_path)

    original_download = sys.modules["huggingface_hub"].snapshot_download
    model_dir = tmp_path / "model-cache" / MODEL_REVISION
    model_dir.mkdir(parents=True)
    for name in ("model.bin", "config.json", "tokenizer.json", "preprocessor_config.json"):
        (model_dir / name).write_bytes(b"fake model file")

    def cached_model(*args, **kwargs):
        original_download(*args, **kwargs)
        return str(model_dir)
    monkeypatch.setattr(sys.modules["huggingface_hub"], "snapshot_download", cached_model)

    userinfo = UserInfo()
    runtime = RuntimeServer()
    original_payload = runtime.runtime

    def runtime_payload():
        payload = original_payload()
        payload["connectionInfo"]["url"] = URL
        return payload
    runtime.runtime = runtime_payload
    faults = SimpleNamespace(delete_status=None, create_status=None)

    def handle(request):
        if request.method == "DELETE" and faults.delete_status:
            runtime.calls.append(request)
            return httpx.Response(faults.delete_status, json={"error": {"code": faults.delete_status}})
        if request.method == "POST" and faults.create_status:
            runtime.calls.append(request)
            return httpx.Response(faults.create_status, json={"error": {"code": faults.create_status}})
        return runtime.handle(request)

    server = FullServer(ml)
    original_http = server.http

    def http(method, url, headers, body, timeout):
        if method == "POST" and url.endswith("/api/kernels"):
            server.ws.namespace = {}
            server.ws.frames = []
        return original_http(method, url, headers, body, timeout)

    store = OwnershipStore(tmp_path / "ownership")
    owners, pipelines = [], []
    durations = {"value": (300.0, 12.0)}

    def ownership_factory(store_, credentials):
        client = ColabRuntimeClient(credentials.access_token, transport=httpx.MockTransport(handle),
                                    account_verifier=GoogleAccountVerifier(opener=userinfo),
                                    sleep=lambda _: None)
        owner = RuntimeOwnership(store_, client)
        owners.append(owner)
        return owner

    def pipeline_factory(ownership, cache):
        splitter = Splitter(tmp_path / f"split-{len(pipelines)}", durations["value"])
        pipeline = ColabFullFilePipeline(ownership, cache, splitter=splitter,
                                         http_request=http, ws_connect=server.connect)
        pipelines.append(pipeline)
        return pipeline

    manager = JobManager(str(tmp_path / "job-state" / "jobs.json"))
    monkeypatch.setattr(routes, "job_manager", manager)
    monkeypatch.setattr(routes, "settings_manager", SettingsManager(tmp_path / "job-state" / "settings.json"))
    credentials = {"value": LaunchCredentials(OAUTH, SCOPES)}
    launch_errors = []

    def install(authorizer=None, connected=True):
        launcher = OfficialColabLauncher(
            credential_provider=lambda: credentials["value"] if connected else None,
            ownership_store=store, ownership_factory=ownership_factory,
            authorizer=authorizer if authorizer is not None else ApprovingAuthorizer(),
            pipeline_factory=pipeline_factory, cache_root=tmp_path / "official-cache",
            preflight_options={"colab_transport": httpx.MockTransport(handle), "userinfo_opener": userinfo})
        original_launch = launcher.launch

        def recording_launch():
            try:
                return original_launch()
            except Exception as exc:
                launch_errors.append(getattr(exc, "code", type(exc).__name__))
                raise
        launcher.launch = recording_launch
        resolver = DefaultEngineResolver(cache_root=tmp_path / "job-cache", official_colab_launcher=launcher)
        monkeypatch.setattr(routes, "engine_resolver", resolver)
        return resolver

    yield SimpleNamespace(routes=routes, manager=manager, source=source, study=study, store=store,
                          runtime=runtime, server=server, ml=ml, userinfo=userinfo, owners=owners,
                          pipelines=pipelines, durations=durations, faults=faults, install=install,
                          credentials=credentials, root=tmp_path, launch_errors=launch_errors)
    for owner in owners:
        owner.close()
        owner.client.close()


def request_body(env, **overrides):
    values = dict(folder=str(env.study), engine="official_colab", scope="selected",
                  file_ids=[env.source.stem], course="개념완성", subject="민법", week=1)
    values.update(overrides)
    return values


def create(env, **overrides):
    return env.routes.create_job(env.routes.CreateJobRequest(**request_body(env, **overrides)))


def run(env, job, token=None, resolver=None):
    runner = TranscriptionRunner(env.manager, resolver or env.routes.engine_resolver)
    runner.run(job.job_id, token or CancellationToken())
    return env.manager.get_job(job.job_id)


def failed_with(env, job):
    """The Job failed and the launcher refused with exactly this code."""
    assert job.status is FileStatus.FAILED and not job.batch_completed and job.error
    return env.launch_errors[-1] if env.launch_errors else None


def posts(env):
    return [r for r in env.runtime.calls if r.method == "POST" and r.url.path == "/v1beta/runtimes"]


def deletes(env):
    return [r for r in env.runtime.calls if r.method == "DELETE"]


def forged(env):
    """A Job that bypassed the API (e.g. persisted earlier): the launcher must still gate it."""
    return env.manager.create_job(str(env.study), [env.source.stem], engine="official_colab")


def add_source(env, lesson):
    path = env.study / f"개념완성_민법_1주차_{lesson}강.mp3"
    path.write_bytes(b"mock MP3 source" * 100)
    return path


def records(env):
    return env.store.load()


# 1. Default OFF ---------------------------------------------------------------

def test_default_production_resolver_is_off_with_reasons_and_no_job(env, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    monkeypatch.setattr(env.routes, "engine_resolver", DefaultEngineResolver(cache_root=env.root / "c"))
    app = FastAPI()
    app.include_router(env.routes.router)
    with TestClient(app) as client:
        status = client.get("/engines/official-colab/status").json()
        assert status["state"] == "DISABLED" and status["available"] is False
        codes = [reason["code"] for reason in status["reasons"]]
        assert codes == ["FEATURE_DISABLED", "COST_GATE_CONDITIONAL", "POLICY_GATE_NOT_VERIFIED"]
        assert all(reason["message"] for reason in status["reasons"])
        assert client.post("/jobs", json=request_body(env)).status_code == 400
    assert env.manager.list_jobs() == [] and env.runtime.calls == [] and env.userinfo.calls == 0


# 2. Fail-closed default authorizer: zero network, zero Runtime -----------------

def test_fail_closed_authorizer_blocks_status_creation_and_forged_jobs_without_network(env):
    env.install(authorizer=FailClosedLaunchAuthorizer())
    status = env.routes.official_colab_status()
    assert status["state"] == "BLOCKED" and not status["available"]
    assert [r["code"] for r in status["reasons"]] == ["COST_GATE_CONDITIONAL", "POLICY_GATE_NOT_VERIFIED"]
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        create(env)
    assert exc.value.status_code == 400
    assert exc.value.detail.startswith("공식 Colab 자동 연결을 지금 사용할 수 없습니다.")
    finished = run(env, forged(env))
    assert finished.status is FileStatus.FAILED
    assert failed_with(env, finished) == "OFFICIAL_COLAB_LAUNCH_BLOCKED"
    assert env.runtime.calls == [] and env.userinfo.calls == 0 and env.server.calls == []
    assert records(env) == []


@pytest.mark.parametrize("forged_fields", [
    {"colab_url": "https://example.invalid"},
    {"engine_config": {"approved": True, "token": TOKEN}},
    {"official_colab_enabled": True, "launch_approval": "GO", "cost_gate": "VERIFIED"},
])
def test_client_fields_cannot_bypass_launch_gate(env, forged_fields):
    from fastapi import HTTPException
    env.install(authorizer=FailClosedLaunchAuthorizer())
    with pytest.raises(HTTPException) as exc:
        create(env, **forged_fields)
    assert exc.value.status_code == 400
    assert env.manager.list_jobs() == [] and env.runtime.calls == []


def test_settings_cannot_enable_or_approve(env):
    env.install(authorizer=FailClosedLaunchAuthorizer())
    current = env.routes.settings_manager.get()
    assert current.last_engine in ("local_whisper", "direct_colab")
    assert env.routes.official_colab_status()["available"] is False


# 3-6. Approved Mock: one click to saved bundle ---------------------------------

def test_one_click_http_create_start_done_bundle_and_owned_runtime_cleanup(env, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    resolver = env.install()
    runner = TranscriptionRunner(env.manager, resolver)
    service = BackgroundExecutionService(runner)
    monkeypatch.setattr(env.routes, "execution_service", service)
    monkeypatch.setattr(env.routes, "transcription_runner", runner)
    app = FastAPI()
    app.include_router(env.routes.router)
    try:
        with TestClient(app) as client:
            status = client.get("/engines/official-colab/status").json()
            assert status == {"state": "READY", "available": True, "reasons": []}
            response = client.post("/jobs", json=request_body(env))
            assert response.status_code == 200
            payload = response.json()
            assert payload["engine_config"] == {} and payload["upload_to_drive"] is False
            assert client.post(f"/jobs/{payload['job_id']}/start").status_code == 202
            assert service.wait_for_quiescence(payload["job_id"], timeout=15)
            finished = env.manager.get_job(payload["job_id"])
    finally:
        service._executor.shutdown(wait=True)
    assert finished.status is FileStatus.DONE and finished.batch_completed
    paths = BundlePaths.final_for(env.source)
    OutputBundleValidator().validate(paths)
    assert paths.txt.read_text(encoding="utf-8") == "한국어 조각 0\n한국어 조각 1"
    assert json.loads(paths.json.read_text(encoding="utf-8"))["segments"][1]["start"] == 300.2
    assert "00:05:00,200" in paths.srt.read_text(encoding="utf-8")
    assert len(posts(env)) == 1 and len(deletes(env)) == 1
    assert [r.state for r in records(env)] == [OwnershipState.CLEANED]


def test_short_mp3_single_chunk(env):
    env.install()
    env.durations["value"] = (42.0,)
    finished = run(env, create(env))
    assert finished.status is FileStatus.DONE
    assert BundlePaths.final_for(env.source).txt.read_text(encoding="utf-8") == "한국어 조각 0"
    assert len(env.ml.decodes) == 1 and len(posts(env)) == 1 and len(deletes(env)) == 1


def test_long_mp3_multi_chunk_merge(env):
    env.install()
    env.durations["value"] = (300.0, 300.0, 300.0, 45.0)
    finished = run(env, create(env))
    assert finished.status is FileStatus.DONE
    paths = BundlePaths.final_for(env.source)
    OutputBundleValidator().validate(paths)
    segments = json.loads(paths.json.read_text(encoding="utf-8"))["segments"]
    assert [s["start"] for s in segments] == [0.2, 300.2, 600.2, 900.2]
    assert len(env.ml.decodes) == 4 and len(env.ml.loads) == 1


def test_multiple_files_share_one_owned_runtime_and_clean_once(env):
    env.install()
    second = add_source(env, 2)
    finished = run(env, create(env, file_ids=[env.source.stem, second.stem]))
    assert finished.status is FileStatus.DONE and finished.done_files == 2
    assert len(posts(env)) == 1 and len(deletes(env)) == 1


# 7. Verified silence ------------------------------------------------------------

def test_whole_silence_completes_with_empty_bundle(env):
    env.install()
    env.server.silent = {0, 1}
    finished = run(env, create(env))
    assert finished.status is FileStatus.DONE
    paths = BundlePaths.final_for(env.source)
    assert paths.txt.read_bytes() == paths.srt.read_bytes() == b""
    assert json.loads(paths.json.read_text(encoding="utf-8"))["sorigul_silence"]["scope"] == "file"


# 8. STOP / CANCEL -----------------------------------------------------------------

@pytest.mark.parametrize("cancel", [False, True])
def test_stop_cancel_mid_file_saves_nothing_and_deletes_owned_runtime(env, cancel):
    env.install()
    token = CancellationToken()

    def after_http(method, name, body):
        if method == "PUT" and name.endswith(".mp3"):
            (token.request_cancel if cancel else token.request_stop)()
    env.server.after_http = after_http
    finished = run(env, create(env), token)
    assert finished.status is (FileStatus.CANCELLED if cancel else FileStatus.STOPPED)
    assert not BundlePaths.final_for(env.source).txt.exists()
    assert len(deletes(env)) == 1 and [r.state for r in records(env)] == [OwnershipState.CLEANED]


# 9. Failure and retry protection --------------------------------------------------

def test_cleanup_failure_marks_job_failed_and_blocks_next_launch_without_second_post(env):
    env.install()
    env.faults.delete_status = 500
    first = run(env, create(env))
    assert first.status is FileStatus.FAILED and not first.batch_completed
    assert any("원격 작업 정리" in e.message for e in first.events)
    status = env.routes.official_colab_status()
    assert [r["code"] for r in status["reasons"]] == ["OWNERSHIP_UNRESOLVED"]
    calls_before = len(env.runtime.calls)
    second = run(env, forged(env))
    assert second.status is FileStatus.FAILED and failed_with(env, second) == "OFFICIAL_COLAB_OWNERSHIP_UNRESOLVED"
    assert len(posts(env)) == 1 and len(env.runtime.calls) == calls_before


@pytest.mark.parametrize("status_code, error", [
    (429, "OFFICIAL_COLAB_LIMITED"), (403, "OFFICIAL_COLAB_AUTH_REQUIRED"),
])
def test_rejected_create_fails_without_jupyter_and_allows_local_choice(env, status_code, error):
    env.install()
    env.faults.create_status = status_code
    finished = run(env, create(env))
    assert finished.status is FileStatus.FAILED and failed_with(env, finished) == error
    assert "PC 전사를 선택할 수 있습니다" in finished.error
    assert env.server.calls == [] and env.ml.decodes == []
    assert [r.state for r in records(env)] == [OwnershipState.BLOCKED]


def test_failed_file_retry_requires_new_job_and_new_owned_runtime(env):
    env.install()
    env.server.fail_decode = 1
    first = run(env, create(env))
    assert first.status is FileStatus.FAILED
    assert not BundlePaths.final_for(env.source).txt.exists()
    env.server.fail_decode = None
    second = run(env, create(env))
    assert second.status is FileStatus.DONE
    assert len(posts(env)) == 2 and len(deletes(env)) == 2


# 10-11. Ownership / account -------------------------------------------------------

def test_unresolved_prior_ownership_blocks_before_any_network(env):
    env.install()
    client = ColabRuntimeClient(OAUTH, transport=httpx.MockTransport(env.runtime.handle),
                                account_verifier=GoogleAccountVerifier(opener=env.userinfo))
    stale = RuntimeOwnership(env.store, client)
    stale.create()
    stale.close()
    client.close()
    calls = len(env.runtime.calls)
    userinfo_calls = env.userinfo.calls
    assert env.routes.official_colab_status()["reasons"][0]["code"] == "OWNERSHIP_UNRESOLVED"
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        create(env)
    finished = run(env, forged(env))
    assert failed_with(env, finished) == "OFFICIAL_COLAB_OWNERSHIP_UNRESOLVED"
    assert len(env.runtime.calls) == calls and env.userinfo.calls == userinfo_calls


def test_corrupt_ownership_storage_is_never_treated_as_clean(env):
    env.install()
    env.store.root.mkdir(parents=True, exist_ok=True)
    (env.store.root / "00000000-0000-4000-8000-000000000000.json").write_text("{corrupt", encoding="utf-8")
    assert "OWNERSHIP_UNRESOLVED" in [r["code"] for r in env.routes.official_colab_status()["reasons"]]
    assert failed_with(env, run(env, forged(env))) == "OFFICIAL_COLAB_OWNERSHIP_UNRESOLVED"
    assert env.runtime.calls == []


def test_account_mismatch_blocks_before_runtime_post(env):
    env.install()
    env.credentials["value"] = LaunchCredentials(OAUTH, SCOPES, expected_account_binding=binding("account-b"))
    finished = run(env, create(env))
    assert failed_with(env, finished) == "OFFICIAL_COLAB_ACCOUNT_MISMATCH"
    assert posts(env) == [] and records(env) == []


def test_account_switch_between_preflight_and_runtime_client_blocks_post(env):
    authorizer = ApprovingAuthorizer()
    env.install(authorizer=authorizer)
    original = authorizer.authorize

    def switch(preflight):
        env.userinfo.subject = "account-b"
        return original(preflight)
    authorizer.authorize = switch
    finished = run(env, create(env))
    assert failed_with(env, finished) == "OFFICIAL_COLAB_ACCOUNT_MISMATCH" and posts(env) == []


def test_not_connected_and_paid_tier_block_without_post(env):
    env.install(connected=False)
    assert "ACCOUNT_NOT_CONNECTED" in [r["code"] for r in env.routes.official_colab_status()["reasons"]]
    assert failed_with(env, run(env, forged(env))) == "OFFICIAL_COLAB_AUTH_REQUIRED"
    env.install()
    env.runtime.subscription = {"name": "subscription", "tier": "SUBSCRIPTION_TIER_PRO"}
    assert failed_with(env, run(env, forged(env))) == "OFFICIAL_COLAB_PAID_TIER"
    env.runtime.subscription = {"name": "subscription", "tier": "SUBSCRIPTION_TIER_FREE"}
    env.runtime.specs = {"runtimeSpecs": []}
    assert failed_with(env, run(env, forged(env))) == "OFFICIAL_COLAB_RESOURCE_UNAVAILABLE"
    assert posts(env) == []


def test_drive_token_credentials_are_refused(env):
    env.install()
    env.credentials["value"] = LaunchCredentials(OAUTH, SCOPES + ("https://www.googleapis.com/auth/drive.file",))
    assert failed_with(env, run(env, forged(env))) == "OFFICIAL_COLAB_AUTH_REQUIRED"
    assert env.runtime.calls == [] and env.userinfo.calls == 0


# 12. Drive selection ---------------------------------------------------------------

def test_drive_default_off_and_explicit_choice_kept_on_job(env):
    env.install()
    assert create(env).upload_to_drive is False
    assert create(env, upload_to_drive=True).upload_to_drive is True


# 13. Local / DirectColab unaffected by an installed launcher -------------------------

def test_launcher_does_not_change_local_or_direct_colab_resolution(env):
    from src.domain.transcription import EngineError
    resolver = env.install()
    local = env.manager.create_job(str(env.study), [env.source.stem], engine="local_whisper")
    assert resolver(local) is resolver._local
    direct = env.manager.create_job(str(env.study), [env.source.stem], engine="direct_colab")
    with pytest.raises(EngineError) as exc:
        resolver(direct)
    assert exc.value.code == "COLAB_URL_MISSING"
    assert env.runtime.calls == []


# 14. Sensitive data -----------------------------------------------------------------

def test_tokens_accounts_runtime_and_proxy_never_persist_log_or_surface(env, caplog, capsys):
    caplog.set_level(logging.DEBUG)
    env.install()
    job = create(env)
    finished = run(env, job)
    assert finished.status is FileStatus.DONE
    runtime_name = posts(env)[0].url.params["runtimeId"]
    jobs_file = Path(env.manager.storage_path).read_text(encoding="utf-8")
    status_text = json.dumps(env.routes.official_colab_status())
    captured = capsys.readouterr()
    surfaces = [jobs_file, status_text, caplog.text, captured.out, captured.err,
                repr(env.credentials["value"])]
    for secret in (OAUTH, PROXY, TOKEN, URL, binding("account-a"), "account-a"):
        for surface in surfaces:
            assert secret not in surface
    assert runtime_name not in jobs_file and runtime_name not in status_text
    assert "official_colab" not in status_text
