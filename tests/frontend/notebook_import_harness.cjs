const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const root = path.resolve(__dirname, '../..')
const ts = require(path.join(root, 'frontend/node_modules/typescript'))
const code = ts.transpileModule(fs.readFileSync(path.join(root, 'frontend/src/components/transcription/NotebookImportPanel.tsx'), 'utf8'), {
  compilerOptions: { module: 1, target: 9, jsx: 4 },
}).outputText

function harness() {
  const slots = [], effects = []
  let cursor = 0, tree
  const base = { job_id: 'import-job', status: 'DONE', engine: 'notebook_import', drive: {}, files: { source: 'DONE' } }
  const state = { imports: 0, uploads: 0, refreshes: 0, current: base, failUpload: false }
  const api = {
    notebookImportJob: async () => null,
    importNotebook: async () => { state.imports++; return state.current },
    uploadNotebookResult: async () => { state.uploads++; if (state.failUpload) throw Error('not delivered'); return state.current },
    job: async () => state.current,
  }
  const react = {
    useState(initial) { const i = cursor++; if (!(i in slots)) slots[i] = initial; return [slots[i], next => { slots[i] = next }] },
    useRef(initial) { const i = cursor++; return slots[i] ||= { current: initial } },
    useEffect(fn, deps) { const i = cursor++; const old = slots[i]; if (!old || deps.some((v, j) => v !== old.deps[j])) { old?.cleanup?.(); slots[i] = { deps }; effects.push(() => { slots[i].cleanup = fn() }) } },
  }
  const exports = {}
  const context = {
    exports, AbortController,
    require(name) {
      if (name === 'react') return react
      if (name === 'react/jsx-runtime') return { jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }) }
      if (name.includes('api/client')) return { api, getUserMessage: error => error.message, isRequestAbort: () => false }
      return new Proxy({}, { get: (_target, property) => String(property) })
    },
  }
  vm.runInNewContext(code, context)
  function render() {
    cursor = 0
    tree = exports.NotebookImportPanel({ scanId: 'scan', itemId: 'item', filename: 'source.mp3', onImported: () => state.refreshes++ })
    while (effects.length) effects.shift()()
    return tree
  }
  function nodes(node) {
    if (arguments.length === 0) node = tree
    if (!node || typeof node !== 'object') return []
    const children = [node.props?.children].flat(Infinity)
    return [node, ...children.flatMap(child => nodes(child))]
  }
  function button(text) { return nodes().find(node => node.type === 'Button' && node.props.children === text).props }
  return { state, api, render, button, nodes, base }
}

async function settle(h) { await Promise.resolve(); await Promise.resolve(); h.render() }
async function imported(h) {
  h.render(); await settle(h)
  h.nodes().find(node => node.type === 'input').props.onChange({ target: { files: [{ name: 'result.zip' }] } })
  h.render()
  await h.button('결과 가져오기').onClick()
  await settle(h)
  assert.equal(h.state.imports, 1)
  assert.equal(h.state.refreshes, 1)
}

;(async () => {
  const success = harness()
  await imported(success)
  await success.button('Drive로 전송').onClick(); await settle(success)
  assert.equal(success.state.uploads, 1)
  assert.equal(success.button('Drive로 전송').disabled, true)
  success.state.current = { ...success.base, drive: { source: { status: 'DONE' } } }
  await success.button('전송 상태 확인').onClick(); await settle(success)
  assert.equal(success.button('Drive로 전송').disabled, true)

  const lost = harness()
  await imported(lost)
  lost.state.failUpload = true
  await lost.button('Drive로 전송').onClick(); await settle(lost)
  assert.equal(lost.button('Drive로 전송').disabled, true, 'unknown mutation must first be checked')
  await lost.button('전송 상태 확인').onClick(); await settle(lost)
  assert.equal(lost.button('Drive로 전송').disabled, false, 'confirmed not delivered permits explicit retry')
  assert.equal(lost.state.uploads, 1, 'never retry automatically')
  console.log('NOTEBOOK IMPORT UI: PASS — explicit import/upload, DONE dedupe, lost-request recovery')
})().catch(error => { console.error(error); process.exitCode = 1 })
