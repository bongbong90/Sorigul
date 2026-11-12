import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, CheckCircle2, Cloud, FilePenLine, RefreshCw, WifiOff } from 'lucide-react'
import { CurrentTaskSection, type CurrentTaskStatus } from '../components/transcription/CurrentTaskSection'
import { FolderSection } from '../components/transcription/FolderSection'
import { QueueTable, type QueueRow, type QueueStatus } from '../components/transcription/QueueTable'
import { TranscriptionActions } from '../components/transcription/TranscriptionActions'
import { Badge, type BadgeTone } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'

type MockRunState = CurrentTaskStatus
type DialogKind = 'start-all' | 'empty-target' | 'retranscribe' | null
type BackendStatus = 'OFFLINE' | 'STARTING' | 'CONNECTED'
type ColabStatus = 'RETRYING' | 'CONNECTED' | 'FAILED'

const MOCK_FOLDERS = ['C:\\Users\\Sorigul\\Lectures', 'C:\\Users\\Sorigul\\CivilLaw']
const RETRYABLE_STATUSES: QueueStatus[] = ['FAILED', 'STOPPED', 'CANCELLED', 'CRASHED']

const MOCK_FILES: QueueRow[] = [
  {
    id: 'public-law-08-01',
    filename: '개념완성_부동산공법_8주차_1강.mp3',
    duration: '54:20',
    status: 'DONE',
    detail: '정상 결과 3종 · 일반 실행에서 자동 건너뜀',
  },
  {
    id: 'public-law-08-02',
    filename: '개념완성_부동산공법_8주차_2강.mp3',
    duration: '48:15',
    status: 'WAITING',
  },
  {
    id: 'verify-failure',
    filename: '기본이론_민법_8주차_22강.mp3',
    duration: '51:30',
    status: 'FAILED',
    detail: '결과 검증 실패 · JSON segments를 확인할 수 없습니다',
  },
  {
    id: 'stopped-file',
    filename: '기본이론_민법_8주차_23강.mp3',
    duration: '47:12',
    status: 'STOPPED',
    detail: '사용자가 전사를 중지함 · 다시 시도하면 처음부터 처리',
  },
  {
    id: 'cancelled-file',
    filename: '핵심이론_중개사법_3주차_4강.mp3',
    duration: '52:10',
    status: 'CANCELLED',
    detail: '대기 작업이 취소됨 · 다시 시도 가능',
  },
  {
    id: 'crashed-file',
    filename: '기초이론_부동산학개론_2주차_6강.mp3',
    duration: '44:08',
    status: 'CRASHED',
    detail: '이전 실행이 정상적으로 끝나지 않음',
  },
  {
    id: 'long-filename-sample',
    filename:
      '30강_[8주차]_26_04_22_[교재2]_주택법_주택의_건설과_공급_및_리모델링에_관한_긴_파일명_예시.mp3',
    duration: '61:05',
    status: 'WAITING',
    detail: '파일명 확인 필요',
  },
  {
    id: 'brokerage-law-done',
    filename: '개념완성_공인중개사법_3주차_5강.mp3',
    duration: '46:42',
    status: 'DONE',
    detail: '로컬 완료 · Google Drive 업로드 실패',
  },
]

const driveExamples: Array<{ label: string; filename: string; tone: BadgeTone }> = [
  { label: 'Drive 대기', filename: '민법_8주차_22강', tone: 'waiting' },
  { label: 'Drive 업로드 중', filename: '공법_8주차_2강', tone: 'preparing' },
  { label: 'Drive 완료', filename: '공법_8주차_1강', tone: 'done' },
  { label: 'Drive 실패', filename: '중개사법_3주차_5강', tone: 'failed' },
  { label: 'Drive 분류 실패', filename: '원래 이름으로 진행한 파일', tone: 'failed' },
  { label: '인증 필요', filename: 'Google Drive 다시 연결', tone: 'cancelled' },
]

