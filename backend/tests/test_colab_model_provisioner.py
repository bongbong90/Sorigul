"""PHASE 17: execute trusted remote source with fake ML/pip/Hub, sockets denied."""

import ast
import importlib.metadata
import json
import os
import socket
import subprocess
import sys
from types import SimpleNamespace

import httpx
import pytest

from src.domain.models import FileStatus
from src.domain.transcription import CancellationToken
from src.services.colab_full_file_pipeline import PipelineError
from src.services.colab_inference_worker import MODEL_REPOSITORY, MODEL_REVISION, PACKAGES
from src.services.colab_model_provisioner import (
    ColabModelProvisioner, FailClosedProvisioningAuthorizer, ProvisionState, build_provisioning_code,
)
from src.services.colab_jupyter_inference import InferenceCode, InferenceError
from src.services.colab_runtime_ownership import OwnershipState
from src.services.output_bundle import BundlePaths, OutputBundleValidator
from test_colab_full_file_pipeline import setup, ml, run as pipeline_run  # noqa: F401
from test_official_colab_desktop_launch import (
    env, create, run as job_run, deletes, posts, records,  # noqa: F401
)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("PHASE 17 external sockets forbidden")
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", denied)


class Approve:
    def authorize(self, owned):
        return True


@pytest.fixture
def remote(monkeypatch, tmp_path, ml):
    versions = dict(PACKAGES)
    path = tmp_path / "model-cache" / MODEL_REVISION
    state = SimpleNamespace(versions=versions, path=path, installs=[], downloads=[],
                            install_fail=False, version_fail=False, download_fail=False,
                            partial=False, wrong_revision=False, gpu=True)
    def version(package):
        if package not in versions:
            raise importlib.metadata.PackageNotFoundError(package)
        return versions[package]
    monkeypatch.setattr(importlib.metadata, "version", version)
    for name, package in (("faster_whisper", "faster-whisper"), ("ctranslate2", "ctranslate2"),
                          ("huggingface_hub", "huggingface-hub")):
        monkeypatch.setattr(sys.modules[name], "__version__", PACKAGES[package], raising=False)

    def fake_run(args, **kwargs):
        if args[0] == "nvidia-smi":
            if not state.gpu:
                raise subprocess.CalledProcessError(1, args)
            return SimpleNamespace(stdout=b"Tesla T4\n")
        assert args[:3] == [sys.executable, "-m", "pip"]
        assert kwargs["env"]["PIP_CONFIG_FILE"] == os.devnull
        assert not any(k.startswith("PIP_") and k != "PIP_CONFIG_FILE" for k in kwargs["env"])
        assert "--isolated" in args and args[args.index("--index-url") + 1] == "https://pypi.org/simple"
        targets = args[args.index("https://pypi.org/simple") + 1:]
        assert set(targets) <= {p + "==" + v for p, v in PACKAGES.items()}
        state.installs.append(targets)
        if state.install_fail:
            raise RuntimeError("SECRET_TOKEN raw package exception")
        if not state.version_fail:
            versions.update(dict(p.split("==") for p in targets))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(subprocess, "run", fake_run)

    def download(repo, **kwargs):
        assert repo == MODEL_REPOSITORY and kwargs["revision"] == MODEL_REVISION
        if not kwargs["local_files_only"]:
            state.downloads.append(kwargs)
            if state.download_fail:
                raise OSError("SECRET_TOKEN lost network")
            path.mkdir(parents=True, exist_ok=True)
            for name in ("model.bin", "config.json", "tokenizer.json", "preprocessor_config.json"):
                if not state.partial or name != "model.bin":
                    (path / name).write_bytes(b"synthetic model")
        if not path.exists():
            raise FileNotFoundError()
        return str(path.with_name("wrong-revision") if state.wrong_revision else path)
    monkeypatch.setattr(sys.modules["huggingface_hub"], "snapshot_download", download)
    return state


