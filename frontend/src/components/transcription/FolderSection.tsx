import { FolderOpen } from 'lucide-react'
import { Button } from '../ui/Button'
import { Card } from '../ui/Card'

interface FolderSectionProps {
  folderPath: string
  onChangeFolder: () => void
}

export function FolderSection({ folderPath, onChangeFolder }: FolderSectionProps) {
  return (
    <Card className="folder-section">
      <div className="folder-details">
        <span className="text-caption" id="current-folder-label">
          현재 폴더
        </span>
        <div className="folder-path" aria-labelledby="current-folder-label">
          <FolderOpen className="transcription-icon" aria-hidden="true" focusable="false" />
          <span title={folderPath}>{folderPath}</span>
        </div>
      </div>
      <Button variant="secondary" onClick={onChangeFolder}>
        폴더 변경
      </Button>
    </Card>
  )
}
