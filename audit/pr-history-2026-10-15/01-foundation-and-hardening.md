# Historical PR review · A — Packaging, security and first UI foundations

> 기준: 2026-10-15 GitHub PR 본문·변경 파일·patch; 각 PR HEAD는 Integration `38b856a0...`의 조상임을 별도 compare 검증. CLOSED는 GitHub MERGED가 아님. 후속 커밋이 코드를 바꿨을 수 있으므로 **PR 당시 변경**만 서술.
> 상태 표기: 검증 = 과거 PR 문서에 적힌 주장일 수 있으며 현 설치본의 증명 아님. 공개 Diff는 원본 PR에서 열람.

## [PR #67](https://github.com/bongbong90/Sorigul/pull/67) · A: Release packaging hardening

- **원본:** Package A: harden release packaging gates; CLOSED / GitHub 미병합; PR HEAD `3181b8f57d7825b2b412dc7b77966cce5d4773be`; 원래 base `review/cuda-release-remediation`; 현재 Integration 조상 커밋(추가 병합 불필요).
- **문제·변경 목적:** Core/Installer 배포 스크립트와 self-test 경계 및 release packaging 계약 검증 강화.
- **변경 파일 7개 (원본 diff 실재 경로):** `.gitignore` (modified, +1/-0); `backend/src/sidecar_main.py` (modified, +131/-42); `backend/tests/test_release_packaging_contract.py` (added, +212/-0); `backend/tests/test_sidecar_cuda_contract.py` (modified, +15/-12); `frontend/src-tauri/tauri.conf.json` (modified, +1/-0); `scripts/build_backend_sidecar.ps1` (modified, +348/-221); `scripts/build_windows_installer.ps1` (modified, +94/-43).
- **대표 변경 위치:** `.gitignore` — `@@ -40,3 +40,4 @@ token*.json`; `backend/src/sidecar_main.py` — `@@ -13,8 +13,27 @@`; `backend/tests/test_release_packaging_contract.py` — `@@ -0,0 +1,212 @@`; `backend/tests/test_sidecar_cuda_contract.py` — `@@ -119,9 +119,7 @@ def test_ffmpeg_resolver_uses_utf8_temp_result_without_stdout_capture():`; `frontend/src-tauri/tauri.conf.json` — `@@ -36,6 +36,7 @@`; `scripts/build_backend_sidecar.ps1` — `@@ -1,50 +1,138 @@`; `scripts/build_windows_installer.ps1` — `@@ -1,40 +1,40 @@`.
- **관련 참조(제목/본문 등장 번호, 실제 종속성은 링크에서 검증):** #8, #9, #10, #12, #13, #64.
- **기존 PR의 테스트/검증 표기:** - stale MSI first-match false pass 제거 / - bounded packaged self-test + progressive log / - 검증 후 transactional promotion + rollback.
- **장애 대응 시작점:** 패키징 실패·FFmpeg/CUDA·manifest 문제 시 sidecar_main 및 두 빌드 스크립트, packaging 테스트를 함께 대조.
- **계보 주의:** PR 자체는 미병합 상태로 종료됐지만 head 커밋은 현 Integration 계보에 포함; 현재 동작 동일성은 최신 파일 및 테스트 재확인 필요.

## [PR #68](https://github.com/bongbong90/Sorigul/pull/68) · B: Job/recovery boundaries

