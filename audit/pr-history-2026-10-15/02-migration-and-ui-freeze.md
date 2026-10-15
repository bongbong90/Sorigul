# Historical PR review · B — Migration contracts, UI freeze and first runtime wiring

> 자료: 원본 PR 본문과 GitHub 원본 변경파일 API의 patch. 모든 HEAD는 현 Integration `38b856a0...` 조상임을 비교 검증. PR CLOSED/unmerged는 GitHub에서 직접 MERGED 처리된 기록이 아니라는 구분 필수.

## [PR #78](https://github.com/bongbong90/Sorigul/pull/78) · Migration contract review

- **원본:** Migration contract review and lock; CLOSED / 직접 MERGED 아님; HEAD `94d83d6a6be50bde01e6bfa4410e58e16ead3119`; 원래 base `audit/legacy-feature-parity`.
- **당시 변경 목적:** Legacy→Tauri 이전 계약 검토 및 선택·제외 범위를 문서로 기록.
- **변경 파일 2개:** `docs/project/MIGRATION_CONTRACT.md` (added, +414/-0); `docs/project/MIGRATION_CONTRACT_REVIEW.md` (added, +576/-0).
- **원본 patch 진입점:** `docs/project/MIGRATION_CONTRACT.md` — `@@ -0,0 +1,414 @@`; `docs/project/MIGRATION_CONTRACT_REVIEW.md` — `@@ -0,0 +1,576 @@`.
- **관련 Issue/PR 번호(제목/본문에서 관측, 연계 여부는 원문 대조):** 명시적 Issue 번호 미확인.
- **PR 본문 검증 흔적:** 본문에 구체 테스트 수치 없음(미확인).
- **다음 장애 시 확인:** 현재 계약 우선순위를 적용하며 오래된 migration review를 현행 승인으로 오인하지 않음.
- **현재 계보:** HEAD는 Integration에 이미 포함. 이후 후속 PR로 내용이 변경·대체됐을 수 있으며 설치형/실제 MP3 동작은 별도 검증 필요.

## [PR #79](https://github.com/bongbong90/Sorigul/pull/79) · Baseline sync

- **원본:** Sync project baseline to migration contract; CLOSED / 직접 MERGED 아님; HEAD `93fcaa73ace5011de4c00b005a3f3eec6384c15a`; 원래 base `docs/migration-contract-review`.
- **당시 변경 목적:** 마이그레이션 계약과 프로젝트 기본 문서/실행 기준을 동기화.
- **변경 파일 15개:** `docs/design/APP_SHELL_IMPLEMENTATION.md` (modified, +4/-2); `docs/design/TRANSCRIPTION_MOCK_INTERACTION.md` (modified, +17/-11); `docs/design/TRANSCRIPTION_SCREEN_SPEC.md` (modified, +8/-2); `docs/design/UI_FREEZE_CHECKLIST.md` (modified, +38/-20); `docs/design/UI_STATE_MATRIX.md` (modified, +44/-30); `docs/design/app_shell_spec.md` (modified, +3/-1); `docs/design/color_system.md` (modified, +8/-1); `docs/design/design.md` (modified, +8/-1); `docs/design/icon_system.md` (modified, +3/-3); `docs/project/DEVELOPMENT_RULES.md` (modified, +35/-18); `docs/project/FEATURE_PARITY.md` (modified, +80/-54); `docs/project/LEGACY_FEATURE_PARITY_AUDIT.md` (modified, +2/-0); `docs/project/MIGRATION_CONTRACT.md` (modified, +1/-1); `docs/project/PROJECT_CHARTER.md` (modified, +13/-16); `docs/project/ROADMAP.md` (modified, +22/-57).
- **원본 patch 진입점:** `docs/design/APP_SHELL_IMPLEMENTATION.md` — `@@ -2,6 +2,8 @@`; `docs/design/TRANSCRIPTION_MOCK_INTERACTION.md` — `@@ -2,6 +2,8 @@`; `docs/design/TRANSCRIPTION_SCREEN_SPEC.md` — `@@ -13,10 +13,12 @@ Sidebar:`; `docs/design/UI_FREEZE_CHECKLIST.md` — `@@ -1,25 +1,43 @@`; `docs/design/UI_STATE_MATRIX.md` — `@@ -1,32 +1,46 @@`; `docs/design/app_shell_spec.md` — `@@ -9,6 +9,8 @@`; `docs/design/color_system.md` — `@@ -22,6 +22,13 @@`.
- **관련 Issue/PR 번호(제목/본문에서 관측, 연계 여부는 원문 대조):** 명시적 Issue 번호 미확인.
- **PR 본문 검증 흔적:** 본문에 구체 테스트 수치 없음(미확인).
- **다음 장애 시 확인:** 프로젝트 초기 설정 및 문서 불일치 시 baseline 문서 히스토리 대조.
- **현재 계보:** HEAD는 Integration에 이미 포함. 이후 후속 PR로 내용이 변경·대체됐을 수 있으며 설치형/실제 MP3 동작은 별도 검증 필요.

