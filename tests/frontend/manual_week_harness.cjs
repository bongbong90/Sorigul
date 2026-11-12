// #180: manual week input executed through the production page callbacks
// (same hook host as #170/#171). Synthetic API responses only.
const assert = require('node:assert/strict')
const { host, deferred } = require('./folder_picker_harness.cjs')

const cases = {}
const EDUWILL = ['2026_이영방_부동산학개론_기초이론_2강', '2026_이영방_부동산학개론_기초이론_3강', '2026_이영방_부동산학개론_기초이론_4강']
const base = (name, extra) => ({
  original_name: name, suggested_name: name, result_type: 'UNCHANGED', can_apply: false,
  warnings: [], conflicts: [], detected_course: '정규', detected_subject: '민법',
  detected_week: '1', detected_lesson: '1', manual_week: '1', typed_target_name: null, ...extra,
})
const weekMismatch = (name, manual = '5') => base(name, {
  result_type: 'WEEK_MISMATCH', detected_week: '4', detected_lesson: '3', manual_week: manual,
  typed_target_name: `정규_민법_${manual}주차_3강.mp3`, warnings: [`파일명은 4주차, 입력한 주차는 ${manual}주차입니다.`],
})
const labels = (h) => h.buttons(h.review()).map((n) => h.text(n))
const button = (h, label) => {
  const found = h.buttons(h.review()).find((n) => h.text(n) === label)
  assert.ok(found, `missing button ${label}`)
  assert.ok(!found.props.disabled, `disabled button ${label}`)
  return found.props.onClick
}
const idle = (h) => {
  assert.equal(h.state('preflightActive'), false)
  assert.equal(h.ref('preflightLockRef'), false)
  assert.equal(h.state('attempt'), null)
  assert.equal(h.state('resolvingId'), null)
  assert.equal(h.component('FilenameReview').preview, undefined)
}
async function selected(folder = 'B', ids = ['B1']) {
  const h = host(folder); await h.settle()
  for (const id of ids) h.component('QueueTable').onToggle(id)
  await h.settle()
  return h
}
const start = async (h) => { h.component('TranscriptionActions').onStart(); await h.settle() }

