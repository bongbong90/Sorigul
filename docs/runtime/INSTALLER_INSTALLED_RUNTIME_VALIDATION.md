# Installer / Installed Runtime Validation

## Status

**TAURI RUNTIME / INSTALLER WORKSTREAM 7 READY**

## Release Hardening Closure

The initial Installer / Installed Runtime Validation pass (below) found and disclosed three
release-hardening gaps rather than treating them as blockers: an orphaned-backend risk on abnormal
desktop termination, a thin packaged cold-start timeout margin, and a missing FFmpeg third-party
license/notice in the installer. This follow-up pass, on the same branch, closes all three:

1. **Orphan prevention (Windows Job Object).** `SidecarManager` now creates a Windows Job Object
   with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` for every owned spawn and assigns the (`CREATE_SUSPENDED`)
   child to it before resuming it, so the assignment can never race the child spawning its own
   grandchild. When Sorigul's own process is torn down by *any* means -- graceful exit, Task
   Manager "End Task", `taskkill /F`, a crash -- Windows itself closes the Job Object handle as
   part of that teardown, which (kill-on-close, sole handle) terminates every process in the job:
   the owned backend and the PyInstaller one-file bootloader's unpacked child alike. Verified for
   real on an installed MSI: killing only `sorigul-desktop.exe` (`Stop-Process -Force`, no `/T`)
   now clears both `sorigul-backend.exe` processes and releases port 8000 within ~0.5s, where the
   initial pass had measured them staying orphaned indefinitely. External/reused backends
   (`Connected { owned: false }`) are never assigned to a job and were re-confirmed to survive a
   forced desktop-app kill.
2. **Packaged cold-start timeout.** The packaged release's `wait_until_healthy` ceiling is now 60s
   (dev stays at 20s), with the same 400ms poll interval and the same early-return-on-success
   behavior -- a fast cold start still reports `Connected` in a few seconds; only the ceiling before
   a slow one is declared `STARTUP_TIMEOUT` changed. Fresh measurements this pass (see Cold Start
   below) landed at ~10.1-10.5s.
3. **FFmpeg third-party notices.** `third_party/THIRD_PARTY_NOTICES.txt` and
   `third_party/licenses/{ffmpeg-gpl-3.0.txt,imageio-ffmpeg-bsd-2-clause.txt}` are now bundled as
   Tauri resources and installed to `C:\Program Files\Sorigul\{THIRD_PARTY_NOTICES.txt,licenses\...}`.
   `scripts/build_windows_installer.ps1` now fails the build outright if any of these three files is
   missing, so a release installer can no longer ship the bundled (GPLv3, confirmed directly from
   the binary's own `-L` output, not assumed) ffmpeg without its license.

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
- Verified output (initial pass's build): `sorigul-backend.exe`, **230,654,187 bytes**,
  SHA-256 `6b064cf604437979d67ea57b11ff1b3531ee302ce2e5f7f5bdbf990892e65ec4` (PyInstaller output is
  not byte-reproducible run-to-run -- see MSI section for the Release Hardening Closure rebuild's
  own hash of the same source).
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
- **License, confirmed not assumed:** this exact bundled binary's own `ffmpeg -L` output states it
  was built with `--enable-gpl --enable-version3` and prints the GPLv3 notice directly --
  **GNU General Public License v3**, identified from the binary itself rather than guessed between
  GPL/LGPL. Build identity: `ffmpeg version 7.1-essentials_build-www.gyan.dev`
  (Gyan Doshi's Windows builds, https://www.gyan.dev/ffmpeg/builds/), unmodified.
- **Third-party notices now bundled and installed** (Release Hardening Closure item 3):
  `third_party/THIRD_PARTY_NOTICES.txt` plus `third_party/licenses/ffmpeg-gpl-3.0.txt` (the
  official GPLv3 text, downloaded verbatim from `https://www.gnu.org/licenses/gpl-3.0.txt`) and
  `third_party/licenses/imageio-ffmpeg-bsd-2-clause.txt` (copied verbatim from the installed
  package's own `dist-info/LICENSE`) are wired into `tauri.conf.json`'s `bundle.resources` and
  verified installed at `C:\Program Files\Sorigul\THIRD_PARTY_NOTICES.txt` and
  `C:\Program Files\Sorigul\licenses\*.txt`. The notice also records FFmpeg's public source
  locations (project + the exact Windows-build provider) as the GPLv3 §6(d) source-availability
  offer. `scripts/build_windows_installer.ps1` fails the build if any of these three files is
  missing.

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

## Cold Start

Packaged (`PACKAGED_STARTUP_TIMEOUT`) vs dev (`DEV_STARTUP_TIMEOUT`) health-wait ceilings are now
separate constants in `lib.rs`: dev stays at 20s, packaged is now 60s. `wait_until_healthy`'s
existing early-return-on-success behavior (poll every 400ms, return the instant health succeeds)
is unchanged, so this only raises the ceiling before a slow cold start is declared
`STARTUP_TIMEOUT` -- it does not make a fast happy path feel slower. Three fresh installed-app
launches this pass, each fully torn down (`sorigul-desktop.exe` + `sorigul-backend.exe` stopped)
before the next to force a genuine re-extraction:

| Run | Launch -> `/api/health` 200 |
|---|---|
| 1 | 10.52s |
| 2 | 10.10s |
| 3 | 10.10s |

**min 10.10s / max 10.52s / avg ~10.24s** -- comfortably inside the new 60s ceiling, with large
margin for a slower disk or antivirus real-time scanning than this measurement environment had.
(The initial pass had measured ~15-18s on the same kind of hardware; the exact figure varies run to
run with OS/disk cache state, which is precisely why a fixed ceiling needs real margin rather than
being tuned to a single measurement.)

Automated semantics for `wait_until_healthy`, all new this pass (`sidecar.rs`):
`wait_until_healthy_reports_connected_as_soon_as_health_succeeds_before_timeout` (health succeeding
partway through a generous timeout returns `Connected` in under 5s, not near the ceiling),
`wait_until_healthy_reports_startup_timeout_once_the_deadline_passes` (`StartupFailed("STARTUP_TIMEOUT")`
once a short deadline passes), and
`wait_until_healthy_reports_backend_exited_immediately_without_waiting_out_the_timeout` (a process
that exits on its own during startup is reported as `StartupFailed("BACKEND_EXITED_DURING_STARTUP...")`
within seconds, not at a 30s deadline).

## Windows Job Object (Orphan Prevention)

Release Hardening Closure item 1. `SidecarManager` (`sidecar.rs`) now:

1. Spawns the owned child with `CREATE_SUSPENDED` added to its existing `CREATE_NO_WINDOW` flag.
2. Creates a Windows Job Object (`CreateJobObjectW` + `SetInformationJobObject` with
   `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, via `windows-sys 0.60`) and assigns the still-suspended
   child to it (`AssignProcessToJobObject`) -- since the child has not executed a single instruction
   yet, this can never race the child spawning a grandchild before joining the job.
3. Resumes the child's thread(s) regardless of whether assignment succeeded (found via a
   `CreateToolhelp32Snapshot` thread walk + `OpenThread`/`ResumeThread`, since
   `std::process::Child` does not expose the `CreateProcessW` thread handle) -- a permanently
   suspended, unsupervised child would be strictly worse than an unsupervised running one.
4. The `JobObject` handle lives inside the same `OwnedProcess` struct as the `Child`; it closes
   (`CloseHandle`, in `Drop`) whenever that struct does -- both on the graceful `cleanup()` path
   (after `taskkill /T /F` has already terminated the tree, making the close a no-op) and, more
   importantly, whenever Windows tears down *our own* process's handles for any reason, which is
   exactly the kill-on-close trigger.

External/reused backends (`Connected { owned: false }`) are never wrapped in `spawn()` and so are
never assigned to a job -- the existing external-backend protection contract is unchanged.

**Automated tests (real processes, not mocked), all new this pass:**
- `job_object_kill_on_close_terminates_owned_process_when_handle_closes_without_cleanup` -- drops
  only the `JobObject` handle (never calling `cleanup()`'s `taskkill`) and confirms the owned
  process is terminated by the OS alone.
- `job_object_supervision_also_terminates_a_child_the_owned_process_spawns` -- the owned root spawns
  its own child process (mirroring the PyInstaller bootloader -> unpacked-child shape), and closing
  only the Job Object handle terminates both the root and that child, confirmed via a
  `Get-CimInstance Win32_Process -Filter "ParentProcessId=..."` lookup for the child's PID.

**Real installed-MSI forced-kill smoke (not a code-review-only pass):**
- Launched the installed app, confirmed `/api/health` 200 and both `sorigul-backend.exe` processes
  running from `C:\Program Files\Sorigul\binaries\`.
- `Stop-Process -Force` on **only** `sorigul-desktop.exe`'s PID (no tree flag, no touching the
  backend) -> within **~0.52s**, both `sorigul-backend.exe` processes were gone and `netstat` showed
  no `LISTENING` entry on port 8000 (only `TIME_WAIT` residue from already-closed connections).
  Under the initial pass's un-hardened build, the identical action left the backend orphaned and
  the port bound indefinitely -- this is the concrete before/after of Release Hardening Closure
  item 1.
- **External-backend protection re-confirmed live:** started a `sorigul-backend.exe` directly (not
  through Tauri), launched the installed app (which reuses it, `Connected { owned: false }`),
  force-killed the desktop app the same way, and confirmed the external backend **survived** and
  stayed healthy (`{"status":"ok"}`) afterward. Torn down separately by the QA session itself
  afterward, never by Sorigul.

## MSI

- Tauri CLI: `@tauri-apps/cli 2.9.4` (unchanged from the prior work package).
- Command, confirmed against `npx tauri build --help` (not guessed): `npx tauri build --bundles msi`.
- Artifact (Release Hardening Closure rebuild): `frontend/src-tauri/target/release/bundle/msi/Sorigul_0.1.0_x64_en-US.msi`.
- Size: **262,520,832 bytes**. SHA-256: `55cec14fcd7a067b87f95ff8897b471ff5b80912cacd6cd221aaf0978b5c5537`.
- Backend sidecar exe re-verified in this rebuild: **230,652,978 bytes**, SHA-256
  `faf23ee06abb5d71c3922db48129324a6a1b1ffa4aaa2712304e4150d894af85`; self-test 7/7 PASS again.
- Signed/unsigned: **UNSIGNED** (no certificate provisioned in this environment; see Code Signing
  below). WiX (`candle`/`light`) resolved and ran without any manual toolchain setup in this
  environment.
- Build fully automated via `scripts/build_windows_installer.ps1` (third-party notice check ->
  sidecar build + self-test -> frontend build -> `cargo fmt/check/clippy/test` ->
  `tauri build --bundles msi` -> artifact report), fails fast on the first non-zero exit at any
  stage.
- **ProductCode is not stable across rebuilds at the same version.** The initial pass's MSI had
  ProductCode `{BA01327D-ACB4-4747-A0D5-8BBC9A1452AC}`; this rebuild (still version `0.1.0`, WiX/Tauri
  mints a fresh ProductCode per build by default) produced `{E5AEE711-4CF5-4343-83D7-55F6DF4A4F09}`.
  Confirmed the hard way: an uninstall attempt using the previous ProductCode failed with
  `msiexec` exit code `1605` ("unknown product"); querying
  `HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*` for the current `DisplayName`
  before uninstalling is the reliable approach (also noted in Uninstall below).

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
- Health: `GET http://127.0.0.1:8000/api/health` -> `200 {"status":"ok"}`. See Cold Start below for
  this pass's timing measurements and the now-60s packaged timeout ceiling (Release Hardening
  Closure item 2).
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
  `/api/health` keeps responding -- correct (verified live in the initial pass, see Native UX).
- **Abnormal termination -- RESOLVED this pass.** The initial pass found that killing *only*
  `sorigul-desktop.exe` (no `/T`) left the backend orphaned indefinitely (inherent Windows behavior
  without Job Object supervision -- `RunEvent::ExitRequested`'s cleanup only runs on a *graceful*
  exit path and is never reached by a forced kill or a crash). This pass closes that gap with a
  Windows Job Object (`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, see the Windows Job Object section
  above) and re-verified the *same* forced-kill action live against a freshly installed MSI:
  backend + PyInstaller child both gone, port released, within ~0.52s.
- The graceful cleanup path itself (`SidecarManager::cleanup()`) is unchanged and remains covered by
  real (non-mocked) `cargo test`s that spawn an actual process and confirm its termination via
  `tasklist` (`cleanup_terminates_the_owned_process`) and that an unowned process survives cleanup
  (`cleanup_does_not_touch_an_unowned_external_process`).
- **External backend protection re-confirmed** under the *new* Job Object supervision specifically
  (not just the pre-existing `owned: false` logic): a backend started outside Tauri, then reused by
  the installed app, survives a forced kill of the desktop app -- see Windows Job Object section.

## Port Release

Verified live, both this pass and the initial pass: after the owned backend is terminated (via
graceful `cleanup()`'s `taskkill /T /F`, or now via Job Object kill-on-close on a forced kill),
`netstat` shows no `LISTENING` entry on port 8000 -- only transient `TIME_WAIT` entries from
already-closed connections, which the OS reclaims on its own.

## Settings Persistence

Verified live: `PUT /api/settings {"close_behavior":"exit"}` against the installed, running backend
persisted to `%LOCALAPPDATA%\Sorigul\settings.json`; the value was still present, unchanged, after a
full MSI reinstall (see Reinstall below). Job-state persistence was not separately exercised this
pass -- no pre-existing job history existed on this clean machine, and per the work package's own
instruction, a fresh job was not artificially created just to populate history (deferred to backend
regression / Full Parity Regression, which already covers `JobManager` persistence).

## Reinstall

Re-run this pass against the rebuilt MSI: `msiexec /i` against the same MSI file, while already
installed under the same ProductCode (`{E5AEE711-...}`, this build) -> **exit code 0**, log:
"Configuration completed successfully" (Windows Installer's expected repair/reconfigure path for an
identical ProductCode+version). `C:\Program Files\Sorigul\` and its resources, **including the
third-party notice files**, were intact afterward.

## Upgrade

**UPGRADE SCENARIO: DEFERRED TO RELEASE VERSION BUMP** -- not exercised via a temporary
`0.1.0 -> 0.1.1` override this pass. Not an Installer-READY blocker per the work package's own
instructions.

## Uninstall

`msiexec /x {ProductCode} /passive /norestart` -> **exit code 0**, log: "Removal completed
successfully." Verified afterward (this pass's rebuild):

- `C:\Program Files\Sorigul\`: removed -- **including** `THIRD_PARTY_NOTICES.txt` and `licenses\*.txt`.
- Process residue: none (`sorigul-desktop.exe`/`sorigul-backend.exe` both absent).
- Port residue: none (`netstat` showed no `LISTENING` entry on 8000).
- Registry: no `Sorigul` entry left under `HKLM:\...\Uninstall\*`.

**Operational note:** the MSI's ProductCode is not stable across rebuilds at the same product
version (see MSI section) -- an uninstall attempt using the *previous* build's ProductCode failed
with `msiexec` exit `1605` ("unknown product"); the fix was to query the registry for the
currently-installed `Sorigul` entry's actual `PSChildName` (ProductCode) rather than assume it. The
initial pass's clean-install/reinstall/uninstall cycle (with `%LOCALAPPDATA%\Sorigul\settings.json`
preservation across both) is unaffected by and separate from this pass's rebuild-and-reinstall
cycle; both confirmed the same user-data-preservation contract.

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

Resolved by the Release Hardening Closure pass (kept here per instruction, not deleted, with the
resolution noted rather than the finding erased):

- ~~Orphaned backend on abnormal app termination.~~ **RESOLVED**: initial pass found killing only
  the desktop process left the backend orphaned indefinitely; this pass adds Windows Job Object
  kill-on-close supervision and re-verified the identical forced-kill action now cleans up within
  ~0.52s (see Windows Job Object section).
- ~~Thin packaged cold-start timeout margin.~~ **RESOLVED**: packaged timeout raised from 20s to
  60s, dev unchanged at 20s; happy-path latency (measured ~10.1-10.5s this pass) is unaffected since
  `wait_until_healthy` already returns immediately on success.
- ~~FFmpeg license notice not yet carried.~~ **RESOLVED**: `THIRD_PARTY_NOTICES.txt` and the two
  license files are now bundled Tauri resources, installed alongside the app, and their presence is
  a hard build-time requirement in `build_windows_installer.ps1`.

Still open:

- **Unsigned installer** -- SmartScreen warning risk (see Code Signing).
- **PyInstaller build is not byte-reproducible run-to-run.** Multiple builds of identical source
  across this project's two validation passes produced different SHA-256 values for
  `sorigul-backend.exe` and the MSI (embedded timestamps/compression ordering, standard PyInstaller
  and WiX behavior) -- the SHA-256 values recorded above are from the specific build that produced
  the artifact tested in that same pass, not a claim of bit-for-bit reproducibility across builds.
- **MSI ProductCode is not stable across rebuilds at the same product version** (new finding this
  pass -- see MSI/Uninstall sections). Any future automation that uninstalls-by-ProductCode must
  query the registry for the currently-installed entry rather than hardcode a value from a prior
  build.
- **Interactive/visual verification gaps.** Folder picker, Explorer window, Tray menu clicks
  ("앱 열기"/"종료"), notification toast, and pixel-level Taskbar/Alt+Tab/Tray/Apps & Features icon
  confirmation were not re-driven or re-photographed in either pass (no interactive display or UI
  automation harness in this unattended agent session) -- all of this code is unchanged from the
  prior two work packages, which recorded live manual PASS for the same surfaces. A human should
  still run through these once before a public release, per the same recommendation the prior work
  package made for its own interactive gaps.
- **`close_behavior = exit`'s live X-click path** was not independently re-driven in either pass
  (requires navigating to Settings and toggling a checkbox before a `WM_CLOSE` test is
  representative); the default `close_behavior = tray` hide path *was* verified live via a real
  `WM_CLOSE` message in the initial pass.
- **Job Object assignment happens after `CreateProcessW`, not fully atomically with it.** The child
  is created `CREATE_SUSPENDED` and assigned to the job before its first instruction ever runs, so
  it cannot itself spawn a grandchild before joining -- but the window between `Command::spawn()`
  returning and this project's own `AssignProcessToJobObject` call is not literally zero. This was a
  deliberate choice over reimplementing `CreateProcessW`/argument-quoting/environment-block
  construction by hand (a larger unsafe-code surface for a race this design already closes to
  "before the child's own first instruction," which a suspended process cannot exploit to spawn
  anything).

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
- `cargo test`: **24 passed** (18 from the initial installer pass + 6 new this pass: 2 Windows Job
  Object tests + 3 `wait_until_healthy` timeout-semantics tests + 1 `cleanup_is_safe_to_call_twice_in_a_row`).

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

The initial Installer / Installed Runtime Validation pass verified a genuinely standalone packaged
backend with zero system-Python dependency, a real MSI that clean-installs/reinstalls/uninstalls
correctly via `msiexec`, bundled ffmpeg with no system-PATH dependency, and Korean/Unicode/space/
long-path handling against the installed backend -- but disclosed, rather than hid, three
release-hardening gaps: an orphaned-backend risk on abnormal termination, a thin packaged
cold-start timeout margin, and a missing FFmpeg license/notice. This Release Hardening Closure pass
verified all three fixes for real on the same machine: a forced kill of only the installed desktop
process now cleans up the owned backend (and its PyInstaller child) via a Windows Job Object within
~0.52s where it previously left them orphaned indefinitely; external/reused backends were
re-confirmed to survive that same forced kill; the packaged startup ceiling is now 60s against a
measured ~10.1-10.5s real cold start; and the bundled ffmpeg's actual GPLv3 license (confirmed from
the binary itself, not assumed) plus imageio-ffmpeg's BSD-2-Clause license are now installed
alongside the app, with the build failing outright if either is missing. Every required Backend,
Frontend, and Rust regression re-passed (88 / lint+typecheck+build / 24), and a fresh MSI rebuilt
with all three fixes clean-installed, reinstalled, and uninstalled correctly, with the installed
license files removed together with the rest of the program on uninstall.

The remaining gaps are unchanged from the initial pass and are exclusively interactive/visual
confirmations (folder picker, Explorer, Tray clicks, notification toast, pixel-level icon
photography) that this unattended agent session has no way to drive or observe, whose underlying
code is untouched by either pass and was already recorded as live manual PASS in the two work
packages before this one.

**TAURI RUNTIME / INSTALLER WORKSTREAM 7 READY**
