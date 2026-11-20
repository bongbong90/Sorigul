// #111 live transcription-folder change detection (Legacy QFileSystemWatcher
// parity, greenfield). One sequential poll loop per selected folder:
//
//   fetch revision -> (changed? await onChanged) -> setTimeout(next poll)
//
// The next poll is only scheduled after the previous revision request and any
// refresh it triggered have settled, so at most one revision request OR one
// watcher refresh is ever in flight -- never both, never overlapping. A burst
// of filesystem changes inside one interval collapses into one refresh, and a
// change that lands while a refresh is running is seen by the very next poll
// and reconciled exactly once more (the stored revision acts as the dirty
// flag). The first successful poll only records a baseline.
//
// Deliberately import-free: kept pure so it can be exercised directly by the
// root contract tests via Node's built-in type stripping.

export const FOLDER_REVISION_POLL_MS = 1000

type TimerHandle = ReturnType<typeof setTimeout>

export interface FolderRevisionWatcherOptions {
  fetchRevision: (signal: AbortSignal) => Promise<string>
  onChanged: (signal: AbortSignal) => Promise<void>
  // Reconcile once right after the baseline is taken (e.g. a change may have
  // been deferred while a transcription or preflight was active).
  reconcileOnStart?: boolean
  intervalMs?: number
  setTimer?: (callback: () => void, ms: number) => TimerHandle
  clearTimer?: (handle: TimerHandle) => void
}

export interface FolderRevisionWatcher {
  stop: () => void
}

export function startFolderRevisionWatcher(options: FolderRevisionWatcherOptions): FolderRevisionWatcher {
  const intervalMs = options.intervalMs ?? FOLDER_REVISION_POLL_MS
  const setTimer = options.setTimer ?? ((callback, ms) => setTimeout(callback, ms))
  const clearTimer = options.clearTimer ?? ((handle) => clearTimeout(handle))
  const controller = new AbortController()
  let timer: TimerHandle | undefined
  let stopped = false
  let baseline: string | undefined
  let reconcilePending = Boolean(options.reconcileOnStart)

  const reconcile = async () => {
    try {
      await options.onChanged(controller.signal)
    } catch {
      // The refresh surfaces its own errors; the watcher just keeps polling.
    }
  }

  const poll = async () => {
    timer = undefined
    try {
      const revision = await options.fetchRevision(controller.signal)
      if (stopped) return
      if (baseline === undefined) {
        baseline = revision
        if (reconcilePending) {
          reconcilePending = false
          await reconcile()
        }
      } else if (revision !== baseline) {
        baseline = revision
        await reconcile()
      }
    } catch {
      // Silent: backend offline/unreadable folder is reported by the global
      // health UI and the explicit refresh paths, never once per poll.
    }
    if (!stopped) timer = setTimer(() => void poll(), intervalMs)
  }

  void poll()
  return {
    stop: () => {
      stopped = true
      if (timer !== undefined) clearTimer(timer)
      timer = undefined
      controller.abort()
    },
  }
}
