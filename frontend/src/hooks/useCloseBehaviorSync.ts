import { useEffect } from 'react'
import { invoke } from '@tauri-apps/api/core'
import { api } from '../api/client'
import { isTauri } from '../lib/native'

const RETRY_INTERVAL_MS = 2000

/**
 * Rust caches close_behavior so the window "close" handler never needs a
 * blocking HTTP call. This keeps that cache correct from app startup
 * regardless of which page is active -- SettingsPage's own sync only runs
 * while that page happens to be mounted, which isn't true if the user
 * closes the window from any other screen without ever visiting Settings.
 * Retries until the backend is reachable, then stops.
 */
export function useCloseBehaviorSync(): void {
  useEffect(() => {
    if (!isTauri()) return
    let active = true
    let synced = false

    async function sync() {
      if (synced) return
      try {
        const settings = await api.settings()
        if (!active) return
        synced = true
        await invoke('set_close_behavior', { behavior: settings.close_behavior })
      } catch {
        // Backend not ready yet; retry on the next tick.
      }
    }

    void sync()
    const timer = window.setInterval(() => void sync(), RETRY_INTERVAL_MS)
    return () => {
      active = false
      window.clearInterval(timer)
    }
  }, [])
}
