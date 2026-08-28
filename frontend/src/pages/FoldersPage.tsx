import { useCallback, useEffect, useState } from 'react'
import { ExternalLink, FileText, FolderOpen, Maximize2, RefreshCw, X } from 'lucide-react'
import { api, getSavedFolder, getUserMessage, saveFolder, type FolderFilter, type FolderItem } from '../api/client'
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

export function FoldersPage() {
  const [folder, setFolder] = useState(getSavedFolder)
  const [filter, setFilter] = useState<FolderFilter>('all')
  const [scanId, setScanId] = useState('')
  const [files, setFiles] = useState<FolderItem[]>([])
  const [selectedId, setSelectedId] = useState<string>()
  const [preview, setPreview] = useState('TXT 결과 파일을 선택하면 약 500자 미리보기를 표시합니다.')
  const [fullText, setFullText] = useState<string>()
  const [message, setMessage] = useState(folder ? '실제 디스크 상태를 기준으로 표시합니다.' : '전사 폴더를 선택해 주세요.')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string>()

  const refresh = useCallback(async (nextFilter = filter) => {
    if (!folder) return
    setLoading(true); setError(undefined)
    try {
      const result = await api.folders(folder, nextFilter)
      setScanId(result.scan_id); setFiles(result.items)
      setSelectedId((current) => result.items.some((item) => item.id === current) ? current : undefined)
      setMessage(`새로고침 완료 · ${result.items.length}개 표시`)
    } catch (cause) {
      setFiles([]); setError(getUserMessage(cause))
    } finally { setLoading(false) }
  }, [filter, folder])

  useEffect(() => { void refresh() }, [refresh])

  async function selectItem(file: FolderItem) {
    setSelectedId(file.id); setFullText(undefined)
    if (file.kind !== 'TXT' || !scanId) {
      setPreview('TXT 결과 파일을 선택하면 약 500자 미리보기를 표시합니다.'); return
    }
    try {
      const result = await api.textPreview(scanId, file.id)
      setPreview(result.text || 'TXT 파일이 비어 있습니다.')
    } catch (cause) { setPreview(getUserMessage(cause)) }
  }

  async function changeFolder() {
    const value = await pickFolder(folder)
    if (!value) return
    saveFolder(value); setFolder(value); setSelectedId(undefined)
  }

  async function showFullText() {
    if (!scanId || !selectedId) return
    try { setFullText((await api.fullText(scanId, selectedId)).text) }
    catch (cause) { setError(getUserMessage(cause)) }
  }

  async function requestOpenFolder(itemId?: string) {
    if (!scanId) return
    try {
      const intent = await api.openFolderIntent(scanId, itemId)
      if (isTauri()) {
        await openInExplorer(intent.folder, intent.item_filename)
        setMessage(`탐색기에서 폴더를 열었습니다 · ${intent.folder}`)
      } else {
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
