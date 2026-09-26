"""Package D source-only UX integrity contracts.

All filesystem behavior uses pytest-owned tmp_path and injected fakes. No
external services, real app-data, MP3 reads, transcription, or packaging.
"""

import json
import re
import threading
from concurrent.futures import Future
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.domain.models import FileStatus
from src.domain.transcription import CancellationToken
from src.services.job_manager import JobManager
from src.services.renamer import BundleRenamer, RenameStatus
from src.services.settings import RuntimeSettings, SettingsManager, SettingsPatch
from src.services.transcription_runner import BackgroundExecutionService
from src.sidecar_main import job_storage_exit_code


ROOT = Path(__file__).resolve().parents[2]


def make_bundle(folder: Path, stem: str):
    for extension in (".mp3", ".txt", ".json", ".srt"):
        (folder / f"{stem}{extension}").write_text(extension, encoding="utf-8")


def test_rename_all_success_conflict_and_nothing(tmp_path):
    make_bundle(tmp_path, "old")
    result = BundleRenamer().apply_rename(str(tmp_path), "old", "new")
    assert result.status == RenameStatus.SUCCESS
    assert all((tmp_path / f"new{ext}").exists() for ext in BundleRenamer.EXTENSIONS)

    (tmp_path / "taken.mp3").write_text("owned", encoding="utf-8")
    conflict = BundleRenamer().apply_rename(str(tmp_path), "new", "taken")
    assert conflict.status == RenameStatus.RENAME_CONFLICT
    assert (tmp_path / "new.mp3").exists()
    assert (tmp_path / "taken.mp3").read_text(encoding="utf-8") == "owned"

    nothing = BundleRenamer().apply_rename(str(tmp_path), "missing", "unused")
    assert nothing.status == RenameStatus.RENAME_NOTHING_TO_DO


def test_rename_apply_failure_rolls_back_and_reports_it(tmp_path):
    make_bundle(tmp_path, "old")
    calls = 0

    def fail_second(source: Path, target: Path):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected apply failure")
        source.rename(target)

    result = BundleRenamer(fail_second).apply_rename(str(tmp_path), "old", "new")
    assert result.status == RenameStatus.RENAME_APPLY_FAILED_ROLLED_BACK
    assert "injected apply failure" in (result.apply_error or "")
    assert all((tmp_path / f"old{ext}").exists() for ext in BundleRenamer.EXTENSIONS)
    assert not any((tmp_path / f"new{ext}").exists() for ext in BundleRenamer.EXTENSIONS)


def test_rename_rollback_failure_is_never_silent(tmp_path):
    make_bundle(tmp_path, "old")
    calls = 0

    def fail_apply_and_rollback(source: Path, target: Path):
        nonlocal calls
        calls += 1
        if calls in {2, 3}:
            raise OSError("injected rollback failure" if calls == 3 else "injected apply failure")
        source.rename(target)

    result = BundleRenamer(fail_apply_and_rollback).apply_rename(str(tmp_path), "old", "new")
    assert result.status == RenameStatus.RENAME_ROLLBACK_FAILED
    assert result.apply_error
    assert result.rollback_error
    assert (tmp_path / "new.mp3").exists(), "partial state remains visible for user inspection"


def test_nullable_settings_distinguish_omitted_null_and_value(tmp_path):
    manager = SettingsManager(tmp_path / "settings.json")
    manager.update(SettingsPatch(
        transcription_folder="C:/test-owned",
        last_course="course",
        last_subject="subject",
    ))
    preserved = manager.update(SettingsPatch(last_engine="direct_colab"))
    assert preserved.transcription_folder == "C:/test-owned"

    cleared = manager.update(SettingsPatch(
        transcription_folder=None,
        last_course=None,
        last_subject=None,
    ))
    assert cleared.transcription_folder is None
    assert cleared.last_course is None
    assert cleared.last_subject is None
    assert cleared.last_engine == "direct_colab"

    persisted = manager.update(SettingsPatch(last_course="new course"))
    assert SettingsManager(tmp_path / "settings.json").get() == persisted


@pytest.mark.parametrize(
    "field",
    [
        "notifications",
        "close_behavior",
        "shutdown",
        "last_engine",
        "subject_stage_overrides",
        "drive_exam_root",
    ],
)
def test_required_setting_rejects_explicit_null_without_changing_file(tmp_path, field):
    path = tmp_path / "settings.json"
    manager = SettingsManager(path)
    manager.update(SettingsPatch(last_course="keep"))
    before = path.read_bytes()
    before_settings = manager.get()

    with pytest.raises(ValidationError):
        SettingsPatch.model_validate({field: None})

    assert path.read_bytes() == before
    assert manager.get() == before_settings
    assert RuntimeSettings.model_validate(json.loads(path.read_text(encoding="utf-8")))


