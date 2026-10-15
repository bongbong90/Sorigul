# Historical PR review · E — Current-contract behavior restores and Windows security

> PR 원본 변경 파일·patch 기반. 개별 HEAD는 Integration 조상. 관련 동작은 최신 제품 계약/후속 구현 우선.

## [PR #134](https://github.com/bongbong90/Sorigul/pull/134) · Week/lesson allocation parity

- **원본:** fix: restore Legacy week and lesson allocation; CLOSED / 직접 GitHub 병합 아님; HEAD `f61686e69c47ab04a6cc8a708df40738ccb12369`; base `audit/full-source-contract-regression`.
- **문제와 해결 범위:** Legacy 주차·강의 순번 배정과 파일 정규화 충돌 처리의 정확성을 복원.
- **실제 변경 파일 2개:** `backend/src/services/normalizer.py` (modified, +50/-11); `backend/tests/test_filename_normalizer_parity.py` (added, +247/-0).
- **patch 수정 진입점:** `backend/src/services/normalizer.py` — `@@ -1,4 +1,6 @@`; `backend/tests/test_filename_normalizer_parity.py` — `@@ -0,0 +1,247 @@`.
- **원문 관련 번호:** #124, #48.
- **당시 검증 내용(원문 발췌):** Changed files: 'normalizer.py' and the new 'backend/tests/test_filename_normalizer_parity.py'. No routes, frontend, or Rust changes. / | 'cargo test --locked --offline' | 54 passed |.
- **장애 분석 가이드:** #180 수동 주차·#192 과목명 축약까지 전후 계약 비교. 자동 번호 덮어쓰기 주의.
- **후속 유의:** 현재 Integration 조상인 것은 입증됨. 기능이 동일하게 유지됐다는 의미는 아니므로 최신 HEAD의 대상 파일/테스트 재확인 필수.

## [PR #135](https://github.com/bongbong90/Sorigul/pull/135) · Trusted Windows system paths

- **원본:** fix: resolve Windows system utilities by trusted paths; CLOSED / 직접 GitHub 병합 아님; HEAD `05efaae352ac3d303d3cdd46a7e666782f93a9e9`; base `fix/filename-week-lesson-parity`.
- **문제와 해결 범위:** Windows system32 유틸리티의 신뢰 가능한 실행 경로 검증으로 경로 하이재킹 위험 완화.
- **실제 변경 파일 13개:** `backend/src/engines/local_whisper.py` (modified, +8/-1); `backend/src/services/drive.py` (modified, +4/-3); `backend/src/services/windows_system.py` (added, +55/-0); `backend/tests/test_package_c_security.py` (modified, +30/-10); `backend/tests/test_windows_system_utilities.py` (added, +219/-0); `docs/runtime/TAURI_RUNTIME_SIDECAR_OS_INTEGRATION.md` (modified, +3/-3); `frontend/src-tauri/Cargo.toml` (modified, +1/-0); `frontend/src-tauri/src/lib.rs` (modified, +54/-16); `frontend/src-tauri/src/shutdown.rs` (modified, +36/-5); `frontend/src-tauri/src/sidecar.rs` (modified, +46/-4); `frontend/src-tauri/src/windows_system.rs` (added, +162/-0); `tests/test_notification_folder_open_contracts.py` (modified, +12/-2); `tests/test_trusted_windows_utilities_contracts.py` (added, +74/-0).
- **patch 수정 진입점:** `backend/src/engines/local_whisper.py` — `@@ -19,6 +19,7 @@`; `backend/src/services/drive.py` — `@@ -27,6 +27,7 @@`; `backend/src/services/windows_system.py` — `@@ -0,0 +1,55 @@`; `backend/tests/test_package_c_security.py` — `@@ -12,9 +12,24 @@`; `backend/tests/test_windows_system_utilities.py` — `@@ -0,0 +1,219 @@`; `docs/runtime/TAURI_RUNTIME_SIDECAR_OS_INTEGRATION.md` — `@@ -64,7 +64,7 @@ The frontend's existing offline/reconnect UX (TranscriptionPage/SettingsPage`; `frontend/src-tauri/Cargo.toml` — `@@ -27,6 +27,7 @@ windows-sys = { version = "0.60", features = [`; `frontend/src-tauri/src/lib.rs` — `@@ -1,6 +1,8 @@`.
- **원문 관련 번호:** #122, #58.
- **당시 검증 내용(원문 발췌):** - new root contract 'tests/test_trusted_windows_utilities_contracts.py' fails on any production literal 'Command::new' (other than the non-Windows 'xdg-open') or bare '*.exe' argv / - Git Bash PATH-shadow case ('which whoami.exe' → '/usr/bin/whoami.exe'): the two #122 tests are 2 failed at 'f61686e' and 2 passed at this HEAD / - process cleanup: backend reap tests and Tauri owned-process / Job Object cleanup tests pass through the absolute taskkill.
- **장애 분석 가이드:** taskkill/기타 시스템 도구가 PATH 문자열 대신 trusted path를 쓰는지 확인.
- **후속 유의:** 현재 Integration 조상인 것은 입증됨. 기능이 동일하게 유지됐다는 의미는 아니므로 최신 HEAD의 대상 파일/테스트 재확인 필수.

