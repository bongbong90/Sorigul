# Historical PR review · C — Core workflow refinements, Colab/Drive, CUDA provenance

> 원본 PR 제목·본문 및 변경 파일/patch 기준. HEAD가 현 Integration의 조상이어도 **현재 동일 코드**라는 뜻은 아니다. 실제 Drive·CUDA·MP3의 현 상태는 새 gate를 통해 판단.

## [PR #88](https://github.com/bongbong90/Sorigul/pull/88) · Refinement plan

- **원본:** Core workflow refinement plan; CLOSED / GitHub 미병합; HEAD `1399faec2b661acead4e36cb916c9276e9e0e24b`; 원래 base `validation/full-feature-parity-release`.
- **당시 목표:** 기존 전사·Drive·파일명·실행 흐름 개선 작업을 단계별 계약으로 정의.
- **변경 파일 4개:** `docs/migration/CORE_WORKFLOW_REFINEMENT_PLAN.md` (added, +411/-0); `docs/project/FEATURE_PARITY.md` (modified, +2/-0); `docs/project/LEGACY_FEATURE_PARITY_AUDIT.md` (modified, +2/-0); `docs/project/MIGRATION_CONTRACT.md` (modified, +3/-1).
- **구현/검증 diff 앵커:** `docs/migration/CORE_WORKFLOW_REFINEMENT_PLAN.md` — `@@ -0,0 +1,411 @@`; `docs/project/FEATURE_PARITY.md` — `@@ -1,5 +1,7 @@`; `docs/project/LEGACY_FEATURE_PARITY_AUDIT.md` — `@@ -7,6 +7,8 @@`; `docs/project/MIGRATION_CONTRACT.md` — `@@ -1,6 +1,8 @@`.
- **관련 원문 표기 번호:** 명시적 Issue 번호 미확인.
- **원본 PR의 검증 문구:** 구체 실행 결과가 본문에 없음 — 미확인.
- **재발 시 추적:** D11+ 결정은 이후 승인 문서 우선순위에 따라 해석.
- **계보:** 현 Integration에 조상으로 포함; 후속 PR과 최신 계약에 의해 수정되었을 수 있음.

## [PR #89](https://github.com/bongbong90/Sorigul/pull/89) · Phase 1 classifier/normalizer

- **원본:** Core workflow Phase 1: classification and normalization; CLOSED / GitHub 미병합; HEAD `cfeca3a49b9807c99b831c65d08298b766536804`; 원래 base `review/core-workflow-plan`.
- **당시 목표:** 과정·과목 분류와 이름 정규화·검토 흐름을 구현.
- **변경 파일 18개:** `backend/src/api/routes.py` (modified, +126/-8); `backend/src/domain/models.py` (modified, +21/-1); `backend/src/services/classification.py` (added, +49/-0); `backend/src/services/job_manager.py` (modified, +10/-2); `backend/src/services/normalizer.py` (modified, +198/-104); `backend/src/services/renamer.py` (modified, +32/-0); `backend/src/services/settings.py` (modified, +16/-1); `backend/tests/test_classification.py` (added, +154/-0); `backend/tests/test_core.py` (modified, +122/-11); `backend/tests/test_job_api_classification.py` (added, +330/-0); `docs/migration/CORE_WORKFLOW_REFINEMENT_PLAN.md` (modified, +1/-1); `frontend/src/api/client.ts` (modified, +32/-6); `frontend/src/components/transcription/ClassificationSection.tsx` (added, +97/-0); `frontend/src/lib/classification.ts` (added, +64/-0); `frontend/src/lib/preflight.ts` (added, +78/-0); `frontend/src/pages/SettingsPage.tsx` (modified, +1/-0); `frontend/src/pages/TranscriptionPage.tsx` (modified, +494/-40); `frontend/src/styles/feature-pages.css` (modified, +13/-0).
- **구현/검증 diff 앵커:** `backend/src/api/routes.py` — `@@ -1,9 +1,18 @@`; `backend/src/domain/models.py` — `@@ -1,6 +1,6 @@`; `backend/src/services/classification.py` — `@@ -0,0 +1,49 @@`; `backend/src/services/job_manager.py` — `@@ -6,7 +6,7 @@`; `backend/src/services/normalizer.py` — `@@ -1,135 +1,229 @@`; `backend/src/services/renamer.py` — `@@ -2,6 +2,38 @@`; `backend/src/services/settings.py` — `@@ -3,7 +3,7 @@`; `backend/tests/test_classification.py` — `@@ -0,0 +1,154 @@`; `backend/tests/test_core.py` — `@@ -4,9 +4,10 @@`.
- **관련 원문 표기 번호:** 명시적 Issue 번호 미확인.
- **원본 PR의 검증 문구:** 구체 실행 결과가 본문에 없음 — 미확인.
- **재발 시 추적:** 과목 별칭 #192, 이름 보존·충돌과 D12/D16 예외 대조.
- **계보:** 현 Integration에 조상으로 포함; 후속 PR과 최신 계약에 의해 수정되었을 수 있음.

