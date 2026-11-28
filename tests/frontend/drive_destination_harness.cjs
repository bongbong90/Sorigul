// #246: execute production picker hooks/JSX/callbacks with offline Drive pages.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const root = path.resolve(__dirname, '../..')
const ts = require(path.join(root, 'frontend/node_modules/typescript'))
const source = fs.readFileSync(path.join(root, 'frontend/src/components/DriveFolderPicker.tsx'), 'utf8')
const code = ts.transpileModule(source, { compilerOptions: {
  target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX,
} }).outputText
const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r }); return { promise, resolve } }
const clone = value => JSON.parse(JSON.stringify(value))
const initial = { drive_exam_root: '시험 폴더', drive_parent: null }
const parent = { folder_id: 'alpha', account_id: 'account-A', display_path: '내 드라이브 / 자료 📚' }
function fixture(id = 'root') {
  const folder = (folder_id, name, can_select = true) => ({ folder_id, name, can_select })
  const crumbs = [{ folder_id: 'root', name: '내 드라이브' }]
  if (id !== 'root') crumbs.push({ folder_id: id, name: id === 'alpha' ? '자료 📚' : '한글 Δ 子' })
  return { account_id: 'account-A', folder: folder(id, crumbs.at(-1).name), breadcrumbs: crumbs,
    children: id === 'root' ? [folder('alpha', '자료 📚'), folder('duplicate', '자료 📚'), folder('readonly', '읽기 전용', false)] : [], next_page_token: null }
}
function mount(saved = initial) {
  let settings = clone(saved), stored = clone(saved), disabled = false, dirty = true, cursor = 0, tree
  const slots = [], effects = [], calls = [], writes = []
  let browseImpl = async id => fixture(id), saveFailure = null, resetFailure = null
  const changed = (a, b) => !a || !b || a.length !== b.length || a.some((v, i) => !Object.is(v, b[i]))
  const react = {
    useState(initialValue) {
      const i = cursor++
      if (!slots[i]) slots[i] = { value: initialValue }
      return [slots[i].value, next => { const value = typeof next === 'function' ? next(slots[i].value) : next; if (!Object.is(value, slots[i].value)) { slots[i].value = value; dirty = true } }]
    },
    useRef(value) { return slots[cursor++] ??= { current: value } },
    useEffect(fn, deps) {
      const i = cursor++, old = slots[i]
      if (!old || changed(old.deps, deps)) {
        slots[i] = { deps, cleanup: old?.cleanup }
        effects.push(() => { old?.cleanup?.(); slots[i].cleanup = fn() })
      }
    },
  }
  const api = {
    driveFolders: (...args) => { calls.push(args); return browseImpl(...args) },
    selectDriveDestination: async (folderId, accountId) => {
      writes.push(['select', folderId, accountId])
      if (saveFailure) throw new Error(saveFailure)
      stored = { ...stored, drive_parent: { layout: 'transcript_root', folder_id: folderId, account_id: accountId, display_path: fixture(folderId).breadcrumbs.map(x => x.name).join(' / ') } }
      return clone(stored)
    },
    resetDriveDestination: async () => {
      writes.push(['reset'])
      if (resetFailure) throw new Error(resetFailure)
      stored = { ...stored, drive_parent: null }; return clone(stored)
    },
    settings: async () => clone(stored),
  }
  function Button() {}
  const jsx = (type, props) => ({ type, props: props || {} })
  const requireMock = name => {
    if (name === 'react') return react
    if (name === 'react/jsx-runtime') return { jsx, jsxs: jsx }
    if (name === './ui/Button') return { Button }
    if (name === '../api/client') return { api, getUserMessage: e => e.message, isRequestAbort: e => e.name === 'AbortError' }
    throw Error(name)
  }
  const module = { exports: {} }
  const context = vm.createContext({ AbortController })
  new vm.Script(`(function(require,module,exports){${code}})`).runInContext(context)(requireMock, module, module.exports)
  function render() {
    dirty = false; cursor = 0
    tree = module.exports.DriveFolderPicker({ settings, disabled, onSaved: next => { settings = next; dirty = true } })
    while (effects.length) effects.shift()()
  }
  const nodes = node => Array.isArray(node) ? node.flatMap(nodes) : node && typeof node === 'object' ? [node, ...nodes(node.props?.children)] : []
  const text = node => Array.isArray(node) ? node.map(text).join('') : node && typeof node === 'object' ? text(node.props?.children) : node == null || typeof node === 'boolean' ? '' : String(node)
  async function settle() { for (let i = 0; i < 80; i++) { await Promise.resolve(); if (dirty) render() } }
  const button = label => nodes(tree).find(n => (n.type === 'button' || n.type === Button) && (text(n) === label || n.props['aria-label'] === label))
  render()
  return {
    calls, writes, settle, text: () => text(tree), settings: () => settings,
    button, click: async label => { const node = button(label); assert.ok(node, `missing ${label}`); assert.ok(!node.props.disabled, `${label} disabled`); node.props.onClick(); await settle() },
    browse: fn => { browseImpl = fn }, failSave: message => { saveFailure = message }, failReset: message => { resetFailure = message },
    setDisabled: async value => { disabled = value; dirty = true; await settle() },
    unmount: () => slots.forEach(slot => slot?.cleanup?.()),
  }
}
const results = {}
async function scenario(name, run) { await run(); results[name] = 'PASS' }
async function choose(h, id = 'alpha') {
  await h.click('저장 위치 선택')
  await h.click(`자료 📚 폴더 열기 (${id})`)
  await h.click('이 폴더 선택')
}
(async () => {
  await scenario('default_and_hierarchy', async () => {
    const h = mount(); await h.settle()
    assert.match(h.text(), /내 드라이브 \(기본 위치\)/); assert.match(h.text(), /시험 폴더.*전사자료/)
    assert.equal(h.button('기본 위치로 되돌리기').props.disabled, true)
    assert.equal(h.calls.length, 0); h.unmount()
  })
  await scenario('unicode_duplicates_and_exact_id', async () => {
    const h = mount(); await choose(h, 'duplicate')
    assert.match(h.text(), /이 폴더를 상위 저장 위치/); assert.match(h.text(), /폴더 ID: duplicate/)
    assert.match(h.text(), /업로드 경로: 내 드라이브 \/ 한글 Δ 子 \/ 과정 \/ \[단계\] 과목/)
    assert.equal(h.writes.length, 0)
    await h.click('확인 후 저장')
    assert.deepEqual(h.writes, [['select', 'duplicate', 'account-A']])
    assert.equal(h.settings().drive_parent.folder_id, 'duplicate'); h.unmount()
  })
  await scenario('breadcrumb_parent_navigation', async () => {
    const h = mount(); await choose(h)
    assert.equal(h.calls.at(-1)[1], 'account-A')
    await h.click('내 드라이브'); assert.equal(h.calls.at(-1)[0], 'root')
    assert.equal(h.button('확인 후 저장'), undefined); h.unmount()
  })
  await scenario('cancel_preserves_settings', async () => {
    const h = mount({ ...initial, drive_parent: parent }); await choose(h)
    await h.click('취소'); assert.equal(h.writes.length, 0)
    assert.deepEqual(h.settings().drive_parent, parent); h.unmount()
  })
  await scenario('restore_default', async () => {
    const h = mount({ ...initial, drive_parent: parent }); await h.settle()
    await h.click('기본 위치로 되돌리기'); assert.equal(h.settings().drive_parent, null)
    assert.deepEqual(h.writes, [['reset']]); h.unmount()
  })
  for (const message of ['접근 권한이 없습니다.', 'Google Drive 계정이 다릅니다.', '연결이 끊겼습니다.']) {
    await scenario(`browse_error_${message}`, async () => {
      const h = mount(); h.browse(async () => { throw Error(message) })
      await h.click('저장 위치 선택'); assert.ok(h.text().includes(message))
      assert.equal(h.button('이 폴더 선택'), undefined); assert.equal(h.writes.length, 0); h.unmount()
    })
  }
  await scenario('readonly_folder_cannot_confirm', async () => {
    const h = mount(); h.browse(async () => { const page = fixture(); page.folder.can_select = false; return page })
    await h.click('저장 위치 선택'); assert.equal(h.button('이 폴더 선택').props.disabled, true)
    assert.match(h.text(), /저장할 권한/); h.unmount()
  })
  await scenario('save_failure_retains_authoritative_settings', async () => {
    const h = mount(); h.failSave('저장 실패'); await choose(h); await h.click('확인 후 저장')
    assert.equal(h.settings().drive_parent, null); assert.match(h.text(), /저장 실패/); h.unmount()
  })
  await scenario('reset_failure_retains_authoritative_settings', async () => {
    const h = mount({ ...initial, drive_parent: parent }); h.failReset('기본값 저장 실패')
    await h.click('기본 위치로 되돌리기'); assert.deepEqual(h.settings().drive_parent, parent)
    assert.match(h.text(), /기본값 저장 실패/); h.unmount()
  })
  await scenario('cancel_discards_late_response', async () => {
    const h = mount(), late = deferred(); h.browse(() => late.promise)
    await h.click('저장 위치 선택'); await h.click('취소')
    late.resolve(fixture()); await h.settle()
    assert.equal(h.button('이 폴더 선택'), undefined); assert.equal(h.writes.length, 0); h.unmount()
  })
  await scenario('disconnect_invalidates_selection', async () => {
    const h = mount(); await choose(h); await h.setDisabled(true)
    assert.equal(h.button('확인 후 저장'), undefined)
    assert.match(h.text(), /연결이 끊겼습니다/); assert.equal(h.writes.length, 0); h.unmount()
  })
  await scenario('pagination_preserves_existing_children', async () => {
    const h = mount(); h.browse(async (id, account, token) => {
      const page = fixture(id)
      if (token) page.children = [{ folder_id: 'extra', name: '추가 폴더', can_select: true }]
      else page.next_page_token = 'page-2'
      return page
    })
    await h.click('저장 위치 선택'); await h.click('폴더 더 보기')
    assert.equal(h.calls.at(-1)[2], 'page-2')
    assert.ok(h.button('자료 📚 폴더 열기 (alpha)')); assert.ok(h.button('추가 폴더 폴더 열기 (extra)')); h.unmount()
  })
  await scenario('api_transport_uses_exact_ids_and_dedicated_mutation', async () => {
    const clientSource = fs.readFileSync(path.join(root, 'frontend/src/api/client.ts'), 'utf8').replaceAll('import.meta.env', 'globalThis.__env')
    const js = ts.transpileModule(clientSource, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } }).outputText
    const calls = [], module = { exports: {} }
    let fail = false
    const context = vm.createContext({ __env: {}, AbortController, URLSearchParams, window: { setTimeout, clearTimeout },
      fetch: async (url, options) => { calls.push({ url, options }); return { ok: !fail, status: fail ? 409 : 200, json: async () => fail ? { detail: '저장 위치 접근 권한을 확인해 주세요.' } : initial } },
    })
    new vm.Script(`(function(module,exports){${js}})`).runInContext(context)(module, module.exports)
    const { api } = module.exports
    await api.driveFolders('folder-α', 'account-A', 'page+2')
    const url = new URL(calls.at(-1).url)
    assert.equal(url.searchParams.get('folder_id'), 'folder-α')
    assert.equal(url.searchParams.get('account_id'), 'account-A')
    assert.equal(url.searchParams.get('page_token'), 'page+2')
    await api.selectDriveDestination('alpha', 'account-A')
    assert.equal(calls.at(-1).options.method, 'PUT')
    assert.deepEqual(JSON.parse(calls.at(-1).options.body), { folder_id: 'alpha', account_id: 'account-A' })
    await api.saveSettings({ ...initial, drive_parent: parent })
    assert.equal('drive_parent' in JSON.parse(calls.at(-1).options.body), false)
    await api.resetDriveDestination(); assert.equal(calls.at(-1).options.method, 'DELETE')
    fail = true
    await assert.rejects(api.selectDriveDestination('alpha', 'account-A'), /접근 권한/)
  })
  console.log(JSON.stringify(results))
})().catch(error => { console.error(error); process.exitCode = 1 })
