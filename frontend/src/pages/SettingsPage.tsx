import { useCallback, useEffect, useRef, useState } from 'react'
import { invoke } from '@tauri-apps/api/core'
import { Bell, Cloud, MonitorCog, Power, Server, XCircle } from 'lucide-react'
import { api, getUserMessage, type DriveAuthState, type RuntimeSettings, type ShutdownState } from '../api/client'
import { isTauri, openInBrowser } from '../lib/native'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'

const defaults: RuntimeSettings = {
  notifications: { file_complete: true, job_complete: true },
  close_behavior: 'tray', shutdown: 'disabled',
}
const shutdownOptions: Array<[RuntimeSettings['shutdown'], string]> = [
  ['disabled', '사용 안 함'], ['immediate', '즉시'], ['15_seconds', '15초 후'], ['30_seconds', '30초 후'],
]
const driveAuthLabel: Record<DriveAuthState, string> = {
  UNAUTHENTICATED: '연결 안 됨', AUTHORIZING: '인증 진행 중', CONNECTED: '연결됨',
  REFRESH_FAILED: '갱신 실패 · 재연결 필요', REAUTH_REQUIRED: '재연결 필요',
}

export function SettingsPage() {
  const [settings, setSettings] = useState<RuntimeSettings>(defaults)
  const [shutdown, setShutdown] = useState<ShutdownState>()
  const [driveAuth, setDriveAuth] = useState<DriveAuthState>()
  const [driveMessage, setDriveMessage] = useState<string>()
  const drivePolling = useRef(false)
  const [backend, setBackend] = useState<'STARTING' | 'CONNECTED' | 'OFFLINE'>('STARTING')
  const [message, setMessage] = useState('설정을 불러오는 중입니다.')
  const shutdownTriggered = useRef(false)

  const load = useCallback(async () => {
    setBackend('STARTING')
    try {
      await api.health()
      const [saved, state, drive] = await Promise.all([api.settings(), api.shutdown(), api.driveStatus()])
      setSettings(saved); setShutdown(state); setDriveAuth(drive.auth_state); setBackend('CONNECTED'); setMessage('저장된 설정을 불러왔습니다.')
    } catch (cause) { setBackend('OFFLINE'); setMessage(getUserMessage(cause)) }
  }, [])

  useEffect(() => { void load() }, [load])
  useEffect(() => {
    if (backend !== 'CONNECTED') return
    const timer = window.setInterval(async () => {
      try { setShutdown(await api.shutdown()) } catch { setBackend('OFFLINE') }
    }, 1000)
    return () => window.clearInterval(timer)
  }, [backend])

  // Tauri caches close_behavior synchronously so the window "close" handler
  // never has to make a blocking HTTP call.
  useEffect(() => {
    if (!isTauri()) return
    void invoke('set_close_behavior', { behavior: settings.close_behavior }).catch(() => {})
  }, [settings.close_behavior])

  // Native shutdown boundary: only fires from the ready_to_shutdown phase,
  // re-confirms with a fresh read right before executing (stale-poll/cancel
  // race guard), and is additionally idempotent on the Rust side.
  useEffect(() => {
    if (!isTauri()) return
    if (shutdown?.phase === 'ready_to_shutdown' && !shutdownTriggered.current) {
      shutdownTriggered.current = true
      void (async () => {
        try {
          const fresh = await api.shutdown()
          setShutdown(fresh)
          if (fresh.phase === 'ready_to_shutdown') await invoke('native_shutdown')
          else shutdownTriggered.current = false
        } catch { shutdownTriggered.current = false }
      })()
    }
    if (shutdownTriggered.current && (shutdown?.phase === 'inactive' || shutdown?.phase === 'cancelled')) {
      shutdownTriggered.current = false
      void invoke('reset_shutdown_gate').catch(() => {})
    }
  }, [shutdown?.phase])

  async function save(next: RuntimeSettings) {
    setSettings(next); setMessage('설정을 저장하는 중입니다.')
    try { setSettings(await api.saveSettings(next)); setMessage('설정이 저장되었습니다.') }
    catch (cause) { setMessage(getUserMessage(cause)) }
  }

  async function cancelShutdown() {
    try { setShutdown(await api.cancelShutdown()); setMessage('PC 종료 요청을 취소했습니다.') }
    catch (cause) { setMessage(getUserMessage(cause)) }
  }

  async function connectDrive() {
    setDriveMessage('Google 인증 페이지를 여는 중입니다.')
    try {
      const result = await api.startDriveAuth()
      if (isTauri()) {
        await openInBrowser(result.authorization_url)
        setDriveMessage('브라우저에서 Google 인증을 완료해 주세요. 완료되면 자동으로 연결됩니다.')
        void pollDriveStatus()
      } else {
        setDriveMessage(`인증 URL: ${result.authorization_url}`)
      }
    } catch (cause) { setDriveMessage(getUserMessage(cause)) }
  }

  // The backend now completes the OAuth handoff itself via a loopback
  // callback listener (dynamic 127.0.0.1 port) once the system browser
  // redirects back -- no code is ever pasted into the UI. This polls the
  // existing status endpoint until that happens, times out, or fails.
  async function pollDriveStatus() {
    if (drivePolling.current) return
    drivePolling.current = true
    try {
      for (let attempt = 0; attempt < 150; attempt += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 2000))
        try {
          const drive = await api.driveStatus()
          setDriveAuth(drive.auth_state)
          if (drive.auth_state === 'CONNECTED') { setDriveMessage('Google Drive 연결이 완료되었습니다.'); return }
          if (drive.auth_state === 'REAUTH_REQUIRED' || drive.auth_state === 'REFRESH_FAILED') {
            setDriveMessage('Google Drive 연결에 실패했습니다. 다시 시도해 주세요.'); return
          }
        } catch { /* transient backend hiccup during polling; keep trying */ }
      }
      setDriveMessage('Google Drive 인증 대기 시간이 초과되었습니다. 다시 시도해 주세요.')
    } finally {
      drivePolling.current = false
    }
  }

  const countdownVisible = shutdown?.phase === 'counting_down' || shutdown?.phase === 'ready_to_shutdown'
  return (
    <div className="feature-page settings-page">
      <div className="page-intro"><div><p className="eyebrow">Desktop UX</p><h2>알림과 종료 동작을 설정하세요</h2><p>{message}</p></div></div>
      <div className="settings-grid">
        <Card className="settings-card"><div className="settings-card-heading"><Bell aria-hidden="true" /><div><h3>Notification</h3><p>완료 시 필요한 알림 요청만 만듭니다.</p></div></div>
          <label className="setting-row"><span><strong>파일 완료 알림</strong><small>각 파일의 결과 검증이 끝나면 Desktop 알림 요청</small></span><input type="checkbox" checked={settings.notifications.file_complete} onChange={(event) => void save({ ...settings, notifications: { ...settings.notifications, file_complete: event.target.checked } })} /></label>
          <label className="setting-row"><span><strong>전체 완료 알림</strong><small>성공과 실패 수를 구분한 Desktop 알림 요청</small></span><input type="checkbox" checked={settings.notifications.job_complete} onChange={(event) => void save({ ...settings, notifications: { ...settings.notifications, job_complete: event.target.checked } })} /></label>
        </Card>
        <Card className="settings-card"><div className="settings-card-heading"><MonitorCog aria-hidden="true" /><div><h3>Tray</h3><p>창을 닫을 때 Desktop runtime이 소비할 동작입니다.</p></div></div>
          <label className="setting-row"><span><strong>실행 중 창을 닫으면 Tray로 이동</strong><small>실제 hide/show는 Tauri runtime에서 수행</small></span><input type="checkbox" checked={settings.close_behavior === 'tray'} onChange={(event) => void save({ ...settings, close_behavior: event.target.checked ? 'tray' : 'exit' })} /></label>
          <div className="setting-note"><Badge tone={settings.close_behavior === 'tray' ? 'done' : 'waiting'}>{settings.close_behavior === 'tray' ? 'Tray로 숨김' : '앱 종료'}</Badge><span>{isTauri() ? 'Tauri runtime이 실제 창 hide/show를 수행합니다.' : '웹 개발 모드에서는 실제 OS 동작을 수행하지 않습니다.'}</span></div>
        </Card>
        <Card className="settings-card settings-card-wide"><div className="settings-card-heading"><Power aria-hidden="true" /><div><h3>완료 후 PC 종료</h3><p>정상 완료 Job 뒤 application countdown을 준비합니다.</p></div></div>
          <div className="shutdown-options" role="radiogroup" aria-label="완료 후 PC 종료 시간">{shutdownOptions.map(([value, label]) => <label key={value} className={settings.shutdown === value ? 'radio-option radio-option-selected' : 'radio-option'}><input type="radio" name="shutdown" value={value} checked={settings.shutdown === value} onChange={() => void save({ ...settings, shutdown: value })} />{label}</label>)}</div>
          {countdownVisible ? <div className="countdown-panel" role="status"><strong className="text-numeric">{shutdown.phase === 'ready_to_shutdown' ? '종료 준비 완료' : `${shutdown.remaining_seconds ?? 0}초 후 PC 종료 요청`}</strong><span>{isTauri() ? '준비 완료 시 실제 Windows 종료 명령이 실행됩니다.' : '웹 개발 모드에서는 실제 Windows 종료 명령을 실행하지 않습니다.'}</span><Button variant="secondary" onClick={() => void cancelShutdown()}><XCircle aria-hidden="true" /> 종료 취소</Button></div> : null}
          {shutdown?.phase === 'cancelled' ? <div className="setting-note"><Badge tone="cancelled">종료 취소됨</Badge><span>다음 정상 Job 완료 시 저장된 정책을 다시 적용합니다.</span></div> : null}
        </Card>
        <Card className="settings-card settings-card-wide"><div className="settings-card-heading"><Cloud aria-hidden="true" /><div><h3>Google Drive</h3><p>OAuth 인증 상태와 Desktop 브라우저 연결입니다.</p></div></div>
          <div className="runtime-state-grid"><div><Badge tone={driveAuth === 'CONNECTED' ? 'done' : driveAuth === 'AUTHORIZING' ? 'preparing' : driveAuth === 'REFRESH_FAILED' || driveAuth === 'REAUTH_REQUIRED' ? 'failed' : 'waiting'}>{driveAuth ? driveAuthLabel[driveAuth] : '확인 중'}</Badge><span>Scope: https://www.googleapis.com/auth/drive</span></div></div>
          <div className="inline-actions"><Button variant="secondary" disabled={!isTauri()} onClick={() => void connectDrive()}>Google Drive 연결</Button></div>
          {driveMessage ? <div className="setting-note"><span>{driveMessage}</span></div> : null}
          {!isTauri() ? <div className="setting-note"><span>웹 개발 모드에서는 브라우저 handoff를 수행하지 않습니다.</span></div> : null}
        </Card>
        <Card className="settings-card settings-card-wide"><div className="settings-card-heading"><Server aria-hidden="true" /><div><h3>Backend / Runtime</h3><p>실제 health 상태를 표시합니다.</p></div></div>
          <div className="runtime-state-grid"><div><Badge tone={backend === 'CONNECTED' ? 'done' : backend === 'STARTING' ? 'preparing' : 'failed'}>{backend === 'CONNECTED' ? 'Backend 연결됨' : backend === 'STARTING' ? 'Backend 시작 중' : 'Backend 오프라인'}</Badge><span>{backend === 'CONNECTED' ? '상태 확인 완료' : '전사를 시작할 수 없음'}</span></div></div>
          <Button variant="secondary" disabled={backend === 'STARTING'} onClick={() => void load()}>다시 연결</Button>
        </Card>
      </div>
    </div>
  )
}