## [PR #90](https://github.com/bongbong90/Sorigul/pull/90) · Phase 2 Drive

- **원본:** Core workflow Phase 2: Google Drive refinement; CLOSED / GitHub 미병합; HEAD `bbc0df2f0361c0ce016d8ce7bd52ecab93017058`; 원래 base `review/core-workflow-phase1`.
- **당시 목표:** 전사 출력물 Drive 폴더·업로드/재시도 관련 흐름 변경.
- **변경 파일 7개:** `backend/src/api/routes.py` (modified, +1/-1); `backend/src/services/drive.py` (modified, +61/-16); `backend/src/services/settings.py` (modified, +2/-0); `backend/tests/test_drive_results_desktop.py` (modified, +156/-15); `frontend/src/api/client.ts` (modified, +1/-0); `frontend/src/pages/SettingsPage.tsx` (modified, +2/-0); `frontend/src/pages/TranscriptionPage.tsx` (modified, +34/-1).
- **구현/검증 diff 앵커:** `backend/src/api/routes.py` — `@@ -52,7 +52,7 @@ def get_job_manager():`; `backend/src/services/drive.py` — `@@ -61,27 +61,69 @@ class DriveClassification:`; `backend/src/services/settings.py` — `@@ -53,6 +53,7 @@ class RuntimeSettings(BaseModel):`; `backend/tests/test_drive_results_desktop.py` — `@@ -96,31 +96,32 @@ def make_done_job(tmp_path, stem="개념완성_민법_8주차_4강"):`; `frontend/src/api/client.ts` — `@@ -142,6 +142,7 @@ export interface RuntimeSettings {`; `frontend/src/pages/SettingsPage.tsx` — `@@ -11,6 +11,7 @@ const defaults: RuntimeSettings = {`; `frontend/src/pages/TranscriptionPage.tsx` — `@@ -574,7 +574,10 @@ export function TranscriptionPage() {`.
- **관련 원문 표기 번호:** 명시적 Issue 번호 미확인.
- **원본 PR의 검증 문구:** 구체 실행 결과가 본문에 없음 — 미확인.
- **재발 시 추적:** 실제 Drive 호출은 가상 테스트와 별도이며 #192/197과 연결 검토.
- **계보:** 현 Integration에 조상으로 포함; 후속 PR과 최신 계약에 의해 수정되었을 수 있음.

## [PR #91](https://github.com/bongbong90/Sorigul/pull/91) · Phase 3A audio

- **원본:** Core workflow Phase 3A: audio metadata and URL normalization; CLOSED / GitHub 미병합; HEAD `89a15decd6f11dd67a2cf5bfa679d55d7852776f`; 원래 base `review/core-workflow-phase2-drive`.
- **당시 목표:** 오디오 길이·메타데이터·Colab URL 정규화 동작 개선.
- **변경 파일 7개:** `backend/requirements.txt` (modified, +1/-0); `backend/src/engines/colab.py` (modified, +67/-43); `backend/src/services/audio_metadata.py` (added, +19/-0); `backend/src/services/colab_url.py` (added, +41/-0); `backend/src/sidecar_main.py` (modified, +6/-0); `backend/tests/test_audio_metadata.py` (added, +43/-0); `backend/tests/test_colab_engine.py` (modified, +165/-0).
- **구현/검증 diff 앵커:** `backend/requirements.txt` — `@@ -6,3 +6,4 @@ pytest-asyncio`; `backend/src/engines/colab.py` — `@@ -49,15 +49,25 @@ def __init__(self):`; `backend/src/services/audio_metadata.py` — `@@ -0,0 +1,19 @@`; `backend/src/services/colab_url.py` — `@@ -0,0 +1,41 @@`; `backend/src/sidecar_main.py` — `@@ -53,6 +53,11 @@ def check_ffmpeg() -> None:`; `backend/tests/test_audio_metadata.py` — `@@ -0,0 +1,43 @@`; `backend/tests/test_colab_engine.py` — `@@ -410,3 +410,168 @@ def test_invalid_response_fails_current_file_and_continues_batch(`.
- **관련 원문 표기 번호:** 명시적 Issue 번호 미확인.
- **원본 PR의 검증 문구:** 구체 실행 결과가 본문에 없음 — 미확인.
- **재발 시 추적:** MP3 메타정보·URL 검증 오류 시 프로브·정규화·연계 테스트 확인.
- **계보:** 현 Integration에 조상으로 포함; 후속 PR과 최신 계약에 의해 수정되었을 수 있음.

