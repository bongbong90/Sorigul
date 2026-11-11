import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './styles/tokens.css'
import './styles/typography.css'
import './styles/base.css'
import './styles/components.css'
import './styles/app-shell.css'
import './styles/transcription-screen.css'
import './styles/feature-pages.css'
import './styles/completion-toast.css'
import App from './App.tsx'
import { CompletionToast } from './components/notification/CompletionToast.tsx'
import { isCompletionToastWindow } from './lib/native'

// One bundle, two windows: the reusable completion toast renders only its own
// view (no App polling, no main-window hooks).
createRoot(document.getElementById('root')!).render(
  <StrictMode>{isCompletionToastWindow() ? <CompletionToast /> : <App />}</StrictMode>,
)