## [PR #80](https://github.com/bongbong90/Sorigul/pull/80) · UI gap closure

- **원본:** Close migration-contract UI gaps; CLOSED / 직접 MERGED 아님; HEAD `9005f67596d26f9325c535a72bd10bb8c79c350c`; 원래 base `docs/contract-baseline-sync`.
- **당시 변경 목적:** 계약과 UI 간 미구현 항목을 정리해 네비게이션/화면 구성 기능을 연결.
- **변경 파일 18개:** `docs/design/APP_SHELL_IMPLEMENTATION.md` (modified, +2/-2); `docs/design/TRANSCRIPTION_MOCK_INTERACTION.md` (modified, +12/-4); `frontend/src/App.tsx` (modified, +48/-2); `frontend/src/components/icons/AppIcons.tsx` (modified, +5/-5); `frontend/src/components/layout/AppShell.tsx` (modified, +40/-10); `frontend/src/components/transcription/CurrentTaskSection.tsx` (modified, +24/-4); `frontend/src/components/transcription/QueueTable.tsx` (modified, +55/-2); `frontend/src/components/transcription/TranscriptionActions.tsx` (modified, +19/-1); `frontend/src/components/ui/Badge.tsx` (modified, +5/-1); `frontend/src/main.tsx` (modified, +1/-0); `frontend/src/pages/FoldersPage.tsx` (added, +162/-0); `frontend/src/pages/LogPage.tsx` (added, +109/-0); `frontend/src/pages/SettingsPage.tsx` (added, +87/-0); `frontend/src/pages/TranscriptionPage.tsx` (modified, +472/-38); `frontend/src/styles/components.css` (modified, +21/-0); `frontend/src/styles/feature-pages.css` (added, +672/-0); `frontend/src/styles/tokens.css` (modified, +8/-0); `frontend/src/styles/transcription-screen.css` (modified, +20/-1).
- **원본 patch 진입점:** `docs/design/APP_SHELL_IMPLEMENTATION.md` — `@@ -2,7 +2,7 @@`; `docs/design/TRANSCRIPTION_MOCK_INTERACTION.md` — `@@ -1,8 +1,8 @@`; `frontend/src/App.tsx` — `@@ -1,10 +1,56 @@`; `frontend/src/components/icons/AppIcons.tsx` — `@@ -1,4 +1,4 @@`; `frontend/src/components/layout/AppShell.tsx` — `@@ -1,12 +1,12 @@`; `frontend/src/components/transcription/CurrentTaskSection.tsx` — `@@ -2,7 +2,17 @@ import { Badge } from '../ui/Badge'`; `frontend/src/components/transcription/QueueTable.tsx` — `@@ -1,14 +1,26 @@`.
- **관련 Issue/PR 번호(제목/본문에서 관측, 연계 여부는 원문 대조):** 명시적 Issue 번호 미확인.
- **PR 본문 검증 흔적:** 본문에 구체 테스트 수치 없음(미확인).
- **다음 장애 시 확인:** 전사·로그·폴더·설정 화면과 Legacy UI 계약 차이 조사 진입점.
- **현재 계보:** HEAD는 Integration에 이미 포함. 이후 후속 PR로 내용이 변경·대체됐을 수 있으며 설치형/실제 MP3 동작은 별도 검증 필요.

## [PR #81](https://github.com/bongbong90/Sorigul/pull/81) · UI state validation