## [PR #92](https://github.com/bongbong90/Sorigul/pull/92) · Phase 3B Colab

- **원본:** Core workflow Phase 3B: Colab rendezvous and integration; CLOSED / GitHub 미병합; HEAD `0e61f19242fae173f19ec73f87ad084af4c70dd6`; 원래 base `review/core-workflow-phase3a-runtime`.
- **당시 목표:** Colab 연결·Rendezvous·전사 경로의 사용자 흐름 구현.
- **변경 파일 14개:** `backend/src/api/routes.py` (modified, +26/-1); `backend/src/services/colab_rendezvous.py` (added, +152/-0); `backend/src/services/drive.py` (modified, +37/-0); `backend/src/services/settings.py` (modified, +2/-0); `backend/tests/test_colab_rendezvous.py` (added, +558/-0); `backend/tests/test_core.py` (modified, +34/-0); `backend/tests/test_job_api_classification.py` (modified, +87/-0); `colab/README.md` (added, +20/-0); `colab/requirements.txt` (added, +4/-0); `colab/sorigul_colab_bootstrap.py` (added, +239/-0); `frontend/src/api/client.ts` (modified, +10/-0); `frontend/src/components/transcription/EngineSection.tsx` (added, +227/-0); `frontend/src/pages/SettingsPage.tsx` (modified, +2/-1); `frontend/src/pages/TranscriptionPage.tsx` (modified, +30/-3).
- **구현/검증 diff 앵커:** `backend/src/api/routes.py` — `@@ -28,6 +28,7 @@`; `backend/src/services/colab_rendezvous.py` — `@@ -0,0 +1,152 @@`; `backend/src/services/drive.py` — `@@ -132,6 +132,9 @@ def find_or_create_folder(self, parent_id: str, name: str) -> str: ...`; `backend/src/services/settings.py` — `@@ -52,6 +52,7 @@ class RuntimeSettings(BaseModel):`; `backend/tests/test_colab_rendezvous.py` — `@@ -0,0 +1,558 @@`; `backend/tests/test_core.py` — `@@ -376,3 +376,37 @@ def test_stop_cancel_consistency(tmp_path):`; `backend/tests/test_job_api_classification.py` — `@@ -328,3 +328,90 @@ def test_job_creation_rejects_normalized_without_rename(tmp_path):`; `colab/README.md` — `@@ -0,0 +1,20 @@`; `colab/requirements.txt` — `@@ -0,0 +1,4 @@`.
- **관련 원문 표기 번호:** 명시적 Issue 번호 미확인.
- **원본 PR의 검증 문구:** 구체 실행 결과가 본문에 없음 — 미확인.
- **재발 시 추적:** Colab Quick Tunnel/서버 비용·가용성은 실사용 시 별도 확인.
- **계보:** 현 Integration에 조상으로 포함; 후속 PR과 최신 계약에 의해 수정되었을 수 있음.

## [PR #93](https://github.com/bongbong90/Sorigul/pull/93) · Phase 4 progress

