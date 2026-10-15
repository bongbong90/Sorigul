import { AudioLines, FileText, LayoutDashboard, Settings } from 'lucide-react'
import type { LucideProps } from 'lucide-react'

type IconProps = LucideProps

const DEFAULT_ICON_SIZE = 20
const DEFAULT_ICON_STROKE_WIDTH = 1.75

function iconClassName(className?: string) {
  return ['app-icon', className].filter(Boolean).join(' ')
}

export function TranscriptionIcon({ className, ...props }: IconProps) {
  return (
    <AudioLines
      {...props}
      className={iconClassName(className)}
      size={DEFAULT_ICON_SIZE}
      strokeWidth={DEFAULT_ICON_STROKE_WIDTH}
      aria-hidden="true"
      focusable="false"
    />
  )
}

export function DashboardIcon({ className, ...props }: IconProps) {
  return (
    <LayoutDashboard
      {...props}
      className={iconClassName(className)}
      size={DEFAULT_ICON_SIZE}
      strokeWidth={DEFAULT_ICON_STROKE_WIDTH}
      aria-hidden="true"
      focusable="false"
    />
  )
}

export function ResultsIcon({ className, ...props }: IconProps) {
  return (
    <FileText
      {...props}
      className={iconClassName(className)}
      size={DEFAULT_ICON_SIZE}
      strokeWidth={DEFAULT_ICON_STROKE_WIDTH}
      aria-hidden="true"
      focusable="false"
    />
  )
}

export function SettingsIcon({ className, ...props }: IconProps) {
  return (
    <Settings
      {...props}
      className={iconClassName(className)}
      size={DEFAULT_ICON_SIZE}
      strokeWidth={DEFAULT_ICON_STROKE_WIDTH}
      aria-hidden="true"
      focusable="false"
    />
  )
}