## [PR #137](https://github.com/bongbong90/Sorigul/pull/137) · Loopback Host hardening

- **원본:** fix: reject untrusted loopback Host headers; CLOSED / 직접 GitHub 병합 아님; HEAD `24a4ecd04aa286c24c2e5b304a0a6ef3e85958d6`; base `fix/trusted-windows-system-utilities`.
- **문제와 해결 범위:** Backend loopback 접속에서 신뢰할 수 없는 Host 헤더·주소 사용 거부.
- **실제 변경 파일 5개:** `backend/src/main.py` (modified, +11/-0); `backend/tests/test_folder_revision.py` (modified, +1/-1); `backend/tests/test_loopback_host_security.py` (added, +155/-0); `backend/tests/test_notification_folder_intent.py` (modified, +1/-1); `tests/test_loopback_host_contracts.py` (added, +35/-0).
- **patch 수정 진입점:** `backend/src/main.py` — `@@ -1,5 +1,6 @@`; `backend/tests/test_folder_revision.py` — `@@ -169,7 +169,7 @@ def _client(tmp_path, monkeypatch):`; `backend/tests/test_loopback_host_security.py` — `@@ -0,0 +1,155 @@`; `backend/tests/test_notification_folder_intent.py` — `@@ -21,7 +21,7 @@ def _client(tmp_path, monkeypatch):`; `tests/test_loopback_host_contracts.py` — `@@ -0,0 +1,35 @@`.
- **원문 관련 번호:** #125, #53.
- **당시 검증 내용(원문 발췌):** Test-only change: 'test_folder_revision.py' and 'test_notification_folder_intent.py' relied on TestClient's default 'testserver' Host. They now use the real 'http://127.0.0.1:8000' / | Frontend lint / typecheck / build | PASS / PASS / PASS | / | cargo fmt --check / check / clippy -D warnings / test | PASS / PASS / PASS / 62 passed |.
- **장애 분석 가이드:** localhost API 악용/외부 오접속시 Host validation/보안 테스트 확인.
- **후속 유의:** 현재 Integration 조상인 것은 입증됨. 기능이 동일하게 유지됐다는 의미는 아니므로 최신 HEAD의 대상 파일/테스트 재확인 필수.

## [PR #139](https://github.com/bongbong90/Sorigul/pull/139) · One global run

- **원본:** fix: enforce one global transcription run; CLOSED / 직접 GitHub 병합 아님; HEAD `07a642b70193b79aea10e30b037f68b68611bfc2`; base `fix/loopback-host-validation`.
- **문제와 해결 범위:** Local/Colab 및 여러 화면/폴더 사이에서 동시에 두 Job이 실행되는 상황 차단.
- **실제 변경 파일 12개:** `backend/src/api/routes.py` (modified, +40/-0); `backend/src/services/transcription_runner.py` (modified, +37/-3); `backend/tests/test_global_single_run.py` (added, +373/-0); `frontend/src/api/client.ts` (modified, +3/-0); `frontend/src/components/transcription/ActiveRunBanner.tsx` (added, +47/-0); `frontend/src/components/transcription/CurrentTaskSection.tsx` (modified, +2/-38); `frontend/src/components/transcription/QueueTable.tsx` (modified, +4/-0); `frontend/src/components/transcription/TranscriptionActions.tsx` (modified, +3/-1); `frontend/src/components/transcription/currentTaskStatus.ts` (added, +38/-0); `frontend/src/pages/TranscriptionPage.tsx` (modified, +95/-16); `frontend/src/styles/feature-pages.css` (modified, +54/-0); `tests/test_global_single_run_contracts.py` (added, +106/-0).
- **patch 수정 진입점:** `backend/src/api/routes.py` — `@@ -1,3 +1,4 @@`; `backend/src/services/transcription_runner.py` — `@@ -625,9 +625,21 @@ def _update_counts(job: JobModel):`; `backend/tests/test_global_single_run.py` — `@@ -0,0 +1,373 @@`; `frontend/src/api/client.ts` — `@@ -318,6 +318,9 @@ export const api = {`; `frontend/src/components/transcription/ActiveRunBanner.tsx` — `@@ -0,0 +1,47 @@`; `frontend/src/components/transcription/CurrentTaskSection.tsx` — `@@ -1,21 +1,9 @@`; `frontend/src/components/transcription/QueueTable.tsx` — `@@ -33,6 +33,7 @@ interface QueueTableProps {`; `frontend/src/components/transcription/TranscriptionActions.tsx` — `@@ -8,6 +8,7 @@ interface TranscriptionActionsProps {`.
- **원문 관련 번호:** #126, #125, #122, #138, #63, #56.
- **당시 검증 내용(원문 발췌):** - Root contracts: 53 passed (includes new 'tests/test_global_single_run_contracts.py'). / - Rust: fmt/check/clippy OK. Test suite: 62/62 on rerun. One pre-existing intermittent failure is unrelated (no Rust changes) and filed as #138..
- **장애 분석 가이드:** 중복 Job/동시 실행·복귀 상태 문제가 생기면 Job API/global-active-run 경계 검토.
- **후속 유의:** 현재 Integration 조상인 것은 입증됨. 기능이 동일하게 유지됐다는 의미는 아니므로 최신 HEAD의 대상 파일/테스트 재확인 필수.

