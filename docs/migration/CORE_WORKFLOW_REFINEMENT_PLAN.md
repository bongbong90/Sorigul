# Sorigul Core Workflow Refinement Plan

Status: `LOCKED` (Phase 0 — documentation only, no implementation)

Branch: `feature/core-workflow-refinement`
Base: `validation/full-feature-parity-release` @ `47aa500b5453e42f186292b41d9b8054f96bc638`

> **Correction pass (2026-08-29, Phase 0.1):** before Phase 1 started, this plan's own first draft was reviewed and corrected in place — over-engineered scope was cut, one internal contract inconsistency was fixed, and several gaps were closed. Corrected/added: D21 no longer exposes Colab chunk counts in the UI (was inconsistent with the already-locked D08 chunk-invisibility contract); D22/D23A drop the planned persistent `drive_auto_upload` setting in favor of a per-run, never-persisted checkbox; D16 gains the `subject_stage_overrides` persistence needed to actually satisfy its own "ask once" contract; Section 5.3's planned global stable-file-ID redesign is replaced by a narrower rename-transaction id remap (D23B, D24, D25, D26 add input validation, mismatch-warning, legacy-Job-compatibility, and Colab-side-artifact/URL-normalization requirements that the first draft omitted). Superseded/replaced text is marked inline rather than deleted; nothing here changes D11, D12, D15, or any decision in `MIGRATION_CONTRACT_REVIEW.md`.

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

Status: `DECIDED (APPROVED_INTENTIONAL_CHANGE, extends D12/D15)` — **corrected 2026-08-29** to specify how "once per new subject value" is actually satisfied.

Final user contract:
Known subjects map to stage automatically: 1차 = {부동산학개론, 민법}; 2차 = {공인중개사법, 부동산공법, 부동산공시법, 부동산세법}. When the user's typed subject does not match any known subject, Sorigul asks the user to pick 1차 or 2차 as a fallback. The default UI flow does not ask for stage on every run — only when the subject is unrecognized and stage cannot be inferred.

To make "once" real rather than aspirational, the answer is persisted: `RuntimeSettings` (see Section 5.4) stores `subject_stage_overrides: Dict[str, "1차" | "2차"]`, keyed by the exact subject string after trimming leading/trailing whitespace — no alias inference, no fuzzy matching, no reintroduction of Legacy's alias table. On a later job with the same trimmed subject string, Sorigul reads the override instead of asking again. A minimal edit affordance (not a separate management screen) lets the user change a previously-picked stage for a given subject value — e.g. an inline "1차/2차 변경" control next to the subject field when an override exists for the current typed subject. No bulk-management UI is introduced.

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

### D21 — Honest duration, progress, and ETA; no fabricated values; no chunk internals in UI

Status: `DECIDED (APPROVED_INTENTIONAL_CHANGE, reinforces `MIGRATION_CONTRACT.md` §6.1's existing "실제 처리 대상 수" denominator requirement, which was never fully implemented in the frontend)` — **corrected 2026-08-29** to remove a chunk-count UI example that violated D08's existing "chunk ON/OFF나 chunk seconds 설정을 사용자 UI에 노출하지 않는다" contract (`MIGRATION_CONTRACT.md` §9.1).

Final user contract:
Queue duration display uses the real MP3 duration (D20) or shows `—` on read failure — no fake numeric duration. Overall progress denominator is `Job.total_files` (already present in `JobModel`, `backend/src/domain/models.py`), not the folder's total MP3 count; files skipped because a valid bundle already exists are excluded from the denominator, consistent with the existing D01/D03 skip contract. Local ETA is either omitted (while too little history exists) or computed from observed processing speed for completed files in the current run — never a hardcoded string like "예상 남은 시간 12분".

Colab progress may be *computed internally* from chunk completion (chunk boundaries are already known — see `MIGRATION_CONTRACT.md` §9.1), but the internal chunk unit itself is never surfaced to the user. The user only ever sees: a progress percentage, elapsed time, and an ETA — never "3 / 5 구간", "chunk 3/5", "300초 조각", or any other chunk-count/chunk-duration phrasing. This is not a new restriction; it is this document correctly applying D08's already-locked chunk-invisibility contract to the progress/ETA display, which the original D21 text drafted in this plan's first version had inconsistently violated.

### D22 — Course/subject/engine/exam-root persistence; Colab URL and Drive auto-upload never persisted

