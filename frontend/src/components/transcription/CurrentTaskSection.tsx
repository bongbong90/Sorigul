import { Badge } from '../ui/Badge'
import { Card } from '../ui/Card'
import { Progress } from '../ui/Progress'

export type CurrentTaskStatus =
  | 'IDLE'
  | 'WAITING'
  | 'PREPARING'
  | 'TRANSCRIBING'
  | 'SAVING'
  | 'VERIFYING'
  | 'DONE'
  | 'FAILED'
  | 'STOPPED'
  | 'CANCELLED'
  | 'CRASHED'
  | 'RETRYING'
  | 'CANCEL_REQUESTED'

interface CurrentTaskSectionProps {
  filename?: string
  progress: number | null
  status: CurrentTaskStatus
  engine?: string
  elapsedSeconds?: number | null
  etaSeconds?: number | null
}

const statusPresentation = {
  IDLE: { label: '준비', tone: 'waiting' as const, detail: '전사 대기' },
  WAITING: { label: '대기', tone: 'waiting' as const, detail: '작업 시작 대기' },
  PREPARING: { label: '준비 중', tone: 'preparing' as const, detail: '엔진 준비 중' },
  TRANSCRIBING: {
    label: '전사 중',
    tone: 'transcribing' as const,
    detail: '전사 진행 중',
  },
  VERIFYING: { label: '검증 중', tone: 'verifying' as const, detail: '결과 파일 확인 중' },
  SAVING: { label: '저장 중', tone: 'preparing' as const, detail: '결과 파일 저장 중' },
  DONE: { label: '완료', tone: 'done' as const, detail: '선택한 파일 완료' },
  FAILED: { label: '실패', tone: 'failed' as const, detail: '오류 원인을 확인해 주세요' },
  STOPPED: { label: '중지됨', tone: 'stopped' as const, detail: '다시 시도하면 처음부터 처리' },
  CANCELLED: { label: '취소됨', tone: 'cancelled' as const, detail: '미완료 파일은 다시 시도 가능' },
  CRASHED: { label: '복구 필요', tone: 'crashed' as const, detail: '완료된 파일은 유지됩니다' },
  RETRYING: { label: '재시도 중', tone: 'retrying' as const, detail: '현재 파일을 처음부터 처리 중' },
  CANCEL_REQUESTED: {
    label: '취소 요청 중',
    tone: 'cancelled' as const,
    detail: '안전하게 작업을 마치는 중',
  },
}

function formatRuntimeSeconds(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return '—'

  const totalSeconds = Math.round(seconds)
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const remainingSeconds = totalSeconds % 60

  if (hours >= 1) {
    return `${hours}:${String(minutes).padStart(2, '0')}:${String(remainingSeconds).padStart(2, '0')}`
  }
  return `${minutes}:${String(remainingSeconds).padStart(2, '0')}`
}

export function CurrentTaskSection({
  filename,
  progress,
  status,
  engine,
  elapsedSeconds,
  etaSeconds,
}: CurrentTaskSectionProps) {
  const presentation = statusPresentation[status]
  const displayFilename = filename ?? '현재 작업 없음'
  const hasObservedEta = etaSeconds != null && Number.isFinite(etaSeconds) && etaSeconds > 0
  const detail = status === 'TRANSCRIBING' && engine === 'local_whisper'
    ? `경과 ${formatRuntimeSeconds(elapsedSeconds)} · ${hasObservedEta ? `ETA 약 ${formatRuntimeSeconds(etaSeconds)}` : 'ETA 계산 중'}`
    : presentation.detail
  const progressValue = ['PREPARING', 'TRANSCRIBING', 'SAVING', 'VERIFYING', 'RETRYING'].includes(status)
    ? progress
    : (progress ?? 0)

  return (
    <Card className="current-task-section">
      <div className="current-task-content">
        <div className="current-task-details">
          <div className="current-task-label">
            <Badge tone={presentation.tone}>{presentation.label}</Badge>
            <h2 className="text-caption" id="current-task-heading">
              현재 작업
            </h2>
          </div>
          <p
            className="current-filename text-card-title"
            title={displayFilename}
            aria-labelledby="current-task-heading"
          >
            {displayFilename}
          </p>
        </div>

        <div className="current-task-progress">
          <strong className="progress-value text-numeric">{progress === null ? '—' : `${progress}%`}</strong>
          <span className="text-caption text-numeric">{detail}</span>
        </div>
      </div>

      <Progress value={progressValue} label="현재 파일 전사 진행률" />
    </Card>
  )
}
