# Study-Use Full Source Contract Regression Re-run — 2026-09-30 (5M)

Issue: #123 · Branch: `audit/full-source-contract-regression-rerun` · Parent: `docs/lock-127-parity-decisions@90ed22e19bef41049f2dc0c4418a7368a7755e4a` · Parent PR: #148 (OPEN, MERGEABLE, NOT MERGED)

This is an audit-only work unit. Production source is unchanged. The 2026-09-29 report and its Legacy inventory remain immutable historical evidence of the first failed audit.

## 1. Exact inputs

| Input | Exact value / state |
|---|---|
| Audited Sorigul source | `90ed22e19bef41049f2dc0c4418a7368a7755e4a` |
| Parent branch | `docs/lock-127-parity-decisions` |
| Legacy baseline | `bongbong90/jeonsa_doumi@fbc86313a179a62a586386551f99384a9fce5fc8` |
| Legacy tracked files | 337 (`git ls-files`, fresh scratch checkout) |
| Canonical contract | `docs/project/CURRENT_PRODUCT_CONTRACT.md` (`LOCKED`) |
| Evidence routing | `CURRENT_SOURCE_OF_TRUTH.md`, `DEVELOPMENT_RULES.md` |
| Completion plan | `SORIGUL_FULL_LEGACY_PARITY_COMPLETION_PLAN_2026-09-28.md` |
| Historical evidence | 2026-09-29 full regression report and 337-file inventory |
| GitHub state consulted | all 21 OPEN Issues; #123/#127/#147; remediation #124/#122/#125/#126/#128/#130/#131/#132/#133/#136/#138; PR #148/#115 |

Evidence precedence was applied exactly as locked: later explicit decisions recorded in the current contract, current locked contract, Legacy ACTIVE runtime, historical documents, then current implementation. Existing implementation was never used by itself to approve a difference.

## 2. Re-run methodology

1. Re-read the four canonical inputs and the complete historical 90-row matrix.
2. Revalidated the unchanged Legacy baseline in a separate scratch checkout; no Legacy source was copied or imported.
3. Re-inspected current source and focused contract tests for every row, not only the formerly failing rows.
4. Re-ran the five filename reproduction cases, global single-run, close guard, Host, Windows utilities, Colab, Drive, packaging, Folders, tooltip, and contract suites through the full tests below.
5. Scanned current source for bare Windows utilities, Legacy runtime references, clipboard/Flask restoration, Core heavy dependencies, MP3 Drive transfer, paid provisioning, broad shell/filesystem permission, queue-clear UI, and fabricated progress/ETA.
6. Audited every currently OPEN GitHub Issue separately from current source reality.

The first sandboxed test attempt could not create pytest's shared temp root, Vite could not spawn its config helper, and sandboxed Rust child-process tests received Windows access-denied. The exact commands were rerun outside that sandbox boundary without changing source or test code. Those canonical reruns passed; the failed harness attempts are not product failures.

## 3. Full 90-row capability matrix

Validation vocabulary: `SOURCE PASS`, `PENDING INSTALLED`, `PENDING EXTERNAL`, and `N/A`. Classifications are independently recomputed at this HEAD.

