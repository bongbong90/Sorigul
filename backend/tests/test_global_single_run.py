"""Issue #126 contracts: at most ONE unfinished transcription execution
globally, regardless of folder or engine (Legacy `_is_transcribe_running()`
parity). A second start is rejected -- never queued -- and a run stays
active until its runner Future has actually returned.

Fakes only: no real Whisper, no real Colab. Races are made deterministic
with threading.Event / threading.Barrier -- never sleeps.
"""

import threading

import pytest
from fastapi.testclient import TestClient

from src.domain.models import FileStatus
from src.domain.transcription import TranscriptionResult
from src.services.job_manager import JobManager
from src.services.transcription_runner import BackgroundExecutionService, TranscriptionRunner

WAIT = 5  # upper bound for Event waits; never used as a sleep
ENGINES = ("local_whisper", "direct_colab")


def result_for(name):
    return TranscriptionResult.from_engine_payload(
        {"text": f"{name} 결과", "segments": [{"start": 0, "end": 1, "text": f"{name} 결과"}]}
    )


class ConcurrencyProbe:
    """Counts runner bodies executing at once across every Job."""

    def __init__(self):
        self._lock = threading.Lock()
        self.current = 0
        self.max_seen = 0

    def enter(self):
        with self._lock:
            self.current += 1
            self.max_seen = max(self.max_seen, self.current)

    def leave(self):
        with self._lock:
            self.current -= 1


class GatedEngine:
    """Blocks inside transcribe until released; same shape for Local/Colab."""

    def __init__(self, probe):
        self.probe = probe
        self.entered = threading.Event()
        self.release = threading.Event()

    def transcribe(self, source_path, token, event_callback, progress_callback):
        self.probe.enter()
        try:
            self.entered.set()
            assert self.release.wait(WAIT)
            return result_for(source_path.stem)
        finally:
            self.probe.leave()


def make_folder(tmp_path, name, stems=("A",)):
    folder = tmp_path / name
    folder.mkdir()
    for stem in stems:
        (folder / f"{stem}.mp3").write_bytes(b"fake-mp3")
    return folder


class Harness:
    def __init__(self, tmp_path, job_finished_callback=None):
        self.tmp_path = tmp_path
        self.manager = JobManager(str(tmp_path / "runtime" / "jobs.json"))
        self.probe = ConcurrencyProbe()
        self.engines = {}
        self.runner = TranscriptionRunner(
            self.manager,
            lambda job: self.engines[job.job_id],
            job_finished_callback=job_finished_callback,
        )
        self.service = BackgroundExecutionService(self.runner)

    def job(self, folder_name, engine="local_whisper"):
        folder = make_folder(self.tmp_path, folder_name)
        engine_config = {"base_url": "https://colab.example"} if engine == "direct_colab" else {}
        job = self.manager.create_job(str(folder), ["A"], engine=engine, engine_config=engine_config)
        self.engines[job.job_id] = GatedEngine(self.probe)
        return job

    def future(self, job_id):
        return self.service._futures[job_id]


@pytest.fixture
def routes():
    import src.api.routes as routes_module

    return routes_module


@pytest.mark.parametrize("engine_a", ENGINES)
@pytest.mark.parametrize("engine_b", ENGINES)
def test_second_job_is_rejected_while_first_runs_across_folders_and_engines(
    tmp_path, engine_a, engine_b
):
    h = Harness(tmp_path)
    a = h.job("폴더A", engine_a)
    b = h.job("폴더B", engine_b)

    assert h.service.start(a.job_id) is True
    assert h.engines[a.job_id].entered.wait(WAIT)

    assert h.service.start(b.job_id) is False
    assert h.manager.get_job(b.job_id).status == FileStatus.WAITING
    assert b.job_id not in h.service._futures, "a rejected start must never be queued"
    assert h.service.active_job_id() == a.job_id

    h.engines[a.job_id].release.set()
    h.future(a.job_id).result(timeout=WAIT)
    assert h.probe.max_seen == 1
    assert not h.engines[b.job_id].entered.is_set()


