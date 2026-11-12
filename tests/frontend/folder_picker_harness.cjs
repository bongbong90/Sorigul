// Execute the production TSX page and revision hook without new dependencies.
// The hook host batches state, runs dependency-based effects/cleanup, and
// exposes JSX props. API promises deliberately ignore abort to test races.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const root = path.resolve(__dirname, '../..')
const ts = require(path.join(root, 'frontend/node_modules/typescript'))
const pagePath = path.join(root, 'frontend/src/pages/TranscriptionPage.tsx')
const deferred = () => {
  let resolve, reject
  const promise = new Promise((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
const fixtures = {
  A: ['DONE', 'DONE', 'INCOMPLETE', 'INCOMPLETE'],
  B: ['DONE', 'INCOMPLETE', 'INCOMPLETE'],
  C: ['INCOMPLETE'],
}
function files(folder) {
  return fixtures[folder].map((completion_status, i) => ({
    id: i === 0 ? 'shared' : `${folder}${i}`, filename: `${folder}${i}.mp3`,
    completion_status, duration_seconds: 10,
  }))
}
function job(folder, status = 'DONE', id = folder) {
  return { job_id: id, folder, status, updated_at: '2026-10-06', files: {},
    drive: {}, events: [], total_files: 4, done_files: 2, failed_files: 0 }
}
function host(initialFolder = 'A', { ignoreAbort = false } = {}) {
  const slots = [], effects = [], timers = new Map(), cache = new Map()
  let cursor = 0, dirty = true, tree, timerId = 0, picked, savedFolder = initialFolder
  let pickerImpl = async () => picked
  const scans = [], settingsWrites = []
  let jobs = [], scanImpl = async (folder) => files(folder)
  let saveImpl = async (value) => value, healthImpl = async () => ({})
  let settingsImpl = async () => ({ transcription_folder: initialFolder,
    last_course: '정규', last_subject: '민법', subject_stage_overrides: {} })
  let revision = 'baseline', normalizeImpl = async () => []
  const created = []
  const api = {
    settings: (...args) => settingsImpl(...args), health: (...args) => healthImpl(...args),
    saveSettings: (value) => { settingsWrites.push(value); return saveImpl(value) },
    scan: (folder, signal) => { scans.push({ folder, signal }); return scanImpl(folder, signal) },
    jobs: async () => jobs, driveStatus: async () => ({ auth_state: 'CONNECTED' }),
    activeJob: async () => null, folderRevision: async () => ({ revision }),
    normalizeBatch: (...args) => normalizeImpl(...args),
    createJob: async (value) => { created.push(value); return job(value.folder) },
    startJob: async () => job(savedFolder),
  }
  const changed = (a, b) => !a || !b || a.length !== b.length || a.some((v, i) => !Object.is(v, b[i]))
  const react = {
    useState: (initial) => {
      const index = cursor++
      if (!slots[index]) slots[index] = { value: typeof initial === 'function' ? initial() : initial }
      const set = (next) => {
        const value = typeof next === 'function' ? next(slots[index].value) : next
        if (!Object.is(value, slots[index].value)) { slots[index].value = value; dirty = true }
      }
      return [slots[index].value, set]
    },
    useRef: (initial) => { const i = cursor++; return (slots[i] ??= { current: initial }) },
    useMemo: (fn, deps) => {
      const i = cursor++
      if (!slots[i] || changed(slots[i].deps, deps)) slots[i] = { value: fn(), deps }
      return slots[i].value
    },
    useCallback: (fn, deps) => react.useMemo(() => fn, deps),
    useEffect: (fn, deps) => {
      const i = cursor++
      if (!slots[i] || changed(slots[i].deps, deps)) {
        const old = slots[i]
        slots[i] = { deps, cleanup: old?.cleanup }
        effects.push(() => { old?.cleanup?.(); slots[i].cleanup = fn() })
      }
    },
  }
  const stub = (name) => Object.defineProperty(() => {}, 'name', { value: name })
  const stubs = new Proxy({}, { get: (_, name) => stub(name) })
  const jsx = (type, props) => ({ type, props: props ?? {} })
  const window = {
    setTimeout: (cb, ms) => { timers.set(++timerId, { cb, ms }); return timerId },
    clearTimeout: (id) => timers.delete(id),
    setInterval: (cb, ms) => { timers.set(++timerId, { cb, ms }); return timerId },
    clearInterval: (id) => timers.delete(id),
  }
  const Controller = ignoreAbort ? class extends AbortController { abort() {} } : AbortController
  const context = vm.createContext({ window, AbortController: Controller, Date, console, setTimeout: window.setTimeout, clearTimeout: window.clearTimeout })
  function load(filename) {
    if (cache.has(filename)) return cache.get(filename)
    const source = filename === pagePath && process.argv[2] ? fs.readFileSync(process.argv[2], 'utf8') : fs.readFileSync(filename, 'utf8')
    const code = ts.transpileModule(source, { compilerOptions: {
      target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX,
    } }).outputText
    const module = { exports: {} }
    cache.set(filename, module.exports)
    const requireLocal = (name) => {
      if (name === 'react') return react
      if (name === 'react/jsx-runtime') return { jsx, jsxs: jsx }
      if (name === 'lucide-react' || name.includes('/components/')) return stubs
      if (name.endsWith('/api/client')) return {
        api, getSavedFolder: () => savedFolder, saveFolder: (value) => { savedFolder = value },
        isRequestAbort: (e) => e.name === 'AbortError', isRequestTimeout: () => false,
        getUserMessage: (e) => e.message,
      }
      if (name.endsWith('/lib/native')) return { pickFolder: () => pickerImpl() }
      if (name.endsWith('/useTrayProgress')) return { useTrayProgress: () => {} }
      return load(path.resolve(path.dirname(filename), `${name}.ts`))
    }
    const wrapper = new vm.Script(`(function(require,module,exports){${code}\n})`, { filename }).runInContext(context)
    wrapper(requireLocal, module, module.exports)
    cache.set(filename, module.exports)
    return module.exports
  }
  const { TranscriptionPage } = load(pagePath)
  function render() {
    cursor = 0; dirty = false; tree = TranscriptionPage()
    while (effects.length) effects.shift()()
    return tree
  }
  async function settle() {
    for (let i = 0; i < 100; i++) { await Promise.resolve(); if (dirty) render() }
  }
  function nodes(node) {
    if (node == null || typeof node !== 'object') return []
    if (Array.isArray(node)) return node.flatMap(nodes)
    return [node, ...nodes(node.props?.children)]
  }
  function component(name) {
    const result = nodes(tree).find((n) => n.type?.name === name)
    assert.ok(result, `missing ${name}`)
    return result.props
  }
  function text(node) {
    if (node == null || typeof node === 'boolean') return ''
    if (Array.isArray(node)) return node.map(text).join('')
    if (typeof node !== 'object') return String(node)
    return text(node.props?.children)
  }
  render()
  return {
    settle, scans, settingsWrites, created, component,
    rows: () => component('QueueTable').rows,
    dialog: () => nodes(tree).find((n) => n.props?.role === 'dialog'),
    text, saved: () => savedFolder,
    pick: async (folder) => { picked = folder; component('FolderSection').onChangeFolder(); await settle() },
    openPicker: () => {
      const pending = deferred(); pickerImpl = () => pending.promise
      component('FolderSection').onChangeFolder()
      return pending
    },
    scan: (fn) => { scanImpl = fn }, jobs: (value) => { jobs = value },
    save: (fn) => { saveImpl = fn }, health: (fn) => { healthImpl = fn },
    settings: (fn) => { settingsImpl = fn }, normalize: (fn) => { normalizeImpl = fn },
    revision: (value) => { revision = value },
    hasTimer: (ms) => [...timers.values()].some((value) => value.ms === ms),
    tick: async (ms) => {
      const entry = [...timers.entries()].find(([, value]) => value.ms === ms)
      assert.ok(entry, `missing ${ms}ms timer`)
      timers.delete(entry[0]); entry[1].cb(); await settle()
    },
    reconnect: async () => { component('RuntimeBanner').onReconnect(); await settle() },
    unmount: () => { for (const slot of slots) slot?.cleanup?.(); timers.clear() },
  }
}
const cases = {}
cases.empty_to_a = async () => {
  const h = host(''); await h.settle(); await h.pick('A')
  assert.equal(h.rows().length, 4); assert.equal(h.scans.at(-1).folder, 'A'); h.unmount()
}
cases.immediate_clear = async () => {
  const h = host(); await h.settle()
  h.component('QueueTable').onToggle('shared'); await h.settle()
  h.component('TranscriptionActions').onStart(); await h.settle()
  const pending = deferred(); h.scan(() => pending.promise)
  await h.pick('B')
  assert.equal(h.component('FolderSection').folderPath, 'B')
  assert.equal(h.saved(), 'B'); assert.equal(h.rows().length, 0)
  assert.equal(h.component('QueueTable').selectedIds.length, 0)
  assert.equal(h.dialog(), undefined)
  assert.match(h.component('RuntimeBanner').message, /새 폴더/)
  h.unmount()
}
cases.rows_counts = async () => {
  const h = host(); await h.settle(); await h.pick('B')
  assert.deepEqual(h.rows().map((r) => r.filename), ['B0.mp3', 'B1.mp3', 'B2.mp3'])
  assert.equal(h.rows().filter((r) => r.status === 'DONE').length, 1)
  h.unmount()
}
cases.confirmation_counts = async () => {
  const h = host(); await h.settle()
  h.component('TranscriptionActions').onStart(); await h.settle()
  assert.match(h.text(h.dialog()), /전체 4개 중 완료 2개를 제외한 2개/)
  await h.pick('B'); assert.equal(h.dialog(), undefined)
  h.component('TranscriptionActions').onStart(); await h.settle()
  assert.match(h.text(h.dialog()), /전체 3개 중 완료 1개를 제외한 2개/)
  h.unmount()
}
cases.selection_shared_stem = async () => {
  const h = host(); await h.settle()
  h.component('QueueTable').onToggle('shared'); await h.settle()
  await h.pick('B'); assert.equal(h.component('QueueTable').selectedIds.length, 0)
  h.unmount()
}
cases.job_clear_and_match = async () => {
  const h = host(); h.jobs([job('A')]); await h.settle()
  assert.equal(h.component('CurrentTaskSection').status, 'DONE')
  const pending = deferred(); h.scan(() => pending.promise)
  await h.pick('B'); assert.equal(h.component('CurrentTaskSection').status, 'IDLE')
  pending.resolve(files('B')); await h.settle()
  assert.equal(h.component('CurrentTaskSection').status, 'IDLE')
  h.jobs([job('A'), job('C', 'FAILED')]); h.scan(async (folder) => files(folder))
  await h.pick('C'); assert.equal(h.component('CurrentTaskSection').status, 'FAILED')
  h.unmount()
}
cases.late_a = async () => {
  const h = host(), a = deferred(); h.scan((folder) => folder === 'A' ? a.promise : Promise.resolve(files(folder)))
  h.jobs([job('A')]); await h.settle(); await h.pick('B')
  assert.equal(h.scans[0].signal.aborted, true)
  a.resolve(files('A')); await h.settle()
  assert.equal(h.rows().length, 3); assert.equal(h.rows()[0].filename, 'B0.mp3')
  assert.equal(h.component('CurrentTaskSection').status, 'IDLE'); h.unmount()
}
cases.late_error = async () => {
  const h = host(), a = deferred(); h.scan((folder) => folder === 'A' ? a.promise : Promise.resolve(files(folder)))
  await h.settle(); await h.pick('B'); a.reject(new Error('old A offline')); await h.settle()
  assert.equal(h.component('RuntimeBanner').status, 'CONNECTED')
  assert.match(h.component('RuntimeBanner').message, /3개 MP3/); h.unmount()
}
cases.rapid_abc = async () => {
  const h = host(), a = deferred(), b = deferred()
  h.scan((folder) => folder === 'A' ? a.promise : folder === 'B' ? b.promise : Promise.resolve(files(folder)))
  await h.settle(); await h.pick('B'); await h.pick('C')
  b.resolve(files('B')); await h.settle(); a.resolve(files('A')); await h.settle()
  assert.deepEqual(h.rows().map((r) => r.filename), ['C0.mp3'])
  assert.equal(h.scans.find((r) => r.folder === 'B').signal.aborted, true); h.unmount()
}
cases.same_folder_generation = async () => {
  const h = host('A', { ignoreAbort: true }), old = deferred(); h.scan(() => old.promise); await h.settle()
  h.scan(async () => files('A').slice(0, 1)); await h.reconnect()
  old.resolve(files('A')); await h.settle()
  assert.equal(h.rows().length, 1); h.unmount()
}
cases.generation_without_abort = async () => {
  const h = host('A', { ignoreAbort: true }), a = deferred(), b = deferred()
  h.scan((folder) => folder === 'A' ? a.promise : folder === 'B' ? b.promise : Promise.resolve(files(folder)))
  await h.settle(); await h.pick('B'); await h.pick('C')
  assert.equal(h.scans[0].signal.aborted, false)
  b.resolve(files('B')); await h.settle(); a.reject(new Error('late A')); await h.settle()
  assert.deepEqual(h.rows().map((r) => r.filename), ['C0.mp3'])
  assert.equal(h.component('RuntimeBanner').status, 'CONNECTED'); h.unmount()
}
cases.settings_failure = async () => {
  const h = host(); await h.settle(); h.save(async () => { throw new Error('save failed') })
  await h.pick('B'); assert.equal(h.rows().length, 3); assert.equal(h.saved(), 'B')
  await h.reconnect(); assert.equal(h.scans.at(-1).folder, 'B')
  assert.equal(h.component('FolderSection').folderPath, 'B'); h.unmount()
}
cases.settings_pending = async () => {
  const h = host(); await h.settle(); const pending = deferred(); h.save(() => pending.promise)
  await h.pick('B'); assert.equal(h.rows().length, 3)
  await h.pick('C'); pending.resolve({ transcription_folder: 'B' }); await h.settle()
  assert.equal(h.component('FolderSection').folderPath, 'C'); assert.equal(h.rows().length, 1); h.unmount()
}
cases.offline_reconnect = async () => {
  const h = host(); await h.settle(); h.scan(async () => { throw new Error('backend offline') })
  await h.pick('B'); assert.equal(h.rows().length, 0)
  assert.equal(h.component('RuntimeBanner').status, 'OFFLINE')
  assert.equal(h.component('RuntimeBanner').message, 'backend offline')
  assert.equal(h.component('FolderSection').folderPath, 'B')
  h.scan(async (folder) => files(folder)); await h.reconnect()
  assert.equal(h.scans.at(-1).folder, 'B'); assert.equal(h.rows().length, 3)
  assert.equal(h.component('RuntimeBanner').status, 'CONNECTED'); h.unmount()
}
cases.settings_hydration = async () => {
  const h = host(''); h.settings(async () => ({ transcription_folder: 'B', subject_stage_overrides: {} }))
  await h.settle(); assert.equal(h.scans.at(-1).folder, 'B'); assert.equal(h.rows().length, 3); h.unmount()
}
cases.preflight_reset = async () => {
  const h = host(); await h.settle()
  // Accept a picker opened before preflight. The existing preflight picker
  // lock is preserved; #171 modal/obstruction behavior is outside this fix.
  const picker = h.openPicker()
  h.normalize(async (_, names) => [{ result_type: 'MISMATCH', original_name: names[0], suggested_name: 'new.mp3', warnings: [], conflicts: [] }])
  h.component('QueueTable').onToggle('A2'); await h.settle()
  h.component('TranscriptionActions').onStart(); await h.settle()
  assert.equal(h.component('FilenameReview').preview.original_name, 'A2.mp3')
  h.component('FilenameReview').onEdit(); h.component('FilenameReview').onValueChange('edited.mp3'); await h.settle()
  picker.resolve('B'); await h.settle()
  assert.equal(h.component('FilenameReview').preview, undefined)
  assert.equal(h.component('FilenameReview').mode, 'review')
  assert.equal(h.component('FilenameReview').value, '')
  assert.equal(h.component('TranscriptionActions').canStart, true)
  h.component('FilenameReview').onContinueOriginal(); await h.settle()
  assert.equal(h.created.length, 0)
  h.component('QueueTable').onToggle('B1'); await h.settle()
  h.component('TranscriptionActions').onStart(); await h.settle()
  // A fresh attempt invokes normalization again; no old attempt/resolution resumes.
  assert.ok(h.component('FilenameReview').preview); h.unmount()
}
cases.watcher_add_remove = async () => {
  const h = host(); await h.settle()
  const baseScans = h.scans.length; await h.tick(1000)
  assert.equal(h.scans.length, baseScans) // baseline/unchanged never refreshes
  h.component('QueueTable').onToggle('A3'); await h.settle()
  h.scan(async () => [...files('A'), { id: 'added', filename: 'added.mp3', completion_status: 'INCOMPLETE' }])
  h.revision('added'); await h.tick(1000)
  assert.equal(h.rows().length, 5); assert.equal(h.component('QueueTable').selectedIds.length, 1)
  h.scan(async () => files('A').slice(0, 3)); h.revision('removed'); await h.tick(1000)
  assert.equal(h.rows().length, 3); assert.equal(h.component('QueueTable').selectedIds.length, 0); h.unmount()
}
cases.watcher_pause_unpause = async () => {
  const h = host(); await h.settle()
  const pending = deferred(); h.normalize(() => pending.promise)
  h.component('QueueTable').onToggle('A2'); await h.settle()
  h.component('TranscriptionActions').onStart(); await h.settle()
  const before = h.scans.length
  assert.equal(h.hasTimer(1000), false)
  h.revision('changed-while-paused'); h.scan(async (folder) => files(folder))
  pending.reject(new Error('normalization failed')); await h.settle()
  // Unpause on the same folder reconciles once even with a fresh baseline.
  assert.equal(h.scans.length, before + 1)
  await h.tick(1000); assert.equal(h.scans.length, before + 1); h.unmount()
}
cases.unmount_abort = async () => {
  const h = host(), pending = deferred(); h.scan(() => pending.promise); await h.settle()
  h.unmount(); assert.equal(h.scans[0].signal.aborted, true)
  pending.resolve(files('A')); await Promise.resolve()
}
;(async () => {
  const results = {}
  for (const [name, run] of Object.entries(cases)) {
    try { await run(); results[name] = 'PASS' }
    catch (e) { results[name] = e.stack }
  }
  console.log(JSON.stringify(results))
})()
