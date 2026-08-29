import { invoke, isTauri } from '@tauri-apps/api/core'
import { open as openDialog } from '@tauri-apps/plugin-dialog'
import { openUrl } from '@tauri-apps/plugin-opener'

export { isTauri }

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

/** Opens a URL in the user's default system browser (Drive OAuth handoff). */
export async function openInBrowser(url: string): Promise<void> {
  if (!isTauri()) return
  await openUrl(url)
}
