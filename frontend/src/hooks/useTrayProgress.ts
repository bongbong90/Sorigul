import { useEffect } from 'react'
import { api, type JobModel } from '../api/client'
import { setTrayProgress, type TrayProgressPayload } from '../lib/native'

const TERMINAL_STATES = new Set(['DONE', 'FAILED', 'CRASHED', 'STOPPED', 'CANCELLED'])
const TRAY_POLL_INTERVAL_MS = 1500

function payloadFromJob(job: JobModel): TrayProgressPayload {
  return {
    status: job.status,
    currentFile: job.current_file,
    currentProgress: job.current_progress,
  }
}

function updateTray(payload: TrayProgressPayload): void {
  void setTrayProgress(payload).catch(() => {
    // The tray is best-effort UI. Job polling and transcription truth must not
    // be weakened by a platform tray failure.
  })
}

/**
 * App-lifetime tray observer (#173). Mount exactly once from App so route
 * changes cannot detach it. The authoritative source is the backend's
 * app-wide active Job (#126); when an observed active Job disappears, one
 * terminal lookup supplies the real final state. Backend failures never infer
 * IDLE/FAILED: the last confirmed tray state is kept.
 */
export function useTrayProgress(): void {
  useEffect(() => {
    let disposed = false
    let timer: ReturnType<typeof setTimeout> | undefined
    let controller: AbortController | undefined
    let observedJobId: string | null = null
    let resolvedJobId: string | null = null
    let lastSentKey: string | null = null

    const send = (payload: TrayProgressPayload) => {
      const key = JSON.stringify(payload)
      if (key === lastSentKey) return
      lastSentKey = key
      updateTray(payload)
    }

    const poll = async (signal: AbortSignal) => {
      const active = await api.activeJob(signal)
      if (disposed) return
      if (active) {
        observedJobId = active.job_id
        resolvedJobId = null
        send(payloadFromJob(active))
        return
      }
      if (!observedJobId) {
        // A historical folder Job on cold start is not an active session.
        send({ status: 'IDLE', currentFile: null, currentProgress: null })
        return
      }
      if (resolvedJobId === observedJobId) return
      const lookupId = observedJobId
      const terminal = await api.job(lookupId, signal)
      if (disposed || observedJobId !== lookupId || !TERMINAL_STATES.has(terminal.status)) return
      resolvedJobId = lookupId
      send(payloadFromJob(terminal))
    }

    const tick = () => {
      controller = new AbortController()
      poll(controller.signal)
        .catch(() => {
          // Offline/starting backend: do not infer failure; keep the last
          // confirmed tooltip and retry on the next tick.
        })
        .finally(() => {
          if (!disposed) timer = setTimeout(tick, TRAY_POLL_INTERVAL_MS)
        })
    }
    tick()

    return () => {
      disposed = true
      if (timer !== undefined) clearTimeout(timer)
      controller?.abort()
    }
  }, [])
}