- **원본:** Validate UI state and UX for freeze; CLOSED / 직접 MERGED 아님; HEAD `89180a0aa5c68bfd115d5e564cf5af1cf12f0afc`; 원래 base `feature/ui-feature-gap-closure`.
- **당시 변경 목적:** UI 상태 매트릭스를 바탕으로 정상·오류·진행 흐름을 검증하고 근거 기록.
- **변경 파일 2개:** `docs/design/UI_STATE_UX_VALIDATION.md` (added, +79/-0); `frontend/src/pages/TranscriptionPage.tsx` (modified, +9/-5).
- **원본 patch 진입점:** `docs/design/UI_STATE_UX_VALIDATION.md` — `@@ -0,0 +1,79 @@`; `frontend/src/pages/TranscriptionPage.tsx` — `@@ -128,11 +128,15 @@ export function TranscriptionPage() {`.
- **관련 Issue/PR 번호(제목/본문에서 관측, 연계 여부는 원문 대조):** 명시적 Issue 번호 미확인.
- **PR 본문 검증 흔적:** 본문에 구체 테스트 수치 없음(미확인).
- **다음 장애 시 확인:** 상태별 버튼 불일치/시각 오류 시 UI_STATE_MATRIX와 원 검증 기록 참조.
- **현재 계보:** HEAD는 Integration에 이미 포함. 이후 후속 PR로 내용이 변경·대체됐을 수 있으며 설치형/실제 MP3 동작은 별도 검증 필요.

## [PR #82](https://github.com/bongbong90/Sorigul/pull/82) · UI freeze v1

- **원본:** Freeze Sorigul UI v1; CLOSED / 직접 MERGED 아님; HEAD `8b20a0836f82d7e4df55e28b1fef1f2fc8a4f0e7`; 원래 base `validation/ui-state-ux`.
- **당시 변경 목적:** UI v1 Freeze의 구성요소·승인 범위·금지 사항을 고정.
- **변경 파일 2개:** `docs/design/UI_FREEZE_CHECKLIST.md` (modified, +26/-26); `docs/design/UI_FREEZE_V1.md` (added, +92/-0).
- **원본 patch 진입점:** `docs/design/UI_FREEZE_CHECKLIST.md` — `@@ -4,40 +4,40 @@`; `docs/design/UI_FREEZE_V1.md` — `@@ -0,0 +1,92 @@`.
- **관련 Issue/PR 번호(제목/본문에서 관측, 연계 여부는 원문 대조):** 명시적 Issue 번호 미확인.
- **PR 본문 검증 흔적:** 본문에 구체 테스트 수치 없음(미확인).
- **다음 장애 시 확인:** 후속 #193/#194 사용자 변경 승인과 초기 Freeze를 구분.
- **현재 계보:** HEAD는 Integration에 이미 포함. 이후 후속 PR로 내용이 변경·대체됐을 수 있으며 설치형/실제 MP3 동작은 별도 검증 필요.

## [PR #83](https://github.com/bongbong90/Sorigul/pull/83) · Backend job foundation

- **원본:** Migrate core backend file and job foundation; CLOSED / 직접 MERGED 아님; HEAD `a2d8b577939660cec634a8fba5eecda1b8eb9348`; 원래 base `freeze/ui-v1`.
- **당시 변경 목적:** 파일 스캔·Job 상태·전사 실행 기반 백엔드 토대를 구축.
- **변경 파일 11개:** `backend/requirements.txt` (added, +5/-0); `backend/src/api/routes.py` (added, +162/-0); `backend/src/domain/models.py` (added, +55/-0); `backend/src/main.py` (added, +10/-0); `backend/src/services/job_manager.py` (added, +118/-0); `backend/src/services/normalizer.py` (added, +135/-0); `backend/src/services/renamer.py` (added, +40/-0); `backend/src/services/scanner.py` (added, +66/-0); `backend/src/utils/paths.py` (added, +13/-0); `backend/tests/test_core.py` (added, +254/-0); `docs/backend/CORE_BACKEND_FILE_JOB_MIGRATION.md` (added, +76/-0).
- **원본 patch 진입점:** `backend/requirements.txt` — `@@ -0,0 +1,5 @@`; `backend/src/api/routes.py` — `@@ -0,0 +1,162 @@`; `backend/src/domain/models.py` — `@@ -0,0 +1,55 @@`; `backend/src/main.py` — `@@ -0,0 +1,10 @@`; `backend/src/services/job_manager.py` — `@@ -0,0 +1,118 @@`; `backend/src/services/normalizer.py` — `@@ -0,0 +1,135 @@`; `backend/src/services/renamer.py` — `@@ -0,0 +1,40 @@`.
- **관련 Issue/PR 번호(제목/본문에서 관측, 연계 여부는 원문 대조):** 명시적 Issue 번호 미확인.
- **PR 본문 검증 흔적:** 본문에 구체 테스트 수치 없음(미확인).
- **다음 장애 시 확인:** Job API/파일분류 저장 결함 시 기본 migration 코드와 최신 routes/job_manager를 비교.
- **현재 계보:** HEAD는 Integration에 이미 포함. 이후 후속 PR로 내용이 변경·대체됐을 수 있으며 설치형/실제 MP3 동작은 별도 검증 필요.

