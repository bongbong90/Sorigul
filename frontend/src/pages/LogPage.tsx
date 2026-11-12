import { useEffect, useMemo, useState } from 'react'
import { CheckCircle2, Clipboard, Cloud, FileCheck2, RotateCcw, TriangleAlert, XCircle } from 'lucide-react'
import { api, getUserMessage, type StructuredEvent } from '../api/client'
import { Badge, type BadgeTone } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'

type LogLevel = 'success' | 'warning' | 'error' | 'neutral'
type LogFilter = 'all' | 'success' | 'warning' | 'error'
const filters: Array<{ id: LogFilter; label: string }> = [
  { id: 'all', label: '전체' }, { id: 'success', label: '성공' },
  { id: 'warning', label: '경고' }, { id: 'error', label: '오류' },
]
const presentation: Record<LogLevel, { tone: BadgeTone; icon: typeof CheckCircle2 }> = {
  success: { tone: 'done', icon: CheckCircle2 }, warning: { tone: 'cancelled', icon: TriangleAlert },
  error: { tone: 'failed', icon: XCircle }, neutral: { tone: 'waiting', icon: FileCheck2 },
}

function eventLevel(event: StructuredEvent): LogLevel {
  if (event.level === 'error') return 'error'
  if (event.level === 'warning') return 'warning'
  if (/완료|연결됨|복구/.test(event.message)) return 'success'
  return 'neutral'
}

export function LogPage() {
  const [filter, setFilter] = useState<LogFilter>('all')
  const [events, setEvents] = useState<StructuredEvent[]>([])
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState<string>()

  useEffect(() => {
    let active = true
    async function refresh() {
      try {
        const result = await api.events()
        if (active) { setEvents(result); setError(undefined) }
      } catch (cause) { if (active) setError(getUserMessage(cause)) }
    }
    void refresh()
    const timer = window.setInterval(() => void refresh(), 4000)
    return () => { active = false; window.clearInterval(timer) }
  }, [])

  const visibleEvents = useMemo(() => events.filter((event) => filter === 'all' || eventLevel(event) === filter), [events, filter])
  async function handleCopy() {
    const text = visibleEvents.map((event) => `${new Date(event.timestamp).toLocaleString('ko-KR')} [${event.category}] ${event.message}${event.filename ? ` · ${event.filename}` : ''}`).join('\n')
    try { await navigator.clipboard.writeText(text); setCopied(true); window.setTimeout(() => setCopied(false), 1400) }
    catch { setError('보이는 로그를 클립보드에 복사하지 못했습니다.') }
  }

  return (
    <div className="feature-page log-page">
      <div className="page-intro"><div><p className="eyebrow">작업 기록</p><h2>실행 흐름과 오류 원인을 확인하세요</h2><p>{error ?? 'Job, 전사, Drive, application event를 표시합니다.'}</p></div><Button variant="secondary" onClick={() => void handleCopy()}><Clipboard aria-hidden="true" />{copied ? '복사됨' : '로그 복사'}</Button></div>
      <div className="filter-bar" aria-label="로그 필터">{filters.map((item) => <button type="button" key={item.id} className={filter === item.id ? 'filter-button filter-button-active' : 'filter-button'} aria-pressed={filter === item.id} onClick={() => setFilter(item.id)}>{item.label}</button>)}</div>
      <Card className="log-list" role="list" aria-label="실행 로그">
        {visibleEvents.map((event, index) => {
          const level = eventLevel(event); const view = presentation[level]
          const Icon = event.category === 'Drive' ? Cloud : event.category === 'Retry' ? RotateCcw : view.icon
          return <article className="log-event" key={`${event.timestamp}-${event.job_id ?? 'app'}-${index}`} role="listitem"><time className="text-timestamp text-numeric">{new Date(event.timestamp).toLocaleTimeString('ko-KR')}</time><span className={`log-icon log-icon-${level}`}><Icon aria-hidden="true" /></span><div className="log-event-copy"><div><strong>{event.message}</strong><Badge tone={view.tone}>{event.category}</Badge></div><p>{event.filename ?? (event.source === 'application' ? 'Application event' : 'Job event')}</p></div></article>
        })}
        {visibleEvents.length === 0 ? <p>표시할 로그가 없습니다.</p> : null}
      </Card>
    </div>
  )
}
