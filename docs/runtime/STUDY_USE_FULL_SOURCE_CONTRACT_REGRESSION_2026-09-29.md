# Study-Use Full Source Contract Regression — 2026-09-29 (5F)

Issue: #123 · Branch: `audit/full-source-contract-regression` · Parent PR: #121 (OPEN, not merged)

This is an **audit-only** work unit. No backend, frontend, Rust, installer, or dependency source was changed. Every independent defect found here was filed as its own Issue and left for a separate work unit.

## 1. Fixed inputs

| Item | Value |
|---|---|
| Source HEAD audited | `71d6920f2ded69868c877916af3095130099e838` (`fix/live-folder-change-detection`, after #106/#110/#111) |
| Legacy baseline | `bongbong90/jeonsa_doumi@fbc86313a179a62a586386551f99384a9fce5fc8` (`main`, verified via GitHub API) |
| Canonical contract | `docs/project/CURRENT_PRODUCT_CONTRACT.md` (LOCKED) + supersession map |
| Completion plan | `docs/project/SORIGUL_FULL_LEGACY_PARITY_COMPLETION_PLAN_2026-09-28.md` |
| Evidence routing | `docs/project/CURRENT_SOURCE_OF_TRUTH.md`, `docs/project/DEVELOPMENT_RULES.md` |
| Decision provenance consulted | `docs/migration/CORE_WORKFLOW_REFINEMENT_PLAN.md` (D11+), `docs/project/MIGRATION_CONTRACT.md` §10, `docs/project/LEGACY_FEATURE_PARITY_AUDIT.md` (historical) |

Historical documents were used only as evidence. None was promoted to current contract.

## 2. Legacy repository-wide inventory methodology

1. The Legacy repository was cloned read-only into a scratch directory **outside** this repository and checked out at the baseline commit. No Legacy source was copied or imported into Sorigul. The only Legacy code executed was `filename_normalizer.py`, run from the scratch clone as comparison evidence (§6).
2. All **337** tracked files (`git ls-files`) were enumerated. Each file received a category and one of `ACTIVE / SUPPORTING / DEPRECATED / ARCHIVED / EXPERIMENTAL / UNKNOWN`. The full per-file table is in [`STUDY_USE_FULL_SOURCE_CONTRACT_REGRESSION_2026-09-29_LEGACY_INVENTORY.md`](STUDY_USE_FULL_SOURCE_CONTRACT_REGRESSION_2026-09-29_LEGACY_INVENTORY.md).
3. Classification followed the **call graph**, not file names:
   - `gui_main.py` imports and `connect()` wiring (458 functions/methods enumerated);
   - `auto_transcribe.py` worker entry;
   - the `backend/main.py` router registration of the Phase 23 Tauri/FastAPI MSI.
4. Legacy had **two ACTIVE runtimes** at the baseline:
   - the PySide v0.9.0 application (`gui_main.py` + `auto_transcribe.py` + `filename_normalizer.py` + Drive uploaders + Colab notebook), which carries the full feature set;
   - the Phase 23 Tauri + FastAPI MSI (`frontend-tauri/`, `backend/`), a released subset.
5. UNKNOWN candidates were investigated until resolved. For example, the Phase 2 backup service/routes are a no-op stub, so they were classified EXPERIMENTAL. **UNKNOWN remaining: 0.**
6. Every user-visible capability was then re-extracted from the ACTIVE code paths, independently of the old 43-item audit, and diffed against it (§5).

| Classification | Files |
|---|---|
| ACTIVE | 58 |
| SUPPORTING | 201 |
| DEPRECATED | 30 (Drive Queue modules, probes, and guard) |
| ARCHIVED | 26 (old backups, icon POC, Drive Queue design docs) |
| EXPERIMENTAL | 22 (Colab CLI/WSL research, backup stub, Tauri Direct Colab path, filename preview stub) |
| UNKNOWN | 0 |

The Tray/notification/shutdown and Folders/results categories have no files of their own. Those capabilities live inside `gui_main.py`, so they were extracted at method level (§4).

## 3. Legend

- **Classification:**
  - `PRESERVED`: current source materially implements the Legacy ACTIVE behavior.
  - `APPROVED_INTENTIONAL_CHANGE`: differs by an approved decision (contract §5, §7, §8).
  - `DEPRECATED_EXCLUDED`: not ACTIVE, or excluded by contract §6.
  - `VALIDATION_ONLY_PENDING`: source is present, but the behavior can only be proven installed or externally.
  - `CONFIRMED_DEFECT`: an Issue was filed.
  - `AMBIGUOUS`: needs a user decision; an Issue was filed.
- **Validation state:**
  - `SOURCE PASS`: inspected, and covered by the tests in §10 where tests exist.
  - `PENDING INSTALLED #n` / `PENDING EXTERNAL #n`: evidence at the named gate is still missing.

## 4. Full capability matrix

Legacy references abbreviate `gui_main.py` as `gm`, `auto_transcribe.py` as `at`, and `filename_normalizer.py` as `fn`.

### 4.1 File workflow / queue

| # | Area | Legacy evidence | Legacy behavior | Current contract | Current Sorigul evidence | Classification | Issue | Validation state | Notes |
|---|---|---|---|---|---|---|---|---|---|
| 1 | File/folder selection | `gm::select_target_folder` | Native folder picker | §4 File | `FolderSection` → `native.pickFolder`, capability `dialog:allow-open` | PRESERVED | — | SOURCE PASS; PENDING INSTALLED #56 | Korean dialog |
| 2 | Folder scan | `gm::_collect_mp3_files_from_target_folder`, `at` | Top-level `.mp3` only | §4 | `scanner.py` `iterdir()`, case-insensitive `.mp3`, no recursion | PRESERVED | — | SOURCE PASS | |
| 3 | Startup load | `gm::_refresh_queue_after_startup`, `ui/target_folder` | Re-open the last folder | §4 | `settings.transcription_folder` + `sorigul.transcriptionFolder` | PRESERVED | — | SOURCE PASS | |
| 4 | Live folder change | `gm::_reset_target_folder_watcher` (QFileSystemWatcher, 1000 ms debounce) | Queue follows OS changes | §4 Folders | `folder_revision.py` + `folderRevisionWatcher.ts` (1 s sequential poll) | PRESERVED | #111 | SOURCE PASS; PENDING INSTALLED #63 | See §8 |
| 5 | Selected / all-incomplete start | `gm::run_transcribe_process` | Checked rows, else all incomplete | §4 | `CreateJobRequest.scope` + UI confirmation | PRESERVED | — | SOURCE PASS | |
| 6 | Complete-bundle skip | `at::is_transcription_complete` | Valid TXT/JSON/SRT → skip | §4 | `scanner.check_bundle`, runner skip unless `force_retranscribe` | PRESERVED | — | SOURCE PASS | |
| 7 | Invalid bundle not DONE | same | Missing or invalid → re-run | §4 | `INCOMPLETE` / `INVALID_RESULT` | PRESERVED | — | SOURCE PASS | Sorigul is stricter (segment validity) |
| 8 | Explicit re-transcribe | contract §4, prior RC-003 | — | §4 | `force_retranscribe` + UI action | PRESERVED | — | SOURCE PASS | |
| 9 | Old result preservation | `at` save flow | Keep the old result until the new one is saved | §4 | `OutputBundleWriter` staged → validate → backup → promote → rollback | PRESERVED | — | SOURCE PASS | Hardened |
| 10 | One-file failure continuation | `at::process_files` | Continue with later files | §4 | Runner continues on non-fatal `EngineError` | PRESERVED | — | SOURCE PASS | |
| 11 | Sequential single run | single `QProcess`, `_is_transcribe_running` guards | One transcription at a time | §4 (prior TR-004) | Per-Job sequential, but `BackgroundExecutionService(max_workers=2)` with no global guard; reachable via Folders-page folder switch | **CONFIRMED_DEFECT** | **#126** (P2) | SOURCE FAIL | |
| 12 | Duration column | `gm::_detect_duration_*` (mutagen → tinytag → raw) | Duration shown | §5L | `audio_metadata.py` (mutagen), `null` → honest unknown | APPROVED_INTENTIONAL_CHANGE | — | SOURCE PASS | §5L |
| 13 | Check all / uncheck all | `btn_filter_all`, `btn_uncheck_all` | Bulk selection | §4 | `QueueTable` tri-state select-all | PRESERVED | — | SOURCE PASS | |
| 14 | Clear DONE / all rows | `btn_clear_done`, `btn_clear_all` | Display-only row removal | — | Queue = live folder scan | **AMBIGUOUS** | **#127** A4 | decision | Recommended: approve (consequence of §5D) |
| 15 | Manual filename edit | `gm::_on_filename_double_clicked` | Inline edit of the target name | §4 | Preflight "이름 수정" + `/rename` | PRESERVED | — | SOURCE PASS | |

### 4.2 Filename

| # | Area | Legacy evidence | Legacy behavior | Current contract | Current Sorigul evidence | Classification | Issue | Validation state | Notes |
|---|---|---|---|---|---|---|---|---|---|
| 16 | Cleanup | `fn::clean_download_stem`, `remove_page_markers` | `+`→space, `(p.N~M)`, forbidden chars, spaces | §4 Filename | `normalizer.py` `PAGE_MARKER_PATTERN`, forbidden chars | PRESERVED | — | SOURCE PASS | |
| 17 | `N주차…M강` detection | `fn::detect_week_lesson` tier 2 | Week N, lesson M | §4, D12 | `WEEK_PATTERN` / `LESSON_PATTERN` | PRESERVED | — | SOURCE PASS | |
| 18 | `[N-M]` bracket detection | `fn::detect_week_lesson` tier 1 (`13강_[4-1] …`) | Week N, lesson M | §4, D12 "unchanged" | Not implemented → INVALID_TARGET | **CONFIRMED_DEFECT** | **#124** (P1) | SOURCE FAIL (§6) | |
| 19 | Week-only + first-free lesson | `fn` tier 3 + `resolve_next_available_lesson` (`12강_[4주차]_…`) | Week N; lesson = first free in that week | §4, MIGRATION_CONTRACT §10.1 | Uses the global `N강` counter as the lesson; no `강` → INVALID_TARGET | **CONFIRMED_DEFECT** | **#124** (P1) | SOURCE FAIL (§6) | Real download format |
| 20 | Course/subject alias detection | `fn::detect_course_name`, `detect_subject_name` | Fixed aliases | §5E | Free-text + `validate_classification_text` | APPROVED_INTENTIONAL_CHANGE | — | SOURCE PASS | |
| 21 | Standard-name protection | `fn::build_unique_normalize_plan` `already_standard` | Never rewrite a standard name | §4 | `STANDARD_PATTERN`, `UNCHANGED` / `MISMATCH` (D24 warn, never auto-rewrite) | PRESERVED | — | SOURCE PASS | |
| 22 | Collision awareness | `fn::collect_existing_lessons` (MP3/TXT/JSON/SRT) | No overwrite | §4 | `collect_existing_stems`, `CONFLICT` | PRESERVED | — | SOURCE PASS | |
| 23 | Next lesson / batch reservation | `reserved_lessons` | Preferred or next free | §4 | `normalize_batch` reservation (preferred + step-forward) | PRESERVED (detected-lesson case) | #124 covers first-free-from-1 | SOURCE PASS | |
| 24 | Same-stem bundle rename | `gm::_apply_smart_filename_normalization_before_transcribe` (`os.replace`; warn-only on partial failure) | MP3+TXT/JSON/SRT together | §4 | `BundleRenamer` preflight conflict + rollback | PRESERVED | — | SOURCE PASS | Hardened |
| 25 | Unresolvable name | Legacy keeps the raw name and continues | — | MIGRATION_CONTRACT §10.2 | `INVALID_TARGET` / `MISMATCH` / `CONFLICT` need explicit `CONTINUE_ORIGINAL` or an edit | PRESERVED | — | SOURCE PASS | Explicit consent |
| 26 | Long Korean / Unicode names | `gm`, `at` | Supported | §4 | UTF-8 JSON, pathlib, tests | PRESERVED | — | SOURCE PASS; PENDING INSTALLED #113 | |

### 4.3 Job / recovery

| # | Area | Legacy evidence | Legacy behavior | Current contract | Current Sorigul evidence | Classification | Issue | Validation state | Notes |
|---|---|---|---|---|---|---|---|---|---|
| 27 | STOP | `stop.flag`, `request_immediate_stop` | Stop; discard in-flight result | §4 | `CancellationToken`, runtime reap, `STOPPED` | PRESERVED | — | SOURCE PASS; PENDING INSTALLED #63 | |
| 28 | CANCEL distinct | Tauri `job_runner` CANCELLED | Distinct from STOP | §4 | `CANCEL_REQUESTED` → `CANCELLED` | PRESERVED | — | SOURCE PASS | |
| 29 | CRASHED | session `running`→`crashed` | Abnormal exit detected | §4 | `JobManager._recover_job` | PRESERVED | — | SOURCE PASS; PENDING INSTALLED #63 | |
| 30 | Retry keeps DONE | session `completed_files` | Skip DONE | §4 | Retry mutation re-checks disk; DONE kept | PRESERVED | — | SOURCE PASS | |
| 31 | Atomic persistence | `*.tmp` + `os.replace` | — | §4 | Unique tmp + `replace`, rollback on failure | PRESERVED | — | SOURCE PASS | |
| 32 | Corrupt quarantine | `corrupt_session` | — | §4 | `jobs.corrupt.<ts>.json`, fail-closed codes | PRESERVED | — | SOURCE PASS | |
| 33 | Restart preservation | Tauri RT-003 | DONE survives restart | §4 | `jobs.json` load | PRESERVED | — | SOURCE PASS; PENDING INSTALLED #63 | |
| 34 | Colab `progress.json` startup resume | `gm::_check_colab_progress_resume_on_startup` | — | — | — | DEPRECATED_EXCLUDED | — | n/a | **No callers** at the baseline, so not ACTIVE |
| 35 | Session status label | `gm::update_session_label` | Previous-run state shown | §4 | Job status + CRASHED event (Log, current task) | PRESERVED | — | SOURCE PASS | |

### 4.4 Local

| # | Area | Legacy evidence | Legacy behavior | Current contract | Current Sorigul evidence | Classification | Issue | Validation state | Notes |
|---|---|---|---|---|---|---|---|---|---|
| 36 | Engine/model | `at` `MODEL_SIZE="medium"` | OpenAI Whisper medium | §4 Local | `LocalWhisperEngine.MODEL_NAME`, runtime rejects other models | PRESERVED | — | SOURCE PASS | |
| 37 | CUDA preferred / CPU fallback | `at` load with CPU retry | — | §4 | `local_runtime_main._transcribe` | PRESERVED | — | SOURCE PASS; PENDING INSTALLED #113/#47 | Release gate requires CUDA |
| 38 | fp16 decision | `at::detect_fp16_setting` | ≥ 6 GiB → True; < 6 GiB, property failure, or no CUDA → False | §4 | `_detect_fp16` (`FP16_MIN_VRAM_BYTES`); also False when device=cpu after a CUDA load failure | PRESERVED | — | SOURCE PASS | Strictly safer |
| 39 | fp16 retry | `at::is_fp16_retryable_error` | One `fp16=False` retry; FileNotFound/Permission/IsADirectory re-raised | §4 | Identical markers/exclusions, one retry | PRESERVED | — | SOURCE PASS | |
| 40 | Decoding options | `at` `transcribe_kwargs` | ko / transcribe / 0 / 5 / 5 / 1.0 / False | §4 | `TRANSCRIBE_OPTIONS` + exact-match `_validate_request` | PRESERVED | — | SOURCE PASS | |
| 41 | Split Local Runtime | monolithic | — | §7 | Versioned runtime, manifest/hash/provenance verification | APPROVED_INTENTIONAL_CHANGE | — | SOURCE PASS; PENDING INSTALLED #113 | |

### 4.5 Colab

| # | Area | Legacy evidence | Legacy behavior | Current contract | Current Sorigul evidence | Classification | Issue | Validation state | Notes |
|---|---|---|---|---|---|---|---|---|---|
| 42 | Engine/model/compute | `colab_transcribe.ipynb` | faster-whisper large-v3, float16 / int8 | §4 Colab | `select_runtime_identity`, `WhisperModel(...)` | PRESERVED | #106 | SOURCE PASS; PENDING EXTERNAL #48 | |
| 43 | Decode options | notebook `transcribe_kwargs` | ko, beam 5, word_timestamps False | §4 | `/transcribe` handler | PRESERVED | — | SOURCE PASS | Identical |
| 44 | Health identity | notebook `/health` | Liveness | §5M | Health returns engine/model/device/compute; Desktop requires faster-whisper + large-v3 | PRESERVED (hardened) | — | SOURCE PASS | |
| 45 | Chunk / tail / merge | v0.9.0 300 s, tail skip, offset merge | — | §5K | `CHUNK_SECONDS=300`, `<1 s` / `<2048 B` tail skip, offset merge sorted | APPROVED_INTENTIONAL_CHANGE (chunk) + PRESERVED (merge) | — | SOURCE PASS | |
| 46 | Automatic retry | 2 retries, 10/20 s, 5xx/524/timeout | — | §5K | Max 1 retry, retryable 408/429/5xx/network | APPROVED_INTENTIONAL_CHANGE | — | SOURCE PASS | |
| 47 | Recovery / STOP / CANCEL | `progress.json` per-file | — | §5K | FAILED reuses verified chunks; STOP/CANCEL clears the cache; cache signature `faster-whisper:large-v3:…:v3`, so an old medium cache is never reused | APPROVED_INTENTIONAL_CHANGE | — | SOURCE PASS | |
| 48 | Stop after current chunk | `_colab_stop_after_current` | — | §4 | Token checked between chunks; the in-flight HTTP chunk completes | PRESERVED | — | SOURCE PASS | |
| 49 | Connection UX | clipboard URL + manual + `연결 확인` | — | §5J | Drive rendezvous primary, manual URL fallback | APPROVED_INTENTIONAL_CHANGE | — | SOURCE PASS; PENDING EXTERNAL #48 | |
| 50 | "Colab 열기" button | `gm::open_colab_notebook` (`btn_colab_open`) | One-click open of the notebook | — | None; `colab/README.md` instructions | **AMBIGUOUS** | **#127** A1 | decision | |
| 51 | Security | none (plain HTTP to a tunnel) | — | §5M | Ed25519 pairing, signed headers, replay nonce cache, content SHA-256, pinned cloudflared hash | APPROVED_INTENTIONAL_CHANGE | — | SOURCE PASS | |
| 52 | Real Colab run | v0.9.0 validation | — | §8 | — | VALIDATION_ONLY_PENDING | #48/#60 | PENDING EXTERNAL | Zero-cost gated |

### 4.6 Result contract

| # | Area | Legacy evidence | Legacy behavior | Current contract | Current Sorigul evidence | Classification | Issue | Validation state | Notes |
|---|---|---|---|---|---|---|---|---|---|
| 53 | TXT | `at::is_transcription_complete` | Must be > 1 byte | §4 | > 0 bytes (`scanner`, `OutputBundleValidator`) | PRESERVED | — | SOURCE PASS | A 1-byte TXT differs; negligible |
| 54 | Empty TXT | same | Treated as incomplete | §4 | Empty speech → `TXT_INVALID` → file FAILED; the old result is kept | PRESERVED | — | SOURCE PASS | Same effective behavior |
| 55 | JSON | same | `text` + `segments` keys, > 1 byte | §4 | Keys + `TranscriptionResult.from_engine_payload` segment validity | PRESERVED (stricter) | — | SOURCE PASS | |
| 56 | SRT | same | Must exist; may be empty | §4 | Existence only; empty allowed | PRESERVED | — | SOURCE PASS | |
| 57 | Same-stem outputs | `at::get_output_paths` | Beside the MP3 | §4 | `BundlePaths.final_for` | PRESERVED | — | SOURCE PASS | |

### 4.7 Google Drive

| # | Area | Legacy evidence | Legacy behavior | Current contract | Current Sorigul evidence | Classification | Issue | Validation state | Notes |
|---|---|---|---|---|---|---|---|---|---|
| 58 | OAuth / token storage | `google_drive_uploader.py` (%APPDATA%) | Local credential/token | §5M | Loopback OAuth, `%LOCALAPPDATA%\Sorigul\auth`, private ACL before publish | PRESERVED (hardened) | #122 | SOURCE PASS; PENDING EXTERNAL #48 | ACL uses bare `whoami`/`icacls` |
| 59 | Bundle | MP3/TXT/JSON/SRT | — | §5B | TXT/JSON/SRT only; the MP3 path is used only as a stem | APPROVED_INTENTIONAL_CHANGE | — | SOURCE PASS | |
| 60 | Classification / stage / exam root | filename re-parse, fixed root | — | §5F/G/H | Job metadata, `resolve_stage`, `drive_exam_root`, 중개사법 week-folder exception | APPROVED_INTENTIONAL_CHANGE | — | SOURCE PASS | |
| 61 | update_or_create | `upload_file` | Same parent/name → update | §5B | `find_file` → `update_file` / `create_file` | PRESERVED | — | SOURCE PASS; PENDING EXTERNAL #48 | Affected by #124 naming |
| 62 | Preflight | `google_drive_upload_service` | Validate before network | §5B | `OutputBundleValidator` + read probe before folder creation | PRESERVED | — | SOURCE PASS | |
| 63 | Failure isolation / retry | local DONE + Drive FAILED | — | §5B | Separate `DriveFileState`, `/drive/retry`, scheduled (never awaited) upload | PRESERVED | — | SOURCE PASS | |
| 64 | Auto-upload toggle | persistent toggle | — | §5I | Per-run `upload_to_drive`; `RuntimeSettings` has no field (`extra="forbid"`) | APPROVED_INTENTIONAL_CHANGE | — | SOURCE PASS | Default OFF each launch |
| 65 | Real Drive mutation | v0.9.0-rc2 / Phase 23E | — | §8 | — | VALIDATION_ONLY_PENDING | #48 | PENDING EXTERNAL | NOT RUN |

### 4.8 Folders / Log

| # | Area | Legacy evidence | Legacy behavior | Current contract | Current Sorigul evidence | Classification | Issue | Validation state | Notes |
|---|---|---|---|---|---|---|---|---|---|
| 66 | Filters | `gm::_set_folder_filter_mode` | 전체 / 완료 / 미완료 / 결과만 | §4 | `/folders/scan` filter + counts | PRESERVED | — | SOURCE PASS; PENDING INSTALLED #56/#63 | |
| 67 | Preview / full text | `gm::_update_folders_preview_for_row` (500 chars), `_show_folders_preview_full_text` | — | §4 | `preview_chars=500`, full ≤ 5 MiB | PRESERVED | — | SOURCE PASS | |
| 68 | TXT encoding fallback | `gm::_read_text_file_with_fallback` (utf-8-sig/utf-8/cp949/euc-kr) | — | — | UTF-8 only → `TXT_NOT_UTF8` | **AMBIGUOUS** | **#127** A5 | decision | |
| 69 | Column sort | `gm::_handle_folders_table_header_clicked` | Name/type asc/desc toggle | — | Fixed name order | **AMBIGUOUS** | **#127** A3 | decision | |
| 70 | Open / reveal | `gm::open_preferred_folder` | Explorer | §4 | `open-intent` → Rust `open_folder_by_intent` → `explorer.exe` | PRESERVED | #122 (bare name) | SOURCE PASS; PENDING INSTALLED #56 | |
| 71 | Live refresh | QFileSystemWatcher | — | §4 | `FoldersPage` `useFolderRevision` | PRESERVED | #111 | SOURCE PASS; PENDING INSTALLED #63 | |
| 72 | Dashboard | `gm::refresh_dashboard_view` | Statistics | §5A | Removed | APPROVED_INTENTIONAL_CHANGE | — | SOURCE PASS | |
| 73 | Log | sidebar log | Execution log | §5A | Structured `LogPage` (Job + application events, filters, copy) | APPROVED_INTENTIONAL_CHANGE | — | SOURCE PASS | |

### 4.9 Desktop

| # | Area | Legacy evidence | Legacy behavior | Current contract | Current Sorigul evidence | Classification | Issue | Validation state | Notes |
|---|---|---|---|---|---|---|---|---|---|
| 74 | File/job notifications + toggles | `ui/notify_each_file`, `ui/notify_total` | — | §4 | `NotificationSettings`, `DesktopCoordinator` events | PRESERVED | — | SOURCE PASS; PENDING INSTALLED #56 | |
| 75 | Toast with 폴더 열기 | `TrayToastWindow` | Folder button | §4 | #110 toast window + job_id-scoped intent | PRESERVED (source) | #110 | **VALIDATION_ONLY_PENDING** (#56/#63) | §7 |
| 76 | Tray open/quit | `gm::setup_tray_icon` | 앱 열기 / 종료 | §4 | `build_tray` | PRESERVED | — | SOURCE PASS; PENDING INSTALLED #56 | |
| 77 | Tray progress tooltip | `gm::_update_tray_tooltip_for_progress` | `N%` + file | — | Static tooltip | **AMBIGUOUS** | **#127** A2 | decision | |
| 78 | Close during run | `gm::closeEvent` | Running → hide to tray + notice; idle → exit | §4, prior UI-004 | `close_behavior=exit` exits unconditionally, killing the run (the user's recorded setting is `exit`) | **CONFIRMED_DEFECT** | **#128** (P2) | SOURCE FAIL | |
| 79 | Close-to-tray (idle) | same | — | §4 | `close_behavior=tray` hide | PRESERVED | — | SOURCE PASS; PENDING INSTALLED #56 | |
| 80 | Shutdown after completion | `SHUTDOWN_WAIT_OPTIONS`, `confirm_shutdown_after_completion` | Immediate / 15 / 30 s, countdown, cancel | §4 | `ShutdownMode`, `DesktopCoordinator` countdown/cancel, Rust `ShutdownGate` | PRESERVED | — | SOURCE PASS; actual shutdown **NOT RUN** (#58) | |
| 81 | Backend auto-start / health / cleanup | Tauri RT-001/002 | No orphan | §4 | `sidecar.rs` Job Object kill-on-close, owned-process cleanup, health reuse | PRESERVED | — | SOURCE PASS; PENDING INSTALLED #113 | |
| 82 | Start Menu shortcut / AppUserModelID | `ensure_start_menu_shortcut`, `apply_windows_app_identity` | — | §4 | MSI shortcut + `identifier` | PRESERVED (installer) | — | PENDING INSTALLED #113 | |
| 83 | Settings persistence | `QSettings` (folder, notify, shutdown, engine) | — | §4 | `settings.json` atomic + quarantine | PRESERVED | — | SOURCE PASS | |
| 84 | Error messages | `_normalize_dialog_text` | Friendly Korean | §4 | `EngineError.user_message`, HTTP detail | PRESERVED | — | SOURCE PASS | |
| 85 | Progress / ETA | `ProgressSmoother` "crawl" interpolation | Smoothed / estimated | §5L | Real metadata; ETA from observed speed only; `null` when unknown | APPROVED_INTENTIONAL_CHANGE | — | SOURCE PASS | |
| 86 | Unicode / Korean paths | — | — | §4 | Rust intent tests (Korean), UTF-8 everywhere | PRESERVED | — | SOURCE PASS; PENDING INSTALLED #113 | |

### 4.10 Removed or excluded paths

| # | Area | Legacy evidence | Current contract | Classification | Notes |
|---|---|---|---|---|---|
| 87 | Prompt / corrections | earlier releases | §5C | APPROVED_INTENTIONAL_CHANGE | Already removed at the Legacy baseline too |
| 88 | MP3 import/move (`MOVED`) | `gm::move_selected_files*` | §5D | APPROVED_INTENTIONAL_CHANGE | |
| 89 | Google Drive Queue | `drive_queue_*`, `colab_drive_worker.py` | §6 | DEPRECATED_EXCLUDED | |
| 90 | Colab CLI/WSL, backup stub, archive/POC | `backend/services/colab_cli_service.py`, backup stub, `archive/` | §6 | DEPRECATED_EXCLUDED | |

**Counts (90 rows):**

| Classification | Rows |
|---|---|
| PRESERVED | 60 (row 75 is source-preserved; its installed click proof is validation-only pending) |
| APPROVED_INTENTIONAL_CHANGE | 16 (row 45 counted here; its merge half is preserved) |
| DEPRECATED_EXCLUDED | 3 |
| VALIDATION_ONLY_PENDING | 2 (rows 52, 65) |
| CONFIRMED_DEFECT | 4 rows → 3 Issues (#124 ×2, #126, #128) |
| AMBIGUOUS | 5 → #127 A1–A5 |

**Legacy ACTIVE capabilities extracted: 86** (rows 1–86).

**Capabilities missed by the prior 43-item audit** (found or re-confirmed by the repository-wide pass):
- rows 4, 75: live watcher and toast folder action — already found by #109 → #110/#111;
- rows 11, 13, 14, 15, 18, 19, 50, 68, 69, 77, 82;
- row 34, which proved to be dead code.

## 5. Approved Intentional Changes — re-verified

| Change | Source proof at HEAD | Result |
|---|---|---|
| Dashboard → Log | No Dashboard route; `AppShell` has 4 destinations; `LogPage` | Conforms |
| Drive 3 files | `DriveUploadService._upload` paths = TXT/JSON/SRT; MP3 never read or sent | Conforms |
| Prompt/corrections removed | No `initial_prompt` or corrections in Local or Colab | Conforms |
| MP3 import/move removed | No move/copy API; scanner reads the selected folder | Conforms |
| Course/subject free text | `validate_classification_text`; no alias table in the normalizer | Conforms |
| Drive metadata classification | `DriveClassifier.classify` uses Job `file_metadata`; narrow legacy fallback | Conforms |
| Stage mapping | `KNOWN_SUBJECT_STAGE` + persisted `subject_stage_overrides` | Conforms |
| Exam root configurable | `RuntimeSettings.drive_exam_root` | Conforms |
| Auto-upload per-run, non-persistent | `CreateJobRequest.upload_to_drive`; no settings field; UI checkbox state only | Conforms |
| Colab rendezvous primary | `ColabRendezvousService`, `EngineSection` auto-connect; manual URL fallback | Conforms |
| 300 s internal chunks, hidden | `CHUNK_SECONDS=300`; no chunk count or duration in UI/API payload | Conforms |
| Honest duration/progress/ETA | mutagen; `current_progress=None` for Local; observed-speed ETA only | Conforms |
| Security hardening | Signed/paired/replay-protected Colab, private token ACL, CSP, minimal capabilities | Conforms (see §9 for new gaps) |

None of these differences was reported as a defect. No current difference was relabelled as an Intentional Change without an approval record: rows 14, 50, 68, 69, and 77 went to #127 instead.

## 6. Confirmed defects (new)

| Issue | Severity | Summary | Required gate |
|---|---|---|---|
| **#124** | **P1** | Week/lesson detection diverges from Legacy. `N강_[M주차]` (the real download format) yields lesson N instead of the first free lesson in week M. `[N-M]` and week-only names become INVALID_TARGET. Affects local and Drive naming continuity. | Before #113 |
| #125 | P2 | Loopback backend accepts any `Host` header, so the API is reachable via DNS rebinding (arbitrary folder scan, transcript read, Job/rename). Distinct from the #53 local-process threat model. | Before #113 (recommended); mandatory before #114 |
| #126 | P2 | Concurrent transcription runs across folders (`max_workers=2`, no global guard; Folders-page folder switch) | Before #113 (recommended); mandatory before #63 |
| #128 | P2 | `close_behavior=exit` kills an active run; Legacy always hid to tray while running | Before #113 (recommended); mandatory before #56 |

#124 reproduction (Legacy `filename_normalizer` executed read-only from the scratch clone; each name alone in an empty folder; 개념완성/민법):

| Input | Legacy | Sorigul |
|---|---|---|
| `1강_[1주차]_26 민법 총칙.mp3` | `개념완성_민법_1주차_1강` | `개념완성_민법_1주차_1강` |
| `13강_[4주차]_민법 물권.mp3` | `개념완성_민법_4주차_1강` | `개념완성_민법_4주차_13강` |
| `13강_[4-1] 시장론 4.mp3` | `개념완성_민법_4주차_1강` | INVALID_TARGET |
| `[4주차] 민법 특강.mp3` | `개념완성_민법_4주차_1강` | INVALID_TARGET |
| `4주차 3강 민법(p.12~34).mp3` | `개념완성_민법_4주차_3강` | `개념완성_민법_4주차_3강` |

Existing tests only use `1강_[1주차]…`, where N = 1 hides the divergence. No decision record approves the change: D12 keeps detection "unchanged", and MIGRATION_CONTRACT §10.1 keeps "preferred or first-free".

### Known defect carried in

**#122 — P2, PRE-ARTIFACT FIX REQUIRED before #113 and #48.** Re-confirmed:

- Git Bash: `which whoami.exe` → `/usr/bin/whoami.exe`. `test_drive_oauth_loopback.py::test_automatic_callback_completes_the_flow_without_manual_paste` and `test_process_recovery_contracts.py::test_ensure_client_builds_drive_service_on_the_bounded_transport` → **2 failed** (`CalledProcessError … whoami.exe … exit status 1`).
- PowerShell: full suite green (§10).
- 5F found the same bare-name class at `drive.py` `icacls.exe` (×2), `local_whisper.py` `taskkill.exe`, `sidecar.rs` `taskkill.exe`, `lib.rs` `explorer.exe`, and `shutdown.rs` `shutdown.exe`. The widened scope is recorded on #122.

**#45** (OPEN, P0 label): fix `22ebe3d` is an ancestor of the audited HEAD and passed review. It is open only pending merge, so it is **not a source blocker**. Artifact confirmation belongs to #113.

## 7. Ambiguities (user decision required)

#127:
- A1 "Colab 열기" button;
- A2 tray progress tooltip;
- A3 Folders column sort;
- A4 queue clear rows (recommended: approve as a §5D consequence);
- A5 TXT preview encoding fallback.

Until #127 is decided, full Legacy parity cannot be declared complete.

## 8. #110 / #111 source review

**#110 completion toast:**

| Check | Source finding |
|---|---|
| `focusable: false` window | `tauri.conf.json` `completion-toast`: `focus:false`, `focusable:false`, `alwaysOnTop`, `skipTaskbar`, no decorations |
| Button wiring | `CompletionToast.tsx`: 폴더 열기 → `open_notification_folder(job_id)`; 확인 → `dismiss_completion_toast` |
| Secure path | Rust fetches `/desktop/jobs/{job_id}/open-folder-intent`. The folder comes only from the stored Job (410 when missing). The toast capability grants only `event listen/unlisten`. |
| Fallback | OS notification (title/body, no folder action) only when the toast fails |
| Dedup | `eventKey`; baseline seeded on the first poll |
| Timing | `COMPLETION_TOAST_TIMEOUT = 7200 ms`; stale-timeout guard (Rust tests) |
| Single reusable window | One window; payload replaced, not stacked; close → hide |

**Real WebView2 click on a `focusable:false` window is not proven by source → PENDING INSTALLED #56/#63.**

**#111 live folder:**

| Check | Source finding |
|---|---|
| Poll cadence | 1 s sequential poll; next poll scheduled only after the fetch and any refresh settle (max 1 in flight) |
| Scope | Top-level only; `REVISION_EXTENSIONS = mp3/txt/json/srt`; metadata (name, size, `mtime_ns`) only; no content read or hash; `follow_symlinks=False`; no recursion |
| Pausing | Paused while `isProcessing \|\| isPreflighting`; reconciles once on resume for the same folder |
| Old-folder abort | Folder change or unmount → `stop()` + `AbortController.abort()` |
| Pages | Folders live refresh + preview refresh via `liveRefresh` |
| Side effects | `onChanged` only re-reads disk; Start/Retry exist only in explicit handlers (`TranscriptionPage` L545/554/569) |

**Actual Explorer modification → PENDING INSTALLED #63.**

## 9. Security / Lightweight / Zero-cost / Git hygiene

### Security

| Area | Finding |
|---|---|
| Shell | No arbitrary shell. No `shell:` plugin. Capabilities: `dialog:allow-open`, `opener:allow-open-url`, `notification:default`, window show/hide/focus. The toast window gets event listen only. |
| Filesystem | No raw filesystem permission in the frontend. Explorer runs only via backend-validated intents (scan-context item ids; job_id → stored folder). |
| Broad opener | `openUrl` is used only for the Drive OAuth URL (`opener:allow-open-url`). |
| CSP | Strict: `script-src 'self'`, `connect-src` limited to ipc + `127.0.0.1:8000`, `object-src 'none'`, `frame-ancestors 'none'`. `unsafe-inline` styles are dev-only. |
| Token exposure | The token is never returned by the API; written only after the private ACL; no token or credential file is tracked. |
| Colab | Unsigned access to `/health` and `/transcribe` → 401; replay nonce cache; content-hash binding; pinned cloudflared SHA-256; anonymous Quick Tunnel only. |
| New defect | **#125**: no Host allowlist; DNS rebinding reaches the loopback API. |
| Known | **#53**: no local-process authentication (threat model open). **#122**: bare-name utilities (widened scope). |

### Lightweight

| Area | Finding |
|---|---|
| Core requirements | `backend/requirements.txt` has no torch, whisper, faster-whisper, or CUDA. |
| Core spec | `sorigul_backend.spec` excludes `torch`, `whisper`, `numba`, `llvmlite`. |
| Local Runtime | Heavyweight dependencies live only in `requirements-whisper.txt` / `tools/requirements-torch-cuda.txt` / `sorigul_local_runtime.spec`. |
| Colab | `faster-whisper` appears only in `colab/requirements.txt`. |
| Frontend / Rust | `package.json` and `Cargo.toml` carry only Tauri plugins, React, lucide, `ureq`, `serde`, `windows-sys`. |
| Build | No fresh size build was run; size is owned by #113. **Source lightweight contract: PASS.** |

### Zero-cost

A `git grep` for paid API / billing / credit / paid-tunnel / managed-GPU terms across `backend/src`, `colab`, `frontend/src`, `frontend/src-tauri/src`, and `scripts` found only the explicit prohibitions in `colab/README.md`. The Colab tunnel is an anonymous Quick Tunnel with no token or account. The Colab runtime is user-started only, and nothing is ever provisioned. Unclear credit status is documented as "use Local", so the path fails closed. **Zero-cost contract: PASS.**

### Git hygiene

| Check | Result |
|---|---|
| Tracked MP3/results, model/cache, installer/build output, credential/token, runtime `jobs.json` / `settings.json` | None tracked (the only name match is `frontend/src/styles/tokens.css`) |
| `.gitignore` | Covers `credentials*.json`, `token*.json`, `*.exe`, `*.msi`, `dist/`, `target/`, `venv/` |
| Tracked tree after the frontend build and cargo runs | Unchanged; only the pre-existing untracked helpers remain, untouched |
| Sensitive paths in this report | None |

**Git hygiene: PASS.**

## 10. Test results (source regression, exact)

All commands ran from **PowerShell** at HEAD `71d6920`, with `CARGO_NET_OFFLINE=true`.

| Suite | Command | Result |
|---|---|---|
| Root contract / release | `venv\Scripts\python.exe -m pytest tests -q -rfE -p no:cacheprovider` | **40 passed**, exit 0 |
| Backend full (includes release / security / package contract tests) | `(backend) ..\venv\Scripts\python.exe -m pytest tests -q -rfE -p no:cacheprovider` | **416 passed, 2 skipped**, 1 warning, exit 0. Skips: `test_app_data_isolation.py:135` (non-Windows fallback); `test_folder_revision.py:123` (symlink privilege). |
| #122 evidence (Git Bash, not a regression) | the two named tests | **2 failed** (`/usr/bin/whoami.exe`) |
| Frontend lint | `npm.cmd run lint` (oxlint) | exit 0 |
| Frontend typecheck | `npm.cmd run typecheck` | exit 0 |
| Frontend build | `npm.cmd run build` | exit 0 (1846 modules) |
| Rust fmt | `cargo fmt --check` | exit 0 |
| Rust check | `cargo check --locked --offline` | exit 0 |
| Rust clippy | `cargo clippy --locked --offline -- -D warnings` | exit 0 |
| Rust clippy (all targets) | `cargo clippy --locked --offline --all-targets -- -D warnings` | exit 0 |
| Rust test | `cargo test --locked --offline` | **54 passed**, 0 failed |
| Whitespace | `git diff --check` | clean (recorded again at commit) |

A green test count is **not** used as parity evidence. Every test above passed while #124, #126, and #128 exist, because no test encodes those Legacy behaviors.

## 11. External / installed pending (NOT RUN in 5F)

| Gate | Pending evidence |
|---|---|
| #113 | Fresh Core / Local Runtime / MSI, sizes, CUDA synthetic, Job Object, Unicode install |
| #56 / #63 | Tray, close, toast click (`focusable:false`), Explorer, live-folder Explorer edits, Folders, retry, CRASHED restart, cleanup |
| #47 | Real personal Local study MP3 |
| #48 / #60 | Real zero-cost Colab and real Drive OAuth/API mutation |
| #58 | Actual Windows shutdown (explicit approval only) |
| #59 | Backend post-start recovery policy |

## 12. Final verdict

```
SOURCE FULL REGRESSION         = FAIL
KNOWN P0/P1 SOURCE BLOCKERS    = 1 (#124, P1)
PRE-ARTIFACT DEFECT BURN-DOWN  = REQUIRED (#124 P1; #122, #125, #126, #128 P2)
USER DECISION REQUIRED         = #127 (AMBIGUOUS A1–A5)
READY FOR #113                 = NO
```

Tests, toolchain, lightweight, zero-cost, and hygiene gates are green. The FAIL comes from the Legacy inventory and contract matrix, not from a test failure.

**Next:** fix each defect in its own work unit (Issue → branch → PR), starting with #124. Then #122 (5G, widened scope), #125, #126, and #128. After the #127 decision, re-run this source regression. #113 starts only when the re-run reports `SOURCE FULL REGRESSION = PASS` with no remaining pre-artifact defects.