- **원본:** Package B: harden process and recovery boundaries; CLOSED / GitHub 미병합; PR HEAD `57ac69e58335f31545c2e778791e8f9f62ae0e68`; 원래 base `review/remediation-a-release-packaging`; 현재 Integration 조상 커밋(추가 병합 불필요).
- **문제·변경 목적:** Job 상태 저장·복구, Colab chunk, Drive 결과물, 취소 및 API 경계를 강화.
- **변경 파일 16개 (원본 diff 실재 경로):** `backend/src/api/routes.py` (modified, +125/-29); `backend/src/domain/transcription.py` (modified, +11/-0); `backend/src/engines/colab.py` (modified, +182/-25); `backend/src/engines/local_whisper.py` (modified, +8/-2); `backend/src/services/drive.py` (modified, +169/-9); `backend/src/services/job_manager.py` (modified, +105/-33); `backend/src/services/output_bundle.py` (modified, +12/-0); `backend/src/services/transcription_runner.py` (modified, +177/-27); `backend/tests/conftest.py` (added, +94/-0); `backend/tests/test_app_data_isolation.py` (added, +139/-0); `backend/tests/test_colab_engine.py` (modified, +319/-26); `backend/tests/test_core.py` (modified, +29/-25); `backend/tests/test_process_recovery_contracts.py` (added, +841/-0); `backend/tests/test_transcription_runner.py` (modified, +4/-4); `frontend/src-tauri/src/lib.rs` (modified, +8/-8); `frontend/src-tauri/src/sidecar.rs` (modified, +526/-63).
- **대표 변경 위치:** `backend/src/api/routes.py` — `@@ -30,7 +30,13 @@`; `backend/src/domain/transcription.py` — `@@ -127,13 +127,20 @@ class CancellationToken:`; `backend/src/engines/colab.py` — `@@ -26,6 +26,128 @@`; `backend/src/engines/local_whisper.py` — `@@ -121,8 +121,14 @@ def transcribe(`; `backend/src/services/drive.py` — `@@ -1,12 +1,16 @@`; `backend/src/services/job_manager.py` — `@@ -4,10 +4,22 @@`; `backend/src/services/output_bundle.py` — `@@ -93,7 +93,17 @@ def commit(`.
- **관련 참조(제목/본문 등장 번호, 실제 종속성은 링크에서 검증):** #14, #16, #17, #18, #19, #20.
- **기존 PR의 테스트/검증 표기:** - pytest pre-collection app-data isolation / - #21 pytest real app-data isolation / ## 검증 상태.
- **장애 대응 시작점:** 실패·재시도·데이터 보존·Chunk 상태 불일치 시 job_manager/runner/output_bundle·Drive 경계와 관련 테스트 확인.
- **계보 주의:** PR 자체는 미병합 상태로 종료됐지만 head 커밋은 현 Integration 계보에 포함; 현재 동작 동일성은 최신 파일 및 테스트 재확인 필요.

## [PR #69](https://github.com/bongbong90/Sorigul/pull/69) · C: External-auth security

- **원본:** Package C: secure Colab and OAuth boundaries; CLOSED / GitHub 미병합; PR HEAD `c393303924f202d6c0045365331ed0a73a49479f`; 원래 base `review/remediation-b-process-recovery`; 현재 Integration 조상 커밋(추가 병합 불필요).
- **문제·변경 목적:** Colab rendezvous URL·서명/신선도 확인과 Google Drive OAuth callback 보안 경계 보완.
- **변경 파일 24개 (원본 diff 실재 경로):** `backend/requirements.txt` (modified, +1/-0); `backend/src/api/routes.py` (modified, +2/-1); `backend/src/engines/colab.py` (modified, +29/-5); `backend/src/services/colab_rendezvous.py` (modified, +61/-11); `backend/src/services/colab_security.py` (added, +185/-0); `backend/src/services/colab_url.py` (modified, +12/-1); `backend/src/services/drive.py` (modified, +216/-41); `backend/src/services/transcription_runner.py` (modified, +20/-5); `backend/tests/test_colab_bootstrap_security.py` (added, +271/-0); `backend/tests/test_colab_engine.py` (modified, +21/-4); `backend/tests/test_colab_rendezvous.py` (modified, +174/-4); `backend/tests/test_drive_oauth_loopback.py` (modified, +140/-1); `backend/tests/test_package_c_security.py` (added, +309/-0); `backend/tests/test_tauri_csp_security.py` (added, +73/-0); `colab/README.md` (modified, +30/-0); `colab/requirements.txt` (modified, +1/-0); `colab/sorigul_colab_bootstrap.py` (modified, +340/-113); `frontend/src-tauri/tauri.conf.json` (modified, +2/-1); `frontend/src/api/client.ts` (modified, +4/-2); `frontend/src/components/transcription/EngineSection.tsx` (modified, +39/-7); `frontend/src/components/ui/Progress.tsx` (modified, +12/-13); `frontend/src/pages/TranscriptionPage.tsx` (modified, +1/-1); `frontend/src/styles/components.css` (modified, +31/-8); `frontend/src/styles/feature-pages.css` (modified, +5/-0).
- **대표 변경 위치:** `backend/requirements.txt` — `@@ -7,3 +7,4 @@ google-api-python-client`; `backend/src/api/routes.py` — `@@ -619,7 +619,8 @@ def poll_colab_rendezvous(request_id: str):`; `backend/src/engines/colab.py` — `@@ -22,6 +22,7 @@`; `backend/src/services/colab_rendezvous.py` — `@@ -1,18 +1,21 @@`; `backend/src/services/colab_security.py` — `@@ -0,0 +1,185 @@`; `backend/src/services/colab_url.py` — `@@ -1,3 +1,4 @@`; `backend/src/services/drive.py` — `@@ -1,9 +1,12 @@`.
- **관련 참조(제목/본문 등장 번호, 실제 종속성은 링크에서 검증):** #23, #24, #25, #26, #27, #28.
- **기존 PR의 테스트/검증 표기:** ## 검증 상태.
- **장애 대응 시작점:** 외부 연결 실패 시 Colab URL·rendezvous·OAuth loopback 코드 및 보안 테스트 확인; 실 API 성공 근거는 별도.
- **계보 주의:** PR 자체는 미병합 상태로 종료됐지만 head 커밋은 현 Integration 계보에 포함; 현재 동작 동일성은 최신 파일 및 테스트 재확인 필요.

