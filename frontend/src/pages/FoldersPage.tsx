import { useCallback, useEffect, useRef, useState } from 'react'
import { ExternalLink, FileText, FolderOpen, Maximize2, RefreshCw, X } from 'lucide-react'
import { api, getSavedFolder, getUserMessage, isRequestAbort, saveFolder, type FolderFilter, type FolderItem } from '../api/client'
import { useFolderRevision } from '../hooks/useFolderRevision'
import { isTauri, openInExplorer, pickFolder } from '../lib/native'
import { Badge, type BadgeTone } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'

const folderFilters: Array<{ id: FolderFilter; label: string }> = [
  { id: 'all', label: '전체' }, { id: 'complete', label: '완료' },
  { id: 'incomplete', label: '미완료' }, { id: 'results', label: '결과만' },
]

function statusLabel(status: FolderItem['status']) {
  return status === 'COMPLETE' ? '완료' : status === 'INCOMPLETE' ? '미완료' : '결과 파일'
}

function statusTone(status: FolderItem['status']): BadgeTone {
  return status === 'COMPLETE' ? 'done' : status === 'INCOMPLETE' ? 'waiting' : 'preparing'
}

const PREVIEW_PLACEHOLDER = 'TXT 결과 파일을 선택하면 약 500자 미리보기를 표시합니다.'

