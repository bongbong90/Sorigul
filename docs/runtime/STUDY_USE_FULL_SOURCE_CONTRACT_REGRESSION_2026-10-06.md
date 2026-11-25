# Final Full Source Contract Regression — 2026-10-06 control / 2026-10-07 execution

Issue: [#123](https://github.com/bongbong90/Sorigul/issues/123)
Branch: `audit/123-final-source-regression-rerun`
Parent: `docs/pre-freeze-plan-reconciliation`
Requested report/control date: 2026-10-06 KST. Actual execution: **2026-10-07 KST**.
Production source changes: **NONE**. Merge: **NONE**.

## Exact identity and scope

| Identity | Value |
|---|---|
| Exact start HEAD | `87d7b1e72840335eaa3baa1e7b805a01a8fe329e` |
| Exact final audited product-source HEAD | `87d7b1e72840335eaa3baa1e7b805a01a8fe329e` — no production/test/contract change |
| Final audit/report commit HEAD | The containing commit, resolved by `git log -1 --format=%H -- docs/runtime/STUDY_USE_FULL_SOURCE_CONTRACT_REGRESSION_2026-10-06.md`; its full SHA is recorded after commit in #123, #7, #116, PR #115, the dedicated audit PR and PR #185 |
| Final candidate identity | Audit branch HEAD = `integration/study-use-final-candidate` HEAD = PR #185 HEAD after normal fast-forward; the new report commit itself is the candidate HEAD |
| Integration PR | [#185](https://github.com/bongbong90/Sorigul/pull/185), base main, OPEN / DO NOT MERGE |
| Reconciliation evidence PR | [#186](https://github.com/bongbong90/Sorigul/pull/186), OPEN / DO NOT MERGE |
| Legacy baseline | `bongbong90/jeonsa_doumi@fbc86313a179a62a586386551f99384a9fce5fc8` |
| Repository change | This report only; exact staging |
| Installed/artifact evidence | Older `780dbb1` artifact is historical only; no current artifact PASS claimed |

A Git commit cannot contain its own literal SHA without changing that SHA. The exact audited source SHA above is literal; the exact containing audit SHA is bound through Git and the read-back GitHub checkpoints, rather than a circular or stale embedded SHA. This report is fixed evidence, not a new product contract.

## Authority and method

Priority used:

1. [CURRENT_PRODUCT_CONTRACT](../project/CURRENT_PRODUCT_CONTRACT.md), including #180 and §9/§10.
2. Its §11 supersession map and [CURRENT_SOURCE_OF_TRUTH](../project/CURRENT_SOURCE_OF_TRUTH.md).
3. [DEVELOPMENT_RULES](../project/DEVELOPMENT_RULES.md).
4. [ROADMAP](../project/ROADMAP.md), current Pre-Freeze order.
5. [Completion plan](../project/SORIGUL_FULL_LEGACY_PARITY_COMPLETION_PLAN_2026-09-28.md), current execution/governance sections.
6. Preserved Legacy ACTIVE evidence: [337-file inventory](STUDY_USE_FULL_SOURCE_CONTRACT_REGRESSION_2026-09-29_LEGACY_INVENTORY.md), fixed-baseline read-only checkout, `gui_main.py`, `auto_transcribe.py`, `filename_normalizer.py`, active backend/Drive/notebook evidence.
7. Current implementation and executable regression tests.

The [2026-09-30 report](STUDY_USE_FULL_SOURCE_CONTRACT_REGRESSION_2026-09-30.md) is historical evidence/template only and was not changed. The current inventory was rebuilt by capability, with separate rows for the newly locked manual-week, remediation, security, packaging, concurrency and governance obligations. The old 90-row total/counts were not copied or used as a target. Legacy code was read, never copied/imported into Sorigul.

Every current source row is supported by the relevant implementation inspection and full executable suite; focused suites repeat the high-risk source contracts. Implementation was not used to approve a product difference. Native/CUDA/actual audio/external behavior remains routed to its real validation gate. An earlier #114 Issue-body reference to bottom-up merge is an old subordinate planning statement, superseded unambiguously by current §10, DEVELOPMENT_RULES, ROADMAP, current Completion Plan, #7/#116 and #185. Refresh that original wording at #114 before its final merge review; it gives no present merge authority.

## Evidence key

All paths below are relative to the repository root. Codes in the matrix identify concrete source/test families.

| Key | Current implementation inspected | Fresh executable evidence |
|---|---|---|
| F | `backend/src/services/scanner.py`; `backend/src/api/routes.py`; `frontend/src/pages/TranscriptionPage.tsx`, FolderSection/QueueTable | backend `test_core.py`, `test_transcription_runner.py`; root `test_folder_picker_reconcile.py`, `test_confirmation_preflight_lifecycle.py`, `test_180_manual_week_frontend.py` |
| N | `backend/src/services/normalizer.py`, `renamer.py`; routes request validation; ClassificationSection; `frontend/src/lib/preflight.ts`; TranscriptionPage | backend `test_manual_week_normalization.py`, `test_filename_normalizer_parity.py`, `test_job_api_classification.py`; root #180/#170/#171 suites |
| J | job_manager, transcription_runner, output_bundle, routes, domain models/transcription | backend runner/local/output/core/global_single_run/process_recovery suites |
| L | `backend/src/local_runtime_main.py`, `engines/local_whisper.py` | `test_local_and_output.py`, `test_sidecar_cuda_contract.py`, runner tests; synthetic child protocol and fake engines, no actual model inference |
| C | `backend/src/engines/colab.py`, colab_security/rendezvous/url; `colab/sorigul_colab_bootstrap.py`; colabSetup | colab_engine/bootstrap_security/rendezvous/package_c_security; root colab_open_convenience |
| D | `backend/src/services/drive.py`, classification/settings; routes; TranscriptionPage | drive_results_desktop/drive_oauth_loopback/classification/job_api_classification/manual_week/package_c_security |
| U | results/folder_revision/desktop_state; FoldersPage/LogPage/folderSort/useFolderRevision | txt_display_encoding_fallback/folder_revision/package_d_ux_integrity/drive_results_desktop; root folders_sort/live_folder_change |
| T | App/useTrayProgress/useDesktopNotifications; Rust lib/close_guard/tray_tooltip/completion_toast/sidecar/shutdown/windows_system | root tray_progress/#174/#168/active_run_close/notification; backend close_guard/desktop/process suites; Rust **83** tests |
| S | loopback Host/CORS, Colab signing, runtime discovery, private ACL, safe stems/intents, Windows tools, Tauri CSP/capabilities, packaging scripts read only | package_c_security/colab_bootstrap_security/loopback_host_security/tauri_csp_security/windows_system_utilities/release_packaging; actual synthetic PS5 Restricted/process fixtures; root trusted_tools/loopback/preflight/bootstrap contract fixtures |
| K | Core/Local specs/requirements, runtime manifest discovery, build scripts/installer inspected without invoking builds | local_and_output/release_packaging/sidecar_cuda/installer_powershell5_restricted_invocation/core_powershell5_process_observation; root core_workflow_release/release_readiness |
| G | current contract/supersession, rules/roadmap/current plan/charter; source-wide cost/priority/browser/process scans; Git/Issue/PR state | root current_product_contract_decisions/release_readiness/core_workflow_release; full root and backend; read-only ancestry/remote verification |
| X | §6 and preserved Legacy call-graph inventory | absence inspection and current full source suites; excluded paths are not restored |

## Current capability matrix

Classification and validation are separate: a preserved source contract can PASS while its real installed proof remains pending. `VALIDATION_ONLY_PENDING` rows do not claim source-test evidence proves actual runtime acceptance. Security hardening and split packaging are approved/current changes under §5M/§7.

| # | Capability | Contract authority | Classification | Evidence key | Validation |
|---:|---|---|---|---|---|
| 1 | File/folder: Native transcription-folder picker; last selected folder retained | §4 File | PRESERVED | F | SOURCE PASS |
| 2 | File/folder: Top-level, case-insensitive MP3 scan; nested media excluded | §4 File | PRESERVED | F | SOURCE PASS |
| 3 | File/folder: Selected-file execution | §4 File | PRESERVED | F | SOURCE PASS |
| 4 | File/folder: No-selection all-incomplete execution requires confirmation | §4 File | PRESERVED | F | SOURCE PASS |
| 5 | File/folder: Valid complete TXT/JSON/SRT bundle is skipped | §4 File | PRESERVED | F | SOURCE PASS |
| 6 | File/folder: Missing/empty/invalid bundle is not DONE | §4 File | PRESERVED | F | SOURCE PASS |
| 7 | File/folder: Explicit retranscription executes replacement | §4 File | PRESERVED | F | SOURCE PASS |
| 8 | File/folder: Results beside MP3 with same stem | §4 File | PRESERVED | F | SOURCE PASS |
| 9 | File/folder: One-file local failure leaves later files runnable | §4 File | PRESERVED | F | SOURCE PASS |
| 10 | File/folder: Bulk selection remains a filesystem projection | §4 File | PRESERVED | F | SOURCE PASS |
| 11 | File/folder: A→B picker acceptance immediately clears/reconciles rows and counts (#170) | §4 File | PRESERVED | F | SOURCE PASS |
| 12 | File/folder: Rapid A→B→C rejects superseded success and error responses (#170) | §4 File | PRESERVED | F | SOURCE PASS |
| 13 | File/folder: Folder switch clears old Job, selection, dialog and preflight (#170) | §4 File | PRESERVED | F | SOURCE PASS |
| 14 | File/folder: Backend/settings failures cannot restore old-folder rows (#170) | §4 File | PRESERVED | F | SOURCE PASS |
| 15 | File/folder: Execute consumes confirmation before inline filename review (#171) | §4 File | PRESERVED | F | SOURCE PASS |
| 16 | File/folder: Cancel leaves no abandoned confirmation/preflight (#171) | §4 File | PRESERVED | F | SOURCE PASS |
| 17 | File/folder: Duplicate Execute cannot create duplicate attempts/Jobs (#171) | §4 File | PRESERVED | F | SOURCE PASS |
| 18 | File/folder: Display-only queue clear removed; filesystem projection retained (§5N) | §4 File | APPROVED_INTENTIONAL_CHANGE | F | SOURCE PASS |
| 19 | File/folder: Real duration from mutagen; unknown duration stays unknown (§5L) | §4 File | APPROVED_INTENTIONAL_CHANGE | F | SOURCE PASS |
| 20 | File/folder: MP3 import/copy/move into a managed folder removed (§5D) | §4 File | APPROVED_INTENTIONAL_CHANGE | F | SOURCE PASS |
| 21 | Filename/manual week: Canonical {과정명}_{과목명}_{N주차}_{M강} format | §4 Filename / §5E / #180 | PRESERVED | N | SOURCE PASS |
| 22 | Filename/manual week: Free-text course/subject plus positive integer manual week | §4 Filename / §5E / #180 | APPROVED_INTENTIONAL_CHANGE | N | SOURCE PASS |
| 23 | Filename/manual week: Server independently rejects missing, bool, non-integer and non-positive week | §4 Filename / §5E / #180 | APPROVED_INTENTIONAL_CHANGE | N | SOURCE PASS |
| 24 | Filename/manual week: Manual week excluded from RuntimeSettings persistence | §4 Filename / §5E / #180 | APPROVED_INTENTIONAL_CHANGE | N | SOURCE PASS |
| 25 | Filename/manual week: Actual folder change clears manual week | §4 Filename / §5E / #180 | APPROVED_INTENTIONAL_CHANGE | N | SOURCE PASS |
| 26 | Filename/manual week: PreflightAttempt snapshots week through paused review | §4 Filename / §5E / #180 | APPROVED_INTENTIONAL_CHANGE | N | SOURCE PASS |
| 27 | Filename/manual week: [N-M] detection wins over other week text | §4 Filename / §5E / #180 | PRESERVED | N | SOURCE PASS |
| 28 | Filename/manual week: N주차 M강 detection preserved | §4 Filename / §5E / #180 | PRESERVED | N | SOURCE PASS |
| 29 | Filename/manual week: [N주차]/week-only uses first free local lesson | §4 Filename / §5E / #180 | PRESERVED | N | SOURCE PASS |
| 30 | Filename/manual week: 13강_[4주차] leading global counter never becomes local lesson | §4 Filename / §5E / #180 | PRESERVED | N | SOURCE PASS |
| 31 | Filename/manual week: detect_week_lesson('13강 민법') remains UNKNOWN | §4 Filename / §5E / #180 | PRESERVED | N | SOURCE PASS |
| 32 | Filename/manual week: Exactly one standalone no-week global N강 enables manual-week fallback | §4 Filename / §5E / #180 | APPROVED_INTENTIONAL_CHANGE | N | SOURCE PASS |
| 33 | Filename/manual week: Eduwill 2강/3강/4강 + week 1 + empty target allocates local 1강/2강/3강 | §4 Filename / §5E / #180 | APPROVED_INTENTIONAL_CHANGE | N | SOURCE PASS |
| 34 | Filename/manual week: Eduwill occupied first lesson allocates 2강/3강/4강; gaps filled | §4 Filename / §5E / #180 | APPROVED_INTENTIONAL_CHANGE | N | SOURCE PASS |
| 35 | Filename/manual week: Eduwill preserves request order; counter value does not reorder allocation | §4 Filename / §5E / #180 | APPROVED_INTENTIONAL_CHANGE | N | SOURCE PASS |
| 36 | Filename/manual week: Explicit source week equal to manual week preserves Legacy behavior | §4 Filename / §5E / #180 | PRESERVED | N | SOURCE PASS |
| 37 | Filename/manual week: Different explicit/manual weeks require WEEK_MISMATCH review | §4 Filename / §5E / #180 | APPROVED_INTENTIONAL_CHANGE | N | SOURCE PASS |
| 38 | Filename/manual week: WEEK_MISMATCH never silently overwrites source or input | §4 Filename / §5E / #180 | APPROVED_INTENTIONAL_CHANGE | N | SOURCE PASS |
| 39 | Filename/manual week: Explicit rename to typed week or week edit resolves mismatch | §4 Filename / §5E / #180 | APPROVED_INTENTIONAL_CHANGE | N | SOURCE PASS |
| 40 | Filename/manual week: Standard canonical filenames protected | §4 Filename / §5E / #180 | PRESERVED | N | SOURCE PASS |
| 41 | Filename/manual week: Preferred/next lesson checks disk plus batch reservations | §4 Filename / §5E / #180 | PRESERVED | N | SOURCE PASS |
| 42 | Filename/manual week: MP3/TXT/JSON/SRT each occupy a target stem | §4 Filename / §5E / #180 | PRESERVED | N | SOURCE PASS |
| 43 | Filename/manual week: Bundle rename preflights collisions; rolls back partial failure | §4 Filename / §5E / #180 | PRESERVED | N | SOURCE PASS |
| 44 | Filename/manual week: Safe filename cleanup and Unicode/Korean/long paths retained | §4 Filename / §5E / #180 | PRESERVED | N | SOURCE PASS |
| 45 | Filename/manual week: CONTINUE_ORIGINAL allows local execution after explicit consent | §4 Filename / §5E / #180 | PRESERVED | N | SOURCE PASS |
| 46 | Filename/manual week: Unresolved CONTINUE_ORIGINAL forces entire run Drive OFF | §4 Filename / §5E / #180 | APPROVED_INTENTIONAL_CHANGE | N | SOURCE PASS |
| 47 | Filename/manual week: Continued WEEK_MISMATCH records no confirmed week/lesson metadata | §4 Filename / §5E / #180 | APPROVED_INTENTIONAL_CHANGE | N | SOURCE PASS |
| 48 | Filename/manual week: Fresh backend normalization rejects stale week/preview before Job creation | §4 Filename / §5E / #180 | APPROVED_INTENTIONAL_CHANGE | N | SOURCE PASS |
| 49 | Job/recovery/results: One global transcription/Drive execution lock and authoritative active-job visibility (#126) | §4 Job / File | PRESERVED | J | SOURCE PASS |
| 50 | Job/recovery/results: Job persistence uses unique temp + atomic replace | §4 Job / File | PRESERVED | J | SOURCE PASS |
| 51 | Job/recovery/results: Failed persistence rolls back memory and prevents unpersisted side effects | §4 Job / File | PRESERVED | J | SOURCE PASS |
| 52 | Job/recovery/results: STOPPED is distinct and current work not committed after stop | §4 Job / File | PRESERVED | J | SOURCE PASS |
| 53 | Job/recovery/results: CANCELLED is distinct from FAILED | §4 Job / File | PRESERVED | J | SOURCE PASS |
| 54 | Job/recovery/results: Active persisted work recovers as CRASHED after restart | §4 Job / File | PRESERVED | J | SOURCE PASS |
| 55 | Job/recovery/results: Manual retry supports failed/stopped/cancelled/crashed files | §4 Job / File | PRESERVED | J | SOURCE PASS |
| 56 | Job/recovery/results: Ordinary retry skips genuinely complete disk results | §4 Job / File | PRESERVED | J | SOURCE PASS |
| 57 | Job/recovery/results: Forced retry queues terminal files despite valid prior bundle (#172) | §4 Job / File | PRESERVED | J | SOURCE PASS |
| 58 | Job/recovery/results: Force intent survives persistence and causes fresh synthetic execution (#172) | §4 Job / File | PRESERVED | J | SOURCE PASS |
| 59 | Job/recovery/results: Mixed retry preserves already-DONE files | §4 Job / File | PRESERVED | J | SOURCE PASS |
| 60 | Job/recovery/results: Retry counters/error/batch completion are reconciled truthfully | §4 Job / File | PRESERVED | J | SOURCE PASS |
| 61 | Job/recovery/results: Corrupt state quarantined; unreadable/quarantine failure fails closed | §4 Job / File | PRESERVED | J | SOURCE PASS |
| 62 | Job/recovery/results: Restart preserves DONE results and prior events | §4 Job / File | PRESERVED | J | SOURCE PASS |
| 63 | Job/recovery/results: Replacement staged and validated before old bundle promotion | §4 Job / File | PRESERVED | J | SOURCE PASS |
| 64 | Job/recovery/results: Engine/validation failure preserves old TXT/JSON/SRT hashes | §4 Job / File | PRESERVED | J | SOURCE PASS |
| 65 | Job/recovery/results: Partial promotion/final-validation failure rolls back prior bundle | §4 Job / File | PRESERVED | J | SOURCE PASS |
| 66 | Job/recovery/results: TXT nonempty; JSON text/segments valid; SRT existence including empty SRT | §4 Job / File | PRESERVED | J | SOURCE PASS |
| 67 | Job/recovery/results: Stop/cancel boundary prevents promotion; no claimed mixed final generation | §4 Job / File | PRESERVED | J | SOURCE PASS |
| 68 | Job/recovery/results: Progress/ETA use observed duration/speed; missing data stays unknown (§5L) | §4 Job / File | APPROVED_INTENTIONAL_CHANGE | J | SOURCE PASS |
| 69 | Local: OpenAI Whisper model medium | §4 Local / #167 | PRESERVED | L | SOURCE PASS |
| 70 | Local: CUDA preferred; GPU/model-load failure falls back to CPU | §4 Local / #167 | PRESERVED | L | SOURCE PASS |
| 71 | Local: Automatic fp16 selected only for CUDA with >=6 GiB; introspection fails closed | §4 Local / #167 | PRESERVED | L | SOURCE PASS |
| 72 | Local: fp16-related failure gets one fp16=False fallback; file errors excluded | §4 Local / #167 | PRESERVED | L | SOURCE PASS |
| 73 | Local: Locked ko/transcribe/0/5/5/1.0/condition_on_previous_text=False decoding | §4 Local / #167 | PRESERVED | L | SOURCE PASS |
| 74 | Local: Worker emits explicit UTF-8 JSON through byte stdout, including errors/self-test | §4 Local / #167 | PRESERVED | L | SOURCE PASS |
| 75 | Local: Core protocol consumer is strict UTF-8; no CP949 fallback | §4 Local / #167 | PRESERVED | L | SOURCE PASS |
| 76 | Local: Synthetic Korean filename under CP949 child encoding finishes DONE | §4 Local / #167 | PRESERVED | L | SOURCE PASS |
| 77 | Local: Worker timeout/stop/cancel reaps owned child and reports cleanup failure | §4 Local / #167 | PRESERVED | L | SOURCE PASS |
| 78 | Local: Subject prompt/correction and automatic text substitution excluded (§5C) | §4 Local / #167 | APPROVED_INTENTIONAL_CHANGE | L | SOURCE PASS |
| 79 | Colab: faster-whisper large-v3; CUDA float16 preferred; CPU int8 fallback | §4 Colab / §5J/K/M / §9 | PRESERVED | C | SOURCE PASS |
| 80 | Colab: Korean decode and segment timestamps | §4 Colab / §5J/K/M / §9 | PRESERVED | C | SOURCE PASS |
| 81 | Colab: Offset-aware merge produces TXT/JSON/SRT | §4 Colab / §5J/K/M / §9 | PRESERVED | C | SOURCE PASS |
| 82 | Colab: Health checks require engine/model/device/compute identity | §4 Colab / §5J/K/M / §9 | PRESERVED | C | SOURCE PASS |
| 83 | Colab: 300-second internal chunks with tail handling; chunk detail hidden | §4 Colab / §5J/K/M / §9 | APPROVED_INTENTIONAL_CHANGE | C | SOURCE PASS |
| 84 | Colab: Initial request + at most one automatic retry | §4 Colab / §5J/K/M / §9 | APPROVED_INTENTIONAL_CHANGE | C | SOURCE PASS |
| 85 | Colab: Verified FAILED cache reused; changed identity rejected | §4 Colab / §5J/K/M / §9 | APPROVED_INTENTIONAL_CHANGE | C | SOURCE PASS |
| 86 | Colab: STOP/CANCEL discard current-file cache; CANCEL reports CANCELLED | §4 Colab / §5J/K/M / §9 | APPROVED_INTENTIONAL_CHANGE | C | SOURCE PASS |
| 87 | Colab: Cancellation observed between bounded chunks | §4 Colab / §5J/K/M / §9 | PRESERVED | C | SOURCE PASS |
| 88 | Colab: Automatic rendezvous primary; manual URL fallback | §4 Colab / §5J/K/M / §9 | APPROVED_INTENTIONAL_CHANGE | C | SOURCE PASS |
| 89 | Colab: Colab-open convenience targets current bootstrap notebook | §4 Colab / §5J/K/M / §9 | PRESERVED | C | SOURCE PASS |
| 90 | Colab: Retry interval remains source default 1.0 s; speculative 10 s change not adopted | §4 Colab / §5J/K/M / §9 | PRESERVED | C | SOURCE PASS |
| 91 | Colab: Real zero-cost Colab session and natural 524 proof pending (#48/#60) | §4 Colab / §5J/K/M / §9 | VALIDATION_ONLY_PENDING | C | PENDING; NOT RUN |
| 92 | Drive: Only TXT/JSON/SRT bundle uploaded; MP3 never uploaded/imported/copied/moved | §5B/F/G/H/I/M | APPROVED_INTENTIONAL_CHANGE | D | SOURCE PASS |
| 93 | Drive: New Job course/subject/stage/week/lesson metadata is classification truth | §5B/F/G/H/I/M | APPROVED_INTENTIONAL_CHANGE | D | SOURCE PASS |
| 94 | Drive: Partial metadata fails closed; only metadata-free Legacy Job uses narrow fallback | §5B/F/G/H/I/M | PRESERVED | D | SOURCE PASS |
| 95 | Drive: Known exact subject stage auto-map; unknown exact subject persisted override | §5B/F/G/H/I/M | APPROVED_INTENTIONAL_CHANGE | D | SOURCE PASS |
| 96 | Drive: Exam root configurable | §5B/F/G/H/I/M | APPROVED_INTENTIONAL_CHANGE | D | SOURCE PASS |
| 97 | Drive: update-or-create uses same parent/name | §5B/F/G/H/I/M | PRESERVED | D | SOURCE PASS |
| 98 | Drive: Validate/read local bundle before remote folder/file mutation | §5B/F/G/H/I/M | PRESERVED | D | SOURCE PASS |
| 99 | Drive: Drive failure/retry remains separate from Local DONE | §5B/F/G/H/I/M | PRESERVED | D | SOURCE PASS |
| 100 | Drive: Per-run auto-upload OFF at every launch and not persisted | §5B/F/G/H/I/M | APPROVED_INTENTIONAL_CHANGE | D | SOURCE PASS |
| 101 | Drive: OAuth loopback state/callback validation and private token boundary | §5B/F/G/H/I/M | PRESERVED | D | SOURCE PASS |
| 102 | Drive: ACL enforced before token publication; permission failure preserves private data | §5B/F/G/H/I/M | PRESERVED | D | SOURCE PASS |
| 103 | Drive: Actual OAuth/Drive mutation pending (#48) | §5B/F/G/H/I/M | VALIDATION_ONLY_PENDING | D | PENDING; NOT RUN |
| 104 | Folders/Log: Filesystem remains result truth, including external changes | §4 Folders / §5A/L / #127 | PRESERVED | U | SOURCE PASS |
| 105 | Folders/Log: All/complete/incomplete/results filters and truthful counts | §4 Folders / §5A/L / #127 | PRESERVED | U | SOURCE PASS |
| 106 | Folders/Log: Bounded TXT preview and full TXT view | §4 Folders / §5A/L / #127 | PRESERVED | U | SOURCE PASS |
| 107 | Folders/Log: UTF-8 BOM/UTF-8/CP949/EUC-KR/UTF-8 replacement display fallback | §4 Folders / §5A/L / #127 | PRESERVED | U | SOURCE PASS |
| 108 | Folders/Log: Display fallback does not rewrite/transcode source TXT | §4 Folders / §5A/L / #127 | PRESERVED | U | SOURCE PASS |
| 109 | Folders/Log: Filename/type ascending/descending only; status/modified non-sortable | §4 Folders / §5A/L / #127 | PRESERVED | U | SOURCE PASS |
| 110 | Folders/Log: Open/reveal uses opaque backend-validated intent and trusted Explorer | §4 Folders / §5A/L / #127 | PRESERVED | U | SOURCE PASS |
| 111 | Folders/Log: Debounced/sequential live change polling reconciles selection and preview | §4 Folders / §5A/L / #127 | PRESERVED | U | SOURCE PASS |
| 112 | Folders/Log: Dashboard removed; four destinations and structured Log | §4 Folders / §5A/L / #127 | APPROVED_INTENTIONAL_CHANGE | U | SOURCE PASS |
| 113 | Folders/Log: Structured Job/application event log and filtering | §4 Folders / §5A/L / #127 | APPROVED_INTENTIONAL_CHANGE | U | SOURCE PASS |
| 114 | Desktop/tray: File/job completion notification settings and truthful success/failure counts | §4 Desktop / #173/#168/#174/#128 | PRESERVED | T | SOURCE PASS |
| 115 | Desktop/tray: Notification result-folder action resolves opaque Job intent | §4 Desktop / #173/#168/#174/#128 | PRESERVED | T | SOURCE PASS |
| 116 | Desktop/tray: Reusable bounded completion toast and OS-notification fallback | §4 Desktop / #173/#168/#174/#128 | PRESERVED | T | SOURCE PASS |
| 117 | Desktop/tray: Idle close-to-tray hides and restore shows/focuses main window | §4 Desktop / #173/#168/#174/#128 | PRESERVED | T | SOURCE PASS |
| 118 | Desktop/tray: Active window close protects transcription and Drive; unknown guard fails safe (#128) | §4 Desktop / #173/#168/#174/#128 | PRESERVED | T | SOURCE PASS |
| 119 | Desktop/tray: Tray observer has one App-lifetime owner, independent of page routes (#173) | §4 Desktop / #173/#168/#174/#128 | PRESERVED | T | SOURCE PASS |
| 120 | Desktop/tray: api.activeJob authoritative polling; observed completion terminal lookup | §4 Desktop / #173/#168/#174/#128 | PRESERVED | T | SOURCE PASS |
| 121 | Desktop/tray: Outage does not fabricate IDLE; subsequent new Job can update tray | §4 Desktop / #173/#168/#174/#128 | PRESERVED | T | SOURCE PASS |
| 122 | Desktop/tray: Tray tooltip shows only real state/current file/progress; no fabricated ETA | §4 Desktop / #173/#168/#174/#128 | PRESERVED | T | SOURCE PASS |
| 123 | Desktop/tray: Official single-instance plugin registered first (#168) | §4 Desktop / #173/#168/#174/#128 | PRESERVED | T | SOURCE PASS |
| 124 | Desktop/tray: Second launch shows existing window; no duplicate backend/tray startup | §4 Desktop / #173/#168/#174/#128 | PRESERVED | T | SOURCE PASS |
| 125 | Desktop/tray: Tray Exit shares CloseCheck; active work blocked; idle confirmed exit (#174) | §4 Desktop / #173/#168/#174/#128 | PRESERVED | T | SOURCE PASS |
| 126 | Desktop/tray: Unavailable/malformed/timed-out Exit guard fails safe; repeat clicks coalesce | §4 Desktop / #173/#168/#174/#128 | PRESERVED | T | SOURCE PASS |
| 127 | Desktop/tray: Tray has no direct cleanup; RunEvent::ExitRequested owns cleanup | §4 Desktop / #173/#168/#174/#128 | PRESERVED | T | SOURCE PASS |
| 128 | Desktop/tray: Owned process trees cleaned; healthy unowned backend never killed | §4 Desktop / #173/#168/#174/#128 | PRESERVED | T | SOURCE PASS |
| 129 | Desktop/tray: Unicode Windows path and shortcut/AppUserModel identity source preserved | §4 Desktop / #173/#168/#174/#128 | PRESERVED | T | SOURCE PASS |
| 130 | Desktop/tray: Atomic settings persistence/corruption handling | §4 Desktop / #173/#168/#174/#128 | PRESERVED | T | SOURCE PASS |
| 131 | Desktop/tray: Shutdown immediate/15/30-second source countdown/cancel and idempotent native gate | §4 Desktop / #173/#168/#174/#128 | PRESERVED | T | SOURCE PASS |
| 132 | Desktop/tray: Actual native installed picker/tray/toast/close/cleanup proof pending (#56/#63) | §4 Desktop / #173/#168/#174/#128 | VALIDATION_ONLY_PENDING | T | PENDING; NOT RUN |
| 133 | Desktop/tray: Actual Windows shutdown pending immediate explicit approval (#58) | §4 Desktop / #173/#168/#174/#128 | VALIDATION_ONLY_PENDING | T | PENDING; NOT RUN |
| 134 | Security: Exact 127.0.0.1/localhost Host allowlist; fixed loopback bind and CORS boundary | §5M / §7 / DEVELOPMENT_RULES | APPROVED_INTENTIONAL_CHANGE | S | SOURCE PASS |
| 135 | Security: Paired signed Colab requests; timestamp/nonce replay protection | §5M / §7 / DEVELOPMENT_RULES | APPROVED_INTENTIONAL_CHANGE | S | SOURCE PASS |
| 136 | Security: Request audio-body SHA-256 mismatch rejected | §5M / §7 / DEVELOPMENT_RULES | APPROVED_INTENTIONAL_CHANGE | S | SOURCE PASS |
| 137 | Security: Pinned cloudflared binary hash; failure never publishes unverified binary | §5M / §7 / DEVELOPMENT_RULES | APPROVED_INTENTIONAL_CHANGE | S | SOURCE PASS |
| 138 | Security: Runtime manifest/version/protocol/hash/clean-provenance validation fails closed | §5M / §7 / DEVELOPMENT_RULES | APPROVED_INTENTIONAL_CHANGE | S | SOURCE PASS |
| 139 | Security: Safe stems/output paths; no arbitrary shell commands or frontend filesystem permission | §5M / §7 / DEVELOPMENT_RULES | APPROVED_INTENTIONAL_CHANGE | S | SOURCE PASS |
| 140 | Security: Trusted Windows whoami/icacls/taskkill/explorer/shutdown resolution | §5M / §7 / DEVELOPMENT_RULES | APPROVED_INTENTIONAL_CHANGE | S | SOURCE PASS |
| 141 | Security: Native PS5 packaging process/Restricted child invocation contracts | §5M / §7 / DEVELOPMENT_RULES | APPROVED_INTENTIONAL_CHANGE | S | SOURCE PASS |
| 142 | Security: Protected-data baseline and guard/session contracts tested with disposable fixtures | §5M / §7 / DEVELOPMENT_RULES | APPROVED_INTENTIONAL_CHANGE | S | SOURCE PASS |
| 143 | Security: No credentials, actual MP3/results/models/install artifacts tracked | §5M / §7 / DEVELOPMENT_RULES | PRESERVED | S | SOURCE PASS |
| 144 | Lightweight/packaging: Core requirements/spec exclude torch/CUDA/Whisper/Local payload | §7 / CURRENT_SOURCE_OF_TRUTH | APPROVED_INTENTIONAL_CHANGE | K | SOURCE PASS |
| 145 | Lightweight/packaging: Separate versioned Local Runtime retains local heavy dependencies | §7 / CURRENT_SOURCE_OF_TRUTH | APPROVED_INTENTIONAL_CHANGE | K | SOURCE PASS |
| 146 | Lightweight/packaging: Core/MSI <=250 MiB source policy retained; fresh size unmeasured | §7 / CURRENT_SOURCE_OF_TRUTH | PRESERVED | K | SOURCE PASS |
| 147 | Lightweight/packaging: Local manifest owns exact scalar torch==2.13.0+cu130 and CUDA 13.0 | §7 / CURRENT_SOURCE_OF_TRUTH | APPROVED_INTENTIONAL_CHANGE | K | SOURCE PASS |
| 148 | Lightweight/packaging: Core manifest owns provenance only; Local-only scalars absent | §7 / CURRENT_SOURCE_OF_TRUTH | APPROVED_INTENTIONAL_CHANGE | K | SOURCE PASS |
| 149 | Lightweight/packaging: Installer consumes Core policy/provenance without installing Local payload | §7 / CURRENT_SOURCE_OF_TRUTH | APPROVED_INTENTIONAL_CHANGE | K | SOURCE PASS |
| 150 | Lightweight/packaging: Local/Core source_head equality mandatory; mismatch rejects runtime | §7 / CURRENT_SOURCE_OF_TRUTH | APPROVED_INTENTIONAL_CHANGE | K | SOURCE PASS |
| 151 | Lightweight/packaging: onefile retained; no automatic onedir change | §7 / CURRENT_SOURCE_OF_TRUTH | PRESERVED | K | SOURCE PASS |
| 152 | Lightweight/packaging: Fresh artifact size/provenance/CUDA and installed pairing pending (#113) | §7 / CURRENT_SOURCE_OF_TRUTH | VALIDATION_ONLY_PENDING | K | PENDING; NOT RUN |
| 153 | Lightweight/packaging: Cold/warm startup measurement pending (#56/#63); no PASS threshold | §7 / CURRENT_SOURCE_OF_TRUTH | VALIDATION_ONLY_PENDING | K | PENDING; NOT RUN |
| 154 | Study-use/zero-cost/governance: Source contains no intentional browser/video pause/close/block behavior | §8/9/10 / ROADMAP current order | PRESERVED | G | SOURCE PASS |
| 155 | Study-use/zero-cost/governance: No process-priority/BELOW_NORMAL change adopted | §8/9/10 / ROADMAP current order | PRESERVED | G | SOURCE PASS |
| 156 | Study-use/zero-cost/governance: Real study MP3 plus concurrent internet lecture pending (#47); no no-slowdown guarantee | §8/9/10 / ROADMAP current order | VALIDATION_ONLY_PENDING | G | PENDING; NOT RUN |
| 157 | Study-use/zero-cost/governance: No paid API/GPU/managed-tunnel automatic fallback or billing/credit activation | §8/9/10 / ROADMAP current order | PRESERVED | G | SOURCE PASS |
| 158 | Study-use/zero-cost/governance: Unclear external cost remains pending without feature deletion/paid substitute (#48/#60) | §8/9/10 / ROADMAP current order | VALIDATION_ONLY_PENDING | G | PENDING; NOT RUN |
| 159 | Study-use/zero-cost/governance: #169 remains non-blocking post-deadline optimization | §8/9/10 / ROADMAP current order | PRESERVED | G | SOURCE PASS |
| 160 | Study-use/zero-cost/governance: Issue→branch→tests→commit→push→PR→checkpoint lifecycle | §8/9/10 / ROADMAP current order | PRESERVED | G | SOURCE PASS |
| 161 | Study-use/zero-cost/governance: Exact staging; no direct main work, rebase, force push, hard reset or clean | §8/9/10 / ROADMAP current order | PRESERVED | G | SOURCE PASS |
| 162 | Study-use/zero-cost/governance: Single consolidated #185 only after #114 PASS + approval; no constituent/bottom-up merge | §8/9/10 / ROADMAP current order | PRESERVED | G | SOURCE PASS |
| 163 | Study-use/zero-cost/governance: Next preflight+Probe→review→NEW Freeze; #113 build not authorized yet | §8/9/10 / ROADMAP current order | PRESERVED | G | SOURCE PASS |
| 164 | Study-use/zero-cost/governance: 2026-10-31 KST deadline unchanged; historical artifact/source PASS not current proof | §8/9/10 / ROADMAP current order | PRESERVED | G | SOURCE PASS |
| 165 | Explicit exclusions: Deprecated Google Drive Queue product path | §6 / preserved Legacy ACTIVE inventory | DEPRECATED_EXCLUDED | X | EXCLUDED; N/A |
| 166 | Explicit exclusions: Archived backups/POCs and no-op backup stubs | §6 / preserved Legacy ACTIVE inventory | DEPRECATED_EXCLUDED | X | EXCLUDED; N/A |
| 167 | Explicit exclusions: Experimental engines/UI/Colab CLI/WSL and uncalled startup-resume paths | §6 / preserved Legacy ACTIVE inventory | DEPRECATED_EXCLUDED | X | EXCLUDED; N/A |
| 168 | Explicit exclusions: Public GitHub Release/signing requirement and paid-resource alternatives | §6 / preserved Legacy ACTIVE inventory | DEPRECATED_EXCLUDED | X | EXCLUDED; N/A |

## Actual classification counts

| Classification | Count |
|---|---:|
| PRESERVED | 109 |
| APPROVED_INTENTIONAL_CHANGE | 47 |
| DEPRECATED_EXCLUDED | 4 |
| VALIDATION_ONLY_PENDING | 8 |
| CONFIRMED_DEFECT | 0 |
| AMBIGUOUS | 0 |
| **Total** | **168** |

Counts are recomputed from the numbered matrix. No source blocker was found: **P0 0 / P1 0**. Lower-priority current Study-Use source blocker: **0**. Accepted residual quality/security/observability and later documentation/operations items below remain explicit.

## #180 and remediation rerun

| Issue | Current source result | Fresh evidence / limits |
|---|---|---|
| #167 | SOURCE PASS | explicit UTF-8 byte producer, strict UTF-8 consumer; CP949 protocol fallback NONE. Korean filenames under a CP949-default synthetic child finish DONE in local/output tests. Actual installed CUDA inference NOT RUN |
| #172 | SOURCE PASS | ordinary bundle recovery remains; forced terminal retry executes a new synthetic replacement despite preserved old bundle, preserves mixed-batch DONE files, reconciles counters/error; engine/validation/partial-promotion failure preserves prior hashes |
| #170 | SOURCE PASS | picker resets rows/counts/Job/selection/dialog/preflight; abort + generation/folder identity reject stale A→B→C responses even when abort is ignored; failed save/offline cannot resurrect old rows |
| #171 | SOURCE PASS | Execute snapshots/consumes confirmation before preflight; Cancel discards confirmation without abandoning a locked attempt; duplicate Execute is coalesced |
| #173 | SOURCE PASS | App owns one observer; authoritative active-job poll followed by terminal lookup; route-independent; outage preserves last confirmed state; later new job allowed |
| #168 | SOURCE PASS | official single-instance first plugin, first-instance callback only show/focus; second-instance argv/cwd ignored; duplicate backend/tray setup excluded by ordering |
| #174 | SOURCE PASS | tray quit → shared guarded exit; active transcription/Drive denied; idle confirmed exit; guard failure safe-hide; no tray cleanup; ExitRequested sole native cleanup authority |
| #180 | SOURCE PASS | manual week strict positive int, not persisted, cleared on folder change, snapshotted; Eduwill allocation + mismatch + final metadata + Drive compatibility + bundle rollback/Unicode exercised |

Exact Eduwill inputs: `2026_이영방_부동산학개론_기초이론_2강.mp3`, `..._3강.mp3`, `..._4강.mp3`. With course `기초이론`, subject `부동산학개론`, manual week **1**, empty target, the batch proposes **1주차_1강 / 1주차_2강 / 1주차_3강**. Occupied lesson 1 yields **2강 / 3강 / 4강**; arbitrary occupied cross-extension stems and gaps are tested. Global counters supply neither week nor local lesson.

Legacy bracket/week/leading-counter detection and canonical protection pass. Explicit week mismatch requires user resolution; silent overwrite **NONE**. CONTINUE_ORIGINAL remains locally runnable, forces Drive OFF, and unresolved WEEK_MISMATCH emits **no confirmed week/lesson**. Final normalized metadata is consumed by the unchanged DriveClassifier; partial metadata fails closed.

## Contract findings

- **Local:** medium/CUDA→CPU and automatic fp16/fallback plus all seven decode fields preserved. Source/protocol synthetic evidence only.
- **Colab:** faster-whisper large-v3, float16/int8, Korean timestamp merge, bounded chunk/retry/cache/cancel/security preserved. Retry default remains **1.0 s** in source; no arbitrary 10-second change. Real session/524 NOT RUN.
- **Drive:** three-file bundle, metadata truth, classification/stage/root, per-run OFF, private OAuth and failure isolation PASS. Real OAuth/Drive mutation NOT RUN.
- **Folders:** disk truth, four filters, bounded preview/full, filename/type sort only, display encoding fallback without rewrite, validated Explorer intent and live change handling PASS.
- **Desktop/tray:** source notifications/folder action/close/single-instance/observer/guard/ownership/Unicode PASS. Native installed proof pending.
- **Security:** full security regression included; exact loopback/Host/CSP boundary, signed paired replay protection, hash/manifest/provenance, safe process/path and trusted native tools fail closed. Existing hardening unchanged.
- **Lightweight:** Core heavy payload exclusion and <=250 MiB policy retained; separate Local exact torch/CUDA scalar owner; Core provenance only and Local/Core source pairing rejects mismatch. No fresh size claim, no Local 2GB defect classification, no onefile→onedir switch.
- **Zero-cost:** source scan found no paid API/GPU/tunnel fallback, billing or credit activation. No external cost guarantee inferred from source; unclear paths stay PENDING.
- **Study-use concurrency:** no intentional browser/video termination/blocking or scheduler priority change found. Real concurrent lecture usability is **VALIDATION_ONLY_PENDING (#47)**; no slowdown guarantee NONE.
- **Governance:** no merge or main development; exact staging only; new report commit followed by normal push/PR/checkpoints. Constituent PRs remain review/evidence only. Only #185 can merge after #114 PASS and final approval.

## Fresh mandatory tests and exact commands

All final invocations use native **Windows PowerShell 5.1.26100.9444 Desktop**, repository venv, unchanged source. Backend/root are separate suites with their correct working directories; no ad-hoc #113 preflight reconstruction. Flags suppress pytest cache writes and expose exact skip reasons. Offline/locked Cargo uses already present dependencies. Frontend production/static build is explicitly required by request §20.C and is `tsc -b && vite build`, not a Local/Core/MSI release build.

| Gate / working directory | Exact child command | Result |
|---|---|---|
| Root / repository | `venv\Scripts\python.exe -m pytest tests -q -ra -p no:cacheprovider` | **211 passed, 0 skipped, 0 failed** |
| Backend / backend | `..\venv\Scripts\python.exe -m pytest tests -q -ra -p no:cacheprovider` | **730 passed, 2 skipped, 0 failed, 0 errors** |
| Frontend / frontend | `npm.cmd run lint` | PASS / exit 0 |
| Frontend / frontend | `npm.cmd run typecheck` | PASS / exit 0 |
| Frontend / frontend | `npm.cmd run build` | PASS / exit 0; 1,851 modules |
| Rust / frontend/src-tauri | `cargo fmt --check` | PASS / exit 0 |
| Rust / frontend/src-tauri | `cargo check --locked --offline` | PASS / exit 0 |
| Rust / frontend/src-tauri | `cargo clippy --locked --offline -- -D warnings` | PASS / exit 0 |
| Rust / frontend/src-tauri | `cargo test --locked --offline` | **83 passed, 0 failed/ignored**; main/doc targets 0 tests |
| Focused root / repository | command below | **154 passed, 0 failed** |
| Focused backend / backend | command below | **371 passed, 0 failed** |
| Working tree / index | `git diff --check`; `git diff --cached --check` | PASS |

Counts match the immediately preceding **211**, **730/2**, **83** baselines. They were observed, not imposed. The two backend skips are `test_app_data_isolation.py:135` (non-Windows Path.home fallback) and `test_folder_revision.py:123` (host does not permit symlink creation). A Starlette/httpx deprecation warning remains; no dependency change was made. Cargo test emitted an MSVC library/exports linker message warning; check and clippy exit 0, all 83 tests PASS.

Focused root (filename/manual week, picker, confirmation, tray, single-instance, global run/close, packaging/security/governance):

```powershell
venv\Scripts\python.exe -m pytest tests/test_180_manual_week_frontend.py tests/test_folder_picker_reconcile.py tests/test_confirmation_preflight_lifecycle.py tests/test_tray_progress_contracts.py tests/test_174_guarded_tray_exit_contracts.py tests/test_168_desktop_single_instance_contracts.py tests/test_global_single_run_contracts.py tests/test_active_run_close_contracts.py tests/test_core_workflow_release_contracts.py tests/test_release_readiness_contracts.py tests/test_trusted_windows_utilities_contracts.py tests/test_loopback_host_contracts.py tests/test_current_product_contract_decisions.py -q -ra -p no:cacheprovider
```

Focused backend (filename/#180/#172/protocol/output/security/packaging/recovery):

```powershell
..\venv\Scripts\python.exe -m pytest tests/test_manual_week_normalization.py tests/test_filename_normalizer_parity.py tests/test_transcription_runner.py tests/test_local_and_output.py tests/test_release_packaging_contract.py tests/test_package_c_security.py tests/test_colab_bootstrap_security.py tests/test_process_recovery_contracts.py tests/test_global_single_run.py tests/test_close_guard.py -q -ra -p no:cacheprovider
```

### Invocation journal and failed attempts

The untracked, ignored `tmp/audit123/run-source-tests.ps1` only selects these commands, changes cwd and captures logs. It does not call real preflight/Probe/build/install/shutdown. Root source tests do exercise copied bootstrap contracts in **disposable Git fixtures**; this is not a candidate preflight/Probe or artifact session.

1. Two ordinary `exec_command` attachment-read attempts could not start the host pwsh process (`CreateProcessAsUserW: 5 / Access denied`). Read-only commands and authorized source checks then used reviewed escalated execution.
2. Initial PS5 `-File tmp/audit123/run-source-tests.ps1 -Suite root/backend` with `-ExecutionPolicy Bypass` failed before tests: a BOM-less script literal containing the Korean repository path was decoded incorrectly. The ignored runner derives cwd instead. No production/test file changed.
3. Root and backend were launched using that initial runner. Root **211 PASS**; backend **723 PASS / 2 SKIP / 7 fixture ERRORS** because inherited process policy was **Bypass**, while the Restricted-invocation fixture explicitly required **Restricted**. This was a measured fixture prerequisite failure, not presumed environment dismissal.
4. Initial Rust runner had `ErrorActionPreference=Stop`; Cargo status text on native stderr terminated the wrapper before a check result. The wrapper records native exit codes with Continue instead. Production source unchanged.
5. Automatic approval review initially rejected frontend static build by interpreting all build output as forbidden. Request §20.C explicitly mandates frontend static build; package.json proves the command runs only TypeScript/Vite. Reviewed rerun allowed it and lint/typecheck/build all PASS. Release artifact prohibition remained intact.
6. Backend and Rust were rerun without execution-policy override, allowing normal native PS5 module discovery. Backend **730 PASS / 2 SKIP / 0 ERROR**; fmt/check/clippy PASS; Rust **83 PASS**. Focused **154 + 371 PASS** followed. Root was finally rechecked in the same normal-policy PS5 environment: **211 PASS**.

7. The first staged diff check rejected Markdown hard-break trailing spaces and an extra EOF blank line in this new report. Report formatting was corrected and re-staged; production/tests remained unchanged. Final diff checks PASS.

Exact launcher families executed:

```powershell
# Initial runner invocations (root, backend, frontend, rust), as journaled above:
& 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' -NoProfile -ExecutionPolicy Bypass -File tmp/audit123/run-source-tests.ps1 -Suite root
# Same launcher with -Suite backend / frontend / rust.

# Final native-policy launcher; suite values: backend, rust, focused, root:
$env:PSModulePath = $null
& 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' -NoProfile -Command '$auditEntry = Join-Path (Get-Location) "tmp\audit123\run-source-tests.ps1"; & ([scriptblock]::Create([IO.File]::ReadAllText($auditEntry))) -Suite backend'
```

Only the tool process's module-path inheritance was removed for native PS5 discovery; system/user execution policy was not changed. No PS7/Git Bash failure is counted as a product defect.

Other executed inspection/lifecycle commands and tools:

- `Get-Content -LiteralPath <attached request> -Raw`; `Get-Location`; `rg --files --hidden -g AGENTS.md` and ancestor-directory AGENTS checks (none found); read applicable writing-style skill. The supplied request controls report/checkpoint style.
- `git status --short`, `git branch --show-current`, `git rev-parse HEAD`, `git remote -v`, `git log -3 --format='%H %s'`.
- `git ls-remote --heads origin docs/pre-freeze-plan-reconciliation integration/study-use-final-candidate audit/123-final-source-regression-rerun`.
- `git switch -c audit/123-final-source-regression-rerun 87d7b1e72840335eaa3baa1e7b805a01a8fe329e`.
- `Get-Content` current authority, historical reports/inventory and source/test/package/spec files in the evidence key; `rg --files` and `rg -n` source/test searches; focused `Select-Object` excerpts; `Get-Command gh,rg,python,cargo,npm`; `Get-ChildItem` repository/temporary Legacy checkout discovery.
- `git -C <read-only jeonsa_doumi-audit checkout> rev-parse HEAD`; `git -C <same checkout> status --short` (clean); `rg -n` Legacy filename/Whisper/ACTIVE GUI affordances.
- Source-wide `rg -n -i` scans for priority/BELOW_NORMAL, browser kill/block, paid API endpoints/GPU/tunnels/billing/credit activation; reviewed matches contained no adopted prohibited behavior. `git ls-files '*.mp3' '*.pt' '*.pth' '*.msi' '*.exe' '*.dll' '*token*' '*credentials*'` returned only `frontend/src/styles/tokens.css`, not secret/artifact data.
- `gh issue list --repo bongbong90/Sorigul --state open --limit 100 --json number,title,body,url` (**27** OPEN Issues including reopened #123); `gh issue view 184/116 --json ...`; `gh api repos/bongbong90/Sorigul/issues/{173,168,174,180,114}/comments?per_page=100`.
- `gh pr view {185,186,115} --repo bongbong90/Sorigul --json ...`; connector `github_fetch_issue` / `github_update_issue` for #123 reopen/control block. Raw read snapshots are ignored local evidence.
- For each ancestry row: `git rev-parse <short SHA>`; `git merge-base --is-ancestor <full SHA> HEAD` (all exit 0).
- `git check-ignore tmp/audit123/run-source-tests.ps1` (ignored).
- Report written with apply_patch; matrix/classification count recomputation and exact report-only diff verification before commit.
- Final authorized lifecycle: `git add docs/runtime/STUDY_USE_FULL_SOURCE_CONTRACT_REGRESSION_2026-10-06.md`; `git diff --cached --stat`; both diff checks; `git commit -m "audit: rerun final full source contract regression (#123)"`; `git push -u origin audit/123-final-source-regression-rerun`.
- Dedicated PR: `gh pr create --base docs/pre-freeze-plan-reconciliation --head audit/123-final-source-regression-rerun --title "audit: final full source contract regression (#123)" --body-file <ignored UTF-8 PR body>`.
- Integration updated by normal fast-forward ref push `git push origin HEAD:refs/heads/integration/study-use-final-candidate`, never force. Local integration ref advances only if its old value matches the checked remote ancestor.
- GitHub bodies changed through explicit body files/structured APIs, with historical suffix preservation; #123/#7/#116/#115/#185 read back. #123 closes COMPLETED only after synchronization and identity/ancestry checks.
- Final remote identity `git ls-remote` and `gh pr view`; GitHub `compare/<ancestor>...<final audit SHA>` for every row verifies `behind_by=0` and final candidate includes the ancestor.

This journal distinguishes failed invocations and source-test commands from forbidden real gate execution. Final lifecycle/remote checkpoint evidence is bound to the containing audit commit in the linked Issue/PR readbacks.

## Current OPEN Issue classification

Read **27** OPEN Issues after #123 reopen. State alone is not evidence of a current source defect. #173/#168/#174/#180 source PASS is in their latest completion comments despite original installed-defect bodies; current code/tests independently PASS here.

| Issues | Source-gate classification / schedule |
|---|---|
| #167/#172/#170/#171/#173/#168/#174/#180 | SOURCE PASS reconfirmed; OPEN / INSTALLED RETEST PENDING. Fresh #113 then #56/#63; #180 also #47 |
| #169 | NON-BLOCKING / POST-DEADLINE OPTIMIZATION; Local size itself not a contract violation |
| #56/#63 | Installed native/integration pending, current old-artifact STOP remains; COLD/WARM startup measurement only |
| #47 | Real study MP3 and simultaneous internet lecture validation pending; same fresh accepted artifact |
| #48/#60 | External-only zero-cost validation pending/best-effort operational limit; no actual session/mutation |
| #59 | Later recovery policy/integration gate; existing manual reconnect/CRASHED preservation is current source behavior; automatic recovery is not silently adopted |
| #58 | Source shutdown contract PASS; actual shutdown pending immediate explicit approval |
| #114 | Final installed workflow/merge gate pending; current single-consolidated policy supersedes original old merge sentence |
| #52/#53/#62 | Accepted residual typed-parser/local-process trust/elapsed-time observability items; non-blocking, remain visible at downstream reviews |
| #54 | README/closeout documentation update scheduled before final workflow/main merge; no product-source blocker |
| #49/#57/#61 | Public signing/release operations/upgrade scenarios/branch protection; not current source-gate blockers |
| #7/#116 | Tracker/deadline controls; synchronize current result, preserve history |
| #123 | This reopened full source audit; close only after all remote/checkpoint readbacks |

#113's old PASS is historical and is **not** a PASS for this candidate; fresh #113 remains a separate future gate after new Freeze approval. #184 CLOSED / PASS and #186 OPEN / NOT MERGED remain unchanged.

## Ancestry required for the candidate

All eleven commits were confirmed ancestors of the audited start, and must remain ancestors of the report/candidate HEAD. Final GitHub comparison readbacks bind these to the audit commit, each with **behind_by = 0**.

| Commit | Exact SHA |
|---|---|
| original artifact source | `780dbb1e799fd5eb79f3c13736061ad34223cc1a` |
| #167 | `debabd06702d0c581c4f40feedba0d8669cc64eb` |
| #172 | `8071886e9cd5d1ad73e6f6cc3eba06f61616b9d0` |
| #170 | `a12b93a1a03a41576b3581ce68b38ebf31fc3619` |
| #171 | `82cee4d7c26621ea76c9b0ef72c2ec774c262375` |
| #173 | `ed3d862df9a8167eedc0592f81030746ac70b10b` |
| #168 | `a4e46c8214e47ba59ff64f862a33dd76514c555d` |
| #174 | `62e96d1c35631ad4b9e2705ee4d60a583dde6eac` |
| #180 | `36ac439c7f631c86e4c5263582d44755ea41c230` |
| reconciliation | `293b4027fbac7347eadcb98dc6c20bfb8a1ef4eb` |
| authority closure / exact parent | `87d7b1e72840335eaa3baa1e7b805a01a8fe329e` |

Existing untracked `monitor.ps1`, `smoke.ps1`, `smoke_desktop.ps1`, `smoke_qa.ps1`, `tunnel_log` were preserved and never staged. Generated frontend/Rust/test evidence is untracked/ignored. Production diff NONE; only this report belongs in the commit.

## Pending / forbidden work-unit outputs

| Work | Result |
|---|---|
| Local Runtime release build / actual model inference | NOT RUN |
| Core release build | NOT RUN |
| MSI build | NOT RUN |
| Install/uninstall | NOT RUN |
| Installed QA | NOT RUN |
| Actual study MP3 | NOT RUN |
| Actual internet lecture | NOT RUN |
| Actual Colab / real 524 | NOT RUN |
| Actual Google OAuth / Drive mutation | NOT RUN |
| Actual Windows shutdown | NOT RUN |
| Candidate canonical run_113_preflight / bootstrap Probe | NOT RUN — separate next gate |
| NEW RELEASE FREEZE | NOT YET |
| Merge | NONE |

## Literal verdict and next gate

SOURCE FULL REGRESSION = PASS
KNOWN P0/P1 SOURCE BLOCKERS = 0
AMBIGUOUS CONTRACT ITEMS = 0
PRODUCT-SOURCE PARITY = COMPLETE
READY FOR CANONICAL PREFLIGHT + BOOTSTRAP PROBE = YES

NEW RELEASE FREEZE = NOT YET
#113 ARTIFACT BUILD = NOT AUTHORIZED YET
MERGE = NONE

**NEXT (separate work unit):** canonical `scripts/run_113_preflight.ps1` → canonical bootstrap Probe → result review → only then NEW RELEASE FREEZE. Local/Core/MSI #113 build must not start before that new Freeze approval. Then one fresh #113 → same artifact #56/#63 (+ startup measurements) → #47 (+ concurrent lecture) → #48/#60 → #59 → #58 (immediate approval) → #114 → approved ancestry-preserving #185 merge.
