import { Badge } from '../ui/Badge'
import { Card } from '../ui/Card'
import { Progress } from '../ui/Progress'
import { currentTaskStatusPresentation as statusPresentation, type CurrentTaskStatus } from './currentTaskStatus'

export type { CurrentTaskStatus } from './currentTaskStatus'

interface CurrentTaskSectionProps {
  filename?: string
  progress: number | null
  status: CurrentTaskStatus
  engine?: string
  elapsedSeconds?: number | null
  etaSeconds?: number | null
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
  const showsRuntime = engine === 'local_whisper' || engine === 'direct_colab'
  const detail = status === 'TRANSCRIBING' && showsRuntime
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