## [PR #70](https://github.com/bongbong90/Sorigul/pull/70) · D: Frontend/filesystem integrity

- **원본:** Package D: harden frontend and filesystem UX integrity; CLOSED / GitHub 미병합; PR HEAD `9a26ef36904c0641ad279707bf60240a839314d1`; 원래 base `review/remediation-c-colab-oauth-security`; 현재 Integration 조상 커밋(추가 병합 불필요).
- **문제·변경 목적:** 파일 이름 변경 검증, 설정 저장, UI native 파일 선택·실행 상태 경계를 보완.
- **변경 파일 22개 (원본 diff 실재 경로):** `backend/src/api/routes.py` (modified, +17/-5); `backend/src/services/renamer.py` (modified, +45/-11); `backend/src/services/settings.py` (modified, +23/-6); `backend/src/services/transcription_runner.py` (modified, +22/-1); `backend/src/sidecar_main.py` (modified, +20/-1); `backend/tests/test_package_d_ux_integrity.py` (added, +292/-0); `frontend/src-tauri/Cargo.lock` (modified, +1/-0); `frontend/src-tauri/Cargo.toml` (modified, +1/-0); `frontend/src-tauri/src/lib.rs` (modified, +104/-2); `frontend/src-tauri/src/sidecar.rs` (modified, +32/-3); `frontend/src/App.tsx` (modified, +28/-1); `frontend/src/api/client.ts` (modified, +110/-47); `frontend/src/components/layout/AppShell.tsx` (modified, +21/-2); `frontend/src/components/transcription/EngineSection.tsx` (modified, +142/-75); `frontend/src/hooks/useCloseBehaviorSync.ts` (modified, +8/-3); `frontend/src/hooks/useDesktopNotifications.ts` (modified, +16/-8); `frontend/src/lib/native.ts` (modified, +30/-0); `frontend/src/pages/LogPage.tsx` (modified, +15/-5); `frontend/src/pages/SettingsPage.tsx` (modified, +66/-16); `frontend/src/pages/TranscriptionPage.tsx` (modified, +85/-30); `frontend/src/styles/app-shell.css` (modified, +33/-0); `frontend/src/styles/transcription-screen.css` (modified, +182/-0).
- **대표 변경 위치:** `backend/src/api/routes.py` — `@@ -12,7 +12,7 @@`; `backend/src/services/renamer.py` — `@@ -1,6 +1,8 @@`; `backend/src/services/settings.py` — `@@ -5,7 +5,7 @@`; `backend/src/services/transcription_runner.py` — `@@ -2,7 +2,7 @@`; `backend/src/sidecar_main.py` — `@@ -21,6 +21,11 @@`; `backend/tests/test_package_d_ux_integrity.py` — `@@ -0,0 +1,292 @@`; `frontend/src-tauri/Cargo.lock` — `@@ -3328,6 +3328,7 @@ dependencies = [`.
- **관련 참조(제목/본문 등장 번호, 실제 종속성은 링크에서 검증):** #29, #30, #31, #32, #33, #34.
- **기존 PR의 테스트/검증 표기:** ## 검증 상태 / Package D + D-R1 + D-R2는 source/tests 기준 **COMPLETE — REMOTE VERIFIED**입니다..
- **장애 대응 시작점:** 파일 잘못 이름변경/선택/상태 꼬임 시 renamer, settings, Tauri lib, UI API 참조.
- **계보 주의:** PR 자체는 미병합 상태로 종료됐지만 head 커밋은 현 Integration 계보에 포함; 현재 동작 동일성은 최신 파일 및 테스트 재확인 필요.

