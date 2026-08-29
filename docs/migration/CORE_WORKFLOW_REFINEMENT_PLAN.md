# Sorigul Core Workflow Refinement Plan

Status: `LOCKED` (Phase 0 — documentation only, no implementation)

Branch: `feature/core-workflow-refinement`
Base: `validation/full-feature-parity-release` @ `47aa500b5453e42f186292b41d9b8054f96bc638`

## 1. Background

`MIGRATION_CONTRACT.md` locked the Legacy→Sorigul parity contract from the `jeonsa_doumi` audit. Since that lock, real usage review surfaced that literal 1:1 Legacy parity is not the right target for several areas: Whisper prompt/correction machinery never helped transcription quality, MP3 upload/import/move added risk without value, and fixed course/subject dropdowns fought how the user actually names courses.

This document is the second product-contract lock. It does not reopen D01–D10 in `MIGRATION_CONTRACT_REVIEW.md`; it narrows or extends specific areas where real usage disagreed with the original audit-derived contract, and it locks several areas `MIGRATION_CONTRACT.md` left unaddressed (exam root configuration, Colab rendezvous, duration/progress honesty). Every deviation from the existing locked contract is recorded below as `SUPERSEDED_BY_PRODUCT_DECISION` (an existing locked line is narrowed or replaced) or `APPROVED_INTENTIONAL_CHANGE` (a new decision in an area the existing contract never locked). Nothing is silently dropped — see Section 3 and the per-decision entries in Section 2.

This is a documentation-only lock (Phase 0). No Python, React, Rust, test, installer, or dependency file changes are part of this work. Phase 1 implementation starts only on a separate, explicit instruction.

## 2. Locked Product Decisions

Decisions are numbered D11 onward, continuing the register in `MIGRATION_CONTRACT_REVIEW.md` (D01–D10). Each entry states status, the superseded/extended contract line (if any), and the final user contract.

### D11 — Google Drive upload bundle: 3 files, not 4

Status: `DECIDED (SUPERSEDED_BY_PRODUCT_DECISION)`

Supersedes:
- `MIGRATION_CONTRACT.md` §4 "Google Drive only, OAuth Drive, MP3/TXT/JSON/SRT 4-file upload", §12 "업로드 bundle은 정확히 MP3, TXT, JSON, SRT 네 파일이다.", §19 acceptance line "Google Drive 4-file bundle... 유지한다."
- `FEATURE_PARITY.md` "Google Drive" section: "MP3/TXT/JSON/SRT 네 파일의 preflight validation을 유지한다."
- `LEGACY_FEATURE_PARITY_AUDIT.md` rows `GD-003` (4종 bundle 업로드), `GD-004` (MP3 포함 preflight)
- `MIGRATION_CONTRACT_REVIEW.md` §4 Already Locked Contracts: "Drive 업로드 4종"

Final user contract:
Drive upload bundle is exactly TXT, JSON, SRT. The original MP3 is never uploaded to, staged in, or otherwise transmitted to Google Drive as part of this bundle. MP3 stays in the local source folder permanently — never deleted, never moved. Drive preflight validation no longer treats MP3 existence as an upload requirement (it still confirms the MP3 exists locally as the transcription source, but does not include it in the upload set or its completeness check for Drive purposes). `update_or_create` semantics and preflight validation for TXT/JSON/SRT are otherwise unchanged from the existing contract.

### D12 — Course/subject: user text input, not fixed alias detection

Status: `DECIDED (SUPERSEDED_BY_PRODUCT_DECISION, partial)`

Supersedes:
- `MIGRATION_CONTRACT.md` §10.1 "course/subject alias 적용" (as a *preserved* normalization behavior)
- `LEGACY_FEATURE_PARITY_AUDIT.md` row `FN-002` "과정·과목·주차·강 감지... alias를 표준 과정/과목/주차/강으로 해석"
- `FEATURE_PARITY.md` "파일명과 결과 bundle": "과정/과목 alias... 기능을 유지한다."
- `backend/src/services/drive.py`'s `COURSES` / `SUBJECT_ALIASES` fixed sets, used today for classification (evidence, not contract — cited for scope)

Retained (not superseded): week/lesson detection from filename remains locked exactly as `MIGRATION_CONTRACT.md` §10.1 describes it.