Status: `DECIDED (APPROVED_INTENTIONAL_CHANGE, extends existing `RuntimeSettings`)` — **corrected 2026-08-29** to remove `drive_auto_upload` as a persistent field (see D23A) and to specify non-destructive migration of the existing `sorigul.transcriptionFolder` localStorage value.

Final user contract:
`RuntimeSettings` (`backend/src/services/settings.py`) gains persistent fields for: transcription folder, last course, last subject, last engine, Google Drive exam root folder (D17), and `subject_stage_overrides` (D16). Existing fields (`notifications`, `close_behavior`, `shutdown`) are unchanged. The Colab tunnel URL is never persisted to settings — it is rediscovered each session via rendezvous (D19) or re-entered manually. Google Drive auto-upload is **not** a persistent setting at all — see D23A; it is a per-run choice made fresh every launch.

Frontend currently persists the selected transcription folder client-side under the `sorigul.transcriptionFolder` `localStorage` key (`frontend/src/api/client.ts`'s `FOLDER_STORAGE_KEY`). When backend `transcription_folder` becomes the settings source of truth, the first read after upgrade must not simply ignore this existing value: if backend `transcription_folder` is empty/unset and a `sorigul.transcriptionFolder` localStorage value exists, Sorigul non-destructively adopts that value into the backend setting on first use, so the user's already-selected folder does not appear to vanish after upgrade. `localStorage` is not deleted immediately — a transition-period fallback read is allowed until the backend setting is confirmed populated.

### D23A — Google Drive auto-upload: per-run checkbox, never persisted

Status: `DECIDED (APPROVED_INTENTIONAL_CHANGE)` — corrects the original Phase 0 draft, which had proposed `drive_auto_upload` as a persistent `RuntimeSettings` field (`SUPERSEDED_BY_PRODUCT_DECISION` relative to this document's own first version, not relative to `MIGRATION_CONTRACT.md`).

Final user contract:
The Transcription screen carries a per-run "전사 완료 후 Google Drive 업로드" checkbox (this is `CreateJobRequest.upload_to_drive`, `backend/src/api/routes.py`, which already exists as a per-job field — no backend field addition needed here). It defaults to unchecked every time the app starts, regardless of what the user chose in a previous run. It is never written to `RuntimeSettings` and never restored from a prior session. This reduces both the surprise-upload risk and the settings surface, replacing the originally-planned global persistent toggle.

### D23B — Course/subject input validation

Status: `DECIDED (APPROVED_INTENTIONAL_CHANGE, new area — course/subject become filename components under D12, so they need the same safety net filenames already require)`

Final user contract:
Because course and subject feed directly into the generated filename (`{course}_{subject}_{N주차}_{M강}`), free-text input is constrained before it is accepted:
- leading/trailing whitespace is trimmed
- empty string (after trim) is rejected
- control characters are rejected
- Windows forbidden filename characters are rejected: `< > : " / \ | ? *`
- a trailing dot or trailing space (both invalid at the end of a Windows filename component) is rejected

Ordinary Korean/English/digit/space input is accepted. Underscore (`_`) is additionally rejected — it is the reserved structural delimiter in the generated filename (`{course}_{subject}_{N주차}_{M강}`), so allowing it inside course/subject would make the course/subject boundary unrecoverable when a standard-form filename is re-parsed. On rejection, Sorigul asks the user to correct the input — it never silently substitutes, strips, or replaces invalid characters on the user's behalf. This mirrors the "user confirms, never silent substitution" principle already locked for filename normalization uncertainty in `MIGRATION_CONTRACT.md` §10.2.

### D24 — Standard-name / typed course-subject mismatch: warn, never silently reroute

Status: `DECIDED (APPROVED_INTENTIONAL_CHANGE, new area)`

Final user contract:
When a file's name is already in standard form (`{course}_{subject}_{N}주차_{M}강.mp3`) and the course/subject embedded in that existing filename differ from the course/subject currently typed for the job, Sorigul does not silently rename the file, does not silently overwrite the file's stored classification metadata, and does not silently route the Drive upload to the newly-typed subject's folder. It shows an explicit mismatch warning and requires the user to resolve it (keep the file's existing course/subject, or confirm the retype and let normalization apply it) before that file proceeds. Local transcription itself is not blocked by an unresolved mismatch — only the classification/rename side is held — but if Drive upload is requested for that file, upload does not proceed to a possibly-wrong folder until the mismatch is resolved.

### D25 — Legacy Job Drive-retry compatibility: fallback filename parsing is legacy-only

Status: `DECIDED (APPROVED_INTENTIONAL_CHANGE, new area — narrows D15's scope to new Jobs only)`

Final user contract:
D15 (Job/file metadata as Drive classification truth) governs every **new** Job created after Phase 1/2 ship. For a **pre-existing** persisted Job that predates `course`/`subject`/`stage`/file metadata (see Section 5.1's backward-compatibility note) and is Drive-retried after upgrade, Sorigul may fall back to parsing the file's already-standard filename to recover a classification — but only for that legacy compatibility path, never as part of the new-Job classification flow, and never reintroducing Legacy's alias-guessing table beyond the same known-subject set D16 already locks. If the legacy file's name cannot be safely classified this way, Drive upload for that file fails with `CLASSIFICATION_FAILED` exactly as today, and the file's Local `DONE` status is left untouched — consistent with `MIGRATION_CONTRACT.md` §12's Local/Drive independence.

### D26 — Colab-side rendezvous artifact and URL normalization are in scope

Status: `DECIDED (APPROVED_INTENTIONAL_CHANGE, new area, extends D19)`

Final user contract:
D19's automatic rendezvous cannot work from Desktop-side code alone — something running inside the user's Colab notebook has to write the connection metadata Desktop polls for. Since no such artifact currently exists in this repository, producing one (a small, greenfield Sorigul-authored Colab notebook cell or bootstrap script — not a copy/import of any Legacy source) implementing the writer side of rendezvous is explicitly in Phase 3 scope, not assumed to already exist. It writes only `schema_version`, `request_id`, `url`, `status`, `updated_at`, `expires_at` — never MP3, transcript, token, or credential data, matching D19/Section 5's metadata shape.

Both the auto-discovered URL and the manual-entry fallback are normalized to a bare base URL before use: `https://host`, `https://host/`, `https://host/health`, and `https://host/transcribe` all normalize to `https://host`, and the health/transcribe calls are then built as `{base}/health` / `{base}/transcribe` — never producing a doubled path such as `/health/health` or `/transcribe/transcribe`.

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
| Chunk count / chunk-duration wording in user-visible progress (e.g. "3 / 5 구간") | Not migrated — corrected out of this plan's own D21 draft | D21, D08 (`MIGRATION_CONTRACT.md` §9.1) |
| Persistent global Drive auto-upload setting | Not migrated — corrected out of this plan's own D22 draft, replaced by per-run checkbox | D23A |
| Global stable file-ID redesign (content hash / inode / persisted ID map) | Not migrated — corrected out of this plan's own Phase 1 draft, replaced by rename-transaction id remap | Section 5.3 |
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

`CreateJobRequest` (`backend/src/api/routes.py`) gains `course: str` and `subject: str` (required), with `stage` derived server-side per D16 (auto for known subjects, otherwise supplied by the client after the fallback prompt, using `subject_stage_overrides` when the subject has been resolved before — see D16, Section 5.4).

Backward compatibility: the new `course`/`subject`/`stage` `JobModel` fields and the new per-file metadata model are `Optional`/default-populated so that a pre-existing `jobs.json` written before this change loads without validation failure — absent metadata is treated as "legacy Job, no metadata," not as a corrupt record. New Job creation always populates these fields; only already-persisted Jobs may legitimately lack them. See D25 for how legacy Jobs without this metadata are handled specifically in Drive retry.

### 5.2 Drive classification (revised)

`DriveClassifier.classify()` (`backend/src/services/drive.py`) changes signature from `classify(filename: str)` to something keyed on Job + file metadata (e.g. `classify(course: str, subject: str, week: str, lesson: str)`), sourced from D15's Job/file metadata rather than re-parsing `Path(filename).stem`. `DriveClassification.folders` continues to yield the same `(exam_root, "전사자료", course, "[stage] subject", "course_subject_Nweek")` tuple shape, with `exam_root` now sourced from Settings (D17) instead of the `DRIVE_ROOT_HIERARCHY` constant, and the upload path list (currently `[source, bundle.txt, bundle.json, bundle.srt]` in `DriveUploadService.upload()`) drops `source` (D11).

### 5.3 Filename identity (revised — corrected 2026-08-29, no global ID redesign)

`ScannedFile.id` (`backend/src/domain/models.py`) is currently `file_path.stem` (`backend/src/services/scanner.py::FileScanner.scan()`). The first version of this plan proposed replacing this scheme entirely (content hash, inode, or a persisted id map) so that ids survive rename. That is now explicitly rejected as over-engineering for what the actual failure is: **stem-based `id` is kept as-is.** `FileScanner`, `JobManager`, and `DriveUploadService`'s existing `item.id == file_id` lookups are not touched.

Instead, the fix lives entirely in the rename transaction: the rename endpoint (`POST /rename`, `backend/src/api/routes.py` → `backend/src/services/renamer.py`) returns both the `old_file_id` and the resulting `new_file_id` (the new stem) in its response. The frontend, on a successful rename, immediately replaces the old id with the new id inside `selectedIds` (and any other local id-keyed state) *before* triggering a rescan — so when the rescan lands, the already-updated selection matches the new stem and the same logical file stays selected. No identity survives across an app restart or a rescan the frontend didn't just trigger itself from a rename it initiated; that is out of scope, because the actual user-facing failure this fixes is exactly "I renamed and now my selection is gone," not general persistent cross-session file identity.

This also constrains scope directly: normalization rename only ever happens before Job creation, as part of the raw-MP3 → rename → rescan → select → start flow. Once a Job exists for a file, that Job's normalization rename does not re-run — a file mid-Job is not subject to this remap path.

### 5.4 Settings (revised — corrected 2026-08-29)

`RuntimeSettings` / `SettingsPatch` (`backend/src/services/settings.py`) gain: `transcription_folder: Optional[str]`, `last_course: Optional[str]`, `last_subject: Optional[str]`, `last_engine: Optional[str]`, `drive_exam_root: str` (default: current hardcoded value), `subject_stage_overrides: Dict[str, Literal["1차", "2차"]]` (default `{}`, keyed by trimmed exact subject string — D16). `drive_auto_upload` is explicitly **not** added here — see D23A; Drive auto-upload stays a per-job field on `CreateJobRequest` (`upload_to_drive`, already present) and is never read from or written to `RuntimeSettings`. Schema growth must stay backward-compatible: `SettingsManager._load()` already tolerates unknown/missing fields via Pydantic defaults and quarantines unparseable files — new fields must all have safe defaults so existing `settings.json` files load unchanged (no migration script needed, per Pydantic's additive-field behavior). `transcription_folder`'s first-run population additionally follows the non-destructive `localStorage` adoption described in D22.

### 5.5 Course/subject input validation (new)

See D23B for the full rule set (trim, non-empty, no control characters, no Windows-forbidden characters, no trailing dot/space). Validation is enforced server-side in the Job-creation path (`CreateJobRequest` validation in `backend/src/api/routes.py` or a dedicated validator called from `JobManager`) so it cannot be bypassed by a frontend that forgets to check; the frontend additionally validates inline for immediate feedback. Rejection is always explicit and correctable by the user — never a silent character substitution.

## 6. Phase 1 — Classification / Filename / Job

Purpose: implement D12, D15, D16 (including `subject_stage_overrides` persistence), D22's `transcription_folder` migration, D23B (input validation), D24 (standard-name mismatch warning), and the rename-selection fix described in Section 5.3 (explicitly **not** a global stable-id redesign).

Expected files:
- `backend/src/domain/models.py` — add `course`, `subject`, `stage` to `JobModel` (all `Optional`/default for backward compatibility, see Section 5.1); add per-file metadata model. `ScannedFile.id` scheme is **unchanged** (still `file_path.stem`).
- `backend/src/services/scanner.py` — no id-scheme change.
- `backend/src/services/normalizer.py` — drop course/subject alias detection from the primary path (D12); keep week/lesson regex, forbidden-char cleanup, `+`→space, standard-name detection, first-free-lesson-number logic; add course/subject input validation (D23B); add standard-name-vs-typed-course/subject mismatch detection (D24)
- `backend/src/services/renamer.py` — bundle-safe rename unchanged in mechanics; rename endpoint response gains `old_file_id`/`new_file_id` (Section 5.3) — no id-mapping storage introduced
- `backend/src/services/job_manager.py` — accept and store `course`/`subject`/`stage`, propagate per-file `week`/`lesson`/`normalized_name`; surface D24 mismatch state to the caller instead of silently proceeding
- `backend/src/services/settings.py` — add `transcription_folder`, `last_course`, `last_subject`, `subject_stage_overrides` fields
- `backend/src/api/routes.py` — `CreateJobRequest` gains `course`/`subject` (validated per D23B); `POST /rename` response gains `old_file_id`/`new_file_id`
- `frontend/src/pages/TranscriptionPage.tsx` — course/subject text inputs with inline validation, prefilled from last-used settings; stage fallback prompt (with inline override-edit affordance) when subject is unrecognized or previously overridden; mismatch warning UI (D24); rename-response id remap into `selectedIds` before rescan (Section 5.3)
- `frontend/src/api/client.ts` — request/response types for the above; on first load, read backend `transcription_folder` and, if empty, fall back to and adopt the existing `sorigul.transcriptionFolder` `localStorage` value (`FOLDER_STORAGE_KEY`) into the backend setting (D22) rather than dropping it

Backend changes: new `FileMetadata` model; `JobManager` job-creation path stores course/subject/stage on the Job and week/lesson/normalized_name per file; `FileScanner` and `FilenameNormalizer` decoupled from Drive's `COURSES`/`SUBJECT_ALIASES` (that logic narrows to D16's known-subject → stage table only, relocated out of the alias-detection role); course/subject validated per D23B before a Job is created; a standard-named file whose embedded course/subject disagrees with the typed course/subject is flagged (D24) rather than silently renamed/reclassified.

Frontend changes: two free-text inputs (course, subject) above the folder picker or in a job-start panel, with immediate validation feedback (D23B); last-used values loaded from `GET /settings` and saved via `PUT /settings` on job start; a stage-selection dialog that appears only when the typed subject is not in the known-subject table and has no existing override, plus a minimal inline "변경" affordance when an override already exists (D16); a mismatch warning surfaced per-file when D24 triggers, requiring explicit user resolution before that file's classification/rename/Drive-routing proceeds; on rename success, the frontend swaps the renamed file's id inside `selectedIds` using the endpoint's `old_file_id`/`new_file_id` response before the next rescan (Section 5.3) — Job creation only happens after this settles.

Tauri changes: none expected.

Tests: normalizer unit tests updated to remove alias-detection assertions and add course/subject-passthrough assertions; input-validation tests for each D23B rule (empty, control char, each forbidden character, trailing dot/space); a rename-selection test that renames a scanned file via the endpoint and asserts the frontend's id remap keeps the same logical file selected across the following rescan (replacing the previous "global stable id" test framing with a transaction-scoped one); a mismatch-warning test (standard-named file, differing typed course/subject, confirms warning fires and neither rename nor Drive routing silently proceeds); Job creation test asserting course/subject/stage/week/lesson land in `JobModel`/file metadata and survive retry, including a test that a legacy Job record missing these fields still loads.

Regression risk: none from an id-scheme change, since none is happening — this was the primary risk in the plan's first draft and is now eliminated by keeping `ScannedFile.id` as-is. Remaining risk is narrower: the rename-response contract change (`old_file_id`/`new_file_id` added to `POST /rename`) must not break any caller assuming the old response shape — check `frontend/src/api/client.ts`'s rename call site.

Migration/data compatibility: existing persisted Jobs (`jobs.json`) predate `course`/`subject`/`stage` fields — they must load with those fields absent/`None` rather than failing validation; no destructive migration. Existing `sorigul.transcriptionFolder` `localStorage` value is adopted into the backend setting on first post-upgrade read, not discarded (D22).

Completion condition: user-entered course/subject (validated per D23B) and file-detected week/lesson land in the same Job's metadata; rename no longer breaks file selection across rescan via the id-remap transaction (not a global id redesign); a pre-existing `sorigul.transcriptionFolder` selection survives upgrade; a standard-named file with a course/subject mismatch against the typed values is warned, never silently rewritten.

Commit boundaries: (1a) domain model course/subject/stage fields + backward-compatible load, (1b) normalizer alias-detection removal + input validation + tests, (1c) Job/API course-subject plumbing, (1d) rename endpoint id-remap response + frontend selection remap + regression test, (1e) frontend course/subject inputs + settings persistence + localStorage folder migration, (1f) mismatch-warning detection + UI + test, (1g) `subject_stage_overrides` persistence + inline override-edit affordance.

## 7. Phase 2 — Google Drive

Purpose: implement D11, D15, D17, D18, D23A (per-run upload checkbox, not a persistent setting), D25 (legacy Job Drive-retry fallback).

Expected files:
- `backend/src/services/drive.py` — `DriveClassifier.classify()` re-keyed to Job/file metadata (D15) for new Jobs, with a legacy-only fallback path for pre-metadata Jobs (D25); `DRIVE_ROOT_HIERARCHY` sourced from Settings (D17); `DriveUploadService.upload()` drops MP3 from the upload/preflight path list (D11)
- `backend/src/services/settings.py` — `drive_exam_root` field only (**not** `drive_auto_upload` — see D23A, Section 5.4)
- `backend/src/api/routes.py` — settings endpoints already generic; verify Drive status/response payload doesn't assume 4 files; `CreateJobRequest.upload_to_drive` (already existing per-job field) remains the sole auto-upload control
- `frontend/src/pages/SettingsPage.tsx` — exam root text input only; **no** Drive auto-upload toggle added here
- `frontend/src/pages/TranscriptionPage.tsx` — per-run "전사 완료 후 Google Drive 업로드" checkbox, unchecked by default on every launch, bound to `CreateJobRequest.upload_to_drive`; Drive path preview reflecting the 3-file bundle and configurable root

Backend changes: `DriveClassification.folders` built from Settings-sourced exam root + Job course/subject/stage + file week, not from filename re-parsing, for any Job created after this ships; a narrow, explicitly-labeled legacy-compatibility path in `DriveClassifier` that only activates when a Job lacks the new metadata (pre-upgrade persisted Job) and falls back to standard-filename parsing per D25 — this path must not be reachable from new-Job creation; upload path list becomes `[bundle.txt, bundle.json, bundle.srt]`.

Frontend changes: exam-root Settings field (Settings screen); per-run Drive-upload checkbox on the Transcription screen, never persisted, always defaulting to unchecked (D23A); Drive-only retry UI unaffected structurally (still targets TXT/JSON/SRT, now naturally excludes MP3).

Tauri changes: none expected.

Tests: `DriveClassifier` unit tests rewritten for metadata-keyed input instead of filename-stem parsing (new-Job path); a separate legacy-fallback test suite covering: standard-named legacy Job → successful fallback classification, non-standard-named legacy Job → `CLASSIFICATION_FAILED` with Local `DONE` preserved (D25); upload-path assertions updated to 3 files; preflight test confirming MP3 absence no longer blocks/no-ops a Drive upload; exam-root setting round-trip test; a test asserting `RuntimeSettings` never gains a `drive_auto_upload` field and the per-run checkbox resets to unchecked across a simulated app restart.

Regression risk: any stored reference to `remote_ids` keyed by 4 filenames (`DriveFileState.remote_file_ids`) — existing persisted Drive state for jobs uploaded under the old 4-file contract must not crash on load; treat as read-compatible (dict with an extra/missing key is not a schema break). The legacy-fallback classification path (D25) is itself a regression-risk surface if its guard leaks into the new-Job path — test explicitly that a new Job with complete metadata never falls through to filename parsing even if parsing would have succeeded.

Migration/data compatibility: no deletion of previously uploaded MP3s from Drive — this document does not retroactively clean up Drive; only new uploads follow the 3-file contract. Legacy Jobs without course/subject/stage metadata remain retryable via the D25 fallback rather than becoming permanently unclassifiable after upgrade.

Completion condition: MP3 never reaches Drive; TXT/JSON/SRT are correctly update-or-created under the configured exam root and Job-metadata-derived subject/stage/week folders for new Jobs; legacy Jobs retain a working (if narrower) Drive-retry path; no global Drive auto-upload setting exists anywhere in `RuntimeSettings`.

Commit boundaries: (2a) Settings exam-root field (no auto-upload field), (2b) `DriveClassifier` metadata-keyed rewrite + tests, (2c) upload path 4→3 file change + preflight tests, (2d) legacy-fallback classification path + tests (D25), (2e) Settings UI for exam root + per-run Drive-upload checkbox on Transcription screen.

## 8. Phase 3 — Colab

Purpose: implement D19, D20, D26 (Colab-side rendezvous artifact, URL normalization); keep D08's 300-second chunk contract from `MIGRATION_CONTRACT.md` §9 unchanged, including chunk-invisibility (reaffirmed by D21's correction).

Expected files:
- `backend/src/engines/colab.py` — replace `_probe_duration()`'s `ffprobe` subprocess call with a shared audio-metadata read (D20); keep the `ffmpeg -ss/-t` splitting subprocess unchanged; centralize base-URL normalization (D26) used for both `/health` and `/transcribe` calls
- `backend/src/utils/ffmpeg_runtime.py` — remove ffprobe resolution/requirement; keep ffmpeg resolution
- `backend/src/services/` — new `audio_metadata.py` (or similar) service wrapping `mutagen`, usable by both queue-duration display (Phase 4) and Colab chunk planning
- `backend/src/services/` — new Colab rendezvous service reading/polling a small JSON file (`colab_connection.json`) under the Sorigul runtime metadata folder
- `backend/src/api/routes.py` — Colab connection status endpoint(s) for the frontend to poll
- `frontend/src/pages/TranscriptionPage.tsx` — Colab connection state UI ("연결 대기 중" → "연결됨"), manual URL fallback field with the same normalization applied client-side before submission
- `frontend/src-tauri/` — none expected unless the rendezvous poll needs a Tauri-side file watch instead of backend polling (default: backend polls, since it already owns filesystem/Drive-adjacent I/O)
- **new: a Colab-side artifact** (D26) — a Sorigul-authored notebook cell or bootstrap script, greenfield (not copied/imported from Legacy), implementing the `/health` and `/transcribe` endpoints already specified by the Direct Colab protocol plus the rendezvous *writer* half: it writes `colab_connection.json` with `schema_version`, `request_id`, `url`, `status`, `updated_at`, `expires_at` to wherever Phase 3's spike (below) determines Desktop reads it from. This is a real Phase 3 deliverable, not an assumption that such an artifact already exists — none currently does in this repository.

Backend changes: `AudioMetadataService.duration_seconds(path) -> Optional[float]` using `mutagen`, with a documented fallback (`None`) on read failure — never raises past the caller; a rendezvous poller that reads `colab_connection.json`, validates `schema_version`, `request_id` freshness/TTL, and calls `/health` before reporting `CONNECTED` — stale JSON alone is never sufficient; a shared URL-normalization function applied to both the rendezvous-discovered URL and the manually-entered URL, collapsing `https://host`, `https://host/`, `https://host/health`, `https://host/transcribe` all to `https://host` before building `{base}/health` / `{base}/transcribe`, so a doubled path (`/health/health`, `/transcribe/transcribe`) cannot occur regardless of what the user or the notebook wrote.

Frontend changes: connection state machine (waiting → found URL → verifying health → connected / failed) and a manual-entry fallback gated behind "직접 URL 입력", not surfaced as the default control; manual entry is normalized identically to the auto-discovered path before being sent to the backend.

Tauri changes: only if rendezvous requires OS-level file watching beyond what the backend's own polling loop can do — default plan keeps this entirely in the backend, since the backend already owns Drive credential access needed to read the rendezvous file if the file lives in a Drive-synced or Drive-API-mediated location. Verify in Phase 3 spike whether `colab_connection.json` is exchanged via Drive API (consistent with Section 17's "Sorigul runtime metadata folder" being a Drive-hosted, small-file channel) or a local well-known path the Colab notebook cannot write to directly by definition — this affects whether Rust needs any involvement, and also determines where the Colab-side artifact (above) writes to. Record the answer as a Phase 3 sub-decision before implementation.

