"""Issue #111 contracts: live transcription-folder change detection.

Legacy watched only the selected folder (QFileSystemWatcher + 1000ms
debounce) and rescanned disk truth. Sorigul restores the behavior with a
bounded revision poll: one folder, top-level only, change-only refresh, no
overlap, and no automatic Job actions.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND = REPO_ROOT / "frontend"
WATCHER = FRONTEND / "src" / "lib" / "folderRevisionWatcher.ts"
JOB_ACTIONS = re.compile(
    r"\b(createJob|startJob|actionJob|handleStart|uploadDrive|retranscribe|"
    r"setDialog|runPreflight|action\(\s*'(retry|stop|cancel)')"
)


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


def test_backend_revision_is_top_level_metadata_only():
    source = read_repo("backend/src/services/folder_revision.py")
    code = source.split('"""', 2)[2]
    assert "os.scandir(root)" in code
    assert "follow_symlinks=False" in code
    assert "st_mtime_ns" in code and "st_size" in code
    for forbidden in ("rglob", "os.walk", ".glob(", "open(", "read_bytes", "read_text", "iterdir"):
        assert forbidden not in code, forbidden
    routes = read_repo("backend/src/api/routes.py")
    endpoint = block_after(routes, 'def get_folder_revision(', "(", ")")
    handler = routes[routes.index(endpoint) :].split("\n\n\n", 1)[0]
    assert "folder_revision(req.folder)" in handler
    assert "job_manager" not in handler and "results_service" not in handler


def test_watcher_core_is_bounded_sequential_and_cleans_up():
    source = WATCHER.read_text(encoding="utf-8")
    assert "import " not in source.split("*/")[-1].split("export const")[0]
    assert "FOLDER_REVISION_POLL_MS = 1000" in source
    assert "setInterval" not in source
    assert "new AbortController()" in source
    stop = block_after(source, "stop: () => {")
    assert "clearTimer(timer)" in stop and "controller.abort()" in stop
    # The next poll is scheduled only after the awaited poll/refresh settles.
    poll = block_after(source, "const poll = async () => {")
    assert poll.rstrip("}").rstrip().endswith("timer = setTimer(() => void poll(), intervalMs)")


def test_hook_watches_only_the_selected_folder_via_revision_api():
    hook = read_repo("frontend/src/hooks/useFolderRevision.ts")
    assert "api.folderRevision(folder, signal)" in hook
    assert "return () => watcher.stop()" in hook
    assert "[folder, paused]" in hook
    assert "setInterval" not in hook
    assert not JOB_ACTIONS.search(hook)
    for path in (FRONTEND / "src").rglob("*.ts*"):
        text = path.read_text(encoding="utf-8")
        assert "@tauri-apps/plugin-fs" not in text, path
        assert "readDir(" not in text and "watchImmediate" not in text, path


def test_transcription_live_refresh_only_reloads_disk_and_defers_while_busy():
    page = read_repo("frontend/src/pages/TranscriptionPage.tsx")
    reconcile = block_after(page, "const reconcileFolderChange = useCallback(")
    assert "await loadFolder(signal)" in reconcile
    assert not JOB_ACTIONS.search(reconcile)
    # Vanished selections are pruned; nothing is auto-selected.
    assert "current.filter((id) => present.has(id))" in reconcile
    assert "setSelectedIds(scanned" not in reconcile
    assert "useFolderRevision(folder, reconcileFolderChange, isProcessing || isPreflighting)" in page
    load = block_after(page, "const loadFolder = useCallback(")
    assert "if (signal?.aborted) return undefined" in load


def test_folders_live_refresh_keeps_filter_selection_and_manual_refresh():
    page = read_repo("frontend/src/pages/FoldersPage.tsx")
    live = block_after(page, "const liveRefresh = async (signal: AbortSignal) => {")
    assert "await refresh(filter, { signal, live: true })" in live
    assert "'all'" not in live and "setFilter" not in live
    assert "api.textPreview(result.scan_id, selected.id, signal)" in live
    assert "fullText !== undefined" in live and "api.fullText(result.scan_id, selected.id, signal)" in live
    assert not JOB_ACTIONS.search(live)
    assert "useFolderRevision(folder, liveRefresh)" in page
    # Stale selection clears preview and full view.
    stale = block_after(page, "if (!selectedId || files.some((file) => file.id === selectedId)) return")
    assert "setPreview(PREVIEW_PLACEHOLDER)" in page and "setFullText(undefined)" in page
    assert stale
    # Manual refresh button is preserved.
    assert "onClick={() => void refresh()}" in page
    assert "'새로고침'" in page


