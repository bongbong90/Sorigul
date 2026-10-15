import { CurrentTaskSection } from '../components/transcription/CurrentTaskSection'
import { FolderSection } from '../components/transcription/FolderSection'
import { QueueTable } from '../components/transcription/QueueTable'
import { TranscriptionActions } from '../components/transcription/TranscriptionActions'

export function TranscriptionPage() {
  return (
    <div className="transcription-page">
      <FolderSection />
      <TranscriptionActions />
      <CurrentTaskSection />
      <QueueTable />
    </div>
  )
}
