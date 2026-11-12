import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Tauri expects a fixed, predictable dev server (see src-tauri/tauri.conf.json
// `devUrl`) and ignores its own Rust build output so file-watch doesn't loop.
// https://v2.tauri.app/start/frontend/vite/
export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: {
    port: 5173,
    strictPort: true,
    watch: { ignored: ['**/src-tauri/**'] },
  },
})
