import { useEffect, useMemo, useState } from 'react'
import { CurrentTaskSection } from '../components/transcription/CurrentTaskSection'
import { FolderSection } from '../components/transcription/FolderSection'
import { QueueTable, type QueueRow } from '../components/transcription/QueueTable'
import { TranscriptionActions } from '../components/transcription/TranscriptionActions'

type MockRunState = 'IDLE' | 'TRANSCRIBING' | 'DONE' | 'CANCELLED'

const MOCK_FOLDERS = ['C:\\Users\\Sorigul\\Lectures', 'C:\\Users\\Sorigul\\CivilLaw']

const MOCK_FILES: QueueRow[] = [
  {
    id: 'public-law-08-01',
    filename: '개념완성_부동산공법_8주차_1강.mp3',
    duration: '54:20',
    status: 'DONE',
  },
  {
    id: 'public-law-08-02',
    filename: '개념완성_부동산공법_8주차_2강.mp3',
    duration: '48:15',
    status: 'WAITING',
  },
  {
    id: 'brokerage-law-03-04',
    filename: '중개사법_핵심이론_3주차_4강.mp3',
    duration: '52:10',
    status: 'WAITING',
  },
  {
    id: 'long-filename-sample',
    filename:
      '30강_[8주차]_26_04_22_[교재2]_주택법_주택의_건설과_공급_및_리모델링에_관한_긴_파일명_예시.mp3',
    duration: '61:05',
    status: 'WAITING',
  },
]

function createMockRows() {
  return MOCK_FILES.map((row) => ({ ...row }))
}

export function TranscriptionPage() {
  const [folderIndex, setFolderIndex] = useState(0)
  const [rows, setRows] = useState(createMockRows)
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [runState, setRunState] = useState<MockRunState>('IDLE')
  const [activeQueue, setActiveQueue] = useState<string[]>([])
  const [activeIndex, setActiveIndex] = useState(0)
  const [progress, setProgress] = useState(0)

  const currentId = activeQueue[activeIndex]
  const currentRow = rows.find((row) => row.id === currentId)
  const completedCount = rows.filter((row) => row.status === 'DONE').length
  const isRunning = runState === 'TRANSCRIBING'
  const canStart = selectedIds.length > 0 && !isRunning

  const selectedIdSet = useMemo(() => new Set(selectedIds), [selectedIds])

  useEffect(() => {
    if (!isRunning || !currentId) {
      return
    }

    const timerId = window.setTimeout(() => {
      if (progress < 90) {
        setProgress(progress + 10)
        return
      }

      const nextId = activeQueue[activeIndex + 1]
      setRows((currentRows) =>
        currentRows.map((row) => {
          if (row.id === currentId) {
            return { ...row, status: 'DONE' }
          }
          if (row.id === nextId) {
            return { ...row, status: 'TRANSCRIBING' }
          }
          return row
        }),
      )

      if (nextId) {
        setActiveIndex((currentIndex) => currentIndex + 1)
        setProgress(0)
        return
      }

      setRunState('DONE')
      setProgress(100)
    }, 500)

    return () => window.clearTimeout(timerId)
  }, [activeIndex, activeQueue, currentId, isRunning, progress])

  function handleChangeFolder() {
    setFolderIndex((currentIndex) => (currentIndex + 1) % MOCK_FOLDERS.length)
    setRows(createMockRows())
    setSelectedIds([])
    setRunState('IDLE')
    setActiveQueue([])
    setActiveIndex(0)
    setProgress(0)
  }

  function handleToggle(id: string) {
    setSelectedIds((currentIds) =>
      currentIds.includes(id)
        ? currentIds.filter((selectedId) => selectedId !== id)
        : [...currentIds, id],
    )
  }

  function handleToggleAll() {
    setSelectedIds(selectedIds.length === rows.length ? [] : rows.map((row) => row.id))
  }

  function handleStart() {
    if (!canStart) {
      return
    }

    const nextQueue = rows.filter((row) => selectedIdSet.has(row.id)).map((row) => row.id)
    const firstId = nextQueue[0]

    setRows((currentRows) =>
      currentRows.map((row) => {
        if (!selectedIdSet.has(row.id)) {
          return row
        }
        return { ...row, status: row.id === firstId ? 'TRANSCRIBING' : 'WAITING' }
      }),
    )
    setActiveQueue(nextQueue)
    setActiveIndex(0)
    setProgress(0)
    setRunState('TRANSCRIBING')
  }

  function handleStop() {
    if (!isRunning || !currentId) {
      return
    }

    setRows((currentRows) =>
      currentRows.map((row) =>
        row.id === currentId ? { ...row, status: 'CANCELLED' } : row,
      ),
    )
    setRunState('CANCELLED')
  }

  return (
    <div className="transcription-page">
      <FolderSection
        folderPath={MOCK_FOLDERS[folderIndex]}
        onChangeFolder={handleChangeFolder}
      />
      <TranscriptionActions
        completedCount={completedCount}
        selectedCount={selectedIds.length}
        totalCount={rows.length}
        canStart={canStart}
        canStop={isRunning}
        onStart={handleStart}
        onStop={handleStop}
      />
      <CurrentTaskSection
        filename={currentRow?.filename}
        progress={progress}
        status={runState}
      />
      <QueueTable
        rows={rows}
        selectedIds={selectedIds}
        currentId={currentId}
        onToggle={handleToggle}
        onToggleAll={handleToggleAll}
      />
    </div>
  )
}
