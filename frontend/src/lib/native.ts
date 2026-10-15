import { invoke, isTauri } from '@tauri-apps/api/core'
import { listen } from '@tauri-apps/api/event'
import { getCurrentWindow } from '@tauri-apps/api/window'
import { open as openDialog } from '@tauri-apps/plugin-dialog'
import { openUrl } from '@tauri-apps/plugin-opener'

export { isTauri }

export interface SidecarStatus {
  state: 'STARTING' | 'CONNECTED' | 'STARTUP_FAILED'
  owned: boolean | null
  code: string | null
  message: string | null
}

/** Subscribe first, then read the latest snapshot so startup events cannot be lost. */
export async function watchSidecarStatus(
  onStatus: (status: SidecarStatus) => void,
): Promise<() => void> {
  if (!isTauri()) return () => {}
  const unlisten = await listen<SidecarStatus>('sorigul://sidecar-status', (event) => {
    onStatus(event.payload)
  })
  try {
    onStatus(await invoke<SidecarStatus>('get_sidecar_status'))
  } catch (error) {
    unlisten()
    throw error
  }
  return unlisten
}

export async function retrySidecarStartup(): Promise<void> {
  if (!isTauri()) return
  await invoke('retry_sidecar_startup')
}

/**
 * Native Windows folder picker when running under Tauri; falls back to a
 * text prompt in plain-browser development. Cancelling the picker is not
 * an error -- both paths resolve to `undefined`.
 */
export async function pickFolder(currentValue: string): Promise<string | undefined> {
  if (isTauri()) {
    const selected = await openDialog({ directory: true, multiple: false, defaultPath: currentValue || undefined })
    return typeof selected === 'string' ? selected : undefined
  }
  const value = window.prompt('전사 폴더 경로를 입력하세요.', currentValue)?.trim()
  return value || undefined
}

/**
 * Opens the backend-validated folder (or reveals a specific file within it)
 * in Windows Explorer. The frontend passes only the opaque scan_id and
 * optional item_id identifiers; the Rust `open_folder_by_intent` command
 * fetches the validated path from the backend and opens it natively.
 *
 * Security: the frontend never constructs or passes a raw filesystem path to
 * any native open call. `opener:allow-open-path` and
 * `opener:allow-reveal-item-in-dir` are NOT in the capability manifest.
 */
export async function openInExplorer(scanId: string, itemId?: string | null): Promise<void> {
  if (!isTauri()) return
  await invoke('open_folder_by_intent', { scanId, itemId: itemId ?? null })
}

/** Label of the single reusable completion toast window (tauri.conf.json). */
export const COMPLETION_TOAST_WINDOW = 'completion-toast'

export type CompletionIntent = 'FILE_COMPLETED' | 'JOB_COMPLETED'

/**
 * One completion event for the Sorigul toast. Opaque identities only: the
 * transcription folder is resolved by the backend from job_id when the user
 * clicks 폴더 열기, and never reaches the frontend.
 */
export interface CompletionToastRequest {
  desktop_intent: CompletionIntent
  job_id: string
  file_id: string | null
  message: string
}

export interface CompletionToast extends CompletionToastRequest {
  generation: number
}

export function isCompletionToastWindow(): boolean {
  return isTauri() && getCurrentWindow().label === COMPLETION_TOAST_WINDOW
}

/** Replaces the toast content and shows it; rejects if the toast cannot be shown. */
export async function showCompletionToast(request: CompletionToastRequest): Promise<void> {
  await invoke('show_completion_toast', { request })
}

/** Subscribe first, then read the current toast so the first event cannot be lost. */
export async function watchCompletionToast(
  onToast: (toast: CompletionToast | null) => void,
): Promise<() => void> {
  const unlisten = await listen<CompletionToast>('sorigul://completion-toast', (event) => {
    onToast(event.payload)
  })
  try {
    onToast(await invoke<CompletionToast | null>('get_completion_toast'))
  } catch (error) {
    unlisten()
    throw error
  }
  return unlisten
}

/** Toast 폴더 열기: the Rust command asks the backend for the Job's validated folder. */
export async function openNotificationFolder(jobId: string): Promise<void> {
  await invoke('open_notification_folder', { jobId })
}

export async function dismissCompletionToast(): Promise<void> {
  await invoke('dismiss_completion_toast')
}

/** Opens a URL in the user's default system browser (Drive OAuth handoff). */
export async function openInBrowser(url: string): Promise<void> {
  if (!isTauri()) return
  await openUrl(url)
}
