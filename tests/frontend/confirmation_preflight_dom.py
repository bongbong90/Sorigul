"""Manual #171 DOM gate using local Chromium + websocket-client, no install.

Run: python tests/frontend/confirmation_preflight_dom.py
The regular root suite uses the dependency-free callback harness. This gate
launches an isolated headless browser profile and the synthetic Vite fixture;
it never contacts the product backend or installed desktop application.
"""
import json
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.request

import websocket

ROOT = Path(__file__).resolve().parents[2]
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
if not CHROME.is_file():
    CHROME = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")


class Browser:
    def __init__(self, ws):
        self.ws, self.serial = ws, 0
        self.events = []

    def call(self, method, **params):
        self.serial += 1
        self.ws.send(json.dumps({"id": self.serial, "method": method, "params": params}))
        while True:
            reply = json.loads(self.ws.recv())
            if reply.get('method') == 'Runtime.exceptionThrown':
                self.events.append(reply['params'])
            if reply.get("id") == self.serial:
                assert "error" not in reply, reply
                return reply.get("result", {})

    def evaluate(self, expression):
        reply = self.call("Runtime.evaluate", expression=expression, awaitPromise=True, returnByValue=True)
        assert "exceptionDetails" not in reply, reply
        return reply["result"].get("value")

    def wait(self, expression):
        self.evaluate("""new Promise((resolve, reject) => {
          const deadline = Date.now() + 10000;
          const check = () => {
            if (EXPRESSION) return resolve(true);
            if (Date.now() > deadline) return reject(new Error('DOM condition timed out'));
            setTimeout(check, 20);
          }; check();
        })""".replace("EXPRESSION", expression))

    def click(self, label, selector="button", exact=True):
        coordinates = self.evaluate("""(() => {
          const label = LABEL;
          const node = [...document.querySelectorAll(SELECTOR)].find(n => EXACT
            ? (n.getAttribute('aria-label') || n.textContent).trim() === label
            : (n.getAttribute('aria-label') || n.textContent).includes(label));
          if (!node || node.disabled) throw new Error('missing/disabled control: ' + label);
          node.scrollIntoView({ block: 'center' });
          const r = node.getBoundingClientRect(), x = r.x + r.width/2, y = r.y + r.height/2;
          const hit = document.elementFromPoint(x,y);
          if (hit !== node && !node.contains(hit)) throw new Error('obstructed control: ' + label + ' hit=' + hit?.className);
          return { x, y };
        })()""".replace("LABEL", json.dumps(label)).replace("SELECTOR", json.dumps(selector)).replace("EXACT", str(exact).lower()))
        self.call("Input.dispatchMouseEvent", type="mousePressed", button="left", clickCount=1, **coordinates)
        self.call("Input.dispatchMouseEvent", type="mouseReleased", button="left", clickCount=1, **coordinates)

    def unobstructed_review(self):
        assert self.evaluate("document.querySelectorAll('.dialog-backdrop, [aria-modal=true]').length") == 0
        self.evaluate("""(() => {
          const buttons = [...document.querySelectorAll('.filename-review button')];
          if (!buttons.length) throw new Error('missing review controls');
          for (const node of buttons) {
            node.scrollIntoView({block:'center'});
            const r = node.getBoundingClientRect(), hit = document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);
            if (node.disabled || (node !== hit && !node.contains(hit))) throw new Error('review control obstructed');
          }
        })()""")


