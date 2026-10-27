# Historical PR review · D — Runtime split, real speech fixture, parity and recovery

> 원본 GitHub changed-file/patch·PR 본문 기준. HEAD ancestor를 확인한 상태이나 하위 문서의 'PASS'는 작성 당시 한정. 고객 실사용과 현 릴리스 판정은 별도.

<a id="pr-100"></a>

## [PR #100](https://github.com/bongbong90/Sorigul/pull/100) · Runtime split

- **원본:** refactor: split Local Whisper runtime from Core; CLOSED / 직접 병합 아님; HEAD `b34a7cd012403552b0e98376d39e7003e7e4cb2c`; 원래 base `fix/release-manifest-scalar-provenance`.
- **당시 변경 목적:** Whisper 모델·Torch·CUDA 무거운 의존성을 Core에서 분리해 별도 Local Runtime으로 구축.
- **변경 파일 14개:** `backend/packaging/sorigul_backend.spec` (modified, +6/-15); `backend/packaging/sorigul_local_runtime.spec` (added, +60/-0); `backend/src/engines/local_whisper.py` (modified, +436/-112); `backend/src/local_runtime_main.py` (added, +178/-0); `backend/src/services/transcription_runner.py` (modified, +8/-2); `backend/src/sidecar_main.py` (modified, +3/-72); `backend/tests/test_local_and_output.py` (modified, +287/-116); `backend/tests/test_process_recovery_contracts.py` (modified, +55/-47); `backend/tests/test_release_packaging_contract.py` (modified, +17/-32); `backend/tests/test_sidecar_cuda_contract.py` (modified, +102/-167); `scripts/build_backend_sidecar.ps1` (modified, +24/-78); `scripts/build_local_whisper_runtime.ps1` (added, +264/-0); `scripts/build_windows_installer.ps1` (modified, +5/-14); `tests/test_release_readiness_contracts.py` (modified, +6/-4).
- **코드·테스트 앵커:** `backend/packaging/sorigul_backend.spec` — `@@ -14,16 +14,13 @@ console window for the backend child. sidecar_main.py's --self-test`; `backend/packaging/sorigul_local_runtime.spec` — `@@ -0,0 +1,60 @@`; `backend/src/engines/local_whisper.py` — `@@ -1,7 +1,14 @@`; `backend/src/local_runtime_main.py` — `@@ -0,0 +1,178 @@`; `backend/src/services/transcription_runner.py` — `@@ -22,7 +22,10 @@`; `backend/src/sidecar_main.py` — `@@ -7,9 +7,9 @@`; `backend/tests/test_local_and_output.py` — `@@ -1,15 +1,31 @@`; `backend/tests/test_process_recovery_contracts.py` — `@@ -1,20 +1,20 @@`.
- **관련 원문 표기 번호:** #97, #46.
- **원본 PR의 검증 표기:** - PowerShell syntax: PASS / - git diff --check: PASS.
- **문제 재발 시:** #191의 Core/Local provenance pairing 실패 시 manifest와 split-boundary 빌드·탐색 코드를 대조.
- **현재 이력:** PR HEAD가 Integration의 조상. 해당 파일의 최신 내용이 이 패치와 같은지는 보장하지 않으며 현재 검증으로 다시 판정.

<a id="pr-102"></a>

## [PR #102](https://github.com/bongbong90/Sorigul/pull/102) · Prebuild provenance