## [PR #140](https://github.com/bongbong90/Sorigul/pull/140) · Active-close guard

- **원본:** fix: protect active work from window close; CLOSED / 직접 GitHub 병합 아님; HEAD `0c3266dd5de21469878ffbf37119c8dcebe33798`; base `fix/global-single-run-enforcement`.
- **문제와 해결 범위:** 전사 또는 Drive 진행 중 X 종료가 실행 중 Job을 종료시키지 않도록 보호.
- **실제 변경 파일 7개:** `backend/src/api/routes.py` (modified, +41/-0); `backend/src/services/drive.py` (modified, +15/-0); `backend/tests/test_close_guard.py` (added, +231/-0); `frontend/src-tauri/src/close_guard.rs` (added, +422/-0); `frontend/src-tauri/src/lib.rs` (modified, +57/-8); `frontend/src/pages/SettingsPage.tsx` (modified, +2/-2); `tests/test_active_run_close_contracts.py` (added, +102/-0).
- **patch 수정 진입점:** `backend/src/api/routes.py` — `@@ -234,6 +234,47 @@ def open_job_folder_intent(job_id: str):`; `backend/src/services/drive.py` — `@@ -753,6 +753,16 @@ def upload(self, job_id: str, file_id: str) -> DriveFileState:`; `backend/tests/test_close_guard.py` — `@@ -0,0 +1,231 @@`; `frontend/src-tauri/src/close_guard.rs` — `@@ -0,0 +1,422 @@`; `frontend/src-tauri/src/lib.rs` — `@@ -1,3 +1,4 @@`; `frontend/src/pages/SettingsPage.tsx` — `@@ -189,8 +189,8 @@ export function SettingsPage() {`; `tests/test_active_run_close_contracts.py` — `@@ -0,0 +1,102 @@`.
- **원문 관련 번호:** #128, #126, #138, #56, #63, #48.
- **당시 검증 내용(원문 발췌):** - Rust 'close_guard' tests: 10 passed. Covers tray → hide, exit coalescing, active/idle/error outcomes, stale-idle superseded, parser valid/malformed/inconsistent, fixed URL, a liv / - Root contracts: 59 passed (new 'tests/test_active_run_close_contracts.py'). / - Rust: fmt, check and clippy '-D warnings' OK. 'cargo test': 72/72 on four full runs. #138 was not observed..
- **장애 분석 가이드:** #195의 유휴 Exit 기본값과 active protected hide 구분; #128/#174 Native 가드 연계.
- **후속 유의:** 현재 Integration 조상인 것은 입증됨. 기능이 동일하게 유지됐다는 의미는 아니므로 최신 HEAD의 대상 파일/테스트 재확인 필수.

## [PR #141](https://github.com/bongbong90/Sorigul/pull/141) · Colab convenience

