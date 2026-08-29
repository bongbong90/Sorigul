# Sorigul Windows App Icon Branding

## Status

**WINDOWS APP ICON / BRANDING READY**

## Baseline

- Branch: `fix/windows-app-icon-branding`
- Parent HEAD: `c6652936768e35a86475181db48419235948f39e`
- Parent branch: `fix/tauri-runtime-smoke-closure`
- Tauri CLI: `2.9.4`

The existing tray registration and runtime lifecycle were verified before icon work began. No
Navigation, React layout, runtime architecture, sidecar, shutdown, OAuth, or Explorer-security
contract was changed by this work package.

## Canonical master decision

The canonical master for the Sorigul Native Windows App Icon is:

`docs/design/reference/app-icon-v1.png`

SHA-256:

`38ca2d8f0aec3409cf9a57f60ed86d26881eace76476803a05c4ffa7a8fab612`

This 1024 x 1024 PNG implements the approved brand contract: an audio waveform transitioning
into text lines in Quiet Teal. The source was used without background removal, color changes,
symbol changes, SVG reconstruction, or other redesign. It is the canonical source for the native
Window, Taskbar, Alt+Tab, EXE, Tray, and future Installer branding surfaces.

Lucide remains the UI functional icon system for Navigation, Action, and Status icons. Adopting
the native app icon does not add a symbol to the frozen React text-brand area.

## Placeholder root cause

The prior Tauri icon set was generated from a temporary solid `#3E6874` master and the temporary
source was then deleted. Every prior PNG contained exactly one fully opaque color, and every ICO
frame (16, 24, 32, 48, 64, and 256) contained the same single-color bitmap.

The khaki/solid-square result was therefore a wrong placeholder master asset issue. It was not a
Tauri configuration error, malformed ICO container, alpha-flattening defect, Windows rendering
problem, stale tray registration, or tray lifecycle defect.

## Tauri icon generation

The installed CLI syntax was checked with:

```text
cd frontend
npx tauri icon --help
```

The production assets were generated with the official Tauri v2 generator:

```text
cd frontend
npx tauri icon ..\docs\design\reference\app-icon-v1.png -o src-tauri\icons
```

The Windows work package retains the generated Windows files. The generator's unrelated iOS,
Android, and macOS outputs were not retained.

## Generated Windows assets

Standard application assets:

- `32x32.png`
- `64x64.png`
- `128x128.png`
- `128x128@2x.png` (256 x 256)
- `icon.png` (512 x 512)
- `icon.ico`

Windows Appx logo assets:

- `StoreLogo.png`
- `Square30x30Logo.png`
- `Square44x44Logo.png`
- `Square71x71Logo.png`
- `Square89x89Logo.png`
- `Square107x107Logo.png`
- `Square142x142Logo.png`
- `Square150x150Logo.png`
- `Square284x284Logo.png`
- `Square310x310Logo.png`

`icon.ico` is a real multi-resolution ICO with 16, 24, 32, 48, 64, and 256 pixel frames. Its
SHA-256 is `51897ca1c6fd9909f25deb44abea680fc20108ed19105164721d03dbff9d34f9`.
Every generated frame contains non-uniform waveform/text content. The source and generated assets
are fully opaque by approved design; alpha remains 255 throughout and was not flattened during
generation. At 16 and 24 pixels fine detail is softened, but the waveform-to-lines silhouette
remains present. No small-size redesign was applied.

## Tauri wiring

`tauri.conf.json` already referenced `icons/32x32.png`, `icons/128x128.png`,
`icons/128x128@2x.png`, and `icons/icon.ico` through the valid Tauri v2 `bundle.icon` field. No
schema or wiring change was necessary.

The native Window, Taskbar, and Alt+Tab surfaces use the generated default application/window
icon. Tray construction continues to use `app.default_window_icon()` from the same generated
source family. The proven `TrayIconBuilder` lifecycle and explicit `set_visible(true)` call were
not changed.

## Manual Windows verification

A fresh dev build was forced after removing only the crate's stale Cargo build output. A newly
compiled `target/debug/sorigul-desktop.exe` was then launched and verified in the live Windows
desktop session:

- Window title bar: Sorigul waveform-to-text icon, not a solid square.
- Taskbar: the same Sorigul icon, not a solid square.
- Alt+Tab: the Sorigul card displays the same icon.
- Tray notification overflow: the same icon is visible, not a solid square.
- `close_behavior=tray`: X hides the window while the app and owned backend remain alive.
- Tray menu: native `앱 열기` and `종료` items are present.
- Tray Open: shows and focuses the existing native window (same window handle).
- Tray Quit: closes the app and owned backend with no orphan process and releases port 8000.

The pre-existing user setting was `close_behavior=exit`; `tray` was used only for the lifecycle
smoke and the original setting was restored after verification.

No global Windows icon cache, Explorer cache, or user profile cache was deleted. Verification used
freshly rebuilt artifacts and fresh processes.

## No-bundle EXE verification

The installed Tauri CLI confirmed `--no-bundle` support. The executable was built without an MSI
or NSIS installer:

```text
cd frontend
npx tauri build --no-bundle
```

Verified artifact:

- Path: `frontend/src-tauri/target/release/sorigul-desktop.exe`
- Size: 4,604,928 bytes
- SHA-256: `25828288f89938eeb5d3350f28f25f4180867298d78e21bff615bc1ff35c79d6`
- Windows Explorer large-icon view: PASS
- Windows Properties dialog icon: PASS

The release artifact did not exist before this build, so the inspected EXE was the output of this
work package rather than a stale executable.

## Automated validation

- Backend compileall: PASS
- Backend pytest: `79 passed`
- Backend import smoke: `PASS: Sorigul Core Backend`
- Frontend lint: PASS
- Frontend typecheck: PASS
- Frontend production build: PASS
- Rust format check: PASS
- Rust check: PASS
- Rust clippy: PASS
- Rust tests: `15 passed`
- Git whitespace check: PASS

## Installer deferred verification

This work package intentionally did not create an installer. The following surfaces remain for the
Installer work package:

- Packaged release EXE within the final installer layout
- MSI and/or NSIS package icon
- Start Menu shortcut icon
- Desktop shortcut icon
- Apps & Features icon

## Known risks

- The approved source is fully opaque, so Windows displays its near-white square background. This
  is intentional under the canonical-source decision and was not altered.
- Fine waveform/text detail is naturally softened at 16 and 24 pixels, although the silhouette
  remains distinguishable.
- Windows may cache icons for a reused executable path. This verification avoided that ambiguity
  with a clean crate rebuild and a newly created release artifact; no user cache was deleted.
- Installer-specific icon propagation is deferred until an installer is produced.

## Final verdict

The canonical Sorigul source now feeds the generated Window, Taskbar, Alt+Tab, EXE, and Tray icon
pipeline, with native Windows smoke and full regression validation complete.

**WINDOWS APP ICON / BRANDING READY**