## [PR #84](https://github.com/bongbong90/Sorigul/pull/84) · Transcription engines

- **원본:** Migrate transcription engines; CLOSED / 직접 MERGED 아님; HEAD `28211075397156fa585ceea27889f3b19a4d1a3b`; 원래 base `feature/core-backend-file-job-migration`.
- **당시 변경 목적:** Local Whisper 및 Colab 엔진 경로의 이전/연결을 구현.
- **변경 파일 16개:** `backend/requirements-whisper.txt` (added, +2/-0); `backend/src/api/routes.py` (modified, +90/-52); `backend/src/domain/models.py` (modified, +4/-0); `backend/src/domain/transcription.py` (added, +164/-0); `backend/src/engines/__init__.py` (added, +4/-0); `backend/src/engines/colab.py` (added, +440/-0); `backend/src/engines/local_whisper.py` (added, +154/-0); `backend/src/services/job_manager.py` (modified, +42/-8); `backend/src/services/output_bundle.py` (added, +196/-0); `backend/src/services/scanner.py` (modified, +4/-1); `backend/src/services/transcription_runner.py` (added, +377/-0); `backend/tests/test_colab_engine.py` (added, +412/-0); `backend/tests/test_core.py` (modified, +13/-0); `backend/tests/test_local_and_output.py` (added, +291/-0); `backend/tests/test_transcription_runner.py` (added, +175/-0); `docs/backend/TRANSCRIPTION_ENGINE_MIGRATION.md` (added, +159/-0).
- **원본 patch 진입점:** `backend/requirements-whisper.txt` — `@@ -0,0 +1,2 @@`; `backend/src/api/routes.py` — `@@ -1,10 +1,15 @@`; `backend/src/domain/models.py` — `@@ -46,10 +46,14 @@ class JobModel(BaseModel):`; `backend/src/domain/transcription.py` — `@@ -0,0 +1,164 @@`; `backend/src/engines/__init__.py` — `@@ -0,0 +1,4 @@`; `backend/src/engines/colab.py` — `@@ -0,0 +1,440 @@`; `backend/src/engines/local_whisper.py` — `@@ -0,0 +1,154 @@`.
- **관련 Issue/PR 번호(제목/본문에서 관측, 연계 여부는 원문 대조):** 명시적 Issue 번호 미확인.
- **PR 본문 검증 흔적:** 본문에 구체 테스트 수치 없음(미확인).
- **다음 장애 시 확인:** Local/Colab 선택과 실행 오류는 최신 Runtime 소스와 후속 #119/#191 변경 함께 확인.
- **현재 계보:** HEAD는 Integration에 이미 포함. 이후 후속 PR로 내용이 변경·대체됐을 수 있으며 설치형/실제 MP3 동작은 별도 검증 필요.

## [PR #85](https://github.com/bongbong90/Sorigul/pull/85) · Drive and desktop UX

