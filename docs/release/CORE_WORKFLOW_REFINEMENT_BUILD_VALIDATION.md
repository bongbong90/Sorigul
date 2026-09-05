# Core Workflow Refinement — Phase 5B Build Validation

## Baseline

- Branch: `feature/core-workflow-refinement`
- Commit: `57b9d468253515b7989932ee67b49d1ca7be4d0e`

## Automated Regression

- Root release tests: 9 passed
- Backend full pytest: 219 passed
- Frontend lint: PASS, 1 existing warning
- Frontend typecheck: PASS
- Frontend build: PASS
- Rust cargo test: 24 passed

## Fresh Artifacts

| Artifact | Size (bytes) | SHA-256 |
| --- | ---: | --- |
| `sorigul-backend.exe` | 231018764 | `5311dc4ee2ecac3864dae124e1fd0d96922401f1a8144fe007e7de9979094a35` |
| `ffmpeg.exe` | 87638016 | `2ce797a0f88d7f067180338fb227f7b1928ea727bd9a4d7a1d022f7c52af71a3` |
| `Sorigul_0.1.0_x64_en-US.msi` | 262889472 | `7266ca15ce3f70ae52f93fe6870c84a28da1843902647eedfb438a6c864dc5fd` |

- Fresh sidecar build: PASS
- Fresh MSI build: PASS

## Sidecar Self-Test

PASS for all 8 reported items:

- `fastapi_app_import`
- `uvicorn_import`
- `google_drive_runtime_import`
- `whisper_import`
- `torch_import`
- `ffmpeg_availability`
- `audio_metadata_service_import`
- `runtime_path_initialization`

## Install

- Existing Sorigul installation before QA: NONE
- Pre-existing Sorigul runtime: NONE
- Install exit code: 0
- ProductCode: `{01D8ECB4-88C7-4B68-B45A-85B834542944}`
- DisplayVersion: `0.1.0`
- InstallLocation: `C:\Program Files\Sorigul\`
- Installed backend hash matches staged: YES
- Installed ffmpeg hash matches staged: YES
- Installed ffprobe: ABSENT
- Installed notices/licenses: PASS

## Installed Runtime

- Health: `GET /api/health` -> HTTP 200, `{"status":"ok"}`
- Cold start to health: 10.32 seconds
- Desktop path: `C:\Program Files\Sorigul\sorigul-desktop.exe`
- Backend path: `C:\Program Files\Sorigul\binaries\sorigul-backend.exe`
- Python descendant: NONE
- Backend console window: NONE (`MainWindowHandle=0`, empty title)
- QA `LOCALAPPDATA` isolation: PASS; used `TEMP\Sorigul_Phase5B_<guid>\LocalAppData`
- Actual user `LOCALAPPDATA` was not used
- Settings smoke: PASS; `shutdown=disabled`, valid `last_engine`, `drive_exam_root` present, no `drive_auto_upload` or `colab_url`

## Synthetic Scan

- Bundled ffmpeg synthetic 1-second silent MP3: PASS, exit code 0
- Korean path scan: PASS
- Spaces path scan: PASS
- Unicode/emoji path and filename scan: PASS
- Long path scan: PASS; folder path 267 characters, file path 274 characters
- `duration_seconds`: PASS; `1.08`, finite and greater than zero
- `/api/folders/scan`: PASS, HTTP 200
- Actual transcription: NOT RUN

## Job Object

- Forced desktop kill: PASS; QA desktop PID only was stopped
- Backend auto cleanup: PASS; both backend processes gone within 0.302 seconds
- Port 8000 release: PASS

## Uninstall

- Uninstall exit code: 0
- Program Files removed: YES
- Registry entry removed: YES
- Process residue: NONE
- Port residue: NONE
- QA temp cleanup: PASS

## External Gates

- Actual Local transcription: NOT RUN
- Actual Colab: NOT RUN
- Actual Drive: NOT RUN
- Actual OAuth: NOT RUN
- Actual Cloudflare: NOT RUN
- Actual user MP3: NOT TOUCHED
- Actual Windows shutdown/restart: NOT RUN

## Final Machine State

- QA Sorigul installation removed
- Production source changed: NO
- Tests changed: NO
- Scripts changed: NO
- Tauri Rust changed: NO
- Protected scratch: NOT TOUCHED
- `tunnel_log`: NOT TOUCHED / NOT STAGED