export function FoldersPage() {
  const [folder, setFolder] = useState(getSavedFolder)
  const [filter, setFilter] = useState<FolderFilter>('all')
  const [scanId, setScanId] = useState('')
  const [files, setFiles] = useState<FolderItem[]>([])
  const [selectedId, setSelectedId] = useState<string>()
  const [preview, setPreview] = useState(PREVIEW_PLACEHOLDER)
  const [fullText, setFullText] = useState<string>()
  const [message, setMessage] = useState(folder ? '실제 디스크 상태를 기준으로 표시합니다.' : '전사 폴더를 선택해 주세요.')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string>()
  // Latest-wins guards: a slower, older folder/preview response (e.g. from
  // the previous folder or an earlier auto-refresh) never overwrites newer UI.
  const refreshSeq = useRef(0)
  const previewSeq = useRef(0)

  const refresh = useCallback(async (nextFilter = filter, options: { signal?: AbortSignal; live?: boolean } = {}) => {
    if (!folder) return undefined
    const seq = ++refreshSeq.current
    setLoading(true)
    try {
      const result = await api.folders(folder, nextFilter, options.signal)
      if (seq !== refreshSeq.current) return undefined
      setScanId(result.scan_id); setFiles(result.items); setError(undefined)
      setMessage(`${options.live ? '폴더 변경 자동 반영' : '새로고침 완료'} · ${result.items.length}개 표시`)
      return result
    } catch (cause) {
      if (seq !== refreshSeq.current || isRequestAbort(cause)) return undefined
      setFiles([]); setError(getUserMessage(cause))
      return undefined
    } finally { if (seq === refreshSeq.current) setLoading(false) }
  }, [filter, folder])

  useEffect(() => { void refresh() }, [refresh])

  // A selection whose file no longer exists (deleted, or outside the current
  // filter) is cleared together with its preview/full view: no stale text.
  useEffect(() => {
    if (!selectedId || files.some((file) => file.id === selectedId)) return
    previewSeq.current += 1
    setSelectedId(undefined); setPreview(PREVIEW_PLACEHOLDER); setFullText(undefined)
  }, [files, selectedId])

  async function selectItem(file: FolderItem) {
    const seq = ++previewSeq.current
    setSelectedId(file.id); setFullText(undefined)
    if (file.kind !== 'TXT' || !scanId) {
      setPreview(PREVIEW_PLACEHOLDER); return
    }
    try {
      const result = await api.textPreview(scanId, file.id)
      if (seq === previewSeq.current) setPreview(result.text || 'TXT 파일이 비어 있습니다.')
    } catch (cause) { if (seq === previewSeq.current) setPreview(getUserMessage(cause)) }
  }

  // #111 live folder change: re-read disk truth with the *current* filter,
  // then re-fetch the still-selected TXT preview (and the open full view) so
  // an externally edited TXT is not shown stale. Runs inside the watcher's
  // single in-flight slot, so these fetches never pile up.
  const liveRefresh = async (signal: AbortSignal) => {
    const result = await refresh(filter, { signal, live: true })
    if (!result || signal.aborted) return
    const selected = result.items.find((item) => item.id === selectedId)
    if (!selected || selected.kind !== 'TXT') return
    const seq = ++previewSeq.current
    try {
      const nextPreview = await api.textPreview(result.scan_id, selected.id, signal)
      if (seq === previewSeq.current) setPreview(nextPreview.text || 'TXT 파일이 비어 있습니다.')
      if (fullText !== undefined) {
        const nextFull = await api.fullText(result.scan_id, selected.id, signal)
        if (seq === previewSeq.current) setFullText(nextFull.text)
      }
    } catch {
      // The file vanished/changed mid-read; the next revision poll reconciles.
    }
  }
  useFolderRevision(folder, liveRefresh)

  async function changeFolder() {
    const value = await pickFolder(folder)
    if (!value) return
    previewSeq.current += 1
    saveFolder(value); setFolder(value); setSelectedId(undefined); setPreview(PREVIEW_PLACEHOLDER); setFullText(undefined)
  }

  async function showFullText() {
    if (!scanId || !selectedId) return
    try { setFullText((await api.fullText(scanId, selectedId)).text) }
    catch (cause) { setError(getUserMessage(cause)) }
  }

  async function requestOpenFolder(itemId?: string) {
    if (!scanId) return
    try {
      if (isTauri()) {
        // Rust open_folder_by_intent fetches the backend-validated path and
        // opens Explorer; the frontend never handles a raw filesystem path.
        await openInExplorer(scanId, itemId)
        setMessage('탐색기에서 폴더를 열었습니다.')
      } else {
        // Browser dev: call the intent API just to show the resolved path.
        const intent = await api.openFolderIntent(scanId, itemId)
        setMessage(`Desktop 폴더 열기 요청 준비됨 · ${intent.folder}`)
      }
    } catch (cause) { setError(getUserMessage(cause)) }
  }

  const selectedFile = files.find((file) => file.id === selectedId)
  return (
    <div className="feature-page folders-page">
      <div className="page-intro"><div><p className="eyebrow">실제 파일 기준</p><h2>전사 폴더의 결과를 확인하세요</h2><p>{error ?? message}</p></div>
        <div className="inline-actions"><Button variant="secondary" onClick={() => void changeFolder()}><FolderOpen aria-hidden="true" /> 폴더 변경</Button><Button variant="secondary" disabled={!scanId} onClick={() => void requestOpenFolder()}><FolderOpen aria-hidden="true" /> 폴더 열기</Button><Button disabled={!folder || loading} onClick={() => void refresh()}><RefreshCw aria-hidden="true" /> {loading ? '새로고침 중' : '새로고침'}</Button></div></div>
      <div className="filter-bar" aria-label="Folders 필터">{folderFilters.map((item) => <button type="button" key={item.id} className={filter === item.id ? 'filter-button filter-button-active' : 'filter-button'} aria-pressed={filter === item.id} onClick={() => { setFilter(item.id); void refresh(item.id) }}>{item.label}</button>)}</div>
      <div className="folders-layout"><Card className="data-table-card"><div className="data-table-scroll"><table className="data-table folders-table"><caption className="visually-hidden">전사 폴더 파일 목록</caption><thead><tr><th>파일명</th><th>유형</th><th>상태</th><th>수정일</th></tr></thead><tbody>
        {files.map((file) => <tr key={file.id} className={selectedId === file.id ? 'data-row-selected' : undefined}><td><button type="button" className="table-file-button" title={file.filename} onClick={() => void selectItem(file)}>{file.filename}</button></td><td>{file.kind}</td><td><Badge tone={statusTone(file.status)}>{statusLabel(file.status)}</Badge></td><td className="text-numeric">{new Date(file.modified_at).toLocaleString('ko-KR')}</td></tr>)}
        {!loading && files.length === 0 ? <tr><td colSpan={4}>표시할 파일이 없습니다.</td></tr> : null}
      </tbody></table></div></Card>
        <Card className="preview-card"><div className="section-heading-row"><div><span className="eyebrow">TXT Preview</span><h2 className="text-section-heading">{selectedFile?.filename ?? '파일을 선택하세요'}</h2></div><FileText aria-hidden="true" /></div><p className="preview-copy">{preview}</p><div className="inline-actions"><Button variant="secondary" disabled={selectedFile?.kind !== 'TXT'} onClick={() => void showFullText()}><Maximize2 aria-hidden="true" /> 전체 보기</Button><Button variant="secondary" disabled={!selectedId} onClick={() => void requestOpenFolder(selectedId)}><ExternalLink aria-hidden="true" /> 폴더 열기</Button></div></Card>
      </div>
      {fullText !== undefined ? <div className="dialog-backdrop" role="presentation"><div className="dialog dialog-wide" role="dialog" aria-modal="true" aria-labelledby="preview-title"><div className="section-heading-row"><h2 className="text-card-title" id="preview-title">TXT 전체 보기</h2><button type="button" className="icon-action" aria-label="전체 보기 닫기" onClick={() => setFullText(undefined)}><X aria-hidden="true" /></button></div><pre className="full-preview-copy">{fullText}</pre></div></div> : null}
    </div>
  )
}
