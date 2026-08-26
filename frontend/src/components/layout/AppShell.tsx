import type { ComponentType, ReactNode, SVGProps } from 'react'
import {
  DashboardIcon,
  ResultsIcon,
  SettingsIcon,
  TranscriptionIcon,
} from '../icons/AppIcons'

type NavigationId = 'transcription' | 'dashboard' | 'results' | 'settings'
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
  children?: ReactNode
}

const primaryNavigation: NavigationItem[] = [
  { id: 'transcription', label: '전사', href: '/', icon: TranscriptionIcon },
  { id: 'dashboard', label: '대시보드', href: '/dashboard', icon: DashboardIcon },
  { id: 'results', label: '결과', href: '/results', icon: ResultsIcon },
]

const settingsNavigation: NavigationItem = {
  id: 'settings',
  label: '설정',
  href: '/settings',
  icon: SettingsIcon,
}

function NavigationLink({ item, activeItem }: { item: NavigationItem; activeItem: NavigationId }) {
  const Icon = item.icon
  const isActive = item.id === activeItem

  return (
    <a
      className={['app-navigation-link', isActive ? 'app-navigation-link-active' : '']
        .filter(Boolean)
        .join(' ')}
      href={item.href}
      aria-current={isActive ? 'page' : undefined}
    >
      <Icon />
      <span>{item.label}</span>
    </a>
  )
}

export function AppShell({ activeItem, title, children }: AppShellProps) {
  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <a className="app-brand" href="/" aria-label="소리글 홈">
          <span>소리글</span>
        </a>

        <nav className="app-navigation" aria-label="주요 메뉴">
          <div className="app-navigation-primary">
            {primaryNavigation.map((item) => (
              <NavigationLink key={item.id} item={item} activeItem={activeItem} />
            ))}
          </div>
          <NavigationLink item={settingsNavigation} activeItem={activeItem} />
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