| # | Area | Legacy behavior | Current contract | Current Sorigul evidence | Classification | Issue / provenance | Validation state |
|---:|---|---|---|---|---|---|---|
| 1 | File/folder selection | Native folder picker | Preserve | `FolderSection`, `native.pickFolder`, dialog capability | PRESERVED | §4 File | SOURCE PASS; PENDING INSTALLED #56 |
| 2 | Folder scan | Top-level MP3 only | Preserve | `scanner.py` non-recursive case-insensitive scan | PRESERVED | §4 File | SOURCE PASS |
| 3 | Startup load | Reopen last folder | Preserve | persisted `transcription_folder` and frontend storage | PRESERVED | §4 File | SOURCE PASS |
| 4 | Live folder change | 1 s debounced watcher | Equivalent live projection | `folder_revision.py`, `useFolderRevision`, sequential 1 s polling | PRESERVED | #111 | SOURCE PASS; PENDING INSTALLED #63 |
| 5 | Start scope | Selected, else all incomplete | Preserve | `CreateJobRequest.scope` and confirmation UI | PRESERVED | §4 File | SOURCE PASS |
| 6 | Complete skip | Valid TXT/JSON/SRT skips | Preserve | scanner/output validator and runner skip | PRESERVED | §4 File | SOURCE PASS |
| 7 | Invalid bundle | Incomplete is not DONE | Preserve | `INCOMPLETE` / `INVALID_RESULT` | PRESERVED | §4 File | SOURCE PASS |
| 8 | Re-transcribe | Explicit rerun | Preserve | `force_retranscribe` and UI action | PRESERVED | §4 File | SOURCE PASS |
| 9 | Old result | Preserve until replacement valid | Preserve | staged write, validate, backup, promote, rollback | PRESERVED | §4 File | SOURCE PASS |
| 10 | File failure | Continue later files | Preserve | runner contains non-fatal per-file error | PRESERVED | §4 File | SOURCE PASS |
| 11 | Global single run | One transcription globally | Preserve, race-safe | one execution lock, max one unfinished Future, 409, global active visibility | PRESERVED | #126 FIXED | SOURCE PASS |
| 12 | Duration | multi-probe duration | Real metadata; honest unknown | `AudioMetadataService` / mutagen | APPROVED_INTENTIONAL_CHANGE | §5L | SOURCE PASS |
| 13 | Bulk selection | Check/uncheck all | Preserve | tri-state selection in `QueueTable` | PRESERVED | §4 File | SOURCE PASS |
| 14 | Queue clear | Display-only row removal | Remove under filesystem-truth model | no clear action; queue remains live projection | APPROVED_INTENTIONAL_CHANGE | #127 A4 / §5N | SOURCE PASS |
| 15 | Filename edit | Edit target name | Preserve safely | preflight rename endpoint and UI | PRESERVED | §4 Filename | SOURCE PASS |
| 16 | Cleanup | plus/page/forbidden/space cleanup | Preserve | normalizer cleanup patterns | PRESERVED | §4 Filename | SOURCE PASS |
| 17 | `N주차…M강` | Detect week and lesson | Preserve | `WEEK_AND_LESSON_PATTERN` | PRESERVED | §4 / D12 | SOURCE PASS |
| 18 | `[N-M]` | Detect week and lesson | Preserve | bracket precedence and parity tests | PRESERVED | #124 FIXED | SOURCE PASS |
| 19 | Week-only | First free lesson; ignore global `N강` | Preserve | `WEEK_ONLY`, first-free allocation | PRESERVED | #124 FIXED | SOURCE PASS |
| 20 | Course/subject | Fixed alias detection | Free-text user input | validated free-text classification | APPROVED_INTENTIONAL_CHANGE | §5E | SOURCE PASS |
| 21 | Standard name | Never rewrite standard name | Preserve | `STANDARD_PATTERN`, unchanged/mismatch | PRESERVED | §4 Filename | SOURCE PASS |
| 22 | Collision | MP3/TXT/JSON/SRT occupy stem | Preserve | `collect_existing_stems` | PRESERVED | §4 Filename | SOURCE PASS |
| 23 | Allocation | Preferred/next and batch reservation | Preserve | bounded step-forward plus reserved batch stems | PRESERVED | #124 | SOURCE PASS |
| 24 | Bundle rename | Same-stem four-file rename | Preserve and harden | preflight conflict plus rollback | PRESERVED | §4 Filename | SOURCE PASS |
| 25 | Unresolvable name | Keep original and continue | Explicit consent | invalid/mismatch/conflict resolution path | PRESERVED | migration §10.2 | SOURCE PASS |
| 26 | Unicode filename | Long Korean/Unicode | Preserve | pathlib/UTF-8 and contract tests | PRESERVED | §4 Filename | SOURCE PASS; PENDING INSTALLED #113 |
| 27 | STOP | Stop and discard in-flight | Preserve | token, worker reap, `STOPPED` | PRESERVED | §4 Job | SOURCE PASS; PENDING INSTALLED #63 |
| 28 | CANCEL | Distinct cancellation | Preserve | `CANCEL_REQUESTED` to `CANCELLED` | PRESERVED | §4 Job | SOURCE PASS |
| 29 | CRASHED | Detect abnormal exit | Preserve | recovery in `JobManager` | PRESERVED | §4 Job | SOURCE PASS; PENDING INSTALLED #63 |
| 30 | Retry | Keep DONE | Preserve | disk recheck and DONE skip | PRESERVED | §4 Job | SOURCE PASS |
| 31 | Persistence | Atomic replace | Preserve | unique temp, fsync/replace boundaries | PRESERVED | §4 Job | SOURCE PASS |
| 32 | Corruption | Quarantine state | Preserve | `jobs.corrupt.<timestamp>.json`, fail closed | PRESERVED | §4 Job | SOURCE PASS |
| 33 | Restart | Preserve completion | Preserve | persisted jobs load/recovery | PRESERVED | §4 Job | SOURCE PASS; PENDING INSTALLED #63 |
| 34 | Colab progress startup resume | Uncalled Legacy path | Excluded non-ACTIVE path | not restored | DEPRECATED_EXCLUDED | Legacy call-graph inventory | N/A |
| 35 | Session state | Show prior run state | Preserve | Job status/current task/Log | PRESERVED | §4 Job | SOURCE PASS |
| 36 | Local engine | OpenAI Whisper medium | Exact preserve | `LocalWhisperEngine.MODEL_NAME`, worker validation | PRESERVED | §4 Local | SOURCE PASS |
| 37 | Local device | CUDA preferred, CPU fallback | Preserve | runtime CUDA load with CPU fallback | PRESERVED | §4 Local | SOURCE PASS; PENDING INSTALLED #113/#47 |
| 38 | fp16 choice | CUDA and at least 6 GiB | Preserve | `_detect_fp16`, fail-closed introspection | PRESERVED | §4 Local | SOURCE PASS |
| 39 | fp16 retry | At most one false retry | Preserve | retryable markers/exclusions, one retry | PRESERVED | §4 Local | SOURCE PASS |
| 40 | Decode args | ko/transcribe/0/5/5/1.0/false | Exact preserve | request exact-match validation | PRESERVED | §4 Local | SOURCE PASS |
| 41 | Local packaging | Monolithic possibility | Separate versioned Local Runtime | manifest/hash/provenance boundary | APPROVED_INTENTIONAL_CHANGE | §7 | SOURCE PASS; PENDING INSTALLED #113 |
| 42 | Colab engine | faster-whisper large-v3; CUDA float16/CPU int8 | Preserve | bootstrap identity and `WhisperModel` | PRESERVED | #106 | SOURCE PASS; PENDING EXTERNAL #48 |
| 43 | Colab decode | ko, beam 5, no word timestamps | Preserve | `/transcribe` fixed arguments | PRESERVED | §4 Colab | SOURCE PASS |
| 44 | Health identity | Liveness | Preserve and harden identity | engine/model/device/compute response and client check | PRESERVED | §5M | SOURCE PASS |
| 45 | Chunk/merge | offset merge and tail handling | 300 s internal chunk; hidden UI | engine chunk/tail/offset tests | APPROVED_INTENTIONAL_CHANGE | §5K | SOURCE PASS |
| 46 | Auto retry | Legacy two retries | Initial plus max one retry | retryable status/network policy | APPROVED_INTENTIONAL_CHANGE | §5K | SOURCE PASS |
| 47 | Recovery cache | Legacy progress file | verified FAILED cache; STOP/CANCEL clear | signed cache identity and clear semantics | APPROVED_INTENTIONAL_CHANGE | §5K | SOURCE PASS |
| 48 | Stop timing | Stop after current chunk | Preserve | cancellation check between chunks | PRESERVED | §4 Colab | SOURCE PASS |
| 49 | Connection UX | Clipboard/manual URL | Rendezvous primary, manual fallback | rendezvous service and manual URL fallback | APPROVED_INTENTIONAL_CHANGE | §5J | SOURCE PASS; PENDING EXTERNAL #48 |
| 50 | Colab open | One-click convenience | Restore for current bootstrap | fixed Colab notebook destination via browser boundary | PRESERVED | #127 A1 / #130 | SOURCE PASS; PENDING INSTALLED #56 |
| 51 | Colab security | Plain tunnel request | signed/pairing/replay/fail-closed | Ed25519, nonce cache, body hash, pinned cloudflared | APPROVED_INTENTIONAL_CHANGE | §5M | SOURCE PASS |
| 52 | Real Colab | Real external runtime | Must be confirmed zero-cost | source cannot prove external runtime | VALIDATION_ONLY_PENDING | #48/#60 | PENDING EXTERNAL |
| 53 | TXT validity | Non-empty TXT | Preserve effective result | non-empty validation | PRESERVED | §4 Results | SOURCE PASS |
| 54 | Empty TXT | Incomplete | Preserve | `TXT_INVALID`, old result kept | PRESERVED | §4 Results | SOURCE PASS |
| 55 | JSON | text/segments and validity | Preserve, stricter segments | payload parsing and validator | PRESERVED | §4 Results | SOURCE PASS |
| 56 | SRT | Exists; may be empty | Preserve | existence validation | PRESERVED | §4 Results | SOURCE PASS |
| 57 | Output location | Same stem beside MP3 | Preserve | `BundlePaths.final_for` | PRESERVED | §4 Results | SOURCE PASS |
| 58 | OAuth/token | Local token | Preserve and harden private ACL | loopback OAuth; ACL before token publish | PRESERVED | #122 | SOURCE PASS; PENDING EXTERNAL #48 |
| 59 | Drive bundle | MP3/TXT/JSON/SRT | TXT/JSON/SRT only; never MP3 | upload bundle excludes MP3 | APPROVED_INTENTIONAL_CHANGE | §5B | SOURCE PASS |
| 60 | Drive classification | Filename/fixed root | metadata, stage mapping, configurable root | persisted file metadata and exact override | APPROVED_INTENTIONAL_CHANGE | §5F/G/H | SOURCE PASS |
| 61 | update-or-create | Update same parent/name | Preserve | find then update/create | PRESERVED | §5B | SOURCE PASS; PENDING EXTERNAL #48 |
| 62 | Drive preflight | Validate before network | Preserve | bundle validation/read probe before folder mutation | PRESERVED | §5B | SOURCE PASS |
| 63 | Drive isolation | Local DONE independent | Preserve | separate Drive state/retry/background execution | PRESERVED | §5B | SOURCE PASS |
| 64 | Auto-upload | Persistent toggle | Per-run only, default OFF, not persisted | request field absent from runtime settings | APPROVED_INTENTIONAL_CHANGE | §5I | SOURCE PASS |
| 65 | Real Drive mutation | External OAuth/API | Required later, safely | not run in source audit | VALIDATION_ONLY_PENDING | #48 | PENDING EXTERNAL |
| 66 | Folder filters | all/complete/incomplete/results | Preserve | scan filters and counts | PRESERVED | §4 Folders | SOURCE PASS; PENDING INSTALLED #56/#63 |
| 67 | Text view | 500-char preview and full view | Preserve; full max 5 MiB | results service bounds | PRESERVED | §4 Folders | SOURCE PASS |
| 68 | TXT fallback | utf-8-sig/utf-8/cp949/euc-kr | Restore display-only plus replace | bounded decoder; no rewrite | PRESERVED | #127 A5 / #133 | SOURCE PASS |
| 69 | Column sort | Name/type toggles | Restore filename/type only | `folderSort.ts`, stable selection/refresh | PRESERVED | #127 A3 / #132 | SOURCE PASS |
| 70 | Explorer | Open/reveal result | Preserve through validated intent | opaque IDs, backend validation, trusted Explorer path | PRESERVED | #122 | SOURCE PASS; PENDING INSTALLED #56 |
| 71 | Folder refresh | Filesystem watcher | Preserve behavior | top-level metadata, one sequential request, selected preview refresh | PRESERVED | #111 | SOURCE PASS; PENDING INSTALLED #63 |
| 72 | Dashboard | Statistics page | Replace with structured Log | Dashboard absent by contract | APPROVED_INTENTIONAL_CHANGE | §5A | SOURCE PASS |
| 73 | Log | Legacy sidebar log | Structured Log | Job/application events and filters | APPROVED_INTENTIONAL_CHANGE | §5A | SOURCE PASS |
| 74 | Notifications | File/job completion toggles | Preserve | settings and desktop coordinator events | PRESERVED | §4 Desktop | SOURCE PASS; PENDING INSTALLED #56 |
| 75 | Actionable toast | Folder open and dismiss | Preserve securely | reusable toast with opaque job ID and validated intent | PRESERVED | #110 | SOURCE PASS; PENDING INSTALLED #56/#63 |
| 76 | Tray | App open and quit | Preserve | tray menu wiring | PRESERVED | §4 Desktop | SOURCE PASS; PENDING INSTALLED #56 |
| 77 | Tray tooltip | State/progress/current file | Restore honestly | real active Job priority, filename-only, no fabricated percent/ETA | PRESERVED | #127 A2 / #131 | SOURCE PASS; PENDING INSTALLED #56/#63 |
| 78 | X close during work | Hide during active run | Preserve for transcription and Drive | unfinished Future truth, idle exit, unknown safe-hide | PRESERVED | #128 FIXED | SOURCE PASS; PENDING INSTALLED #56 |
| 79 | Idle close-to-tray | Hide when configured | Preserve | tray behavior immediate hide | PRESERVED | §4 Desktop | SOURCE PASS; PENDING INSTALLED #56 |
| 80 | Shutdown | immediate/15/30, countdown/cancel | Preserve | coordinator plus trusted fixed shutdown command | PRESERVED | #58 | SOURCE PASS; actual shutdown NOT RUN |
| 81 | Sidecar lifecycle | Auto-start/health/no orphan | Preserve | owned child, Job Object kill-on-close, trusted fallback | PRESERVED | #138 test-only fix | SOURCE PASS; PENDING INSTALLED #113 |
| 82 | Windows identity | Shortcut/AppUserModelID | Preserve | MSI identity/config | PRESERVED | §4 Desktop | PENDING INSTALLED #113 |
| 83 | Settings | Persist user settings | Preserve | atomic JSON and corrupt quarantine | PRESERVED | §4 Desktop | SOURCE PASS |
| 84 | Errors | Friendly Korean errors | Preserve | normalized user messages and HTTP detail | PRESERVED | §4 Desktop | SOURCE PASS |
| 85 | Progress/ETA | Smoothed/fabricated possible | Real observed values only | metadata/observed-speed calculations; unknown is null | APPROVED_INTENTIONAL_CHANGE | §5L | SOURCE PASS |
| 86 | Unicode path | Korean/Unicode paths | Preserve | Python/Rust intent tests and UTF-8 contracts | PRESERVED | §4 Desktop | SOURCE PASS; PENDING INSTALLED #113 |
| 87 | Prompt/corrections | Subject substitutions | Do not migrate | no prompt/correction layer | APPROVED_INTENTIONAL_CHANGE | §5C | SOURCE PASS |
| 88 | MP3 import/move | Managed move/import | Remove | selected-folder scan only | APPROVED_INTENTIONAL_CHANGE | §5D | SOURCE PASS |
| 89 | Google Drive Queue | Deprecated queue modules | Exclude | no current product path | DEPRECATED_EXCLUDED | §6 | N/A |
| 90 | Colab CLI/WSL, backup, archive/POC | Experimental/non-ACTIVE paths | Exclude | no current runtime reference | DEPRECATED_EXCLUDED | §6 | N/A |

