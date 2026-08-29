# Installer / Installed Runtime Validation

## Status

**INSTALLER / INSTALLED RUNTIME VALIDATION READY**

## Baseline

- Branch: `feature/installer-installed-runtime-validation`, created from
  `origin/feature/tauri-runtime-sidecar-os-integration` at `b6af9cebc14d5d913e7ece3c9798ca5b1a690af2`
  (includes the original Tauri Runtime work, PR #3 Manual Smoke Closure, and PR #4 Windows App
  Icon/Branding).
- Migration Contract: unchanged.
- UI Freeze v1 (전사 / 로그 / Folders / 설정 screen structure and navigation): unchanged. The only
  UI behavior change is inside the Settings page's Google Drive card (added in the prior Tauri
  Runtime work package, not part of the original frozen four-screen set): the manual
  authorization-code paste step is replaced by automatic status polling (see OAuth section below).
- This work package changes no product feature. It packages the existing dev-mode Sorigul into an
  installable, standalone Windows desktop app.

## Packaging Architecture

```
MSI installer
  -> C:\Program Files\Sorigul\sorigul-desktop.exe   (Tauri shell, unchanged UI)
       -> spawns C:\Program Files\Sorigul\binaries\sorigul-backend.exe (packaged FastAPI, PyInstaller one-file)
            -> PATH-injected sibling C:\Program Files\Sorigul\binaries\ffmpeg.exe (bundled, no system PATH dependency)
```

`resource_dir/binaries/{sorigul-backend.exe,ffmpeg.exe}` is the existing contract from the prior
Tauri Runtime work package (`packaged_spawn_spec` in `lib.rs`); this package fills it in rather than
replacing it.

## Backend Packaging

- Entry point: `backend/src/sidecar_main.py` -- `sorigul-backend.exe --port 8000` (normal run,
  identical FastAPI app as dev) and `sorigul-backend.exe --self-test` (import/runtime checks only;
  never downloads a model, never touches Google, never transcribes).
- Build tool: PyInstaller `6.22.2`, **one-file** mode (`backend/packaging/sorigul_backend.spec`).
  One-file was attempted first per the work package's own decision tree; it built and ran
  successfully (see Known Risks for the cold-start cost it does carry), so no fallback to `onedir`
  was needed.
- Packaging-only dependencies isolated in `tools/requirements-packaging.txt` (`pyinstaller==6.22.2`,
  `imageio-ffmpeg==0.6.0`), separate from `backend/requirements*.txt`.
- Built via `scripts/build_backend_sidecar.ps1` (installs requirements, runs PyInstaller with a
  clean workpath/distpath, stages the exe + ffmpeg into `frontend/src-tauri/binaries/`, runs
  `--self-test` against the staged copy, fails the script on any non-zero exit).
