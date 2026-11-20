"""Issue #126 contracts: one transcription run globally, and the active run
stays visible and controllable from any folder.

The backend execution service is authoritative (behavior is covered by
backend/tests/test_global_single_run.py); these source contracts pin the
frontend wiring that keeps a second Start from being prepared and keeps
another folder's run out of the current folder queue.
"""

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def read_repo(path):
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def block_after(source, marker, open_char="{", close_char="}"):
    start = source.index(marker)
    depth = 0
    for index in range(source.index(open_char, start), len(source)):
        if source[index] == open_char:
            depth += 1
        elif source[index] == close_char:
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(f"unterminated block after {marker!r}")


PAGE = "frontend/src/pages/TranscriptionPage.tsx"


def test_backend_guard_is_checked_and_registered_under_one_lock():
    runner = read_repo("backend/src/services/transcription_runner.py")
    start = runner[runner.index("    def start(self, job_id: str) -> bool:") :]
    start = start[: start.index("\n    def ", 10)]
    locked = start[start.index("with self._lock:") :]
    assert locked.index("_unfinished_job_id_locked()") < locked.index("self._executor.submit(")
    assert locked.index("self._executor.submit(") < locked.index("self._futures[job_id] = future")
    assert "not future.done()" in runner, "active means an unfinished Future, not a finished token"
    routes = read_repo("backend/src/api/routes.py")
    assert "BackgroundExecutionService(transcription_runner)" in routes
    assert "max_workers=1" not in routes, "a single worker would queue, not reject"


def test_active_job_endpoint_is_read_only_and_future_backed():
    routes = read_repo("backend/src/api/routes.py")
    assert '@router.get("/execution/active-job", response_model=Optional[JobModel])' in routes
    handler = routes[routes.index("def get_active_execution_job(") :].split("\n\n\n", 1)[0]
    assert "execution_service.active_job_id()" in handler
    for forbidden in ("list_jobs", "mutate_job", "update_job", "start(", "folder"):
        assert forbidden not in handler, forbidden


def test_client_exposes_the_authoritative_active_run():
    client = read_repo("frontend/src/api/client.ts")
    assert "activeJob: (signal?: AbortSignal) => request<JobModel | null>('/execution/active-job'" in client


def test_page_keeps_folder_job_and_global_run_separate():
    page = read_repo(PAGE)
    assert "useState<JobModel | null>(null)" in page and "setGlobalActiveJob" in page
    load = block_after(page, "const loadFolder = useCallback(")
    assert "api.activeJob(signal)" in load and "setGlobalActiveJob(activeRun)" in load
    assert re.findall(r"rowsFrom\(([^)]*)\)", page.split("function rowsFrom", 1)[1]) == ["files, job"]
    assert "globalActiveJob" not in block_after(page, "function rowsFrom(")


def test_second_start_is_blocked_before_preflight_and_in_the_button():
    page = read_repo(PAGE)
    assert "!isPreflighting && !globalRunActive} canStop" in page
    handle_start = block_after(page, "function handleStart(")
    assert "if (globalRunActive) { setMessage(OTHER_RUN_ACTIVE_MESSAGE); return }" in handle_start
    attempt = block_after(page, "function startAttempt(")
    assert attempt.index("globalRunActive") < attempt.index("preflightLockRef.current = true")
    assert "actionsDisabled={globalRunActive}" in page
    assert "disabled={isPreflighting || globalRunActive ||" in page


def test_other_folder_run_is_visible_with_stop_and_cancel():
    page = read_repo(PAGE)
    assert "globalActiveJob.job_id !== job?.job_id ? globalActiveJob : null" in page
    assert "onStop={() => void runJobAction(otherActiveRun, 'stop')}" in page
    assert "onCancel={() => void runJobAction(otherActiveRun, 'cancel')}" in page
    action = block_after(page, "async function runJobAction(")
    assert "api.actionJob(target.job_id, actionName)" in action
    assert "canRetry={otherActiveRun === null}" in page
    banner = read_repo("frontend/src/components/transcription/ActiveRunBanner.tsx")
    for text in ("전사 작업 진행 중", "다른 폴더의 전사가 진행 중입니다.", "현재 파일", "중지", "작업 취소"):
        assert text in banner, text
    assert "title={activeJob.folder}" in banner


def test_global_run_poll_is_bounded_and_clears_only_on_backend_idle():
    page = read_repo(PAGE)
    effect = page[page.index("const pollGlobalRun =") :].split("}, [pollGlobalRun])", 1)[0]
    assert effect.count("new AbortController()") == 1
    assert effect.count("window.setTimeout(") == 2  # initial + reschedule, one timer at a time
    assert "window.clearTimeout(timer)" in effect and "controller?.abort()" in effect
    assert "api.activeJob(controller.signal)" in effect
    assert "setGlobalActiveJob(next)" in effect and "if (!next) return" in effect
    assert "setInterval" not in effect