## 4. Classification counts

| Classification | Count |
|---|---:|
| PRESERVED | 68 |
| APPROVED_INTENTIONAL_CHANGE | 17 |
| DEPRECATED_EXCLUDED | 3 |
| VALIDATION_ONLY_PENDING | 2 |
| CONFIRMED_DEFECT | 0 |
| AMBIGUOUS | 0 |
| **Total** | **90** |

The counts were recomputed from the rows above. They match, but were not copied from, the expected direction in the execution brief.

## 5. Previously failing and ambiguous rows

| Historical row(s) | Prior state | Current evidence | Current state |
|---|---|---|---|
| 11 | concurrent global runs | backend execution lock, 409 race tests, cross-folder active controls | PRESERVED / #126 VERIFIED |
| 18/19 | bracket and week-only filename defects | five Legacy comparison cases, first-free/batch/cross-extension tests | PRESERVED / #124 VERIFIED |
| 78 | exit killed active work | transcription Future and Drive guard; unknown safe-hide | PRESERVED / #128 VERIFIED |
| 50 | A1 ambiguous | current bootstrap Colab-open path | PRESERVED / #130 VERIFIED |
| 77 | A2 ambiguous | honest real-state tray tooltip | PRESERVED / #131 VERIFIED |
| 69 | A3 ambiguous | filename/type-only sort | PRESERVED / #132 VERIFIED |
| 14 | A4 ambiguous | locked queue-clear removal | APPROVED_INTENTIONAL_CHANGE / #127 VERIFIED |
| 68 | A5 ambiguous | display-only bounded fallback | PRESERVED / #133 VERIFIED |

