import { useEffect, useState } from 'react'
import { AppShell } from './components/layout/AppShell'
import type { NavigationId } from './components/layout/AppShell'
import { useDesktopNotifications } from './hooks/useDesktopNotifications'
import { FoldersPage } from './pages/FoldersPage'
import { LogPage } from './pages/LogPage'
import { SettingsPage } from './pages/SettingsPage'
import { TranscriptionPage } from './pages/TranscriptionPage'

const pageTitles: Record<NavigationId, string> = {
  transcription: '전사',
  log: '로그',
  folders: 'Folders',
  settings: '설정',
}

const pagePaths: Record<NavigationId, string> = {
  transcription: '/',
  log: '/log',
  folders: '/folders',
  settings: '/settings',
}

function pageFromPath(pathname: string): NavigationId {
  const match = (Object.entries(pagePaths) as Array<[NavigationId, string]>).find(
    ([, path]) => path === pathname,
  )
  return match?.[0] ?? 'transcription'
}

function App() {
  const [activePage, setActivePage] = useState<NavigationId>(() => pageFromPath(window.location.pathname))
  useDesktopNotifications()

  useEffect(() => {
    const handlePopState = () => setActivePage(pageFromPath(window.location.pathname))
    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [])

  function handleNavigate(page: NavigationId) {
    window.history.pushState(null, '', pagePaths[page])
    setActivePage(page)
  }

  const page = {
    transcription: <TranscriptionPage />,
    log: <LogPage />,
    folders: <FoldersPage />,
    settings: <SettingsPage />,
  }[activePage]

  return (
    <AppShell activeItem={activePage} title={pageTitles[activePage]} onNavigate={handleNavigate}>
      {page}
    </AppShell>
  )
}

export default App
