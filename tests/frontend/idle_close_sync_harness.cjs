// #195: execute the actual startup hook with delayed settings/native failures.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const root = path.resolve(__dirname, '../..')
const ts = require(path.join(root, 'frontend/node_modules/typescript'))
const code = ts.transpileModule(fs.readFileSync(path.join(root, 'frontend/src/hooks/useCloseBehaviorSync.ts'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText
const settle = async () => { for (let i = 0; i < 20; i++) await Promise.resolve() }
function mount({ settings = async () => ({ close_behavior: 'tray' }), failures = 0 } = {}) {
  const timers = new Map(), calls = []
  let cleanup, serial = 0
  const module = { exports: {} }
  const requireMock = name => {
    if (name === 'react') return { useEffect: fn => { cleanup = fn() } }
    if (name === '@tauri-apps/api/core') return { invoke: async (...args) => { calls.push(args); if (failures-- > 0) throw Error('synthetic native sync failure') } }
    if (name.endsWith('/api/client')) return { api: { settings } }
    if (name.endsWith('/lib/native')) return { isTauri: () => true }
    throw Error(name)
  }
  const context = vm.createContext({ AbortController, window: {
    setTimeout: fn => { const id = ++serial; timers.set(id, fn); return id },
    clearTimeout: id => timers.delete(id),
  } })
  new vm.Script(`(function(require,module,exports){${code}})`).runInContext(context)(requireMock, module, module.exports)
  module.exports.useCloseBehaviorSync()
  return { calls, timers, unmount: () => cleanup(), tick: async () => {
    const [id, fn] = timers.entries().next().value; timers.delete(id); await fn(); await settle()
  } }
}
(async () => {
  let release
  const h = mount({ settings: () => new Promise(r => { release = r }) })
  await settle(); assert.equal(h.calls.length, 0)
  release({ close_behavior: 'tray' }); await settle()
  assert.equal(h.calls[0][0], 'set_close_behavior'); assert.equal(h.calls[0][1].behavior, 'tray')
  assert.equal(h.timers.size, 0); h.unmount()
  const retry = mount({ failures: 1 }); await settle()
  assert.equal(retry.timers.size, 1); await retry.tick()
  assert.equal(retry.calls.length, 2); assert.equal(retry.timers.size, 0); retry.unmount()
  let offline = true
  const backend = mount({ settings: async () => { if (offline) throw Error('offline'); return { close_behavior: 'exit' } } })
  await settle(); assert.equal(backend.calls.length, 0); assert.equal(backend.timers.size, 1)
  offline = false; await backend.tick(); assert.equal(backend.calls[0][1].behavior, 'exit'); backend.unmount()
  const late = mount({ settings: () => new Promise(r => { release = r }) })
  late.unmount(); release({ close_behavior: 'exit' }); await settle(); assert.equal(late.calls.length, 0)
  console.log('4 PASS: saved Tray, native sync retry, Backend retry, late reply after unmount')
})().catch(e => { console.error(e); process.exitCode = 1 })
