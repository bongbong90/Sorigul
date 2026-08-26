import { useEffect, useMemo, useRef } from 'react'
import { Badge } from '../ui/Badge'
import { Card } from '../ui/Card'

export type QueueStatus = 'WAITING' | 'TRANSCRIBING' | 'DONE' | 'CANCELLED'

export interface QueueRow {
  id: string
  filename: string
  duration: string
  status: QueueStatus
}

interface QueueTableProps {
  rows: QueueRow[]
  selectedIds: string[]
  currentId?: string
  onToggle: (id: string) => void
  onToggleAll: () => void
}

const statusPresentation = {
  WAITING: { label: '대기', tone: 'waiting' as const },
  TRANSCRIBING: { label: '전사 중', tone: 'transcribing' as const },
  DONE: { label: '완료', tone: 'done' as const },
  CANCELLED: { label: '중지됨', tone: 'cancelled' as const },
}

export function QueueTable({
  rows,
  selectedIds,
  currentId,
  onToggle,
  onToggleAll,
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
                  </td>
                  <td className="duration-cell text-numeric">{row.duration}</td>
                  <td className="status-cell">
                    <Badge tone={presentation.tone}>{presentation.label}</Badge>
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