def actions(server):
    result = []
    for message in server.ws.sent:
        code = message["content"]["code"]
        if "_sorigul_receipt = _sorigul_provision(" in code:
            result.append(ast.literal_eval(ast.parse(code).body[-1].value.args[0])["action"])
    return result


def missing_model(remote):
    if remote.path.exists():
        (remote.path / "model.bin").unlink(missing_ok=True)


@pytest.mark.parametrize("packages,model", [(False, False), (True, False), (False, True), (True, True)])
def test_full_provisioning_then_readonly_prepare_decode_and_cleanup(setup, remote, packages, model):
    if packages:
        remote.versions.clear()
    if model:
        missing_model(remote)
    events = []
    pipeline = setup.pipeline()
    pipeline._provisioning_authorizer = Approve()
    pipeline._provisioning_event = events.append
    result = pipeline_run(setup, pipeline)
    assert result.text == "한국어 조각 0\n한국어 조각 1"
    assert actions(setup.server) == ["CHECK"] + (["INSTALL"] if packages else []) + (["DOWNLOAD"] if model else []) + ["VERIFY"]
    assert len(remote.installs) == int(packages) and len(remote.downloads) == int(model)
    assert events[-1]["state"] == "READY" and all(set(e) == {"kind", "state", "message"} for e in events)
    assert pipeline.provisioning_report["revision"] == MODEL_REVISION
    assert len(setup.ml.loads) == 1  # verification-loaded CUDA model reused for both chunks
    assert len([c for c in setup.server.calls if c == ("POST", "/api/kernels")]) == 1
    assert sum("_sorigul_receipt = _sorigul_prepare(" in m["content"]["code"] for m in setup.server.ws.sent) == 1
    assert pipeline.last_report.status == "COMPLETED" and not pipeline.last_report.cleanup.cleanup_required
    for path, content in setup.outputs.items():
        assert path.read_bytes() == content


def test_only_mismatched_packages_installed(setup, remote):
    remote.versions["ctranslate2"] = "wrong"
    pipeline = setup.pipeline()
    pipeline._provisioning_authorizer = Approve()
    pipeline_run(setup, pipeline)
    assert remote.installs == [["ctranslate2==4.6.0"]]


@pytest.mark.parametrize("fault,expected", [
    ("install_fail", "PACKAGE_INSTALL_FAILED"),
    ("version_fail", "PACKAGE_VERSION_MISMATCH"),
    ("download_fail", "MODEL_DOWNLOAD_FAILED"),
    ("partial", "MODEL_CACHE_INCOMPLETE"),
    ("wrong_revision", "MODEL_REVISION_MISMATCH"),
    ("gpu", "GPU_UNAVAILABLE"),
    ("load_fail", "MODEL_LOAD_FAILED"),
    ("import_fail", "PACKAGE_IMPORT_FAILED"),
])
def test_failures_no_upload_no_decode_no_retry(setup, remote, monkeypatch, fault, expected, caplog):
    if fault in ("install_fail", "version_fail"):
        remote.versions.clear()
    if fault in ("download_fail", "partial"):
        missing_model(remote)
    if fault == "load_fail":
        setup.ml.load_fail = True
    elif fault == "import_fail":
        monkeypatch.setitem(sys.modules, "faster_whisper", None)
    else:
        setattr(remote, fault, False if fault == "gpu" else True)
    pipeline = setup.pipeline()
    pipeline._provisioning_authorizer = Approve()
    with pytest.raises(PipelineError) as exc:
        pipeline_run(setup, pipeline)
    assert exc.value.code == expected
    assert not setup.ml.decodes and len(remote.installs) <= 1 and len(remote.downloads) <= 1
    assert not any(m == "PUT" for m, p in setup.server.calls)
    assert "SECRET_TOKEN" not in caplog.text + str(pipeline.last_report)
    for path, content in setup.outputs.items():
        assert path.read_bytes() == content


