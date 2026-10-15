import { useCallback, useEffect, useMemo, useState } from 'react'
import { AlertTriangle, CheckCircle2, Cloud, FilePenLine, RefreshCw, WifiOff } from 'lucide-react'
import { api, getSavedFolder, getUserMessage, saveFolder, type JobModel, type NormalizationPreview, type ScannedFile } from '../api/client'
import { pickFolder } from '../lib/native'
import { CurrentTaskSection, type CurrentTaskStatus } from '../components/transcription/CurrentTaskSection'
import { FolderSection } from '../components/transcription/FolderSection'
import { QueueTable, type QueueRow, type QueueStatus } from '../components/transcription/QueueTable'
import { TranscriptionActions } from '../components/transcription/TranscriptionActions'
import { Badge, type BadgeTone } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'

type DialogKind = 'start-all' | 'empty-target' | 'retranscribe' | null
type BackendStatus = 'OFFLINE' | 'STARTING' | 'CONNECTED'
const ACTIVE_STATES = new Set(['WAITING', 'PREPARING', 'TRANSCRIBING', 'SAVING', 'VERIFYING', 'CANCEL_REQUESTED'])
const drivePresentation: Record<string, { label: string; tone: BadgeTone }> = {
  DISABLED: { label: 'Drive 사용 안 함', tone: 'waiting' }, AUTH_REQUIRED: { label: '인증 필요', tone: 'cancelled' },
  CLASSIFICATION_FAILED: { label: 'Drive 분류 실패', tone: 'failed' }, PENDING: { label: 'Drive 대기', tone: 'waiting' },
  UPLOADING: { label: 'Drive 업로드 중', tone: 'preparing' }, DONE: { label: 'Drive 완료', tone: 'done' },
  FAILED: { label: 'Drive 실패', tone: 'failed' },
}

function queueStatus(value: string): QueueStatus {
  return value as QueueStatus
}

function rowsFrom(files: ScannedFile[], job?: JobModel): QueueRow[] {
  return files.map((file) => {
    const local = job?.files[file.id] ?? (file.completion_status === 'DONE' ? 'DONE' : 'WAITING')
    const drive = job?.drive[file.id]
    const localDetail = file.completion_status === 'INVALID_RESULT' ? '기존 결과 bundle 검증 실패' : file.completion_status === 'DONE' ? '정상 TXT/JSON/SRT bundle' : undefined
    const driveDetail = drive && drive.status !== 'DISABLED' ? `${drivePresentation[drive.status]?.label ?? drive.status}${drive.error ? ` · ${drive.error}` : ''}` : undefined
    return { id: file.id, filename: file.filename, duration: '—', status: queueStatus(local), detail: [localDetail, driveDetail].filter(Boolean).join(' · ') || undefined }
  })
}

