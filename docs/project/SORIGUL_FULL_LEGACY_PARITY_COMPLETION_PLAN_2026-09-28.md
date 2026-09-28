# Sorigul Full Legacy Parity Rebaseline & Completion Plan

Date: 2026-09-28  
Status: CANONICAL COMPLETION PLAN CANDIDATE  
Audit issue: #109  
Legacy baseline: `bongbong90/jeonsa_doumi@fbc86313a179a62a586386551f99384a9fce5fc8`  
Sorigul planning base: `test/korean-real-speech-fixture@81acb9dfbb324719bd7780c432d5aec1da328aab`

---

## 1. Why this rebaseline exists

Sorigul must not be completed by repeatedly patching isolated defects after they become visible in a test screen.

The completion baseline is rebuilt from four evidence sources:

1. the actual Legacy `jeonsa_doumi` runtime/source and validation history;
2. the current Sorigul source;
3. explicit product decisions made by the user across the 전사프로그램 conversations;
4. current non-negotiable operating constraints: lightweight packaging, zero-cost execution, user-data safety, and full Git/GitHub traceability.

Default rule:

> Legacy ACTIVE user-visible behavior and functional contracts are preserved unless an explicit later user decision changed them.

Internal implementation may change. Silent product behavior changes may not.

---

## 2. Evidence hierarchy

When sources conflict, use this order:

1. explicit later user decision from 전사프로그램 conversation history;
2. current locked Sorigul product decision that can be tied to such a user decision;
3. actual Legacy runtime code / active validation evidence;
4. historical design/research documents;
5. current Sorigul implementation.

Current Sorigul code is never itself proof that a product change was intended.

A new deviation requires:

`Evidence → Conflict → Options → Impact → User Decision → Contract Lock`.

---

## 3. Non-negotiable project constraints

### 3.1 Study-use goal

Target is `STUDY USE READY`, not public distribution optimization.

No public GitHub Release is required.

### 3.2 Zero-cost

Never automatically use or enable:

- paid transcription APIs;
- paid GPU services;
- cloud credits;
- billing activation;
- paid tunnel fallback;
- paid resource fallback.

If zero-cost safety cannot be established, the external gate remains pending. The feature is not deleted.

### 3.3 Lightweight architecture

The Phase 2/#46 architecture is preserved:

```text
Core Sorigul
- Tauri / React
- FastAPI Core
- Job/File/State
- Colab client
- Drive
- Folders / Log / Desktop UX
- FFmpeg
        |
        +-- versioned Local Whisper Runtime
            - OpenAI Whisper
            - torch / CUDA
            - Local-only heavyweight payload
```

Never restore torch/CUDA/Whisper into the Core MSI.

Historical #46 evidence:
- Core sidecar: 35.05 MiB
- staged Core + FFmpeg: 118.63 MiB
- MSI: 66.81 MiB
- Local Runtime: separate, ~1911 MiB
- Core reduction vs old sidecar: 98.18%

After source remediation, these historical results remain valid history but are not current-HEAD evidence. Fresh revalidation is #113.

### 3.4 Git/GitHub lifecycle

Every development work unit follows #107:

`Issue → branch → implementation/review → tests → commit → push → PR → Issue/#7 update → approved merge gate`.

No completed work is left only in a local working tree.

Do not use:
- `git add .`
- `git add -A`
- force push
- rebase
- `reset --hard`
- `git clean`

No premature main merge.

### 3.5 User-data safety

Never commit or automatically delete:
- real MP3;
- TXT/JSON/SRT user results;
- Whisper model cache;
- OAuth credentials/tokens;
- runtime job data;
- installers/build artifacts.

Actual Windows shutdown is executed only after immediate explicit user approval for that exact test.


### 3.6 Hard delivery deadline — usable before November 2026

The product must be usable for the user's daily study **before 2026-11-01 KST**.

