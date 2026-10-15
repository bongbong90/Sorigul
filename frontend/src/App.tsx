import { AppShell } from './components/layout/AppShell'
import { TranscriptionPage } from './pages/TranscriptionPage'

function App() {
  return (
    <AppShell activeItem="transcription" title="전사">
      <TranscriptionPage />
    </AppShell>
  )
}

export default App
