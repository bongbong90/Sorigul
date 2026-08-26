import { Play, Square } from 'lucide-react'
import { Button } from '../ui/Button'

export function TranscriptionActions() {
  return (
    <div className="transcription-controls" aria-label="전사 제어">
      <div className="action-buttons">
        <Button disabled>
          <Play className="transcription-icon-small" aria-hidden="true" focusable="false" />
          전사 시작
        </Button>
        <Button variant="secondary">
          <Square className="transcription-icon-small" aria-hidden="true" focusable="false" />
          전사 중지
        </Button>
      </div>

      <div className="overall-progress" aria-label="전체 진행률">
        <span className="text-caption">전체 진행률</span>
        <strong className="text-section-heading text-numeric">1 / 4 완료</strong>
      </div>
    </div>
  )
}
