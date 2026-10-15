import { useEffect, useMemo, useRef } from 'react'
import { MoreHorizontal, RotateCcw } from 'lucide-react'
import { Badge } from '../ui/Badge'
import { Card } from '../ui/Card'

export type QueueStatus =
  | 'WAITING'
  | 'TRANSCRIBING'
  | 'VERIFYING'
  | 'DONE'
  | 'FAILED'
  | 'STOPPED'
  | 'CANCELLED'
  | 'CRASHED'
  | 'RETRYING'
  | 'CANCEL_REQUESTED'

export interface QueueRow {
  id: string
  filename: string
  duration: string
  status: QueueStatus
  detail?: string
}

interface QueueTableProps {
  rows: QueueRow[]
  selectedIds: string[]
  currentId?: string
  onToggle: (id: string) => void
  onToggleAll: () => void
  onRetry: (id: string) => void
  onRetranscribe: (id: string) => void
}

const statusPresentation = {
  WAITING: { label: '대기', tone: 'waiting' as const },
  TRANSCRIBING: { label: '전사 중', tone: 'transcribing' as const },
  VERIFYING: { label: '검증 중', tone: 'verifying' as const },
  DONE: { label: '완료', tone: 'done' as const },
  FAILED: { label: '실패', tone: 'failed' as const },
  STOPPED: { label: '중지됨', tone: 'stopped' as const },
  CANCELLED: { label: '취소됨', tone: 'cancelled' as const },
  CRASHED: { label: '복구 필요', tone: 'crashed' as const },
  RETRYING: { label: '재시도 중', tone: 'retrying' as const },
  CANCEL_REQUESTED: { label: '취소 요청 중', tone: 'cancelled' as const },
}

const retryableStatuses: QueueStatus[] = ['FAILED', 'STOPPED', 'CANCELLED', 'CRASHED']

export function QueueTable({
  rows,
  selectedIds,
  currentId,
  onToggle,
  onToggleAll,
  onRetry,
  onRetranscribe,
}: QueueTableProps) {
  const selectAllRef = useRef<HTMLInputElement>(null)
  const selectedIdSet = useMemo(() => new Set(selectedIds), [selectedIds])
  const allSelected = rows.length > 0 && rows.every((row) => selectedIdSet.has(row.id))
  const someSelected = rows.some((row) => selectedIdSet.has(row.id))

  useEffect(() => {
    if (selectAllRef.current) {
      selectAllRef.current.indeterminate = someSelected && !allSelected
    }
  }, [allSelected, someSelected])

  return (
    <Card className="queue-section">
      <div className="queue-table-scroll">
        <table className="queue-table">
          <caption className="visually-hidden">전사 대상 파일 목록</caption>
          <colgroup>
            <col className="selection-column" />
            <col className="filename-column" />
            <col className="duration-column" />
            <col className="status-column" />
            <col className="row-action-column" />
          </colgroup>
          <thead>
            <tr>
              <th scope="col" className="selection-cell">
                <input
                  ref={selectAllRef}
                  type="checkbox"
                  aria-label="모든 파일 선택"
                  checked={allSelected}
                  onChange={onToggleAll}
                />
              </th>
              <th scope="col">파일명</th>
              <th scope="col" className="duration-cell">
                재생시간
              </th>
              <th scope="col" className="status-cell">
                상태
              </th>
              <th scope="col" className="row-action-cell">
                <span className="visually-hidden">파일 작업</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const presentation = statusPresentation[row.status]

              return (
                <tr
                  key={row.id}
                  className={row.id === currentId ? 'queue-row-current' : undefined}
                >
                  <td className="selection-cell">
                    <input
                      type="checkbox"
                      aria-label={`${row.filename} 선택`}
                      checked={selectedIdSet.has(row.id)}
                      onChange={() => onToggle(row.id)}
                    />
                  </td>
                  <td>
                    <span className="queue-filename" title={row.filename}>
                      {row.filename}
                    </span>
                    {row.detail ? <span className="queue-row-detail">{row.detail}</span> : null}
                  </td>
                  <td className="duration-cell text-numeric">{row.duration}</td>
                  <td className="status-cell">
                    <Badge tone={presentation.tone}>{presentation.label}</Badge>
                  </td>
                  <td className="row-action-cell">
                    {row.status === 'DONE' ? (
                      <button
                        type="button"
                        className="icon-action"
                        aria-label={`${row.filename} 다시 전사`}
                        title="다시 전사"
                        onClick={() => onRetranscribe(row.id)}
                      >
                        <MoreHorizontal aria-hidden="true" focusable="false" />
                      </button>
                    ) : null}
                    {retryableStatuses.includes(row.status) ? (
                      <button
                        type="button"
                        className="icon-action"
                        aria-label={`${row.filename} 다시 시도`}
                        title="다시 시도"
                        onClick={() => onRetry(row.id)}
                      >
                        <RotateCcw aria-hidden="true" focusable="false" />
                      </button>
                    ) : null}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </Card>
  )
}