Planning target:
- **2026-10-20:** installed daily-use beta — Local transcription and core desktop workflow usable on the user's PC
- **2026-10-27:** release-candidate study build — all source remediation and installed integration complete; zero-cost external paths validated when safely available
- **2026-10-30:** final STUDY USE workflow regression
- **2026-10-31:** contingency / Git closeout / bottom-up merge window

This is a schedule constraint, not permission to cut required Legacy parity silently.

To protect the deadline, until STUDY USE READY:
- no new product features outside the approved parity/completion plan;
- no cosmetic redesign unless it blocks actual use;
- no architecture refactor that is not required for a known blocker;
- no public-release/signing work;
- documentation polish stays behind functional blockers;
- build/install is done at meaningful gates, not after every small source change;
- an external zero-cost dependency that is unavailable must not prevent the Local path from being usable.

Critical-path order:
1. #107/#112 governance and canonical contract
2. #106 transcription-engine parity
3. #110/#111 remaining Legacy parity gaps
4. source-level full regression
5. #113 fresh lightweight current-HEAD build/install
6. #56/#63 installed desktop integration
7. #47 actual Local study audio as soon as suitable user audio is available
8. #48/#60 zero-cost Colab/Drive validation, started early enough to leave recovery time
9. #59 recovery policy
10. #58 shutdown only with immediate explicit approval
11. #114 final STUDY USE regression
12. #54/#55 docs closeout and bottom-up merge

Schedule rule:
If a blocker threatens the 2026-10-31 deadline, record the blocker in GitHub immediately and work only the minimum safe fix needed to restore the approved contract. Do not substitute a different engine, paid service, destructive shortcut, or feature deletion to meet the date.

---

## 4. Canonical product contract after Legacy + conversation decisions

This section distinguishes preserved Legacy behavior from explicit approved changes.

### 4.1 Preserve from Legacy

#### Core file workflow

- user selects a transcription folder;
- top-level MP3 scan only; no recursive scan;
- selected-file execution plus “nothing selected = all incomplete” confirmation flow;
- valid completed TXT/JSON/SRT bundle is skipped;
- invalid/incomplete bundle is not treated as DONE;
- outputs live beside the MP3 with the same stem;
- explicit re-transcription is available;
- old valid results survive until replacement output validates successfully;
- one file failure does not destroy successful files or prevent later files when the failure is file-local.

#### Filename handling

- Korean/long filenames;
- page/download-name cleanup behavior that still applies under the approved free-text course/subject model;
- week/lesson detection;
- standard-name protection;
- MP3/TXT/JSON/SRT collision awareness;
- next available lesson allocation;
- safe same-stem bundle rename / rollback behavior.

#### Job / recovery

- progress and clear state;
- STOPPED and CANCELLED remain distinct;
- both are retryable;
- DONE files remain preserved/skipped during retry;
- CRASHED after abnormal exit;
- manual retry for CRASHED;
- atomic persistence;
- corrupt state quarantine;
- completed results preserved across restart.

#### Local

- OpenAI Whisper `medium`;
- local CUDA preferred;
- GPU/model-load failure → CPU fallback;
- Legacy-compatible fp16 automatic decision and fp16 failure fallback;
- locked decoding options:
  - `language="ko"`
  - `task="transcribe"`
  - `temperature=0`
  - `beam_size=5`
  - `best_of=5`
  - `patience=1.0`
  - `condition_on_previous_text=False`.

#### Colab engine identity

- Colab transcription engine remains `faster-whisper`;
- model remains `large-v3`;
- CUDA preferred in Colab;
- CUDA compute type `float16`;
- CPU fallback compute type `int8`;
- Korean transcription;
- segment timestamps returned and merged into TXT/JSON/SRT.

#### Results / Folders

- actual filesystem is canonical;
- filters: all / complete / incomplete / results;
- TXT preview;
- full TXT view;
- open/reveal folder/file;
- external file changes must be reflected by the product.

#### Desktop

- file-complete notification;
- job-complete notification;
- Legacy-equivalent notification path to open/reveal the result folder;
- Tray;
- close-to-tray / exit behavior;
- completed-job shutdown policy;
- immediate / 15 sec / 30 sec;
- countdown and cancel;
- backend auto-start and cleanup;
- Unicode/Korean paths;
- no orphan backend/process tree.