- **원본:** fix: harden Local Runtime pre-build provenance; CLOSED / 직접 병합 아님; HEAD `d80a37b569d0ccd27faf11fe9dbac7e486cc0ea1`; 원래 base `feature/study-use-local-runtime-split`.
- **당시 변경 목적:** Local Runtime 사전 빌드의 manifest·해시·Core 일치성 검사 강화.
- **변경 파일 6개:** `backend/src/engines/local_whisper.py` (modified, +73/-3); `backend/tests/test_local_and_output.py` (modified, +17/-0); `backend/tests/test_release_packaging_contract.py` (modified, +9/-2); `backend/tests/test_sidecar_cuda_contract.py` (modified, +13/-2); `scripts/build_backend_sidecar.ps1` (modified, +12/-2); `scripts/build_windows_installer.ps1` (modified, +8/-1).
- **코드·테스트 앵커:** `backend/src/engines/local_whisper.py` — `@@ -29,6 +29,7 @@`; `backend/tests/test_local_and_output.py` — `@@ -142,6 +142,23 @@ def test_runtime_manifest_missing_invalid_version_and_hash_fail_closed(tmp_path,`; `backend/tests/test_release_packaging_contract.py` — `@@ -319,6 +319,7 @@ def test_manifest_contains_release_identity_without_personal_data_fields():`; `backend/tests/test_sidecar_cuda_contract.py` — `@@ -106,9 +106,20 @@ def test_core_build_has_no_local_install_and_scans_archive():`; `scripts/build_backend_sidecar.ps1` — `@@ -12,7 +12,8 @@`; `scripts/build_windows_installer.ps1` — `@@ -10,7 +10,6 @@`.
- **관련 원문 표기 번호:** #100, #98, #101, #99, #97, #46.
- **원본 PR의 검증 표기:** - corresponding regression tests / PRE-BUILD REVIEW = PASS / - PowerShell syntax: PASS.
- **문제 재발 시:** 잘못된 Local 산출물 수용을 막는 fail-closed 로직과 build script 확인.
- **현재 이력:** PR HEAD가 Integration의 조상. 해당 파일의 최신 내용이 이 패치와 같은지는 보장하지 않으며 현재 검증으로 다시 판정.

<a id="pr-103"></a>

## [PR #103](https://github.com/bongbong90/Sorigul/pull/103) · Installed synthetic split QA

- **원본:** test: validate split runtime installed synthetic gate; CLOSED / 직접 병합 아님; HEAD `10f369a15bda49c2e3277a1ecac7aace432cd6e7`; 원래 base `fix/local-runtime-prebuild-hardening`.
- **당시 변경 목적:** 분리 Runtime을 설치형 환경에서 synthetic으로 검증하는 게이트 확립.
- **변경 파일 4개:** `backend/tests/test_release_packaging_contract.py` (modified, +10/-0); `docs/runtime/STUDY_USE_INSTALLED_SYNTHETIC_VALIDATION_2026-09-28.md` (added, +224/-0); `scripts/build_backend_sidecar.ps1` (modified, +4/-1); `scripts/build_windows_installer.ps1` (modified, +4/-1).
- **코드·테스트 앵커:** `backend/tests/test_release_packaging_contract.py` — `@@ -354,6 +354,7 @@ def test_installer_rejects_malformed_or_stale_manifest_before_frontend_build():`; `docs/runtime/STUDY_USE_INSTALLED_SYNTHETIC_VALIDATION_2026-09-28.md` — `@@ -0,0 +1,224 @@`; `scripts/build_backend_sidecar.ps1` — `@@ -370,7 +370,10 @@ result_path.write_text(imageio_ffmpeg.get_ffmpeg_exe(), encoding="utf-8")`; `scripts/build_windows_installer.ps1` — `@@ -78,7 +78,10 @@ try {`.
- **관련 원문 표기 번호:** #46, #98, #100, #102, #97, #99.
- **원본 PR의 검증 표기:** - Local Runtime build: PASS — 1,911.45 MiB, SHA-256 '7504ca7811434e5ba0d633135d445994585ca551a83891eb6b414148f34b302a' / - Local CUDA synthetic: PASS — protocol 1, 'device=cuda', clean exit / - Core build: PASS — 35.05 MiB, SHA-256 'c106ddea7ab2e6989d284b2fb93630b6d9f5113f7a2f16f98f4a8d456fdab8b9'.
- **문제 재발 시:** synthetic 통과와 실제 사용자 MP3/일반 프로필 구분 필수.
- **현재 이력:** PR HEAD가 Integration의 조상. 해당 파일의 최신 내용이 이 패치와 같은지는 보장하지 않으며 현재 검증으로 다시 판정.

<a id="pr-105"></a>

## [PR #105](https://github.com/bongbong90/Sorigul/pull/105) · Korean CUDA speech fixture