def test_no_heavy_watcher_dependency_or_permission_widening():
    package = json.loads(read_repo("frontend/package.json"))
    deps = {**package.get("dependencies", {}), **package.get("devDependencies", {})}
    assert not {"chokidar", "@tauri-apps/plugin-fs"} & set(deps)
    assert "watchdog" not in read_repo("backend/requirements.txt").lower()
    cargo = read_repo("frontend/src-tauri/Cargo.toml")
    assert not re.search(r"^\s*notify\s*=", cargo, re.MULTILINE)
    assert "tauri-plugin-fs" not in cargo


HARNESS = r"""
import { pathToFileURL } from 'node:url'
const { startFolderRevisionWatcher } = await import(pathToFileURL(process.argv[2]).href)

function scenario({ revisions, reconcileOnStart = false, failAt = new Set(), holdRefresh = false }) {
  const timers = []
  const log = { fetches: 0, changes: 0, inFlight: 0, maxInFlight: 0, aborted: false }
  let index = 0
  let release
  const enter = () => { log.inFlight += 1; log.maxInFlight = Math.max(log.maxInFlight, log.inFlight) }
  const watcher = startFolderRevisionWatcher({
    reconcileOnStart,
    setTimer: (cb) => { timers.push(cb); return timers.length },
    clearTimer: () => { timers.length = 0 },
    fetchRevision: async (signal) => {
      enter(); log.fetches += 1
      signal.addEventListener('abort', () => { log.aborted = true })
      const at = index++
      await null
      log.inFlight -= 1
      if (failAt.has(at)) throw new Error('offline')
      return revisions[Math.min(at, revisions.length - 1)]
    },
    onChanged: async () => {
      enter(); log.changes += 1
      if (holdRefresh && log.changes === 1) await new Promise((resolve) => { release = resolve })
      log.inFlight -= 1
    },
  })
  const settle = async () => { for (let i = 0; i < 20; i++) await null }
  const tick = async () => { await settle(); const cb = timers.shift(); if (cb) cb(); await settle() }
  return { watcher, timers, log, tick, settle, release: () => release() }
}

const out = {}

{ const s = scenario({ revisions: ['A'] })
  for (let i = 0; i < 5; i++) await s.tick()
  out.stable = s.log.changes }

{ const s = scenario({ revisions: ['A', 'A', 'B', 'B', 'B'] })
  for (let i = 0; i < 6; i++) await s.tick()
  out.aToB = s.log.changes }

{ const s = scenario({ revisions: ['A', 'B', 'C', 'C', 'C'], holdRefresh: true })
  await s.tick(); await s.tick()
  const fetchesWhileHeld = s.log.fetches
  for (let i = 0; i < 3; i++) await s.tick()
  out.heldPending = { changes: s.log.changes, fetches: s.log.fetches - fetchesWhileHeld, timers: s.timers.length }
  s.release(); await s.settle()
  for (let i = 0; i < 4; i++) await s.tick()
  out.held = { changes: s.log.changes, maxInFlight: s.log.maxInFlight } }

{ const s = scenario({ revisions: ['A'], reconcileOnStart: true })
  for (let i = 0; i < 4; i++) await s.tick()
  out.reconcileOnStart = s.log.changes }

{ const s = scenario({ revisions: ['A', 'B', 'B'], failAt: new Set([1, 2]) })
  // Initial poll (A) + two failing polls.
  for (let i = 0; i < 2; i++) await s.tick()
  out.outageFetches = s.log.fetches
  const duringOutage = s.log.changes
  for (let i = 0; i < 3; i++) await s.tick()
  out.offline = { duringOutage, after: s.log.changes } }

{ const s = scenario({ revisions: ['A', 'B'] })
  await s.settle()
  s.watcher.stop()
  const fetches = s.log.fetches
  for (let i = 0; i < 3; i++) await s.tick()
  out.stopped = { aborted: s.log.aborted, extraFetches: s.log.fetches - fetches, timers: s.timers.length, changes: s.log.changes } }

console.log(JSON.stringify(out))
"""


def test_watcher_core_behavior_has_no_refresh_storm(tmp_path):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not available")
    harness = tmp_path / "harness.mjs"
    harness.write_text(HARNESS, encoding="utf-8")
    completed = subprocess.run(
        [node, str(harness), str(WATCHER)],
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout.strip().splitlines()[-1])

    assert result["stable"] == 0  # baseline + identical revisions: no refresh
    assert result["aToB"] == 1  # one change, one refresh
    # While a refresh is in flight, no poll or second refresh starts.
    assert result["heldPending"] == {"changes": 1, "fetches": 0, "timers": 0}
    # B->C during the refresh is reconciled exactly once afterwards.
    assert result["held"] == {"changes": 2, "maxInFlight": 1}
    assert result["reconcileOnStart"] == 1
    # Poll errors are silent; the stored baseline still catches the change.
    assert result["outageFetches"] == 3
    assert result["offline"] == {"duringOutage": 0, "after": 1}
    assert result["stopped"] == {"aborted": True, "extraFetches": 0, "timers": 0, "changes": 0}