- Verified output (this session's build): `sorigul-backend.exe`, **230,654,187 bytes**,
  SHA-256 `6b064cf604437979d67ea57b11ff1b3531ee302ce2e5f7f5bdbf990892e65ec4`.
- Self-test (staged copy, real run): `fastapi_app_import`, `uvicorn_import`,
  `google_drive_runtime_import`, `whisper_import`, `torch_import`, `ffmpeg_availability`,
  `runtime_path_initialization` -- **all 7 PASS**, exit code 0.
- Console mode: built windowed (`console=False`) so the packaged backend never shows a console
  window. Because a windowed PyInstaller build has no attached stdio, `--self-test` also writes its
  result to `sorigul-backend-selftest.log` next to the exe so a build script (or a human) can read
  the result either way.
- Real standalone run (this session, outside the installer, then again from the installed
  location): `GET /api/health` -> `{"status":"ok"}`; only `sorigul-backend.exe` (two OS processes --
  the PyInstaller one-file bootloader and its unpacked child, both spawned from
  `C:\Program Files\Sorigul\binaries\`) ever appeared in the process list; **no `python.exe` process
  ever appeared**.

## Whisper Runtime

- `whisper` import: PASS (`openai-whisper==20250625`, unchanged pin).
- `torch` import: PASS (`torch==2.13.0`, CPU build, resolved automatically as openai-whisper's
  dependency).
- Model bundled in the installer: **No.** The `medium` model weight is not embedded in the MSI or
  the exe. `LocalWhisperEngine`'s existing cache/load behavior (`whisper.load_model("medium", ...)`)
  is unchanged -- the model downloads/caches on first real use, exactly as in dev mode.
- Model cache policy: unchanged and untouched. No existing user's Whisper cache was read, moved, or
  deleted by this work package or its testing.

## FFmpeg

- Provider: `imageio-ffmpeg==0.6.0` (PyPI package, BSD-2-Clause wrapper), which bundles a static
  ffmpeg build reproducibly resolvable via `imageio_ffmpeg.get_ffmpeg_exe()`.
- FFmpeg version: `v7.1` (`ffmpeg-win-x86_64-v7.1.exe`).
- Verified binary: **87,638,016 bytes**, SHA-256
  `2ce797a0f88d7f067180338fb227f7b1928ea727bd9a4d7a1d022f7c52af71a3`.
- Bundled location: `frontend/src-tauri/binaries/ffmpeg.exe` -> installed
  `C:\Program Files\Sorigul\binaries\ffmpeg.exe`.
- System PATH dependency: **removed** for the packaged release. `packaged_spawn_spec` in `lib.rs`
  now checks both `sorigul-backend.exe` and `ffmpeg.exe` exist under `resource_dir/binaries/` before
  spawning (`PACKAGED_BACKEND_MISSING` / `PACKAGED_FFMPEG_MISSING` otherwise) and prepends that
  `binaries/` directory onto the **child process's own** `PATH` only (`SpawnSpec.env`, applied via
  `Command::env` in `sidecar.rs`) -- the app's own process-wide environment is never touched. Dev
  mode is unchanged: `dev_spawn_spec()` passes no extra env and still relies on whatever ffmpeg the
  developer has on their own PATH, same as before this work package.
- License notice (Known Risk, not a runtime defect): the ffmpeg binary imageio-ffmpeg bundles is
  itself licensed under FFmpeg's own terms (GPL/LGPL depending on the exact build), separately from
  imageio-ffmpeg's own BSD-2-Clause wrapper license. Carrying FFmpeg's license text/notice in the
  installer or an About screen is a packaging-legal follow-up not yet added.

## Tauri Resources

- `tauri.conf.json` -> `bundle.resources` now declares
  `binaries/sorigul-backend.exe` and `binaries/ffmpeg.exe` (Tauri v2's official `bundle.resources`
  map, not `externalBin`/sidecar, matching the existing `resource_dir/binaries/...` contract exactly
  so it was not changed).
- Verified: `cargo check` fails explicitly (`resource path 'binaries\ffmpeg.exe' doesn't exist`) if
  the binaries aren't staged first -- confirming the resources are actually wired into the build,
  not just declared.
- Actual installed resource path (this session's real MSI install):
  `C:\Program Files\Sorigul\binaries\sorigul-backend.exe` and `...\binaries\ffmpeg.exe`, both present
  and matching the staged file sizes.

## Release Spawn

- Dev: unchanged (`venv\Scripts\python.exe -m uvicorn src.main:app ...` from `backend/`, no env
  injection).
- Packaged: `resource_dir/binaries/sorigul-backend.exe --port 8000`, with `PATH` prepended with
  `resource_dir/binaries/` for the child only.
- **Dev Python fallback removed.** Previously, `spawn_spec_for_current_build` silently fell back to
  `dev_spawn_spec()` (hunting for a venv/system Python) if `packaged_spawn_spec` failed for any
  reason in a release build. It now returns `Result<SpawnSpec, String>`; a release build's failure
  to resolve its own packaged resources surfaces as `SidecarStatus::StartupFailed(reason)` (emitted
  as the existing `sorigul://sidecar-status` event) and **never** falls back to hunting for a system
  Python. Debug builds always use `dev_spawn_spec()`; release builds always use
  `packaged_spawn_spec()` -- no fallback in either direction.
- Missing-resource failure behavior, each a distinct explicit error: `RESOURCE_DIR_UNAVAILABLE`,
  `PACKAGED_BACKEND_MISSING`, `PACKAGED_FFMPEG_MISSING`. Covered by three new Rust unit tests
  (`packaged_spawn_spec_fails_explicitly_when_backend_exe_is_missing`,
  `..._when_ffmpeg_is_missing`, `..._succeeds_and_prepends_binaries_dir_to_child_path_when_both_present`)
  against a Tauri-independent `packaged_spawn_spec_from_resource_dir(&Path)` core function, using
  real temp directories -- not mocked.

## MSI

- Tauri CLI: `@tauri-apps/cli 2.9.4` (unchanged from the prior work package).
- Command, confirmed against `npx tauri build --help` (not guessed): `npx tauri build --bundles msi`.
- Artifact: `frontend/src-tauri/target/release/bundle/msi/Sorigul_0.1.0_x64_en-US.msi`.
- Size: **262,504,448 bytes**. SHA-256: `b88bc8bc2cb8b0db2c7c4a48b3a74b3d1265d5f9507d9ff026607dfe7ea42b0e`.
- Signed/unsigned: **UNSIGNED** (no certificate provisioned in this environment; see Code Signing
  below). WiX (`candle`/`light`) resolved and ran without any manual toolchain setup in this
  environment.
- Build fully automated via `scripts/build_windows_installer.ps1` (sidecar build + self-test ->
  frontend build -> `cargo fmt/check/clippy/test` -> `tauri build --bundles msi` -> artifact
  report), fails fast on the first non-zero exit at any stage.

## Clean Install

- Pre-check (this session): no prior Sorigul installation, no running Sorigul process, no
  `%LOCALAPPDATA%\Sorigul` -- genuinely clean machine state before testing began.
- `msiexec /i "Sorigul_0.1.0_x64_en-US.msi" /passive /norestart /log ...` -> **exit code 0**,
  log confirms "Installation completed successfully."
- Installed path: `C:\Program Files\Sorigul\` (`InstallLocation` in the Apps/uninstall registry key
  matches). Elevation: required and used (log shows `MsiRunningElevated = 1`, `Privileged = 1`).
- WebView2: not embedded; the machine's existing system WebView2 was used automatically (the
  installed app rendered a real "Sorigul"-titled window and made live HTTP calls against the
  backend without any separate WebView2 install step).

## Installed Runtime

- Window: a real native window with `MainWindowTitle == "Sorigul"` was confirmed open
  (`Get-Process` on the installed `sorigul-desktop.exe`).
- Backend auto-start: confirmed -- `sorigul-backend.exe` (bootloader + child) both running from
  `C:\Program Files\Sorigul\binaries\sorigul-backend.exe`, started automatically by the app, no
  manual launch.
- Health: `GET http://127.0.0.1:8000/api/health` -> `200 {"status":"ok"}`. First-launch latency was
  ~15-18s (see Known Risks -- PyInstaller one-file cold-start extraction), within the existing 20s
  Rust health-probe timeout but with limited margin.
- Backend exe path: `C:\Program Files\Sorigul\binaries\sorigul-backend.exe` (confirmed via
  `Get-Process ... | Select Path`) -- never a repo path, never a venv path.
- `python.exe` dependency: **none, at any point** across every launch in this session (fresh
  install, standalone re-launch, reinstall).
- `node`/Vite dependency: none -- the frontend is the pre-built `dist/` bundle loaded by the
  installed exe's own WebView2, no dev server involved.
- Backend console: none -- no `conhost.exe` process was ever present, and the backend processes'
  `MainWindowTitle` was empty (no window at all), matching the existing `CREATE_NO_WINDOW` +
  `Stdio::null()` + windowed-PyInstaller-build discipline.

## Native UX

- Folder picker / Explorer open / Tray menu clicks ("앱 열기", "종료") / Notification toast: **NOT
  RUN** in this automated pass -- this is an unattended agent session with no interactive display or
  UI-automation harness to click a native dialog, tray menu item, or observe a toast, the same
  limitation the prior Tauri Runtime work package recorded for its own interactive smoke. The
  underlying code for all of these is **unchanged** from that work package and from Windows App
  Icon/Branding, both of which recorded live manual PASS for tray open/hide/quit and Explorer/picker
  behavior against the same `native.ts`/`lib.rs` code this package did not touch.
- `close_behavior = tray` (the default): **verified live in this pass**, without needing UI
  automation -- a real `WM_CLOSE` message was posted to the installed app's actual window handle
  (`user32.dll` `PostMessage`, the same message the OS sends for an X-button click or Alt+F4). The
  window's `IsWindowVisible` flipped to `false` (hidden, not destroyed), the app process and the
  owned backend process both remained running, and `/api/health` kept responding -- exactly the
  documented tray-hide contract.
- `close_behavior = exit` (requires navigating to Settings and toggling a checkbox to take effect in
  the Rust-cached value) was not independently re-driven this pass for the same no-interactive-display
  reason; its underlying `set_close_behavior` command and the `RunEvent::ExitRequested` cleanup path
  are unchanged and are covered by the existing (non-mocked) `cargo test` suite.

## Unicode / Windows

All four path classes were tested for real against the **installed** packaged backend
(`POST /api/scan`, `POST /api/folders/scan`) using a temporary QA folder tree under
`%TEMP%\소리글 설치 검증\...` created solely for this test and removed afterward, with a 1-second
silence MP3 generated by the **bundled** ffmpeg (`ffmpeg -f lavfi -i anullsrc ...`) as the scan
target in each folder:

- **Korean** (`B_한글경로\소리글_전사자료_테스트\한글_파일명.mp3`): PASS -- `200`, correct UTF-8
  filename/path round-tripped exactly.
- **Unicode incl. emoji** (`D_유니코드_🎙️테스트\데이터\유니코드_🎙️_파일.mp3`): PASS -- `200`,
  emoji preserved byte-for-byte in the JSON response.
- **Spaces** (`C_공백 경로\소리글 설치 검증 자료\공백 포함 파일명.mp3`): PASS -- `200`.
- **Long path** (668 characters, 8 nested Korean-named segments, well past the classic 260-char
  `MAX_PATH`): PASS -- `200`, full path round-tripped exactly. This machine's
  `HKLM\SYSTEM\CurrentControlSet\Control\FileSystem\LongPathsEnabled` was already `1` **before this
  session** (read-only checked, not modified, per instruction); the result should be read as "the
  application does not itself impose any path-length truncation" rather than as a guarantee under
  `LongPathsEnabled = 0`.
- Folder-picker dialog / Explorer-open for these same paths: NOT RUN (see Native UX -- no
  interactive display). The backend-side path handling exercised above is what the architecture
  actually validates on (the frontend/Rust layers pass these strings through opaquely, per the prior
  work package's design), so this is the load-bearing part of the Unicode contract.

## Folder Picker

NOT RUN (interactive native dialog; no interactive display in this session -- see Native UX).

## Explorer

NOT RUN (interactive; see Native UX). The server-validated open-intent boundary
(`POST /folders/{scan_id}/open-intent`) itself is unchanged by this work package.

## Tray

Existence/icon/menu-click NOT independently re-verified visually this pass (see Native UX). The
default `close_behavior = tray` hide path was verified live via `WM_CLOSE` (see above).

## Notification

NOT RUN -- requires either a real completed transcription or a live UI session to trigger safely;
per the work package's own instructions this is an allowed NOT RUN rather than a forced fake event.

## Process Cleanup

- `close_behavior = tray`, window hidden via `WM_CLOSE`: app + owned backend process both survive,
  `/api/health` keeps responding -- correct (verified live, see Native UX).
- **Abnormal termination test** (this session): killing *only* `sorigul-desktop.exe`
  (`taskkill /PID ... /F`, no `/T`) while `sorigul-backend.exe` was running left the backend process
  **orphaned** (still running, port 8000 still `LISTENING`) until manually cleaned up. This is
  inherent Windows process behavior (no parent-child auto-kill without a Job Object) and is **not a
  regression from this work package** -- it is the reason `RunEvent::ExitRequested`'s cleanup exists
  in the first place, and it only runs when the app exits through its own normal paths (Tray "종료",
  or a window actually closing under `close_behavior = exit`), not when the process is killed
  externally or crashes. Flagged as a Known Risk with a suggested future improvement (Job Object
  supervision), not treated as a blocking defect here.
- The graceful cleanup path itself (`SidecarManager::cleanup()`) is unchanged from the prior work
  package and remains covered by real (non-mocked) `cargo test`s that spawn an actual process and
  confirm its termination via `tasklist` (`cleanup_terminates_the_owned_process`) and that an
  unowned process survives cleanup (`cleanup_does_not_touch_an_unowned_external_process`).

## Port Release

Verified live: after a full `taskkill /IM sorigul-backend.exe /T /F` (simulating the same
process-tree-kill `cleanup()` performs internally via `taskkill.exe /PID <pid> /T /F`), `netstat`
showed no `LISTENING` entry on port 8000 -- only transient `TIME_WAIT` entries from already-closed
connections, which the OS reclaims on its own.

## Settings Persistence

Verified live: `PUT /api/settings {"close_behavior":"exit"}` against the installed, running backend
persisted to `%LOCALAPPDATA%\Sorigul\settings.json`; the value was still present, unchanged, after a
full MSI reinstall (see Reinstall below). Job-state persistence was not separately exercised this
pass -- no pre-existing job history existed on this clean machine, and per the work package's own
instruction, a fresh job was not artificially created just to populate history (deferred to backend
regression / Full Parity Regression, which already covers `JobManager` persistence).

## Reinstall

`msiexec /i` against the same MSI, same version, while already installed -> **exit code 0**, log:
"Configuration completed successfully" (Windows Installer's expected repair/reconfigure path for an
identical ProductCode+version). `C:\Program Files\Sorigul\` and its resources were intact afterward,
and `%LOCALAPPDATA%\Sorigul\settings.json` (the test value from Settings Persistence above) was
preserved untouched.

## Upgrade

**UPGRADE SCENARIO: DEFERRED TO RELEASE VERSION BUMP** -- not exercised via a temporary
`0.1.0 -> 0.1.1` override this pass. Not an Installer-READY blocker per the work package's own
instructions.

## Uninstall

`msiexec /x {ProductCode} /passive /norestart` -> **exit code 0**, log: "Removal completed
successfully." Verified afterward:

- `C:\Program Files\Sorigul\`: removed.
- Start Menu folder (`...\Start Menu\Programs\Sorigul`): removed.
- Desktop shortcut (`%PUBLIC%\Desktop\Sorigul.lnk`): removed.
- Apps/uninstall registry entry: removed.
- Process residue: none (`sorigul-desktop.exe`/`sorigul-backend.exe` both absent).
- Port residue: none (`netstat` showed no `LISTENING` entry on 8000).
- `%LOCALAPPDATA%\Sorigul\settings.json`: **preserved**, confirmed present and unchanged
  immediately after uninstall.

The preserved `settings.json` was itself synthetic QA data created fresh in this session (this
machine had no `%LOCALAPPDATA%\Sorigul` before testing began) -- it was removed afterward by this
QA pass as its own cleanup, not as part of, or a test of, the uninstaller's behavior.

## Final machine state

**UNINSTALLED AFTER QA.**

## User Data Preservation

Confirmed end-to-end: `%LOCALAPPDATA%\Sorigul\settings.json` survived both a reinstall and a full
uninstall untouched. No `jobs.json`, `auth/`, token, or cache path existed on this machine to test
against (clean machine), but the same `SettingsManager`/`JobManager`/`GoogleOAuthService` file
paths and atomic-write-then-replace persistence logic (unchanged by this work package) apply to all
of them identically.

## Windows Icons

- MSI / installed EXE / Start Menu / Desktop shortcut: all reference the same `icon.ico` produced
  and pixel-verified by the Windows App Icon/Branding work package (`docs/runtime/
  WINDOWS_APP_ICON_BRANDING.md`), unchanged by this package. The Start Menu and Desktop shortcuts
  were confirmed (via `WScript.Shell` `CreateShortcut`) to target the correct installed exe with
  `IconLocation` index `0` (the embedded icon).
- Taskbar / Alt+Tab / Tray / Apps & Features pixel-level visual confirmation: **NOT independently
  re-verified this pass** (no interactive display) -- the icon pipeline itself is unchanged from the
  prior work package, which already recorded live manual PASS for exactly these surfaces.
- Desktop shortcut: **PASS, not N/A** -- the installer creates one by default (confirmed present at
  `%PUBLIC%\Desktop\Sorigul.lnk` after clean install, removed after uninstall).
- Transparent-branding contract: unchanged: no solid-color-square regression is possible since no
  icon asset was touched by this work package.

## OAuth Loopback Callback

The manual "paste the code from the browser address bar" fallback (the prior work package's
explicitly deferred packaging decision, needed because the old fixed `redirect_uri =
http://127.0.0.1` on port 80 requires elevation to bind) is **replaced** with a real desktop-loopback
flow, implemented in `backend/src/services/drive.py`:

- `LoopbackCallbackServer` binds `127.0.0.1:0` (OS-assigned ephemeral port -- never a fixed port, no
  elevation needed) and its `redirect_uri` is wired directly into the `Flow.from_client_secrets_file`
  / `authorization_url()` call, replacing the old fixed port-80 URI.
- A per-flow random `state` (`secrets.token_urlsafe(24)`) is generated and required to match on
  callback; a mismatched or missing `state` is rejected (`400`) without consuming the listener, so
  the legitimate callback is still accepted afterward.
- On a valid callback, `GoogleOAuthService` now **automatically** calls `complete()` on a background
  thread -- the manual "인증 코드 입력" text field and "인증 완료" button were removed from
  `SettingsPage.tsx`; the button now just opens the browser and the UI polls `GET /api/drive/status`
  every 2s (up to 5 minutes, matching the backend's own callback timeout) until it observes
  `CONNECTED` or a terminal failure state.
- The browser response on success is the minimal HTML specified: "Google Drive 연결이
  완료되었습니다.<br>이 창을 닫고 소리글로 돌아가세요." -- no code or token is ever echoed back to
  the browser, logged, or sent to the frontend (`BaseHTTPRequestHandler.log_message` is silenced
  specifically to stop the stdlib from printing the callback's raw query string, which contains the
  code).
- Credential provisioning boundary unchanged: `DRIVE_CREDENTIAL_PROVISIONING_REQUIRED` still fires
  if `%LOCALAPPDATA%\Sorigul\auth\google_oauth_client.json` is absent; no credential auto-discovery
  was added; nothing under `%LOCALAPPDATA%` was read by the build/release process.
- 9 new automated tests in `backend/tests/test_drive_oauth_loopback.py`, all against real
  `127.0.0.1` sockets (no external network): dynamic port allocation (two servers never collide),
  listener start-serve-one-request-then-stop, incorrect-state rejection without consuming the
  outcome, missing-code handling, callback timeout without hanging, duplicate-callback (only the
  first code is ever captured), no-code/token-in-logs (`capsys` assertion), and (via a
  `sys.modules`-stubbed `google_auth_oauthlib.flow.Flow`, since that package isn't installed in the
  dev venv) that `start()` wires the loopback `redirect_uri` into the real `authorization_url` and
  that a real callback automatically flips the service to `CONNECTED` with a token file written and
  the raw code never appearing in it.
- **Actual Google account login: NOT RUN** (no real credential, no real browser consent, per the
  work package's own explicit scope).

## Credential Provisioning Boundary

Unchanged and re-confirmed: no `credentials*.json`, `client_secret*.json`,
`google_oauth_client.json`, `google_drive_token.json`, or `token*.json` is tracked in git
(`git ls-files | grep -iE "credentials|client_secret|google_oauth_client|google_drive_token|token\.json|refresh_token"`
-> no matches). No such file was read from `%LOCALAPPDATA%` by any build script.

## Actual Google Smoke

NOT RUN.

## Actual Windows Shutdown

NOT RUN — destructive system action intentionally not executed.

## Code Signing

**Installer signing: UNSIGNED.** No code-signing certificate was purchased, generated, or otherwise
provisioned in this environment. **Known Risk:** installing or launching the unsigned MSI/exe may
trigger a Windows SmartScreen warning. This does not block Installer runtime-functionality PASS per
the work package's own instructions.

## Known Risks

- **One-file cold-start latency.** PyInstaller one-file re-extracts the ~230MB bundle to a temp
  directory on every launch; observed backend health-check latency after a fresh app launch was
  ~15-18s, inside the existing 20s Rust `wait_until_healthy` timeout but with limited margin on a
  slower disk. One-file did not prove technically infeasible (it built, ran, and passed every test
  performed against it), so no switch to `onedir` was made; a future pass could revisit `onedir` if
  cold-start latency becomes a real-world problem.
- **Orphaned backend on abnormal app termination.** Killing only the desktop app process (Task
  Manager "End Task", a crash, or any kill that bypasses `RunEvent::ExitRequested`) leaves the
  backend process running with port 8000 still bound -- verified empirically this pass. This is
  inherent Windows process behavior without Job Object supervision, not a regression introduced
  here; a future improvement could wrap the spawned child in a Job Object with
  `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`.
- **FFmpeg license notice not yet carried.** The bundled ffmpeg binary (via `imageio-ffmpeg`) is
  itself GPL/LGPL-licensed upstream, separately from `imageio-ffmpeg`'s own BSD-2-Clause wrapper;
  the installer does not yet surface FFmpeg's license/notice text (About screen or installed
  `NOTICE` file) -- a packaging-legal follow-up.
- **Unsigned installer** -- SmartScreen warning risk (see Code Signing).
- **PyInstaller build is not byte-reproducible run-to-run.** Two builds of identical source in this
  same session produced different SHA-256 values for `sorigul-backend.exe` (embedded
  timestamps/compression ordering, standard PyInstaller behavior) -- the SHA-256 recorded above is
  from the specific build that produced the recorded MSI, not a claim of bit-for-bit reproducibility
  across builds.
- **Interactive/visual verification gaps.** Folder picker, Explorer window, Tray menu clicks
  ("앱 열기"/"종료"), notification toast, and pixel-level Taskbar/Alt+Tab/Tray/Apps & Features icon
  confirmation were not re-driven or re-photographed this pass (no interactive display or UI
  automation harness in this unattended agent session) -- all of this code is unchanged from the
  prior two work packages, which recorded live manual PASS for the same surfaces. A human should
  still run through these once before a public release, per the same recommendation the prior work
  package made for its own interactive gaps.
- **`close_behavior = exit`'s live X-click path** was not independently re-driven this pass (requires
  navigating to Settings and toggling a checkbox before a `WM_CLOSE` test is representative); the
  default `close_behavior = tray` hide path *was* verified live via a real `WM_CLOSE` message.

## Deferred Full Parity Regression

- Actual Google account login / Drive upload.
- Actual Windows shutdown.
- Long real Local Whisper transcription and Direct Colab actual network transcription.
- Interactive folder-picker / Explorer / Tray-click / Notification-toast smoke (see Known Risks).
- Upgrade-version-bump simulation (deferred to an actual release version bump).
- Paid Windows code signing.

## Backend validation

- `python -m compileall backend/src backend/tests`: PASS.
- `pytest backend/tests -q`: **88 passed** (79 prior + 9 new OAuth loopback tests).
- `python -c "from src.main import app; print('PASS:', app.title)"`: `PASS: Sorigul Core Backend`.

## Frontend validation

- `npm run lint` (oxlint): PASS.
- `npm run typecheck` (`tsc -b --noEmit`): PASS.
- `npm run build`: PASS.

## Rust validation

- `cargo fmt --check`: PASS.
- `cargo check`: PASS (requires `frontend/src-tauri/binaries/{sorigul-backend.exe,ffmpeg.exe}` to be
  staged first -- confirms `bundle.resources` is genuinely wired, not just declared; see Tauri
  Resources above).
- `cargo clippy --all-targets -- -D warnings`: PASS.
- `cargo test`: **18 passed** (15 prior + 3 new for `packaged_spawn_spec_from_resource_dir`).

## Runtime artifact check

`git ls-files | grep -iE "jobs\.json|settings\.json|\.mp3$|\.srt$"` -> no matches. All QA-created
temp files (test folders under `%TEMP%`, the synthetic `%LOCALAPPDATA%\Sorigul\settings.json`) lived
entirely outside the repository and were removed after testing.

## Credential tracked check

`git ls-files | grep -iE "credentials|client_secret|google_oauth_client|google_drive_token|token\.json|refresh_token"`
-> no matches.

## git diff --check

Clean (no whitespace errors) across all changed/added files at commit time.

## UI Freeze changed?

No structural change (screens, navigation, layout untouched). The Google Drive card's interaction
was simplified (manual code-paste input/button removed, replaced by automatic polling) -- that card
itself was added by the prior Tauri Runtime work package, not part of the original frozen v1
four-screen baseline.

## Migration Contract changed?

No.

## Final Verdict

Every `Packaged Backend`, `Release Runtime`, `Installer`, `Windows`, and `Security`/`Git` REQUIRED
PASS item (per this work package's own PASS/BLOCKED criteria) was verified for real on this
machine: a genuinely standalone packaged backend with zero system-Python dependency, a real MSI that
clean-installs/reinstalls/uninstalls correctly via `msiexec`, bundled ffmpeg with no system-PATH
dependency, Korean/Unicode/space/long-path handling verified against the installed backend, and full
user-data preservation across reinstall and uninstall. The remaining gaps are exclusively
interactive/visual confirmations (folder picker, Explorer, Tray clicks, notification toast,
pixel-level icon photography) that this unattended agent session has no way to drive or observe, and
whose underlying code is unchanged from two prior work packages that already recorded live manual
PASS for them -- the same category of gap those prior work packages themselves called out rather
than papering over.

**INSTALLER / INSTALLED RUNTIME VALIDATION READY**