Representative filename results at current HEAD are identical to Legacy for all five historical reproduction inputs: `1강_[1주차]`, `13강_[4주차]`, `13강_[4-1]`, `[4주차]`, and `4주차 3강 ...(p.12~34)`.

## 6. Historical remediation re-check

| Issue | Verdict | Fresh evidence |
|---|---|---|
| #124 | FIXED / VERIFIED | filename parity full suite |
| #122 | FIXED / VERIFIED | PowerShell and Git Bash backend 536/2; all utilities trusted absolute |
| #125 | FIXED / VERIFIED | exact TrustedHost allowlist; foreign/suffix rejected |
| #126 | FIXED / VERIFIED | global lock/race/visibility/stop-cancel tests |
| #128 | FIXED / VERIFIED | active transcription/Drive close guard tests |
| #130 | RESTORED / VERIFIED | current Colab bootstrap open contracts |
| #131 | RESTORED / VERIFIED | honest tray tooltip source/Rust tests |
| #132 | RESTORED / VERIFIED | filename/type sorting tests |
| #133 | RESTORED / VERIFIED | TXT fallback order/bounds/no-rewrite tests |
| #136 | FIXED / VERIFIED | both build scripts resolve trusted taskkill |
| #138 | FIXED / VERIFIED | no fixed sleeps; escalated OS-level Rust suite 78/78 |
| #147 | LOCKED / VERIFIED | contract A1-A5 table, §5N, supersession map |