## [PR #71](https://github.com/bongbong90/Sorigul/pull/71) · E: Prebuild gate/authority

- **원본:** Package E: close pre-build release validation contracts; CLOSED / GitHub 미병합; PR HEAD `e5a523e7e3e5b19ab73d272bccfd59b6eeabec42`; 원래 base `review/remediation-d-frontend-filesystem-ux`; 현재 Integration 조상 커밋(추가 병합 불필요).
- **문제·변경 목적:** 배포 의존성 고정·Source of Truth 문서 라우팅 및 release-only 설정과 선행 검증 강화.
- **변경 파일 14개 (원본 diff 실재 경로):** `backend/requirements.txt` (modified, +10/-10); `backend/src/sidecar_main.py` (modified, +97/-18); `backend/tests/test_release_packaging_contract.py` (modified, +124/-4); `backend/tests/test_sidecar_cuda_contract.py` (modified, +1/-0); `colab/requirements.txt` (modified, +4/-4); `docs/README.md` (added, +10/-0); `docs/project/CURRENT_SOURCE_OF_TRUTH.md` (added, +101/-0); `docs/release/CURRENT_RELEASE_STATUS.md` (added, +69/-0); `frontend/src-tauri/tauri.conf.json` (modified, +0/-3); `frontend/src-tauri/tauri.release.conf.json` (added, +13/-0); `scripts/build_backend_sidecar.ps1` (modified, +7/-0); `scripts/build_windows_installer.ps1` (modified, +5/-5); `scripts/run_core_workflow_regression.ps1` (modified, +44/-16); `tests/test_release_readiness_contracts.py` (added, +178/-0).
- **대표 변경 위치:** `backend/requirements.txt` — `@@ -1,10 +1,10 @@`; `backend/src/sidecar_main.py` — `@@ -14,8 +14,11 @@`; `backend/tests/test_release_packaging_contract.py` — `@@ -1,3 +1,4 @@`; `backend/tests/test_sidecar_cuda_contract.py` — `@@ -173,6 +173,7 @@ def test_packaged_self_test_uses_bounded_watchdog_and_complete_fresh_log():`; `colab/requirements.txt` — `@@ -1,5 +1,5 @@`; `docs/README.md` — `@@ -0,0 +1,10 @@`; `docs/project/CURRENT_SOURCE_OF_TRUTH.md` — `@@ -0,0 +1,101 @@`.
- **관련 참조(제목/본문 등장 번호, 실제 종속성은 링크에서 검증):** #37, #38, #39, #40, #41, #44.
- **기존 PR의 테스트/검증 표기:** - packaged self-test app-data isolation / - readiness contract tests / - #37 packaged self-test user app-data isolation.
- **장애 대응 시작점:** 릴리스 선행검증·패키지 경로 오류 시 release conf, scripts, canonical 문서 계보 확인.
- **계보 주의:** PR 자체는 미병합 상태로 종료됐지만 head 커밋은 현 Integration 계보에 포함; 현재 동작 동일성은 최신 파일 및 테스트 재확인 필요.

## [PR #73](https://github.com/bongbong90/Sorigul/pull/73) · Design foundation