export function TranscriptionPage() {
  const [folder, setFolder] = useState(getSavedFolder)
  const [files, setFiles] = useState<ScannedFile[]>([])
  const [job, setJob] = useState<JobModel>()
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [backendStatus, setBackendStatus] = useState<BackendStatus>('STARTING')
  const [driveAuth, setDriveAuth] = useState('UNAUTHENTICATED')
  const [dialog, setDialog] = useState<DialogKind>(null)
  const [pendingIds, setPendingIds] = useState<string[]>([])
  const [message, setMessage] = useState('Backend 연결 상태를 확인하고 있습니다.')
  const [normalization, setNormalization] = useState<NormalizationPreview>()
  const [filenameValue, setFilenameValue] = useState('')
  const [filenameResolution, setFilenameResolution] = useState('')
  const [filenameMode, setFilenameMode] = useState<'review' | 'editing' | 'resolved'>('review')
  const [uploadToDrive, setUploadToDrive] = useState(false)
  const activeJobId = job?.job_id
  const activeJobStatus = job?.status

  const loadFolder = useCallback(async () => {
    if (!folder) { setFiles([]); setMessage('전사 폴더를 선택해 주세요.'); return }
    try {
      const [scanned, jobs, drive] = await Promise.all([api.scan(folder), api.jobs(), api.driveStatus()])
      const matching = jobs.filter((item) => item.folder === folder).sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at))[0]
      setFiles(scanned); setJob(matching); setUploadToDrive(matching?.upload_to_drive ?? false); setDriveAuth(drive.auth_state); setBackendStatus('CONNECTED'); setMessage(`실제 디스크에서 ${scanned.length}개 MP3를 확인했습니다.`)
    } catch (cause) { setBackendStatus('OFFLINE'); setMessage(getUserMessage(cause)) }
  }, [folder])

  const reconnect = useCallback(async () => {
    setBackendStatus('STARTING')
    try { await api.health(); await loadFolder() }
    catch (cause) { setBackendStatus('OFFLINE'); setMessage(getUserMessage(cause)) }
  }, [loadFolder])

  useEffect(() => { void reconnect() }, [reconnect])
  useEffect(() => {
    const healthTimer = window.setInterval(async () => {
      try { await api.health(); setBackendStatus('CONNECTED') } catch { setBackendStatus('OFFLINE') }
    }, 4000)
    return () => window.clearInterval(healthTimer)
  }, [])
  useEffect(() => {
    if (!activeJobId || !activeJobStatus || !ACTIVE_STATES.has(activeJobStatus)) return
    let active = true
    const timer = window.setInterval(async () => {
      try {
        const updated = await api.job(activeJobId)
        if (active) setJob(updated)
        if (!ACTIVE_STATES.has(updated.status)) { window.clearInterval(timer); if (active) void loadFolder() }
      } catch (cause) { if (active) { setBackendStatus('OFFLINE'); setMessage(getUserMessage(cause)) } }
    }, 1500)
    return () => { active = false; window.clearInterval(timer) }
  }, [activeJobId, activeJobStatus, loadFolder])

  const rows = useMemo(() => rowsFrom(files, job), [files, job])
  const selectedSet = useMemo(() => new Set(selectedIds), [selectedIds])
  const currentRow = rows.find((row) => row.filename === job?.current_file)
  const completedCount = rows.filter((row) => row.status === 'DONE').length
  const failedRows = rows.filter((row) => row.status === 'FAILED')
  const isProcessing = Boolean(job && ACTIVE_STATES.has(job.status))
  const canControl = Boolean(job && ['PREPARING', 'TRANSCRIBING', 'SAVING', 'VERIFYING'].includes(job.status))
  const runState: CurrentTaskStatus = job ? (job.status as CurrentTaskStatus) : 'IDLE'

  async function changeFolder() {
    const value = await pickFolder(folder)
    if (!value) return
    saveFolder(value); setFolder(value); setSelectedIds([]); setJob(undefined); setNormalization(undefined)
  }

  function toggle(id: string) {
    if (isProcessing) return
    setSelectedIds((current) => current.includes(id) ? current.filter((value) => value !== id) : [...current, id])
    void reviewFilename(id)
  }

  async function reviewFilename(id: string) {
    const file = files.find((item) => item.id === id)
    if (!file || !folder) return
    try {
      const result = await api.normalize(folder, file.filename, files.filter((item) => item.id !== id).map((item) => item.filename))
      setNormalization(result); setFilenameValue(result.suggested_name); setFilenameMode('review'); setFilenameResolution('')
    } catch (cause) { setMessage(getUserMessage(cause)) }
  }

  function handleStart() {
    if (!folder || isProcessing) return
    if (selectedIds.length === 0) {
      const targets = rows.filter((row) => row.status !== 'DONE').map((row) => row.id)
      setPendingIds(targets); setDialog(targets.length ? 'start-all' : 'empty-target'); return
    }
    const targets = rows.filter((row) => selectedSet.has(row.id) && row.status !== 'DONE').map((row) => row.id)
    if (!targets.length) { setDialog('empty-target'); return }
    void createAndStart(targets, false, 'selected')
  }

  async function createAndStart(ids: string[], force: boolean, scope: 'selected' | 'all_incomplete') {
    try {
      const created = await api.createJob({ folder, file_ids: ids, scope, force_retranscribe: force, upload_to_drive: uploadToDrive })
      setJob(created); setDialog(null); setPendingIds([]); setMessage('Job을 생성했습니다. 전사를 시작합니다.')
      setJob(await api.startJob(created.job_id))
    } catch (cause) { setMessage(getUserMessage(cause)); setDialog(null) }
  }

  async function action(actionName: 'stop' | 'cancel' | 'retry') {
    if (!job) return
    try {
      const updated = await api.actionJob(job.job_id, actionName)
      setJob(updated)
      if (actionName === 'retry' && updated.status === 'WAITING') setJob(await api.startJob(job.job_id))
    } catch (cause) { setMessage(getUserMessage(cause)) }
  }

  async function uploadDrive(retry = false) {
    if (!job) return
    const targets = Object.entries(job.files).filter(([id, state]) => state === 'DONE' && (!selectedIds.length || selectedSet.has(id))).map(([id]) => id)
    if (!targets.length) { setMessage('Drive에 업로드할 로컬 완료 파일이 없습니다.'); return }
    for (const id of targets) {
      try { await api.uploadDrive(job.job_id, id, retry || job.drive[id]?.status === 'FAILED') }
      catch (cause) { setMessage(getUserMessage(cause)) }
    }
    setJob(await api.job(job.job_id))
  }

  async function applyFilename() {
    if (!normalization || !folder || !filenameValue.toLowerCase().endsWith('.mp3')) return
    try {
      await api.rename(folder, normalization.original_name.replace(/\.mp3$/i, ''), filenameValue.replace(/\.mp3$/i, ''))
      setFilenameMode('resolved'); setFilenameResolution(`이름을 “${filenameValue}”로 변경했습니다.`); await loadFolder()
    } catch (cause) { setMessage(getUserMessage(cause)) }
  }

  const crashed = rows.some((row) => row.status === 'CRASHED')
  const driveEntries = job ? Object.entries(job.drive).filter(([, state]) => state.status !== 'DISABLED') : []
  return (
    <div className="transcription-page">
      <RuntimeBanner status={backendStatus} message={message} onReconnect={() => void reconnect()} />
      <FolderSection folderPath={folder || '선택된 폴더 없음'} onChangeFolder={() => void changeFolder()} />
      {crashed ? <div className="status-banner status-banner-warning" role="status"><AlertTriangle aria-hidden="true" /><div><strong>이전 작업이 비정상적으로 종료되었습니다.</strong><span>완료 파일은 유지되며 자동 재개하지 않습니다.</span></div><Button variant="secondary" onClick={() => void action('retry')}>다시 시도</Button></div> : null}
      <TranscriptionActions completedCount={completedCount} selectedCount={selectedIds.length} totalCount={rows.length} canStart={backendStatus === 'CONNECTED' && Boolean(folder) && !isProcessing} canStop={canControl} canCancel={canControl} retryCount={failedRows.length} onStart={handleStart} onStop={() => void action('stop')} onCancel={() => void action('cancel')} onRetryFailed={() => void action('retry')} />
      {job && job.failed_files > 0 ? <div className="result-summary" aria-live="polite"><div><strong>{job.done_files}개 완료</strong><span>{job.failed_files}개 실패 · 성공한 결과는 유지됩니다.</span></div><Badge tone="failed">부분 실패</Badge></div> : null}
      <CurrentTaskSection filename={currentRow?.filename ?? job?.current_file ?? undefined} progress={job?.current_progress ?? null} status={runState} />
      <QueueTable rows={rows} selectedIds={selectedIds} currentId={currentRow?.id} onToggle={toggle} onToggleAll={() => setSelectedIds(selectedIds.length === rows.length ? [] : rows.map((row) => row.id))} onRetry={() => void action('retry')} onRetranscribe={(id) => { setPendingIds([id]); setDialog('retranscribe') }} />
      <FilenameReview preview={normalization} mode={filenameMode} value={filenameValue} resolution={filenameResolution} onValueChange={setFilenameValue} onContinueOriginal={() => { setFilenameMode('resolved'); setFilenameResolution('원래 이름으로 Local 전사를 계속합니다. Drive 분류는 보류될 수 있습니다.') }} onEdit={() => setFilenameMode('editing')} onApply={() => void applyFilename()} onReset={() => setFilenameMode('review')} />
      <section className="service-section" aria-labelledby="service-heading"><div className="section-heading-row"><div><h2 className="text-section-heading" id="service-heading">연결 및 저장 상태</h2><p>전사 결과와 외부 서비스 상태를 분리해 표시합니다.</p></div></div><div className="service-grid">
        <Card className="service-card"><div className="service-card-heading"><Cloud aria-hidden="true" /><strong>Direct Colab</strong><Badge tone={job?.engine === 'direct_colab' ? 'done' : 'waiting'}>{job?.engine === 'direct_colab' ? '현재 Job 엔진' : '사용 안 함'}</Badge></div><p>실제 Job에 저장된 engine 선택을 표시합니다.</p></Card>
        <Card className="service-card service-card-wide"><div className="service-card-heading"><Cloud aria-hidden="true" /><strong>Google Drive</strong><Badge tone={driveAuth === 'CONNECTED' ? 'done' : 'cancelled'}>{driveAuth === 'CONNECTED' ? '연결됨' : '인증 필요'}</Badge></div><p>로컬 완료 상태와 독립적으로 업로드하고 실패한 Drive만 재시도합니다.</p><label className="setting-row"><span><strong>전사 완료 후 자동 업로드</strong><small>MP3/TXT/JSON/SRT 정확히 4개</small></span><input type="checkbox" checked={uploadToDrive} onChange={(event) => setUploadToDrive(event.target.checked)} /></label><div className="drive-status-list">{driveEntries.map(([id, state]) => { const view = drivePresentation[state.status]; return <div className="drive-status-item" key={id}><span>{id}</span><Badge tone={view?.tone ?? 'waiting'}>{view?.label ?? state.status}</Badge></div> })}{driveEntries.length === 0 ? <span>아직 Drive 업로드 기록이 없습니다.</span> : null}</div><div className="inline-actions"><Button variant="secondary" disabled={!driveEntries.some(([, state]) => state.status === 'FAILED')} onClick={() => void uploadDrive(true)}>Drive 실패 다시 시도</Button></div></Card>
      </div></section>
      {dialog ? <div className="dialog-backdrop" role="presentation"><div className="dialog" role="dialog" aria-modal="true" aria-labelledby="dialog-title">
        {dialog === 'start-all' ? <><h2 className="text-card-title" id="dialog-title">전체 파일을 전사할까요?</h2><p className="dialog-summary">전체 <strong>{rows.length}개</strong> 중 완료 <strong>{completedCount}개</strong>를 제외한 <strong>{pendingIds.length}개</strong> 파일을 전사합니다.</p><div className="dialog-actions"><Button variant="secondary" onClick={() => setDialog(null)}>취소</Button><Button onClick={() => void createAndStart([], false, 'all_incomplete')}>실행</Button></div></> : null}
        {dialog === 'empty-target' ? <><h2 className="text-card-title" id="dialog-title">처리할 파일이 없습니다</h2><p>선택한 파일이 모두 완료되었거나 실제 전사 대상이 0개입니다.</p><div className="dialog-actions"><Button onClick={() => setDialog(null)}>확인</Button></div></> : null}
        {dialog === 'retranscribe' ? <><h2 className="text-card-title" id="dialog-title">다시 전사</h2><ul className="contract-list"><li>기존 정상 결과를 보존합니다.</li><li>새 결과 검증 성공 후에만 교체합니다.</li></ul><div className="dialog-actions"><Button variant="secondary" onClick={() => setDialog(null)}>취소</Button><Button onClick={() => void createAndStart(pendingIds, true, 'selected')}>다시 전사 시작</Button></div></> : null}
      </div></div> : null}
    </div>
  )
}