Tests: `AudioMetadataService` unit tests (valid MP3, corrupt MP3, missing file → `None`); rendezvous freshness/TTL tests (stale JSON rejected, wrong `request_id` rejected, valid JSON + failing `/health` rejected, valid JSON + passing `/health` accepted); URL normalization tests covering all four input shapes in D26 collapsing to the same base and producing non-doubled `/health`/`/transcribe` paths, for both the rendezvous-discovered and manually-entered cases; packaged-runtime validation that `mutagen` ships correctly and `ffprobe.exe` is no longer required by the installer; an end-to-end check that the Colab-side artifact's writer output is readable by the Desktop-side rendezvous poller (schema round-trip).

Regression risk: `mutagen` may not read duration correctly for all MP3 encodings Legacy produced (VBR edge cases) — spike against a sample of real user MP3s before committing to the library; keep `Optional[float]` contract so a bad read degrades to `—` display rather than blocking transcription (consistent with D21). The Colab-side artifact is new surface area with no prior version to regress against — its own correctness (health/transcribe protocol conformance, rendezvous write correctness) is the primary risk, not a regression of existing behavior.

Migration/data compatibility: none — this is a runtime dependency change, not a data format change.

Completion condition: opening and running the Colab-side artifact connects Sorigul without URL copy/paste; packaged Local/Colab transcription work without `ffprobe.exe` present; all four URL input shapes normalize identically with no doubled paths.