- **원본:** Core workflow Phase 4: honest duration, progress and ETA; CLOSED / GitHub 미병합; HEAD `e20c7a906c6049b25fbf6dd603fe9cd6aadf0874`; 원래 base `review/core-workflow-phase3b-colab`.
- **당시 목표:** 전사 파일 시간·진행률·ETA를 실제 데이터와 맞추도록 구현.
- **변경 파일 12개:** `backend/src/domain/models.py` (modified, +1/-0); `backend/src/engines/colab.py` (modified, +2/-0); `backend/src/services/scanner.py` (modified, +10/-2); `backend/src/services/transcription_runner.py` (modified, +182/-2); `backend/tests/test_colab_engine.py` (modified, +4/-0); `backend/tests/test_core.py` (modified, +30/-0); `backend/tests/test_job_api_classification.py` (modified, +82/-0); `backend/tests/test_transcription_runner.py` (modified, +238/-0); `frontend/src/api/client.ts` (modified, +2/-0); `frontend/src/components/transcription/CurrentTaskSection.tsx` (modified, +32/-3); `frontend/src/components/transcription/TranscriptionActions.tsx` (modified, +5/-5); `frontend/src/pages/TranscriptionPage.tsx` (modified, +47/-5).
- **구현/검증 diff 앵커:** `backend/src/domain/models.py` — `@@ -46,6 +46,7 @@ class ScannedFile(BaseModel):`; `backend/src/engines/colab.py` — `@@ -388,6 +388,7 @@ def _transcribe_serial(`; `backend/src/services/scanner.py` — `@@ -2,12 +2,19 @@`; `backend/src/services/transcription_runner.py` — `@@ -1,10 +1,12 @@`; `backend/tests/test_colab_engine.py` — `@@ -116,6 +116,8 @@ def test_colab_uses_fixed_300_seconds_and_merges_offsets(tmp_path):`; `backend/tests/test_core.py` — `@@ -73,6 +73,36 @@ def test_file_scan_rejects_invalid_segment(tmp_path):`; `backend/tests/test_job_api_classification.py` — `@@ -1,4 +1,5 @@`; `backend/tests/test_transcription_runner.py` — `@@ -1,6 +1,8 @@`; `frontend/src/api/client.ts` — `@@ -41,6 +41,7 @@ export interface ScannedFile {`.
- **관련 원문 표기 번호:** 명시적 Issue 번호 미확인.
- **원본 PR의 검증 문구:** 구체 실행 결과가 본문에 없음 — 미확인.
- **재발 시 추적:** 실측 진도와 추정치 혼동·화면 진행 표시 시 API/runner 및 UI 포맷 확인.
- **계보:** 현 Integration에 조상으로 포함; 후속 PR과 최신 계약에 의해 수정되었을 수 있음.

## [PR #94](https://github.com/bongbong90/Sorigul/pull/94) · Phase 5A regression

- **원본:** Core workflow Phase 5A: release regression suite; CLOSED / GitHub 미병합; HEAD `57b9d468253515b7989932ee67b49d1ca7be4d0e`; 원래 base `review/core-workflow-phase4-progress`.
- **당시 목표:** 릴리스 전 각 기능의 회귀 테스트와 검증 스크립트 강화.
- **변경 파일 2개:** `scripts/run_core_workflow_regression.ps1` (added, +51/-0); `tests/test_core_workflow_release_contracts.py` (added, +129/-0).
- **구현/검증 diff 앵커:** `scripts/run_core_workflow_regression.ps1` — `@@ -0,0 +1,51 @@`; `tests/test_core_workflow_release_contracts.py` — `@@ -0,0 +1,129 @@`.
- **관련 원문 표기 번호:** 명시적 Issue 번호 미확인.
- **원본 PR의 검증 문구:** 구체 실행 결과가 본문에 없음 — 미확인.
- **재발 시 추적:** 현 HEAD #123/#114가 최종 gate이며 과거 테스트 결과 자동 재사용 금지.
- **계보:** 현 Integration에 조상으로 포함; 후속 PR과 최신 계약에 의해 수정되었을 수 있음.

## [PR #95](https://github.com/bongbong90/Sorigul/pull/95) · Phase 5B installed evidence

