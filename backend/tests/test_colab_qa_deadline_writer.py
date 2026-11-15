"""LIVE-B2D offline: fake clock deadline gates and atomic QA writer. No network."""
import json
import os
import socket

import pytest

from qa import colab_qa_deadline as deadline_module
from qa import colab_qa_writer as writer_module
from qa.colab_qa_coordinator import _empty_coordinator
from qa.colab_qa_deadline import (CLEANUP_RESERVE_SECONDS, RUNTIME_LIMIT_SECONDS, WORK_LIMIT_SECONDS,
                                  RunDeadline, authorize_runtime_creation)
from qa.colab_qa_run import QAResultSaveError
from qa.colab_qa_writer import SCHEMA, QAResultWriter, validate_record
from qa.colab_readback import QADiagnostics
from src.services.colab_runtime_ownership import OwnershipRecord, OwnershipState, OwnershipStore

EXECUTION = "00000000-0000-4000-8000-0000000000aa"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*a, **k):
        pytest.fail("NETWORK_FORBIDDEN")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)


class Clock:
    def __init__(self, t=0.0):
        self.t = t

    def __call__(self):
        return self.t


def started(clock):
    d = RunDeadline(clock=clock)
    assert d.start_work() and d.mark_runtime_created()
    return d


# ---- deadline -----------------------------------------------------------------

def test_normal_run_under_limits_passes_and_reports_elapsed():
    clock = Clock()
    d = started(clock)
    clock.t = 600
    assert d.may_start(20)
    d.begin_cleanup()
    clock.t = 700
    d.mark_runtime_cleaned()
    assert d.verdict() == "PASS" and d.elapsed() == (600, 700)


def test_step_blocked_just_before_work_limit():
    clock = Clock()
    d = started(clock)
    clock.t = WORK_LIMIT_SECONDS - 20
    assert d.may_start(20)
    clock.t = WORK_LIMIT_SECONDS - 19
    assert not d.may_start(20)


def test_work_limit_exceeded_is_recorded_as_fail():
    clock = Clock()
    d = started(clock)
    clock.t = WORK_LIMIT_SECONDS + 1
    d.check_step()
    assert not d.may_start(1)
    d.begin_cleanup()
    d.mark_runtime_cleaned()
    assert d.verdict() == "FAIL"


def test_runtime_limit_during_cleanup_fails_even_if_cleaned():
    clock = Clock()
    d = started(clock)
    clock.t = 100
    d.begin_cleanup()
    clock.t = RUNTIME_LIMIT_SECONDS + 1
    d.mark_runtime_cleaned()
    assert d.verdict() == "FAIL"


def test_insufficient_cleanup_reserve_blocks_new_work(monkeypatch):
    clock = Clock()
    d = started(clock)
    clock.t = 1000
    assert d.may_start(20)
    monkeypatch.setattr(deadline_module, "CLEANUP_RESERVE_SECONDS", RUNTIME_LIMIT_SECONDS - 1000)
    assert not d.may_start(20)


@pytest.mark.parametrize("step", [0, -1, 21, float("nan"), float("inf"), True, "5", None])
def test_unbounded_or_invalid_step_is_blocked(step):
    assert not started(Clock()).may_start(step)


def test_non_monotonic_or_broken_clock_is_not_verified():
    clock = Clock(10)
    d = started(clock)
    clock.t = 5
    assert not d.may_start(20)
    assert d.verdict() == "NOT_VERIFIED"
    broken = RunDeadline(clock=lambda: float("nan"))
    assert not broken.start_work() and broken.verdict() == "NOT_VERIFIED"


def test_missing_cleanup_marks_are_not_verified_never_pass():
    clock = Clock()
    d = started(clock)
    d.begin_cleanup()
    assert d.verdict() == "NOT_VERIFIED"  # No confirmed CLEANED observation.


def test_after_cleanup_starts_no_new_work_and_only_one_runtime():
    clock = Clock()
    d = started(clock)
    assert not d.mark_runtime_created()  # Max 1 Runtime per run, failed or not.
    d.begin_cleanup()
    assert not d.may_start(20)
    assert RunDeadline(clock=clock).mark_runtime_created() is False  # Work not started.


def test_creation_gate_allows_once_and_blocks_uncertain_or_repeat(tmp_path):
    store = OwnershipStore(tmp_path / "ownership")
    clock = Clock()
    d = RunDeadline(clock=clock)
    assert not authorize_runtime_creation(store, d)  # Work not started.
    d.start_work()
    assert authorize_runtime_creation(store, d) and d.runtimes_created == 1
    assert not authorize_runtime_creation(store, d)  # Repeat request: never a second Runtime.
    with store.transaction():
        store._save(OwnershipRecord(EXECUTION, "00000000-0000-4000-8000-0000000000ab",
                                    "runtimes/sorigul-" + "3" * 32, "a" * 64,
                                    state=OwnershipState.CREATE_UNCERTAIN,
                                    last_remote_state="REQUEST_SENT_OR_PENDING",
                                    checked_at="2026-11-15T00:00:00+00:00"))
    fresh = RunDeadline(clock=clock)
    fresh.start_work()
    assert not authorize_runtime_creation(store, fresh) and fresh.runtimes_created == 0
    late = RunDeadline(clock=clock)
    late.start_work()
    clock.t = WORK_LIMIT_SECONDS - CLEANUP_RESERVE_SECONDS
    assert not late.may_create_runtime()  # Not enough time left for work + cleanup.


# ---- writer -------------------------------------------------------------------

def record():
    return {"schema": SCHEMA, "diagnostics": QADiagnostics().snapshot(), "coordinator": _empty_coordinator()}


def files(root):
    return sorted(p.name for p in root.iterdir()) if root.exists() else []


