# Historical PR review · F — Release-readiness, #113 evidence and obsolete integration proposals

> 실제 변경 파일/patch 및 당시 PR 본문만으로 기술. `main` 대상 구형 통합 PR은 이후 후보로 대체된 이력이지 현재 자동 병합 대상이 아님.

<a id="pr-146"></a>

## [PR #146](https://github.com/bongbong90/Sorigul/pull/146) · Deterministic Job Object QA

- **원본:** test: make Job Object kill-on-close checks deterministic; CLOSED/미병합(단일 GitHub merge 아님); HEAD `e7996d8bbc932c2b67b3a4ef9f70495bf2a0e6d0`; base `fix/build-script-trusted-taskkill`.
- **구현 또는 기록 목적:** Windows Job Object kill-on-close 검사 타이밍과 synthetic 프로세스 관찰을 안정화.
- **변경 파일 1개:** `frontend/src-tauri/src/sidecar.rs` (modified, +59/-15).
- **원본 patch 앵커:** `frontend/src-tauri/src/sidecar.rs` — `@@ -848,11 +848,9 @@ mod tests {`.
- **PR 원문 내 연관 번호:** #138.
- **당시 검증·차단 기록:** kill-on-close tests so the final source regression does not depend on / - root-only test: fixed 500 ms sleep / - root+child test: fixed 800 ms sleep / - real timeout failure when it does not.
- **장애/개발 시 주의:** 자식 프로세스 잔류·강제 종료 테스트 신뢰성은 #56/#63에 최신 실제 설치 검증 필요.
- **후속 계보:** 원본 HEAD는 현재 Integration 조상. 본문 실행 결과는 당시 상태 한정.

<a id="pr-148"></a>

## [PR #148](https://github.com/bongbong90/Sorigul/pull/148) · Parity contract decisions

- **원본:** docs: lock #127 parity decisions; CLOSED/미병합(단일 GitHub merge 아님); HEAD `90ed22e19bef41049f2dc0c4418a7368a7755e4a`; base `fix/deterministic-job-object-test`.
- **구현 또는 기록 목적:** Legacy 대비 사용자 승인 A2/A3/A5 등 기능 차이를 Current Product Contract에 명시.
- **변경 파일 2개:** `docs/project/CURRENT_PRODUCT_CONTRACT.md` (modified, +26/-0); `tests/test_current_product_contract_decisions.py` (added, +97/-0).
- **원본 patch 앵커:** `docs/project/CURRENT_PRODUCT_CONTRACT.md` — `@@ -80,6 +80,7 @@ Legacy ACTIVE user-visible capability와 functional behavior는 기본적으로`; `tests/test_current_product_contract_decisions.py` — `@@ -0,0 +1,97 @@`.
- **PR 원문 내 연관 번호:** #127, #123, #147, #130, #131, #132, #133.
- **당시 검증·차단 기록:** - 'tests/test_current_product_contract_decisions.py': root contract test for the lock; guards against A4 being recorded as a restoration. / | New contract test | 4 passed | / | Root pytest | 82 passed | / | Backend pytest | 536 passed, 2 skipped |.
- **장애/개발 시 주의:** 현행 제품 결정 우선순위와 증거 문서의 상태(LOCKED/HISTORICAL) 확인.
- **후속 계보:** 원본 HEAD는 현재 Integration 조상. 본문 실행 결과는 당시 상태 한정.

<a id="pr-149"></a>

## [PR #149](https://github.com/bongbong90/Sorigul/pull/149) · Fresh #123 full source audit

- **원본:** audit: re-run full source contract regression; CLOSED/미병합(단일 GitHub merge 아님); HEAD `c8c08b39d1854f605d38a8b50660c89994431f6a`; base `docs/lock-127-parity-decisions`.
- **구현 또는 기록 목적:** 전체 Legacy/현 제품 소스 회귀감사 보고서를 새 HEAD 기준으로 기록.
- **변경 파일 1개:** `docs/runtime/STUDY_USE_FULL_SOURCE_CONTRACT_REGRESSION_2026-09-30.md` (added, +272/-0).
- **원본 patch 앵커:** `docs/runtime/STUDY_USE_FULL_SOURCE_CONTRACT_REGRESSION_2026-09-30.md` — `@@ -0,0 +1,272 @@`.
- **PR 원문 내 연관 번호:** #123, #113, #56, #63, #47, #48, #60, #58.
- **당시 검증·차단 기록:** - SOURCE FULL REGRESSION = PASS / ## Test results / - frontend lint/typecheck/build: PASS / - Rust fmt/check/clippy/all-targets: PASS.
- **장애/개발 시 주의:** 당시 audit Source와 10/15 Integration의 #123 결과를 혼동하지 않음.
- **후속 계보:** 원본 HEAD는 현재 Integration 조상. 본문 실행 결과는 당시 상태 한정.