### 4.2 Approved Intentional Changes from conversation history

These are not parity bugs.

#### Dashboard → structured Log

Legacy statistics Dashboard is removed by explicit user decision.

Sorigul navigation/product direction uses:
- Transcription
- Log
- Folders
- Settings

Do not restore the statistics Dashboard as a parity “fix”.

#### Drive 4 files → 3 files

Legacy uploaded MP3/TXT/JSON/SRT.

The user later explicitly changed Sorigul to:

- TXT
- JSON
- SRT

only.

The original MP3 is not uploaded/imported/moved by Sorigul.

Keep:
- `update_or_create`;
- Drive failure independent from Local DONE;
- local results preserved on Drive failure.

Issue #108 was created from incomplete context and was corrected/closed after recovering the direct user decision. Remaining real external validation stays in #48.

#### Prompt/corrections removed

Legacy subject-specific prompts/corrections and automatic text substitution are intentionally not migrated.

Engine decoding options are separate and remain locked.

#### MP3 import/move removed

Sorigul does not import/copy/move MP3 into a managed folder.

The user places MP3 into the selected transcription folder through the OS. Sorigul scans and processes it.

#### Course/subject model

Course and subject are free-text user input, not Legacy fixed aliases/dropdowns on the primary path.

Week/lesson remain filename-derived.

Known subject stage is inferred; unknown exact subject can have a persisted 1차/2차 override.

#### Drive classification

New Jobs use Job/file metadata as classification truth.

Legacy persisted Jobs without metadata may use the narrow compatibility fallback.

Exam root is configurable.

The existing `공인중개사법 → 중개사법` week-folder continuity exception remains documented; it is not generalized.

#### Colab connection UX

Auto rendezvous is primary.

Manual URL entry remains fallback.

Old clipboard URL auto-detection/persistence is not required as the primary path.

#### Colab chunk/recovery policy

- internal 300-second chunking;
- chunk internals hidden from user UI;
- FAILED may reuse verified completed chunks internally;
- initial request + max one automatic retry per chunk;
- STOP/CANCEL does not reuse current-file chunk progress;
- CANCEL ends as CANCELLED.

This is the approved Sorigul contract even where older Legacy documents mention different chunk behavior.

#### Duration/progress

Use real audio metadata; current approved implementation uses `mutagen` and keeps `ffmpeg` for actual chunk splitting.

No fabricated duration/progress/ETA.

Colab chunk counts/durations are not exposed to users.

#### Drive auto-upload

Per-run checkbox only.

Defaults OFF each app launch.

Never persisted.

#### Security hardening

Keep current greenfield security improvements, including:
- signed Colab requests;
- pairing/replay protection;
- private OAuth/token handling;
- strict local/runtime boundaries;
- fail-closed security behavior;
- no broad arbitrary shell/filesystem permissions.

These may differ internally from Legacy but must not remove approved product capability.

### 4.3 Explicit exclusions

Do not restore:
- deprecated Google Drive Queue product path;
- archived backup/POC paths;
- old experimental UI engines;
- public release/signing requirements as STUDY USE blockers;
- paid fallback paths.

---

## 5. Full parity re-audit result at current planning head

Legend:
- `COVERED`: current source materially implements the contract;
- `DEFECT`: implementation contradicts the canonical contract;
- `MISSING`: required capability absent;
- `APPROVED_CHANGE`: differs from Legacy by explicit decision;
- `PENDING_INSTALLED`: source exists but current-head installed evidence needed;
- `PENDING_EXTERNAL`: real external service validation pending;
- `PENDING_INPUT`: requires real user input that does not currently exist.

