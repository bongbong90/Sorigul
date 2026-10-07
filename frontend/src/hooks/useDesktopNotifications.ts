import { useEffect, useRef } from 'react'
import { isPermissionGranted, requestPermission, sendNotification } from '@tauri-apps/plugin-notification'
import { api, type StructuredEvent } from '../api/client'
import { isTauri, showCompletionToast, type CompletionIntent } from '../lib/native'

const RELEVANT_INTENTS = new Set<string>(['FILE_COMPLETED', 'JOB_COMPLETED'] satisfies CompletionIntent[])
const POLL_INTERVAL_MS = 4000

function eventKey(event: StructuredEvent): string {
  return `${event.desktop_intent}|${event.job_id ?? ''}|${event.timestamp}|${event.message}`
}

function oldestFirst(a: StructuredEvent, b: StructuredEvent): number {
  return Date.parse(a.timestamp) - Date.parse(b.timestamp)
}

/**
 * Turns the backend's FILE_COMPLETED / JOB_COMPLETED application events
 * into the Sorigul completion toast (Legacy TrayToastWindow parity: 폴더 열기 /
 * 확인). The backend already only emits these events when the corresponding
 * notifications.* setting is enabled, so no extra settings check is needed
 * here. Runs once at the app root so it fires regardless of which page is
 * active.
 *
 * Exactly one surface per event: the toast is the primary path, and a plain
 * OS notification (title/body only, no folder action) is used only when the
 * toast itself could not be shown.
 */
export function useDesktopNotifications(): void {
  const seen = useRef<Set<string>>(new Set())
  const initialized = useRef(false)
  const permissionGranted = useRef(false)

  useEffect(() => {
    if (!isTauri()) return
    let active = true
    let timer: number | undefined
    let controller: AbortController | undefined

    async function ensurePermission(): Promise<boolean> {
      if (permissionGranted.current) return true
      let granted = await isPermissionGranted()
      if (!granted) {
        granted = (await requestPermission()) === 'granted'
      }
      permissionGranted.current = granted
      return granted
    }

    async function notify(event: StructuredEvent) {
      try {
        await showCompletionToast({
          desktop_intent: event.desktop_intent as CompletionIntent,
          job_id: event.job_id ?? '',
          file_id: event.file_id ?? null,
          message: event.message,
        })
        return
      } catch (error) {
        console.warn(
          '[notifications] completion toast unavailable; degraded OS notification without folder action',
          String(error),
        )
      }
      if (await ensurePermission()) sendNotification({ title: 'Sorigul', body: event.message })
    }

    async function poll() {
      let events: StructuredEvent[]
      controller = new AbortController()
      try {
        events = await api.events(controller.signal)
      } catch {
        if (active) timer = window.setTimeout(() => void poll(), POLL_INTERVAL_MS)
        return
      }
      if (!active) return
      const relevant = events.filter((event) => event.desktop_intent && RELEVANT_INTENTS.has(event.desktop_intent))

      if (!initialized.current) {
        for (const event of relevant) seen.current.add(eventKey(event))
        initialized.current = true
        if (active) timer = window.setTimeout(() => void poll(), POLL_INTERVAL_MS)
        return
      }

      // Oldest first, so when several arrive in one poll the single reused
      // toast ends on the most recent one.
      const unseen = relevant.filter((event) => !seen.current.has(eventKey(event))).sort(oldestFirst)
      for (const event of unseen) {
        seen.current.add(eventKey(event))
        await notify(event)
        if (!active) return
      }
      if (active) timer = window.setTimeout(() => void poll(), POLL_INTERVAL_MS)
    }

    void poll()
    return () => {
      active = false
      if (timer !== undefined) window.clearTimeout(timer)
      controller?.abort()
    }
  }, [])
}
