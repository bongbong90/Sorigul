import { useEffect, useState } from 'react'
import { AppShell } from './components/layout/AppShell'
import type { NavigationId } from './components/layout/AppShell'
import { useCloseBehaviorSync } from './hooks/useCloseBehaviorSync'
import { useDesktopNotifications } from './hooks/useDesktopNotifications'
import { FoldersPage } from './pages/FoldersPage'
import { LogPage } from './pages/LogPage'
import { SettingsPage } from './pages/SettingsPage'
import { TranscriptionPage } from './pages/TranscriptionPage'
import { retrySidecarStartup, watchSidecarStatus, type SidecarStatus } from './lib/native'

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
  const [sidecarStatus, setSidecarStatus] = useState<SidecarStatus | null>(null)
  useDesktopNotifications()
  useCloseBehaviorSync()

  useEffect(() => {
    const handlePopState = () => setActivePage(pageFromPath(window.location.pathname))
    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [])

  useEffect(() => {
    let active = true
    let unsubscribe: (() => void) | undefined
    void watchSidecarStatus((status) => {
      if (active) setSidecarStatus(status)
    }).then((stop) => {
      if (active) unsubscribe = stop
      else stop()
    }).catch(() => {
      if (active) {
        setSidecarStatus({
          state: 'STARTUP_FAILED', owned: null, code: 'STATUS_UNAVAILABLE',
          message: 'Backend 시작 상태를 확인하지 못했습니다. 다시 시도해 주세요.',
        })
      }
    })
    return () => { active = false; unsubscribe?.() }
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
    <AppShell
      activeItem={activePage}
      title={pageTitles[activePage]}
      onNavigate={handleNavigate}
      sidecarStatus={sidecarStatus}
      onRetrySidecar={() => void retrySidecarStartup()}
    >
      {page}
    </AppShell>
  )
}

export default App