def test_no_approval_zero_remote_commands(setup, remote):
    pipeline = setup.pipeline()
    pipeline._provisioning_authorizer = FailClosedProvisioningAuthorizer()
    with pytest.raises(PipelineError) as exc:
        pipeline_run(setup, pipeline)
    assert exc.value.code == "PROVISIONING_NOT_APPROVED"
    assert actions(setup.server) == [] and not remote.installs and not remote.downloads


@pytest.mark.parametrize("change", ["account", "record"])
def test_binding_mismatch_zero_install_or_download(setup, remote, change):
    if change == "account":
        setup.userinfo.subject = "other-account"
    else:
        setup.owner._record = None
    pipeline = setup.pipeline()
    pipeline._provisioning_authorizer = Approve()
    with pytest.raises(PipelineError):
        pipeline_run(setup, pipeline)
    assert not actions(setup.server) and not remote.installs and not remote.downloads


@pytest.mark.parametrize("cancel", [False, True])
@pytest.mark.parametrize("stage", ["INSTALL", "DOWNLOAD"])
def test_stop_cancel_during_provisioning_is_uncertain_and_blocks_retry(setup, remote, cancel, stage):
    remote.versions.clear()
    missing_model(remote)
    token = CancellationToken()
    def after_send(index):
        if actions(setup.server)[-1] == stage:
            token.request_cancel() if cancel else token.request_stop()
    setup.server.after_send = after_send
    pipeline = setup.pipeline()
    pipeline._provisioning_authorizer = Approve()
    from src.domain.transcription import CancelRequested, StopRequested
    with pytest.raises(CancelRequested if cancel else StopRequested):
        pipeline_run(setup, pipeline, token)
    assert "REMOTE_STATE_UNCERTAIN" in pipeline.last_report.signals
    assert not setup.ml.decodes
    before = list(actions(setup.server))
    with pytest.raises(PipelineError) as exc:
        pipeline_run(setup, pipeline)
    assert exc.value.code == "PRIOR_EXECUTION_UNRESOLVED" and actions(setup.server) == before


@pytest.mark.parametrize("stage", ["CHECK", "INSTALL", "DOWNLOAD", "VERIFY"])
def test_lost_remote_response_is_never_retried(setup, remote, stage):
    remote.versions.clear()
    missing_model(remote)
    original_recv = setup.server.ws.recv
    def recv(timeout):
        if actions(setup.server) and actions(setup.server)[-1] == stage:
            raise OSError("SECRET_TOKEN unknown kernel response")
        return original_recv(timeout)
    setup.server.ws.recv = recv
    pipeline = setup.pipeline()
    pipeline._provisioning_authorizer = Approve()
    with pytest.raises(PipelineError) as exc:
        pipeline_run(setup, pipeline)
    assert exc.value.code == "STATE_UNCERTAIN" and "REMOTE_STATE_UNCERTAIN" in pipeline.last_report.signals
    assert actions(setup.server).count(stage) == 1 and not setup.ml.decodes


def test_server_authorized_launcher_to_saved_bundle(env, remote):
    remote.versions.clear()
    missing_model(remote)
    events = []
    env.install(provisioning_authorizer=Approve(), provisioning_event=events.append)
    finished = job_run(env, create(env))
    assert finished.status is FileStatus.DONE and finished.batch_completed
    paths = BundlePaths.final_for(env.source)
    OutputBundleValidator().validate(paths)
    assert paths.txt.read_text(encoding="utf-8") == "한국어 조각 0\n한국어 조각 1"
    assert "00:05:00,200" in paths.srt.read_text(encoding="utf-8")
    assert json.loads(paths.json.read_text(encoding="utf-8"))["segments"][1]["start"] == 300.2
    assert len(posts(env)) == len(deletes(env)) == 1 and records(env)[0].state is OwnershipState.CLEANED
    assert len(remote.installs) == len(remote.downloads) == 1 and events[-1]["state"] == "READY"
    assert "SECRET_TOKEN" not in str(finished)


