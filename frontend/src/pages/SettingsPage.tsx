import { useEffect, useState } from 'react'
import { Bell, MonitorCog, Power, Server, XCircle } from 'lucide-react'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'

type ShutdownOption = 'off' | 'now' | '15' | '30'

export function SettingsPage() {
  const [fileNotification, setFileNotification] = useState(true)
  const [batchNotification, setBatchNotification] = useState(true)
  const [closeToTray, setCloseToTray] = useState(true)
  const [shutdownOption, setShutdownOption] = useState<ShutdownOption>('off')
  const [countdown, setCountdown] = useState<number | null>(null)

  useEffect(() => {
    if (countdown === null || countdown <= 0) return
    const timerId = window.setTimeout(() => setCountdown((value) => (value === null ? null : value - 1)), 1000)
    return () => window.clearTimeout(timerId)
  }, [countdown])

  function previewShutdown() {
    if (shutdownOption === 'off') return
    setCountdown(shutdownOption === 'now' ? 5 : Number(shutdownOption))
  }

  return (
    <div className="feature-page settings-page">
      <div className="page-intro">
        <div>
          <p className="eyebrow">Desktop UX</p>
          <h2>알림과 종료 동작을 설정하세요</h2>
          <p>알림, 창 닫기, 완료 후 종료 동작을 선택할 수 있습니다.</p>
        </div>
      </div>

      <div className="settings-grid">
        <Card className="settings-card">
          <div className="settings-card-heading"><Bell aria-hidden="true" /><div><h3>Notification</h3><p>완료 시 필요한 알림만 받습니다.</p></div></div>
          <label className="setting-row"><span><strong>파일 완료 알림</strong><small>각 파일의 결과 검증이 끝나면 알림</small></span><input type="checkbox" checked={fileNotification} onChange={(event) => setFileNotification(event.target.checked)} /></label>
          <label className="setting-row"><span><strong>전체 완료 알림</strong><small>성공과 실패 수를 구분해 알림</small></span><input type="checkbox" checked={batchNotification} onChange={(event) => setBatchNotification(event.target.checked)} /></label>
        </Card>

        <Card className="settings-card">
          <div className="settings-card-heading"><MonitorCog aria-hidden="true" /><div><h3>Tray</h3><p>창을 닫을 때의 동작을 명확히 합니다.</p></div></div>
          <label className="setting-row"><span><strong>실행 중 창을 닫으면 Tray로 이동</strong><small>Tray에서 앱 열기 또는 완전 종료 가능</small></span><input type="checkbox" checked={closeToTray} onChange={(event) => setCloseToTray(event.target.checked)} /></label>
          <div className="setting-note"><Badge tone={closeToTray ? 'done' : 'waiting'}>{closeToTray ? 'Tray로 숨김' : '종료 확인 표시'}</Badge><span>앱이 실행 중인 동안 Tray에서 다시 열거나 완전히 종료할 수 있습니다.</span></div>
        </Card>

        <Card className="settings-card settings-card-wide">
          <div className="settings-card-heading"><Power aria-hidden="true" /><div><h3>완료 후 PC 종료</h3><p>전체 작업 종료 후 선택한 시간에 종료합니다.</p></div></div>
          <div className="shutdown-options" role="radiogroup" aria-label="완료 후 PC 종료 시간">
            {([
              ['off', '사용 안 함'],
              ['now', '즉시'],
              ['15', '15초 후'],
              ['30', '30초 후'],
            ] as Array<[ShutdownOption, string]>).map(([value, label]) => (
              <label key={value} className={shutdownOption === value ? 'radio-option radio-option-selected' : 'radio-option'}>
                <input type="radio" name="shutdown" value={value} checked={shutdownOption === value} onChange={() => { setShutdownOption(value); setCountdown(null) }} />
                {label}
              </label>
            ))}
          </div>
          <Button variant="secondary" disabled={shutdownOption === 'off'} onClick={previewShutdown}>Countdown 미리보기</Button>
          {countdown !== null ? (
            <div className="countdown-panel" role="status">
              <strong className="text-numeric">{Math.max(countdown, 0)}초 후 PC를 종료합니다.</strong>
              <span>{countdown === 0 ? '종료 시점입니다. 종료 전에는 언제든 취소할 수 있습니다.' : '저장된 결과는 유지됩니다.'}</span>
              <Button variant="secondary" onClick={() => setCountdown(null)}><XCircle aria-hidden="true" /> 종료 취소</Button>
            </div>
          ) : null}
        </Card>

        <Card className="settings-card settings-card-wide">
          <div className="settings-card-heading"><Server aria-hidden="true" /><div><h3>Backend / Runtime</h3><p>시작과 연결 실패 상태를 사용자가 이해할 수 있게 표시합니다.</p></div></div>
          <div className="runtime-state-grid">
            <div><Badge tone="preparing">Backend 시작 중</Badge><span>앱 실행 후 준비 상태 확인</span></div>
            <div><Badge tone="failed">Backend 연결 실패</Badge><span>자동 시작 또는 앱 준비 상태 확인 실패</span></div>
            <div><Badge tone="cancelled">Backend 오프라인</Badge><span>전사를 시작할 수 없음</span></div>
          </div>
          <Button variant="secondary">다시 연결</Button>
        </Card>
      </div>
    </div>
  )
}
