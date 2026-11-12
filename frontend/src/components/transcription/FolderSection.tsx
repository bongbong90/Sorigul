import { FolderOpen } from 'lucide-react'
import { Button } from '../ui/Button'
import { Card } from '../ui/Card'

export function FolderSection() {
  return (
    <Card className="folder-section">
      <div className="folder-details">
        <span className="text-caption" id="current-folder-label">
          현재 폴더
        </span>
        <div className="folder-path" aria-labelledby="current-folder-label">
          <FolderOpen className="transcription-icon" aria-hidden="true" focusable="false" />
          <span title="C:\Users\Sorigul\Lectures">C:\Users\Sorigul\Lectures</span>
        </div>
      </div>
      <Button variant="secondary">폴더 변경</Button>
    </Card>
  )
}
