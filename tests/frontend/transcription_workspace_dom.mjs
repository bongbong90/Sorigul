// Manual source DOM gate: node tests/frontend/transcription_workspace_dom.mjs
import fs from 'node:fs'
import path from 'node:path'
import { spawn } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import assert from 'node:assert/strict'
import net from 'node:net'
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..')
const out = path.join(root, 'tmp/stabilization-20261015')
fs.mkdirSync(out, { recursive: true })
const profile = fs.mkdtempSync(path.join(root, 'tmp/workspace-browser-'))
const baseline = process.argv.includes('--baseline')
const webview2 = process.argv.includes('--webview2')
const chromium = ['C:/Program Files/Google/Chrome/Application/chrome.exe', 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'].find(fs.existsSync)
assert.ok(chromium, 'Local Chromium required')
const server = spawn(process.execPath, [path.join(root, 'tests/frontend/transcription_workspace_browser.mjs')], { cwd: root, windowsHide: true, env:{...process.env,SORIGUL_QA_BASELINE:baseline?'1':'0'} })
let proc, ws, serial = 0
const pending = new Map(), errors = [], results = {}
const pause = ms => new Promise(r => setTimeout(r, ms))
function call(method, params = {}) {
  const id = ++serial
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => { pending.delete(id); reject(Error(`CDP timeout: ${method}`)) }, 15000)
    pending.set(id, { resolve: v => { clearTimeout(timer); resolve(v) }, reject: e => { clearTimeout(timer); reject(e) } })
    ws.send(JSON.stringify({ id, method, params }))
  })
}
async function ev(expression) {
  const v = await call('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true })
  assert.ok(!v.exceptionDetails, JSON.stringify(v.exceptionDetails))
  return v.result.value
}
async function wait(expression) {
  const deadline = Date.now() + 30000
  while (!await ev(`Boolean(${expression})`)) { assert.ok(Date.now() < deadline, `DOM timeout: ${expression}`); await pause(30) }
}
async function click(label, selector = 'button', exact = true) {
  const point = await ev(`(()=>{const n=[...document.querySelectorAll(${JSON.stringify(selector)})].find(n=>${exact ? '(n.getAttribute("aria-label")||n.textContent).trim()===' : '(n.getAttribute("aria-label")||n.textContent).includes('}${JSON.stringify(label)}${exact ? '' : ')'});if(!n||n.disabled)throw Error('missing/disabled: '+${JSON.stringify(label)});n.scrollIntoView({block:'center'});const r=n.getBoundingClientRect(),x=r.x+r.width/2,y=r.y+r.height/2,hit=document.elementFromPoint(x,y);if(n!==hit&&!n.contains(hit))throw Error('obstructed: '+${JSON.stringify(label)});return{x,y}})()`)
  await call('Input.dispatchMouseEvent', { type: 'mousePressed', button: 'left', clickCount: 1, ...point })
  await call('Input.dispatchMouseEvent', { type: 'mouseReleased', button: 'left', clickCount: 1, ...point })
}
async function shot(name) {
  const v = await call('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false })
  fs.writeFileSync(path.join(out, name + '.png'), Buffer.from(v.data, 'base64'))
}
const metrics = `(()=>{const elements=[document.scrollingElement,document.body,document.querySelector('#root'),...document.querySelectorAll('.app-shell,.app-main,.app-main-content,.transcription-page,.queue-table-scroll')];return elements.filter(e=>e&&e.getBoundingClientRect().height>0).map(e=>({tag:e.tagName,cls:e.className,height:e.clientHeight,scrollHeight:e.scrollHeight,scrollTop:e.scrollTop,overflow:getComputedStyle(e).overflowY}))})()`
try {
  const url = await new Promise((resolve, reject) => {
    let text = ''
    server.stdout.on('data', v => { text += v; const m = text.match(/READY (\S+)/); if (m) resolve(m[1]) })
    server.stderr.on('data', v => errors.push(String(v)))
    server.on('exit', code => reject(Error(`fixture exited ${code}: ${errors.join('')}`)))
  })
  let port
  if (webview2) {
    port = await new Promise(r => { const socket=net.createServer();socket.listen(0,'127.0.0.1',()=>{const p=socket.address().port;socket.close(()=>r(p))}) })
    const host = path.join(root,'frontend/src-tauri/target/debug/examples/transcription_workspace_qa.exe')
    assert.ok(fs.existsSync(host),'Build the isolated QA example first')
    proc = spawn(host,[url+'?long=1',profile,String(port)],{windowsHide:true,stdio:['ignore','pipe','pipe']})
    proc.stdout.on('data',v=>errors.push(String(v)))
    proc.stderr.on('data',v=>errors.push(String(v)))
  } else {
    proc = spawn(chromium, ['--headless=new', '--remote-debugging-port=0', `--user-data-dir=${profile}`, '--no-first-run', '--no-default-browser-check', '--disable-background-networking', 'about:blank'], { windowsHide: true, stdio: 'ignore' })
    const portFile = path.join(profile, 'DevToolsActivePort'), deadline = Date.now() + 15000
    while (!fs.existsSync(portFile)) { assert.ok(Date.now() < deadline, 'browser startup timeout'); await pause(100) }
    port = fs.readFileSync(portFile, 'utf8').split('\n')[0]
  }
  let target
  const targetDeadline=Date.now()+30000
  while(!target) {
    assert.equal(proc.exitCode,null,`QA host exited: ${errors.join('')}`)
    try { target=(await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find(t=>t.type==='page') } catch {}
    if(!target) { assert.ok(Date.now()<targetDeadline,'CDP startup timeout');await pause(100) }
  }
  ws = new WebSocket(target.webSocketDebuggerUrl)
  await new Promise(r => ws.addEventListener('open', r, { once: true }))
  ws.addEventListener('message', e => {
    const v = JSON.parse(e.data)
    if (v.method === 'Runtime.exceptionThrown') errors.push(v.params)
    if (v.id) { const p = pending.get(v.id); pending.delete(v.id); v.error ? p?.reject(Error(JSON.stringify(v.error))) : p?.resolve(v.result) }
  })
  await call('Page.enable'); await call('Runtime.enable'); await call('Network.enable')
  await call('Network.setBlockedURLs', { urls: ['http://127.0.0.1:8000/*', 'http://localhost:8000/*', 'https://www.googleapis.com/*', 'https://accounts.google.com/*'] })
  async function navigate(query = '') {
    await call('Page.navigate', { url: url + query })
    await wait("window.__workspace && document.querySelectorAll('tbody tr').length>0")
  }
  if(webview2)await wait("document.readyState==='complete' && window.__workspace && document.querySelectorAll('tbody tr').length===80")
  await call('Emulation.setDeviceMetricsOverride', { width: 1440, height: 926, deviceScaleFactor: 1, mobile: false })
  await navigate('?long=1')
  await shot(baseline ? 'ui-before-top' : 'ui-after-top')
  if (baseline) {
    results.hidden_absolute_elements = await ev("[...document.querySelectorAll('.visually-hidden')].map(e=>({tag:e.tagName,text:e.textContent,offsetParent:e.offsetParent?.tagName,top:e.getBoundingClientRect().top}))")
    if(process.argv.includes('--probe'))await ev("document.querySelector('.app-main').style.position='relative'")
    await ev("document.querySelector('.app-main').scrollTop=100000")
    results.scroll_before = await ev(metrics)
    await shot('ui-before-bottom')
  } else {
    for (const [width, height] of [[1440,926],[1024,768],[800,650],[1920,1080]]) {
      await call('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: false })
      const m = await ev(metrics)
      assert.equal(m[0].scrollHeight, m[0].height, `document must not scroll at ${width}`)
      assert.deepEqual(m.filter(e => ['auto','scroll'].includes(e.overflow) && e.scrollHeight > e.height + 1).map(e => e.cls), ['app-main'])
      assert.equal(await ev("document.querySelectorAll('.app-top-bar .transcription-controls').length"), 1)
      assert.equal(await ev("document.querySelectorAll('.app-main .transcription-controls').length"), 0)
      assert.ok(await ev("[...document.querySelectorAll('.app-top-bar button')].every(e=>{const r=e.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth&&r.bottom<=document.querySelector('.app-top-bar').getBoundingClientRect().bottom})"))
      await ev("document.querySelector('.app-main').scrollTop=100000")
      await pause(50)
      assert.ok(await ev("document.querySelector('tbody tr:last-child').getBoundingClientRect().bottom<=document.querySelector('.app-main').getBoundingClientRect().bottom"))
      results[`single_scroll_header_last_row_${width}`] = 'PASS'
    }
    await shot('ui-after-bottom')
    results.scroll_after = await ev(metrics)
    await ev("document.querySelector('.app-main').scrollTop=0;document.querySelector('.app-main').focus()")
    await call('Input.dispatchKeyEvent',{type:'keyDown',key:'PageDown',code:'PageDown',windowsVirtualKeyCode:34})
    await call('Input.dispatchKeyEvent',{type:'keyUp',key:'PageDown',code:'PageDown',windowsVirtualKeyCode:34})
    await pause(300)
    assert.ok(await ev("document.querySelector('.app-main').scrollTop>0"))
    await call('Input.dispatchMouseEvent',{type:'mouseWheel',x:700,y:400,deltaX:0,deltaY:400})
    await pause(300)
    results.keyboard_and_wheel = 'PASS'
    await ev("document.querySelector('.app-brand').focus()")
    for(let i=0;i<5;i++) {
      await call('Input.dispatchKeyEvent',{type:'keyDown',key:'Tab',code:'Tab',windowsVirtualKeyCode:9})
      await call('Input.dispatchKeyEvent',{type:'keyUp',key:'Tab',code:'Tab',windowsVirtualKeyCode:9})
    }
    assert.equal(await ev("document.activeElement.textContent.trim()"),'전사 시작')
    await click('모든 파일 선택','input')
    await wait("document.querySelector('.overall-progress').textContent.includes('80개 선택')")
    await click('모든 파일 선택','input')
    results.keyboard_header_and_queue_selection = 'PASS'
    for (const page of ['로그','Folders','설정']) {
      await click(page, '.app-navigation-link')
      await wait(`document.querySelector('h1').textContent===${JSON.stringify(page)}`)
      assert.equal(await ev("document.querySelectorAll('.app-top-bar button').length"), 0)
      assert.equal(await ev("document.scrollingElement.scrollHeight>document.scrollingElement.clientHeight"), false)
      results[`navigation_${page}`] = 'PASS'
    }
    await click('전사', '.app-navigation-link')
    await wait("document.querySelector('.app-top-bar .transcription-controls')")
    await ev("(()=>{let e=document.querySelector('input[placeholder=\"예: 1\"]');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e,'1');e.dispatchEvent(new Event('input',{bubbles:true}));})()")
    await click('전사 시작'); await wait("document.querySelector('[aria-modal=true]')")
    await click('실행'); await wait('window.__workspace.started.length===1')
    assert.equal((await ev('window.__workspace.created'))[0].upload_to_drive, false)
    await click('로그','.app-navigation-link'); await click('전사','.app-navigation-link')
    await wait("document.querySelector('.current-task-section').textContent.includes('42%')")
    assert.equal(await ev("document.querySelector('input[placeholder=\"예: 1\"]').value"),'1')
    await click('전사 중지'); await wait("window.__workspace.actions.includes('stop')")
    results.start_stop_navigation_preserves_state = 'PASS'
    await navigate('?state=TRANSCRIBING')
    await click('작업 취소'); await wait("window.__workspace.actions.includes('cancel')")
    results.cancel = 'PASS'
    await navigate('?state=FAILED')
    await wait("document.querySelector('[role=alert]')?.textContent.includes('현재 앱 빌드')")
    await shot('ui-after-failed')
    await click('설정','.app-navigation-link')
    await wait("document.querySelector('.drive-retry-list button:not(:disabled)')")
    await click('Drive 실패 다시 시도')
    await wait('window.__workspace.uploads.length===1')
    assert.deepEqual(await ev('window.__workspace.actions'),[])
    await click('전사','.app-navigation-link')
    await click('실패 파일 다시 시도 · 1'); await wait("window.__workspace.actions.includes('retry')")
    results.failure_and_drive_only_retry = 'PASS'
    await navigate()
    await click('Colab','.engine-option',false)
    await click('Colab 연결 설정')
    await wait("document.querySelector('h1').textContent==='설정'")
    await click('Colab 연결'); await wait("document.querySelector('.engine-state-connected')")
    await shot('ui-after-settings')
    await click('전사','.app-navigation-link')
    await wait("document.querySelector('.engine-section').textContent.includes('연결됨')")
    assert.equal(await ev("document.querySelector('input[value=direct_colab]').checked"),true)
    results.colab_connection_in_settings = 'PASS'
    await navigate('?state=DONE')
    await wait("document.querySelector('.overall-progress').textContent.includes('3 / 3 완료')")
    results.done = 'PASS'
    assert.deepEqual(errors, [])
  }
  fs.writeFileSync(path.join(out, baseline ? 'scroll-before.json' : webview2 ? 'webview2-ui-results.json' : 'ui-results.json'),JSON.stringify(results,null,2))
  console.log(JSON.stringify(results,null,2))
} catch(e) {
  console.error(e)
  if(ws?.readyState===WebSocket.OPEN)console.error(await ev('({ready:!!window.__workspace,rows:document.querySelectorAll("tbody tr").length,text:document.body.innerText.slice(0,2000)})').catch(()=>errors))
  process.exitCode=1
} finally {
  if(ws?.readyState===WebSocket.OPEN){await call('Browser.close').catch(()=>{});ws.close()}
  if(proc && proc.exitCode===null)await new Promise(r=>{proc.once('exit',r);setTimeout(()=>{proc.kill();r()},5000).unref()})
  server.kill()
  // Keep the owned isolated profile as local debugging evidence (Git ignored).
}