def test_post_terminal_start_waits_for_previous_future_without_duplicate_runner(tmp_path):
    manager = JobManager(str(tmp_path / "runtime" / "jobs.json"))
    job = manager.create_job(str(tmp_path), ["fake"])
    calls = []

    class FakeRunner:
        job_manager = manager

        def run(self, job_id, token):
            calls.append(job_id)

    service = BackgroundExecutionService(FakeRunner(), max_workers=1)
    previous = Future()
    token = CancellationToken()
    token.mark_finished()
    service._futures[job.job_id] = previous
    service._tokens[job.job_id] = token
    result = []
    started = threading.Event()

    def start_next():
        started.set()
        result.append(service.start(job.job_id))

    thread = threading.Thread(target=start_next)
    thread.start()
    assert started.wait(1)
    assert calls == [], "new runner must not overlap the previous Future"
    previous.set_result(None)
    thread.join(timeout=1)
    assert result == [True]
    new_future = service._futures.get(job.job_id)
    if new_future is not None:
        new_future.result(timeout=1)
    assert calls == [job.job_id]
    service._executor.shutdown(wait=True)


def test_quiescence_wait_is_bounded(tmp_path):
    manager = JobManager(str(tmp_path / "runtime" / "jobs.json"))
    job = manager.create_job(str(tmp_path), ["fake"])

    class FakeRunner:
        job_manager = manager

        def run(self, job_id, token):
            raise AssertionError("must not start while prior Future is pending")

    service = BackgroundExecutionService(FakeRunner(), max_workers=1)
    service._futures[job.job_id] = Future()
    assert service.wait_for_quiescence(job.job_id, timeout=0.01) is False
    service._executor.shutdown(wait=True)


def test_sidecar_job_storage_exit_codes_are_stable():
    assert job_storage_exit_code("JOB_STORAGE_READ_FAILED") == 20
    assert job_storage_exit_code("JOB_STORAGE_QUARANTINE_FAILED") == 21
    assert job_storage_exit_code("JOB_STORAGE_WRITE_FAILED") == 22
    assert job_storage_exit_code("UNKNOWN") == 1


def test_engine_section_uses_semantic_external_css_only():
    component = (ROOT / "frontend/src/components/transcription/EngineSection.tsx").read_text(encoding="utf-8")
    css = (ROOT / "frontend/src/styles/transcription-screen.css").read_text(encoding="utf-8")
    old_tailwind_classes = {
        "bg-white", "p-6", "rounded-xl", "border-gray-100", "shadow-sm",
        "space-y-4", "flex-1", "items-center", "border-primary-500",
        "bg-primary-50", "text-gray-900", "text-gray-500", "w-5", "h-5",
        "bg-gray-50", "text-green-600", "text-blue-600", "text-yellow-600",
        "text-red-600", "focus:ring-1", "disabled:opacity-50",
    }
    assert not any(marker in component for marker in old_tailwind_classes)
    assert "style=" not in component
    for state_class in (
        ".engine-option-selected",
        ".engine-option-disabled",
        ".engine-state-connected",
        ".engine-state-waiting",
        ".engine-state-verifying",
        ".engine-error",
        ".engine-manual-input",
    ):
        assert state_class in css


def test_frontend_deadline_and_polling_contracts_are_explicit():
    client = (ROOT / "frontend/src/api/client.ts").read_text(encoding="utf-8")
    assert "new AbortController()" in client
    assert "REQUEST_TIMEOUT" in client
    assert "BACKEND_OFFLINE" in client
    assert "LONG_EXTERNAL_BRIDGE: 90_000" in client
    assert "callerSignal?.removeEventListener" in client

    async_interval = re.compile(r"setInterval\([^\n]*(?:async|=>\s*void)")
    source_root = ROOT / "frontend/src"
    offenders = []
    for path in source_root.rglob("*.tsx"):
        if async_interval.search(path.read_text(encoding="utf-8")):
            offenders.append(path.relative_to(ROOT).as_posix())
    for path in source_root.rglob("*.ts"):
        if async_interval.search(path.read_text(encoding="utf-8")):
            offenders.append(path.relative_to(ROOT).as_posix())
    assert offenders == []


def test_sidecar_status_uses_snapshot_plus_structured_event():
    rust = (ROOT / "frontend/src-tauri/src/lib.rs").read_text(encoding="utf-8")
    native = (ROOT / "frontend/src/lib/native.ts").read_text(encoding="utf-8")
    shell = (ROOT / "frontend/src/components/layout/AppShell.tsx").read_text(encoding="utf-8")
    assert "SidecarStatusPayload" in rust
    assert 'format!("{resolved:?}")' not in rust
    assert "get_sidecar_status" in rust
    assert "sidecar_status: Mutex" in rust
    assert "await listen<SidecarStatus>" in native
    assert "get_sidecar_status" in native
    assert "Backend 시작 실패" in shell
