import { useEffect, useRef, useState } from 'react'
import { api, getUserMessage, isRequestAbort, type JobModel } from '../../api/client'
import { Button } from '../ui/Button'
import { Card } from '../ui/Card'

export function NotebookImportPanel({ scanId, itemId, filename, onImported }: {
  scanId: string; itemId: string; filename: string; onImported: () => void
}) {
  const [archive, setArchive] = useState<File>()
  const [job, setJob] = useState<JobModel>()
  const [busy, setBusy] = useState(false)
  const [requested, setRequested] = useState(false)
  const [message, setMessage] = useState('원본 MP3를 선택한 뒤 Notebook에서 다운로드한 결과 ZIP을 가져오세요.')
  const importEpoch = useRef(0)
  const stem = filename.replace(/\.mp3$/i, '')
  const drive = job?.drive[stem]
  const terminalFailure = drive && ['FAILED', 'AUTH_REQUIRED', 'CLASSIFICATION_FAILED'].includes(drive.status)
  const inFlight = requested && !terminalFailure && drive?.status !== 'DONE'
  useEffect(() => {
    const controller = new AbortController()
    const epoch = importEpoch.current
    void api.notebookImportJob(scanId, itemId, controller.signal).then(previous => {
      if (!controller.signal.aborted && epoch === importEpoch.current) setJob(previous ?? undefined)
    }).catch(cause => { if (!isRequestAbort(cause)) setMessage(getUserMessage(cause)) })
    return () => controller.abort()
  }, [scanId, itemId])

  async function importResult() {
    if (!archive || busy) return
    importEpoch.current += 1
    setBusy(true)
    try {
      const imported = await api.importNotebook(scanId, itemId, archive)
      setJob(imported); setRequested(false)
      setMessage('가져오기 완료. 원본 MP3와 결과를 검증했습니다. Drive 전송은 별도 요청입니다.')
      onImported()
    } catch (cause) { setMessage(getUserMessage(cause)) }
    finally { setBusy(false) }
  }

  async function upload() {
    if (!job || busy || inFlight || drive?.status === 'DONE') return
    setBusy(true); setRequested(true)
    try { setJob(await api.uploadNotebookResult(job.job_id)); setMessage('Drive 전송을 요청했습니다. 상태 확인으로 결과를 확인하세요.') }
    catch (cause) { setMessage(`${getUserMessage(cause)} 상태 확인 후 다시 요청하세요.`) }
    finally { setBusy(false) }
  }

  async function checkStatus() {
    if (!job || busy) return
    setBusy(true)
    try {
      const fresh = await api.job(job.job_id)
      setJob(fresh)
      if (!fresh.drive[stem] || fresh.drive[stem].status === 'DISABLED') setRequested(false)
    }
    catch (cause) { setMessage(getUserMessage(cause)) }
    finally { setBusy(false) }
  }

  return <Card>
    <h2 className="text-section-heading">Notebook 결과 가져오기</h2>
    <p>원본: {filename} · 기존 TXT/JSON/SRT는 덮어쓰지 않습니다.</p>
    <label>Notebook 결과 ZIP <input type="file" accept=".zip,application/zip" disabled={busy} onChange={event => setArchive(event.target.files?.[0])} /></label>
    <div className="inline-actions">
      <Button disabled={!archive || busy || Boolean(job)} onClick={() => void importResult()}>결과 가져오기</Button>
      <Button variant="secondary" disabled={!job || busy || inFlight || drive?.status === 'DONE' || drive?.status === 'UPLOADING' || drive?.status === 'PENDING'} onClick={() => void upload()}>{terminalFailure ? 'Drive 전송 재시도' : 'Drive로 전송'}</Button>
      <Button variant="secondary" disabled={!job || busy} onClick={() => void checkStatus()}>전송 상태 확인</Button>
    </div>
    <p role="status">{message}</p>
    {job ? <p>결과 가져오기: 완료 · Drive: {drive?.status === 'DONE' ? '완료' : terminalFailure ? '전송 실패 — 가져온 결과는 보존됩니다.' : inFlight || drive?.status === 'UPLOADING' || drive?.status === 'PENDING' ? '전송 중' : '전송 전'} {drive?.error ?? ''}</p> : null}
  </Card>
}