const originalFilename = '23강_[8주차]_민법_법률행위와_의사표시.mp3'
const recommendedFilename = '기본이론_민법_8주차_23강.mp3'

function createMockRows() {
  return MOCK_FILES.map((row) => ({ ...row }))
}

export function TranscriptionPage() {
  const [folderIndex, setFolderIndex] = useState(0)
  const [rows, setRows] = useState(createMockRows)
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [runState, setRunState] = useState<MockRunState>('IDLE')
  const [activeQueue, setActiveQueue] = useState<string[]>([])
  const [activeIndex, setActiveIndex] = useState(0)
  const [progress, setProgress] = useState(0)
  const [dialog, setDialog] = useState<DialogKind>(null)
  const [pendingQueue, setPendingQueue] = useState<string[]>([])
  const [retriedIds, setRetriedIds] = useState<string[]>([])
  const [retranscribingId, setRetranscribingId] = useState<string>()
  const [filenameMode, setFilenameMode] = useState<'review' | 'editing' | 'resolved'>('review')
  const [filenameValue, setFilenameValue] = useState(recommendedFilename)
  const [filenameResolution, setFilenameResolution] = useState('')
  const [backendStatus, setBackendStatus] = useState<BackendStatus>('OFFLINE')
  const [colabStatus, setColabStatus] = useState<ColabStatus>('RETRYING')

  const currentId = activeQueue[activeIndex]
  const currentRow = rows.find((row) => row.id === currentId)
  const completedCount = rows.filter((row) => row.status === 'DONE').length
  const failedCount = rows.filter((row) => row.status === 'FAILED').length
  const failedRows = rows.filter((row) => row.status === 'FAILED')
  const isProcessing = ['TRANSCRIBING', 'VERIFYING', 'RETRYING', 'CANCEL_REQUESTED'].includes(
    runState,
  )
  const canControl = ['TRANSCRIBING', 'VERIFYING', 'RETRYING'].includes(runState)
  const selectedIdSet = useMemo(() => new Set(selectedIds), [selectedIds])

  const hasForbiddenCharacter = /[<>:"/\\|?*]/.test(filenameValue.replace(/\.mp3$/i, ''))
  const hasNameConflict = filenameValue === '개념완성_부동산공법_8주차_1강.mp3'
  const filenameIsValid = filenameValue.trim().length > 4 && !hasForbiddenCharacter && !hasNameConflict

  useEffect(() => {
    if (runState === 'CANCEL_REQUESTED' && currentId) {
      const cancelTimer = window.setTimeout(() => {
        setRows((currentRows) =>
          currentRows.map((row) =>
            row.id === currentId
              ? { ...row, status: 'CANCELLED', detail: '작업이 취소됨 · 다시 시도 가능' }
              : row,
          ),
        )
        setRunState('CANCELLED')
      }, 600)

      return () => window.clearTimeout(cancelTimer)
    }

    if (!['TRANSCRIBING', 'VERIFYING', 'RETRYING'].includes(runState) || !currentId) {
      return
    }

    const timerId = window.setTimeout(() => {
      const activeStatus = rows.find((row) => row.id === currentId)?.status

      if (activeStatus === 'RETRYING') {
        setRows((currentRows) =>
          currentRows.map((row) =>
            row.id === currentId ? { ...row, status: 'TRANSCRIBING', detail: '처음부터 다시 처리 중' } : row,
          ),
        )
        setRunState('TRANSCRIBING')
        return
      }

      if (activeStatus !== 'VERIFYING' && progress < 80) {
        setProgress((currentProgress) => currentProgress + 20)
        return
      }

      if (activeStatus !== 'VERIFYING') {
        setRows((currentRows) =>
          currentRows.map((row) =>
            row.id === currentId ? { ...row, status: 'VERIFYING', detail: 'TXT/JSON/SRT 결과 확인 중' } : row,
          ),
        )
        setRunState('VERIFYING')
        setProgress(92)
        return
      }

      const shouldFail = currentId === 'verify-failure' && !retriedIds.includes(currentId)
      const finalStatus: QueueStatus = shouldFail ? 'FAILED' : 'DONE'
      const finalDetail = shouldFail
        ? '결과 검증 실패 · 다음 파일은 계속 처리됩니다'
        : currentId === retranscribingId
          ? '새 결과 검증 완료 · 기존 결과 교체 예정'
          : '정상 결과 · 검증 완료'
      const nextId = activeQueue[activeIndex + 1]

      setRows((currentRows) =>
        currentRows.map((row) => {
          if (row.id === currentId) {
            return { ...row, status: finalStatus, detail: finalDetail }
          }
          if (row.id === nextId) {
            return { ...row, status: 'TRANSCRIBING', detail: '전사 중' }
          }
          return row
        }),
      )

      if (nextId) {
        setActiveIndex((currentIndex) => currentIndex + 1)
        setProgress(0)
        setRunState('TRANSCRIBING')
        return
      }

      setRunState('DONE')
      setProgress(100)
      setRetranscribingId(undefined)
    }, 650)

    return () => window.clearTimeout(timerId)
  }, [activeIndex, activeQueue, currentId, progress, retranscribingId, retriedIds, rows, runState])

  useEffect(() => {
    if (backendStatus !== 'STARTING') {
      return
    }
    const timerId = window.setTimeout(() => setBackendStatus('CONNECTED'), 900)
    return () => window.clearTimeout(timerId)
  }, [backendStatus])

  function resetRun() {
    setRunState('IDLE')
    setActiveQueue([])
    setActiveIndex(0)
    setProgress(0)
    setPendingQueue([])
    setDialog(null)
    setRetranscribingId(undefined)
  }

  function handleChangeFolder() {
    setFolderIndex((currentIndex) => (currentIndex + 1) % MOCK_FOLDERS.length)
    setRows(createMockRows())
    setSelectedIds([])
    setRetriedIds([])
    resetRun()
  }

  function handleToggle(id: string) {
    if (isProcessing) return
    setSelectedIds((currentIds) =>
      currentIds.includes(id)
        ? currentIds.filter((selectedId) => selectedId !== id)
        : [...currentIds, id],
    )
  }

  function handleToggleAll() {
    if (isProcessing) return
    setSelectedIds(selectedIds.length === rows.length ? [] : rows.map((row) => row.id))
  }

  function startQueue(ids: string[], options?: { retry?: boolean; retranscribe?: boolean }) {
    const firstId = ids[0]
    if (!firstId) {
      setDialog('empty-target')
      return
    }

    if (options?.retry) {
      setRetriedIds((currentIds) => [...new Set([...currentIds, ...ids])])
    }

    setRows((currentRows) =>
      currentRows.map((row) => {
        if (!ids.includes(row.id)) return row
        if (row.id === firstId) {
          return {
            ...row,
            status: options?.retry ? 'RETRYING' : 'TRANSCRIBING',
            detail: options?.retranscribe ? '기존 결과를 보존한 채 새 전사 시도 중' : '전사 준비 완료',
          }
        }
        return { ...row, status: 'WAITING', detail: '실행 대기 중' }
      }),
    )
    setActiveQueue(ids)
    setActiveIndex(0)
    setProgress(0)
    setRunState(options?.retry ? 'RETRYING' : 'TRANSCRIBING')
    setDialog(null)
    setPendingQueue([])
  }

  function handleStart() {
    if (isProcessing) return

    if (selectedIds.length === 0) {
      const targetIds = rows.filter((row) => row.status !== 'DONE').map((row) => row.id)
      setPendingQueue(targetIds)
      setDialog(targetIds.length === 0 ? 'empty-target' : 'start-all')
      return
    }

    const targetIds = rows
      .filter((row) => selectedIdSet.has(row.id) && row.status !== 'DONE')
      .map((row) => row.id)
    startQueue(targetIds)
  }

  function handleStop() {
    if (!canControl || !currentId) return
    setRows((currentRows) =>
      currentRows.map((row) =>
        row.id === currentId
          ? { ...row, status: 'STOPPED', detail: '사용자가 중지함 · 다시 시도하면 처음부터 처리' }
          : row,
      ),
    )
    setRunState('STOPPED')
  }

  function handleCancel() {
    if (!canControl || !currentId) return
    setRows((currentRows) =>
      currentRows.map((row) =>
        row.id === currentId ? { ...row, status: 'CANCEL_REQUESTED', detail: '안전하게 작업을 취소하는 중' } : row,
      ),
    )
    setRunState('CANCEL_REQUESTED')
  }

  function handleRetry(ids: string[]) {
    if (isProcessing) return
    const targets = rows
      .filter((row) => ids.includes(row.id) && RETRYABLE_STATUSES.includes(row.status))
      .map((row) => row.id)
    startQueue(targets, { retry: true })
  }

  function handleRetranscribe(id: string) {
    if (isProcessing) return
    setPendingQueue([id])
    setRetranscribingId(id)
    setDialog('retranscribe')
  }

  function applyFilename() {
    if (!filenameIsValid) return
    setFilenameMode('resolved')
    setFilenameResolution(`이름을 “${filenameValue}”로 변경할 준비가 되었습니다.`)
  }

  return (
    <div className="transcription-page">
      <RuntimeBanner
        status={backendStatus}
        onReconnect={() => setBackendStatus('STARTING')}
      />

      <FolderSection folderPath={MOCK_FOLDERS[folderIndex]} onChangeFolder={handleChangeFolder} />

      {rows.some((row) => row.status === 'CRASHED') ? (
        <div className="status-banner status-banner-warning" role="status">
          <AlertTriangle aria-hidden="true" focusable="false" />
          <div>
            <strong>이전 작업이 비정상적으로 종료되었습니다.</strong>
            <span>완료된 파일은 유지됩니다. 자동으로 재개하지 않습니다.</span>
          </div>
          <Button variant="secondary" onClick={() => handleRetry(['crashed-file'])}>
            다시 시도
          </Button>
        </div>
      ) : null}

      <TranscriptionActions
        completedCount={completedCount}
        selectedCount={selectedIds.length}
        totalCount={rows.length}
        canStart={!isProcessing}
        canStop={canControl}
        canCancel={canControl}
        retryCount={failedRows.length}
        onStart={handleStart}
        onStop={handleStop}
        onCancel={handleCancel}
        onRetryFailed={() => handleRetry(failedRows.map((row) => row.id))}
      />

      {failedCount > 0 ? (
        <div className="result-summary" aria-live="polite">
          <div>
            <strong>{completedCount}개 완료</strong>
            <span>{failedCount}개 실패 · 성공한 결과는 유지됩니다.</span>
          </div>
          <Badge tone="failed">부분 실패</Badge>
        </div>
      ) : null}

      <CurrentTaskSection
        filename={currentRow?.filename}
        progress={progress}
        status={runState}
      />

      <QueueTable
        rows={rows}
        selectedIds={selectedIds}
        currentId={currentId}
        onToggle={handleToggle}
        onToggleAll={handleToggleAll}
        onRetry={(id) => handleRetry([id])}
        onRetranscribe={handleRetranscribe}
      />

      <FilenameReview
        mode={filenameMode}
        value={filenameValue}
        resolution={filenameResolution}
        hasForbiddenCharacter={hasForbiddenCharacter}
        hasNameConflict={hasNameConflict}
        isValid={filenameIsValid}
        onValueChange={setFilenameValue}
        onContinueOriginal={() => {
          setFilenameMode('resolved')
          setFilenameResolution('원래 이름으로 Local 전사를 계속합니다. Drive 분류는 보류됩니다.')
        }}
        onEdit={() => setFilenameMode('editing')}
        onApply={applyFilename}
        onReset={() => {
          setFilenameMode('review')
          setFilenameValue(recommendedFilename)
          setFilenameResolution('')
        }}
      />

      <section className="service-section" aria-labelledby="service-heading">
        <div className="section-heading-row">
          <div>
            <h2 className="text-section-heading" id="service-heading">연결 및 저장 상태</h2>
            <p>전사 결과와 외부 서비스 상태를 분리해 표시합니다.</p>
          </div>
        </div>
        <div className="service-grid">
          <Card className="service-card">
            <div className="service-card-heading">
              <Cloud aria-hidden="true" focusable="false" />
              <strong>Direct Colab</strong>
              <Badge tone={colabStatus === 'CONNECTED' ? 'done' : colabStatus === 'FAILED' ? 'failed' : 'retrying'}>
                {colabStatus === 'CONNECTED' ? '연결됨' : colabStatus === 'FAILED' ? '연결 실패' : '재시도 중'}
              </Badge>
            </div>
            <p>
              {colabStatus === 'RETRYING'
                ? '연결 문제로 다시 시도 중입니다.'
                : colabStatus === 'CONNECTED'
                  ? 'Colab 전사를 시작할 수 있습니다.'
                  : '연결을 확인하고 다시 시도해 주세요.'}
            </p>
            <div className="inline-actions">
              <Button variant="secondary" onClick={() => setColabStatus('CONNECTED')}>연결 다시 확인</Button>
              <button type="button" className="text-action" onClick={() => setColabStatus('FAILED')}>실패 상태 보기</button>
            </div>
          </Card>

          <Card className="service-card service-card-wide">
            <div className="service-card-heading">
              <Cloud aria-hidden="true" focusable="false" />
              <strong>Google Drive</strong>
              <Badge tone="failed">전사 완료 · Drive 실패</Badge>
            </div>
            <p>로컬 결과는 정상 완료 상태로 유지됩니다. Google Drive만 다시 시도할 수 있습니다.</p>
            <div className="drive-status-list">
              {driveExamples.map((item) => (
                <div className="drive-status-item" key={item.label}>
                  <span>{item.filename}</span>
                  <Badge tone={item.tone}>{item.label}</Badge>
                </div>
              ))}
            </div>
            <Button variant="secondary">Google Drive 업로드 다시 시도</Button>
          </Card>
        </div>
      </section>

      {dialog ? (
        <div className="dialog-backdrop" role="presentation">
          <div className="dialog" role="dialog" aria-modal="true" aria-labelledby="dialog-title">
            {dialog === 'start-all' ? (
              <>
                <h2 className="text-card-title" id="dialog-title">전체 파일을 전사할까요?</h2>
                <p className="dialog-summary">
                  전체 <strong>{rows.length}개</strong> 중 완료 <strong>{completedCount}개</strong>를 제외한{' '}
                  <strong>{pendingQueue.length}개</strong> 파일을 전사합니다.
                </p>
                <p className="secondary-copy">완료된 결과 파일은 자동으로 건너뜁니다.</p>
                <div className="dialog-actions">
                  <Button variant="secondary" onClick={() => setDialog(null)}>취소</Button>
                  <Button onClick={() => startQueue(pendingQueue)}>실행</Button>
                </div>
              </>
            ) : null}
            {dialog === 'empty-target' ? (
              <>
                <h2 className="text-card-title" id="dialog-title">처리할 파일이 없습니다</h2>
                <p>선택한 파일이 모두 완료되었거나 실제 전사 대상이 0개입니다.</p>
                <div className="dialog-actions">
                  <Button onClick={() => setDialog(null)}>확인</Button>
                </div>
              </>
            ) : null}
            {dialog === 'retranscribe' ? (
              <>
                <h2 className="text-card-title" id="dialog-title">다시 전사</h2>
                <ul className="contract-list">
                  <li>기존 정상 결과를 보존합니다.</li>
                  <li>새 전사를 별도로 시도합니다.</li>
                  <li>새 결과 검증 성공 후에만 교체합니다.</li>
                </ul>
                <div className="dialog-actions">
                  <Button variant="secondary" onClick={() => setDialog(null)}>취소</Button>
                  <Button onClick={() => startQueue(pendingQueue, { retranscribe: true })}>다시 전사 시작</Button>
                </div>
              </>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  )
}

function RuntimeBanner({ status, onReconnect }: { status: BackendStatus; onReconnect: () => void }) {
  const connected = status === 'CONNECTED'
  return (
    <div className={connected ? 'runtime-banner runtime-banner-connected' : 'runtime-banner'} role="status">
      {connected ? <CheckCircle2 aria-hidden="true" /> : <WifiOff aria-hidden="true" />}
      <div>
        <strong>
          {status === 'OFFLINE' ? 'Backend 오프라인' : status === 'STARTING' ? 'Backend 시작 중' : 'Backend 연결됨'}
        </strong>
        <span>
          {status === 'OFFLINE'
            ? '최근 오류: Backend 연결 실패. 실제 전사는 시작되지 않았습니다.'
            : status === 'STARTING'
              ? '연결 상태를 확인하고 있습니다.'
              : 'Backend 연결 상태가 정상입니다. 전사를 시작할 수 있습니다.'}
        </span>
      </div>
      {!connected ? (
        <Button variant="secondary" disabled={status === 'STARTING'} onClick={onReconnect}>
          <RefreshCw aria-hidden="true" focusable="false" />
          {status === 'STARTING' ? '연결 중' : '다시 연결'}
        </Button>
      ) : null}
    </div>
  )
}

interface FilenameReviewProps {
  mode: 'review' | 'editing' | 'resolved'
  value: string
  resolution: string
  hasForbiddenCharacter: boolean
  hasNameConflict: boolean
  isValid: boolean
  onValueChange: (value: string) => void
  onContinueOriginal: () => void
  onEdit: () => void
  onApply: () => void
  onReset: () => void
}

function FilenameReview(props: FilenameReviewProps) {
  return (
    <Card className="filename-review">
      <div className="section-heading-row">
        <div>
          <span className="eyebrow">파일명 확인 필요</span>
          <h2 className="text-section-heading">정규화 결과를 확인해 주세요</h2>
        </div>
        <FilePenLine aria-hidden="true" focusable="false" />
      </div>

      {props.mode === 'resolved' ? (
        <div className="resolved-state" role="status">
          <CheckCircle2 aria-hidden="true" />
          <span>{props.resolution}</span>
          <button type="button" className="text-action" onClick={props.onReset}>다시 확인</button>
        </div>
      ) : (
        <>
          <dl className="filename-comparison">
            <div><dt>원본</dt><dd>{originalFilename}</dd></div>
            <div><dt>추천</dt><dd>{recommendedFilename}</dd></div>
          </dl>
          {props.mode === 'editing' ? (
            <div className="filename-editor">
              <label htmlFor="normalized-filename">수정할 이름</label>
              <input
                className={props.isValid ? 'input' : 'input input-error'}
                id="normalized-filename"
                value={props.value}
                onChange={(event) => props.onValueChange(event.target.value)}
              />
              <div className="validation-list" aria-live="polite">
                <span className={props.hasForbiddenCharacter ? 'validation-failed' : 'validation-passed'}>
                  {props.hasForbiddenCharacter ? '금지 문자 포함' : '금지 문자 없음'}
                </span>
                <span className={props.hasNameConflict ? 'validation-failed' : 'validation-passed'}>
                  {props.hasNameConflict ? '이름 충돌 또는 중복' : '중복 및 이름 충돌 없음'}
                </span>
              </div>
            </div>
          ) : null}
          <div className="inline-actions">
            <Button variant="secondary" onClick={props.onContinueOriginal}>원래 이름으로 계속</Button>
            {props.mode === 'editing' ? (
              <Button disabled={!props.isValid} onClick={props.onApply}>이름 적용</Button>
            ) : (
              <Button onClick={props.onEdit}>이름 수정</Button>
            )}
          </div>
        </>
      )}
    </Card>
  )
}
