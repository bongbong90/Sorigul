import type { ComponentType, ReactNode, SVGProps } from 'react'
import {
  FoldersIcon,
  LogIcon,
  SettingsIcon,
  TranscriptionIcon,
} from '../icons/AppIcons'

export type NavigationId = 'transcription' | 'log' | 'folders' | 'settings'
type NavigationIcon = ComponentType<SVGProps<SVGSVGElement>>

interface NavigationItem {
  id: NavigationId
  label: string
  href: string
  icon: NavigationIcon
}

interface AppShellProps {
  activeItem: NavigationId
  title: string
  onNavigate: (item: NavigationId) => void
  children?: ReactNode
}

const primaryNavigation: NavigationItem[] = [
  { id: 'transcription', label: '전사', href: '/', icon: TranscriptionIcon },
  { id: 'log', label: '로그', href: '/log', icon: LogIcon },
  { id: 'folders', label: 'Folders', href: '/folders', icon: FoldersIcon },
]

const settingsNavigation: NavigationItem = {
  id: 'settings',
  label: '설정',
  href: '/settings',
  icon: SettingsIcon,
}

function NavigationLink({
  item,
  activeItem,
  onNavigate,
}: {
  item: NavigationItem
  activeItem: NavigationId
  onNavigate: (item: NavigationId) => void
}) {
  const Icon = item.icon
  const isActive = item.id === activeItem

  return (
    <a
      className={['app-navigation-link', isActive ? 'app-navigation-link-active' : '']
        .filter(Boolean)
        .join(' ')}
      href={item.href}
      aria-current={isActive ? 'page' : undefined}
      onClick={(event) => {
        event.preventDefault()
        onNavigate(item.id)
      }}
    >
      <Icon />
      <span>{item.label}</span>
    </a>
  )
}

export function AppShell({ activeItem, title, onNavigate, children }: AppShellProps) {
  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <a
          className="app-brand"
          href="/"
          aria-label="소리글 홈"
          onClick={(event) => {
            event.preventDefault()
            onNavigate('transcription')
          }}
        >
          <span>소리글</span>
        </a>

        <nav className="app-navigation" aria-label="주요 메뉴">
          <div className="app-navigation-primary">
            {primaryNavigation.map((item) => (
              <NavigationLink
                key={item.id}
                item={item}
                activeItem={activeItem}
                onNavigate={onNavigate}
              />
            ))}
          </div>
          <NavigationLink
            item={settingsNavigation}
            activeItem={activeItem}
            onNavigate={onNavigate}
          />
        </nav>
      </aside>

      <header className="app-top-bar">
        <h1 className="text-page-title">{title}</h1>
      </header>

      <main className="app-main" id="main-content">
        <div className="app-main-content">{children}</div>
      </main>
    </div>
  )
}
