# Study Use Installed Synthetic Validation — 2026-09-28

## Verdict

**Issue #46 installed synthetic gate: PASS**

Validation source HEAD: `67fed29ffb5691a513f93beefb7ef00e4df3891f`

Validation branch: `test/study-use-installed-synthetic`

Pull request: #103

This pass used fresh artifacts from the validation source HEAD. No actual study
file, actual Colab execution, Drive upload, paid resource, or Windows shutdown
was used.

## Source and regression

The first Core build from prerequisite HEAD `d80a37b569d0ccd27faf11fe9dbac7e486cc0ea1`
found a PowerShell compatibility blocker. PowerShell 7 deserialized the integral
`core_sidecar_size_limit_mib` JSON value as `Int64`, while the scripts accepted
only the `Int32` representation used by Windows PowerShell. The failed candidate
was never promoted or reused.

Fix commit: `67fed29ffb5691a513f93beefb7ef00e4df3891f`
(`fix: accept PowerShell JSON integer widths`)

The fix accepts `Int32` or `Int64` while preserving the exact positive value
check in both the Core and installer gates.

Regression after the fix:

- focused packaging tests: 27 passed
- root release/readiness: 21 passed
- backend: 372 passed, 1 skipped
- frontend lint, typecheck, production build: PASS
- Rust fmt, check, clippy with warnings denied: PASS
- Rust tests: 38 passed
- PowerShell syntax: PASS
- `git diff --check`: PASS

## Fresh Local Runtime

Canonical prepared location:
`%LOCALAPPDATA%\Sorigul\runtime\local-whisper\v1`

| Property | Result |
|---|---|
| Build and atomic install | PASS |
| Executable size | 2,004,298,539 bytes (1,911.45 MiB) |
| Executable / worker SHA-256 | `7504ca7811434e5ba0d633135d445994585ca551a83891eb6b414148f34b302a` |
| `runtime_type` | `sorigul-local-whisper` |
| `runtime_version` | `1` |
| `protocol_version` | `1` |
| `torch_requirement` | exact scalar `torch==2.13.0+cu130` |
| `expected_cuda` | exact scalar `13.0` |
| `source_head` | `67fed29ffb5691a513f93beefb7ef00e4df3891f` |
| `tracked_tree_clean` | `true` |
| Manifest JSON round-trip | PASS |
| Manifest size/hash match | PASS |

The build-time and installed/prepared `--self-test` executions both returned
protocol 1, `ok=true`, `status=DONE`, and `device=cuda`. This covers torch import,
the pinned CUDA contract, a CUDA tensor allocation/compute/readback, clean exit,
and zero remaining Local worker processes.

## Fresh Core and size gate

The installer script builds and promotes its own isolated current-run Core
candidate. The values below are from that final candidate and match the
installed files.

| Artifact | Size | SHA-256 |
|---|---:|---|
| Core sidecar | 36,756,447 bytes (35.05 MiB) | `c106ddea7ab2e6989d284b2fb93630b6d9f5113f7a2f16f98f4a8d456fdab8b9` |
| FFmpeg | 87,638,016 bytes (83.58 MiB) | `2ce797a0f88d7f067180338fb227f7b1928ea727bd9a4d7a1d022f7c52af71a3` |
| Staged Core binaries | 124,394,463 bytes (118.63 MiB) | n/a (two-file set) |

Historical comparison:

| Measure | Historical | Fresh | Reduction |
|---|---:|---:|---:|
| Core sidecar | 1,928.62 MiB | 35.05 MiB | 1,893.57 MiB / 98.18% |
| Staged binaries | 2,012.63 MiB | 118.63 MiB | 1,894.00 MiB / 94.11% |
| MSI | 1,957.74 MiB | 66.81 MiB | 1,890.93 MiB / 96.59% |

Core sidecar and MSI are each below the 250 MiB policy ceiling.

The final installed Core PyInstaller archive contained 689 inventoried entries.
Entry-based checks found zero matches for torch, CUDA, cublas, cuDNN, cuFFT,
cuSPARSE, cuSOLVER, Whisper, numba, or llvmlite payloads. The installed program
directory contained eight expected Core/resource files and no Local Runtime,
Whisper model, or torch/CUDA payload.

## Fresh MSI and clean install