- **원본:** Design system foundation; CLOSED / GitHub 미병합; PR HEAD `1ad6ffb54eabb9c689bab63554bd8bbae5a66546`; 원래 base `chore/frontend-foundation`; 현재 Integration 조상 커밋(추가 병합 불필요).
- **문제·변경 목적:** 디자인 시스템 토큰·공통 UI 컴포넌트 및 앱 화면 골격 수립.
- **변경 파일 16개 (원본 diff 실재 경로):** `README.md` (modified, +2/-1); `docs/design/DESIGN_SYSTEM_FOUNDATION.md` (added, +92/-0); `docs/design/design.md` (modified, +45/-1); `docs/design/icon_system.md` (modified, +21/-4); `frontend/README.md` (modified, +14/-25); `frontend/src/App.tsx` (modified, +71/-3); `frontend/src/components/ui/Badge.tsx` (added, +23/-0); `frontend/src/components/ui/Button.tsx` (added, +18/-0); `frontend/src/components/ui/Card.tsx` (added, +5/-0); `frontend/src/components/ui/Input.tsx` (added, +33/-0); `frontend/src/components/ui/Progress.tsx` (added, +23/-0); `frontend/src/main.tsx` (modified, +3/-0); `frontend/src/styles/base.css` (modified, +2/-1); `frontend/src/styles/components.css` (added, +231/-0); `frontend/src/styles/tokens.css` (added, +67/-0); `frontend/src/styles/typography.css` (added, +83/-0).
- **대표 변경 위치:** `README.md` — `@@ -27,7 +27,8 @@ docs/design/`; `docs/design/DESIGN_SYSTEM_FOUNDATION.md` — `@@ -0,0 +1,92 @@`; `docs/design/design.md` — `@@ -21,4 +21,48 @@`; `docs/design/icon_system.md` — `@@ -2,15 +2,32 @@`; `frontend/README.md` — `@@ -1,32 +1,21 @@`; `frontend/src/App.tsx` — `@@ -1,8 +1,76 @@`; `frontend/src/components/ui/Badge.tsx` — `@@ -0,0 +1,23 @@`.
- **관련 참조(제목/본문 등장 번호, 실제 종속성은 링크에서 검증):** PR 본문에 명시적 번호 근거 없음.
- **기존 PR의 테스트/검증 표기:** 검증 수치의 명시적 근거를 이 PR 본문에서 확보하지 못함(미확인).
- **장애 대응 시작점:** 색상/버튼/카드 일관성 문제 시 tokens/UI components 및 디자인 문서 참조.
- **계보 주의:** PR 자체는 미병합 상태로 종료됐지만 head 커밋은 현 Integration 계보에 포함; 현재 동작 동일성은 최신 파일 및 테스트 재확인 필요.

## [PR #74](https://github.com/bongbong90/Sorigul/pull/74) · App shell

- **원본:** App shell implementation; CLOSED / GitHub 미병합; PR HEAD `5d66771b276244ebea7d5a8cf3b481d0ae619389`; 원래 base `feature/design-system-foundation`; 현재 Integration 조상 커밋(추가 병합 불필요).
- **문제·변경 목적:** 4화면 내비게이션 셸·아이콘·스크롤 구조 도입.
- **변경 파일 12개 (원본 diff 실재 경로):** `.gitignore` (modified, +1/-0); `README.md` (modified, +3/-2); `docs/design/APP_SHELL_IMPLEMENTATION.md` (added, +77/-0); `docs/design/icon_system.md` (modified, +11/-7); `frontend/README.md` (modified, +2/-1); `frontend/package-lock.json` (modified, +10/-0); `frontend/package.json` (modified, +1/-0); `frontend/src/App.tsx` (modified, +2/-73); `frontend/src/components/icons/AppIcons.tsx` (added, +63/-0); `frontend/src/components/layout/AppShell.tsx` (added, +83/-0); `frontend/src/main.tsx` (modified, +1/-0); `frontend/src/styles/app-shell.css` (added, +125/-0).
- **대표 변경 위치:** `.gitignore` — `@@ -15,6 +15,7 @@ build/`; `README.md` — `@@ -11,7 +11,7 @@ Greenfield 프로젝트이며`; `docs/design/APP_SHELL_IMPLEMENTATION.md` — `@@ -0,0 +1,77 @@`; `docs/design/icon_system.md` — `@@ -1,33 +1,37 @@`; `frontend/README.md` — `@@ -3,7 +3,8 @@`; `frontend/package-lock.json` — `@@ -8,6 +8,7 @@`; `frontend/package.json` — `@@ -11,6 +11,7 @@`.
- **관련 참조(제목/본문 등장 번호, 실제 종속성은 링크에서 검증):** PR 본문에 명시적 번호 근거 없음.
- **기존 PR의 테스트/검증 표기:** 검증 수치의 명시적 근거를 이 PR 본문에서 확보하지 못함(미확인).
- **장애 대응 시작점:** 사이드바/헤더/스크롤 문제 시 AppShell, app-shell.css 와 후속 #193/#194 변경 비교.
- **계보 주의:** PR 자체는 미병합 상태로 종료됐지만 head 커밋은 현 Integration 계보에 포함; 현재 동작 동일성은 최신 파일 및 테스트 재확인 필요.

