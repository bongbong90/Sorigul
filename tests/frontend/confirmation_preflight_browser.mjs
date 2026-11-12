// Source-only DOM fixture: real React/page/components/CSS, synthetic APIs.
// No desktop runtime, installed application, user data, or new dependencies.
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..')
const frontend = path.join(root, 'frontend')
const { createServer } = await import(pathToFileURL(path.join(frontend, 'node_modules/vite/dist/node/index.js')).href)
const { default: react } = await import(pathToFileURL(path.join(frontend, 'node_modules/@vitejs/plugin-react/dist/index.js')).href)
const mockId = '\0sorigul-171-api'
const entryId = '\0sorigul-171-entry'
const mock = `
const type = new URLSearchParams(location.search).get('type') || 'INVALID_TARGET';
const control = window.__171 = { created: [], started: [], normalized: [], renamed: [], release: null };
const settings = { transcription_folder: 'B', last_course: '정규', last_subject: '민법', subject_stage_overrides: {} };
const files = [
  { id: 'DONE', filename: 'DONE.mp3', completion_status: 'DONE' },
  { id: 'B1', filename: 'B1.mp3', completion_status: 'INCOMPLETE' },
  { id: 'B2', filename: 'B2.mp3', completion_status: 'INCOMPLETE' },
];
const job = (status) => ({ job_id: 'synthetic-171', folder: 'B', status, files: {}, drive: {}, events: [], total_files: 2, done_files: 0, failed_files: 0 });
export const api = {
  health: async () => ({}), settings: async () => settings, saveSettings: async (value) => value,
  scan: async () => files, jobs: async () => [], activeJob: async () => null,
  driveStatus: async () => ({ auth_state: 'CONNECTED' }),
  normalizeBatch: async (_, names) => {
    control.normalized.push([...names]);
    if (new URLSearchParams(location.search).has('hold') && control.normalized.length === 1) {
      await new Promise((resolve) => { control.release = resolve });
    }
    return names.map((name) => ({ original_name: name, suggested_name: name, result_type: type,
      can_apply: false, warnings: [], conflicts: type === 'CONFLICT' ? ['occupied'] : [],
      detected_course: '기초', detected_subject: '민법', detected_week: 1, detected_lesson: 1 }));
  },
  rename: async (_, oldStem, newStem) => { control.renamed.push([oldStem, newStem]); return { old_file_id: oldStem, new_file_id: newStem } },
  createJob: async (value) => { control.created.push(value); return job('WAITING') },
  startJob: async (id) => { control.started.push(id); return job('TRANSCRIBING') },
  job: async () => job('TRANSCRIBING'),
};
export const getSavedFolder = () => 'B';
export const saveFolder = () => {};
export const getUserMessage = (e) => e.message;
export const isRequestAbort = (e) => e.name === 'AbortError';
export const isRequestTimeout = () => false;
`
const entry = `
import { createElement } from 'react';
import { createRoot } from 'react-dom/client';
import { TranscriptionPage } from '/src/pages/TranscriptionPage.tsx';
import '/src/styles/tokens.css';
import '/src/styles/typography.css';
import '/src/styles/base.css';
import '/src/styles/components.css';
import '/src/styles/transcription-screen.css';
import '/src/styles/feature-pages.css';
createRoot(document.getElementById('root')).render(createElement(TranscriptionPage));
`
const server = await createServer({
  configFile: false, root: frontend, clearScreen: false, logLevel: 'error',
  resolve: { dedupe: ['react', 'react-dom'] },
  plugins: [react(), {
    name: 'sorigul-171-synthetic-api',
    enforce: 'pre',
    resolveId(id) {
      if (id.endsWith('/api/client')) return mockId
      if (id.endsWith('/lib/native')) return '\0sorigul-171-native'
      if (id.endsWith('/useTrayProgress') || id.endsWith('/useFolderRevision')) return '\0sorigul-171-hooks'
      if (id === '/__171_entry.js') return entryId
    },
    load(id) {
      if (id === mockId) return mock
      if (id === entryId) return entry
      if (id === '\0sorigul-171-native') return 'export const pickFolder = async () => null; export const openInBrowser = async () => {}'
      if (id === '\0sorigul-171-hooks') return 'export const useTrayProgress = () => {}; export const useFolderRevision = () => {}'
    },
    configureServer(instance) {
      instance.middlewares.use(async (req, res, next) => {
        if (!req.url.startsWith('/__171__')) return next()
        res.setHeader('Content-Type', 'text/html; charset=utf-8')
        res.end(await instance.transformIndexHtml(req.url, '<!doctype html><html><body><div id="root"></div><script type="module" src="/__171_entry.js"></script></body></html>'))
      })
    },
  }],
  server: { host: '127.0.0.1', port: 0, strictPort: false },
})
await server.listen()
console.log(`READY http://127.0.0.1:${server.httpServer.address().port}/__171__`)
process.on('SIGTERM', async () => { await server.close(); process.exit(0) })
