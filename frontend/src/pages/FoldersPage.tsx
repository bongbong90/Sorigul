import { useMemo, useState } from 'react'
import { ExternalLink, FileText, FolderOpen, Maximize2, RefreshCw, X } from 'lucide-react'
import { Badge, type BadgeTone } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'

type FolderFilter = 'all' | 'complete' | 'incomplete' | 'results'
type FolderStatus = '완료' | '미완료' | '결과 파일'

interface FolderFile {
  id: string
  filename: string
  type: 'MP3' | 'TXT' | 'JSON' | 'SRT'
  status: FolderStatus
  modified: string
}

const initialFiles: FolderFile[] = [
  { id: 'mp3-1', filename: '개념완성_부동산공법_8주차_1강.mp3', type: 'MP3', status: '완료', modified: '2026-08-27 21:42' },
  { id: 'txt-1', filename: '개념완성_부동산공법_8주차_1강.txt', type: 'TXT', status: '결과 파일', modified: '2026-08-27 22:22' },
  { id: 'json-1', filename: '개념완성_부동산공법_8주차_1강.json', type: 'JSON', status: '결과 파일', modified: '2026-08-27 22:22' },
  { id: 'srt-1', filename: '개념완성_부동산공법_8주차_1강.srt', type: 'SRT', status: '결과 파일', modified: '2026-08-27 22:22' },
  { id: 'mp3-2', filename: '기본이론_민법_8주차_23강.mp3', type: 'MP3', status: '미완료', modified: '2026-08-27 18:06' },
  { id: 'mp3-long', filename: '30강_[8주차]_26_04_22_주택법_주택의_건설과_공급_및_리모델링에_관한_긴_파일명.mp3', type: 'MP3', status: '미완료', modified: '2026-08-27 17:54' },
]

const previewText =
  '민법에서 법률행위는 의사표시를 요소로 하는 법률요건입니다. 의사표시의 해석에서는 당사자의 진정한 의사와 표시된 내용을 함께 살펴야 합니다. 강의에서는 법률행위의 성립요건과 효력요건을 구분하고, 의사와 표시가 일치하지 않는 경우의 효과를 사례 중심으로 설명합니다. 비진의표시, 통정허위표시, 착오, 사기와 강박의 요건을 비교할 때에는 선의의 제3자 보호 여부와 취소 가능성을 함께 확인해야 합니다. 각 유형의 요건과 효과를 표로 정리하면 사례 판단 순서를 더 쉽게 확인할 수 있습니다.'

const folderFilters: Array<{ id: FolderFilter; label: string }> = [
  { id: 'all', label: '전체' },
  { id: 'complete', label: '완료' },
  { id: 'incomplete', label: '미완료' },
  { id: 'results', label: '결과만' },
]

function statusTone(status: FolderStatus): BadgeTone {
  if (status === '완료') return 'done'
  if (status === '미완료') return 'waiting'
  return 'preparing'
}

export function FoldersPage() {
  const [filter, setFilter] = useState<FolderFilter>('all')
  const [files, setFiles] = useState(initialFiles)
  const [selectedId, setSelectedId] = useState('txt-1')
  const [message, setMessage] = useState('실제 디스크 상태를 기준으로 표시합니다.')
  const [showFullPreview, setShowFullPreview] = useState(false)

  const visibleFiles = useMemo(
    () =>
      files.filter((file) => {
        if (filter === 'complete') return file.status === '완료'
        if (filter === 'incomplete') return file.status === '미완료'
        if (filter === 'results') return file.status === '결과 파일'
        return true
      }),
    [files, filter],
  )
  const selectedFile = files.find((file) => file.id === selectedId)

  function handleRefresh() {
    setFiles((currentFiles) => {
      if (currentFiles.some((file) => file.id === 'external-srt')) return currentFiles
      return [
        ...currentFiles,
        { id: 'external-srt', filename: '외부에서_추가된_민법_보충자료.srt', type: 'SRT', status: '결과 파일', modified: '방금 전' },
      ]
    })
    setMessage('새로고침 완료 · 앱 외부에서 추가된 파일 변경을 반영했습니다.')
  }

  return (
    <div className="feature-page folders-page">
      <div className="page-intro">
        <div>
          <p className="eyebrow">실제 파일 기준</p>
          <h2>전사 폴더의 결과를 확인하세요</h2>
          <p>{message}</p>
        </div>
        <div className="inline-actions">
          <Button variant="secondary" onClick={() => setMessage('현재 미리보기에서는 폴더 위치를 안내만 합니다.')}>
            <FolderOpen aria-hidden="true" /> 폴더 열기
          </Button>
          <Button onClick={handleRefresh}>
            <RefreshCw aria-hidden="true" /> 새로고침
          </Button>
        </div>
      </div>

      <div className="filter-bar" aria-label="Folders 필터">
        {folderFilters.map((item) => (
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

      <div className="folders-layout">
        <Card className="data-table-card">
          <div className="data-table-scroll">
            <table className="data-table folders-table">
              <caption className="visually-hidden">전사 폴더 파일 목록</caption>
              <thead><tr><th>파일명</th><th>유형</th><th>상태</th><th>수정일</th></tr></thead>
              <tbody>
                {visibleFiles.map((file) => (
                  <tr key={file.id} className={selectedId === file.id ? 'data-row-selected' : undefined}>
                    <td>
                      <button type="button" className="table-file-button" title={file.filename} onClick={() => setSelectedId(file.id)}>
                        {file.filename}
                      </button>
                    </td>
                    <td>{file.type}</td>
                    <td><Badge tone={statusTone(file.status)}>{file.status}</Badge></td>
                    <td className="text-numeric">{file.modified}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <Card className="preview-card">
          <div className="section-heading-row">
            <div>
              <span className="eyebrow">TXT Preview</span>
              <h2 className="text-section-heading">{selectedFile?.filename ?? '파일을 선택하세요'}</h2>
            </div>
            <FileText aria-hidden="true" />
          </div>
          <p className="preview-copy">{selectedFile?.type === 'TXT' ? previewText : 'TXT 결과 파일을 선택하면 약 500자 미리보기를 표시합니다.'}</p>
          <div className="inline-actions">
            <Button variant="secondary" disabled={selectedFile?.type !== 'TXT'} onClick={() => setShowFullPreview(true)}>
              <Maximize2 aria-hidden="true" /> 전체 보기
            </Button>
            <Button variant="secondary" onClick={() => setMessage('현재 미리보기에서는 선택한 파일의 위치를 안내만 합니다.')}>
              <ExternalLink aria-hidden="true" /> 폴더 열기
            </Button>
          </div>
        </Card>
      </div>

      {showFullPreview ? (
        <div className="dialog-backdrop" role="presentation">
          <div className="dialog dialog-wide" role="dialog" aria-modal="true" aria-labelledby="preview-title">
            <div className="section-heading-row">
              <h2 className="text-card-title" id="preview-title">TXT 전체 보기</h2>
              <button type="button" className="icon-action" aria-label="전체 보기 닫기" onClick={() => setShowFullPreview(false)}><X aria-hidden="true" /></button>
            </div>
            <p className="full-preview-copy">{previewText} {previewText}</p>
          </div>
        </div>
      ) : null}
    </div>
  )
}