def test_simultaneous_starts_admit_exactly_one(tmp_path):
    h = Harness(tmp_path)
    a = h.job("폴더A", "local_whisper")
    b = h.job("폴더B", "direct_colab")
    barrier = threading.Barrier(2)
    results = {}

    def contender(job_id):
        barrier.wait(WAIT)
        results[job_id] = h.service.start(job_id)

    threads = [threading.Thread(target=contender, args=(j.job_id,)) for j in (a, b)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(WAIT)

    assert sorted(results.values()) == [False, True]
    winner = next(job_id for job_id, ok in results.items() if ok)
    loser = next(job_id for job_id, ok in results.items() if not ok)
    assert h.engines[winner].entered.wait(WAIT)
    assert h.service.active_job_id() == winner
    assert loser not in h.service._futures
    assert h.manager.get_job(loser).status == FileStatus.WAITING

    h.engines[winner].release.set()
    h.future(winner).result(timeout=WAIT)
    assert h.probe.max_seen == 1


def test_next_run_is_allowed_once_the_first_future_is_done(tmp_path):
    h = Harness(tmp_path)
    a = h.job("폴더A")
    b = h.job("폴더B", "direct_colab")

    assert h.service.start(a.job_id)
    assert h.engines[a.job_id].entered.wait(WAIT)
    h.engines[a.job_id].release.set()
    h.future(a.job_id).result(timeout=WAIT)
    assert h.service.active_job_id() is None

    assert h.service.start(b.job_id) is True
    assert h.engines[b.job_id].entered.wait(WAIT)
    h.engines[b.job_id].release.set()
    h.future(b.job_id).result(timeout=WAIT)
    assert h.manager.get_job(a.job_id).status == FileStatus.DONE
    assert h.manager.get_job(b.job_id).status == FileStatus.DONE
    assert h.probe.max_seen == 1


def test_terminal_persisted_but_runner_not_returned_still_blocks(tmp_path):
    persisted = threading.Event()
    hold_return = threading.Event()

    def finished(_job):
        persisted.set()
        assert hold_return.wait(WAIT)

    h = Harness(tmp_path, job_finished_callback=finished)
    a = h.job("폴더A")
    b = h.job("폴더B")
    assert h.service.start(a.job_id)
    h.engines[a.job_id].release.set()
    assert persisted.wait(WAIT)

    assert h.manager.get_job(a.job_id).status == FileStatus.DONE
    assert not h.service.is_active(a.job_id), "token is finished..."
    assert h.service.active_job_id() == a.job_id, "...but the Future is not"
    assert h.service.start(b.job_id) is False

    hold_return.set()
    h.future(a.job_id).result(timeout=WAIT)
    assert h.service.start(b.job_id) is True
    h.engines[b.job_id].release.set()
    h.future(b.job_id).result(timeout=WAIT)


@pytest.mark.parametrize("action", ["stop", "cancel"])
def test_requested_stop_or_cancel_keeps_the_run_exclusive(tmp_path, monkeypatch, routes, action):
    h = Harness(tmp_path)
    monkeypatch.setattr(routes, "job_manager", h.manager)
    monkeypatch.setattr(routes, "execution_service", h.service)
    a = h.job("폴더A")
    b = h.job("폴더B", "direct_colab")
    assert h.service.start(a.job_id)
    assert h.engines[a.job_id].entered.wait(WAIT)

    requested = routes.job_action(a.job_id, routes.JobActionRequest(action=action))
    if action == "cancel":
        assert requested.status == FileStatus.CANCEL_REQUESTED
    assert h.service.start(b.job_id) is False

    h.engines[a.job_id].release.set()
    h.future(a.job_id).result(timeout=WAIT)
    expected = FileStatus.CANCELLED if action == "cancel" else FileStatus.STOPPED
    assert h.manager.get_job(a.job_id).status == expected
    assert h.service.start(b.job_id) is True
    h.engines[b.job_id].release.set()
    h.future(b.job_id).result(timeout=WAIT)
    assert h.probe.max_seen == 1


def test_same_job_double_start_is_rejected(tmp_path):
    h = Harness(tmp_path)
    a = h.job("폴더A")
    assert h.service.start(a.job_id)
    assert h.engines[a.job_id].entered.wait(WAIT)
    assert h.service.start(a.job_id) is False
    h.engines[a.job_id].release.set()
    h.future(a.job_id).result(timeout=WAIT)


def test_invariant_violation_is_surfaced_not_silently_resolved(tmp_path):
    h = Harness(tmp_path)
    a = h.job("폴더A")
    b = h.job("폴더B")
    from concurrent.futures import Future

    from src.services.transcription_runner import ExecutionInvariantError

    h.service._futures = {a.job_id: Future(), b.job_id: Future()}
    with pytest.raises(ExecutionInvariantError):
        h.service.active_job_id()
    c = h.job("폴더C")
    assert h.service.start(c.job_id) is False


# -- HTTP surface --------------------------------------------------------------


@pytest.fixture
def api(tmp_path, monkeypatch, routes):
    from src.main import app

    h = Harness(tmp_path)
    monkeypatch.setattr(routes, "job_manager", h.manager)
    monkeypatch.setattr(routes, "execution_service", h.service)
    return TestClient(app, base_url="http://127.0.0.1:8000"), h


def test_active_job_endpoint_reports_the_future_owner(api):
    client, h = api
    assert client.get("/api/execution/active-job").json() is None

    a = h.job("폴더A")
    assert h.service.start(a.job_id)
    assert h.engines[a.job_id].entered.wait(WAIT)
    body = client.get("/api/execution/active-job").json()
    assert body["job_id"] == a.job_id
    assert body["status"] == FileStatus.TRANSCRIBING

    h.engines[a.job_id].release.set()
    h.future(a.job_id).result(timeout=WAIT)
    response = client.get("/api/execution/active-job")
    assert response.status_code == 200 and response.json() is None


def test_active_job_endpoint_covers_the_start_waiting_window(api):
    client, h = api
    entered = threading.Event()
    gate = threading.Event()
    real_run = h.runner.run

    def gated_run(job_id, token):
        entered.set()
        assert gate.wait(WAIT)
        return real_run(job_id, token)

    h.runner.run = gated_run
    a = h.job("폴더A")
    assert h.service.start(a.job_id)
    assert entered.wait(WAIT)
    assert h.manager.get_job(a.job_id).status == FileStatus.WAITING

    body = client.get("/api/execution/active-job").json()
    assert body["job_id"] == a.job_id and body["status"] == FileStatus.WAITING
    assert client.post(f"/api/jobs/{h.job('폴더B').job_id}/start").status_code == 409

    gate.set()
    h.engines[a.job_id].release.set()
    h.future(a.job_id).result(timeout=WAIT)


def test_active_job_endpoint_never_fakes_a_missing_job(api, monkeypatch):
    client, h = api
    a = h.job("폴더A")
    assert h.service.start(a.job_id)
    assert h.engines[a.job_id].entered.wait(WAIT)
    monkeypatch.setattr(h.manager, "get_job", lambda _job_id: None)
    response = client.get("/api/execution/active-job")
    assert response.status_code == 500
    assert a.folder not in response.text
    monkeypatch.undo()
    h.engines[a.job_id].release.set()
    h.future(a.job_id).result(timeout=WAIT)


def test_http_second_start_is_409_and_allowed_after_completion(api, routes):
    client, h = api
    a = h.job("폴더A")
    b = h.job("폴더B", "direct_colab")
    assert client.post(f"/api/jobs/{a.job_id}/start").status_code == 202
    assert h.engines[a.job_id].entered.wait(WAIT)

    rejected = client.post(f"/api/jobs/{b.job_id}/start")
    assert rejected.status_code == 409
    detail = rejected.json()["detail"]
    assert detail == routes.OTHER_RUN_ACTIVE_MESSAGE
    assert a.folder not in detail and "폴더A" not in detail
    assert client.post(f"/api/jobs/{a.job_id}/start").status_code == 409

    h.engines[a.job_id].release.set()
    h.future(a.job_id).result(timeout=WAIT)
    assert client.post(f"/api/jobs/{b.job_id}/start").status_code == 202
    h.engines[b.job_id].release.set()
    h.future(b.job_id).result(timeout=WAIT)


def test_retry_of_another_job_is_refused_without_mutation(api, routes):
    client, h = api
    b = h.job("폴더B")
    b.status = FileStatus.FAILED
    b.files["A"] = FileStatus.FAILED
    h.manager.update_job(b)
    before = h.manager.get_job(b.job_id)

    a = h.job("폴더A", "direct_colab")
    assert h.service.start(a.job_id)
    assert h.engines[a.job_id].entered.wait(WAIT)

    response = client.post(f"/api/jobs/{b.job_id}/action", json={"action": "retry"})
    assert response.status_code == 409
    assert response.json()["detail"] == routes.OTHER_RUN_ACTIVE_MESSAGE
    after = h.manager.get_job(b.job_id)
    assert after.status == FileStatus.FAILED and after.files == before.files
    assert [e.message for e in after.events] == [e.message for e in before.events]
    assert b.job_id not in h.service._futures

    h.engines[a.job_id].release.set()
    h.future(a.job_id).result(timeout=WAIT)
    retried = client.post(f"/api/jobs/{b.job_id}/action", json={"action": "retry"})
    assert retried.status_code == 200 and retried.json()["status"] == FileStatus.WAITING
    assert client.post(f"/api/jobs/{b.job_id}/start").status_code == 202
    h.engines[b.job_id].release.set()
    h.future(b.job_id).result(timeout=WAIT)
    assert h.probe.max_seen == 1
