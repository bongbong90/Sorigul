import { isTauri } from '@tauri-apps/api/core'
import { open as openDialog } from '@tauri-apps/plugin-dialog'
import { openPath, openUrl, revealItemInDir } from '@tauri-apps/plugin-opener'

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
 * Opens the backend-validated folder (or reveals a specific file within
 * it) in Windows Explorer. Only ever called with a path the backend has
 * already resolved and validated -- never an arbitrary frontend value.
 */
export async function openInExplorer(folder: string, itemFilename?: string | null): Promise<void> {
  if (!isTauri()) return
  if (itemFilename) {
    const separator = folder.endsWith('\\') || folder.endsWith('/') ? '' : '\\'
    await revealItemInDir(`${folder}${separator}${itemFilename}`)
  } else {
    await openPath(folder)
  }
}

/** Opens a URL in the user's default system browser (Drive OAuth handoff). */
export async function openInBrowser(url: string): Promise<void> {
  if (!isTauri()) return
  await openUrl(url)
}