- **원본:** feat: restore Colab open convenience; CLOSED / 직접 GitHub 병합 아님; HEAD `ef48a5a9a7dfe3663bf5c4af10489b5c1bc6c251`; base `fix/active-run-close-protection`.
- **문제와 해결 범위:** Colab 연결 준비 및 노트북 열기 편의 동작 복원.
- **실제 변경 파일 5개:** `colab/README.md` (modified, +5/-5); `frontend/src/components/transcription/EngineSection.tsx` (modified, +24/-0); `frontend/src/lib/colabSetup.ts` (added, +9/-0); `frontend/src/styles/transcription-screen.css` (modified, +33/-0); `tests/test_colab_open_convenience_contracts.py` (added, +110/-0).
- **patch 수정 진입점:** `colab/README.md` — `@@ -4,18 +4,18 @@ Google Colab GPU 런타임을 사용하여 Sorigul 전사를 수행하기 위한`; `frontend/src/components/transcription/EngineSection.tsx` — `@@ -3,6 +3,8 @@ import { api, getUserMessage, isRequestAbort, isRequestTimeout } from '../../api`; `frontend/src/lib/colabSetup.ts` — `@@ -0,0 +1,9 @@`; `frontend/src/styles/transcription-screen.css` — `@@ -100,6 +100,38 @@`; `tests/test_colab_open_convenience_contracts.py` — `@@ -0,0 +1,110 @@`.
- **원문 관련 번호:** #130, #138, #48, #60, #56.
- **당시 검증 내용(원문 발췌):** - Rust test: 72 passed.
- **장애 분석 가이드:** 외부 URL, 앱 설정 이동, Colab 수동 연결 UX 후속 #194와 비교.
- **후속 유의:** 현재 Integration 조상인 것은 입증됨. 기능이 동일하게 유지됐다는 의미는 아니므로 최신 HEAD의 대상 파일/테스트 재확인 필수.

## [PR #142](https://github.com/bongbong90/Sorigul/pull/142) · Honest tray tooltip

- **원본:** feat: restore honest tray progress tooltip; CLOSED / 직접 GitHub 병합 아님; HEAD `c508e8a6968068aa45dc6343222552cae567acfd`; base `fix/colab-open-convenience`.
- **문제와 해결 범위:** 트레이 tooltip 상태에서 실제 전사 파일·진행률만 사용하도록 개선.
- **실제 변경 파일 7개:** `frontend/src-tauri/src/lib.rs` (modified, +31/-1); `frontend/src-tauri/src/tray_tooltip.rs` (added, +203/-0); `frontend/src/hooks/useTrayProgress.ts` (added, +76/-0); `frontend/src/lib/native.ts` (modified, +20/-0); `frontend/src/pages/TranscriptionPage.tsx` (modified, +2/-0); `tests/test_notification_folder_open_contracts.py` (modified, +2/-1); `tests/test_tray_progress_contracts.py` (added, +70/-0).
- **patch 수정 진입점:** `frontend/src-tauri/src/lib.rs` — `@@ -2,6 +2,7 @@ mod close_guard;`; `frontend/src-tauri/src/tray_tooltip.rs` — `@@ -0,0 +1,203 @@`; `frontend/src/hooks/useTrayProgress.ts` — `@@ -0,0 +1,76 @@`; `frontend/src/lib/native.ts` — `@@ -13,6 +13,26 @@ export interface SidecarStatus {`; `frontend/src/pages/TranscriptionPage.tsx` — `@@ -14,6 +14,7 @@ import {`; `tests/test_notification_folder_open_contracts.py` — `@@ -152,7 +152,8 @@ def test_toast_window_is_declared_once_hidden_non_activating_and_off_taskbar():`; `tests/test_tray_progress_contracts.py` — `@@ -0,0 +1,70 @@`.
- **원문 관련 번호:** #131, #56, #63.
- **당시 검증 내용(원문 발췌):** 원문 테스트 수치 없음(미확인).
- **장애 분석 가이드:** ETA/진행률 fabrication·백그라운드 상태 멈춤 시 tray 상태 observer #173과 연결.
- **후속 유의:** 현재 Integration 조상인 것은 입증됨. 기능이 동일하게 유지됐다는 의미는 아니므로 최신 HEAD의 대상 파일/테스트 재확인 필수.

## [PR #143](https://github.com/bongbong90/Sorigul/pull/143) · Folders sorting

