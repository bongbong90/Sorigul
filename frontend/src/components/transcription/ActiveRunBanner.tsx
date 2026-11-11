import { AudioLines, Square, X } from 'lucide-react'
import type { JobModel } from '../../api/client'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import { currentTaskStatusPresentation, type CurrentTaskStatus } from './currentTaskStatus'

const CONTROLLABLE_STATES = new Set(['PREPARING', 'TRANSCRIBING', 'SAVING', 'VERIFYING'])

interface ActiveRunBannerProps {
  activeJob: JobModel
  sameFolder: boolean
  onStop: () => void
  onCancel: () => void
}

// The app-wide single transcription run (#126) when it is not the Job shown
// in the current folder queue. Its file states are never merged into the
// current folder rows; only its identity, progress and Stop/Cancel live here.
export function ActiveRunBanner({ activeJob, sameFolder, onStop, onCancel }: ActiveRunBannerProps) {
  const view = currentTaskStatusPresentation[activeJob.status as CurrentTaskStatus] ?? currentTaskStatusPresentation.WAITING
  const canControl = CONTROLLABLE_STATES.has(activeJob.status)
  return (
    <div className="status-banner active-run-banner" role="status" aria-live="polite">
      <AudioLines aria-hidden="true" focusable="false" />
      <div>
        <strong>전사 작업 진행 중</strong>
        <span>{sameFolder ? '이 폴더의 다른 전사 작업이 진행 중입니다.' : '다른 폴더의 전사가 진행 중입니다.'} 종료된 뒤 새 전사를 시작할 수 있습니다.</span>
        <dl className="active-run-details">
          <div><dt>폴더</dt><dd title={activeJob.folder}>{activeJob.folder}</dd></div>
          {activeJob.current_file ? <div><dt>현재 파일</dt><dd title={activeJob.current_file}>{activeJob.current_file}</dd></div> : null}
          <div><dt>진행</dt><dd>{activeJob.done_files} / {activeJob.total_files} 완료</dd></div>
        </dl>
      </div>
      <Badge tone={view.tone}>{view.label}</Badge>
      <div className="inline-actions">
        <Button variant="secondary" disabled={!canControl} onClick={onStop}>
          <Square aria-hidden="true" focusable="false" />
          중지
        </Button>
        <Button variant="secondary" disabled={!canControl} onClick={onCancel}>
          <X aria-hidden="true" focusable="false" />
          작업 취소
        </Button>
      </div>
    </div>
  )
}
