import { useEffect, useRef } from 'react'
import { api } from '../api/client'
import { startFolderRevisionWatcher } from '../lib/folderRevisionWatcher'

// Watches only the one selected transcription folder (#111). `onChanged`
// must only re-read disk truth (scan/refresh) -- never create, start, retry
// or re-transcribe a Job. While `paused`, no polling happens; the first poll
// after un-pausing on the same folder reconciles once so a change made in the
// meantime is not lost. Changing the folder or unmounting stops the old loop
// and aborts its in-flight request, so a late response cannot touch the new
// folder's view.
export function useFolderRevision(
  folder: string,
  onChanged: (signal: AbortSignal) => Promise<void>,
  paused = false,
): void {
  const onChangedRef = useRef(onChanged)
  const deferredFolderRef = useRef<string | null>(null)

  useEffect(() => { onChangedRef.current = onChanged }, [onChanged])

  useEffect(() => {
    if (!folder) return
    if (paused) {
      deferredFolderRef.current = folder
      return
    }
    const reconcileOnStart = deferredFolderRef.current === folder
    deferredFolderRef.current = null
    const watcher = startFolderRevisionWatcher({
      fetchRevision: async (signal) => (await api.folderRevision(folder, signal)).revision,
      onChanged: (signal) => onChangedRef.current(signal),
      reconcileOnStart,
    })
    return () => watcher.stop()
  }, [folder, paused])
}
