import { useMemo, useState } from 'react'
import { CheckCircle2, Clipboard, Cloud, FileCheck2, RotateCcw, TriangleAlert, XCircle } from 'lucide-react'
import { Badge, type BadgeTone } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'

type LogLevel = 'success' | 'warning' | 'error' | 'neutral'
type LogFilter = 'all' | 'success' | 'warning' | 'error'

interface LogEvent {
  id: string
  time: string
  category: string
  message: string
  detail: string
  level: LogLevel
}

const logEvents: LogEvent[] = [
  { id: '1', time: '22:14:03', category: '전사', message: '전사 시작', detail: '완료 5개를 제외한 7개 파일', level: 'neutral' },
  { id: '2', time: '22:22:41', category: '파일 완료', message: '민법 8주차 21강 완료', detail: 'TXT/JSON/SRT 검증 완료', level: 'success' },
  { id: '3', time: '22:22:44', category: 'Drive', message: 'Google Drive 업로드 완료', detail: '기존 파일 갱신 또는 새 파일 저장', level: 'success' },
  { id: '4', time: '22:24:10', category: 'Stop', message: '사용자가 전사를 중지함', detail: '현재 파일은 다시 시도하면 처음부터 처리', level: 'warning' },
  { id: '5', time: '22:25:18', category: 'Cancel', message: '대기 작업 취소', detail: '완료된 파일은 유지됨', level: 'warning' },
  { id: '6', time: '22:30:32', category: 'Colab', message: 'Colab 연결 오류', detail: '네트워크 연결을 확인해 주세요', level: 'error' },
  { id: '7', time: '22:30:42', category: 'Retry', message: '자동 재시도', detail: '연결 문제로 다시 시도 중', level: 'warning' },
  { id: '8', time: '22:31:01', category: '파일 실패', message: '전사 실패', detail: '실패 파일만 다시 시도할 수 있음', level: 'error' },
  { id: '9', time: '22:32:14', category: '결과 검증', message: 'JSON 결과 검증 실패', detail: 'segments 필드를 확인할 수 없음', level: 'error' },
  { id: '10', time: '22:34:08', category: 'CRASHED', message: '이전 작업 복구 필요', detail: '자동 재개하지 않음 · 완료 파일 유지', level: 'warning' },
  { id: '11', time: '22:35:27', category: 'Runtime', message: 'Backend 연결 복구', detail: '상태 확인 완료', level: 'success' },
]

const filters: Array<{ id: LogFilter; label: string }> = [
  { id: 'all', label: '전체' },
  { id: 'success', label: '성공' },
  { id: 'warning', label: '경고' },
  { id: 'error', label: '오류' },
]

const levelPresentation: Record<LogLevel, { tone: BadgeTone; icon: typeof CheckCircle2 }> = {
  success: { tone: 'done', icon: CheckCircle2 },
  warning: { tone: 'cancelled', icon: TriangleAlert },
  error: { tone: 'failed', icon: XCircle },
  neutral: { tone: 'waiting', icon: FileCheck2 },
}

export function LogPage() {
  const [filter, setFilter] = useState<LogFilter>('all')
  const [copied, setCopied] = useState(false)
  const visibleEvents = useMemo(
    () => logEvents.filter((event) => filter === 'all' || event.level === filter),
    [filter],
  )

  function handleCopy() {
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1400)
  }

  return (
    <div className="feature-page log-page">
      <div className="page-intro">
        <div>
          <p className="eyebrow">작업 기록</p>
          <h2>실행 흐름과 오류 원인을 확인하세요</h2>
          <p>중요한 작업과 오류만 읽기 쉽게 정리합니다.</p>
        </div>
        <Button variant="secondary" onClick={handleCopy}>
          <Clipboard aria-hidden="true" focusable="false" />
          {copied ? '복사됨' : '로그 복사'}
        </Button>
      </div>

      <div className="filter-bar" aria-label="로그 필터">
        {filters.map((item) => (
          <button
            type="button"
            key={item.id}
            className={filter === item.id ? 'filter-button filter-button-active' : 'filter-button'}
            aria-pressed={filter === item.id}
            onClick={() => setFilter(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>

      <Card className="log-list" role="list" aria-label="실행 로그">
        {visibleEvents.map((event) => {
          const presentation = levelPresentation[event.level]
          const Icon = event.category === 'Drive' ? Cloud : event.category === 'Retry' ? RotateCcw : presentation.icon
          return (
            <article className="log-event" key={event.id} role="listitem">
              <time className="text-timestamp text-numeric">{event.time}</time>
              <span className={`log-icon log-icon-${event.level}`}><Icon aria-hidden="true" /></span>
              <div className="log-event-copy">
                <div>
                  <strong>{event.message}</strong>
                  <Badge tone={presentation.tone}>{event.category}</Badge>
                </div>
                <p>{event.detail}</p>
              </div>
            </article>
          )
        })}
      </Card>
    </div>
  )
}