## [PR #75](https://github.com/bongbong90/Sorigul/pull/75) · Transcription screen static

- **원본:** Transcription screen static UI; CLOSED / GitHub 미병합; PR HEAD `f37916df86e20a60287a133cc4802653b69434b6`; 원래 base `feature/app-shell`; 현재 Integration 조상 커밋(추가 병합 불필요).
- **문제·변경 목적:** 파일 목록·현재 작업·폴더·작업버튼 등 전사 화면 컴포넌트 최초 구현.
- **변경 파일 11개 (원본 diff 실재 경로):** `README.md` (modified, +2/-1); `docs/design/TRANSCRIPTION_SCREEN_IMPLEMENTATION.md` (added, +86/-0); `frontend/README.md` (modified, +2/-1); `frontend/src/App.tsx` (modified, +6/-1); `frontend/src/components/transcription/CurrentTaskSection.tsx` (added, +36/-0); `frontend/src/components/transcription/FolderSection.tsx` (added, +20/-0); `frontend/src/components/transcription/QueueTable.tsx` (added, +93/-0); `frontend/src/components/transcription/TranscriptionActions.tsx` (added, +24/-0); `frontend/src/main.tsx` (modified, +1/-0); `frontend/src/pages/TranscriptionPage.tsx` (added, +15/-0); `frontend/src/styles/transcription-screen.css` (added, +213/-0).
- **대표 변경 위치:** `README.md` — `@@ -11,7 +11,7 @@ Greenfield 프로젝트이며`; `docs/design/TRANSCRIPTION_SCREEN_IMPLEMENTATION.md` — `@@ -0,0 +1,86 @@`; `frontend/README.md` — `@@ -4,7 +4,8 @@ React + TypeScript + Vite 기반 개발 환경.`; `frontend/src/App.tsx` — `@@ -1,7 +1,12 @@`; `frontend/src/components/transcription/CurrentTaskSection.tsx` — `@@ -0,0 +1,36 @@`; `frontend/src/components/transcription/FolderSection.tsx` — `@@ -0,0 +1,20 @@`; `frontend/src/components/transcription/QueueTable.tsx` — `@@ -0,0 +1,93 @@`.
- **관련 참조(제목/본문 등장 번호, 실제 종속성은 링크에서 검증):** PR 본문에 명시적 번호 근거 없음.
- **기존 PR의 테스트/검증 표기:** 검증 수치의 명시적 근거를 이 PR 본문에서 확보하지 못함(미확인).
- **장애 대응 시작점:** 전사 화면 레이아웃·파일목록 누락 시 화면 각 컴포넌트와 후속 #194 변경 비교.
- **계보 주의:** PR 자체는 미병합 상태로 종료됐지만 head 커밋은 현 Integration 계보에 포함; 현재 동작 동일성은 최신 파일 및 테스트 재확인 필요.

## [PR #76](https://github.com/bongbong90/Sorigul/pull/76) · Transcription mock interaction

