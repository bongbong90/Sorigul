import { useEffect, useRef, useState } from 'react'
import { api, getUserMessage, isRequestAbort, type DriveFolderPage, type RuntimeSettings } from '../api/client'
import { Button } from './ui/Button'

export function DriveFolderPicker({ settings, disabled, onSaved }: {
  settings: RuntimeSettings
  disabled: boolean
  onSaved: (settings: RuntimeSettings) => void
}) {
  const [opened, setOpened] = useState(false)
  const [page, setPage] = useState<DriveFolderPage>()
  const [busy, setBusy] = useState<'loading' | 'saving' | null>(null)
  const [confirming, setConfirming] = useState(false)
  const [message, setMessage] = useState('')
  const serial = useRef(0)
  const controller = useRef<AbortController | null>(null)

  useEffect(() => () => { serial.current++; controller.current?.abort() }, [])
  useEffect(() => {
    if (disabled) {
      serial.current++; controller.current?.abort()
      setPage(undefined); setConfirming(false); setBusy(null)
    }
  }, [disabled])

  async function browse(folderId = 'root', accountId?: string, token?: string) {
    controller.current?.abort()
    const request = new AbortController()
    controller.current = request
    const ticket = ++serial.current
    setBusy('loading'); setMessage(''); setConfirming(false)
    if (!token) setPage(undefined)
    try {
      const next = await api.driveFolders(folderId, accountId, token, request.signal)
      if (ticket !== serial.current) return
      setPage(previous => token && previous?.folder.folder_id === next.folder.folder_id
        && previous.account_id === next.account_id
        ? { ...next, children: [...previous.children, ...next.children] } : next)
    } catch (cause) {
      if (ticket === serial.current && !isRequestAbort(cause)) {
        setPage(undefined); setMessage(getUserMessage(cause))
      }
    } finally { if (ticket === serial.current) setBusy(null) }
  }

  function close() {
    if (busy === 'saving') return
    serial.current++; controller.current?.abort()
    setOpened(false); setPage(undefined); setBusy(null); setConfirming(false); setMessage('')
  }

  async function persist(reset = false) {
    if (disabled || busy || (!reset && (!page || !confirming))) return
    const ticket = ++serial.current
    setBusy('saving'); setMessage('')
    try {
      const saved = reset ? await api.resetDriveDestination()
        : await api.selectDriveDestination(page!.folder.folder_id, page!.account_id)
      if (ticket !== serial.current) return
      onSaved(saved); setOpened(false); setPage(undefined); setConfirming(false)
      setMessage(reset ? '기본 저장 위치로 되돌렸습니다.' : 'Google Drive 저장 위치를 저장했습니다.')
    } catch (cause) {
      if (ticket !== serial.current) return
      setMessage(getUserMessage(cause))
      // A timed-out mutation may have persisted. Show authoritative settings
      // when available; never pretend an optimistic destination was saved.
      try {
        const saved = await api.settings()
        if (ticket === serial.current) onSaved(saved)
      } catch { /* retain the original failure/uncertain-result message */ }
    } finally { if (ticket === serial.current) setBusy(null) }
  }

  const location = settings.drive_parent?.display_path || '내 드라이브 (기본 위치)'
  const preview = page?.breadcrumbs.map(part => part.name).join(' / ')
  const suffix = '과정 / [단계] 과목 / 과정_과목_N주차'
  const currentRoot = settings.drive_parent?.layout === 'transcript_root'
    ? location : `${location} / ${settings.drive_exam_root} / 전사자료`
  return <div className="drive-destination">
    <div className="setting-note"><strong>현재 저장 위치</strong><span>{currentRoot}</span>
      <small>{suffix} 아래에 TXT·JSON·SRT를 저장합니다.</small>
      <small>변경한 위치는 새 작업에 적용됩니다. 기존 작업의 저장 위치는 유지됩니다.</small>
    </div>
    <div className="inline-actions">
      <Button variant="secondary" disabled={disabled || busy !== null || opened} onClick={() => { setOpened(true); void browse() }}>저장 위치 선택</Button>
      <Button variant="secondary" disabled={disabled || busy !== null || opened || !settings.drive_parent} onClick={() => void persist(true)}>기본 위치로 되돌리기</Button>
    </div>
    {message ? <p role="status">{message}</p> : null}
    {opened ? <section role="dialog" aria-modal="false" aria-label="Google Drive 저장 폴더 선택" className="drive-folder-dialog">
      <h4>Google Drive 저장 폴더 선택</h4>
      {disabled ? <p role="alert">Google Drive 또는 Backend 연결이 끊겼습니다. 다시 연결한 뒤 선택해 주세요.</p> : null}
      <nav aria-label="Drive 폴더 경로">{page?.breadcrumbs.map((part, index) => <span key={part.folder_id}>
        {index > 0 ? ' / ' : ''}<button type="button" disabled={disabled || busy !== null} onClick={() => void browse(part.folder_id, page.account_id)}>{part.name}</button>
      </span>)}</nav>
      {busy === 'loading' ? <p role="status">폴더를 불러오는 중입니다.</p> : null}
      {page ? <>
        <ul className="drive-folder-list">{page.children.map(folder => <li key={folder.folder_id}>
          <button type="button" disabled={disabled || busy !== null} aria-label={`${folder.name} 폴더 열기 (${folder.folder_id})`} onClick={() => void browse(folder.folder_id, page.account_id)}>
            <strong>{folder.name}</strong><small>폴더 ID: {folder.folder_id}{folder.can_select ? '' : ' · 저장 권한 없음'}</small>
          </button>
        </li>)}</ul>
        {page.children.length === 0 ? <p>하위 폴더가 없습니다.</p> : null}
        {page.next_page_token ? <Button variant="secondary" disabled={disabled || busy !== null} onClick={() => void browse(page.folder.folder_id, page.account_id, page.next_page_token!)}>폴더 더 보기</Button> : null}
        <p>업로드 경로: {preview} / {suffix} / TXT·JSON·SRT</p>
        {confirming ? <div className="setting-note" role="status"><strong>이 폴더를 상위 저장 위치로 사용하시겠습니까?</strong><span>{preview}</span><small>폴더 ID: {page.folder.folder_id}</small></div> : null}
        {!page.folder.can_select ? <p role="alert">이 폴더에 저장할 권한이 없습니다.</p> : null}
        <div className="inline-actions">
          {confirming ? <Button disabled={disabled || busy !== null} onClick={() => void persist()}>확인 후 저장</Button>
            : <Button disabled={disabled || busy !== null || !page.folder.can_select} onClick={() => setConfirming(true)}>이 폴더 선택</Button>}
        </div>
      </> : busy === null ? <Button variant="secondary" disabled={disabled} onClick={() => void browse()}>내 드라이브부터 다시 탐색</Button> : null}
      <Button variant="secondary" disabled={busy === 'saving'} onClick={close}>취소</Button>
    </section> : null}
  </div>
}