- **원본:** test: validate Local CUDA with Korean real-speech fixtures; CLOSED / 직접 병합 아님; HEAD `81acb9dfbb324719bd7780c432d5aec1da328aab`; 원래 base `test/study-use-installed-synthetic`.
- **당시 변경 목적:** 한글 음성 fixture와 GPU 실행 경계의 테스트 근거 수집.
- **변경 파일 1개:** `docs/runtime/STUDY_USE_KOREAN_REAL_SPEECH_FIXTURE_VALIDATION_2026-09-28.md` (added, +165/-0).
- **코드·테스트 앵커:** `docs/runtime/STUDY_USE_KOREAN_REAL_SPEECH_FIXTURE_VALIDATION_2026-09-28.md` — `@@ -0,0 +1,165 @@`.
- **관련 원문 표기 번호:** #46, #47, #104.
- **원본 PR의 검증 표기:** - records a 60-second short fixture PASS on actual CUDA / - records a 29:32 repeated-real-speech stress fixture PASS on actual CUDA.
- **문제 재발 시:** 사용자 #47 학습강의 실제 재생·전사 품질 검증을 대체하지 않음.
- **현재 이력:** PR HEAD가 Integration의 조상. 해당 파일의 최신 내용이 이 패치와 같은지는 보장하지 않으며 현재 검증으로 다시 판정.

<a id="pr-115"></a>

## [PR #115](https://github.com/bongbong90/Sorigul/pull/115) · Legacy parity completion roadmap

- **원본:** docs: rebaseline full Legacy parity completion plan (planning/checkpoint only); CLOSED / 직접 병합 아님; HEAD `80bc2f2cd2d95e66d52fddc6d091f89df8fa1180`; 원래 base `test/korean-real-speech-fixture`.
- **당시 변경 목적:** Legacy 대응 범위·Issue·시간표·체크포인트를 재정의하는 과거 계획 이력.
- **변경 파일 1개:** `docs/project/SORIGUL_FULL_LEGACY_PARITY_COMPLETION_PLAN_2026-09-28.md` (added, +864/-0).
- **코드·테스트 앵커:** `docs/project/SORIGUL_FULL_LEGACY_PARITY_COMPLETION_PLAN_2026-09-28.md` — `@@ -0,0 +1,864 @@`.
- **관련 원문 표기 번호:** #116, #7, #189, #113, #56, #63.
- **원본 PR의 검증 표기:** Official deadline updated in #116 and #7. Historical 2026-10-31 checkpoints below remain audit history only. Goal: installed, working Korean MP3 Local-GPU study transcription with  / - Source/upstream/tracked identity and existing Freeze: 250/250 PASS, unchanged. No new Freeze or canonical preflight rerun. / - New canonical session ACTIVE and Single Writer acquisition/competition denial PASS..
- **문제 재발 시:** 과거 마감·계획 기록은 현 10/25 마감 및 최신 Current Product Contract를 덮지 않음.
- **현재 이력:** PR HEAD가 Integration의 조상. 해당 파일의 최신 내용이 이 패치와 같은지는 보장하지 않으며 현재 검증으로 다시 판정.

<a id="pr-117"></a>

## [PR #117](https://github.com/bongbong90/Sorigul/pull/117) · Contract/governance lock

