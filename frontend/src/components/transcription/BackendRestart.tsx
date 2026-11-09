import { useEffect, useRef, useState } from 'react'
import { getBackendRecoveryStatus, restartBackend, type BackendRecoveryStatus } from '../../lib/native'
import { Button } from '../ui/Button'

export function BackendRestart({ offline, onRecovered, onRestarting, onFailure }: {
  offline: boolean
  onRecovered: () => Promise<void>
  onRestarting?: (busy: boolean) => void
  onFailure?: (message: string) => void
}) {
  const [status, setStatus] = useState<BackendRecoveryStatus | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const running = useRef(false)
  useEffect(() => {
    let active = true
    let timer: number | undefined
    async function check() {
      try {
        const current = await getBackendRecoveryStatus()
        if (active) setStatus(current)
      } catch {
        if (active) setStatus(null)
      } finally {
        if (active) timer = window.setTimeout(() => void check(), 4000)
      }
    }
    if (offline) void check()
    return () => { active = false; if (timer !== undefined) window.clearTimeout(timer) }
  }, [offline])

  async function restart() {
    if (running.current || !status?.can_restart) return
    running.current = true
    onRestarting?.(true)
    setBusy(true)
    setError('')
    try {
      await restartBackend()
      await onRecovered()
    } catch (cause) {
      const code = String(cause)
      const current = await getBackendRecoveryStatus().catch(() => null)
      setStatus(current)
      const message = current?.message && !current.can_restart ? `${current.message} (${code})` : `Backend 다시 시작 또는 상태 동기화를 완료하지 못했습니다. (${code})`
      setError(message)
      onFailure?.(message)
    } finally {
      running.current = false
      onRestarting?.(false)
      setBusy(false)
    }
  }
  return <div>
    {(offline && status?.backend_exited || busy) ? <Button variant="secondary" disabled={busy || !status?.can_restart} onClick={() => void restart()}>{busy ? 'Backend 시작 중' : 'Backend 다시 시작'}</Button> : null}
    {error || offline && status?.message ? <p role="alert" className="text-caption">{error || status?.message}</p> : null}
  </div>
}
