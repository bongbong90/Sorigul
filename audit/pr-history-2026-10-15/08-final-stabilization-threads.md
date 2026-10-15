# Historical PR review · H — Final filename rule, source audit and heartbeat race

> 이 파일은 74건 전체 이력 검토의 마지막 4건. 본문은 원본 변경 파일 API와 PR 원문 기반. 테스트 수치는 과거 범위 한정.

<a id="pr-183"></a>

## [PR #183](https://github.com/bongbong90/Sorigul/pull/183) · Eduwill no-week filename

- **원본:** feat: manual week input + Eduwill no-week normalization (#180); CLOSED / GitHub 병합 아님; HEAD `36ac439c7f631c86e4c5263582d44755ea41c230`; base `fix/174-guarded-tray-exit`.
- **문제·수정 목적:** 수동 주차 입력 및 에듀윌 파일명에 주차 토큰이 없는 경우의 정규화·강 번호 처리.
- **실제 변경 파일 16개:** `backend/src/api/routes.py` (modified, +42/-23); `backend/src/services/normalizer.py` (modified, +144/-36); `backend/tests/test_core.py` (modified, +2/-2); `backend/tests/test_filename_normalizer_parity.py` (modified, +2/-1); `backend/tests/test_job_api_classification.py` (modified, +14/-10); `backend/tests/test_manual_week_normalization.py` (added, +490/-0); `frontend/src/api/client.ts` (modified, +12/-5); `frontend/src/components/transcription/ClassificationSection.tsx` (modified, +19/-1); `frontend/src/lib/classification.ts` (modified, +16/-0); `frontend/src/lib/preflight.ts` (modified, +5/-3); `frontend/src/pages/TranscriptionPage.tsx` (modified, +111/-22); `frontend/src/styles/feature-pages.css` (modified, +1/-1); `tests/frontend/confirmation_preflight_harness.cjs` (modified, +7/-1); `tests/frontend/folder_picker_harness.cjs` (modified, +9/-4); `tests/frontend/manual_week_harness.cjs` (added, +244/-0); `tests/test_180_manual_week_frontend.py` (added, +55/-0).
- **Patch 진입점:** `backend/src/api/routes.py` — `@@ -9,9 +9,11 @@`; `backend/src/services/normalizer.py` — `@@ -2,7 +2,7 @@`; `backend/tests/test_core.py` — `@@ -306,7 +306,7 @@ def test_job_create_modes(tmp_path, test_dir):`; `backend/tests/test_filename_normalizer_parity.py` — `@@ -231,6 +231,7 @@ def test_batch_endpoint_and_job_metadata_use_restored_allocation(tmp_path):`; `backend/tests/test_job_api_classification.py` — `@@ -43,7 +43,7 @@ def test_create_job_all_incomplete_uses_eligible_target_denominator(tmp_path, mo`; `backend/tests/test_manual_week_normalization.py` — `@@ -0,0 +1,490 @@`; `frontend/src/api/client.ts` — `@@ -55,8 +55,14 @@ export interface NormalizationPreview {`; `frontend/src/components/transcription/ClassificationSection.tsx` — `@@ -8,10 +8,13 @@ import { Input } from '../ui/Input'`; `frontend/src/lib/classification.ts` — `@@ -46,6 +46,22 @@ export function validateClassificationText(raw: string, fieldLabel: string): Cla`; `frontend/src/lib/preflight.ts` — `@@ -9,16 +9,18 @@ export type FileResolution =`.
- **본문 관련 번호:** #180, #182, #170, #171, #168, #173, #174.
- **당시 검증 문구:** Refs #180 (stays OPEN — SOURCE PASS / INSTALLED RETEST PENDING). Stacked on #182. Do not merge. / - Backend full: 730 passed, 2 skipped (includes the new 'test_manual_week_normalization.py', 98 tests). / - Root 'pytest tests' under Windows PowerShell 5.1: 211 passed (includes the #170/#171 page harnesses, the new #180 page harness with 18 scenarios, and the #168/#173/#174 contracts / - Frontend lint, typecheck and build: PASS. 'git diff --check': clean..
- **지금 문제 생기면:** #192 중개사법 파일명 예외와 교차; 기존 파일 덮어쓰기·중복 순번·반드시 확인 단계 유지.
- **최종 경계:** 이 PR HEAD는 현 Integration 조상. 최신 파일 소스가 반드시 같은 로직이라는 증거는 아님.

<a id="pr-186"></a>

## [PR #186](https://github.com/bongbong90/Sorigul/pull/186) · Final prefreeze reconciliation

- **원본:** docs: reconcile final Study-Use pre-freeze contract (#184); CLOSED / GitHub 병합 아님; HEAD `87d7b1e72840335eaa3baa1e7b805a01a8fe329e`; base `fix/180-manual-week-eduwill-normalization`.
- **문제·수정 목적:** 사용자 개인 학습 일정과 릴리스 Gate, 우선순위/계약을 Freeze 전에 재조정.
- **실제 변경 파일 5개:** `docs/project/CURRENT_PRODUCT_CONTRACT.md` (modified, +49/-2); `docs/project/DEVELOPMENT_RULES.md` (modified, +6/-3); `docs/project/PROJECT_CHARTER.md` (modified, +1/-1); `docs/project/ROADMAP.md` (modified, +21/-3); `docs/project/SORIGUL_FULL_LEGACY_PARITY_COMPLETION_PLAN_2026-09-28.md` (modified, +4/-4).
- **Patch 진입점:** `docs/project/CURRENT_PRODUCT_CONTRACT.md` — `@@ -55,6 +55,27 @@ Legacy ACTIVE user-visible capability와 functional behavior는 기본적으로`; `docs/project/DEVELOPMENT_RULES.md` — `@@ -73,9 +73,12 @@`; `docs/project/PROJECT_CHARTER.md` — `@@ -52,6 +52,6 @@ Greenfield implementation, Legacy behavioral parity.`; `docs/project/ROADMAP.md` — `@@ -19,7 +19,25 @@`; `docs/project/SORIGUL_FULL_LEGACY_PARITY_COMPLETION_PLAN_2026-09-28.md` — `@@ -136,7 +136,7 @@ Planning target:`.
- **본문 관련 번호:** #184, #180, #185, #114, #12, #54, #55.
- **당시 검증 문구:** - Completion Plan critical path #12 → '#54/#55 docs closeout → #114 PASS + final gate approval → one consolidated integration PR merge' / - governance/contract focused tests ('test_current_product_contract_decisions', 'test_release_readiness_contracts', 'test_core_workflow_release_contracts'): **29 passed** / - root, Windows PowerShell 5.1 canonical, 'venv\Scripts\python.exe -m pytest tests -q -rfE -p no:cacheprovider': **211 passed** / - 'git diff --check': PASS; 'git diff --cached --check': PASS.
- **지금 문제 생기면:** 당시 10/31 계획은 최신 10/25 일정으로 상위 변경됨; stale 계획을 출시 판정에 재사용 금지.
- **최종 경계:** 이 PR HEAD는 현 Integration 조상. 최신 파일 소스가 반드시 같은 로직이라는 증거는 아님.

<a id="pr-187"></a>

## [PR #187](https://github.com/bongbong90/Sorigul/pull/187) · Final #123 source audit

- **원본:** audit: final #123 source regression and classification closure; CLOSED / GitHub 병합 아님; HEAD `035db132609b9ed298f1f4c1d8aacd838bd41056`; base `docs/pre-freeze-plan-reconciliation`.
- **문제·수정 목적:** Legacy 전체 범위 소스 회귀검증과 문서 분류 잠금의 최종 감사·기록.
- **실제 변경 파일 3개:** `docs/project/CURRENT_SOURCE_OF_TRUTH.md` (modified, +1/-0); `docs/runtime/STUDY_USE_FULL_SOURCE_CONTRACT_REGRESSION_2026-10-06.md` (added, +433/-0); `tests/test_release_readiness_contracts.py` (modified, +1/-0).
- **Patch 진입점:** `docs/project/CURRENT_SOURCE_OF_TRUTH.md` — `@@ -114,6 +114,7 @@ Classification values are exact: CURRENT CONTRACT, SUPERSEDED, HISTORICAL E`; `docs/runtime/STUDY_USE_FULL_SOURCE_CONTRACT_REGRESSION_2026-10-06.md` — `@@ -0,0 +1,433 @@`; `tests/test_release_readiness_contracts.py` — `@@ -11,6 +11,7 @@`.
- **본문 관련 번호:** #123, #7, #116, #185, #113, #187, #186, #114, #115.
- **당시 검증 문구:** ## #123 Source-of-Truth Classification Closure — PASS (2026-10-07 KST) / - Windows PowerShell **5.1.26100.9444 Desktop**, repository venv: focused release-readiness **14 PASS**; exact-once, duplicate prevention, allowed classification set and historical / - Final committed-tree focused rerun at '035db132609b9ed298f1f4c1d8aacd838bd41056': **14 PASS**. Working/staged diff checks **PASS**; tracked tree/index **CLEAN**. Five pre-existin / #123 final full source regression at the current consolidated candidate is **PASS**. Production code/tests/contracts are unchanged; the only tracked change is the new fixed regress / - P0/P1 source blockers: **0**. SOURCE FULL REGRESSION = PASS. PRODUCT-SOURCE PARITY = COMPLETE..
- **지금 문제 생기면:** #199/#201과 마찬가지로 새 HEAD에서 테스트 재실행이 필요하며 과거 #123 PASS를 대체 사용하지 않음.
- **최종 경계:** 이 PR HEAD는 현 Integration 조상. 최신 파일 소스가 반드시 같은 로직이라는 증거는 아님.

<a id="pr-188"></a>

## [PR #188](https://github.com/bongbong90/Sorigul/pull/188) · Heartbeat read/replace race

- **원본:** fix: harden #113 heartbeat reads against replace race (#164); CLOSED / GitHub 병합 아님; HEAD `28ba869bec598e8d436d0877d13a28194c305aff`; base `audit/123-final-source-regression-rerun`.
- **문제·수정 목적:** 단일 Writer heartbeat JSON을 atomic replace 중 읽을 때 race로 인한 거짓 실패를 완화.
- **실제 변경 파일 2개:** `scripts/run_113_session_bootstrap.ps1` (modified, +7/-3); `tests/test_113_session_bootstrap_contract.py` (modified, +128/-2).
- **Patch 진입점:** `scripts/run_113_session_bootstrap.ps1` — `@@ -42,13 +42,17 @@ function Write-AtomicJson([string]$Path, $Value) {`; `tests/test_113_session_bootstrap_contract.py` — `@@ -39,6 +39,43 @@ def test_repository_owns_one_guard_and_activation_boundary():`.
- **본문 관련 번호:** #113, #164, #116, #7, #189, #56, #63, #47, #48.
- **당시 검증 문구:** Official deadline updated in #116 and #7. Historical 2026-10-31 checkpoints below remain audit history only. Goal: installed, working Korean MP3 Local-GPU study transcription with  / - Source/upstream/tracked identity and existing Freeze: 250/250 PASS, unchanged. No new Freeze or canonical preflight rerun. / - New canonical session ACTIVE and Single Writer acquisition/competition denial PASS. / - Fresh Local, installer-owned Core, MSI, source/provenance/hash verification and lightweight heavy-payload exclusion PASS. Current Core/MSI attempt 2 supersedes a non-final harnes / - Protected-data zero-change checkpoint FAILED: one directory metadata discrepancy, cause unresolved. Strict HARD STOP retained. No protected data restored or zero-change exception.
- **지금 문제 생기면:** Bootstrap/probe에서 heartbeat 순간 불일치 시 replace/파일 획득과 lock 정리 경로, 로그를 분리해 진단.
- **최종 경계:** 이 PR HEAD는 현 Integration 조상. 최신 파일 소스가 반드시 같은 로직이라는 증거는 아님.