| Property | Result |
|---|---|
| MSI path | `frontend/src-tauri/target/release/bundle/msi/Sorigul_0.1.0_x64_en-US.msi` |
| MSI size | 70,053,888 bytes (66.81 MiB) |
| MSI SHA-256 | `0e623ba30ef6fd33b6b0736ca9e77b5107ffb5856d91437e24ed2a14beb33a90` |
| Source HEAD | `67fed29ffb5691a513f93beefb7ef00e4df3891f` |
| Local Runtime bundled | NO |
| Clean uninstall of prior registered product | PASS |
| Fresh install | PASS |
| Installed location | `C:\Program Files\Sorigul\` |
| Fresh ProductCode | `{2BA7F9F4-A5A4-4B96-89B3-49989810CD0B}` |

The initial silent uninstall attempt failed with MSI error 1730 because a silent
process could not display the required elevation prompt. No files or registry
keys were manually removed. Re-running the exact registered-product uninstall
through UAC elevation succeeded, left no product registration or install
directory, and the fresh MSI then installed successfully through the same
normal elevated Windows Installer path.

The installed Core sidecar, FFmpeg, and build manifest match the current-run
staged files and manifest exactly.

## Installed runtime validation

| Check | Result |
|---|---|
| Tauri desktop launch | PASS |
| Backend auto-start | PASS; PyInstaller bootloader + child |
| Backend ownership | PASS; desktop -> backend -> backend parent chain |
| Backend console hidden | PASS; zero backend window handles |
| `/api/health` | PASS; `status=ok` in 5.42 seconds |
| Expected installed Core executable | PASS |
| Bundled FFmpeg | PASS |
| System Python dependency | NONE; zero new `python.exe` |
| Vite/Node dependency | NONE; zero new `node.exe` |
| Core startup without Local Runtime | PASS in isolated empty app-data |
| Runtime discovery | PASS at the canonical versioned location |
| Core/Local source provenance | PASS; exact HEAD match |
| Installed CUDA synthetic | PASS; `device=cuda` |

The missing-runtime Core startup test used isolated empty app-data. The desktop,
backend, and health endpoint remained available without creating a Local Runtime.
No user's runtime or data was renamed or overwritten.

## Fail-closed Local Runtime fixtures

Controlled temporary fixtures exercised the same Local Runtime verification
contract while the installed Core health endpoint remained available:

| Fixture | Error code | Result |
|---|---|---|
| Missing runtime | `LOCAL_RUNTIME_MISSING` | PASS |
| Invalid JSON manifest | `LOCAL_RUNTIME_INVALID` | PASS |
| Wrong protocol | `LOCAL_RUNTIME_VERSION_MISMATCH` | PASS |
| Wrong artifact hash | `LOCAL_RUNTIME_INVALID` | PASS |
| Wrong source HEAD | `LOCAL_RUNTIME_PROVENANCE_MISMATCH` | PASS |

The canonical runtime was read for hash/provenance validation only. Negative
fixtures lived under a dedicated temporary directory and were removed.

## Unicode, filesystem, and FFmpeg synthetic

A dedicated temporary path containing Korean, spaces, and Unicode (`Ω`) was
used. Installed bundled FFmpeg generated a 0.20-second silent synthetic MP3,
and the installed backend discovered the exact Korean filename and full path,
reported duration metadata, and classified the intentionally output-less file
as incomplete. The temporary directory was removed afterward.

No actual study MP3, TXT, JSON, or SRT was read or modified.

## Cleanup, ownership, and port release

Forced-close Job Object validation killed only `sorigul-desktop.exe`. Windows
Job Object kill-on-close removed both owned backend processes and released port
8000 in 1.01 seconds. No desktop, backend, Local worker, listener, or orphan
remained.

Normal-close validation used isolated app-data with `close_behavior=exit`, the
canonical runtime executable exposed through a same-volume hard link, and a real
`WM_CLOSE`. The installed desktop's normal exit path removed desktop/backend
processes and released port 8000 in 1.12 seconds. The isolated app-data and hard
link were then removed.

Final process state:

- desktop: 0
- owned backend: 0
- Local worker: 0
- port 8000 listener: 0
- orphan: NONE

## Safety and not-run items

- User data touched: NO
- Actual study MP3: NOT RUN
- Long real lecture: NOT RUN
- Actual Colab network transcription: NOT RUN
- Actual Drive upload: NOT RUN
- Paid API/GPU/billing/fallback: NOT RUN
- Actual Windows shutdown: NOT RUN
- PR/main merge: NOT PERFORMED

## Final gate matrix

- FRESH LOCAL RUNTIME BUILD: PASS
- FRESH CORE BUILD: PASS
- CORE SIZE GATE: PASS
- CORE CONTENT GATE: PASS
- LOCAL CUDA SYNTHETIC: PASS
- FRESH MSI: PASS
- CLEAN INSTALL: PASS
- BACKEND AUTO-START: PASS
- HEALTH: PASS
- JOB OBJECT: PASS
- FFMPEG: PASS
- UNICODE SYNTHETIC: PASS
- LOCAL RUNTIME DISCOVERY: PASS
- PROVENANCE: PASS
- INSTALLED CUDA SYNTHETIC: PASS
- CLOSE CLEANUP: PASS
- PORT RELEASE: PASS
- ORPHAN: NONE
- NO USER DATA TOUCHED: PASS

**#46 INSTALLED SYNTHETIC GATE: PASS**

Next work unit: Phase 3 / Issue #47 actual Local Korean MP3 gate. It was not
started in this validation.