## 7. Security

- Uvicorn binds `127.0.0.1`; TrustedHost permits only `127.0.0.1` and `localhost`. No wildcard, suffix, or foreign Host is accepted. CORS origin policy and Host validation remain separate.
- #53 is an OPEN threat-model/residual-risk item, not a current contract regression: another process under the same local user can reach the loopback API. No current locked requirement mandates local-process authentication before #113. It remains explicit and is not confused with #125.
- `whoami`, both `icacls` calls, backend and Rust `taskkill`, `explorer`, and `shutdown` resolve via trusted absolute Windows directories. Build tooling does the same for both taskkill sites. Bundled FFmpeg sibling/PATH handling remains the intentional fixed-resource design.
- The frontend has no broad shell permission or arbitrary filesystem-open permission. Explorer accepts opaque intent IDs and launches only after backend validation.
- Production CSP is strict. OAuth/token material is not returned by APIs and token publication fails closed until private ACL enforcement succeeds.
- Colab uses pairing, signed requests, content hashes, timestamp/nonce replay protection, health identity checks, and pinned cloudflared SHA-256.

**SECURITY SOURCE GATE = PASS**

## 8. Lightweight

`backend/requirements.txt` contains no torch, Whisper, faster-whisper, or CUDA package. The Core PyInstaller spec explicitly excludes torch/whisper/numba/llvmlite. Heavy OpenAI Whisper/torch belongs only to the separate Local Runtime spec and requirements; faster-whisper belongs only to the Colab runtime.

