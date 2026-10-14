import { Play, RotateCcw, Square, X } from 'lucide-react'
import { Button } from '../ui/Button'

interface TranscriptionActionsProps {
  canStart: boolean
  canStop: boolean
  canCancel: boolean
  canRetry: boolean
  retryCount: number
  onStart: () => void
  onStop: () => void
  onCancel: () => void
  onRetryFailed: () => void
}

export function TranscriptionActions({
  canStart,
  canStop,
  canCancel,
  canRetry,
  retryCount,
  onStart,
  onStop,
  onCancel,
  onRetryFailed,
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
        <Button variant="secondary" disabled={!canCancel} onClick={onCancel}>
          <X className="transcription-icon-small" aria-hidden="true" focusable="false" />
          작업 취소
        </Button>
        {retryCount > 0 ? (
          <Button variant="secondary" disabled={!canRetry} onClick={onRetryFailed}>
            <RotateCcw className="transcription-icon-small" aria-hidden="true" focusable="false" />
            실패 파일 다시 시도 · {retryCount}
          </Button>
        ) : null}
      </div>
    </div>
  )
}

export function OverallProgress({ progressDoneCount, progressTotalCount, selectedCount, engine }: {
  progressDoneCount: number | null; progressTotalCount: number | null; selectedCount: number; engine?: string
}) {
  return <div className="overall-progress" aria-label="전체 진행률" aria-live="polite">
    <span className="text-caption">전체 진행률 · {selectedCount}개 선택</span>
    <strong className="text-section-heading text-numeric">{progressDoneCount !== null && progressTotalCount !== null ? `${progressDoneCount} / ${progressTotalCount} 완료` : '현재 작업 없음'}</strong>
    {engine ? <span className="text-caption">실제 엔진 · {engine === 'direct_colab' ? 'Google Colab' : 'Local'}</span> : null}
  </div>
}
