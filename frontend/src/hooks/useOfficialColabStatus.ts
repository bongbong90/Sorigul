import { useCallback, useEffect, useState } from 'react'
import { api, isRequestAbort } from '../api/client'
import type { OfficialColabStatus } from '../api/client'

// Shown while the backend has not answered (or is offline). Never "ready":
// automatic official Colab is only offered when the server says so (#245).
const UNKNOWN_STATUS: OfficialColabStatus = {
  state: 'DISABLED',
  available: false,
  reasons: [{ code: 'STATUS_UNKNOWN', message: '공식 Colab 자동 연결 상태를 확인하지 못했습니다.' }],
}

/**
 * Reads the server's official Colab readiness. No polling: refreshed on mount
 * and whenever `refreshKey` changes (e.g. the selected engine). The status
 * carries reasons only -- no credentials, account ids, Runtime names or URLs.
 */
export function useOfficialColabStatus(refreshKey?: unknown): {
  status: OfficialColabStatus
  refresh: (signal?: AbortSignal) => Promise<OfficialColabStatus>
} {
  const [status, setStatus] = useState<OfficialColabStatus>(UNKNOWN_STATUS)

  const refresh = useCallback(async (signal?: AbortSignal) => {
    try {
      const next = await api.officialColabStatus(signal)
      if (!signal?.aborted) setStatus(next)
      return next
    } catch (error) {
      if (!isRequestAbort(error) && !signal?.aborted) setStatus(UNKNOWN_STATUS)
      return UNKNOWN_STATUS
    }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    void refresh(controller.signal)
    return () => controller.abort()
  }, [refresh, refreshKey])

  return { status, refresh }
}