- **원본:** docs: lock development governance and current product contract; CLOSED / 직접 병합 아님; HEAD `3d35321c03db8304b524909520a7398c6689f73a`; 원래 base `audit/full-legacy-parity-rebaseline`.
- **당시 변경 목적:** 개발 규칙 및 사용자 승인된 현재 제품 계약·증거 우선순위 고정.
- **변경 파일 12개:** `README.md` (modified, +10/-20); `docs/README.md` (modified, +7/-6); `docs/migration/CORE_WORKFLOW_REFINEMENT_PLAN.md` (modified, +2/-0); `docs/project/CURRENT_PRODUCT_CONTRACT.md` (added, +230/-0); `docs/project/CURRENT_SOURCE_OF_TRUTH.md` (modified, +32/-30); `docs/project/DEVELOPMENT_RULES.md` (modified, +58/-27); `docs/project/FEATURE_PARITY.md` (modified, +2/-0); `docs/project/LEGACY_FEATURE_PARITY_AUDIT.md` (modified, +2/-0); `docs/project/MIGRATION_CONTRACT.md` (modified, +2/-0); `docs/project/MIGRATION_CONTRACT_REVIEW.md` (modified, +2/-0); `docs/project/PROJECT_CHARTER.md` (modified, +35/-39); `docs/project/ROADMAP.md` (modified, +29/-20).
- **코드·테스트 앵커:** `README.md` — `@@ -1,39 +1,29 @@`; `docs/README.md` — `@@ -1,10 +1,11 @@`; `docs/migration/CORE_WORKFLOW_REFINEMENT_PLAN.md` — `@@ -5,6 +5,8 @@ Status: LOCKED (Phase 0 — documentation only, no implementation)`; `docs/project/CURRENT_PRODUCT_CONTRACT.md` — `@@ -0,0 +1,230 @@`; `docs/project/CURRENT_SOURCE_OF_TRUTH.md` — `@@ -4,16 +4,16 @@`; `docs/project/DEVELOPMENT_RULES.md` — `@@ -1,37 +1,68 @@`; `docs/project/FEATURE_PARITY.md` — `@@ -1,5 +1,7 @@`; `docs/project/LEGACY_FEATURE_PARITY_AUDIT.md` — `@@ -1,5 +1,7 @@`.
- **관련 원문 표기 번호:** #107, #112, #106.
- **원본 PR의 검증 표기:** - full Issue/branch/test/commit/push/PR/Tracker lifecycle / - 'git diff --check': PASS / - relative Markdown link validation: PASS.
- **문제 재발 시:** Issue/PR 절차·외부 유료 서비스 금지·Historical vs Current 충돌 해석.
- **현재 이력:** PR HEAD가 Integration의 조상. 해당 파일의 최신 내용이 이 패치와 같은지는 보장하지 않으며 현재 검증으로 다시 판정.

<a id="pr-119"></a>

## [PR #119](https://github.com/bongbong90/Sorigul/pull/119) · Engine parity

- **원본:** fix: restore Local and Colab transcription engine parity; CLOSED / 직접 병합 아님; HEAD `d95a5d9281b3144f209500f7ff193a4216703c76`; 원래 base `docs/governance-contract-lock`.
- **당시 변경 목적:** Legacy 요구에 맞춰 Local medium·Colab large-v3 선택·실행 계약 복구.
- **변경 파일 13개:** `backend/src/engines/colab.py` (modified, +32/-1); `backend/src/local_runtime_main.py` (modified, +40/-3); `backend/tests/test_colab_bootstrap_security.py` (modified, +67/-10); `backend/tests/test_colab_engine.py` (modified, +54/-1); `backend/tests/test_colab_rendezvous.py` (modified, +4/-1); `backend/tests/test_local_and_output.py` (modified, +74/-1); `backend/tests/test_package_c_security.py` (modified, +6/-0); `colab/requirements.txt` (modified, +3/-1); `colab/sorigul_colab_bootstrap.py` (modified, +69/-20); `docs/project/CURRENT_SOURCE_OF_TRUTH.md` (modified, +3/-0); `frontend/src/components/transcription/EngineSection.tsx` (modified, +2/-2); `frontend/src/pages/TranscriptionPage.tsx` (modified, +1/-1); `tests/test_core_workflow_release_contracts.py` (modified, +21/-0).
- **코드·테스트 앵커:** `backend/src/engines/colab.py` — `@@ -26,6 +26,8 @@`; `backend/src/local_runtime_main.py` — `@@ -12,6 +12,20 @@`; `backend/tests/test_colab_bootstrap_security.py` — `@@ -1,5 +1,6 @@`; `backend/tests/test_colab_engine.py` — `@@ -1,4 +1,5 @@`; `backend/tests/test_colab_rendezvous.py` — `@@ -293,7 +293,10 @@ class FakeResponse:`; `backend/tests/test_local_and_output.py` — `@@ -273,12 +273,22 @@ def test_worker_output_verification_rejects_missing_txt(runtime_dir, tmp_path):`; `backend/tests/test_package_c_security.py` — `@@ -97,10 +97,16 @@ def test_direct_client_signs_health_and_audio_hash(tmp_path, monkeypatch):`; `colab/requirements.txt` — `@@ -1,4 +1,6 @@`.
- **관련 원문 표기 번호:** #106, #113, #118.
- **원본 PR의 검증 표기:** - frontend lint: PASS / - frontend typecheck: PASS / - frontend production build: PASS.
- **문제 재발 시:** CPU/GPU fallback·Colab 모델 선택·실 API와 mock 결과를 구별.
- **현재 이력:** PR HEAD가 Integration의 조상. 해당 파일의 최신 내용이 이 패치와 같은지는 보장하지 않으며 현재 검증으로 다시 판정.

