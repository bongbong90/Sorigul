import { useEffect, useRef } from 'react'
import { api, type JobModel } from '../api/client'
import { setTrayProgress, type TrayProgressPayload } from '../lib/native'

const TERMINAL_STATES = new Set(['DONE', 'FAILED', 'CRASHED', 'STOPPED', 'CANCELLED'])

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
 * Reuses the page's existing Job snapshots. The only request here is a
 * one-shot terminal lookup when an observed active Future disappears before
 * the selected folder Job carries its terminal state.
 */
export function useTrayProgress(globalActiveJob: JobModel | null, folderJob?: JobModel): void {
  const lastObservedActiveJobIdRef = useRef<string | null>(null)
  const terminalLookupJobIdRef = useRef<string | null>(null)
  const resolvedTerminalJobIdRef = useRef<string | null>(null)

  useEffect(() => {
    if (globalActiveJob) {
      if (lastObservedActiveJobIdRef.current !== globalActiveJob.job_id) {
        resolvedTerminalJobIdRef.current = null
      }
      lastObservedActiveJobIdRef.current = globalActiveJob.job_id
      updateTray(payloadFromJob(globalActiveJob))
      return
    }

    const observedJobId = lastObservedActiveJobIdRef.current
    if (!observedJobId) {
      // A historical folder Job on cold start is not an active session.
      updateTray({ status: 'IDLE', currentFile: null, currentProgress: null })
      return
    }

    if (folderJob?.job_id === observedJobId && TERMINAL_STATES.has(folderJob.status)) {
      resolvedTerminalJobIdRef.current = observedJobId
      updateTray(payloadFromJob(folderJob))
      return
    }
    if (
      resolvedTerminalJobIdRef.current === observedJobId
      || terminalLookupJobIdRef.current === observedJobId
    ) return

    terminalLookupJobIdRef.current = observedJobId
    void api.job(observedJobId).then((terminalJob) => {
      if (
        lastObservedActiveJobIdRef.current !== observedJobId
        || !TERMINAL_STATES.has(terminalJob.status)
      ) return
      resolvedTerminalJobIdRef.current = observedJobId
      updateTray(payloadFromJob(terminalJob))
    }).catch(() => {
      // Do not infer failure from an offline backend. Keep the last confirmed
      // active tooltip until a real Job snapshot is available.
    }).finally(() => {
      if (terminalLookupJobIdRef.current === observedJobId) {
        terminalLookupJobIdRef.current = null
      }
    })
  }, [folderJob, globalActiveJob])
}
