"""Official Colab upkeep (#60): token renew, owned Runtime / lock recovery,
stage progress and user guidance. No network, no Runtime create."""

import json
from types import SimpleNamespace

import pytest

from src.engines.official_colab import OfficialColabJobEngine
from src.services.colab_full_file_pipeline import PipelineCleanup, PipelineError, PipelineReport
from src.services.colab_maintenance import ColabMaintenance, recover_owned_runtimes, settle_file_checkpoints
from src.services.colab_runtime_ownership import OwnershipState, OwnershipStore
from src.services.official_colab_launcher import (
    FailClosedLaunchAuthorizer, OfficialColabLauncher, OwnedRuntimeProvisioningAuthorizer)


class Store:
    def __init__(self, *states):
        self.records = [SimpleNamespace(state=s, execution_id=f"{i:032x}") for i, s in enumerate(states)]

    def load(self):
        return list(self.records)


def checkpoint(root, name, status):
    path = root / ".pipeline-locks" / name / "attempt.json"
    path.parent.parent.mkdir(parents=True, exist_ok=True)
    with OwnershipStore(path.parent).transaction():  # as the pipeline creates it
        pass
    path.write_text(json.dumps(dict(version=1, execution_id="a" * 32, status=status)), encoding="utf-8")
    return path


@pytest.mark.parametrize("status,after", [("CLEANUP_REQUIRED", "FAILED"), ("STATE_UNCERTAIN", "FAILED"),
                                          ("ACTIVE", "FAILED"), ("COMPLETED", "COMPLETED")])
def test_checkpoints_settle_only_when_every_owned_runtime_is_cleaned(tmp_path, status, after):
    path = checkpoint(tmp_path, "f" * 64, status)
    cache_file = path.parent.parent.parent / "kept-cache.json"
    cache_file.write_text("verified chunks", encoding="utf-8")
    settle_file_checkpoints(tmp_path, Store(OwnershipState.CLEANED), job_active=lambda: False)
    assert json.loads(path.read_text(encoding="utf-8"))["status"] == after
    assert cache_file.read_text(encoding="utf-8") == "verified chunks"


@pytest.mark.parametrize("store,active", [(Store(OwnershipState.CLEANUP_REQUIRED), False),
                                          (Store(OwnershipState.CLEANED), True)])
def test_checkpoints_untouched_while_runtime_unresolved_or_job_active(tmp_path, store, active):
    path = checkpoint(tmp_path, "e" * 64, "CLEANUP_REQUIRED")
    assert settle_file_checkpoints(tmp_path, store, job_active=lambda: active) == 0
    assert json.loads(path.read_text(encoding="utf-8"))["status"] == "CLEANUP_REQUIRED"


def test_recovery_without_pending_records_needs_no_account_or_network():
    class Auth:
        def for_launch(self):
            raise AssertionError("no credential use when nothing is pending")
    assert recover_owned_runtimes(Auth(), Store(OwnershipState.CLEANED)) is True


def test_recovery_without_account_keeps_records_and_never_raises():
    class Auth:
        def for_launch(self):
            raise RuntimeError("offline")
    store = Store(OwnershipState.CLEANUP_REQUIRED)
    assert recover_owned_runtimes(Auth(), store) is False
    assert store.records[0].state is OwnershipState.CLEANUP_REQUIRED


def test_maintenance_renews_colab_and_drive_tokens_best_effort(tmp_path):
    calls = []
    colab = SimpleNamespace(refreshable=lambda: True,
                            check=lambda include_preflight: calls.append(("colab", include_preflight)))
    token = tmp_path / "drive.json"
    token.write_text("{}", encoding="utf-8")
    def drive_fail():
        calls.append("drive")
        raise RuntimeError("offline")
    drive = SimpleNamespace(token_path=token, ensure_client=drive_fail)
    ColabMaintenance(colab_auth=colab, drive_auth=drive, store=Store(), cache_root=tmp_path,
                     job_active=lambda: False).run_once()
    assert calls == [("colab", False), "drive"]


def test_expired_but_refreshable_account_is_not_reported_disconnected(tmp_path):
    class Credentials:
        def __call__(self):
            return None  # access token expired

        def refreshable(self):
            return True
    launcher = OfficialColabLauncher(credential_provider=Credentials(), ownership_store=Store(),
                                     authorizer=FailClosedLaunchAuthorizer(), cache_root=tmp_path)
    codes = [r["code"] for r in launcher.status()["reasons"]]
    assert "ACCOUNT_NOT_CONNECTED" not in codes
    assert codes == ["COST_GATE_CONDITIONAL", "POLICY_GATE_NOT_VERIFIED"]


def test_product_provisioning_only_on_this_apps_runtime():
    authorizer = OwnedRuntimeProvisioningAuthorizer()
    assert authorizer.authorize(SimpleNamespace(name="runtimes/sorigul-" + "a" * 32))
    assert not authorizer.authorize(SimpleNamespace(name="runtimes/other"))
    assert not authorizer.authorize(None)


def report(diagnostic=None, signals=()):
    return PipelineReport("FAILED", "X", tuple(signals), (), False, PipelineCleanup(), diagnostic)


@pytest.mark.parametrize("stage,code,expected", [
    ("audio_decode", "KERNEL_EXECUTION_FAILED", "AUDIO_DECODE_FAILED"),
    ("model_init", "MODEL_LOAD_FAILED", "MODEL_LOAD_FAILED"),
    ("inference", "CUDA_FAILED", "DEVICE_FAILED"),
    (None, "PRIOR_EXECUTION_UNRESOLVED", "PRIOR_EXECUTION_UNRESOLVED")])
def test_user_guidance_follows_failure_stage(stage, code, expected):
    diagnostic = {"stage": stage, "exception": None, "message": None, "runtime": None} if stage else None
    error = OfficialColabJobEngine._normalize(PipelineError(code), report(diagnostic))
    assert error.code.endswith(expected) and error.user_message


def test_stage_progress_is_monotonic_and_never_reaches_100():
    seen = []

    class Pipeline:
        last_report = None

        def transcribe(self, source, token, event, progress):
            progress(0.0)
            for state, message in (("CHECKING", "GPU와 전사 환경을 확인하고 있습니다."),
                                   ("DOWNLOADING", "모델을 준비하고 있습니다."),
                                   ("READY", "전사 환경 준비가 완료되었습니다.")):
                event("info", "ColabProvisioning:" + state, message)
            progress(0.5)
            progress(1.0)
            raise PipelineError("X")

    engine = OfficialColabJobEngine(None, None, pipeline_factory=lambda *_: Pipeline())
    token = SimpleNamespace(raise_if_requested=lambda: None)
    with pytest.raises(Exception):
        engine.transcribe("x.mp3", token, lambda *a: None, seen.append)
    numbers = [v for v in seen if v is not None]
    assert numbers == sorted(numbers) and numbers[-1] < 1
    assert 0.02 in numbers and 0.2 in numbers and 0.575 in numbers and seen[-1] is None