- **원본:** feat: restore Folders column sorting; CLOSED / 직접 GitHub 병합 아님; HEAD `ec06007e0bbbfbbe2d5a27da311186b0758d6359`; base `fix/honest-tray-progress-tooltip`.
- **문제와 해결 범위:** Folders 파일명/유형 정렬 조작과 기존 사용자 동작 복원.
- **실제 변경 파일 4개:** `frontend/src/lib/folderSort.ts` (added, +40/-0); `frontend/src/pages/FoldersPage.tsx` (modified, +25/-4); `frontend/src/styles/feature-pages.css` (modified, +18/-0); `tests/test_folders_sort_contracts.py` (added, +109/-0).
- **patch 수정 진입점:** `frontend/src/lib/folderSort.ts` — `@@ -0,0 +1,40 @@`; `frontend/src/pages/FoldersPage.tsx` — `@@ -1,7 +1,8 @@`; `frontend/src/styles/feature-pages.css` — `@@ -77,6 +77,7 @@`; `tests/test_folders_sort_contracts.py` — `@@ -0,0 +1,109 @@`.
- **원문 관련 번호:** #132, #111, #138, #56, #63.
- **당시 검증 내용(원문 발췌):** - frontend lint: PASS / - frontend typecheck: PASS / - frontend build: PASS (1851 modules).
- **장애 분석 가이드:** 정렬 순서·타입별 동작은 계약상 허용된 컬럼만 확인.
- **후속 유의:** 현재 Integration 조상인 것은 입증됨. 기능이 동일하게 유지됐다는 의미는 아니므로 최신 HEAD의 대상 파일/테스트 재확인 필수.

## [PR #144](https://github.com/bongbong90/Sorigul/pull/144) · TXT display encoding

- **원본:** fix: restore TXT display encoding fallback; CLOSED / 직접 GitHub 병합 아님; HEAD `665fe8f73b545347bd24d92add85d66fbf242f92`; base `fix/folders-column-sorting`.
- **문제와 해결 범위:** 결과 TXT 표시만 제한된 문자 인코딩 fallback 허용, 저장 포맷은 유지.
- **실제 변경 파일 2개:** `backend/src/services/results.py` (modified, +17/-8); `backend/tests/test_txt_display_encoding_fallback.py` (added, +260/-0).
- **patch 수정 진입점:** `backend/src/services/results.py` — `@@ -13,6 +13,19 @@`; `backend/tests/test_txt_display_encoding_fallback.py` — `@@ -0,0 +1,260 @@`.
- **원문 관련 번호:** #133, #138, #56, #63.
- **당시 검증 내용(원문 발췌):** - dedicated encoding fallback tests: 13 passed / - existing ResultsService/live-folder tests: 46 passed, 1 skipped / - frontend lint/typecheck/build: PASS.
- **장애 분석 가이드:** 한글 깨짐시 UTF-8 BOM/cp949/euc-kr 읽기 순서와 원본 파일 무변경 검사.
- **후속 유의:** 현재 Integration 조상인 것은 입증됨. 기능이 동일하게 유지됐다는 의미는 아니므로 최신 HEAD의 대상 파일/테스트 재확인 필수.

## [PR #145](https://github.com/bongbong90/Sorigul/pull/145) · Trusted taskkill in build

- **원본:** fix: resolve build taskkill by trusted path; CLOSED / 직접 GitHub 병합 아님; HEAD `683339687462043d51ebc54e455eedcf3f546955`; base `fix/txt-display-encoding-fallback`.
- **문제와 해결 범위:** 프로세스 종료 도구 호출 경로를 신뢰된 시스템 유틸리티로 제한.
- **실제 변경 파일 4개:** `backend/tests/test_sidecar_cuda_contract.py` (modified, +1/-1); `scripts/build_backend_sidecar.ps1` (modified, +18/-1); `scripts/build_local_whisper_runtime.ps1` (modified, +18/-1); `tests/test_trusted_windows_utilities_contracts.py` (modified, +64/-1).
- **patch 수정 진입점:** `backend/tests/test_sidecar_cuda_contract.py` — `@@ -144,7 +144,7 @@ def test_core_self_test_excludes_local_runtime_and_local_self_test_is_bounded():`; `scripts/build_backend_sidecar.ps1` — `@@ -15,6 +15,22 @@ $SelfTestTimeoutSeconds = 300`; `scripts/build_local_whisper_runtime.ps1` — `@@ -15,6 +15,22 @@ $ProtocolVersion = 1`; `tests/test_trusted_windows_utilities_contracts.py` — `@@ -1,6 +1,9 @@`.
- **원문 관련 번호:** #113, #136, #138.
- **당시 검증 내용(원문 발췌):** build/self-test scripts before the fresh #113 artifact gate. / - Contracts: 'tests/test_trusted_windows_utilities_contracts.py' (extended), 'backend/tests/test_sidecar_cuda_contract.py' (one assertion that pinned the old bare call now pins the / - self-test timeout behavior (300 s).
- **장애 분석 가이드:** Windows 빌드 시 taskkill 실패·경로보안 관련 #135/JobObject 검증을 대조.
- **후속 유의:** 현재 Integration 조상인 것은 입증됨. 기능이 동일하게 유지됐다는 의미는 아니므로 최신 HEAD의 대상 파일/테스트 재확인 필수.
