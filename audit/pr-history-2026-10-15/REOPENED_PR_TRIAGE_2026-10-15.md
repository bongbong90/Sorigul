# 2026-10-15 — Reopened PR Triage / Consolidated Main-Merge Ledger

> User direction: review every PR and commit, reopen all technically reopenable closed-unmerged PRs, classify the entire history, produce reviewable PRs and ultimately promote accepted Integration to `main`.
>
> This file **records the current reopen operation**. Earlier original CLOSED-unmerged snapshots remain intact. GitHub historic `MERGED` events are not rewritten.

## Verified current remote state

- Previous audit **89 PRs = 13 already MERGED + 74 CLOSED-unmerged + 2 OPEN**. All **74 former CLOSED-unmerged PRs were successfully reopened on 2026-10-15**, independently read back from GitHub current open-PR collection. Current snapshot = **76 OPEN / 13 MERGED / 0 CLOSED-unmerged**.
- 74 reopenings comprise **70 originally stacked-base PRs** and **4 originally main-base PRs** (#98, #162, #163, #166). **Reopen is metadata only, not merge**. They remain unmerged unless GitHub separately reports a merge operation.
- Prior 74/74 ancestry proof: every **original PR head SHA** is an ancestor of Integration HEAD `38b856a0dfe18448005a59bf7bb36479f3cd2692`; no feature-code replay required. Reopening does not demonstrate a current diff can be safely merged to its historical base.
- Prior comprehensive audit: **153 commit IDs** in Integration history and **89 original PRs**, documented in [complete reconciliation](COMMIT_PR_FULL_RECONCILIATION_2026-10-15.md), [original file/PR inventory](pr-inventory.json), and [case study index](README.md). The **13 old MERGED** PRs cannot be reopened under GitHub semantics: #1, #2, #3, #4, #5, #6, #72, #190, #196, #197, #198, #200, #202.
- Existing OPEN canonical PRs: [#185 Integration→main](https://github.com/bongbong90/Sorigul/pull/185) and [#204 history archive→Integration](https://github.com/bongbong90/Sorigul/pull/204). This triage update enters **the existing #204 archive through a separate review PR**; it does not add duplicate code to Integration.
- [#205 governance and final-main tracker](https://github.com/bongbong90/Sorigul/issues/205), [#203 original audit](https://github.com/bongbong90/Sorigul/issues/203).

## Category & merge decision

| Class | Number | Working disposition |
|---|---:|---|
| **Historical STACKED** | 70 | Reopened to recover PR review visibility. For each, assess exact current base/head, mergeability and diff *before any historical target-branch merge*. Original commits already belong to Integration; **never merge independently to main**. No automatic claim that replaying old diff is safe. |
| **Historical MAIN** | 4 | Reopened for review but **DO NOT MERGE** into main individually; these are obsolete, partial, old candidate branches already superseded by #185. |
| **Already MERGED** | 13 | Preserve original GitHub MERGED provenance and code ancestry. Not reopenable. |
| **Current integration/main PR** | 1 (#185) | Sole code-promotion route. `main` merge requires current-HEAD fresh installed Core/Local acceptance, real Korean MP3, #47 and #114 PASS, release provenance, and final human review. |
| **Current history archive PR** | 1 (#204) | Documentation-only; requires planned Integration timing and new HEAD/Freeze coordination. This archive is not a shortcut for installed acceptance. |

**Release gate is not waived by administrative reopen.** Source-level #123 PASS and 260/260 current Freeze input checks are supported at `38b856a`. #191 normal installed Core/Runtime pairing and actual Korean MP3 failure remain unresolved, #47 real MP3+lecture concurrency is PENDING, #114 final study workflow regression is PENDING. No claim that a repository-only operation ran Windows installed product tests. **Never merge #185 just because GitHub marks it mergeable.**

## All 74 reopened PRs — original basis and topic

Original base and head identities are taken from the original per-PR audit; the current GitHub `OPEN` status was independently read back. The historical head SHA is NOT silently replaced by current branch head. Follow each linked per-PR case to inspect exact touched files and regression entry points.

| PR | Topic group | Original base | Original head SHA | Reopen outcome / review disposition |
|---|---|---|---|---|
| [#67](https://github.com/bongbong90/Sorigul/pull/67) | 01 foundation and hardening | `review/cuda-release-remediation` | `3181b8f57d78` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#68](https://github.com/bongbong90/Sorigul/pull/68) | 01 foundation and hardening | `review/remediation-a-release-packaging` | `57ac69e58335` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#69](https://github.com/bongbong90/Sorigul/pull/69) | 01 foundation and hardening | `review/remediation-b-process-recovery` | `c393303924f2` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#70](https://github.com/bongbong90/Sorigul/pull/70) | 01 foundation and hardening | `review/remediation-c-colab-oauth-security` | `9a26ef36904c` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#71](https://github.com/bongbong90/Sorigul/pull/71) | 01 foundation and hardening | `review/remediation-d-frontend-filesystem-ux` | `e5a523e7e3e5` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#73](https://github.com/bongbong90/Sorigul/pull/73) | 01 foundation and hardening | `chore/frontend-foundation` | `1ad6ffb54eab` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#74](https://github.com/bongbong90/Sorigul/pull/74) | 01 foundation and hardening | `feature/design-system-foundation` | `5d66771b2762` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#75](https://github.com/bongbong90/Sorigul/pull/75) | 01 foundation and hardening | `feature/app-shell` | `f37916df86e2` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#76](https://github.com/bongbong90/Sorigul/pull/76) | 01 foundation and hardening | `feature/transcription-screen-static-ui` | `154e550e6aef` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#77](https://github.com/bongbong90/Sorigul/pull/77) | 01 foundation and hardening | `feature/transcription-screen-mock-interaction` | `b7cc7cbeb78a` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#78](https://github.com/bongbong90/Sorigul/pull/78) | 02 migration and ui freeze | `audit/legacy-feature-parity` | `94d83d6a6be5` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#79](https://github.com/bongbong90/Sorigul/pull/79) | 02 migration and ui freeze | `docs/migration-contract-review` | `93fcaa73ace5` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#80](https://github.com/bongbong90/Sorigul/pull/80) | 02 migration and ui freeze | `docs/contract-baseline-sync` | `9005f67596d2` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#81](https://github.com/bongbong90/Sorigul/pull/81) | 02 migration and ui freeze | `feature/ui-feature-gap-closure` | `89180a0aa5c6` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#82](https://github.com/bongbong90/Sorigul/pull/82) | 02 migration and ui freeze | `validation/ui-state-ux` | `8b20a0836f82` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#83](https://github.com/bongbong90/Sorigul/pull/83) | 02 migration and ui freeze | `freeze/ui-v1` | `a2d8b5779396` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#84](https://github.com/bongbong90/Sorigul/pull/84) | 02 migration and ui freeze | `feature/core-backend-file-job-migration` | `282110753971` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#85](https://github.com/bongbong90/Sorigul/pull/85) | 02 migration and ui freeze | `feature/transcription-engine-migration` | `2c8b7e561517` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#86](https://github.com/bongbong90/Sorigul/pull/86) | 02 migration and ui freeze | `review/drive-results-desktop-ux-clean` | `1f9aa6472215` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#87](https://github.com/bongbong90/Sorigul/pull/87) | 02 migration and ui freeze | `feature/drive-results-desktop-ux` | `47aa500b5453` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#88](https://github.com/bongbong90/Sorigul/pull/88) | Core / Runtime / Provenance | `validation/full-feature-parity-release` | `1399faec2b66` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#89](https://github.com/bongbong90/Sorigul/pull/89) | Core / Runtime / Provenance | `review/core-workflow-plan` | `cfeca3a49b98` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#90](https://github.com/bongbong90/Sorigul/pull/90) | Core / Runtime / Provenance | `review/core-workflow-phase1` | `bbc0df2f0361` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#91](https://github.com/bongbong90/Sorigul/pull/91) | Core / Runtime / Provenance | `review/core-workflow-phase2-drive` | `89a15decd6f1` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#92](https://github.com/bongbong90/Sorigul/pull/92) | Core / Runtime / Provenance | `review/core-workflow-phase3a-runtime` | `0e61f19242fa` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#93](https://github.com/bongbong90/Sorigul/pull/93) | Core / Runtime / Provenance | `review/core-workflow-phase3b-colab` | `e20c7a906c60` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#94](https://github.com/bongbong90/Sorigul/pull/94) | Core / Runtime / Provenance | `review/core-workflow-phase4-progress` | `57b9d4682535` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#95](https://github.com/bongbong90/Sorigul/pull/95) | Core / Runtime / Provenance | `review/core-workflow-phase5a-regression` | `9db695b6dcc9` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#96](https://github.com/bongbong90/Sorigul/pull/96) | Core / Runtime / Provenance | `review/core-workflow-phase5b-installed-validation` | `94a08f51fb5e` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#98](https://github.com/bongbong90/Sorigul/pull/98) | Core / Runtime / Provenance | `main` | `22ebe3d28170` | **OPEN** · HISTORIC MAIN — HOLD / no direct main merge |
| [#100](https://github.com/bongbong90/Sorigul/pull/100) | 04 runtime and legacy parity | `fix/release-manifest-scalar-provenance` | `b34a7cd01240` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#102](https://github.com/bongbong90/Sorigul/pull/102) | 04 runtime and legacy parity | `feature/study-use-local-runtime-split` | `d80a37b569d0` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#103](https://github.com/bongbong90/Sorigul/pull/103) | 04 runtime and legacy parity | `fix/local-runtime-prebuild-hardening` | `10f369a15bda` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#105](https://github.com/bongbong90/Sorigul/pull/105) | 04 runtime and legacy parity | `test/study-use-installed-synthetic` | `81acb9dfbb32` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#115](https://github.com/bongbong90/Sorigul/pull/115) | 04 runtime and legacy parity | `test/korean-real-speech-fixture` | `80bc2f2cd2d9` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#117](https://github.com/bongbong90/Sorigul/pull/117) | 04 runtime and legacy parity | `audit/full-legacy-parity-rebaseline` | `3d35321c03db` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#119](https://github.com/bongbong90/Sorigul/pull/119) | 04 runtime and legacy parity | `docs/governance-contract-lock` | `d95a5d9281b3` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#120](https://github.com/bongbong90/Sorigul/pull/120) | 04 runtime and legacy parity | `fix/transcription-engine-parity` | `a423ade363c6` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#121](https://github.com/bongbong90/Sorigul/pull/121) | 04 runtime and legacy parity | `fix/notification-folder-open-parity` | `71d6920f2ded` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#129](https://github.com/bongbong90/Sorigul/pull/129) | 04 runtime and legacy parity | `fix/live-folder-change-detection` | `2e4179561995` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#134](https://github.com/bongbong90/Sorigul/pull/134) | 05 parity restoration and security | `audit/full-source-contract-regression` | `f61686e69c47` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#135](https://github.com/bongbong90/Sorigul/pull/135) | 05 parity restoration and security | `fix/filename-week-lesson-parity` | `05efaae352ac` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#137](https://github.com/bongbong90/Sorigul/pull/137) | 05 parity restoration and security | `fix/trusted-windows-system-utilities` | `24a4ecd04aa2` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#139](https://github.com/bongbong90/Sorigul/pull/139) | 05 parity restoration and security | `fix/loopback-host-validation` | `07a642b70193` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#140](https://github.com/bongbong90/Sorigul/pull/140) | 05 parity restoration and security | `fix/global-single-run-enforcement` | `0c3266dd5de2` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#141](https://github.com/bongbong90/Sorigul/pull/141) | 05 parity restoration and security | `fix/active-run-close-protection` | `ef48a5a9a7df` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#142](https://github.com/bongbong90/Sorigul/pull/142) | 05 parity restoration and security | `fix/colab-open-convenience` | `c508e8a69680` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#143](https://github.com/bongbong90/Sorigul/pull/143) | 05 parity restoration and security | `fix/honest-tray-progress-tooltip` | `ec06007e0bbb` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#144](https://github.com/bongbong90/Sorigul/pull/144) | 05 parity restoration and security | `fix/folders-column-sorting` | `665fe8f73b54` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#145](https://github.com/bongbong90/Sorigul/pull/145) | 05 parity restoration and security | `fix/txt-display-encoding-fallback` | `683339687462` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#146](https://github.com/bongbong90/Sorigul/pull/146) | Release governance / historical main | `fix/build-script-trusted-taskkill` | `e7996d8bbc93` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#148](https://github.com/bongbong90/Sorigul/pull/148) | Release governance / historical main | `fix/deterministic-job-object-test` | `90ed22e19bef` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#149](https://github.com/bongbong90/Sorigul/pull/149) | Release governance / historical main | `docs/lock-127-parity-decisions` | `c8c08b39d185` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#152](https://github.com/bongbong90/Sorigul/pull/152) | Release governance / historical main | `audit/full-source-contract-regression-rerun` | `141dec3871c9` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#153](https://github.com/bongbong90/Sorigul/pull/153) | Release governance / historical main | `docs/classify-123-rerun-report` | `d06a74def23a` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#155](https://github.com/bongbong90/Sorigul/pull/155) | Release governance / historical main | `fix/packaged-local-runtime-cuda-selftest` | `09bccc82b3d8` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#157](https://github.com/bongbong90/Sorigul/pull/157) | Release governance / historical main | `gate/fresh-current-head-artifact-revalidation-r2` | `e52bd39a200b` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#158](https://github.com/bongbong90/Sorigul/pull/158) | Release governance / historical main | `docs/classify-6a-r3-blocked-report` | `40d721ebb287` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#160](https://github.com/bongbong90/Sorigul/pull/160) | Release governance / historical main | `test/split-runtime-manifest-gate-reconciliation` | `a33ac99ee47c` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#162](https://github.com/bongbong90/Sorigul/pull/162) | Release governance / historical main | `main` | `4beebf868003` | **OPEN** · HISTORIC MAIN — HOLD / no direct main merge |
| [#163](https://github.com/bongbong90/Sorigul/pull/163) | Native UX / Session guards | `main` | `14c72f0db835` | **OPEN** · HISTORIC MAIN — HOLD / no direct main merge |
| [#165](https://github.com/bongbong90/Sorigul/pull/165) | Native UX / Session guards | `fix/113-preflight-orchestration` | `780dbb1e799f` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#166](https://github.com/bongbong90/Sorigul/pull/166) | Native UX / Session guards | `main` | `780dbb1e799f` | **OPEN** · HISTORIC MAIN — HOLD / no direct main merge |
| [#175](https://github.com/bongbong90/Sorigul/pull/175) | Native UX / Session guards | `fix/113-canonical-session-bootstrap` | `debabd06702d` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#176](https://github.com/bongbong90/Sorigul/pull/176) | Native UX / Session guards | `fix/167-local-worker-utf8-protocol` | `8071886e9cd5` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#177](https://github.com/bongbong90/Sorigul/pull/177) | Native UX / Session guards | `fix/172-forced-retranscription-retry` | `a12b93a1a03a` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#178](https://github.com/bongbong90/Sorigul/pull/178) | Native UX / Session guards | `fix/170-folder-picker-immediate-reconcile` | `82cee4d7c266` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#179](https://github.com/bongbong90/Sorigul/pull/179) | Native UX / Session guards | `fix/171-confirmation-preflight-lifecycle` | `ed3d862df9a8` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#181](https://github.com/bongbong90/Sorigul/pull/181) | Native UX / Session guards | `fix/173-app-lifetime-tray-progress` | `a4e46c8214e4` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#182](https://github.com/bongbong90/Sorigul/pull/182) | Native UX / Session guards | `fix/168-desktop-single-instance` | `62e96d1c3563` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#183](https://github.com/bongbong90/Sorigul/pull/183) | 08 final stabilization threads | `fix/174-guarded-tray-exit` | `36ac439c7f63` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#186](https://github.com/bongbong90/Sorigul/pull/186) | 08 final stabilization threads | `fix/180-manual-week-eduwill-normalization` | `87d7b1e72840` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#187](https://github.com/bongbong90/Sorigul/pull/187) | 08 final stabilization threads | `docs/pre-freeze-plan-reconciliation` | `035db132609b` | **OPEN** · STACKED — assess original-base diff; no main replay |
| [#188](https://github.com/bongbong90/Sorigul/pull/188) | 08 final stabilization threads | `audit/123-final-source-regression-rerun` | `28ba869bec59` | **OPEN** · STACKED — assess original-base diff; no main replay |

## Required completion before issue #205 can close

1. [x] Check exact original ancestry for 74/74 (earlier audit) and commit/PR classification for 153/89.
2. [x] Reopen all GitHub-reopenable historical PRs, read back **74/74 OPEN**.
3. [x] Preserve historical MERGED 13 status without invalid reopen attempts.
4. [ ] Triage each *present-day* historical base↔head merge diff, branch-protection/check status, whether current code is superseded, and approve or reject unnecessary historical merge commits. Do **not** describe historical branch clean-up as application release.
5. [ ] Review/land audit archive #204 into Integration only when release freeze is intentionally superseded and reverified.
6. [ ] Finish #191 fresh normal-profile Core/Runtime pairing, real Korean MP3 #47, and final end-to-end #114 with recorded PASS. Not possible using GitHub API alone.
7. [ ] Confirm no unwanted product/runtime changes; merge the single canonical #185 to `main` **with merge commit** after all #114 and release gates PASS; verify ancestry/commit counts afterward.

**Change scope:** Documentation-only repository audit. No code, installer, media, tokens, auth, settings, user state, protected storage, current Freeze or `main` changed by this branch. Does not change a prior PASS/STOP result retroactively.