<a id="pr-152"></a>

## [PR #152](https://github.com/bongbong90/Sorigul/pull/152) · #123 report classification

- **원본:** docs: classify #123 rerun report; CLOSED/미병합(단일 GitHub merge 아님); HEAD `141dec3871c9daf484fc6f3d41fcdfaa53a45f27`; base `audit/full-source-contract-regression-rerun`.
- **구현 또는 기록 목적:** 새 #123 문서가 문서 분류표의 exact-once gate를 통과하도록 historical로 등록.
- **변경 파일 2개:** `docs/project/CURRENT_SOURCE_OF_TRUTH.md` (modified, +1/-0); `tests/test_release_readiness_contracts.py` (modified, +1/-0).
- **원본 patch 앵커:** `docs/project/CURRENT_SOURCE_OF_TRUTH.md` — `@@ -102,6 +102,7 @@ Classification values are exact: CURRENT CONTRACT, SUPERSEDED, HISTORICAL E`; `tests/test_release_readiness_contracts.py` — `@@ -9,6 +9,7 @@`.
- **PR 원문 내 연관 번호:** #123, #151, #150, #113.
- **당시 검증·차단 기록:** It records the #123 PASS at fixed audit HEAD 'c8c08b39d1854f605d38a8b50660c89994431f6a'. It does not create current product authority or automatically approve later source or artif / - lock the 9/30 report in the test 'HISTORICAL_EVIDENCE' set / ## Tests / - 'git diff --check': PASS.
- **장애/개발 시 주의:** #199/#200 재발 문제의 선례. 신규 docs/*.md은 ledger와 historical lock 일치 확인.
- **후속 계보:** 원본 HEAD는 현재 Integration 조상. 본문 실행 결과는 당시 상태 한정.

<a id="pr-153"></a>

## [PR #153](https://github.com/bongbong90/Sorigul/pull/153) · Packaged CUDA selftest

- **원본:** fix: restore packaged Local Runtime CUDA self-test; CLOSED/미병합(단일 GitHub merge 아님); HEAD `d06a74def23af7e8a571e3ed9a106cf0ab150f30`; base `docs/classify-123-rerun-report`.
- **구현 또는 기록 목적:** 설치형 Local Runtime에서 CUDA 실제 self-test 경로가 작동하도록 수정.
- **변경 파일 2개:** `backend/tests/test_sidecar_cuda_contract.py` (modified, +55/-0); `scripts/build_local_whisper_runtime.ps1` (modified, +74/-3).
- **원본 patch 앵커:** `backend/tests/test_sidecar_cuda_contract.py` — `@@ -150,6 +150,61 @@ def test_core_self_test_excludes_local_runtime_and_local_self_test_is_bounded():`; `scripts/build_local_whisper_runtime.ps1` — `@@ -10,6 +10,9 @@`.
- **PR 원문 내 연관 번호:** #113, #150, #123.
- **당시 검증·차단 기록:** ## Failure / A fresh PyInstaller Local Runtime candidate built successfully and returned a successful CUDA self-test JSON response, but the Windows PowerShell 5 build script read its process ex / - failed candidate promoted: NO / Windows PowerShell 5 'Start-Process -PassThru' did not retain the native process handle on the bounded polling path. Once the process exited, 'ExitCode' remained '$null'; '$null -n.
- **장애/개발 시 주의:** #191 Runtime pairing과 CUDA tensor 성공은 별개; 설치형 프로필에서 재증명 필요.
- **후속 계보:** 원본 HEAD는 현재 Integration 조상. 본문 실행 결과는 당시 상태 한정.

<a id="pr-155"></a>

## [PR #155](https://github.com/bongbong90/Sorigul/pull/155) · Fresh current-head installed QA

