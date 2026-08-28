import { useEffect, useRef } from 'react'
import { isPermissionGranted, requestPermission, sendNotification } from '@tauri-apps/plugin-notification'
import { api, type StructuredEvent } from '../api/client'
import { isTauri } from '../lib/native'

const RELEVANT_INTENTS = new Set(['FILE_COMPLETED', 'JOB_COMPLETED'])
const POLL_INTERVAL_MS = 4000

function eventKey(event: StructuredEvent): string {
  return `${event.desktop_intent}|${event.job_id ?? ''}|${event.timestamp}|${event.message}`
}

/**
 * Turns the backend's FILE_COMPLETED / JOB_COMPLETED application events
 * into real OS notifications. The backend already only emits these events
 * when the corresponding notifications.* setting is enabled, so no extra
 * settings check is needed here. Runs once at the app root so it fires
 * regardless of which page is active.
 */
export function useDesktopNotifications(): void {
  const seen = useRef<Set<string>>(new Set())
  const initialized = useRef(false)
  const permissionGranted = useRef(false)

  useEffect(() => {
    if (!isTauri()) return
    let active = true

    async function ensurePermission(): Promise<boolean> {
      if (permissionGranted.current) return true
      let granted = await isPermissionGranted()
      if (!granted) {
        granted = (await requestPermission()) === 'granted'
      }
      permissionGranted.current = granted
      return granted
    }

    async function poll() {
      let events: StructuredEvent[]
      try {
        events = await api.events()
      } catch {
        return
      }
      if (!active) return
      const relevant = events.filter((event) => event.desktop_intent && RELEVANT_INTENTS.has(event.desktop_intent))

      if (!initialized.current) {
        for (const event of relevant) seen.current.add(eventKey(event))
        initialized.current = true
        return
      }

      const unseen = relevant.filter((event) => !seen.current.has(eventKey(event)))
      if (unseen.length === 0) return
      const granted = await ensurePermission()
      for (const event of unseen) {
        seen.current.add(eventKey(event))
        if (granted) sendNotification({ title: 'Sorigul', body: event.message })
      }
    }

    void poll()
    const timer = window.setInterval(() => void poll(), POLL_INTERVAL_MS)
    return () => {
      active = false
      window.clearInterval(timer)
    }
  }, [])
}