| Area | Current verdict | Notes / issue |
| --- | --- | --- |
| top-level MP3 scan | COVERED | scanner is non-recursive |
| selected/all-incomplete Start | COVERED | D01 confirmation flow implemented |
| complete bundle skip | COVERED | TXT/JSON/SRT validation |
| explicit re-transcribe | COVERED | UI action + safe replacement flow |
| filename normalization / conflict | COVERED | preflight + user resolution |
| bundle rename / rollback | COVERED | MP3/TXT/JSON/SRT transaction |
| per-file failure continuation | COVERED | success files preserved; batch summary |
| STOP / CANCEL / Retry | COVERED source | installed integrated QA still #63 |
| CRASHED persistence/retry | COVERED source | installed/restart QA #63 |
| atomic jobs persistence / corrupt quarantine | COVERED | fail-closed storage behavior |
| Local `medium` | COVERED | split Local Runtime |
| Local CUDA/CPU fallback | COVERED | #46 CUDA synthetic passed |
| Local fp16 Legacy parity | DEFECT | current runtime uses CUDA=>fp16 directly; fix #106 |
| Colab infrastructure/chunk/security | COVERED source | current 300s/signed/rendezvous structure |
| Colab engine/model identity | DEFECT | current bootstrap uses OpenAI Whisper medium; must be faster-whisper large-v3; #106 |
| Colab UI label/internal jargon | DEFECT | current user-visible medium/Direct Colab wording; #106 |
| Drive OAuth/client/status | COVERED source | real account mutation pending #48 |
| Drive 3-file bundle | APPROVED_CHANGE | TXT/JSON/SRT is the current approved contract |
| Drive update-or-create | COVERED source | external create/update validation #48 |
| Drive failure isolation | COVERED source | Local DONE remains independent |
| Folders filters/preview/full/open | COVERED source | installed QA #56/#63 |
| real filesystem canonical results | COVERED on refresh | live change detection gap below |
| transcription-folder live change detection | MISSING | Legacy QFileSystemWatcher-equivalent; #111 |
| structured Log | APPROVED_CHANGE | replaces statistics Dashboard |
| desktop notifications | COVERED source | actual installed validation #56 |
| notification folder-open action | MISSING | Legacy-equivalent action absent; #110 |
| Tray / close behavior | COVERED source | current-head installed QA #56 |
| shutdown source/countdown/cancel | COVERED source | actual shutdown pending #58 |
| post-start backend recovery | POLICY/QA OPEN | #59 |
| sidecar health/ownership/Job Object | HISTORIC PASS | fresh current-head gate #113 |
| Core lightweight split | HISTORIC PASS | #46; must survive remediation |
| MSI / Unicode / cleanup | HISTORIC PASS | fresh current-head #113 + #56/#63 |
| actual Local personal study MP3 | PENDING_INPUT | #47 |
| actual zero-cost Colab | PENDING_EXTERNAL | #48/#60 |
| actual Drive OAuth/API mutation | PENDING_EXTERNAL | #48 |
| prompt/corrections | APPROVED_CHANGE | intentionally removed |
| MP3 import/move | APPROVED_CHANGE | intentionally removed |
| Legacy statistics Dashboard | APPROVED_CHANGE | intentionally removed |
| deprecated Drive Queue | EXCLUDED | do not restore |

---

## 6. Newly identified non-patchwork gaps

The re-audit adds two Legacy behaviors that were not safely covered by the old 43-item matrix or current source:

### #110 Notification folder-open action

Current Sorigul sends real desktop notification title/body but does not expose the Legacy-equivalent folder-open action.

Restore the capability using the current safe Explorer/open-intent boundary. Do not reintroduce broad shell permissions.

### #111 Live transcription-folder change detection

Legacy used `QFileSystemWatcher`.

Current Sorigul correctly reads disk truth when refreshed, but does not yet preserve the live-change user behavior.

Restore an equivalent greenfield watcher/poll mechanism scoped only to the selected transcription folder.

These are implementation gaps, not reasons to copy Legacy architecture.

---

## 7. Source-of-truth correction

The repository contains historical documents that remain valuable evidence but can conflict with later decisions.

Example:
- early Legacy/migration docs: Drive MP3/TXT/JSON/SRT;
- direct later user decision: Drive TXT/JSON/SRT only.