cases.start_requires_week = async () => {
  const h = await selected()
  assert.equal(h.component('ClassificationSection').week, '')
  await start(h)
  idle(h); assert.equal(h.normalized.length, 0); assert.equal(h.dialog(), undefined)
  assert.match(h.component('RuntimeBanner').message, /주차/)
  assert.equal(h.component('ClassificationSection').weekError, '주차를 입력해 주세요.')
  h.unmount()
}
cases.start_all_requires_week_before_confirmation = async () => {
  const h = host('B'); await h.settle(); await start(h)
  assert.equal(h.dialog(), undefined); assert.equal(h.state('pendingIds').length, 0)
  assert.match(h.component('RuntimeBanner').message, /주차/); h.unmount()
}
cases.retranscribe_requires_week_at_execute = async () => {
  const h = host('B'); await h.settle()
  h.component('QueueTable').onRetranscribe('shared'); await h.settle()
  const execute = h.buttons(h.dialog()).find((n) => h.text(n) === '다시 전사 시작').props.onClick
  execute(); await h.settle()
  idle(h); assert.equal(h.dialog(), undefined); assert.equal(h.normalized.length, 0)
  assert.match(h.component('RuntimeBanner').message, /주차/); h.unmount()
}
cases.invalid_week_inputs_are_rejected = async () => {
  for (const value of ['1주차', '1.5', '0', '-1', ' ', 'abc', '1e2', '１']) {
    const h = await selected(); await h.week(value)
    if (value.trim()) assert.ok(h.component('ClassificationSection').weekError, `no inline error for ${value}`)
    await start(h)
    idle(h); assert.equal(h.normalized.length, 0, `normalized with ${value}`)
    assert.ok(h.component('ClassificationSection').weekError); h.unmount()
  }
  const h = await selected(); await h.week(' 12 ')
  assert.equal(h.component('ClassificationSection').weekError, undefined)
  h.normalize(async (_, names) => names.map((name) => base(name)))
  await start(h)
  assert.equal(h.normalized[0][4], 12); assert.equal(h.created[0].week, 12); h.unmount()
}
cases.week_is_sent_snapshotted_and_input_locked = async () => {
  const h = await selected('B', ['B1', 'B2']); await h.week('3')
  h.normalize(async (_, names) => names.map((name) => weekMismatch(name, '3')))
  await start(h)
  assert.equal(h.normalized[0][4], 3)
  assert.equal(h.state('attempt').week, 3)
  assert.equal(h.component('ClassificationSection').disabled, true)
  h.component('ClassificationSection').onWeekChange('9'); await h.settle()
  assert.equal(h.component('ClassificationSection').week, '3') // live edits blocked mid-attempt
  button(h, '원래 이름으로 Local 전사 계속')(); await h.settle()
  assert.equal(h.normalized.length, 2); assert.equal(h.normalized[1][4], 3)
  button(h, '원래 이름으로 Local 전사 계속')(); await h.settle()
  assert.equal(h.created.length, 1); assert.equal(h.created[0].week, 3)
  h.unmount()
}
cases.week_mismatch_review_is_separate_from_classification_mismatch = async () => {
  const h = await selected(); await h.week('5')
  h.normalize(async (_, names) => names.map((name) => weekMismatch(name)))
  await start(h)
  const shown = labels(h)
  assert.deepEqual(shown, ['입력한 주차로 파일명 변경', '주차 입력 수정', '원래 이름으로 Local 전사 계속'])
  assert.ok(!shown.includes('현재 파일의 분류 사용'))
  const text = h.text(h.review())
  assert.match(text, /4주차 3강/); assert.match(text, /5주차/); assert.match(text, /정규_민법_5주차_3강\.mp3/)
  assert.match(text, /파일명은 4주차, 입력한 주차는 5주차입니다/)
  assert.equal(h.renamed.length, 0); assert.equal(h.created.length, 0); h.unmount()
}
cases.rename_to_typed_week_uses_manual_week_target = async () => {
  const h = await selected(); await h.week('5')
  h.normalize(async (_, names) => names.map((name) => name === 'B1.mp3' ? weekMismatch(name) : base(name, { manual_week: '5', detected_week: '5', detected_lesson: '3' })))
  await start(h)
  button(h, '입력한 주차로 파일명 변경')(); await h.settle()
  assert.deepEqual(h.renamed[0].slice(1), ['B1', '정규_민법_5주차_3강'])
  assert.ok(!h.renamed.some((args) => args[2].includes('4주차')))
  assert.equal(h.created.length, 1)
  assert.deepEqual(Array.from(h.created[0].file_ids), ['정규_민법_5주차_3강'])
  assert.equal(h.created[0].week, 5); assert.deepEqual({ ...h.created[0].file_resolutions }, {})
  h.unmount()
}
cases.classification_mismatch_rename_uses_manual_week = async () => {
  const h = await selected(); await h.week('5')
  h.normalize(async (_, names) => names.map((name) => name === 'B1.mp3'
    ? base(name, { result_type: 'MISMATCH', detected_course: '기본', detected_week: '4', detected_lesson: '3', manual_week: '5', typed_target_name: '정규_민법_5주차_3강.mp3' })
    : base(name, { manual_week: '5' })))
  await start(h)
  assert.ok(labels(h).includes('현재 파일의 분류 사용'))
  button(h, '입력한 분류로 파일명 변경')(); await h.settle()
  assert.deepEqual(h.renamed[0].slice(1), ['B1', '정규_민법_5주차_3강'])
  assert.equal(h.created[0].week, 5); h.unmount()
}
cases.rename_without_free_lesson_is_disabled = async () => {
  const h = await selected(); await h.week('5')
  h.normalize(async (_, names) => names.map((name) => ({ ...weekMismatch(name), typed_target_name: null })))
  await start(h)
  const rename = h.buttons(h.review()).find((n) => h.text(n) === '입력한 주차로 파일명 변경')
  assert.equal(rename.props.disabled, true)
  h.component('FilenameReview').onRenameToTyped(); await h.settle()
  assert.equal(h.renamed.length, 0); assert.equal(h.created.length, 0); h.unmount()
}
cases.edit_week_releases_preflight = async () => {
  const h = await selected(); await h.week('5')
  h.normalize(async (_, names) => names.map((name) => weekMismatch(name)))
  await start(h)
  button(h, '주차 입력 수정')(); await h.settle()
  idle(h); assert.equal(h.created.length, 0); assert.equal(h.renamed.length, 0)
  assert.equal(h.component('ClassificationSection').disabled, false)
  assert.equal(h.component('ClassificationSection').week, '5')
  assert.equal(h.component('ClassificationSection').weekError, '파일명은 4주차, 입력한 주차는 5주차입니다. 주차를 확인해 주세요.')
  assert.ok(h.transitions.some(({ name, value }) => name === 'message' && /주차를 수정/.test(value)))
  await h.week('4')
  assert.equal(h.component('ClassificationSection').weekError, undefined)
  h.normalize(async (_, names) => names.map((name) => base(name, { manual_week: '4' })))
  await start(h)
  assert.equal(h.normalized.at(-1)[4], 4); assert.equal(h.created[0].week, 4); h.unmount()
}
cases.continue_original_forces_drive_off = async () => {
  const h = await selected(); await h.week('5')
  const toggle = h.nodes().find((n) => n.type === 'input' && n.props.type === 'checkbox')
  toggle.props.onChange({ target: { checked: true } }); await h.settle()
  h.normalize(async (_, names) => names.map((name) => weekMismatch(name)))
  await start(h)
  button(h, '원래 이름으로 Local 전사 계속')(); await h.settle()
  assert.equal(h.created[0].upload_to_drive, false)
  assert.deepEqual({ ...h.created[0].file_resolutions }, { B1: 'CONTINUE_ORIGINAL' })
  assert.equal(h.renamed.length, 0); h.unmount()
}
cases.eduwill_batch_auto_renames_in_request_order = async () => {
  const h = host('B'); h.scan(async () => EDUWILL.map((id) => ({ id, filename: `${id}.mp3`, completion_status: 'INCOMPLETE', duration_seconds: 10 })))
  await h.settle()
  for (const id of EDUWILL) h.component('QueueTable').onToggle(id)
  await h.week('1')
  h.normalize(async (_, names) => names.map((name, i) => base(name, {
    result_type: 'NORMALIZED', can_apply: true, suggested_name: `기초이론_부동산학개론_1주차_${i + 1}강.mp3`,
    detected_lesson: String(i + 1),
  })))
  await start(h)
  assert.deepEqual(Array.from(h.normalized[0][1]), EDUWILL.map((id) => `${id}.mp3`))
  assert.deepEqual(h.renamed.map((args) => args[2]), [1, 2, 3].map((n) => `기초이론_부동산학개론_1주차_${n}강`))
  assert.deepEqual(Array.from(h.created[0].file_ids), [1, 2, 3].map((n) => `기초이론_부동산학개론_1주차_${n}강`))
  assert.equal(h.created[0].week, 1); h.unmount()
}
cases.folder_switch_clears_week_and_error = async () => {
  const h = await selected('A', ['A2']); await h.week('4')
  await h.pick('B')
  assert.equal(h.component('ClassificationSection').week, '')
  await h.week('x'); assert.ok(h.component('ClassificationSection').weekError)
  await h.pick('C')
  assert.equal(h.component('ClassificationSection').week, '')
  assert.equal(h.component('ClassificationSection').weekError, undefined)
  h.component('QueueTable').onToggle('C1'); await h.settle(); await start(h)
  assert.equal(h.normalized.length, 0); assert.match(h.component('RuntimeBanner').message, /주차/)
  h.unmount()
}
cases.rapid_abc_never_inherits_week = async () => {
  const h = host('A'), a = deferred(), b = deferred()
  h.scan((folder) => folder === 'A' ? a.promise : folder === 'B' ? b.promise : Promise.resolve([{ id: 'C1', filename: 'C1.mp3', completion_status: 'INCOMPLETE' }]))
  await h.settle(); await h.week('4'); await h.pick('B'); await h.week('7'); await h.pick('C')
  b.resolve([]); a.resolve([]); await h.settle()
  assert.equal(h.component('ClassificationSection').week, '')
  assert.equal(h.component('FolderSection').folderPath, 'C'); h.unmount()
}
cases.same_folder_retry_keeps_week = async () => {
  const h = await selected(); await h.week('2')
  h.normalize(async (_, names) => names.map((name) => base(name, { manual_week: '2' })))
  await start(h); assert.equal(h.created.length, 1)
  await h.reconnect()
  assert.equal(h.component('ClassificationSection').week, '2'); h.unmount()
}
cases.late_normalize_after_folder_switch_is_dropped = async () => {
  const h = await selected('A', ['A2']); await h.week('5')
  const picker = h.openPicker(), pending = deferred()
  h.normalize(() => pending.promise)
  await start(h)
  assert.equal(h.state('preflightActive'), true)
  picker.resolve('B'); await h.settle()
  idle(h); assert.equal(h.component('ClassificationSection').week, '')
  pending.resolve([weekMismatch('A2.mp3')]); await h.settle()
  idle(h); assert.equal(h.created.length, 0); assert.equal(h.renamed.length, 0)
  assert.equal(h.component('ClassificationSection').week, ''); h.unmount()
}
cases.week_never_persisted_to_settings = async () => {
  const h = await selected(); await h.week('6')
  h.normalize(async (_, names) => names.map((name) => base(name, { manual_week: '6' })))
  await start(h)
  assert.equal(h.created.length, 1)
  assert.ok(h.settingsWrites.length > 0)
  for (const write of h.settingsWrites) {
    assert.ok(!Object.keys(write).some((key) => /week/i.test(key)), JSON.stringify(write))
  }
  h.unmount()
}
cases.drive_path_preview_shows_manual_week = async () => {
  const h = await selected()
  const toggle = h.nodes().find((n) => n.type === 'input' && n.props.type === 'checkbox')
  toggle.props.onChange({ target: { checked: true } }); await h.settle()
  const preview = () => { const node = h.nodes().find((n) => n.type?.name === 'DrivePathPreview'); return h.text(node.type(node.props)) }
  assert.match(preview(), /주차를 입력하면 주차 폴더가 표시됩니다/)
  await h.week('3')
  assert.match(preview(), /전사자료/); assert.match(preview(), /\[1차\] 민법/); assert.match(preview(), /정규_민법_3주차/)
  await h.week('3주차'); assert.doesNotMatch(preview(), /3주차$/m)
  h.unmount()
}
;(async () => {
  const results = {}
  for (const [name, run] of Object.entries(cases)) {
    try { await run(); results[name] = 'PASS' }
    catch (e) { results[name] = e.stack }
  }
  console.log(JSON.stringify(results))
})()
