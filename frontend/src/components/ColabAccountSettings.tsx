import { useEffect, useState } from 'react'
import { Cloud } from 'lucide-react'
import { api, getUserMessage, isRequestAbort, type ColabAuthStatus } from '../api/client'
import { isTauri, openInBrowser } from '../lib/native'
import { Badge } from './ui/Badge'
import { Button } from './ui/Button'
import { Card } from './ui/Card'

const blockers: Record<string, string> = {
  FEATURE_DISABLED: '공식 Colab 전사는 현재 비활성화되어 있습니다.',
  COST_GATE_CONDITIONAL: '유료 자원 미사용 조건이 확인되지 않았습니다.',
  POLICY_GATE_NOT_VERIFIED: '자동 전사 이용 정책 적합성을 확인 중입니다.',
  ACCOUNT_NOT_CONNECTED: 'Colab 계정 연결을 확인해 주세요.',
  OWNERSHIP_UNRESOLVED: '이전 원격 작업의 소유권과 정리 상태를 확인해야 합니다.',
  PAID_OR_UNKNOWN_TIER: '유료 구독이거나 구독 상태가 확인되지 않았습니다.',
  GPU_UNAVAILABLE_OR_UNKNOWN: '무료 GPU 자원을 사용할 수 없거나 확인되지 않았습니다.',
  COLAB_ACCESS_UNVERIFIED: '공식 Colab API 접근 권한이 확인되지 않았습니다.',
}

export function ColabAccountSettings({ online, criticalWork }: { online: boolean; criticalWork: boolean }) {
  const [status, setStatus] = useState<ColabAuthStatus>()
  const [message, setMessage] = useState<string>()
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!online) return
    let active = true
    let timer: number | undefined
    let controller: AbortController | undefined
    const poll = async () => {
      controller = new AbortController()
      try {
        const next = await api.colabAuthStatus(controller.signal)
        if (active) setStatus(next)
      } catch (cause) {
        if (active && !isRequestAbort(cause)) setMessage(getUserMessage(cause))
      } finally {
        if (active) timer = window.setTimeout(() => void poll(), 1500)
      }
    }
    void poll()
    return () => { active = false; window.clearTimeout(timer); controller?.abort() }
  }, [online])

  async function connect() {
    setBusy(true)
    setMessage('기본 브라우저에서 Google Colab 인증을 여는 중입니다.')
    let started = false
    try {
      const result = await api.startColabAuth()
      started = true
      const url = new URL(result.authorization_url)
      if (url.origin !== 'https://accounts.google.com' || url.pathname !== '/o/oauth2/v2/auth') throw new Error('인증 주소를 확인하지 못했습니다.')
      await openInBrowser(result.authorization_url)
      setStatus(await api.colabAuthStatus())
      setMessage('브라우저에서 인증을 완료해 주세요. 계정 연결 후에도 전사 실행 조건을 별도로 확인합니다.')
    } catch (cause) {
      if (started) await api.cancelColabAuth().catch(() => {})
      setMessage(getUserMessage(cause))
    } finally { setBusy(false) }
  }

  async function action(kind: 'check' | 'cancel' | 'disconnect') {
    setBusy(true)
    setMessage(kind === 'check' ? 'Google 계정과 읽기 전용 접근 상태를 확인하고 있습니다.' : '연결 상태를 변경하고 있습니다.')
    try {
      const next = await (kind === 'check' ? api.checkColabAuth() : kind === 'cancel' ? api.cancelColabAuth() : api.disconnectColabAuth())
      setStatus(next)
      setMessage(kind === 'disconnect' ? 'Google Colab 연결을 해제했습니다.' : kind === 'cancel' ? '인증을 취소했습니다.' : '계정 확인을 마쳤습니다. 아래 전사 차단 사유를 확인해 주세요.')
    } catch (cause) { setMessage(getUserMessage(cause)) }
    finally { setBusy(false) }
  }

  const pending = status?.auth_state === 'AUTHORIZING'
  const disabled = !online || busy || criticalWork
  return (
    <Card className="settings-card settings-card-wide">
      <div className="settings-card-heading"><Cloud aria-hidden="true" /><div><h3>공식 Google Colab 계정</h3><p>Google Drive와 별도로 연결합니다. 계정 연결은 GPU 전사 실행 승인을 의미하지 않습니다.</p></div></div>
      <div className="runtime-state-grid"><div><Badge tone={status?.auth_state === 'CONNECTED' ? 'done' : pending ? 'preparing' : 'waiting'}>{status?.message ?? '연결 상태 확인 중'}</Badge><span>{status?.notice}</span></div></div>
      <div className="inline-actions">
        <Button variant="secondary" disabled={disabled || pending || !isTauri() || !status?.configured} onClick={() => void connect()}>Google Colab 연결</Button>
        <Button variant="secondary" disabled={disabled || pending || !status?.configured || status?.auth_state === 'DISCONNECTED'} onClick={() => void action('check')}>연결 상태 확인</Button>
        <Button variant="secondary" disabled={disabled || pending || !isTauri() || !status?.configured} onClick={() => void connect()}>다시 인증</Button>
        {pending ? <Button variant="secondary" disabled={!online || busy} onClick={() => void action('cancel')}>인증 취소</Button> : <Button variant="secondary" disabled={disabled || !status?.disconnect_allowed || status?.auth_state === 'DISCONNECTED'} onClick={() => void action('disconnect')}>연결 해제</Button>}
      </div>
      <div className="setting-note" role="status"><Badge tone="waiting">실행 조건 미확인</Badge><span>공식 Colab 전사 시작은 차단되어 있습니다.</span></div>
      <ul>{status?.blocking_reasons.map((reason) => <li key={reason}>{blockers[reason] ?? '전사 실행 조건 확인이 필요합니다.'}</li>)}</ul>
      {status?.preflight ? <p className="text-caption">읽기 전용 확인: {status.preflight.tier === 'FREE' ? '무료 구독 확인' : '구독 조건 확인 필요'} · {status.preflight.t4 === 'ELIGIBLE' ? 'T4 자원 후보 확인' : 'GPU 확인 필요'} · Runtime 생성 권한 미검증</p> : null}
      {message ? <div className="setting-note" role="status"><span>{message}</span></div> : null}
      {!isTauri() ? <p className="text-caption">계정 연결은 Desktop 앱의 기본 브라우저에서 진행합니다.</p> : null}
    </Card>
  )
}
