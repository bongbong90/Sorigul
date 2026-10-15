import { useEffect, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

/** Keep callbacks with the page; render their one control group in the shell. */
export function HeaderActions({ active, children }: { active: boolean; children: ReactNode }) {
  const [target, setTarget] = useState<HTMLElement | null>(null)
  useEffect(() => { setTarget(document.getElementById('transcription-header-actions')) }, [])
  if (!active) return null
  // Standalone component previews can render without AppShell.
  return target ? createPortal(children, target) : children
}