@pytest.fixture
def writer(tmp_path):
    return QAResultWriter(tmp_path / "sorigul-qa-results")


def test_normal_atomic_write_and_reread(writer):
    final = writer.write(record(), execution_id=EXECUTION)
    assert files(writer.root) == ["qa-result-" + EXECUTION + ".json"]
    assert json.loads(final.read_bytes()) == record() and writer.exists(EXECUTION)


@pytest.mark.parametrize("make", [
    lambda t: "relative/sorigul-qa-results",
    lambda t: t / "other-results",
    lambda t: t / "x" / ".." / "sorigul-qa-results",
])
def test_invalid_root_rejected(tmp_path, make):
    with pytest.raises(QAResultSaveError):
        QAResultWriter(make(tmp_path))


def test_root_inside_product_app_data_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(writer_module, "get_app_data_dir", lambda: tmp_path / "Sorigul")
    with pytest.raises(QAResultSaveError):
        QAResultWriter(tmp_path / "Sorigul" / "sorigul-qa-results")


def test_link_or_junction_root_rejected(tmp_path):
    target = tmp_path / "elsewhere"
    target.mkdir()
    link = tmp_path / "sorigul-qa-results"
    try:
        if os.name == "nt":
            import _winapi
            _winapi.CreateJunction(str(target), str(link))
        else:
            os.symlink(target, link)
    except (OSError, AttributeError):
        pytest.skip("link creation unavailable")
    with pytest.raises(QAResultSaveError):
        QAResultWriter(link).write(record(), execution_id=EXECUTION)
    assert files(target) == []


@pytest.mark.parametrize("mutate", [
    lambda r: r["coordinator"].__setitem__("lease", "mock-proxy-secret"),
    lambda r: r["coordinator"].__setitem__("observer", "https://runtime.example.invalid/prefix"),
    lambda r: r["diagnostics"]["readback"].__setitem__("error_code", "sorigul-transfer/x/chunk-00000.mp3"),
    lambda r: r["diagnostics"].__setitem__("account", "a" * 64),
    lambda r: r["coordinator"].__setitem__("work_elapsed_seconds", 1.5),
    lambda r: r["coordinator"].__setitem__("work_elapsed_seconds", -1),
    lambda r: r["diagnostics"].__setitem__("readback", b"mp3 bytes"),
    lambda r: r.__setitem__("schema", "OTHER"),
])
def test_sensitive_or_unschematized_records_rejected_before_any_write(writer, mutate):
    bad = record()
    mutate(bad)
    with pytest.raises(ValueError):
        validate_record(bad)
    with pytest.raises(QAResultSaveError) as error:
        writer.write(bad, execution_id=EXECUTION)
    assert str(error.value) == "QA_RESULT_SAVE_FAILED" and error.value.__cause__ is None
    assert files(writer.root) == []


def test_invalid_execution_id_path_rejected(writer):
    for bad in ("../x", "00000000-0000-1000-8000-000000000001", EXECUTION + "/x"):
        with pytest.raises(QAResultSaveError):
            writer.write(record(), execution_id=bad)
    assert files(writer.root) == []


def test_existing_file_is_never_overwritten(writer):
    writer.root.mkdir()
    final = writer.root / ("qa-result-" + EXECUTION + ".json")
    final.write_bytes(b"user content")
    with pytest.raises(QAResultSaveError):
        writer.write(record(), execution_id=EXECUTION)
    assert final.read_bytes() == b"user content" and files(writer.root) == [final.name]


@pytest.mark.parametrize("target", ["write", "fsync"])
def test_temp_write_or_disk_error_fails_without_partial_files(writer, monkeypatch, target):
    def fail(*a, **k):
        raise OSError("disk")
    monkeypatch.setattr(writer_module.os, target, fail)
    with pytest.raises(QAResultSaveError):
        writer.write(record(), execution_id=EXECUTION)
    monkeypatch.undo()
    assert files(writer.root) == []


def test_short_write_loops_until_complete(writer, monkeypatch):
    real = os.write
    monkeypatch.setattr(writer_module.os, "write", lambda fd, data: real(fd, bytes(data[:7])))
    final = writer.write(record(), execution_id=EXECUTION)
    assert json.loads(final.read_bytes()) == record()


def test_failure_before_publish_leaves_nothing(writer, monkeypatch):
    def fail(temp, final):
        raise OSError("publish")
    monkeypatch.setattr(writer, "_publish", fail)
    with pytest.raises(QAResultSaveError):
        writer.write(record(), execution_id=EXECUTION)
    assert files(writer.root) == [] and not writer.exists(EXECUTION)


def test_verification_failure_after_publish_quarantines_result(writer, monkeypatch):
    def fail(*a):
        raise ValueError
    monkeypatch.setattr(writer, "_verify", fail)
    with pytest.raises(QAResultSaveError):
        writer.write(record(), execution_id=EXECUTION)
    names = files(writer.root)
    assert len(names) == 1 and names[0].startswith(".qa-result-" + EXECUTION + ".invalid-")
    assert not writer.exists(EXECUTION)


def test_cancellation_during_commit_is_preserved_and_not_committed(writer, monkeypatch):
    def cancel(*a):
        raise KeyboardInterrupt
    monkeypatch.setattr(writer, "_verify", cancel)
    with pytest.raises(KeyboardInterrupt):
        writer.write(record(), execution_id=EXECUTION)
    assert not writer.exists(EXECUTION)


def test_tampered_published_content_is_not_committed(writer, monkeypatch):
    real = writer._publish
    def publish(temp, final):
        real(temp, final)
        final.write_bytes(b"{}\n")
    monkeypatch.setattr(writer, "_publish", publish)
    with pytest.raises(QAResultSaveError):
        writer.write(record(), execution_id=EXECUTION)
    assert not writer.exists(EXECUTION)