Fresh Core/MSI size and artifact provenance were deliberately not measured here; they belong to #113.

**SOURCE LIGHTWEIGHT CONTRACT = PASS**

## 9. Zero-cost

No source path provisions paid APIs, paid GPU, credit/billing activation, or a managed paid tunnel fallback. Colab is user-started; Quick Tunnel is anonymous best-effort and has no paid fallback. Unsafe-to-confirm external cost state remains pending rather than silently escalating.

**ZERO-COST SOURCE CONTRACT = PASS**

## 10. Git hygiene

- Tracked MP3: none.
- Actual user TXT/JSON/SRT, models/cache, OAuth credentials/tokens, runtime jobs/settings, generated `dist`/Rust `target`, and build/install artifacts: none tracked.
- The only pre-existing untracked files remain `monitor.ps1`, `smoke.ps1`, `smoke_desktop.ps1`, `smoke_qa.ps1`, and `tunnel_log`; all were untouched.
- Production source changes in this audit: none.

**GIT HYGIENE = PASS**

## 11. OPEN Issue gate classification

All 21 currently OPEN Issues were read. OPEN tracker state was not treated as proof of a current source defect.

| Class | Issues | Gate interpretation |
|---|---|---|
| A. Current source blocker | none | no current P0/P1 or pre-artifact source defect |
| B. Installed/artifact gate pending | #45, #56, #63, #113 | #45 fix `22ebe3d` is an ancestor; fresh artifact confirmation is #113 |
| C. External/input validation pending | #47, #48, #58, #60 | real audio/account/runtime/shutdown evidence only; #58 needs immediate approval |
| D. Final workflow/recovery pending | #59, #114 | later policy/integration gates |
| E. Docs/closeout/tracking | #7, #54, #55, #62, #116, #123 | does not contradict audited source |
| F. Public-release/non-goal operations | #49, #57, #61 | signing, upgrade operations, branch protection are not study-use source blockers |
| G. Accepted residual/non-blocking risk | #52, #53 | typed Explorer parsing quality and local-process auth threat model remain explicit |