function RuntimeBanner({ status, message, onReconnect }: { status: BackendStatus; message: string; onReconnect: () => void }) {
  const connected = status === 'CONNECTED'
  return <div className={connected ? 'runtime-banner runtime-banner-connected' : 'runtime-banner'} role="status">{connected ? <CheckCircle2 aria-hidden="true" /> : <WifiOff aria-hidden="true" />}<div><strong>{status === 'OFFLINE' ? 'Backend 오프라인' : status === 'STARTING' ? 'Backend 시작 중' : 'Backend 연결됨'}</strong><span>{message}</span></div>{!connected ? <Button variant="secondary" disabled={status === 'STARTING'} onClick={onReconnect}><RefreshCw aria-hidden="true" />{status === 'STARTING' ? '연결 중' : '다시 연결'}</Button> : null}</div>
}

function FilenameReview({ preview, mode, value, resolution, onValueChange, onContinueOriginal, onEdit, onApply, onReset }: { preview?: NormalizationPreview; mode: 'review' | 'editing' | 'resolved'; value: string; resolution: string; onValueChange: (value: string) => void; onContinueOriginal: () => void; onEdit: () => void; onApply: () => void; onReset: () => void }) {
  const invalid = /[<>:"/\\|?*]/.test(value.replace(/\.mp3$/i, '')) || !value.toLowerCase().endsWith('.mp3')
  return <Card className="filename-review"><div className="section-heading-row"><div><span className="eyebrow">파일명 확인</span><h2 className="text-section-heading">정규화 결과를 확인해 주세요</h2></div><FilePenLine aria-hidden="true" /></div>
    {!preview ? <p>파일을 선택하면 실제 Backend 정규화 결과를 표시합니다.</p> : mode === 'resolved' ? <div className="resolved-state" role="status"><CheckCircle2 aria-hidden="true" /><span>{resolution}</span><button type="button" className="text-action" onClick={onReset}>다시 확인</button></div> : <><dl className="filename-comparison"><div><dt>원본</dt><dd>{preview.original_name}</dd></div><div><dt>추천</dt><dd>{preview.suggested_name}</dd></div></dl>{preview.warnings.map((warning) => <p key={warning}>{warning}</p>)}{mode === 'editing' ? <div className="filename-editor"><label htmlFor="normalized-filename">수정할 이름</label><input className={invalid ? 'input input-error' : 'input'} id="normalized-filename" value={value} onChange={(event) => onValueChange(event.target.value)} /></div> : null}<div className="inline-actions"><Button variant="secondary" onClick={onContinueOriginal}>원래 이름으로 계속</Button>{mode === 'editing' ? <Button disabled={invalid} onClick={onApply}>이름 적용</Button> : <Button onClick={onEdit}>이름 수정</Button>}</div></>}
  </Card>
}
