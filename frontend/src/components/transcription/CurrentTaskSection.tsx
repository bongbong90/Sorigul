import { Badge } from '../ui/Badge'
import { Card } from '../ui/Card'
import { Progress } from '../ui/Progress'

const CURRENT_PROGRESS = 64

export function CurrentTaskSection() {
  return (
    <Card className="current-task-section">
      <div className="current-task-content">
        <div className="current-task-details">
          <div className="current-task-label">
            <Badge tone="transcribing">전사 중</Badge>
            <h2 className="text-caption" id="current-task-heading">
              현재 작업
            </h2>
          </div>
          <p
            className="current-filename text-card-title"
            title="개념완성_부동산공법_8주차_2강.mp3"
            aria-labelledby="current-task-heading"
          >
            개념완성_부동산공법_8주차_2강.mp3
          </p>
        </div>

        <div className="current-task-progress">
          <strong className="progress-value text-numeric">{CURRENT_PROGRESS}%</strong>
          <span className="text-caption text-numeric">예상 남은 시간 12분</span>
        </div>
      </div>

      <Progress value={CURRENT_PROGRESS} label="현재 파일 전사 진행률" />
    </Card>
  )
}
