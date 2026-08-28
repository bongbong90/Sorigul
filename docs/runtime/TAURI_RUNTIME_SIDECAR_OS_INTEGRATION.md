# Tauri Runtime / Sidecar / OS Integration

## Baseline

- Branch: `feature/tauri-runtime-sidecar-os-integration`, created from `feature/drive-results-desktop-ux` at `2c8b7e5`
- UI Freeze v1: `LOCKED` (no navigation, screen, or action changes)
- Migration Contract: unchanged
- Shutdown policy (batch_completed / STOPPED / CANCELLED / CRASHED / fatal / Drive-independent): unchanged, reused as-is

## Tauri version

- `@tauri-apps/cli` `2.9.4`, `tauri` (Rust crate) `2.11.5`, `tauri-build` `2.6.3` (Cargo.lock-resolved; `Cargo.toml`/`package.json` pin the `2` major only, consistent with the rest of the project's dependency style)
- Plugins: `tauri-plugin-dialog` `2.7.2`, `tauri-plugin-notification` `2.3.3`, `tauri-plugin-opener` `2.5.4` (JS: `@tauri-apps/api` `2.11.1` + matching plugin packages)
- v2 APIs only; no v1 API used anywhere
- `tauri-plugin-shell` was intentionally **not** added. The sidecar process is spawned entirely from Rust (`std::process::Command`), never from JS, so the frontend needs no shell/process-execution capability at all.

## Runtime architecture

The existing React UI (`frontend/src`) is unchanged in structure and is wrapped, not replaced: `frontend/src-tauri` is a new Tauri shell around the same Vite build (`frontendDist: "../dist"`, dev at `devUrl: "http://localhost:5173"`). No UI was rebuilt or duplicated.

```
frontend/src-tauri/
  Cargo.toml, build.rs, tauri.conf.json
  capabilities/default.json   -- minimal permission set
  icons/                      -- generated via `tauri icon` from a brand-color placeholder
  src/
    main.rs                   -- entry point, suppresses console subsystem in release
    lib.rs                    -- app builder: plugins, tray, window-close policy, commands
    sidecar.rs                -- backend process lifecycle (unit-testable, Tauri-independent)
    shutdown.rs                -- native shutdown executor + idempotent gate (unit-testable)
```

`sidecar.rs` and `shutdown.rs` depend only on `std` (+ `ureq` for the health probe) and expose trait seams (`HealthProbe`, `ShutdownExecutor`) specifically so their ownership/duplicate-spawn/idempotence rules are covered by `cargo test`, independent of a running Tauri app or a real backend process.

## Dev vs packaged backend launch

Both paths hit the same product API (`backend/src/main.py`'s FastAPI app on `127.0.0.1:8000`); only how the process is started differs, selected via `cfg!(debug_assertions)`:

- **Dev** (`cargo run` / `tauri dev`): spawns `python -m uvicorn src.main:app --host 127.0.0.1 --port 8000` with `current_dir` set to `backend/` (resolved from `CARGO_MANIFEST_DIR` at compile time, so it doesn't depend on the process's runtime CWD). Python executable resolution order: `SORIGUL_BACKEND_PYTHON` env override -> `<repo>/venv/Scripts/python.exe` if present -> `python` on `PATH`.
- **Packaged**: resolves `sorigul-backend.exe` under the bundle's resource directory (`app.path().resource_dir()/binaries/sorigul-backend.exe`) and spawns it with `--port 8000`. **The standalone backend binary itself is not built by this work package** -- see Packaging decision required below.

The frontend's existing API boundary (`frontend/src/api/client.ts`, `VITE_BACKEND_URL`) is untouched; Tauri only makes sure something is listening on that URL before the user needs it.

## Backend ownership

`SidecarManager::start()` runs a pre-flight health probe (`GET /api/health`, expects `{"status":"ok"}`) before doing anything:

| Probe result | Action |
|---|---|
| Healthy | Reuse it. Do not spawn. Marked `owned = false`, never touched again. |
| Responds, but not our payload | `StartupFailed("PORT_OCCUPIED_BY_OTHER_SERVICE")`. Never spawn, never kill. |
| Unreachable | Spawn our own child, marked `owned = true`. |

A second `start()` call while a process is already owned (or already reused externally) is a no-op -- it neither re-probes nor re-spawns (`duplicate_start_does_not_spawn_a_second_process` test). Nothing is ever killed by guessing a PID; `cleanup()` only ever acts on the `Child` handle this process itself created via `spawn()`.

## Health / startup / reconnect

After a successful spawn, `wait_until_healthy()` polls the same health probe every 400ms up to a 20s timeout, and separately watches the owned child via `try_wait()` so a crash *during* startup is reported as `BACKEND_EXITED_DURING_STARTUP` rather than silently timing out. The final status is emitted as a `sorigul://sidecar-status` Tauri event (for future diagnostics; not currently consumed by the frontend).

The frontend's existing offline/reconnect UX (`TranscriptionPage`/`SettingsPage`'s `api.health()` polling, `BackendStatus` state) is **unchanged** -- it already treats "can't reach `/api/health`" as OFFLINE regardless of cause, which is exactly correct whether the cause is "backend still starting", "backend crashed", or "backend never started". No 100ms-scale polling was introduced anywhere (existing cadences: 1s health, 4s events/log, 4s notifications).

## Process cleanup / orphan prevention / port handling

Cleanup runs from exactly one place -- `RunEvent::ExitRequested` in `lib.rs::run()` -- reached by every legitimate exit path (tray "종료", or the last window closing with `close_behavior = exit`), so cleanup logic isn't duplicated or racy across handlers. `SidecarManager::cleanup()`:

- is a no-op if nothing is owned (reused-external case), and idempotent if called after an owned process is already gone;
- on Windows, kills the owned process **and its child tree** via `taskkill.exe /PID <pid> /T /F` (fixed executable + fixed argument list, no shell string concatenation -- same discipline as the shutdown executor) rather than a single-process `kill()`, since `uvicorn`/Python can spawn workers;
- reaps the process afterward (`child.wait()`).

Port release relies on the OS reclaiming the port once the owned process (and any of its children) actually exit; Tauri itself never binds the port.

Verified with real spawned processes in `sidecar.rs` tests (not mocked): `cleanup_terminates_the_owned_process` confirms the PID is gone from `tasklist` after cleanup; `cleanup_does_not_touch_an_unowned_external_process` spawns an unrelated process the manager never adopted and asserts it survives an unowned `cleanup()` call.

## Console visibility

- The owned backend child is spawned with `CREATE_NO_WINDOW` (Windows-only `creation_flags`) and `Stdio::null()` on all three streams, so no console window appears for it in dev or packaged builds.
- The app's own process is compiled with `#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]` in `main.rs`, so packaged (release) builds have no console of their own either; dev builds keep the console for logs.

## Native Folder Picker

`frontend/src/lib/native.ts` exports `pickFolder()`: under Tauri, opens the native Windows folder picker (`@tauri-apps/plugin-dialog`'s `open({ directory: true })`); outside Tauri (plain browser dev), falls back to the pre-existing `window.prompt`. Cancelling the picker resolves to `undefined` and is treated as a no-op, not an error, in both `TranscriptionPage.tsx` and `FoldersPage.tsx`'s `changeFolder()`. Korean/Unicode/space/long-name paths pass through unmodified (no manual path parsing on the Rust or JS side); the selected path is handed to the existing `api.scan()` boundary exactly as the old prompt-entered value was.

## Explorer open

`FoldersPage.tsx`'s `requestOpenFolder()` still calls the existing backend `POST /folders/{scan_id}/open-intent`, which returns a **server-validated** `{ folder, item_filename? }` (root re-validated under the scanned directory; `item_filename` is a bare basename, never a path). Under Tauri, `native.ts`'s `openInExplorer()` passes that value straight to `@tauri-apps/plugin-opener`'s `openPath()` (folder only) or `revealItemInDir()` (folder + highlighted file) -- the frontend never constructs or accepts an arbitrary path itself. No `os.startfile()` or any other Explorer-launching code was added to the Python backend.

## Notification

`frontend/src/hooks/useDesktopNotifications.ts`, mounted once at the app root (`App.tsx`) so it works regardless of the active page:

- Polls the existing `GET /api/events` every 4s (same order of magnitude as the existing Log page poll).
- The backend already only appends `FILE_COMPLETED` / `JOB_COMPLETED` application events when `notifications.file_complete` / `notifications.job_complete` is enabled (`desktop_state.py`, unchanged) -- so "setting OFF" is enforced at the source and the hook needs no separate settings check.
- Dedupe: on the very first poll after mount, all currently-present relevant events are recorded as "seen" without notifying (avoids a notification burst from history/a reused backend); every poll after that only notifies for event keys (`intent|job_id|timestamp|message`) not seen before.
- Notification body is the backend's existing short Korean user message (e.g. "파일 전사 완료: {filename}") -- never a raw traceback, path, or token.
- Requests the OS notification permission once, lazily, only the first time it actually has something to send.
- No Python toast library was added; the OS notification call (`@tauri-apps/plugin-notification`'s `sendNotification`) happens entirely in the JS/Tauri layer.

## Tray

Built once in `lib.rs::build_tray()` during `setup()` (never re-built, so no duplicate icons): one `TrayIconBuilder` with a 2-item menu ("앱 열기" / "종료"), using the app's configured window icon.

- **앱 열기**: shows and focuses the `main` window.
- **종료**: always performs a real exit -- owned-backend cleanup, then `app.exit(0)` -- regardless of the current `close_behavior` setting (matches the contract: Quit always quits).
- **close_behavior = tray**: the window's `CloseRequested` handler calls `api.prevent_close()` and hides the window; the backend keeps running.
- **close_behavior = exit**: the handler does not prevent the close; the run loop's `RunEvent::ExitRequested` performs cleanup as the window (and app) actually close.

`close_behavior` itself stays backend-owned (`GET/PUT /api/settings`, unchanged); Rust just caches the last-saved value (`set_close_behavior` command, invoked from `SettingsPage.tsx` whenever settings load or save) so the close handler never has to make a blocking HTTP call.

## Shutdown native boundary

`backend`'s existing state machine (`inactive` / `counting_down` / `cancelled` / `ready_to_shutdown`, `batch_completed`-based eligibility) is **unmodified**. `SettingsPage.tsx` adds one effect: when polling reports `ready_to_shutdown` and hasn't already triggered for this cycle, it re-reads `GET /api/desktop/shutdown` once more (closes the poll-race window where a stale in-flight response could still say `ready_to_shutdown` just after a cancel) and only then calls the `native_shutdown` Tauri command if that fresh read still says `ready_to_shutdown`.

`shutdown.rs`:

- `RealShutdownExecutor`: fixed executable (`shutdown.exe`) + fixed arguments (`/s /t 0`) only -- no string built from user/network input ever reaches the command line, matching the same `CREATE_NO_WINDOW` + argv-array discipline as the sidecar's `taskkill` call.
- `ShutdownGate`: an atomic "has this cycle already executed" guard. `trigger()` calls the executor at most once per cycle no matter how many times it's called (duplicate polling, a stale ready event, etc.); `reset()` (invoked via the `reset_shutdown_gate` command whenever the frontend observes the phase leave `counting_down`/`ready_to_shutdown`, e.g. on cancel) re-arms it for the next countdown.
- `ShutdownExecutor` is a trait specifically so `cargo test` exercises the gate/idempotence logic through a `CountingExecutor` fake -- **no test ever calls the real Windows shutdown command.**

## Shutdown cancel race safety

Two independent layers, per the explicit "polling race" requirement:

1. **Frontend**: before invoking `native_shutdown`, re-confirms with a fresh `GET /api/desktop/shutdown`; a `useRef` guard prevents firing more than once per observed `ready_to_shutdown`; the guard resets (and calls `reset_shutdown_gate`) once the phase is observed to be `inactive` or `cancelled`.
2. **Native (Rust)**: `ShutdownGate` makes the executor call idempotent regardless of how many times or from how many stale IPC calls `native_shutdown` is invoked in one cycle.

## OAuth Desktop handoff

Backend contract unchanged: scope `https://www.googleapis.com/auth/drive`, token at `%LOCALAPPDATA%\Sorigul\auth\google_drive_token.json`, `POST /api/drive/auth/start` / `POST /api/drive/auth/complete` (`backend/src/services/drive.py`, not modified).

What this work package connects: `SettingsPage.tsx` gained a minimal "Google Drive" card (auth-state badge from `GET /api/drive/status`, a "Google Drive 연결" button). Under Tauri, clicking it calls the existing `start` endpoint and opens the returned `authorization_url` in the system's default browser via `native.ts`'s `openInBrowser()` (`@tauri-apps/plugin-opener`'s `openUrl`) -- no embedded webview, no secret ever touches the frontend.

**Automatic callback capture is deferred (PACKAGING DECISION REQUIRED).** The backend's OAuth flow uses a fixed `redirect_uri` of `http://127.0.0.1` (no port, i.e. port 80), which on Windows requires either elevated privileges or an installer-time reservation (`netsh http add urlacl` or similar) to bind reliably -- an installer/packaging decision, not something this runtime work package should silently assume. Until that's decided, the completion side of the handoff is a manual step: the browser will fail to load `http://127.0.0.1/?code=...`, but the `code` is visible in its address bar; the user pastes it into the new Settings card, which calls the existing `complete` endpoint. This keeps the boundary genuinely connected (browser opens for real, completion endpoint is exercised for real) without inventing a fragile privileged listener under a schedule that explicitly defers packaging decisions.

No OAuth secret, client credential path, or token is ever sent to the frontend or logged; `actual Google OAuth smoke: NOT RUN` (requires a real Google account and explicit user approval, out of scope for an automated pass).

## Unicode / Windows paths

No path is parsed, rebuilt, or transcoded across any boundary in this work package -- the picker's selection, the backend's validated `folder`/`item_filename`, and the sidecar's `current_dir` are all passed through as opaque OS strings (Rust `String`/`PathBuf`, JS `string`, Python `str`/`Path`) with a single owner each. `openInExplorer()`'s only string manipulation is appending a `\` separator when joining `folder` + `item_filename` for `revealItemInDir`, and both halves are already backend-validated.

## Security / capabilities

`capabilities/default.json` grants exactly:

- `core:default` + `core:window:allow-show` / `allow-hide` / `allow-set-focus` (tray open/close-to-tray)
- `dialog:allow-open` (folder picker only -- not the broader `dialog:default`, which also covers save/message/confirm dialogs this app never uses)
- `opener:allow-open-url`, `opener:allow-open-path`, `opener:allow-reveal-item-in-dir` (OAuth browser handoff, folder open, file reveal -- not blanket `opener:default`)
- `notification:default` (the plugin's own scope; nothing broader)

No shell/process-execution permission exists in any capability file (the shell plugin isn't even a dependency -- see Tauri version above). No filesystem-scope permission (`fs:*`) is granted at all; the app never reads/writes files through Tauri's FS layer -- all filesystem access stays in the Python backend, exactly as before.

## Tests

**Rust** (`cargo test`, all in `frontend/src-tauri/src/{sidecar,shutdown}.rs`), 10 tests, all passing, no destructive OS side effects:

- Sidecar: reuse-when-healthy (no spawn), port-conflict startup failure (no spawn), spawn-and-own-when-unreachable, duplicate `start()` doesn't re-spawn, cleanup terminates the owned process (verified via `tasklist`), cleanup leaves an unrelated/unowned process running (verified via `tasklist`).
- Shutdown: executor fires on first trigger, is idempotent across duplicate triggers, `reset()` re-arms it for a new cycle, a fresh gate reports not-yet-executed. All against a `CountingExecutor` fake -- never `RealShutdownExecutor`.

**Backend**: unchanged this pass; re-run for regression (79 passed, same as the prior work package -- no backend source was touched).

**Frontend**: no new automated test files were added (this project has no existing frontend test runner configured); coverage for the new folder-picker/notification/shutdown-trigger/Drive-card logic was validated via `tsc` typecheck + `oxlint` + production build, consistent with this repo's existing frontend validation approach.

## Actual OS smoke results

- **Windows shutdown**: `NOT RUN` -- verified exclusively via the `ShutdownGate`/`CountingExecutor` unit tests above; the real `shutdown.exe /s /t 0` was never invoked.
- **Google OAuth login**: `NOT RUN` -- requires a real Google account and explicit user approval.
- **Interactive Tauri `dev` desktop smoke** (window opens, tray hides/shows, native folder picker dialog appears, etc.): `NOT RUN` in this pass -- this is an unattended agent session with no interactive display to drive/observe a GUI app opening a real window, so no launch was attempted rather than guessing at a result. Compilation, unit tests, and `cargo check`/`clippy`/`fmt` stand in as the automated verification; a human should run `npm run tauri dev` once to confirm the window/tray/picker visually before this ships.

## Deferred Installer work

- MSI/NSIS bundling (`tauri build`) was not run; `tauri.conf.json` declares `bundle.targets: ["msi", "nsis"]` but no installer was produced.
- Clean install / reinstall / upgrade / uninstall-residue validation.
- GitHub Release / external distribution.

## Packaging decision required

1. **Backend sidecar binary.** The packaged launch path (`packaged_spawn_spec` in `lib.rs`) expects a standalone `sorigul-backend.exe` under the bundle's resource directory; producing that binary (PyInstaller or equivalent) and wiring it back into `tauri.conf.json`'s `bundle.externalBin` is not done here (declaring `externalBin` without the file present fails even `cargo check`, so it's deliberately left undeclared until the binary exists).
2. **OAuth callback loopback listener.** The fixed `redirect_uri = http://127.0.0.1` (port 80) needs a decision on how a packaged installer reserves/binds that port (or on changing the redirect URI, which would be a Drive-contract change out of this work package's scope) before automatic callback capture can replace the manual code-paste fallback.
3. **OAuth client credential provisioning** into `%LOCALAPPDATA%\Sorigul\auth\google_oauth_client.json` for a packaged build (unchanged from the prior work package's deferral).

## Known risks

- The manual OAuth code-paste fallback is more friction than an automatic callback and depends on the user correctly copying the `code` query parameter out of a browser address bar that shows a failed page load.
- `packaged_spawn_spec`'s resource path is unexercised by any test (no packaged build was produced this pass); it should be smoke-tested once a real `tauri build` + sidecar binary exist.
- Icons are a solid-brand-color placeholder generated for this pass (`icons/source-icon.png` was deleted after generation), not final design assets.

## Final verdict

All in-scope automated checks (Rust compile/test/fmt/clippy, backend regression, frontend typecheck/lint/build, whitespace, credential/runtime-artifact scan) passed; the two items requiring a live GUI/browser/Windows-shutdown are explicitly `NOT RUN` and called out above rather than assumed.

`TAURI RUNTIME / SIDECAR / OS INTEGRATION READY`
