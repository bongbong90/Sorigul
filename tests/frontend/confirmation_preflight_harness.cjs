// #171: execute production page callbacks with batched hook state. The
// companion browser fixture covers real React commits and DOM hit-testing.
const assert = require('node:assert/strict')
const { host, deferred, job } = require('./folder_picker_harness.cjs')

const cases = {}
const preview = (name, type = 'INVALID_TARGET') => ({
  original_name: name, suggested_name: name, result_type: type,
  can_apply: false, warnings: [], conflicts: type === 'CONFLICT' ? ['occupied'] : [],
  detected_course: '기초', detected_subject: '민법', detected_week: 1, detected_lesson: 1,
})
const idle = (h) => {
  assert.equal(h.state('dialog'), null)
  assert.equal(h.state('pendingIds').length, 0)
  assert.equal(h.state('preflightActive'), false)
  assert.equal(h.ref('preflightLockRef'), false)
  assert.equal(h.state('normalization'), undefined)
  assert.equal(h.state('resolvingId'), null)
  assert.equal(h.state('attempt'), null)
  assert.equal(h.created.length, 0)
  assert.equal(h.started.length, 0)
}
const invariant = (h) => {
  assert.ok(!(h.state('dialog') !== null && h.state('preflightActive')), 'confirmation overlaps active preflight')
  assert.ok(!(h.dialog() && h.component('FilenameReview').preview), 'confirmation blocks filename review')
}
const button = (h, node, label) => {
  const found = h.buttons(node).find((n) => h.text(n) === label)
  assert.ok(found, `missing button ${label}`)
  assert.ok(!found.props.disabled)
  return found.props.onClick
}
const execute = (h, kind) => button(h, h.dialog(), kind === 'start-all' ? '실행' : '다시 전사 시작')
async function open(kind) {
  const h = host('B'); await h.settle(); await h.week('1')
  if (kind === 'start-all') h.component('TranscriptionActions').onStart()
  else h.component('QueueTable').onRetranscribe('shared')
  await h.settle()
  assert.equal(h.state('dialog'), kind)
  assert.equal(h.state('preflightActive'), false)
  assert.equal(h.ref('preflightLockRef'), false)
  assert.equal(h.normalized.length, 0)
  invariant(h)
  if (kind === 'start-all') {
    assert.match(h.text(h.dialog()), /전체 3개 중 완료 1개를 제외한 2개/)
    assert.deepEqual(Array.from(h.state('pendingIds')), ['B1', 'B2'])
  } else {
    assert.match(h.text(h.dialog()), /기존 정상 결과를 보존합니다.*새 결과 검증 성공 후에만 교체합니다/s)
    assert.deepEqual(Array.from(h.state('pendingIds')), ['shared'])
  }
  return h
}
for (const kind of ['start-all', 'retranscribe']) {
  cases[`${kind}_confirmation`] = async () => { const h = await open(kind); h.unmount() }
  cases[`${kind}_cancel`] = async () => {
    const h = await open(kind)
    button(h, h.dialog(), '취소')(); await h.settle()
    idle(h); assert.equal(h.normalized.length, 0)
    // Confirmation Cancel must not be widened to reset active preflight.
    assert.ok(!h.transitions.some(({ name }) => ['preflightActive', 'normalization', 'attempt', 'resolvingId', 'fileResolutions'].includes(name)))
    h.component('FilenameReview').onContinueOriginal(); await h.settle(); idle(h)
    h.unmount()
  }
  cases[`${kind}_execute_consumes_before_normalize`] = async () => {
    const h = await open(kind), pending = deferred(), original = h.state('pendingIds')
    h.normalize(() => {
      assert.equal(h.state('dialog'), null)
      assert.equal(h.state('pendingIds').length, 0)
      assert.equal(h.ref('preflightLockRef'), true)
      return pending.promise
    })
    execute(h, kind)()
    assert.equal(h.state('dialog'), null); assert.equal(h.state('pendingIds').length, 0)
    original.push('stale') // seed must be an independent snapshot
    await h.settle(); invariant(h); assert.equal(h.dialog(), undefined)
    assert.ok(!h.nodes().some((n) => n.props.className === 'dialog-backdrop' || n.props['aria-modal']))
    pending.resolve(h.normalized[0][1].map((name) => preview(name)))
    await h.settle(); invariant(h)
    assert.ok(!h.state('attempt').ids.includes('stale'))
    h.unmount()
  }
  for (const type of ['INVALID_TARGET', 'CONFLICT', 'MISMATCH']) {
    cases[`${kind}_${type}_review_and_job`] = async () => {
      const h = await open(kind)
      h.normalize(async (_, names) => names.map((name) => preview(name, type)))
      execute(h, kind)(); await h.settle(); invariant(h)
      assert.equal(h.state('pendingIds').length, 0)
      const targets = kind === 'start-all' ? ['B1', 'B2'] : ['shared']
      assert.equal(h.created.length, 0)
      for (const id of targets) {
        assert.equal(h.state('resolvingId'), id)
        button(h, h.review(), type === 'MISMATCH' ? '원래 이름으로 Local 전사 계속' : '원래 이름으로 계속')()
        await h.settle(); invariant(h)
      }
      assert.equal(h.created.length, 1); assert.equal(h.started.length, 1)
      assert.deepEqual(Array.from(h.created[0].file_ids), targets)
      assert.equal(h.created[0].force_retranscribe, kind === 'retranscribe')
      assert.equal(h.created[0].scope, 'selected') // existing finalized snapshot contract
      assert.equal(h.ref('preflightLockRef'), false)
      assert.equal(h.state('preflightActive'), false)
      assert.equal(h.component('FilenameReview').preview, undefined)
      h.unmount()
    }
  }
  cases[`${kind}_no_issue_job`] = async () => {
    const h = await open(kind)
    h.normalize(async (_, names) => names.map((name) => preview(name, 'UNCHANGED')))
    execute(h, kind)(); await h.settle(); invariant(h)
    assert.equal(h.created.length, 1); assert.equal(h.started.length, 1)
    assert.equal(h.created[0].file_ids.length, kind === 'start-all' ? 2 : 1)
    assert.equal(h.created[0].force_retranscribe, kind === 'retranscribe')
    assert.equal(h.state('pendingIds').length, 0)
    h.unmount()
  }
  for (const reason of ['global_run', 'colab', 'classification']) {
    cases[`${kind}_early_rejection_${reason}`] = async () => {
      const h = await open(kind)
      if (reason === 'global_run') { h.active(job('C', 'TRANSCRIBING')); await h.reconnect() }
      if (reason === 'colab') { h.component('EngineSection').onChangeEngine('direct_colab'); await h.settle() }
      if (reason === 'classification') { h.component('ClassificationSection').onCourseChange(''); await h.settle() }
      execute(h, kind)(); await h.settle(); idle(h); invariant(h)
      assert.match(h.component('RuntimeBanner').message, reason === 'global_run' ? /다른 전사 작업/ : reason === 'colab' ? /Colab 연결/ : /과정명\/과목명/)
      assert.equal(h.normalized.length, 0)
      h.unmount()
    }
  }
  cases[`${kind}_double_execute`] = async () => {
    const h = await open(kind), pending = deferred()
    h.normalize(() => pending.promise)
    const confirm = execute(h, kind)
    confirm(); confirm(); await h.settle(); invariant(h)
    assert.equal(h.normalized.length, 1)
    pending.resolve(h.normalized[0][1].map((name) => preview(name, 'UNCHANGED')))
    await h.settle(); invariant(h)
    assert.equal(h.created.length, 1); assert.equal(h.started.length, 1)
    h.unmount()
  }
  cases[`${kind}_folder_switch`] = async () => {
    const h = await open(kind)
    await h.pick('C'); idle(h); invariant(h)
    // #180: folder C never inherits folder B's week.
    assert.equal(h.component('ClassificationSection').week, '')
    h.component('TranscriptionActions').onStart(); await h.settle()
    assert.equal(h.dialog(), undefined); assert.match(h.component('RuntimeBanner').message, /주차/)
    await h.week('1')
    h.component('TranscriptionActions').onStart(); await h.settle()
    assert.match(h.text(h.dialog()), /전체 1개 중 완료 0개를 제외한 1개/)
    assert.deepEqual(Array.from(h.state('pendingIds')), ['shared'])
    h.unmount()
  }
}
cases.edit_apply_remaps_target = async () => {
  const h = await open('start-all')
  h.normalize(async (_, names) => names.map((name) => preview(name)))
  h.rename(async (_, oldStem, newStem) => ({ old_file_id: oldStem, new_file_id: newStem }))
  execute(h, 'start-all')(); await h.settle(); invariant(h)
  button(h, h.review(), '이름 수정')(); await h.settle()
  h.component('FilenameReview').onValueChange('edited.mp3'); await h.settle()
  button(h, h.review(), '이름 적용')(); await h.settle(); invariant(h)
  assert.equal(h.renamed.length, 1)
  assert.equal(h.state('resolvingId'), 'B2')
  button(h, h.review(), '원래 이름으로 계속')(); await h.settle()
  assert.deepEqual(Array.from(h.created[0].file_ids), ['edited', 'B2'])
  assert.equal(h.started.length, 1); h.unmount()
}
cases.use_file_classification = async () => {
  const h = await open('retranscribe')
  h.normalize(async (_, names) => names.map((name) => preview(name, 'MISMATCH')))
  execute(h, 'retranscribe')(); await h.settle(); invariant(h)
  button(h, h.review(), '현재 파일의 분류 사용')(); await h.settle(); invariant(h)
  assert.equal(h.normalized.at(-1)[4], 1) // resumed attempt keeps its week snapshot
  assert.equal(h.created.length, 1); assert.equal(h.created[0].course, '기초')
  assert.equal(h.created[0].force_retranscribe, true); assert.equal(h.started.length, 1)
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