Issue #112 owns a durable supersession/source-of-truth map.

Historical material is not deleted. It is clearly marked as historical/superseded where necessary.

---

## 8. Execution plan

Do not rebuild/install after every small source fix. Complete source-level remediation first, then produce one fresh current-head artifact set.

### Workstream 0 — Rebaseline plan — #109

This document.

Deliverables:
- complete evidence baseline;
- current gap matrix;
- issue mapping;
- final execution order.

No production source change.

### Workstream 1 — Governance / canonical contract

Issues:
- #107 mandatory Git/GitHub lifecycle
- #112 canonical contract/supersession map

Deliverables:
- repository governance docs explicitly require the lifecycle;
- current contract map clearly distinguishes Legacy / approved change / deprecated / current study-use constraints.

Purpose:
prevent another implementation from taking current code or stale docs as product truth.

### Workstream 2 — Transcription engine parity

Issue:
- #106

Required:
- Local remains OpenAI Whisper medium in separate Local Runtime;
- restore Legacy-compatible fp16 decision/fallback;
- Colab becomes faster-whisper large-v3;
- CUDA float16 / CPU int8;
- health identifies/validates compatible engine/model;
- retain signed FastAPI/pairing/rendezvous;
- retain 300s internal chunk/retry/cancel contract;
- fix user-facing engine labels;
- never put Local heavyweight runtime back into Core/MSI.

No real external Colab execution in this source work unit.

### Workstream 3 — Auxiliary Legacy parity

Issues:
- #110 notification folder-open
- #111 live folder change detection

Implement each as its own work unit/PR.

Do not combine their independent commits/Issues.

### Workstream 4 — Source-level full contract regression

After #106/#110/#111 and governance source changes:

Run full source regression against:
- all preserved Legacy ACTIVE contracts;
- all approved intentional changes;
- zero-cost fail-closed rules;
- lightweight packaging exclusions;
- security boundaries.

Any newly found defect gets its own Issue before fixing.

No “fix while auditing without Issue”.

### Workstream 5 — Fresh current-HEAD lightweight installed gate

Issue:
- #113

One fresh current HEAD:
- Local Runtime;
- Core;
- MSI;
- clean install;
- provenance;
- archive exclusion;
- sizes;
- CUDA synthetic;
- health;
- Job Object;
- FFmpeg;
- Unicode;
- process cleanup;
- fail-closed runtime negatives.

Acceptance:
- Core/MSI do not contain torch/CUDA/Whisper/Local Runtime;
- size regression ceiling remains <=250 MiB;
- no orphan;
- no user data touched.

### Workstream 6 — Installed Desktop integration

Issues:
- #56
- #63

Validate the same installed artifact:
- Tray;
- close behavior;
- folder picker;
- Explorer reveal;
- notification;
- #110 notification interaction;
- #111 live folder changes;
- Folders scan/preview/full view;
- FAILED/STOPPED/CANCELLED/CRASHED retry;
- result preservation;
- process cleanup.

### Workstream 7 — External zero-cost paths

Issues:
- #48
- #60

#### Colab

Only if the session can be confirmed as zero-cost:
- faster-whisper large-v3;
- actual GPU when available;
- short audio;
- long/chunk audio;
- merge;
- TXT/JSON/SRT;
- retry/cancel;
- no paid tunnel or managed fallback.

If safe free execution cannot be established:
`PENDING_ZERO_COST_EXTERNAL_VALIDATION`.

#### Drive

Current approved bundle:
- TXT
- JSON
- SRT

Validate:
- OAuth;
- credential/token protection;
- create;
- update same parent/name;
- timeout/failure;
- Local DONE + Drive FAILED;
- persistence after app restart;
- no MP3 upload;
- no billing activation/paid fallback.

### Workstream 8 — Real personal Local study gate

Issue:
- #47

Current state:
`PENDING_REAL_AUDIO`.

5A controlled real Korean speech remains valid supporting evidence, but does not close #47.