#45's Issue body is stale relative to source: `22ebe3d` is an ancestor of this audit HEAD and its source tests pass. The Issue remains meaningful for fresh artifact confirmation, not as a source blocker.

## 12. Fresh test results

| Gate | Exact command | Fresh result |
|---|---|---|
| Root PowerShell | `venv\Scripts\python.exe -m pytest tests -q -rfE -p no:cacheprovider` | **82 passed** |
| Backend PowerShell | `..\venv\Scripts\python.exe -m pytest tests -q -rfE -p no:cacheprovider` from `backend` | **536 passed, 2 skipped** |
| Backend Git Bash | same backend command under Git Bash | **536 passed, 2 skipped** |
| Frontend lint | `npm.cmd run lint` | PASS |
| Frontend typecheck | `npm.cmd run typecheck` | PASS |
| Frontend build | `npm.cmd run build` | PASS (1,851 modules) |
| Rust fmt | `cargo fmt --check` | PASS |
| Rust check | `cargo check --locked --offline` | PASS |
| Rust clippy | `cargo clippy --locked --offline -- -D warnings` | PASS |
| Rust all targets | `cargo clippy --locked --offline --all-targets -- -D warnings` | PASS |
| Rust test | `cargo test --locked --offline` | **78 passed** |
| Whitespace | `git diff --check` | PASS |

The backend PowerShell/Git Bash counts match. The Git Bash Windows-utility PATH-shadow regression did not recur. The final Rust run passed every #138 process/Job Object test; production code remains unchanged by #138.

## 13. Installed/external pending

- #113 Fresh Local Runtime/Core/MSI: **PENDING**.
- #56/#63 installed Windows UX/integration: **PENDING**.
- #47 personal study MP3: **PENDING**.
- #48/#60 real zero-cost Colab/Drive: **PENDING / CONDITIONAL**.
- #58 actual Windows shutdown: **PENDING EXPLICIT APPROVAL**.
- #59 post-start recovery policy/integration: **PENDING**.
- #46, #104, and past Colab/Drive evidence remain historical only and were not promoted to current-HEAD PASS.

No artifact build, install, real personal MP3, external Colab/Drive mutation, Explorer UI interaction, or shutdown was performed.

## 14. Final verdict

All 90 rows are resolved under the current locked contract. There is no confirmed source defect, unresolved ambiguity, P0/P1 source blocker, or known pre-artifact defect. Security, lightweight, zero-cost, Git hygiene, and every canonical regression suite pass. The remaining items are correctly routed to installed, external, or later workflow gates.

SOURCE FULL REGRESSION = PASS

KNOWN P0/P1 SOURCE BLOCKERS = 0

KNOWN PRE-ARTIFACT DEFECTS = 0

AMBIGUOUS CONTRACT ITEMS = 0

PRODUCT-SOURCE PARITY = COMPLETE

READY FOR #113 = YES