<a id="pr-120"></a>

## [PR #120](https://github.com/bongbong90/Sorigul/pull/120) · Actionable notification

- **원본:** feat: restore actionable completion notification; CLOSED / 직접 병합 아님; HEAD `a423ade363c6ac671862e7fbc706bc0c829874d6`; 원래 base `fix/transcription-engine-parity`.
- **당시 변경 목적:** 전사 종료 알림에서 실제 결과 폴더를 열거나 확인하는 Desktop 행동 복구.
- **변경 파일 14개:** `backend/src/api/routes.py` (modified, +22/-1); `backend/src/services/results.py` (modified, +13/-0); `backend/tests/test_notification_folder_intent.py` (added, +151/-0); `docs/runtime/TAURI_RUNTIME_SIDECAR_OS_INTEGRATION.md` (modified, +16/-3); `frontend/src-tauri/capabilities/completion-toast.json` (added, +10/-0); `frontend/src-tauri/src/completion_toast.rs` (added, +288/-0); `frontend/src-tauri/src/lib.rs` (modified, +294/-8); `frontend/src-tauri/tauri.conf.json` (modified, +15/-0); `frontend/src/components/notification/CompletionToast.tsx` (added, +88/-0); `frontend/src/hooks/useDesktopNotifications.ts` (modified, +39/-13); `frontend/src/lib/native.ts` (modified, +56/-0); `frontend/src/main.tsx` (modified, +6/-3); `frontend/src/styles/completion-toast.css` (added, +54/-0); `tests/test_notification_folder_open_contracts.py` (added, +164/-0).
- **코드·테스트 앵커:** `backend/src/api/routes.py` — `@@ -37,7 +37,13 @@`; `backend/src/services/results.py` — `@@ -174,3 +174,16 @@ def _resolve_item(self, scan_id: str, item_id: str, expected_suffix: Optional[st`; `backend/tests/test_notification_folder_intent.py` — `@@ -0,0 +1,151 @@`; `docs/runtime/TAURI_RUNTIME_SIDECAR_OS_INTEGRATION.md` — `@@ -92,8 +92,19 @@ Verified with real spawned processes in sidecar.rs tests (not mocked): cleanu`; `frontend/src-tauri/capabilities/completion-toast.json` — `@@ -0,0 +1,10 @@`; `frontend/src-tauri/src/completion_toast.rs` — `@@ -0,0 +1,288 @@`; `frontend/src-tauri/src/lib.rs` — `@@ -1,3 +1,4 @@`; `frontend/src-tauri/tauri.conf.json` — `@@ -18,6 +18,21 @@`.
- **관련 원문 표기 번호:** #110, #56, #63, #113.
- **원본 PR의 검증 표기:** - 'eventKey' dedup, first-poll snapshot ignore and 4s polling are unchanged. When several unseen events arrive in one poll, they are handled oldest-first, so the toast ends on the  / | Backend full | 397 passed, 1 skipped (pre-existing non-Windows-only test) | / | Frontend lint / typecheck / build | PASS / PASS / PASS |.
- **문제 재발 시:** 알림 경로 접근, Native 소유 폴더 검증과 트레이 운영을 함께 확인.
- **현재 이력:** PR HEAD가 Integration의 조상. 해당 파일의 최신 내용이 이 패치와 같은지는 보장하지 않으며 현재 검증으로 다시 판정.

<a id="pr-121"></a>

## [PR #121](https://github.com/bongbong90/Sorigul/pull/121) · Live folder updates