Final user contract:
Course and subject are free-text fields the user types (see D22 for persistence). Sorigul does not restrict input to a fixed dropdown or alias table on the primary path. Week/lesson extraction from the original filename is unchanged and independent of this decision — see Section 8. Filename normalization builds `{course}_{subject}_{N주차}_{M강}` from the user's typed course/subject plus the detected week/lesson.

### D13 — Prompt / corrections: not migrated

Status: `DECIDED (APPROVED_INTENTIONAL_CHANGE, new area — not previously locked by MIGRATION_CONTRACT.md)`

Scope note: subject-specific prompt, `initial_prompt` profiles, common/subject corrections, and automatic transcription-text replacement existed in Legacy but were never captured as an ACTIVE item in `LEGACY_FEATURE_PARITY_AUDIT.md`'s 43-item inventory and are not referenced anywhere in `MIGRATION_CONTRACT.md`. This is a new decision closing a gap the original audit missed, not a reversal of a locked line.

Final user contract:
Sorigul does not implement subject-specific prompts, `initial_prompt` profiles, common corrections, subject corrections, automatic transcription-text replacement, or any correction/prompt editing UI, on Local or Colab. TXT/JSON/SRT are generated directly from the engine's returned transcription result with no text substitution layer. `MIGRATION_CONTRACT.md` §8 Local Whisper inference options (`language`, `task`, `temperature`, `beam_size`, `best_of`, `patience`, `condition_on_previous_text`) are unaffected — those are decoding parameters, not prompt/correction text.

### D14 — MP3 import/move: not migrated

Status: `DECIDED (APPROVED_INTENTIONAL_CHANGE, new area — not previously locked by MIGRATION_CONTRACT.md)`

Scope note: same as D13 — the Legacy "select external MP3 → move into 전사자료 folder → transcribe" flow was never an ACTIVE audit item and is not referenced in `MIGRATION_CONTRACT.md`.

Final user contract:
Sorigul provides no MP3 upload, import, copy, or move UI. The user places MP3 files directly into the transcription folder using the OS file system; Sorigul only selects that folder, scans it, and transcribes what it finds. No feature moves or copies MP3s into a managed folder before transcription.

### D15 — Google Drive classification source of truth: Job/file metadata, not filename re-parsing

Status: `DECIDED (SUPERSEDED_BY_PRODUCT_DECISION)`

Supersedes:
- `LEGACY_FEATURE_PARITY_AUDIT.md` row `GD-002`: "파일명 정규화 결과로 Drive 경로를 분류"
- Current implementation evidence (not contract text, cited for scope): `backend/src/services/drive.py::DriveClassifier.classify()` re-parses `Path(filename).stem` against a fixed standard-name regex to recover course/subject/week/lesson for Drive folder targeting.

Final user contract:
Drive classification reads `course`, `subject`, `stage` from Job-level metadata and `week`, `lesson`, `normalized_name` from per-file metadata (see Section 5). It does not re-derive these values by pattern-matching the current filename. A file's classification metadata survives rename and survives retry. Filename remains the display/output naming convention; it is not re-parsed as the classification source.

### D16 — Stage ([1차]/[2차]) mapping: automatic for known subjects, fallback for unknown

Status: `DECIDED (APPROVED_INTENTIONAL_CHANGE, extends D12/D15)`

Final user contract:
Known subjects map to stage automatically: 1차 = {부동산학개론, 민법}; 2차 = {공인중개사법, 부동산공법, 부동산공시법, 부동산세법}. When the user's typed subject does not match any known subject, Sorigul asks the user to pick 1차 or 2차 as a fallback, once per new subject value (not on every job). The default UI flow does not ask for stage on every run — only when the subject is unrecognized and stage cannot be inferred.

### D17 — Google Drive exam root: persistent setting, not hardcoded

Status: `DECIDED (APPROVED_INTENTIONAL_CHANGE, new area — clarifies undocumented hardcoding)`

Scope note: `MIGRATION_CONTRACT.md` never explicitly locked the exam root string as code-level; `backend/src/services/drive.py::DRIVE_ROOT_HIERARCHY = ("2026 제37회 공인중개사 자격시험", "전사자료")` is current implementation evidence of the gap this decision closes, not a locked contract line being reversed.

