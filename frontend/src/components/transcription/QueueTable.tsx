import { Badge } from '../ui/Badge'
import { Card } from '../ui/Card'

const sampleRows = [
  {
    filename: '개념완성_부동산공법_8주차_1강.mp3',
    duration: '54:20',
    status: '완료',
    tone: 'done' as const,
    selected: false,
    current: false,
  },
  {
    filename: '개념완성_부동산공법_8주차_2강.mp3',
    duration: '48:15',
    status: '전사 중',
    tone: 'transcribing' as const,
    selected: true,
    current: true,
  },
  {
    filename: '중개사법_핵심이론_3주차_4강.mp3',
    duration: '52:10',
    status: '대기',
    tone: 'waiting' as const,
    selected: false,
    current: false,
  },
  {
    filename:
      '30강_[8주차]_26_04_22_[교재2]_주택법_주택의_건설과_공급_및_리모델링에_관한_긴_파일명_예시.mp3',
    duration: '61:05',
    status: '대기',
    tone: 'waiting' as const,
    selected: false,
    current: false,
  },
]

export function QueueTable() {
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
                <input type="checkbox" aria-label="모든 파일 선택" checked={false} readOnly />
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
            {sampleRows.map((row) => (
              <tr key={row.filename} className={row.current ? 'queue-row-current' : undefined}>
                <td className="selection-cell">
                  <input
                    type="checkbox"
                    aria-label={`${row.filename} 선택`}
                    checked={row.selected}
                    readOnly
                  />
                </td>
                <td>
                  <span className="queue-filename" title={row.filename}>
                    {row.filename}
                  </span>
                </td>
                <td className="duration-cell text-numeric">{row.duration}</td>
                <td className="status-cell">
                  <Badge tone={row.tone}>{row.status}</Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}
