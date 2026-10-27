// #173: executes the production useTrayProgress hook with a fake React effect
// host, fake timers, and a scripted backend. "Route changes" re-render the
// App-level host: an effect with stable deps must not clean up or re-run.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const root = path.resolve(__dirname, '../..')
const ts = require(path.join(root, 'frontend/node_modules/typescript'))
const hookPath = path.join(root, 'frontend/src/hooks/useTrayProgress.ts')
const POLL = 1500

function mount() {
  const timers = new Map()
  let timerId = 0, now = 0
  const sent = [], aborts = []
  const state = { active: null, jobs: {}, activeFails: false, jobFails: false, jobCalls: [], activeCalls: 0, trayFails: false }
  let cleanup, effectRuns = 0, cleanups = 0
  const react = { useEffect(fn) { if (effectRuns === 0) { effectRuns++; cleanup = fn() } } }
  const abortable = (signal, value, fail) => new Promise((resolve, reject) => {
    signal.addEventListener('abort', () => { aborts.push(1); reject(new Error('aborted')) })
    Promise.resolve().then(() => (fail() ? reject(new Error('offline')) : resolve(value())))
  })
  const api = {
    activeJob: (signal) => { state.activeCalls++; return abortable(signal, () => state.active, () => state.activeFails) },
    job: (id, signal) => { state.jobCalls.push(id); return abortable(signal, () => state.jobs[id], () => state.jobFails) },
  }
  const native = { setTrayProgress: (p) => { sent.push(p); return state.trayFails ? Promise.reject(new Error('tray')) : Promise.resolve() } }
  const code = ts.transpileModule(fs.readFileSync(hookPath, 'utf8'), { compilerOptions: {
    target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } }).outputText
  const module = { exports: {} }
  const sandbox = {
    module, exports: module.exports, AbortController, console, Promise,
    require: (n) => (n === 'react' ? react : n.endsWith('/api/client') ? { api } : n.endsWith('/lib/native') ? native : {}),
    setTimeout: (fn, ms) => { const id = ++timerId; timers.set(id, { fn, at: now + ms }); return id },
    clearTimeout: (id) => timers.delete(id),
  }
  vm.runInNewContext(code, sandbox)
  module.exports.useTrayProgress()
  const flush = async () => { for (let i = 0; i < 20; i++) await Promise.resolve() }
  return {
    state, sent, aborts, timers,
    async advance() {
      await flush()
      now += POLL
      for (const [id, t] of [...timers]) if (t.at <= now) { timers.delete(id); t.fn() }
      await flush()
    },
    settle: flush,
    // App re-render on navigation: a stable-deps effect is not re-run.
    reroute() { react.useEffect(() => {}, []) },
    unmount() { cleanups++; cleanup() },
    get cleanups() { return cleanups },
    get effectRuns() { return effectRuns },
  }
}
const J = (id, status, extra = {}) => ({ job_id: id, status, current_file: null, current_progress: null, ...extra })
const last = (h) => JSON.parse(JSON.stringify(h.sent[h.sent.length - 1]))
const scenarios = {
  async cold_idle() {
    const h = mount(); await h.settle()
    assert.deepEqual(last(h), { status: 'IDLE', currentFile: null, currentProgress: null })
    h.state.jobs.old = J('old', 'DONE'); await h.advance()
    assert.equal(h.state.jobCalls.length, 0, 'historical job never looked up'); h.unmount()
  },
  async active_and_progress() {
    const h = mount(); h.state.active = J('a', 'TRANSCRIBING', { current_file: 'x.mp3', current_progress: 10 })
    await h.settle(); await h.advance()
    assert.deepEqual(last(h), { status: 'TRANSCRIBING', currentFile: 'x.mp3', currentProgress: 10 })
    h.state.active = J('a', 'TRANSCRIBING', { current_file: 'y.mp3', current_progress: 55 }); await h.advance()
    assert.deepEqual(last(h), { status: 'TRANSCRIBING', currentFile: 'y.mp3', currentProgress: 55 }); h.unmount()
  },
  async route_survives() {
    const h = mount(); h.state.active = J('a', 'TRANSCRIBING', { current_file: 'x.mp3', current_progress: 1 })
    await h.advance()
    for (const _route of ['settings', 'folders', 'log', 'transcription']) { h.reroute(); await h.advance() }
    assert.equal(h.cleanups, 0); assert.equal(h.effectRuns, 1)
    assert.equal(h.timers.size, 1, 'poll still scheduled')
    h.state.active = J('a', 'TRANSCRIBING', { current_progress: 80 }); await h.advance()
    assert.equal(last(h).currentProgress, 80); h.unmount()
  },
  async terminal(status) {
    const h = mount(); h.state.active = J('a', 'TRANSCRIBING', { current_file: 'x.mp3', current_progress: 50 })
    await h.advance(); h.reroute()
    h.state.active = null; h.state.jobs.a = J('a', status, { current_file: 'x.mp3', current_progress: status === 'DONE' ? 100 : 50 })
    await h.advance(); await h.advance(); await h.advance()
    assert.equal(last(h).status, status); assert.deepEqual(h.state.jobCalls, ['a'], 'lookup once')
    h.unmount()
  },
  async lookup_failure_keeps_state() {
    const h = mount(); h.state.active = J('a', 'TRANSCRIBING', { current_progress: 50 }); await h.advance()
    const before = h.sent.length
    h.state.active = null; h.state.jobFails = true; await h.advance(); await h.advance()
    assert.equal(h.sent.length, before, 'nothing inferred'); assert.ok(h.state.jobCalls.length >= 1)
    h.state.jobFails = false; h.state.jobs.a = J('a', 'DONE'); await h.advance()
    assert.equal(last(h).status, 'DONE'); h.unmount()
  },
  async non_terminal_lookup_retries() {
    const h = mount(); h.state.active = J('a', 'SAVING'); await h.advance()
    h.state.active = null; h.state.jobs.a = J('a', 'SAVING'); await h.advance()
    assert.equal(last(h).status, 'SAVING')
    h.state.jobs.a = J('a', 'DONE'); await h.advance(); assert.equal(last(h).status, 'DONE'); h.unmount()
  },
  async outage_no_fake_idle() {
    const h = mount(); h.state.active = J('a', 'TRANSCRIBING', { current_progress: 30 }); await h.advance()
    const before = h.sent.length; h.state.activeFails = true
    await h.advance(); await h.advance(); await h.advance()
    assert.equal(h.sent.length, before); h.state.activeFails = false
    h.state.active = J('a', 'TRANSCRIBING', { current_progress: 40 }); await h.advance()
    assert.equal(last(h).currentProgress, 40); h.unmount()
  },
  async startup_unavailable() {
    const h = mount(); h.state.activeFails = true
    await h.advance(); await h.advance()
    assert.equal(h.sent.length, 0, 'no FAILED before backend answers'); h.state.activeFails = false
    await h.advance(); assert.equal(last(h).status, 'IDLE'); h.unmount()
  },
  async new_job_after_terminal() {
    const h = mount(); h.state.active = J('a', 'TRANSCRIBING'); await h.advance()
    h.state.active = null; h.state.jobs.a = J('a', 'DONE'); await h.advance(); await h.advance()
    assert.equal(last(h).status, 'DONE')
    h.state.active = J('b', 'PREPARING'); await h.advance(); assert.equal(last(h).status, 'PREPARING')
    h.state.active = null; h.state.jobs.b = J('b', 'FAILED'); await h.advance(); await h.advance()
    assert.equal(last(h).status, 'FAILED'); assert.deepEqual(h.state.jobCalls, ['a', 'b']); h.unmount()
  },
  async tray_failure_best_effort() {
    const h = mount(); h.state.trayFails = true; h.state.active = J('a', 'TRANSCRIBING', { current_progress: 5 })
    await h.advance(); h.state.active = J('a', 'TRANSCRIBING', { current_progress: 6 }); await h.advance()
    assert.equal(last(h).currentProgress, 6, 'polling continues despite tray failure'); h.unmount()
  },
  async unmount_cleanup() {
    const h = mount(); h.state.active = J('a', 'TRANSCRIBING'); await h.advance()
    // Fire the next tick so a request is in flight, then unmount before it settles.
    for (const [id, t] of [...h.timers]) { h.timers.delete(id); t.fn() }
    h.unmount(); await h.settle()
    assert.equal(h.timers.size, 0, 'timer cleared'); assert.ok(h.aborts.length >= 1, 'in-flight aborted')
    const calls = h.state.activeCalls; await h.advance(); await h.advance()
    assert.equal(h.state.activeCalls, calls, 'no polling after unmount')
  },
}
async function main() {
  const results = {}
  const run = async (name, fn, ...args) => {
    try { await fn(...args); results[name] = 'PASS' } catch (e) { results[name] = String((e && e.stack) || e) }
  }
  for (const [name, fn] of Object.entries(scenarios)) if (name !== 'terminal') await run(name, fn)
  for (const s of ['DONE', 'FAILED', 'STOPPED', 'CANCELLED', 'CRASHED']) await run(`terminal_${s}`, scenarios.terminal, s)
  console.log(JSON.stringify(results))
}
main()