- **원본:** test: validate fresh current-head installed artifact; CLOSED/미병합(단일 GitHub merge 아님); HEAD `09bccc82b3d86a72986d6df0bfba32594c662b07`; base `fix/packaged-local-runtime-cuda-selftest`.
- **구현 또는 기록 목적:** 빌드·설치·Runtime 연결과 실제 Tauri 구동에 대한 #113 검증 시도 근거 기록.
- **변경 파일 1개:** `docs/runtime/STUDY_USE_CURRENT_HEAD_INSTALLED_VALIDATION_2026-10-02.md` (added, +282/-0).
- **원본 patch 앵커:** `docs/runtime/STUDY_USE_CURRENT_HEAD_INSTALLED_VALIDATION_2026-10-02.md` — `@@ -0,0 +1,282 @@`.
- **PR 원문 내 연관 번호:** #113, #150, #154, #45, #153, #123, #116, #115.
- **당시 검증·차단 기록:** CLOSED / VERIFIED — historical isolated CUDA PASS and handle-retention fix are preserved. The #150 candidate was not reused and #150 was not reopened. Full #123 rerun after #150 re / - 'git diff --check' and staged diff check: PASS. / #113 body/checkpoint, #45 checkpoint, #116 BODY, PR #115 and #7 updated. #56/#63 remain OPEN and pending; no current fresh installed identity is available for them. #123 historical.
- **장애/개발 시 주의:** blocked/PASS 이력을 시도별로 구분하고 현재 Core/Local Artifact 증거로 재사용 금지.
- **후속 계보:** 원본 HEAD는 현재 Integration 조상. 본문 실행 결과는 당시 상태 한정.

<a id="pr-157"></a>

## [PR #157](https://github.com/bongbong90/Sorigul/pull/157) · Classify blocked #113 report

- **원본:** docs: classify 6A-R3 blocked validation report; CLOSED/미병합(단일 GitHub merge 아님); HEAD `e52bd39a200b29310c81cf479d2020ef912af347`; base `gate/fresh-current-head-artifact-revalidation-r2`.
- **구현 또는 기록 목적:** 차단된 설치 검증 보고서를 역사적 증거로 분류하고 문서 ledger에 등록.
- **변경 파일 2개:** `docs/project/CURRENT_SOURCE_OF_TRUTH.md` (modified, +1/-0); `tests/test_release_readiness_contracts.py` (modified, +1/-0).
- **원본 patch 앵커:** `docs/project/CURRENT_SOURCE_OF_TRUTH.md` — `@@ -100,6 +100,7 @@ Classification values are exact: CURRENT CONTRACT, SUPERSEDED, HISTORICAL E`; `tests/test_release_readiness_contracts.py` — `@@ -9,6 +9,7 @@`.
- **PR 원문 내 연관 번호:** #156, #154, #113.
- **당시 검증·차단 기록:** - 'git diff --check': PASS. / - Exact diff: only 'docs/project/CURRENT_SOURCE_OF_TRUTH.md' and 'tests/test_release_readiness_contracts.py'; report body and product/runtime/packaging source unchanged..
- **장애/개발 시 주의:** #201과는 별개 문서 분류 이슈; 새 문서에는 분류표 누락 방지.
- **후속 계보:** 원본 HEAD는 현재 Integration 조상. 본문 실행 결과는 당시 상태 한정.

<a id="pr-158"></a>

## [PR #158](https://github.com/bongbong90/Sorigul/pull/158) · Split runtime manifest gate