- **원본:** Transcription screen mock interactions; CLOSED / GitHub 미병합; PR HEAD `154e550e6aefd4dfecd5e0140d0ff1f69bf17f5c`; 원래 base `feature/transcription-screen-static-ui`; 현재 Integration 조상 커밋(추가 병합 불필요).
- **문제·변경 목적:** 전사 UI mock 상호작용과 상태별 동작·테이블·제어버튼 변경.
- **변경 파일 7개 (원본 diff 실재 경로):** `docs/design/TRANSCRIPTION_MOCK_INTERACTION.md` (added, +108/-0); `frontend/src/components/transcription/CurrentTaskSection.tsx` (modified, +28/-8); `frontend/src/components/transcription/FolderSection.tsx` (modified, +10/-3); `frontend/src/components/transcription/QueueTable.tsx` (modified, +77/-58); `frontend/src/components/transcription/TranscriptionActions.tsx` (modified, +26/-6); `frontend/src/pages/TranscriptionPage.tsx` (modified, +173/-5); `frontend/src/styles/transcription-screen.css` (modified, +5/-0).
- **대표 변경 위치:** `docs/design/TRANSCRIPTION_MOCK_INTERACTION.md` — `@@ -0,0 +1,108 @@`; `frontend/src/components/transcription/CurrentTaskSection.tsx` — `@@ -2,35 +2,55 @@ import { Badge } from '../ui/Badge'`; `frontend/src/components/transcription/FolderSection.tsx` — `@@ -2,7 +2,12 @@ import { FolderOpen } from 'lucide-react'`; `frontend/src/components/transcription/QueueTable.tsx` — `@@ -1,43 +1,49 @@`; `frontend/src/components/transcription/TranscriptionActions.tsx` — `@@ -1,23 +1,43 @@`; `frontend/src/pages/TranscriptionPage.tsx` — `@@ -1,15 +1,183 @@`; `frontend/src/styles/transcription-screen.css` — `@@ -187,6 +187,11 @@`.
- **관련 참조(제목/본문 등장 번호, 실제 종속성은 링크에서 검증):** PR 본문에 명시적 번호 근거 없음.
- **기존 PR의 테스트/검증 표기:** 검증 수치의 명시적 근거를 이 PR 본문에서 확보하지 못함(미확인).
- **장애 대응 시작점:** 실제 API 동작을 증명하는 PR이 아니라 초기 상호작용 기록; 최신 Job UX와 비교 시 주의.
- **계보 주의:** PR 자체는 미병합 상태로 종료됐지만 head 커밋은 현 Integration 계보에 포함; 현재 동작 동일성은 최신 파일 및 테스트 재확인 필요.

## [PR #77](https://github.com/bongbong90/Sorigul/pull/77) · Legacy parity inventory

- **원본:** Legacy feature parity audit; CLOSED / GitHub 미병합; PR HEAD `b7cc7cbeb78a8f96b231687f5615bfa0c0d94350`; 원래 base `feature/transcription-screen-mock-interaction`; 현재 Integration 조상 커밋(추가 병합 불필요).
- **문제·변경 목적:** Legacy 기능·결손 및 이전 기준 감사 문서 기록.
- **변경 파일 1개 (원본 diff 실재 경로):** `docs/project/LEGACY_FEATURE_PARITY_AUDIT.md` (added, +308/-0).
- **대표 변경 위치:** `docs/project/LEGACY_FEATURE_PARITY_AUDIT.md` — `@@ -0,0 +1,308 @@`.
- **관련 참조(제목/본문 등장 번호, 실제 종속성은 링크에서 검증):** PR 본문에 명시적 번호 근거 없음.
- **기존 PR의 테스트/검증 표기:** 검증 수치의 명시적 근거를 이 PR 본문에서 확보하지 못함(미확인).
- **장애 대응 시작점:** 과거 동작 근거 추적에 유용하지만 CURRENT_PRODUCT_CONTRACT 최신 승인보다 우선하지 않음.
- **계보 주의:** PR 자체는 미병합 상태로 종료됐지만 head 커밋은 현 Integration 계보에 포함; 현재 동작 동일성은 최신 파일 및 테스트 재확인 필요.
