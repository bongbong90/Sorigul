import { Play, Square } from 'lucide-react'
import { Button } from '../ui/Button'

interface TranscriptionActionsProps {
  completedCount: number
  selectedCount: number
  totalCount: number
  canStart: boolean
  canStop: boolean
  onStart: () => void
  onStop: () => void
}

export function TranscriptionActions({
  completedCount,
  selectedCount,
  totalCount,
  canStart,
  canStop,
  onStart,
  onStop,
}: TranscriptionActionsProps) {
  return (
    <div className="transcription-controls" aria-label="전사 제어">
      <div className="action-buttons">
        <Button disabled={!canStart} onClick={onStart}>
          <Play className="transcription-icon-small" aria-hidden="true" focusable="false" />
          전사 시작
        </Button>
        <Button variant="secondary" disabled={!canStop} onClick={onStop}>
          <Square className="transcription-icon-small" aria-hidden="true" focusable="false" />
          전사 중지
        </Button>
      </div>

      <div className="overall-progress" aria-label="전체 진행률" aria-live="polite">
        <span className="text-caption">전체 진행률 · {selectedCount}개 선택</span>
        <strong className="text-section-heading text-numeric">
          {completedCount} / {totalCount} 완료
        </strong>
      </div>
    </div>
  )
}
