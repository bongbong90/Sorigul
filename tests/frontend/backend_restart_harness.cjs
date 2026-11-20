// Execute the production component with controlled native replies and React hooks.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const root = path.resolve(__dirname, '../..')
const code = process.env.SORIGUL_RESTART_COMPONENT_JS
  ? fs.readFileSync(process.env.SORIGUL_RESTART_COMPONENT_JS, 'utf8')
  : require(path.join(root, 'frontend/node_modules/typescript')).transpileModule(
    fs.readFileSync(path.join(root, 'frontend/src/components/transcription/BackendRestart.tsx'), 'utf8'),
    { compilerOptions: { module: 1, target: 9, jsx: 4 } }).outputText
const ready = { backend_exited: true, can_restart: true, message: null, code: null }
function host() {
  const slots = [], effects = [], timers = new Map()
  let index = 0, dirty = false, serial = 0, tree, offline = true
  const h = { status: ready, calls: 0, synced: 0, restart: async () => {}, sync: async () => {} }
  const react = {
    useState(initial) { const i = index++; if (!(i in slots)) slots[i] = initial; return [slots[i], value => { slots[i] = value; dirty = true }] },
    useRef(initial) { const i = index++; return slots[i] ||= { current: initial } },
    useEffect(fn, deps) { const i = index++; const previous = slots[i]; if (!previous || deps.some((v, j) => v !== previous.deps[j])) { previous?.cleanup?.(); slots[i] = { deps }; effects.push(() => { slots[i].cleanup = fn() }) } },
  }
  const jsx = (type, props) => ({ type, props })
  const module = { exports: {} }
  const requireMock = name => {
    if (name === 'react') return react
    if (name === 'react/jsx-runtime') return { jsx, jsxs: jsx }
    if (name.endsWith('/lib/native')) return { getBackendRecoveryStatus: async () => h.status, restartBackend: async () => { h.calls++; await h.restart() } }
    if (name.endsWith('/ui/Button')) return { Button: 'button' }
    throw Error(name)
  }
  const context = vm.createContext({ window: { setTimeout(fn) { const id = ++serial; timers.set(id, fn); return id }, clearTimeout: id => timers.delete(id) } })
  new vm.Script(`(function(require,module,exports){${code}})`).runInContext(context)(requireMock, module, module.exports)
  function render() { index = 0; dirty = false; tree = module.exports.BackendRestart({ offline, onRecovered: async () => { h.synced++; await h.sync() } }); for (const effect of effects.splice(0)) effect() }
  function nodes(value, type) { if (!value || typeof value !== 'object') return []; if (Array.isArray(value)) return value.flatMap(v => nodes(v, type)); return [...(value.type === type ? [value] : []), ...nodes(value.props?.children, type)] }
  async function flush() { for (let i = 0; i < 30; i++) { await Promise.resolve(); if (dirty) render() } }
  Object.assign(h, { flush, button: () => nodes(tree, 'button')[0], alerts: () => nodes(tree, 'p').map(n => n.props.children).join(' '), render: value => { offline = value; render() }, tick: async () => { const entries = [...timers]; timers.clear(); for (const [, fn] of entries) fn(); await flush() } })
  render(); return h
}
;(async () => {
  const passive = host(); await passive.flush(); await passive.tick()
  assert.equal(passive.calls, 0, 'polls must never restart automatically')
  passive.status = { ...ready, backend_exited: false, can_restart: false }; await passive.tick()
  assert.equal(passive.button(), undefined, 'live/unconfirmed backend has no restart action')
  passive.status = { ...ready, can_restart: false, message: 'Worker active' }; await passive.tick()
  assert.equal(passive.button().props.disabled, true)
  assert.match(passive.alerts(), /Worker active/)

  const manual = host(); await manual.flush()
  let release; manual.restart = () => new Promise(r => { release = r })
  const click = manual.button().props.onClick
  click(); click(); await manual.flush()
  assert.equal(manual.calls, 1, 'rapid duplicate user request is suppressed')
  await manual.tick(); manual.render(false); manual.render(true); await manual.flush()
  assert.equal(manual.button().props.disabled, true, 'pending operation survives connectivity render changes')
  release(); await manual.flush(); assert.equal(manual.synced, 1)

  const failed = host(); await failed.flush()
  failed.restart = async () => { throw 'STARTUP_TIMEOUT' }
  failed.button().props.onClick(); await failed.flush(); await failed.tick()
  assert.match(failed.alerts(), /STARTUP_TIMEOUT/)
  assert.equal(failed.synced, 0)
  failed.render(false); await failed.flush(); assert.match(failed.alerts(), /STARTUP_TIMEOUT/)

  const sync = host(); await sync.flush(); sync.sync = async () => { throw 'JOBS_SYNC_FAILED' }
  sync.button().props.onClick(); await sync.flush(); assert.match(sync.alerts(), /JOBS_SYNC_FAILED/)
  console.log('PASS: no automatic restart; confirmed-exit action; active guard; explicit/deduplicated restart; stable pending/error state; sync failure surfaced')
})().catch(error => { console.error(error); process.exitCode = 1 })