Final user contract:
The exam root folder name (e.g. `2026 제37회 공인중개사 자격시험`) is a persistent Settings value, editable in Settings UI, defaulting to the current value for existing installs. `전사자료` remains a fixed path segment beneath it. No code change or MSI rebuild is required to update the exam root for a new year/exam.

### D18 — Drive folder naming: no new abbreviation without cause

Status: `DECIDED (APPROVED_INTENTIONAL_CHANGE, clarifies existing behavior)`

Final user contract:
Drive subject folder names use the full subject name (`[1차] 부동산학개론`, `[2차] 공인중개사법`, etc.) without abbreviation. The existing `공인중개사법 → 중개사법` abbreviation inside the week folder name (`backend/src/services/drive.py`'s `week_subject` substitution) is preserved only because removing it would break continuity with the user's existing Drive folder structure for that subject; this is the one documented exception and is not extended to any other subject.

### D19 — Colab connection URL: automatic rendezvous first, manual entry as fallback

Status: `DECIDED (APPROVED_INTENTIONAL_CHANGE, new area — MIGRATION_CONTRACT.md §9 only locks the 300s chunk/retry policy, not connection UX)`

Final user contract:
When Colab engine is selected, Sorigul polls for connection metadata written by the user's running Colab notebook (see Section 5, Colab rendezvous contract) and verifies it with a real `/health` call before showing "Colab 연결됨". A manual URL entry field remains available as an explicit fallback for when Drive auth is unavailable or automatic rendezvous fails, but it is not the primary flow and clipboard auto-detection is removed from the primary path.

### D20 — ffprobe dependency: remove in favor of a Python audio metadata library

Status: `DECIDED (APPROVED_INTENTIONAL_CHANGE, new area)`

Final user contract:
MP3 duration is read via a bundled Python library (`mutagen`, pending Phase 3 spike confirmation — see Section 8) rather than shelling out to `ffprobe.exe`. `ffmpeg.exe` remains required and bundled for actual 300-second chunk splitting (`backend/src/engines/colab.py`'s `ffmpeg -ss ... -t ...` cut, unaffected). Duration reads that fail return an honest "unknown" state rather than blocking transcription.

### D21 — Honest duration, progress, and ETA; no fabricated values

Status: `DECIDED (APPROVED_INTENTIONAL_CHANGE, reinforces `MIGRATION_CONTRACT.md` §6.1's existing "실제 처리 대상 수" denominator requirement, which was never fully implemented in the frontend)`

Final user contract:
Queue duration display uses the real MP3 duration (D20) or shows `—` on read failure — no fake numeric duration. Overall progress denominator is `Job.total_files` (already present in `JobModel`, `backend/src/domain/models.py`), not the folder's total MP3 count; files skipped because a valid bundle already exists are excluded from the denominator, consistent with the existing D01/D03 skip contract. Local ETA is either omitted (while too little history exists) or computed from observed processing speed for completed files in the current run — never a hardcoded string like "예상 남은 시간 12분". Colab ETA may use exact chunk-count progress (e.g. "3 / 5 구간") since chunk boundaries are already known.

### D22 — Course/subject/engine/exam-root persistence; Colab URL never persisted

Status: `DECIDED (APPROVED_INTENTIONAL_CHANGE, extends existing `RuntimeSettings`)`

Final user contract:
`RuntimeSettings` (`backend/src/services/settings.py`) gains persistent fields for: transcription folder, last course, last subject, last engine, Google Drive exam root folder (D17). Existing fields (`notifications`, `close_behavior`, `shutdown`) are unchanged. The Colab tunnel URL is never persisted to settings — it is rediscovered each session via rendezvous (D19) or re-entered manually. Drive auto-upload defaults to **off** on first run and after upgrade unless the user already has an explicit saved preference; this is a deliberate default chosen to avoid surprise cloud uploads, not a preservation of any prior default (none was previously locked).

## 3. Removed Legacy Features (final, do not re-open without new user decision)

| Feature | Status | Governing decision |
| --- | --- | --- |
| Whisper subject-specific prompt / `initial_prompt` profile | Not migrated | D13 |
| Common corrections / subject corrections / auto text replacement | Not migrated | D13 |
| Prompt/correction editing UI | Not migrated | D13 |
| MP3 upload / import / copy / move UI | Not migrated | D14 |
| MP3 in Google Drive upload bundle | Not migrated | D11 |
| Fixed course dropdown | Not migrated | D12 |
| Fixed subject alias dropdown as the primary classification path | Not migrated (fallback stage picker only, D16) | D12, D16 |
| Filename-reparsing as Drive classification truth | Not migrated | D15 |
| `ffprobe.exe` runtime dependency | Not migrated | D20 |
| Dashboard, Drive Queue, Resume, MYBOX, provider selector | Already excluded by `MIGRATION_CONTRACT.md` §16 — reaffirmed, not reopened | Prior contract |
| Whisper advanced controls, Colab chunk controls, global output folder | Already excluded by `MIGRATION_CONTRACT.md` §16 — reaffirmed, not reopened | Prior contract |
| STOPPED/CANCELLED state merge | Already rejected by D04 — reaffirmed, not reopened | Prior contract |

## 4. Retained Core Features (unchanged from `MIGRATION_CONTRACT.md`)

Filesystem-based Folders truth; 전체/완료/미완료/결과만 filters; TXT preview and full view; Explorer open; Log screen; file/job Desktop notifications; STOPPED/CANCELLED/CRASHED distinction; Retry; 다시 전사; safe output replacement; existing-result preservation; Drive-only retry; Tray; shutdown countdown; Google OAuth loopback; backend sidecar auto-start; Job Object orphan prevention. These carry forward from `MIGRATION_CONTRACT.md` §4, §13–16 with no change in this document.

## 5. Updated Data Contracts

### 5.1 Job metadata (new)

`JobModel` (`backend/src/domain/models.py`) gains job-level fields:

```
course: str
subject: str
stage: Literal["1차", "2차"]
```

And per-file metadata (new model, e.g. `FileMetadata`, keyed by file id):

```
week: Optional[str]
lesson: Optional[str]
normalized_name: Optional[str]
```

`CreateJobRequest` (`backend/src/api/routes.py`) gains `course: str` and `subject: str` (required), with `stage` derived server-side per D16 (auto for known subjects, otherwise supplied by the client after the fallback prompt).

### 5.2 Drive classification (revised)

`DriveClassifier.classify()` (`backend/src/services/drive.py`) changes signature from `classify(filename: str)` to something keyed on Job + file metadata (e.g. `classify(course: str, subject: str, week: str, lesson: str)`), sourced from D15's Job/file metadata rather than re-parsing `Path(filename).stem`. `DriveClassification.folders` continues to yield the same `(exam_root, "전사자료", course, "[stage] subject", "course_subject_Nweek")` tuple shape, with `exam_root` now sourced from Settings (D17) instead of the `DRIVE_ROOT_HIERARCHY` constant, and the upload path list (currently `[source, bundle.txt, bundle.json, bundle.srt]` in `DriveUploadService.upload()`) drops `source` (D11).

### 5.3 Filename identity (revised)

`ScannedFile.id` (`backend/src/domain/models.py`) is currently `file_path.stem` (`backend/src/services/scanner.py::FileScanner.scan()`), which breaks identity across rename since a rename changes the stem. Phase 1 must define a rename-stable id — see Section 6's exit condition and Section 8's investigation note. This document does not lock the specific mechanism (content hash, persisted id map, or path-plus-fingerprint); that remains a Phase 1 technical decision, deferred the same way `MIGRATION_CONTRACT.md` §17 defers D09's internal mechanism, provided the product contract (selection survives rename) is met.

### 5.4 Settings (revised)

`RuntimeSettings` / `SettingsPatch` (`backend/src/services/settings.py`) gain: `transcription_folder: Optional[str]`, `last_course: Optional[str]`, `last_subject: Optional[str]`, `last_engine: Optional[str]`, `drive_exam_root: str` (default: current hardcoded value), `drive_auto_upload: bool` (default `False`). Schema growth must stay backward-compatible: `SettingsManager._load()` already tolerates unknown/missing fields via Pydantic defaults and quarantines unparseable files — new fields must all have safe defaults so existing `settings.json` files load unchanged (no migration script needed, per Pydantic's additive-field behavior).

## 6. Phase 1 — Classification / Filename / Job

Purpose: implement D12, D15, D16, D22 (course/subject persistence only), and the rename-identity fix.

Expected files:
- `backend/src/domain/models.py` — add `course`, `subject`, `stage` to `JobModel`; add per-file metadata model; revise `ScannedFile.id` scheme
- `backend/src/services/scanner.py` — rename-stable id generation
- `backend/src/services/normalizer.py` — drop course/subject alias detection from the primary path (D12); keep week/lesson regex, forbidden-char cleanup, `+`→space, standard-name detection, first-free-lesson-number logic
- `backend/src/services/renamer.py` — bundle-safe rename must preserve/update the file's stable id mapping
- `backend/src/services/job_manager.py` — accept and store `course`/`subject`/`stage`, propagate per-file `week`/`lesson`/`normalized_name`
- `backend/src/services/settings.py` — add `last_course`, `last_subject` fields
- `backend/src/api/routes.py` — `CreateJobRequest` gains `course`/`subject`; `ScanRequest`/scan response surfaces stable ids
- `frontend/src/pages/TranscriptionPage.tsx` — course/subject text inputs, prefilled from last-used settings; stage fallback prompt when subject is unrecognized
- `frontend/src/api/client.ts` — request/response types for the above

Backend changes: new `FileMetadata` model; `JobManager` job-creation path stores course/subject/stage on the Job and week/lesson/normalized_name per file; `FileScanner` and `FilenameNormalizer` decoupled from Drive's `COURSES`/`SUBJECT_ALIASES` (that logic narrows to D16's known-subject → stage table only, relocated out of the alias-detection role).

Frontend changes: two free-text inputs (course, subject) above the folder picker or in a job-start panel; last-used values loaded from `GET /settings` and saved via `PUT /settings` on job start; a stage-selection dialog that appears only when the typed subject is not in the known-subject table.

Tauri changes: none expected.

Tests: normalizer unit tests updated to remove alias-detection assertions and add course/subject-passthrough assertions; a new rename-identity test that renames a scanned file and asserts the same logical file/selection still resolves after rescan; Job creation test asserting course/subject/stage/week/lesson land in `JobModel`/file metadata and survive retry.

Regression risk: any code path still assuming `ScannedFile.id == file stem` (e.g. `DriveUploadService.upload()`'s `FileScanner(job.folder).scan()` lookup by `item.id == file_id`) must be audited for the id-scheme change — flag as a Phase 1 sub-task, not a Phase 2 surprise.

Migration/data compatibility: existing persisted Jobs (`jobs.json`) predate `course`/`subject`/`stage` fields — they must load with those fields absent/`None` rather than failing validation; no destructive migration.

Completion condition: user-entered course/subject and file-detected week/lesson land in the same Job's metadata, and rename no longer breaks file selection across rescan.

Commit boundaries: (1a) domain model + scanner id scheme, (1b) normalizer alias-detection removal + tests, (1c) Job/API course-subject plumbing, (1d) frontend course/subject inputs + settings persistence, (1e) rename-identity regression test.

## 7. Phase 2 — Google Drive

Purpose: implement D11, D15, D17, D18.

Expected files:
- `backend/src/services/drive.py` — `DriveClassifier.classify()` re-keyed to Job/file metadata (D15); `DRIVE_ROOT_HIERARCHY` sourced from Settings (D17); `DriveUploadService.upload()` drops MP3 from the upload/preflight path list (D11)
- `backend/src/services/settings.py` — `drive_exam_root`, `drive_auto_upload` fields
- `backend/src/api/routes.py` — settings endpoints already generic; verify Drive status/response payload doesn't assume 4 files
- `frontend/src/pages/SettingsPage.tsx` — exam root text input; Drive auto-upload toggle (default off)
- `frontend/src/pages/TranscriptionPage.tsx` / a Drive status component — Drive path preview reflecting the 3-file bundle and configurable root

Backend changes: `DriveClassification.folders` built from Settings-sourced exam root + Job course/subject/stage + file week, not from filename re-parsing; upload path list becomes `[bundle.txt, bundle.json, bundle.srt]`.

Frontend changes: exam-root Settings field; Drive-only retry UI unaffected structurally (still targets TXT/JSON/SRT, now naturally excludes MP3); Drive auto-upload checkbox defaulting off with explicit save.

Tauri changes: none expected.

Tests: `DriveClassifier` unit tests rewritten for metadata-keyed input instead of filename-stem parsing; upload-path assertions updated to 3 files; preflight test confirming MP3 absence no longer blocks/no-ops a Drive upload; exam-root setting round-trip test.

Regression risk: any stored reference to `remote_ids` keyed by 4 filenames (`DriveFileState.remote_file_ids`) — existing persisted Drive state for jobs uploaded under the old 4-file contract must not crash on load; treat as read-compatible (dict with an extra/missing key is not a schema break).

Migration/data compatibility: no deletion of previously uploaded MP3s from Drive — this document does not retroactively clean up Drive; only new uploads follow the 3-file contract.

Completion condition: MP3 never reaches Drive, and TXT/JSON/SRT are correctly update-or-created under the configured exam root and Job-metadata-derived subject/stage/week folders.

Commit boundaries: (2a) Settings exam-root + auto-upload fields, (2b) `DriveClassifier` metadata-keyed rewrite + tests, (2c) upload path 4→3 file change + preflight tests, (2d) Settings UI for exam root and auto-upload toggle.

## 8. Phase 3 — Colab

Purpose: implement D19, D20; keep D08's 300-second chunk contract from `MIGRATION_CONTRACT.md` §9 unchanged.

Expected files:
- `backend/src/engines/colab.py` — replace `_probe_duration()`'s `ffprobe` subprocess call with a shared audio-metadata read (D20); keep the `ffmpeg -ss/-t` splitting subprocess unchanged
- `backend/src/utils/ffmpeg_runtime.py` — remove ffprobe resolution/requirement; keep ffmpeg resolution
- `backend/src/services/` — new `audio_metadata.py` (or similar) service wrapping `mutagen`, usable by both queue-duration display (Phase 4) and Colab chunk planning
- `backend/src/services/` — new Colab rendezvous service reading/polling a small JSON file (`colab_connection.json`) under the Sorigul runtime metadata folder
- `backend/src/api/routes.py` — Colab connection status endpoint(s) for the frontend to poll
- `frontend/src/pages/TranscriptionPage.tsx` — Colab connection state UI ("연결 대기 중" → "연결됨"), manual URL fallback field
- `frontend/src-tauri/` — none expected unless the rendezvous poll needs a Tauri-side file watch instead of backend polling (default: backend polls, since it already owns filesystem/Drive-adjacent I/O)

Backend changes: `AudioMetadataService.duration_seconds(path) -> Optional[float]` using `mutagen`, with a documented fallback (`None`) on read failure — never raises past the caller; a rendezvous poller that reads `colab_connection.json`, validates `schema_version`, `request_id` freshness/TTL, and calls `/health` before reporting `CONNECTED` — stale JSON alone is never sufficient.

Frontend changes: connection state machine (waiting → found URL → verifying health → connected / failed) and a manual-entry fallback gated behind "직접 URL 입력", not surfaced as the default control.

Tauri changes: only if rendezvous requires OS-level file watching beyond what the backend's own polling loop can do — default plan keeps this entirely in the backend, since the backend already owns Drive credential access needed to read the rendezvous file if the file lives in a Drive-synced or Drive-API-mediated location. Verify in Phase 3 spike whether `colab_connection.json` is exchanged via Drive API (consistent with Section 17's "Sorigul runtime metadata folder" being a Drive-hosted, small-file channel) or a local well-known path the Colab notebook cannot write to directly by definition — this affects whether Rust needs any involvement. Record the answer as a Phase 3 sub-decision before implementation.

Tests: `AudioMetadataService` unit tests (valid MP3, corrupt MP3, missing file → `None`); rendezvous freshness/TTL tests (stale JSON rejected, wrong `request_id` rejected, valid JSON + failing `/health` rejected, valid JSON + passing `/health` accepted); packaged-runtime validation that `mutagen` ships correctly and `ffprobe.exe` is no longer required by the installer.

Regression risk: `mutagen` may not read duration correctly for all MP3 encodings Legacy produced (VBR edge cases) — spike against a sample of real user MP3s before committing to the library; keep `Optional[float]` contract so a bad read degrades to `—` display rather than blocking transcription (consistent with D21).

Migration/data compatibility: none — this is a runtime dependency change, not a data format change.

Completion condition: opening and running the Colab notebook connects Sorigul without URL copy/paste, and packaged Local/Colab transcription work without `ffprobe.exe` present.

Commit boundaries: (3a) `AudioMetadataService` + tests, (3b) `_probe_duration` replacement in `colab.py` + `ffmpeg_runtime.py` ffprobe removal, (3c) rendezvous service + tests, (3d) frontend Colab connection UI + manual fallback.

## 9. Phase 4 — Runtime UX

Purpose: implement D20 (duration display), D21 (progress/ETA honesty).

Expected files:
- `frontend/src/pages/TranscriptionPage.tsx` — replace hardcoded `duration: '—'` (line ~33) with real duration from `AudioMetadataService` via scan response; replace any fixed/fake ETA text with the honest computation described in D21
- `backend/src/api/routes.py` / `backend/src/services/scanner.py` — surface duration in the scan response payload
- `backend/src/services/job_manager.py` — expose per-run observed processing speed (elapsed / files done) for ETA computation, and confirm `total_files`/`done_files`/`failed_files` already exclude skipped-complete files (verify against D01/D03 skip contract, `MIGRATION_CONTRACT.md` §6.1–6.2)
- `frontend/src/pages/TranscriptionPage.tsx`, Colab chunk display — chunk-based progress ("3 / 5 구간") sourced from `AudioChunk` count already present in `backend/src/engines/colab.py`

Backend changes: scan response includes `duration_seconds: Optional[float]`; Job model already has `total_files`/`done_files`/`failed_files` (`backend/src/domain/models.py`) — Phase 4 is primarily verifying these are correctly denominator-scoped (excluding auto-skipped complete files) and wiring them to the frontend, not adding new fields.

Frontend changes: remove all hardcoded progress/ETA strings; render `—` when duration or ETA is unavailable rather than a fabricated number; Colab progress renders exact chunk fractions.

Tauri changes: none expected.

Tests: scan-response duration field test; ETA-omitted-when-no-history test; ETA-present-and-plausible-when-history-exists test; denominator test confirming auto-skipped complete files are excluded from `total_files`.

Regression risk: low — this phase mostly removes fabricated UI values and wires already-existing backend fields (`JobModel.total_files` etc. already exist per Section 5.1's baseline read) rather than introducing new state.

Migration/data compatibility: none.

Completion condition: no fake progress percentage, no fixed ETA string, no unconditional `—` placeholder for duration appear in the running app.

Commit boundaries: (4a) scan-response duration wiring + frontend display, (4b) honest Local ETA computation + tests, (4c) Colab chunk-based progress display, (4d) denominator audit/fix if needed.

## 10. Phase 5 — Release Validation

Purpose: full regression against this refined contract before any release claim, mirroring the rigor of the existing `docs/release/FINAL_FEATURE_PARITY_REGRESSION.md` and `docs/runtime/INSTALLER_INSTALLED_RUNTIME_VALIDATION.md` precedents but scoped to the decisions in this document plus everything already locked.

Included: full automated regression; fresh sidecar build; fresh MSI; exact hashes; installed Program Files smoke test; backend health check; no Python dependency required on the target machine; no backend console window; forced-kill cleanup (Job Object orphan prevention, already-retained per Section 4); real MP3 through Local; real MP3 through Direct Colab (rendezvous + chunking); Google Drive TXT/JSON/SRT-only upload verification (no MP3 present in the resulting Drive folder); Folders screen against real disk state; retry flows (Local and Colab); normal-exit cleanup.

Explicit prohibition carried from the operating instructions: actual Windows shutdown must not be executed without the user's immediate, explicit approval at the time of that specific test step — this applies to Phase 5 execution, not to this Phase 0 document.

Completion condition: every item above passes on a freshly built, freshly installed MSI, with the 3-file Drive contract, direct-input course/subject, auto Colab rendezvous, and honest duration/progress all verified end-to-end.

Commit boundaries: (5a) regression suite updates reflecting Phase 1–4 contract changes, (5b) fresh build/install artifacts and hash record, (5c) final validation report doc (naming to follow the existing `docs/release/` convention, e.g. `CORE_WORKFLOW_REFINEMENT_REGRESSION.md`).

## 11. Test Strategy

- Unit tests travel with each Phase's commits (see Sections 6–10) — no phase closes without its own tests landing in the same phase.
- Contract-level tests (rename identity, Drive 3-file bundle, denominator correctness) are written as integration tests against the backend, not just unit tests of isolated functions, since these are exactly the areas where prior implementation (filename-keyed id, filename-reparsed classification) silently violated the intended contract.
- No UI automation framework changes are proposed here; manual UI verification against `docs/design/UI_STATE_MATRIX.md` states remains the existing pattern for this project and is reused, not replaced.
- Phase 5 reuses the existing installed-runtime validation pattern (`docs/runtime/INSTALLER_INSTALLED_RUNTIME_VALIDATION.md`) rather than inventing a new validation format.

## 12. Data Safety

No phase deletes: user MP3, TXT, JSON, SRT, Whisper model cache, Google OAuth credential, Google Drive token, settings, jobs, or runtime history. Specifically:

- Phase 1's rename-identity fix must not delete or orphan any file during rename — it only changes how the *id* is derived/tracked, not the rename mechanics already locked in `MIGRATION_CONTRACT.md` §10.1 (same-stem bundle rename, no overwrite).
- Phase 2's MP3-removal-from-Drive-bundle is upload-scope-only — it does not retroactively delete MP3s already uploaded to Drive by prior versions, and it does not touch the local MP3 at all (it was never uploaded from local disk to begin with; D11 only stops future uploads).
- Phase 3's ffprobe removal must not affect existing chunk manifests or resume/failure-recovery state (`ChunkManifest` in `backend/src/engines/colab.py`) — this is a duration-read path change, not a manifest schema change.
- Settings schema growth (Section 5.4) must remain additive — new optional fields with safe defaults — so pre-existing `settings.json` continues to load without a migration step, per `SettingsManager`'s existing tolerant-load/quarantine behavior.
- Runtime data location `%LOCALAPPDATA%\Sorigul\` is unchanged by this plan.

## 13. Git / Commit Strategy

- Work happens on `feature/core-workflow-refinement`, branched from `validation/full-feature-parity-release` @ `47aa500b5453e42f186292b41d9b8054f96bc638`.
- No `git add .` / `git add -A` — every commit stages named files.
- No `git reset --hard`, `git clean`, `git rebase`, `git merge`, or force push in this workflow.
- No direct commits to `main`.
- Phase 0 (this document) is committed as documentation-only.
- Each future Phase (1–5) is implemented in its own set of commits per the Commit Boundaries listed in Sections 6–10, sub-stepped (a/b/c/...) when a single phase step is large, matching this project's existing Phase/Task branch convention (`docs/project/DEVELOPMENT_RULES.md` "Git workflow").
- No implementation commit lands as part of Phase 0.

## 14. Exit Criteria

Phase 0 (this document) is exit-ready when:

- `docs/migration/CORE_WORKFLOW_REFINEMENT_PLAN.md` exists with all 14 sections and is internally consistent with `MIGRATION_CONTRACT.md`'s still-valid sections.
- Every conflict between this document and prior locked contracts (D11, D12, D15) is explicitly marked `SUPERSEDED_BY_PRODUCT_DECISION` with the exact superseded document/line identified — not silently overwritten.
- Every new-area decision (D13, D14, D16–D22) is explicitly marked `APPROVED_INTENTIONAL_CHANGE`.
- `MIGRATION_CONTRACT.md`, `FEATURE_PARITY.md`, and `LEGACY_FEATURE_PARITY_AUDIT.md` carry non-destructive amendment notices pointing here for the superseded lines (Section 2's D11/D12/D15 entries), without deleting their original evidence/content.
- No Python/React/Rust/test/installer/dependency file is touched.
- The branch is pushed for review; `main` is untouched.
- Release-ready status is not claimed, and Phase 1 implementation does not start, until explicit follow-up instruction.