- **원본:** Migrate Drive results and desktop UX; CLOSED / 직접 MERGED 아님; HEAD `2c8b7e561517963d54a744323075fabf5b4433a1`; 원래 base `feature/transcription-engine-migration`.
- **당시 변경 목적:** Drive 결과 업로드와 Desktop 사용자 플로우의 초기 이전.
- **변경 파일 22개:** `backend/requirements.txt` (modified, +4/-1); `backend/src/api/routes.py` (modified, +191/-5); `backend/src/domain/models.py` (modified, +34/-0); `backend/src/main.py` (modified, +9/-0); `backend/src/services/desktop_state.py` (added, +141/-0); `backend/src/services/drive.py` (added, +367/-0); `backend/src/services/job_manager.py` (modified, +2/-0); `backend/src/services/results.py` (added, +176/-0); `backend/src/services/settings.py` (added, +99/-0); `backend/src/services/transcription_runner.py` (modified, +18/-1); `backend/tests/test_drive_results_desktop.py` (added, +351/-0); `backend/tests/test_transcription_runner.py` (modified, +75/-0); `docs/backend/DRIVE_RESULTS_DESKTOP_UX_MIGRATION.md` (added, +173/-0); `frontend/src/api/client.ts` (added, +267/-0); `frontend/src/components/transcription/CurrentTaskSection.tsx` (modified, +12/-3); `frontend/src/components/transcription/QueueTable.tsx` (modified, +4/-0); `frontend/src/components/ui/Progress.tsx` (modified, +8/-1); `frontend/src/pages/FoldersPage.tsx` (modified, +71/-139); `frontend/src/pages/LogPage.tsx` (modified, +40/-83); `frontend/src/pages/SettingsPage.tsx` (modified, +53/-64); `frontend/src/pages/TranscriptionPage.tsx` (modified, +150/-570); `frontend/src/styles/components.css` (modified, +14/-0).
- **원본 patch 진입점:** `backend/requirements.txt` — `@@ -2,4 +2,7 @@ fastapi`; `backend/src/api/routes.py` — `@@ -1,6 +1,6 @@`; `backend/src/domain/models.py` — `@@ -21,6 +21,24 @@ class BundleStatus(str, Enum):`; `backend/src/main.py` — `@@ -1,8 +1,17 @@`; `backend/src/services/desktop_state.py` — `@@ -0,0 +1,141 @@`; `backend/src/services/drive.py` — `@@ -0,0 +1,367 @@`; `backend/src/services/job_manager.py` — `@@ -102,6 +102,7 @@ def create_job(`.
- **관련 Issue/PR 번호(제목/본문에서 관측, 연계 여부는 원문 대조):** 명시적 Issue 번호 미확인.
- **PR 본문 검증 흔적:** 본문에 구체 테스트 수치 없음(미확인).
- **다음 장애 시 확인:** OAuth/업로드/결과 폴더 불일치는 최신 Drive UI/Backend 계약으로 역추적.
- **현재 계보:** HEAD는 Integration에 이미 포함. 이후 후속 PR로 내용이 변경·대체됐을 수 있으며 설치형/실제 MP3 동작은 별도 검증 필요.

## [PR #86](https://github.com/bongbong90/Sorigul/pull/86) · Tauri sidecar OS

