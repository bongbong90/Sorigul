import { useEffect, useState } from 'react'
import { CheckCircle } from 'lucide-react'
import { Button } from '../ui/Button'
import {
  dismissCompletionToast,
  openNotificationFolder,
  watchCompletionToast,
  type CompletionIntent,
  type CompletionToast as CompletionToastPayload,
} from '../../lib/native'

const TITLES: Record<CompletionIntent, string> = {
  FILE_COMPLETED: '파일 전사 완료',
  JOB_COMPLETED: '전사 작업 종료',
}

function folderErrorMessage(error: unknown): string {
  return String(error).includes('HTTP 410') ? '전사 폴더를 찾을 수 없습니다.' : '폴더를 열 수 없습니다.'
}

/**
 * Content of the reusable `completion-toast` window (Legacy TrayToastWindow).
 * Showing, placement and auto-hide are owned by Rust; this view only renders
 * the latest payload and forwards 폴더 열기 / 확인.
 */
export function CompletionToast() {
  const [toast, setToast] = useState<CompletionToastPayload | null>(null)
  const [opening, setOpening] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let disposed = false
    let unlisten: (() => void) | undefined
    watchCompletionToast((next) => {
      if (disposed) return
      setToast((current) => (next && current && next.generation < current.generation ? current : next))
      setError(null)
      setOpening(false)
    })
      .then((stop) => {
        if (disposed) stop()
        else unlisten = stop
      })
      .catch((reason) => console.warn('[completion-toast] subscription failed', String(reason)))
    return () => {
      disposed = true
      unlisten?.()
    }
  }, [])

  async function handleOpenFolder() {
    if (!toast) return
    setOpening(true)
    setError(null)
    try {
      await openNotificationFolder(toast.job_id)
    } catch (reason) {
      setError(folderErrorMessage(reason))
    } finally {
      setOpening(false)
    }
  }

  return (
    <section className="completion-toast" role="status" aria-live="polite">
      <header className="completion-toast-header">
        <CheckCircle className="completion-toast-icon" aria-hidden="true" />
        <span className="text-caption">Sorigul</span>
      </header>
      <p className="text-card-title completion-toast-title">{toast ? TITLES[toast.desktop_intent] : ''}</p>
      {error ? (
        <p className="text-body completion-toast-error" role="alert">
          {error}
        </p>
      ) : (
        <p className="text-body completion-toast-message" title={toast?.message}>
          {toast?.message}
        </p>
      )}
      <div className="completion-toast-actions">
        <Button variant="secondary" onClick={() => void handleOpenFolder()} disabled={!toast || opening}>
          폴더 열기
        </Button>
        <Button onClick={() => void dismissCompletionToast()}>확인</Button>
      </div>
    </section>
  )
}