- **원본:** Core workflow Phase 5B: installed build validation record; CLOSED / GitHub 미병합; HEAD `9db695b6dcc9140086e42e1114c872aa32acf801`; 원래 base `review/core-workflow-phase5a-regression`.
- **당시 목표:** 당시 설치형 빌드·실행 검증 기록을 남김.
- **변경 파일 1개:** `docs/release/CORE_WORKFLOW_REFINEMENT_BUILD_VALIDATION.md` (added, +110/-0).
- **구현/검증 diff 앵커:** `docs/release/CORE_WORKFLOW_REFINEMENT_BUILD_VALIDATION.md` — `@@ -0,0 +1,110 @@`.
- **관련 원문 표기 번호:** 명시적 Issue 번호 미확인.
- **원본 PR의 검증 문구:** 구체 실행 결과가 본문에 없음 — 미확인.
- **재발 시 추적:** 과거 MSI/Runtime pairing 증거를 현재 HEAD 증거로 대체 사용하면 안 됨.
- **계보:** 현 Integration에 조상으로 포함; 후속 PR과 최신 계약에 의해 수정되었을 수 있음.

## [PR #96](https://github.com/bongbong90/Sorigul/pull/96) · CUDA remediation

- **원본:** CUDA release remediation; CLOSED / GitHub 미병합; HEAD `94a08f51fb5ee6f273fbb2ce5a38b7b557c5d75f`; 원래 base `review/core-workflow-phase5b-installed-validation`.
- **당시 목표:** 릴리스 CUDA 엔진 및 패키징 미충족 상태를 개선.
- **변경 파일 5개:** `backend/packaging/sorigul_backend.spec` (modified, +3/-2); `backend/src/sidecar_main.py` (modified, +33/-0); `backend/tests/test_sidecar_cuda_contract.py` (added, +222/-0); `scripts/build_backend_sidecar.ps1` (modified, +172/-16); `tools/requirements-torch-cuda.txt` (added, +2/-0).
- **구현/검증 diff 앵커:** `backend/packaging/sorigul_backend.spec` — `@@ -22,7 +22,7 @@ dev-mode contract (see docs/runtime/INSTALLER_INSTALLED_RUNTIME_VALIDATION.md`; `backend/src/sidecar_main.py` — `@@ -17,6 +17,27 @@`; `backend/tests/test_sidecar_cuda_contract.py` — `@@ -0,0 +1,222 @@`; `scripts/build_backend_sidecar.ps1` — `@@ -49,13 +49,66 @@ if (-not (Test-Path $VenvPython)) {`; `tools/requirements-torch-cuda.txt` — `@@ -0,0 +1,2 @@`.
- **관련 원문 표기 번호:** #12, #13, #10, #67.
- **원본 PR의 검증 문구:** - wait for packaged self-test completion / - #13 CUDA/ffmpeg self-test gap / - #10 historical self-test hang mitigation.
- **재발 시 추적:** Runtime/Core 구분·CUDA 13.0 고정은 후속 #100/#98/현재 계약과 함께 재확인.
- **계보:** 현 Integration에 조상으로 포함; 후속 PR과 최신 계약에 의해 수정되었을 수 있음.

## [PR #98](https://github.com/bongbong90/Sorigul/pull/98) · Scalar provenance

- **원본:** fix: enforce scalar release manifest provenance; CLOSED / GitHub 미병합; HEAD `22ebe3d28170386ab1a580ae2f3ed2f533f19269`; 원래 base `main`.
- **당시 목표:** Local/Core 매니페스트 원본 HEAD·Scalar CUDA 메타데이터 형식 및 검증 강화.
- **변경 파일 3개:** `backend/tests/test_release_packaging_contract.py` (modified, +101/-0); `scripts/build_backend_sidecar.ps1` (modified, +37/-6); `scripts/build_windows_installer.ps1` (modified, +35/-1).
- **구현/검증 diff 앵커:** `backend/tests/test_release_packaging_contract.py` — `@@ -1,3 +1,4 @@`; `scripts/build_backend_sidecar.ps1` — `@@ -358,14 +358,28 @@ result_path.write_text(imageio_ffmpeg.get_ffmpeg_exe(), encoding="utf-8")`; `scripts/build_windows_installer.ps1` — `@@ -77,7 +77,41 @@ try {`.
- **관련 원문 표기 번호:** #45, #46.
- **원본 PR의 검증 문구:** R1-FIX REVIEW = PASS / - scalar serialization regression: PASS / - PowerShell syntax: PASS.
- **재발 시 추적:** Source HEAD 다르면 #191 Provenance mismatch; manifest 소유권은 후속 #100에 따라 달라짐.
- **계보:** 현 Integration에 조상으로 포함; 후속 PR과 최신 계약에 의해 수정되었을 수 있음.