- **원본:** Integrate Tauri desktop runtime and sidecar; CLOSED / 직접 MERGED 아님; HEAD `1f9aa647221589543f38ab6e5952d1ac06f04135`; 원래 base `review/drive-results-desktop-ux-clean`.
- **당시 변경 목적:** Tauri Desktop와 Backend sidecar 실행·종료·OS 연계 구현.
- **변경 파일 27개:** `docs/runtime/TAURI_RUNTIME_SIDECAR_OS_INTEGRATION.md` (added, +190/-0); `frontend/package-lock.json` (modified, +274/-0); `frontend/package.json` (modified, +7/-1); `frontend/src-tauri/.gitignore` (added, +2/-0); `frontend/src-tauri/Cargo.lock` (added, +5395/-0); `frontend/src-tauri/Cargo.toml` (added, +27/-0); `frontend/src-tauri/build.rs` (added, +3/-0); `frontend/src-tauri/capabilities/default.json` (added, +17/-0); `frontend/src-tauri/icons/128x128.png` (added, +0/-0); `frontend/src-tauri/icons/128x128@2x.png` (added, +0/-0); `frontend/src-tauri/icons/32x32.png` (added, +0/-0); `frontend/src-tauri/icons/64x64.png` (added, +0/-0); `frontend/src-tauri/icons/icon.ico` (added, +0/-0); `frontend/src-tauri/icons/icon.png` (added, +0/-0); `frontend/src-tauri/src/lib.rs` (added, +212/-0); `frontend/src-tauri/src/main.rs` (added, +5/-0); `frontend/src-tauri/src/shutdown.rs` (added, +138/-0); `frontend/src-tauri/src/sidecar.rs` (added, +388/-0); `frontend/src-tauri/tauri.conf.json` (added, +40/-0); `frontend/src/App.tsx` (modified, +2/-0); `frontend/src/api/client.ts` (modified, +14/-1); `frontend/src/hooks/useDesktopNotifications.ts` (added, +71/-0); `frontend/src/lib/native.ts` (added, +40/-0); `frontend/src/pages/FoldersPage.tsx` (modified, +10/-4); `frontend/src/pages/SettingsPage.tsx` (modified, +77/-7); `frontend/src/pages/TranscriptionPage.tsx` (modified, +2/-1); `frontend/vite.config.ts` (modified, +9/-1).
- **원본 patch 진입점:** `docs/runtime/TAURI_RUNTIME_SIDECAR_OS_INTEGRATION.md` — `@@ -0,0 +1,190 @@`; `frontend/package-lock.json` — `@@ -8,11 +8,16 @@`; `frontend/package.json` — `@@ -8,14 +8,20 @@`; `frontend/src-tauri/.gitignore` — `@@ -0,0 +1,2 @@`; `frontend/src-tauri/Cargo.toml` — `@@ -0,0 +1,27 @@`; `frontend/src-tauri/build.rs` — `@@ -0,0 +1,3 @@`; `frontend/src-tauri/capabilities/default.json` — `@@ -0,0 +1,17 @@`.
- **관련 Issue/PR 번호(제목/본문에서 관측, 연계 여부는 원문 대조):** #3, #4, #5, #2.
- **PR 본문 검증 흔적:** - #3 Tauri desktop runtime smoke closure.
- **다음 장애 시 확인:** 실행/중복실행/프로세스 잔류는 Tauri lib.rs·sidecar.rs 후속 #168/#174 참조.
- **현재 계보:** HEAD는 Integration에 이미 포함. 이후 후속 PR로 내용이 변경·대체됐을 수 있으며 설치형/실제 MP3 동작은 별도 검증 필요.

## [PR #87](https://github.com/bongbong90/Sorigul/pull/87) · Parity release gate

- **원본:** Full feature parity release validation; CLOSED / 직접 MERGED 아님; HEAD `47aa500b5453e42f186292b41d9b8054f96bc638`; 원래 base `feature/drive-results-desktop-ux`.
- **당시 변경 목적:** 전체 Legacy 기능 대조와 릴리스 검증 당시 근거 수집.
- **변경 파일 5개:** `backend/src/main.py` (modified, +1/-1); `docs/release/FINAL_FEATURE_PARITY_REGRESSION.md` (added, +54/-0); `docs/release/RELEASE_CHECKLIST.md` (added, +24/-0); `docs/release/RELEASE_NOTES_0.1.0.md` (added, +15/-0); `scripts/build_backend_sidecar.ps1` (modified, +11/-7).
- **원본 patch 진입점:** `backend/src/main.py` — `@@ -6,7 +6,7 @@`; `docs/release/FINAL_FEATURE_PARITY_REGRESSION.md` — `@@ -0,0 +1,54 @@`; `docs/release/RELEASE_CHECKLIST.md` — `@@ -0,0 +1,24 @@`; `docs/release/RELEASE_NOTES_0.1.0.md` — `@@ -0,0 +1,15 @@`; `scripts/build_backend_sidecar.ps1` — `@@ -20,8 +20,9 @@`.
- **관련 Issue/PR 번호(제목/본문에서 관측, 연계 여부는 원문 대조):** 명시적 Issue 번호 미확인.
- **PR 본문 검증 흔적:** 본문에 구체 테스트 수치 없음(미확인).
- **다음 장애 시 확인:** 해당 시점의 PASS는 이후 빌드·실사용 근거가 아니며 #123/#114가 현행 gate.
- **현재 계보:** HEAD는 Integration에 이미 포함. 이후 후속 PR로 내용이 변경·대체됐을 수 있으며 설치형/실제 MP3 동작은 별도 검증 필요.