@pytest.mark.parametrize("fail_provisioning", [False, True])
def test_runtime_delete_failure_keeps_owned_record_and_preserves_bundle(env, remote, fail_provisioning):
    remote.versions.clear()
    remote.install_fail = fail_provisioning
    env.faults.delete_status = 503
    env.install(provisioning_authorizer=Approve())
    finished = job_run(env, create(env))
    assert finished.status is FileStatus.FAILED and not finished.batch_completed
    assert records(env)[0].state is not OwnershipState.CLEANED
    if not fail_provisioning:
        OutputBundleValidator().validate(BundlePaths.final_for(env.source))


def test_provisioner_and_executor_cannot_repeat_attempt(setup, remote, monkeypatch):
    from src.services.colab_jupyter_inference import ColabJupyterInference
    from src.services.colab_jupyter_files import ColabJupyterFileTransfer
    from src.services.colab_full_file_pipeline import _BoundRuntime
    runtime = _BoundRuntime(setup.owner)
    info = runtime.get_owned_runtime().connection_info
    transfer = ColabJupyterFileTransfer(info, http_request=setup.server.http)
    inference = ColabJupyterInference(runtime, transfer, reuse_kernel=True,
        http_request=setup.server.http, ws_connect=setup.server.connect)
    provisioner = ColabModelProvisioner(inference, authorizer=Approve())
    try:
        provisioner.run()
        with pytest.raises(InferenceError) as exc:
            provisioner.run()
        assert exc.value.code is InferenceCode.DUPLICATE_EXECUTION
        with pytest.raises(InferenceError):
            inference.provision_step("INSTALL")  # no server approval, even direct internal call
        assert remote.installs == []
        with pytest.raises(InferenceError):
            inference.provision_step("CHECK", authorizer=Approve())
        assert actions(setup.server) == ["CHECK", "VERIFY"]
    finally:
        inference.cleanup()


@pytest.mark.parametrize("action", ["pip install evil", "https://evil.invalid", "", None])
def test_no_caller_commands_or_urls(action):
    with pytest.raises(ValueError):
        build_provisioning_code("a" * 32, action)


def test_authorization_revoked_before_install_is_fail_closed(setup, remote):
    remote.versions.clear()
    class Revoked:
        allowed = True
        def authorize(self, owned):
            return self.allowed
    auth = Revoked()
    setup.server.after_send = lambda index: setattr(auth, "allowed", False)
    pipeline = setup.pipeline()
    pipeline._provisioning_authorizer = auth
    with pytest.raises(PipelineError) as exc:
        pipeline_run(setup, pipeline)
    assert exc.value.code == "PROVISIONING_NOT_APPROVED"
    assert actions(setup.server) == ["CHECK"] and not remote.installs


def test_stale_import_version_is_rejected(setup, remote, monkeypatch):
    monkeypatch.setattr(sys.modules["ctranslate2"], "__version__", "wrong")
    pipeline = setup.pipeline()
    pipeline._provisioning_authorizer = Approve()
    with pytest.raises(PipelineError) as exc:
        pipeline_run(setup, pipeline)
    assert exc.value.code == "PACKAGE_IMPORT_FAILED" and not setup.ml.decodes


def test_incomplete_marker_is_never_ready(setup, remote):
    (remote.path / "model.bin.incomplete").write_bytes(b"partial")
    pipeline = setup.pipeline()
    pipeline._provisioning_authorizer = Approve()
    with pytest.raises(PipelineError) as exc:
        pipeline_run(setup, pipeline)
    assert exc.value.code == "MODEL_CACHE_INCOMPLETE" and not setup.ml.decodes


@pytest.mark.parametrize("lost_kernel", [True, False])
def test_kernel_create_uncertainty_or_delete_failure_blocks_clean_completion(setup, remote, lost_kernel):
    setup.server.create_error = lost_kernel
    setup.server.delete_status = 503
    pipeline = setup.pipeline()
    pipeline._provisioning_authorizer = Approve()
    with pytest.raises(PipelineError):
        pipeline_run(setup, pipeline)
    assert pipeline.last_report.cleanup.cleanup_required
    if lost_kernel:
        assert "REMOTE_STATE_UNCERTAIN" in pipeline.last_report.signals
    assert pipeline.last_report.status != "COMPLETED"


