import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './styles/tokens.css'
import './styles/typography.css'
import './styles/base.css'
import './styles/components.css'
import './styles/app-shell.css'
import './styles/transcription-screen.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
