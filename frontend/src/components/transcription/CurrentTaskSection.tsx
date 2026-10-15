import { Badge } from '../ui/Badge'
import { Card } from '../ui/Card'
import { Progress } from '../ui/Progress'

export type CurrentTaskStatus = 'IDLE' | 'TRANSCRIBING' | 'DONE' | 'CANCELLED'

interface CurrentTaskSectionProps {
  filename?: string
  progress: number
  status: CurrentTaskStatus
}

const statusPresentation = {
  IDLE: { label: '준비', tone: 'waiting' as const, detail: '모의 전사 대기' },
  TRANSCRIBING: {
    label: '전사 중',
    tone: 'transcribing' as const,
    detail: '예상 남은 시간 12분',
  },
  DONE: { label: '완료', tone: 'done' as const, detail: '선택한 파일 완료' },
  CANCELLED: { label: '중지됨', tone: 'cancelled' as const, detail: '진행이 중지되었습니다' },
}

export function CurrentTaskSection({ filename, progress, status }: CurrentTaskSectionProps) {
  const presentation = statusPresentation[status]
  const displayFilename = filename ?? '현재 작업 없음'

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
          <strong className="progress-value text-numeric">{progress}%</strong>
          <span className="text-caption text-numeric">{presentation.detail}</span>
        </div>
      </div>

      <Progress value={progress} label="현재 파일 모의 전사 진행률" />
    </Card>
  )
}