- **원본:** test: lock split-runtime manifest gate; CLOSED/미병합(단일 GitHub merge 아님); HEAD `40d721ebb287ec5a1eda60f77ac3f40c99813f37`; base `docs/classify-6a-r3-blocked-report`.
- **구현 또는 기록 목적:** Core는 경량 provenance, Local이 Torch/CUDA 검증 소유한다는 계약과 테스트 고정.
- **변경 파일 6개:** `backend/tests/test_local_and_output.py` (modified, +99/-0); `backend/tests/test_release_packaging_contract.py` (modified, +16/-1); `docs/project/CURRENT_PRODUCT_CONTRACT.md` (modified, +10/-0); `docs/project/CURRENT_SOURCE_OF_TRUTH.md` (modified, +13/-3); `docs/release/CURRENT_RELEASE_STATUS.md` (modified, +33/-21); `tests/test_release_readiness_contracts.py` (modified, +41/-0).
- **원본 patch 앵커:** `backend/tests/test_local_and_output.py` — `@@ -159,6 +159,105 @@ def test_runtime_manifest_provenance_is_required_and_must_match(runtime_dir):`; `backend/tests/test_release_packaging_contract.py` — `@@ -329,6 +329,8 @@ def test_manifest_contains_release_identity_without_personal_data_fields():`; `docs/project/CURRENT_PRODUCT_CONTRACT.md` — `@@ -198,6 +198,16 @@ Legacy의 display-only queue clear 버튼은 복구하지 않는다. (#127 A4, A`; `docs/project/CURRENT_SOURCE_OF_TRUTH.md` — `@@ -24,9 +24,19 @@ ambiguous authority.`; `docs/release/CURRENT_RELEASE_STATUS.md` — `@@ -14,20 +14,31 @@ This is the living current release ledger, not a historical validation artifact.`; `tests/test_release_readiness_contracts.py` — `@@ -152,6 +152,47 @@ def test_cuda_and_python_release_contracts_remain_exact():`.
- **PR 원문 내 연관 번호:** #154, #45, #113, #123, #159, #116, #115, #7.
- **당시 검증·차단 기록:** - Protect Core field absence, installer non-consumption, Local scalar/JSON round-trip validation and fail-closed runtime identity/provenance/hash checks. Existing mismatch and work / - packaging targeted: 18 PASS / 0 SKIPPED / - Local/output targeted: 60 PASS / 0 SKIPPED / - release readiness: 14 PASS / 0 SKIPPED.
- **장애/개발 시 주의:** #191 manifest/Source HEAD mismatch가 실제로 무엇을 막는지 추적.
- **후속 계보:** 원본 HEAD는 현재 Integration 조상. 본문 실행 결과는 당시 상태 한정.

<a id="pr-160"></a>

## [PR #160](https://github.com/bongbong90/Sorigul/pull/160) · PS5 self-test observation

- **원본:** test: lock Core self-test process observation on PowerShell 5; CLOSED/미병합(단일 GitHub merge 아님); HEAD `a33ac99ee47c040692e0dd4cf0149795baa4e92a`; base `test/split-runtime-manifest-gate-reconciliation`.
- **구현 또는 기록 목적:** PowerShell 5 환경에서 packaged Core 자체검증의 프로세스 관찰과 타이밍을 신뢰할 수 있게 보강.
- **변경 파일 1개:** `backend/tests/test_core_powershell5_process_observation.py` (added, +217/-0).
- **원본 patch 앵커:** `backend/tests/test_core_powershell5_process_observation.py` — `@@ -0,0 +1,217 @@`.
- **PR 원문 내 연관 번호:** #159, #158, #123, #45, #113, #116, #115, #7.
- **당시 검증·차단 기록:** PR: https://github.com/bongbong90/Sorigul/pull/160 — OPEN / NOT MERGED, base 'test/split-runtime-manifest-gate-reconciliation'. / - Base: 'test/split-runtime-manifest-gate-reconciliation' / exact start HEAD '40d721ebb287ec5a1eda60f77ac3f40c99813f37'; parent PR #158 OPEN / MERGEABLE / NOT MERGED at preflight a / - Branch: 'fix/core-powershell5-selftest-handle-retention'; exact local / remote tracking / live remote HEAD: 'a33ac99ee47c040692e0dd4cf0149795baa4e92a' (all identical). / - Commit: 'a33ac99ee47c040692e0dd4cf0149795baa4e92a' — 'test: lock Core self-test process observation on PowerShell 5'..
- **장애/개발 시 주의:** PS5 프로세스 ID·종료시점 오관찰과 실제 orphan 여부 구분.
- **후속 계보:** 원본 HEAD는 현재 Integration 조상. 본문 실행 결과는 당시 상태 한정.

<a id="pr-162"></a>

## [PR #162](https://github.com/bongbong90/Sorigul/pull/162) · Obsolete main integration candidate