def run(browser, url):
    results = {}
    for kind in ("start-all", "retranscribe"):
        for disposition in ("INVALID_TARGET", "CONFLICT", "MISMATCH", "UNCHANGED"):
            browser.call("Page.navigate", url=f"{url}?type={disposition}&hold=1")
            browser.wait("window.__171 && document.querySelector('.transcription-controls button:not(:disabled)')")
            if kind == "start-all":
                browser.click("전사 시작")
            else:
                browser.click("DONE.mp3 다시 전사")
            browser.wait("document.querySelector('[aria-modal=true]')")
            summary = browser.evaluate("document.querySelector('.dialog').textContent")
            if kind == "start-all":
                assert "전체 3개 중 완료 1개를 제외한 2개" in summary, summary
            else:
                assert "기존 정상 결과를 보존합니다." in summary
                assert "새 결과 검증 성공 후에만 교체합니다." in summary
            browser.click("실행" if kind == "start-all" else "다시 전사 시작")
            browser.wait("window.__171.release !== null")
            assert browser.evaluate("document.querySelectorAll('.dialog-backdrop, [aria-modal=true]').length") == 0
            browser.evaluate("window.__171.release()")
            targets = 2 if kind == "start-all" else 1
            if disposition != "UNCHANGED":
                browser.wait("document.querySelector('.filename-review button')")
                for index in range(targets):
                    browser.unobstructed_review()
                    if disposition == "MISMATCH":
                        browser.click("원래 이름으로 Local 전사 계속", ".filename-review button")
                    else:
                        browser.click("원래 이름으로 계속", ".filename-review button")
                    if index + 1 < targets:
                        browser.wait("document.querySelector('.filename-review').textContent.includes('B2.mp3')")
            browser.wait("window.__171.started.length === 1")
            created = browser.evaluate("window.__171.created")
            assert len(created) == 1
            assert created[0]["file_ids"] == (["B1", "B2"] if kind == "start-all" else ["DONE"])
            assert created[0]["force_retranscribe"] == (kind == "retranscribe")
            results[f"{kind}_{disposition}_hit_test_and_job"] = "PASS"
    # Actual mouse clicks reach Edit / Apply and both classification choices.
    for action in ("edit", "classification", "rename_to_typed"):
        disposition = "INVALID_TARGET" if action == "edit" else "MISMATCH"
        browser.call("Page.navigate", url=f"{url}?type={disposition}")
        browser.wait("window.__171 && document.querySelector('.transcription-controls button:not(:disabled)')")
        browser.click("DONE.mp3 다시 전사"); browser.wait("document.querySelector('[aria-modal=true]')")
        browser.click("다시 전사 시작"); browser.wait("document.querySelector('.filename-review button')")
        browser.unobstructed_review()
        if action == "edit":
            browser.click("이름 수정", ".filename-review button")
            browser.wait("document.querySelector('#normalized-filename')")
            browser.evaluate("""(() => {
              const input = document.querySelector('#normalized-filename');
              Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,'edited.mp3');
              input.dispatchEvent(new Event('input',{bubbles:true}));
            })()""")
            browser.click("이름 적용", ".filename-review button")
        elif action == "classification":
            browser.click("현재 파일의 분류 사용", ".filename-review button")
        else:
            browser.click("입력한 분류로 파일명 변경", ".filename-review button")
        browser.wait("window.__171.started.length === 1")
        assert browser.evaluate("window.__171.created.length") == 1
        results[f"{action}_mouse_reachable"] = "PASS"
    return results


def main():
    server = subprocess.Popen(["node", str(ROOT / "tests/frontend/confirmation_preflight_browser.mjs")],
                              cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                              creationflags=subprocess.CREATE_NO_WINDOW)
    browser_process = ws = profile_dir = None
    try:
        ready = server.stdout.readline().strip()
        assert ready.startswith("READY "), ready or server.stderr.read()
        url = ready.removeprefix("READY ")
        profile_dir = tempfile.TemporaryDirectory(prefix="171-browser-", dir=ROOT / "tmp")
        profile = profile_dir.name
        assert Path(profile).resolve().is_relative_to((ROOT / "tmp").resolve())
        browser_process = subprocess.Popen([str(CHROME), "--headless=new", "--remote-debugging-port=0",
            f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check", "--disable-background-networking",
            "--window-size=1400,1000", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW)
        port_file = Path(profile) / "DevToolsActivePort"
        deadline = time.monotonic() + 15
        while not port_file.exists():
            assert time.monotonic() < deadline, "headless browser startup timed out"
            time.sleep(0.1)
        port = port_file.read_text().splitlines()[0]
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=10) as response:
            target = next(item for item in json.load(response) if item["type"] == "page")
        ws = websocket.create_connection(target["webSocketDebuggerUrl"], timeout=15, suppress_origin=True)
        browser = Browser(ws)
        browser.call("Page.enable")
        browser.call("Runtime.enable")
        browser.call("Network.enable")
        browser.call("Network.setBlockedURLs", urls=["http://127.0.0.1:8000/*", "http://localhost:8000/*"])
        try:
            results = run(browser, url)
        except Exception:
            print(json.dumps({"exceptions": browser.events, "body": browser.evaluate("document.body.innerText")}, ensure_ascii=True))
            raise
        browser.call("Browser.close")
        browser_process.wait(timeout=10)
        ws.close(); ws = None
        print(json.dumps(results, ensure_ascii=False))
    finally:
        if ws:
            try:
                Browser(ws).call("Browser.close")
            except Exception:
                pass
            ws.close()
        if browser_process and browser_process.poll() is None:
            browser_process.terminate(); browser_process.wait(timeout=10)
        server.terminate(); server.wait(timeout=10)
        if profile_dir:
            profile_dir.cleanup()


if __name__ == "__main__":
    main()
