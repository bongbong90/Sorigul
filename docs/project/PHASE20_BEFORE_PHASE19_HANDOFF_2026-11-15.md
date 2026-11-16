# SORIGUL — CURRENT handoff: PHASE 20 implementation BEFORE PHASE 19 final packaging (2026-11-15)

**Status:** CURRENT SCHEDULING DECISION / not a release or execution approval.  
**Authority:** User 2026-11-15 scheduling reversal; [Phase 20 #246](https://github.com/bongbong90/Sorigul/issues/246), [Phase 19 #269](https://github.com/bongbong90/Sorigul/issues/269), [execution defect #270](https://github.com/bongbong90/Sorigul/issues/270), [Local-first decision #264](https://github.com/bongbong90/Sorigul/issues/264).  
**Preserved submitted Phase 19 evidence:** [RESULT](../release/PHASE19_2026-11-15_RESULT.md) and [EXECUTION_AND_ROLLBACK_PLAN](../release/PHASE19_2026-11-15_EXECUTION_AND_ROLLBACK_PLAN.md). Both are original fixed-date reports, **HISTORICAL EVIDENCE ONLY**. Their local-file bytes were separately verified against the SHA256 values posted in #269; GitHub copies preserve the reported text, not necessarily the original line-ending bytes.

## Resumption update — 2026-11-16 KST

Phase 20 is already **IMPLEMENTED_MOCK_VERIFIED** at `087aba661c3ebf5feb25dc25be4077b91efe8373` ([Draft #272](https://github.com/bongbong90/Sorigul/pull/272), 15 feature files). The feature requirements below describe that implementation; do not restart Phase 20 development. Its preserved official results are Root **264 PASS / 4 FAIL**, Backend **843 PASS / 2 SKIP**, Frontend lint/typecheck/build PASS, Rust fmt/check/clippy PASS and **96 tests PASS**. Two Root failures need #268; two are #270 WinError 5. Integration remains `58d734a`; no constituent PR has been merged.

Native Windows resumption used the existing [Draft #273](https://github.com/bongbong90/Sorigul/pull/273) at `e39977301f5f937c44d36d093a44448f49d7baf2`, stacked only on `087aba6`, in an isolated worktree with no concurrent Cargo/Backend/Root suite. Diagnostic unit tests **3 PASS**; the existing launch matrix **32/32 PASS under each of PS7 and Windows PowerShell 5.1 parents**. The four named historical Backend/Root failures passed in separate targeted runs; related Root bootstrap **66 PASS** and Backend PS5 **20 PASS**. #268's unchanged `6a7320b` separately passed all **14 readiness tests**. These are scoped observations, not a new official full regression or release PASS.

**#270 remains BLOCKED / actual cause NOT DETERMINED.** Historical errors occur at Python `_winapi.CreateProcess` before PS5 script execution, including inherited cwd/environment helper calls; the current matrix and related suites did not reproduce them. Read-only ACL/event inspection found no attributable deny or matching AppLocker/Defender block; inspected CodeIntegrity errors concerned Chrome and do not establish a Sorigul cause. The tool's restricted shell also failed at `CreateProcessAsUserW` while the permitted native execution path worked; that separate launcher failure does not prove the historical Python cause. No production/test workaround, security-policy change, release Freeze or artifact/installer transition was performed. Local sanitized logs are under `tmp/issue270-evidence`; #270/#269/#7 and the existing PRs hold the resumption record.

Next: retain #268/#272 review evidence, obtain an attributable #270 reproduction or supported-host remediation evidence, confirm the approved final source, then run the official full regression and canonical preflight/Probe before a new exact-head Freeze. Packaging/installation still require separate approval and verified rollback MSI. Earlier implementation-first instructions below are satisfied by #272; historical Phase 19 results remain immutable.

## Critical supersession: prevent the same delay in a new chat

**CURRENT ORDER: PHASE 20 source implementation + offline Mock QA + commit/push/Draft PR → final approved source candidate / #268 reconciliation → #270 remediation and full canonical source regression/preflight/Freeze → PHASE 19 Local Runtime/Core/MSI final packaging and installed QA (separately authorized).**

The uploaded Phase 19 RESULT and ROLLBACK_PLAN, and historical #269/#270 comments, say **“do not begin Phase 20 before Phase 19 COMPLETE”** / **“Phase 20 gated”**. Those statements are retained as evidence of the attempted run, but **are SUPERSEDED AS A SCHEDULING DEPENDENCY** by the user's newer Phase 20-before-Phase 19 instruction, already recorded in #246 and #7. They must not block Phase 20 code, synthetic fixtures, Mock tests, issue/branch/commit/push/Draft PR. Do not relabel Phase 19 FAIL as PASS: #270 remains a blocker for required official regression, final Release Freeze and actual Windows packaging/installed acceptance.

## What Phase 20 actually builds (Issue #246)

- **Scope:** Settings → Google Drive folder-only parent destination picker with breadcrumb and explicit confirmation; display readable path while storing **validated exact Drive folder ID** and verified account binding. A default/restore-to-`root` option preserves current behavior.
- **Hierarchy:** under selected parent, keep existing `drive_exam_root / 전사자료 / course / subject / week` classification; do **not** write the 3-file bundle directly under selected parent or move old content.
- **Safety:** duplicate names are identified by ID; reject trashed/deleted/inaccessible/foreign-account/ambiguous destinations; never silently fall back to `root` or a same-name folder. No OAuth scope expansion, token reuse outside approved Drive client, billing, paid fallback or real cloud mutation without separate approval.
- **Durability:** snapshot parent ID and appropriate classification/account binding **at Job creation**; settings changes, app restart and manual Drive retry must NOT redirect an earlier Job. Preserve legacy jobs without spontaneous remote uploads or migrations.
- **Preservation:** per-run automatic Drive upload DEFAULT OFF; TXT/JSON/SRT only (no MP3); Local DONE and Drive FAILED independently; existing safe update-or-create/ambiguity, user-file retention and explicit Retry.
- **Implementation surfaces (verify actual source before changing):** `backend/src/services/drive.py`, `backend/src/services/settings.py`, relevant job schemas/persistence/routes, `frontend/src/pages/SettingsPage.tsx` and API client. Existing Google Drive feature source is independent of Colab LIVE.
- **Tests:** folder-only chooser and Unicode/duplicate names; missing access/trashed/revoked/moved/account changes; no wrong-parent upload, no fallback; Job snapshot/retry after settings changes and reboot; legacy jobs; synthetic Mock Drive tree + exact TXT/JSON/SRT output; frontend state/error handling; retained Local and Colab default-blocked behavior.
- **Output:** reviewable Phase 20 changes, affected targeted offline/Mock PASS evidence, Issue #246 update, meaningful commit+push, Draft PR; do not claim overall full regression or release PASS if #270 remains. No need to wait for Google policy reply per #264.

**Do not repeat the Phase 19 build before Phase 20 source is finalized.** Source changes alter release-input provenance, so final current-HEAD freeze and versioned Local Runtime (~2GB) / Core source_head pairing must come after the chosen Phase 20 integration point.

## Phase 19 BLOCKED — exact preserved technical handoff

| Gate | Verified 2026-11-15 result |
|---|---|
| Integration source HEAD | `58d734a64b9f8a7ec3ab4ba82970c1a821ca1158` |
| #268 Draft candidate | `6a7320b8bbba189780ad7ecdd9b96a6a7a138b66`, readiness `14 PASS`, **not merged** |
| Integration official Root | **265 PASS / 2 FAIL** (release contract mismatch, #266) |
| Candidate official Root | **265 PASS / 2 FAIL / 1 teardown ERROR**, CreateProcess WinError 5 |
| Backend suite | **808 PASS / 2 SKIP / 1 warning** |
| Frontend | lint/typecheck/build **PASS** |
| Rust | fmt PASS; check/clippy/test FAIL, os error 5; also fails with fresh target |
| Canonical preflight | **36 PASS / 2 FAIL** at step 4/7, PS5 subprocess WinError 5 |
| Probe / Release Freeze / Runtime/Core/MSI | **NOT RUN / NOT CREATED** |
| Install / CUDA / synthetic / recovery / process-owned cleanup | **NOT RUN** for current HEAD |
| User protected baseline / rollback MSI | **NOT VERIFIED**; no installed transition performed |
| Process observation | validation-owned matched processes 0, TCP8000 listener 0; **not installed cleanup PASS** |

**#270 diagnosis:** supported PS5 host fails exact `test_installer_powershell5_restricted_invocation.py::test_nested_invocation_preserves_file_identity_and_exit_zero` and `test_core_powershell5_process_observation.py::test_core_ps5_retains_exact_synthetic_child_exit_code[23-python]`. Rust dependency build-script executable launches also fail `os error 5` from fresh target. Simple PS5 probes (20/20) PASS but do not exonerate policy/harness. Separate wrong-cwd collection failure and PS7 module-auto-load setup error are invocation limitations, not proof of the canonical defect's cause. Root cause **NOT DETERMINED**; never weaken tests, disable OS protections, cherry-pick retries or claim full PASS. Full source regression and official preflight must actually pass before Phase 19 Freeze/build.

## Phase 19 resumption: safety and rollback (after Phase 20)

1. Verify approved final release source HEAD, PR ancestry, exact-file diff, release-input inventory. Resolve `#266/#268` contract regression under review/merge policy, and `#270` real Windows execution failures on a supported host. Run canonical full source regression + preflight/Probe; only then generate a new exact-head Freeze.
2. Before any approved artifact work, obtain a new canonical single-writer `SESSION_ACTIVE` with protected real-profile baseline. Retain existing user settings/jobs/OAuth/media/results/model/cache and five untracked helpers; never delete locks or mutate security settings. Local builder publishes to `%LOCALAPPDATA%/Sorigul/runtime/local-whisper/v1`, so isolate only owned build children in a dedicated standard-user LOCALAPPDATA/APPDATA/WebView environment, never the real user Runtime.
3. Build the isolated versioned Local Runtime (exact torch `2.13.0+cu130`, CUDA 13.0, real GPU tensor, hashes/manifest). Run `build_windows_installer.ps1`, which itself invokes Core build—do not run a redundant standalone Core build. Verify recursive archive/PYZ for `multipart/python_multipart` as well as excluded torch/CUDA/Whisper; report actual presence, not merely absence of direct source imports. Core/MSI each <=250MiB, Core manifest excludes Local-only torch/CUDA fields; source_head matches.
4. Re-verify installed ProductCode **`{021BCE70-EDE5-49E4-B85C-E7AFD1CCA75B}`** and version 0.1.0 immediately before transition. Exact hash-verified rollback MSI is **NOT YET VERIFIED**; no install/uninstall or normal-user profile transition before separate scope approval and verified rollback. Guard actual application/worker/WebView absence, TCP8000 and installer state; never infer no autolaunch from `/qn` only.
5. After separately approved install, validate actual installed Desktop→Backend automatic start, same-source Local, CUDA synthetic, TXT/JSON/SRT, multi-file/skip, STOP/CANCEL/RETRY/CRASHED, folders/scan/log/Unicode, tray clean exit and no owned residual processes/ports; compare protected metadata in canonical guard. Do not rerun 52:34 user lecture without a new reason/approval; never perform Windows shutdown absent immediate explicit approval.

### Explicitly not performed in 2026-11-15 Phase 19

No active artifact session, Freeze, Runtime/Core/MSI build, install, uninstall, user profile switch, real MP3, real Drive/Colab, actual shutdown or main merge. Protected baseline and rollback readiness remain pending. No PASS can be inferred from historical #47/#113/#56/#63/#59 installed evidence for the new candidate HEAD.

## Source of truth for next CODEX session

1. Read [Phase 20 #246](https://github.com/bongbong90/Sorigul/issues/246) and its **current execution order**.
2. Read this handoff and the two exact-date Phase 19 reports; distinguish historical blocked verdict from superseded Phase 20 timing.
3. Phase 20's implementation PR is now ready as Draft #272 at `087aba6`; preserve it and use the resumption update above. Track #270 as the unresolved Phase 19 release gate.
4. Once Phase 20 changes are in the approved release candidate, resume Phase 19 gates and protected rollout; not before.
5. Report separately: `PHASE20_IMPLEMENTATION_STATUS`, `PHASE19_RELEASE_STATUS`, `COLAB_EXTERNAL_STATUS`, `USER_DATA_PRESERVATION`. Google policy answer is not a Local development blocker.