Commit boundaries: (3a) `AudioMetadataService` + tests, (3b) `_probe_duration` replacement in `colab.py` + `ffmpeg_runtime.py` ffprobe removal, (3c) URL normalization function + tests, (3d) rendezvous service (reader/poller) + tests, (3e) Colab-side rendezvous writer artifact, (3f) frontend Colab connection UI + manual fallback.

## 9. Phase 4 — Runtime UX

Purpose: implement D20 (duration display), D21 (progress/ETA honesty).

Expected files:
- `frontend/src/pages/TranscriptionPage.tsx` — replace hardcoded `duration: '—'` (line ~33) with real duration from `AudioMetadataService` via scan response; replace any fixed/fake ETA text with the honest computation described in D21
- `backend/src/api/routes.py` / `backend/src/services/scanner.py` — surface duration in the scan response payload
- `backend/src/services/job_manager.py` — expose per-run observed processing speed (elapsed / files done) for ETA computation, and confirm `total_files`/`done_files`/`failed_files` already exclude skipped-complete files (verify against D01/D03 skip contract, `MIGRATION_CONTRACT.md` §6.1–6.2)
- `frontend/src/pages/TranscriptionPage.tsx`, Colab progress display — percentage/elapsed/ETA computed internally from `AudioChunk` completion already present in `backend/src/engines/colab.py`, but the chunk unit itself is never rendered to the user (D21, D08)