When real personal study audio becomes available:
- installed app;
- actual Local CUDA;
- short then long;
- TXT/JSON/SRT;
- Folders;
- completed skip;
- result preservation.

Do not fabricate this evidence using synthetic/repeated speech.

### Workstream 9 — Backend recovery policy

Issue:
- #59

Current recommended personal-use direction:
- clear OFFLINE state after post-start failure;
- explicit user reconnect/restart;
- preserve job/results;
- no infinite automatic restart daemon unless a real need is demonstrated.

Lock and validate the final behavior.

### Workstream 10 — Actual shutdown

Issue:
- #58

Source/countdown/cancel tests first.

Actual `shutdown.exe` test only after the user explicitly approves it at that moment.

### Workstream 11 — Final STUDY USE workflow

Issue:
- #114

One installed artifact must exercise the whole product:
- scan;
- normalization;
- Local/Colab;
- progress/ETA;
- Stop/Cancel/Retry/CRASHED;
- outputs;
- Folders;
- Drive;
- Log;
- notifications;
- Tray;
- live folder changes;
- cleanup;
- Unicode;
- approved shutdown check.

Verdict:
`STUDY WORKFLOW REGRESSION = PASS`.

### Workstream 12 — Docs / Git closeout / merge

Issues:
- #54 README
- #55 canonical developer test command
- #7 tracker
- #107/#112 documentation closeout
- any remaining work-unit issues

Then:
- verify every stacked PR diff/base;
- keep evidence commits;
- bottom-up merge only after #114 PASS;
- no rebase/force push;
- no public GitHub Release required.

---

## 9. Issue map

### Existing / active

- #47 actual personal Local MP3
- #48 zero-cost Colab/Drive external
- #54 root README
- #55 developer test command
- #56 installed Windows Native UX
- #58 actual shutdown
- #59 backend recovery policy
- #60 Quick Tunnel operational limitation
- #63 installed Folders/retry/cleanup QA
- #106 engine parity
- #107 Git/GitHub lifecycle
- #109 full rebaseline/audit
- #110 notification folder-open
- #111 live folder change detection
- #112 canonical contract/supersession
- #113 fresh current-head lightweight installed gate
- #114 final Study Workflow Regression

### Corrected historical issue

- #108: closed as duplicate after recovering the direct user-approved 3-file Drive decision. The remaining external validation belongs to #48.

### Historical evidence retained

- #46 installed synthetic PASS at prior source
- #97 lightweight architecture gate
- #99 Local Runtime source split
- #104 controlled Korean real-speech fixture

These remain valid historical evidence and must not be rewritten as current-HEAD validation after source changes.

---

## 10. PR strategy

Current stack remains unmerged.

The rebaseline plan branch is stacked on top of the completed 5A branch.

Future source work is stacked in execution order.

For every PR:
- exact parent branch;
- exact work-unit scope only;
- no unrelated fixes;
- tests in body;
- Issue links;
- OPEN until final approved merge sequence.

Main merge only after #114 PASS and final closeout review.

---

## 11. Final STUDY USE READY definition

Sorigul is `STUDY USE READY = YES` only when:

1. every Legacy ACTIVE behavior is either:
   - preserved and validated, or
   - explicitly replaced by a user-approved Intentional Change;
2. no known unapproved parity defect remains;
3. Local = OpenAI Whisper medium, local CUDA preferred, approved fallback behavior;
4. Colab = faster-whisper large-v3 under the approved Sorigul chunk/security model;
5. TXT/JSON/SRT generation/validation is reliable;
6. Drive = approved TXT/JSON/SRT bundle, update-or-create, failure isolation;
7. file/job/retry/recovery contracts pass;
8. Folders/Log/notification/Tray/shutdown contracts pass;
9. live folder behavior and notification folder-open parity are restored;
10. Core remains lightweight and Local Runtime remains separate;
11. zero-cost guarantees are preserved;
12. fresh current-head installed artifact passes;
13. final study workflow regression passes;
14. all development work has traceable Issue/commit/push/PR/Tracker history;
15. user data remains intact.

Public release readiness is not a project completion criterion.