- **원본:** integrate: consolidate Study-Use release candidate through #161; CLOSED/미병합(단일 GitHub merge 아님); HEAD `4beebf86800300b8af9e7cf5f1d0d9608c410e19`; base `main`.
- **구현 또는 기록 목적:** #161까지의 과거 통합 후보를 main에 제안했으나 후속 통합 후보로 대체되어 CLOSED.
- **변경 파일 100개:** `README.md` (modified, +10/-20); `backend/packaging/sorigul_backend.spec` (modified, +6/-15); `backend/packaging/sorigul_local_runtime.spec` (added, +60/-0); `backend/src/api/routes.py` (modified, +118/-1); `backend/src/engines/colab.py` (modified, +32/-1); `backend/src/engines/local_whisper.py` (modified, +513/-112); `backend/src/local_runtime_main.py` (added, +215/-0); `backend/src/main.py` (modified, +11/-0); `backend/src/services/drive.py` (modified, +19/-3); `backend/src/services/folder_revision.py` (added, +58/-0); `backend/src/services/normalizer.py` (modified, +50/-11); `backend/src/services/results.py` (modified, +30/-8); `backend/src/services/transcription_runner.py` (modified, +45/-5); `backend/src/services/windows_system.py` (added, +55/-0); `backend/src/sidecar_main.py` (modified, +3/-72); `backend/tests/test_close_guard.py` (added, +231/-0); `backend/tests/test_colab_bootstrap_security.py` (modified, +67/-10); `backend/tests/test_colab_engine.py` (modified, +54/-1); `backend/tests/test_colab_rendezvous.py` (modified, +4/-1); `backend/tests/test_core_powershell5_process_observation.py` (added, +217/-0); `backend/tests/test_filename_normalizer_parity.py` (added, +247/-0); `backend/tests/test_folder_revision.py` (added, +202/-0); `backend/tests/test_global_single_run.py` (added, +373/-0); `backend/tests/test_installer_powershell5_restricted_invocation.py` (added, +226/-0); `backend/tests/test_local_and_output.py` (modified, +468/-108); `backend/tests/test_loopback_host_security.py` (added, +155/-0); `backend/tests/test_notification_folder_intent.py` (added, +151/-0); `backend/tests/test_package_c_security.py` (modified, +36/-10); `backend/tests/test_process_recovery_contracts.py` (modified, +55/-47); `backend/tests/test_release_packaging_contract.py` (modified, +126/-8); `backend/tests/test_sidecar_cuda_contract.py` (modified, +168/-167); `backend/tests/test_txt_display_encoding_fallback.py` (added, +260/-0); `backend/tests/test_windows_system_utilities.py` (added, +219/-0); `colab/README.md` (modified, +5/-5); `colab/requirements.txt` (modified, +3/-1); `colab/sorigul_colab_bootstrap.py` (modified, +69/-20); `docs/README.md` (modified, +7/-6); `docs/migration/CORE_WORKFLOW_REFINEMENT_PLAN.md` (modified, +2/-0); `docs/project/CURRENT_PRODUCT_CONTRACT.md` (added, +266/-0); `docs/project/CURRENT_SOURCE_OF_TRUTH.md` (modified, +53/-34); `docs/project/DEVELOPMENT_RULES.md` (modified, +58/-27); `docs/project/FEATURE_PARITY.md` (modified, +2/-0); `docs/project/LEGACY_FEATURE_PARITY_AUDIT.md` (modified, +2/-0); `docs/project/MIGRATION_CONTRACT.md` (modified, +2/-0); `docs/project/MIGRATION_CONTRACT_REVIEW.md` (modified, +2/-0); `docs/project/PROJECT_CHARTER.md` (modified, +35/-39); `docs/project/ROADMAP.md` (modified, +29/-20); `docs/project/SORIGUL_FULL_LEGACY_PARITY_COMPLETION_PLAN_2026-09-28.md` (added, +864/-0); `docs/release/CURRENT_RELEASE_STATUS.md` (modified, +33/-21); `docs/runtime/STUDY_USE_CURRENT_HEAD_INSTALLED_VALIDATION_2026-10-02.md` (added, +282/-0); `docs/runtime/STUDY_USE_FULL_SOURCE_CONTRACT_REGRESSION_2026-09-29.md` (added, +396/-0); `docs/runtime/STUDY_USE_FULL_SOURCE_CONTRACT_REGRESSION_2026-09-29_LEGACY_INVENTORY.md` (added, +350/-0); `docs/runtime/STUDY_USE_FULL_SOURCE_CONTRACT_REGRESSION_2026-09-30.md` (added, +272/-0); `docs/runtime/STUDY_USE_INSTALLED_SYNTHETIC_VALIDATION_2026-09-28.md` (added, +224/-0); `docs/runtime/STUDY_USE_KOREAN_REAL_SPEECH_FIXTURE_VALIDATION_2026-09-28.md` (added, +165/-0); `docs/runtime/TAURI_RUNTIME_SIDECAR_OS_INTEGRATION.md` (modified, +18/-5); `frontend/src-tauri/Cargo.toml` (modified, +1/-0); `frontend/src-tauri/capabilities/completion-toast.json` (added, +10/-0); `frontend/src-tauri/src/close_guard.rs` (added, +422/-0); `frontend/src-tauri/src/completion_toast.rs` (added, +288/-0); `frontend/src-tauri/src/lib.rs` (modified, +433/-30); `frontend/src-tauri/src/shutdown.rs` (modified, +36/-5); `frontend/src-tauri/src/sidecar.rs` (modified, +105/-19); `frontend/src-tauri/src/tray_tooltip.rs` (added, +203/-0); `frontend/src-tauri/src/windows_system.rs` (added, +162/-0); `frontend/src-tauri/tauri.conf.json` (modified, +15/-0); `frontend/src/api/client.ts` (modified, +19/-6); `frontend/src/components/notification/CompletionToast.tsx` (added, +88/-0); `frontend/src/components/transcription/ActiveRunBanner.tsx` (added, +47/-0); `frontend/src/components/transcription/CurrentTaskSection.tsx` (modified, +2/-38); `frontend/src/components/transcription/EngineSection.tsx` (modified, +26/-2); `frontend/src/components/transcription/QueueTable.tsx` (modified, +4/-0); `frontend/src/components/transcription/TranscriptionActions.tsx` (modified, +3/-1); `frontend/src/components/transcription/currentTaskStatus.ts` (added, +38/-0); `frontend/src/hooks/useDesktopNotifications.ts` (modified, +39/-13); `frontend/src/hooks/useFolderRevision.ts` (added, +37/-0); `frontend/src/hooks/useTrayProgress.ts` (added, +76/-0); `frontend/src/lib/colabSetup.ts` (added, +9/-0); `frontend/src/lib/folderRevisionWatcher.ts` (added, +85/-0); `frontend/src/lib/folderSort.ts` (added, +40/-0); `frontend/src/lib/native.ts` (modified, +76/-0); `frontend/src/main.tsx` (modified, +6/-3); `frontend/src/pages/FoldersPage.tsx` (modified, +83/-18); `frontend/src/pages/SettingsPage.tsx` (modified, +2/-2); `frontend/src/pages/TranscriptionPage.tsx` (modified, +124/-19); `frontend/src/styles/completion-toast.css` (added, +54/-0); `frontend/src/styles/feature-pages.css` (modified, +72/-0); `frontend/src/styles/transcription-screen.css` (modified, +33/-0); `scripts/build_backend_sidecar.ps1` (modified, +69/-62); `scripts/build_local_whisper_runtime.ps1` (added, +352/-0); `scripts/build_windows_installer.ps1` (modified, +82/-5); `tests/test_active_run_close_contracts.py` (added, +102/-0); `tests/test_colab_open_convenience_contracts.py` (added, +110/-0); `tests/test_core_workflow_release_contracts.py` (modified, +21/-0); `tests/test_current_product_contract_decisions.py` (added, +97/-0); `tests/test_folders_sort_contracts.py` (added, +109/-0); `tests/test_global_single_run_contracts.py` (added, +106/-0); `tests/test_live_folder_change_contracts.py` (added, +225/-0); `tests/test_loopback_host_contracts.py` (added, +35/-0); `tests/test_notification_folder_open_contracts.py` (added, +175/-0).
- **원본 patch 앵커:** `README.md` — `@@ -1,39 +1,29 @@`; `backend/packaging/sorigul_backend.spec` — `@@ -14,16 +14,13 @@ console window for the backend child. sidecar_main.py's --self-test`; `backend/packaging/sorigul_local_runtime.spec` — `@@ -0,0 +1,60 @@`; `backend/src/api/routes.py` — `@@ -1,3 +1,4 @@`; `backend/src/engines/colab.py` — `@@ -26,6 +26,8 @@`; `backend/src/engines/local_whisper.py` — `@@ -1,7 +1,14 @@`; `backend/src/local_runtime_main.py` — `@@ -0,0 +1,215 @@`; `backend/src/main.py` — `@@ -1,5 +1,6 @@`.
- **PR 원문 내 연관 번호:** #161, #6, #98, #100, #102, #103, #105, #115.
- **당시 검증·차단 기록:** 본문 테스트 증거 미확인.
- **장애/개발 시 주의:** 현재 main 승격은 오직 #185. 이전 main용 PR을 재오픈하여 별도 병합하지 않음.
- **후속 계보:** 원본 HEAD는 현재 Integration 조상. 본문 실행 결과는 당시 상태 한정.