Backend changes: scan response includes `duration_seconds: Optional[float]`; Job model already has `total_files`/`done_files`/`failed_files` (`backend/src/domain/models.py`) — Phase 4 is primarily verifying these are correctly denominator-scoped (excluding auto-skipped complete files) and wiring them to the frontend, not adding new fields; Colab progress computation may use chunk completion internally but its output to the frontend is a percentage/ETA value, not a chunk count.

Frontend changes: remove all hardcoded progress/ETA strings; render `—` when duration or ETA is unavailable rather than a fabricated number; Colab progress renders as percentage/elapsed/ETA only — no "N / M 구간", "chunk", or "300초" wording anywhere in the UI (D21 correction, reaffirming D08's existing chunk-invisibility lock).

Tauri changes: none expected.

Tests: scan-response duration field test; ETA-omitted-when-no-history test; ETA-present-and-plausible-when-history-exists test; denominator test confirming auto-skipped complete files are excluded from `total_files`; a UI-content test/lint asserting no chunk-count or "300초" string appears in Colab progress rendering (D21 correction).

Regression risk: low — this phase mostly removes fabricated UI values and wires already-existing backend fields (`JobModel.total_files` etc. already exist per Section 5.1's baseline read) rather than introducing new state.

Migration/data compatibility: none.

Completion condition: no fake progress percentage, no fixed ETA string, no unconditional `—` placeholder for duration, and no chunk-count/chunk-duration wording appear in the running app.

Commit boundaries: (4a) scan-response duration wiring + frontend display, (4b) honest Local ETA computation + tests, (4c) Colab percentage/elapsed/ETA progress display with no chunk-unit exposure, (4d) denominator audit/fix if needed.

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
- Every new-area decision (D13, D14, D16–D26) is explicitly marked `APPROVED_INTENTIONAL_CHANGE`.
- `MIGRATION_CONTRACT.md`, `FEATURE_PARITY.md`, and `LEGACY_FEATURE_PARITY_AUDIT.md` carry non-destructive amendment notices pointing here for the superseded lines (Section 2's D11/D12/D15 entries), without deleting their original evidence/content.
- No Python/React/Rust/test/installer/dependency file is touched.
- The branch is pushed for review; `main` is untouched.
- Release-ready status is not claimed, and Phase 1 implementation does not start, until explicit follow-up instruction.