@pytest.mark.parametrize("bad_receipt", ["revision", "action", "missing", "error_code"])
def test_malformed_or_mismatched_receipt_blocks_transcription(setup, remote, bad_receipt):
    def corrupt(index):
        if actions(setup.server) == ["CHECK"]:
            frame = json.loads(setup.server.ws.frames[0])
            data = frame["content"]["user_expressions"]["receipt"]["data"]
            receipt = json.loads(ast.literal_eval(data["text/plain"]))
            receipt[bad_receipt] = ["arbitrary"] if bad_receipt == "missing" else "SECRET_TOKEN"
            data["text/plain"] = repr(json.dumps(receipt))
            setup.server.ws.frames[0] = json.dumps(frame)
    setup.server.after_send = corrupt
    pipeline = setup.pipeline()
    pipeline._provisioning_authorizer = Approve()
    with pytest.raises(PipelineError) as exc:
        pipeline_run(setup, pipeline)
    assert exc.value.code == "STATE_UNCERTAIN"
    assert "REMOTE_STATE_UNCERTAIN" in pipeline.last_report.signals and not setup.ml.decodes


def test_gpu_loss_after_preparation_never_decodes_on_cpu(setup, remote):
    # Once read-only preparation has replied, lose CUDA before the first decode.
    def after_send(index):
        if index is None and "_sorigul_receipt = _sorigul_prepare(" in setup.server.ws.sent[-1]["content"]["code"]:
            setup.ml.cuda = 0
    setup.server.after_send = after_send
    pipeline = setup.pipeline()
    pipeline._provisioning_authorizer = Approve()
    with pytest.raises(PipelineError) as exc:
        pipeline_run(setup, pipeline)
    assert exc.value.code == "GPU_UNAVAILABLE" and not setup.ml.decodes
    assert all(options["device"] == "cuda" for path, options in setup.ml.loads)


@pytest.mark.parametrize("cancel", [True, False])
def test_job_stop_cancel_during_preparation_closes_owned_runtime(env, remote, cancel):
    remote.versions.clear()
    token = CancellationToken()
    def after_send(index):
        if actions(env.server)[-1] == "INSTALL":
            (token.request_cancel if cancel else token.request_stop)()
    env.server.after_send = after_send
    env.install(provisioning_authorizer=Approve())
    job_run(env, create(env), token)
    assert records(env)[0].state is OwnershipState.CLEANED
    assert len(deletes(env)) == 1 and not env.ml.decodes


def test_job_preparation_error_is_sanitized_and_runtime_closed(env, remote, caplog, capsys):
    from test_colab_runtime_client import OAUTH
    from test_colab_jupyter_files import TOKEN, URL
    remote.versions.clear()
    remote.install_fail = True
    env.install(provisioning_authorizer=Approve())
    finished = job_run(env, create(env))
    assert finished.status is FileStatus.FAILED and records(env)[0].state is OwnershipState.CLEANED
    captured = capsys.readouterr()
    text = caplog.text + captured.out + captured.err + finished.model_dump_json()
    for sensitive in ("SECRET_TOKEN", OAUTH, TOKEN, URL):
        assert sensitive not in text
    assert any(e.category.startswith("ColabProvisioning:") for e in finished.events)


def test_two_files_recheck_versions_but_install_and_download_only_once(env, remote):
    from test_official_colab_desktop_launch import add_source
    remote.versions.clear()
    missing_model(remote)
    second = add_source(env, 2)
    env.install(provisioning_authorizer=Approve())
    finished = job_run(env, create(env, file_ids=[env.source.stem, second.stem]))
    assert finished.status is FileStatus.DONE and finished.done_files == 2
    assert len(remote.installs) == len(remote.downloads) == 1
    assert actions(env.server).count("CHECK") == actions(env.server).count("VERIFY") == 2