- **원본:** feat: restore live transcription-folder change detection; CLOSED / 직접 병합 아님; HEAD `71d6920f2ded69868c877916af3095130099e838`; 원래 base `fix/notification-folder-open-parity`.
- **당시 변경 목적:** 선택 폴더의 새로운 파일/변경을 감지·목록에 반영하는 기능 복원.
- **변경 파일 9개:** `backend/src/api/routes.py` (modified, +15/-0); `backend/src/services/folder_revision.py` (added, +58/-0); `backend/tests/test_folder_revision.py` (added, +202/-0); `frontend/src/api/client.ts` (modified, +16/-6); `frontend/src/hooks/useFolderRevision.ts` (added, +37/-0); `frontend/src/lib/folderRevisionWatcher.ts` (added, +85/-0); `frontend/src/pages/FoldersPage.tsx` (modified, +59/-15); `frontend/src/pages/TranscriptionPage.tsx` (modified, +27/-3); `tests/test_live_folder_change_contracts.py` (added, +225/-0).
- **코드·테스트 앵커:** `backend/src/api/routes.py` — `@@ -44,6 +44,7 @@`; `backend/src/services/folder_revision.py` — `@@ -0,0 +1,58 @@`; `backend/tests/test_folder_revision.py` — `@@ -0,0 +1,202 @@`; `frontend/src/api/client.ts` — `@@ -119,6 +119,11 @@ export interface FolderScanResult {`; `frontend/src/hooks/useFolderRevision.ts` — `@@ -0,0 +1,37 @@`; `frontend/src/lib/folderRevisionWatcher.ts` — `@@ -0,0 +1,85 @@`; `frontend/src/pages/FoldersPage.tsx` — `@@ -1,6 +1,7 @@`; `frontend/src/pages/TranscriptionPage.tsx` — `@@ -13,6 +13,7 @@ import {`.
- **관련 원문 표기 번호:** #111, #63, #56, #113.
- **원본 PR의 검증 표기:** - revision targeted ('backend/tests/test_folder_revision.py'): 19 passed, 1 skipped (symlink creation not permitted on host) / - root contracts: 40 passed (incl. Node-driven watcher behavior test: no storm, max 1 in flight, stop/abort; mutation-checked) / - frontend lint / typecheck / build: PASS.
- **문제 재발 시:** stale scan/폴더 변경 시 #170, Job 선택 상태와 동기화 점검.
- **현재 이력:** PR HEAD가 Integration의 조상. 해당 파일의 최신 내용이 이 패치와 같은지는 보장하지 않으며 현재 검증으로 다시 판정.

<a id="pr-129"></a>

## [PR #129](https://github.com/bongbong90/Sorigul/pull/129) · Full parity source audit

- **원본:** docs: validate full Legacy and current-contract source regression; CLOSED / 직접 병합 아님; HEAD `2e4179561995dfa1910f75f6d509e8160bac732e`; 원래 base `fix/live-folder-change-detection`.
- **당시 변경 목적:** Legacy/Current 제품 계약 대비 전체 소스 수준 회귀감사 결과 기록.
- **변경 파일 3개:** `docs/project/CURRENT_SOURCE_OF_TRUTH.md` (modified, +2/-0); `docs/runtime/STUDY_USE_FULL_SOURCE_CONTRACT_REGRESSION_2026-09-29.md` (added, +396/-0); `docs/runtime/STUDY_USE_FULL_SOURCE_CONTRACT_REGRESSION_2026-09-29_LEGACY_INVENTORY.md` (added, +350/-0).
- **코드·테스트 앵커:** `docs/project/CURRENT_SOURCE_OF_TRUTH.md` — `@@ -100,6 +100,8 @@ Classification values are exact: CURRENT CONTRACT, SUPERSEDED, HISTORICAL E`; `docs/runtime/STUDY_USE_FULL_SOURCE_CONTRACT_REGRESSION_2026-09-29.md` — `@@ -0,0 +1,396 @@`; `docs/runtime/STUDY_USE_FULL_SOURCE_CONTRACT_REGRESSION_2026-09-29_LEGACY_INVENTORY.md` — `@@ -0,0 +1,350 @@`.
- **관련 원문 표기 번호:** #123, #124, #125, #126, #128, #127.
- **원본 PR의 검증 표기:** | Root contract tests | 40 passed (re-run after the ledger edit: 40 passed) | / | 'cargo test --locked --offline' | 54 passed | / #122 evidence: under Git Bash the two known Drive tests fail (2 failed, '/usr/bin/whoami.exe'). This is not a new regression..
- **문제 재발 시:** #123 재실행·최근 버전 source/installed validation과 과거 감사 구분.
- **현재 이력:** PR HEAD가 Integration의 조상. 해당 파일의 최신 내용이 이 패치와 같은지는 보장하지 않으며 현재 검증으로 다시 판정.
