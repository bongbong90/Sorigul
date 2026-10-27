# Sorigul historical PR forensic / maintenance index (2026-10-15)

> **목적:** GitHub에서 CLOSED지만 직접 MERGED 처리되지 않았던 74개 PR을 개별 분석하여 이후 장애 조사·기능 변경·품질 재검증의 출발점을 제공한다. 이 문서는 코드 실행이나 최신 release readiness의 승인서가 아니다.

## 정확한 Git 이력 해석

- 범위: 2026-10-15 당시 GitHub의 **CLOSED / merged_at=null** 74개 원본 PR. 이 중 13개는 2026-10-15 정리 작업에서 관리상 CLOSED 처리됐고, 나머지 61개는 그 전에 이미 CLOSED였다.
- 74개 모두 각 PR의 **정확한 head commit이** `integration/study-use-final-candidate` `38b856a0dfe18448005a59bf7bb36479f3cd2692`의 조상임을 GitHub compare(behind=0)로 확인했다. 이것은 코드 계보의 포함이지 PR 상태 `MERGED`나 최신 기능 PASS를 뜻하지 않는다.
- `main`에는 각 CLOSED PR을 병합하지 않았다. 최종 Integration→main 이행은 [PR #185](https://github.com/bongbong90/Sorigul/pull/185)가 책임지며 **#123/Preflight/Freeze, #191, #47, #114** gate에 걸려 있다.
- 초기 PR들은 연속된 **stacked base**를 사용했으므로 원본 diff는 원래 base와 그 PR HEAD 사이의 변화다. 이제 와서 옛 head를 `main`에 rebase/merge하면 변경 중복, 충돌 또는 과거 동작 역행 위험이 있다.
- 후속 PR들이 같은 파일을 재수정했을 수 있다. 여기 적힌 **당시 변경 목적·검증 표기와 현재 코드의 구현 진실은 별도로 구분**한다. Source of Truth는 현 `docs/project/CURRENT_PRODUCT_CONTRACT.md`를 따른다.
- 개인 MP3/경로/Drive 인증/로그 원문은 복사하지 않는다. 감사 브랜치는 Integration에서 독립했고 아직 현재 릴리스 HEAD에 병합하지 않았다.

## 전체 커밋·PR·브랜치 통합 대조

- [전체 153개 커밋 / 89개 PR / 91개 원격 브랜치 대조 및 병합 판단](./COMMIT_PR_FULL_RECONCILIATION_2026-10-15.md): 기존 74건 개별 감사기록의 상위 원장으로, 최초 커밋부터 현재 Integration HEAD까지의 commit SHA·PR 상태와 병합 보류 사유를 정리한다. **코드 병합 및 installed PASS를 의미하지 않는다.**

## 찾아보기

| 기록 파일 | 범위/대상 | PR 수 |
|---|---|---:|
| [01-foundation-and-hardening.md](./01-foundation-and-hardening.md) | 패키징 보안 초기 UI | 10 |
| [02-migration-and-ui-freeze.md](./02-migration-and-ui-freeze.md) | Migration/첫 UI Freeze | 10 |
| [03-core-workflow-and-provenance.md](./03-core-workflow-and-provenance.md) | Core workflow·Colab·CUDA | 10 |
| [04-runtime-and-legacy-parity.md](./04-runtime-and-legacy-parity.md) | Runtime 분리·Legacy 패리티 | 10 |
| [05-parity-restoration-and-security.md](./05-parity-restoration-and-security.md) | 기능 복구·Windows 보안 | 10 |
| [06-release-governance-and-early-main-candidates.md](./06-release-governance-and-early-main-candidates.md) | Release Gate/옛 main 후보 | 10 |
| [07-native-ux-and-session-guards.md](./07-native-ux-and-session-guards.md) | Native UX·Single Writer | 10 |
| [08-final-stabilization-threads.md](./08-final-stabilization-threads.md) | 최종 정리·heartbeat | 4 |
| [pr-inventory.json](./pr-inventory.json) | **74개 PR × 총 842개 수정 파일 이력**; path, diff 통계, head/base, 보조 인덱스 | 74 |

## 장애·기능별 역추적 지침

### 전사 화면·UI·폴더/분류
관련 PR: [#73](https://github.com/bongbong90/Sorigul/pull/73), [#74](https://github.com/bongbong90/Sorigul/pull/74), [#75](https://github.com/bongbong90/Sorigul/pull/75), [#76](https://github.com/bongbong90/Sorigul/pull/76), [#80](https://github.com/bongbong90/Sorigul/pull/80), [#81](https://github.com/bongbong90/Sorigul/pull/81), [#82](https://github.com/bongbong90/Sorigul/pull/82), [#89](https://github.com/bongbong90/Sorigul/pull/89), [#91](https://github.com/bongbong90/Sorigul/pull/91), [#93](https://github.com/bongbong90/Sorigul/pull/93), [#134](https://github.com/bongbong90/Sorigul/pull/134), [#143](https://github.com/bongbong90/Sorigul/pull/143), [#144](https://github.com/bongbong90/Sorigul/pull/144), [#177](https://github.com/bongbong90/Sorigul/pull/177), [#178](https://github.com/bongbong90/Sorigul/pull/178), [#183](https://github.com/bongbong90/Sorigul/pull/183)
전사/폴더/분류 오동작이면 최신 `TranscriptionPage.tsx`, `AppShell.tsx`, `classification.py`, `normalizer.py`, `QueueTable.tsx`와 과거 테스트 비교; 현재 #192/#193/#194 후속 포함

### Local Whisper·CUDA·배포
관련 PR: [#67](https://github.com/bongbong90/Sorigul/pull/67), [#71](https://github.com/bongbong90/Sorigul/pull/71), [#84](https://github.com/bongbong90/Sorigul/pull/84), [#86](https://github.com/bongbong90/Sorigul/pull/86), [#94](https://github.com/bongbong90/Sorigul/pull/94), [#95](https://github.com/bongbong90/Sorigul/pull/95), [#96](https://github.com/bongbong90/Sorigul/pull/96), [#98](https://github.com/bongbong90/Sorigul/pull/98), [#100](https://github.com/bongbong90/Sorigul/pull/100), [#102](https://github.com/bongbong90/Sorigul/pull/102), [#103](https://github.com/bongbong90/Sorigul/pull/103), [#105](https://github.com/bongbong90/Sorigul/pull/105), [#119](https://github.com/bongbong90/Sorigul/pull/119), [#153](https://github.com/bongbong90/Sorigul/pull/153), [#155](https://github.com/bongbong90/Sorigul/pull/155), [#158](https://github.com/bongbong90/Sorigul/pull/158), [#160](https://github.com/bongbong90/Sorigul/pull/160), [#175](https://github.com/bongbong90/Sorigul/pull/175)
설치 Core/Local manifest의 source_head/hash가 맞는지 먼저 확인하고 Worker spawn·CUDA self-test를 분리. 현 #191 pairing 증거 우선

### Colab·외부 인증·Drive
관련 PR: [#68](https://github.com/bongbong90/Sorigul/pull/68), [#69](https://github.com/bongbong90/Sorigul/pull/69), [#85](https://github.com/bongbong90/Sorigul/pull/85), [#90](https://github.com/bongbong90/Sorigul/pull/90), [#91](https://github.com/bongbong90/Sorigul/pull/91), [#92](https://github.com/bongbong90/Sorigul/pull/92), [#120](https://github.com/bongbong90/Sorigul/pull/120), [#137](https://github.com/bongbong90/Sorigul/pull/137), [#141](https://github.com/bongbong90/Sorigul/pull/141)
Colab 연결/URL·OAuth loopback·Drive 업로드 실패의 경계를 구분. 비용 가능 외부 호출은 별도 승인이 없으면 금지

### Job·재시도·결과물·회복
관련 PR: [#68](https://github.com/bongbong90/Sorigul/pull/68), [#83](https://github.com/bongbong90/Sorigul/pull/83), [#89](https://github.com/bongbong90/Sorigul/pull/89), [#93](https://github.com/bongbong90/Sorigul/pull/93), [#120](https://github.com/bongbong90/Sorigul/pull/120), [#121](https://github.com/bongbong90/Sorigul/pull/121), [#134](https://github.com/bongbong90/Sorigul/pull/134), [#139](https://github.com/bongbong90/Sorigul/pull/139), [#140](https://github.com/bongbong90/Sorigul/pull/140), [#146](https://github.com/bongbong90/Sorigul/pull/146), [#176](https://github.com/bongbong90/Sorigul/pull/176), [#177](https://github.com/bongbong90/Sorigul/pull/177), [#178](https://github.com/bongbong90/Sorigul/pull/178)
JobManager·Runner·OutputBundle·Close guard 상태 전이와 atomic 저장 및 기존 DONE 결과 보존 확인

### Windows Desktop·Tray·Single Writer
관련 PR: [#70](https://github.com/bongbong90/Sorigul/pull/70), [#86](https://github.com/bongbong90/Sorigul/pull/86), [#120](https://github.com/bongbong90/Sorigul/pull/120), [#135](https://github.com/bongbong90/Sorigul/pull/135), [#137](https://github.com/bongbong90/Sorigul/pull/137), [#140](https://github.com/bongbong90/Sorigul/pull/140), [#142](https://github.com/bongbong90/Sorigul/pull/142), [#145](https://github.com/bongbong90/Sorigul/pull/145), [#146](https://github.com/bongbong90/Sorigul/pull/146), [#160](https://github.com/bongbong90/Sorigul/pull/160), [#165](https://github.com/bongbong90/Sorigul/pull/165), [#175](https://github.com/bongbong90/Sorigul/pull/175), [#179](https://github.com/bongbong90/Sorigul/pull/179), [#181](https://github.com/bongbong90/Sorigul/pull/181), [#182](https://github.com/bongbong90/Sorigul/pull/182), [#188](https://github.com/bongbong90/Sorigul/pull/188)
중복 실행/종료 잔류/heartbeat/race 시 `src-tauri/src/lib.rs`, `sidecar.rs`, close_guard, bootstrap와 해당 tests 추적

### 계약·패리티·Source/release gate
관련 PR: [#71](https://github.com/bongbong90/Sorigul/pull/71), [#77](https://github.com/bongbong90/Sorigul/pull/77), [#78](https://github.com/bongbong90/Sorigul/pull/78), [#79](https://github.com/bongbong90/Sorigul/pull/79), [#87](https://github.com/bongbong90/Sorigul/pull/87), [#88](https://github.com/bongbong90/Sorigul/pull/88), [#94](https://github.com/bongbong90/Sorigul/pull/94), [#95](https://github.com/bongbong90/Sorigul/pull/95), [#98](https://github.com/bongbong90/Sorigul/pull/98), [#105](https://github.com/bongbong90/Sorigul/pull/105), [#115](https://github.com/bongbong90/Sorigul/pull/115), [#117](https://github.com/bongbong90/Sorigul/pull/117), [#129](https://github.com/bongbong90/Sorigul/pull/129), [#148](https://github.com/bongbong90/Sorigul/pull/148), [#149](https://github.com/bongbong90/Sorigul/pull/149), [#152](https://github.com/bongbong90/Sorigul/pull/152), [#157](https://github.com/bongbong90/Sorigul/pull/157), [#158](https://github.com/bongbong90/Sorigul/pull/158), [#160](https://github.com/bongbong90/Sorigul/pull/160), [#162](https://github.com/bongbong90/Sorigul/pull/162), [#163](https://github.com/bongbong90/Sorigul/pull/163), [#166](https://github.com/bongbong90/Sorigul/pull/166), [#186](https://github.com/bongbong90/Sorigul/pull/186), [#187](https://github.com/bongbong90/Sorigul/pull/187)
Current Product Contract를 우선, 오래된 기술 자문·Freeze·#123 결과는 고정 당시 범위로 한정

## 유지보수 시 실제 절차

1. **현재 재현·현행 계약 먼저 확인:** 실제 Source HEAD, Runtime/Core manifest, 설치본, 사용자 데이터의 보존 조건, 변경된 API/상태를 확인한다. 이 역사 문서는 옛 동작을 자동으로 복원하라는 지시가 아니다.
2. **변경 파일 검색:** `pr-inventory.json`에서 현재 문제 파일 경로를 찾아 과거 PR 후보를 좁힌다. 같은 파일을 여러 번 수정했다면 순서대로 비교한다.
3. **PR별 분석 열기:** 아래 목차에서 기록의 해당 PR 상세 항목을 연다. 원본 PR 링크를 통해 Diff·토론·테스트·관련 Issue까지 추적한다.
4. **이력 연결:** `git log --all --oneline -- <path>` 와 `git blame`으로 현재 행의 도입/후속 수정을 확인한다. 단순 PR 제목으로 현재 버그 원인을 확정하지 않는다.
5. **검증 범위 보존:** 과거 PR의 PASS는 당시 테스트·환경 한정. 현 HEAD에서 집중 테스트, 그 다음 릴리스 canonical gates, 마지막 사용자 실사용 검증을 수행한다.
6. **향후 PR/Issue 업데이트:** 발견한 원인과 기존 이력의 관련성을 해당 최신 Issue와 신규 PR에 링크하되, 개인 데이터·비밀·실제 Drive/Colab API 호출은 승인 없으면 금지한다.

## PR별 바로가기 (총 74건; 번호 오름차순)

| PR | 원래 PR 제목 | 분석 | 당시 PR 직접 병합 |
|---:|---|---|---|
| [#67](https://github.com/bongbong90/Sorigul/pull/67) | Package A: harden release packaging gates | [파일·patch·검증·주의점](./01-foundation-and-hardening.md#pr-67) | CLOSED / 미병합 |
| [#68](https://github.com/bongbong90/Sorigul/pull/68) | Package B: harden process and recovery boundaries | [파일·patch·검증·주의점](./01-foundation-and-hardening.md#pr-68) | CLOSED / 미병합 |
| [#69](https://github.com/bongbong90/Sorigul/pull/69) | Package C: secure Colab and OAuth boundaries | [파일·patch·검증·주의점](./01-foundation-and-hardening.md#pr-69) | CLOSED / 미병합 |
| [#70](https://github.com/bongbong90/Sorigul/pull/70) | Package D: harden frontend and filesystem UX integrity | [파일·patch·검증·주의점](./01-foundation-and-hardening.md#pr-70) | CLOSED / 미병합 |
| [#71](https://github.com/bongbong90/Sorigul/pull/71) | Package E: close pre-build release validation contracts | [파일·patch·검증·주의점](./01-foundation-and-hardening.md#pr-71) | CLOSED / 미병합 |
| [#73](https://github.com/bongbong90/Sorigul/pull/73) | Design system foundation | [파일·patch·검증·주의점](./01-foundation-and-hardening.md#pr-73) | CLOSED / 미병합 |
| [#74](https://github.com/bongbong90/Sorigul/pull/74) | App shell implementation | [파일·patch·검증·주의점](./01-foundation-and-hardening.md#pr-74) | CLOSED / 미병합 |
| [#75](https://github.com/bongbong90/Sorigul/pull/75) | Transcription screen static UI | [파일·patch·검증·주의점](./01-foundation-and-hardening.md#pr-75) | CLOSED / 미병합 |
| [#76](https://github.com/bongbong90/Sorigul/pull/76) | Transcription screen mock interactions | [파일·patch·검증·주의점](./01-foundation-and-hardening.md#pr-76) | CLOSED / 미병합 |
| [#77](https://github.com/bongbong90/Sorigul/pull/77) | Legacy feature parity audit | [파일·patch·검증·주의점](./01-foundation-and-hardening.md#pr-77) | CLOSED / 미병합 |
| [#78](https://github.com/bongbong90/Sorigul/pull/78) | Migration contract review and lock | [파일·patch·검증·주의점](./02-migration-and-ui-freeze.md#pr-78) | CLOSED / 미병합 |
| [#79](https://github.com/bongbong90/Sorigul/pull/79) | Sync project baseline to migration contract | [파일·patch·검증·주의점](./02-migration-and-ui-freeze.md#pr-79) | CLOSED / 미병합 |
| [#80](https://github.com/bongbong90/Sorigul/pull/80) | Close migration-contract UI gaps | [파일·patch·검증·주의점](./02-migration-and-ui-freeze.md#pr-80) | CLOSED / 미병합 |
| [#81](https://github.com/bongbong90/Sorigul/pull/81) | Validate UI state and UX for freeze | [파일·patch·검증·주의점](./02-migration-and-ui-freeze.md#pr-81) | CLOSED / 미병합 |
| [#82](https://github.com/bongbong90/Sorigul/pull/82) | Freeze Sorigul UI v1 | [파일·patch·검증·주의점](./02-migration-and-ui-freeze.md#pr-82) | CLOSED / 미병합 |
| [#83](https://github.com/bongbong90/Sorigul/pull/83) | Migrate core backend file and job foundation | [파일·patch·검증·주의점](./02-migration-and-ui-freeze.md#pr-83) | CLOSED / 미병합 |
| [#84](https://github.com/bongbong90/Sorigul/pull/84) | Migrate transcription engines | [파일·patch·검증·주의점](./02-migration-and-ui-freeze.md#pr-84) | CLOSED / 미병합 |
| [#85](https://github.com/bongbong90/Sorigul/pull/85) | Migrate Drive results and desktop UX | [파일·patch·검증·주의점](./02-migration-and-ui-freeze.md#pr-85) | CLOSED / 미병합 |
| [#86](https://github.com/bongbong90/Sorigul/pull/86) | Integrate Tauri desktop runtime and sidecar | [파일·patch·검증·주의점](./02-migration-and-ui-freeze.md#pr-86) | CLOSED / 미병합 |
| [#87](https://github.com/bongbong90/Sorigul/pull/87) | Full feature parity release validation | [파일·patch·검증·주의점](./02-migration-and-ui-freeze.md#pr-87) | CLOSED / 미병합 |
| [#88](https://github.com/bongbong90/Sorigul/pull/88) | Core workflow refinement plan | [파일·patch·검증·주의점](./03-core-workflow-and-provenance.md#pr-88) | CLOSED / 미병합 |
| [#89](https://github.com/bongbong90/Sorigul/pull/89) | Core workflow Phase 1: classification and normalization | [파일·patch·검증·주의점](./03-core-workflow-and-provenance.md#pr-89) | CLOSED / 미병합 |
| [#90](https://github.com/bongbong90/Sorigul/pull/90) | Core workflow Phase 2: Google Drive refinement | [파일·patch·검증·주의점](./03-core-workflow-and-provenance.md#pr-90) | CLOSED / 미병합 |
| [#91](https://github.com/bongbong90/Sorigul/pull/91) | Core workflow Phase 3A: audio metadata and URL normalization | [파일·patch·검증·주의점](./03-core-workflow-and-provenance.md#pr-91) | CLOSED / 미병합 |
| [#92](https://github.com/bongbong90/Sorigul/pull/92) | Core workflow Phase 3B: Colab rendezvous and integration | [파일·patch·검증·주의점](./03-core-workflow-and-provenance.md#pr-92) | CLOSED / 미병합 |
| [#93](https://github.com/bongbong90/Sorigul/pull/93) | Core workflow Phase 4: honest duration, progress and ETA | [파일·patch·검증·주의점](./03-core-workflow-and-provenance.md#pr-93) | CLOSED / 미병합 |
| [#94](https://github.com/bongbong90/Sorigul/pull/94) | Core workflow Phase 5A: release regression suite | [파일·patch·검증·주의점](./03-core-workflow-and-provenance.md#pr-94) | CLOSED / 미병합 |
| [#95](https://github.com/bongbong90/Sorigul/pull/95) | Core workflow Phase 5B: installed build validation record | [파일·patch·검증·주의점](./03-core-workflow-and-provenance.md#pr-95) | CLOSED / 미병합 |
| [#96](https://github.com/bongbong90/Sorigul/pull/96) | CUDA release remediation | [파일·patch·검증·주의점](./03-core-workflow-and-provenance.md#pr-96) | CLOSED / 미병합 |
| [#98](https://github.com/bongbong90/Sorigul/pull/98) | fix: enforce scalar release manifest provenance | [파일·patch·검증·주의점](./03-core-workflow-and-provenance.md#pr-98) | CLOSED / 미병합 |
| [#100](https://github.com/bongbong90/Sorigul/pull/100) | refactor: split Local Whisper runtime from Core | [파일·patch·검증·주의점](./04-runtime-and-legacy-parity.md#pr-100) | CLOSED / 미병합 |
| [#102](https://github.com/bongbong90/Sorigul/pull/102) | fix: harden Local Runtime pre-build provenance | [파일·patch·검증·주의점](./04-runtime-and-legacy-parity.md#pr-102) | CLOSED / 미병합 |
| [#103](https://github.com/bongbong90/Sorigul/pull/103) | test: validate split runtime installed synthetic gate | [파일·patch·검증·주의점](./04-runtime-and-legacy-parity.md#pr-103) | CLOSED / 미병합 |
| [#105](https://github.com/bongbong90/Sorigul/pull/105) | test: validate Local CUDA with Korean real-speech fixtures | [파일·patch·검증·주의점](./04-runtime-and-legacy-parity.md#pr-105) | CLOSED / 미병합 |
| [#115](https://github.com/bongbong90/Sorigul/pull/115) | docs: rebaseline full Legacy parity completion plan (planning/checkpoint only) | [파일·patch·검증·주의점](./04-runtime-and-legacy-parity.md#pr-115) | CLOSED / 미병합 |
| [#117](https://github.com/bongbong90/Sorigul/pull/117) | docs: lock development governance and current product contract | [파일·patch·검증·주의점](./04-runtime-and-legacy-parity.md#pr-117) | CLOSED / 미병합 |
| [#119](https://github.com/bongbong90/Sorigul/pull/119) | fix: restore Local and Colab transcription engine parity | [파일·patch·검증·주의점](./04-runtime-and-legacy-parity.md#pr-119) | CLOSED / 미병합 |
| [#120](https://github.com/bongbong90/Sorigul/pull/120) | feat: restore actionable completion notification | [파일·patch·검증·주의점](./04-runtime-and-legacy-parity.md#pr-120) | CLOSED / 미병합 |
| [#121](https://github.com/bongbong90/Sorigul/pull/121) | feat: restore live transcription-folder change detection | [파일·patch·검증·주의점](./04-runtime-and-legacy-parity.md#pr-121) | CLOSED / 미병합 |
| [#129](https://github.com/bongbong90/Sorigul/pull/129) | docs: validate full Legacy and current-contract source regression | [파일·patch·검증·주의점](./04-runtime-and-legacy-parity.md#pr-129) | CLOSED / 미병합 |
| [#134](https://github.com/bongbong90/Sorigul/pull/134) | fix: restore Legacy week and lesson allocation | [파일·patch·검증·주의점](./05-parity-restoration-and-security.md#pr-134) | CLOSED / 미병합 |
| [#135](https://github.com/bongbong90/Sorigul/pull/135) | fix: resolve Windows system utilities by trusted paths | [파일·patch·검증·주의점](./05-parity-restoration-and-security.md#pr-135) | CLOSED / 미병합 |
| [#137](https://github.com/bongbong90/Sorigul/pull/137) | fix: reject untrusted loopback Host headers | [파일·patch·검증·주의점](./05-parity-restoration-and-security.md#pr-137) | CLOSED / 미병합 |
| [#139](https://github.com/bongbong90/Sorigul/pull/139) | fix: enforce one global transcription run | [파일·patch·검증·주의점](./05-parity-restoration-and-security.md#pr-139) | CLOSED / 미병합 |
| [#140](https://github.com/bongbong90/Sorigul/pull/140) | fix: protect active work from window close | [파일·patch·검증·주의점](./05-parity-restoration-and-security.md#pr-140) | CLOSED / 미병합 |
| [#141](https://github.com/bongbong90/Sorigul/pull/141) | feat: restore Colab open convenience | [파일·patch·검증·주의점](./05-parity-restoration-and-security.md#pr-141) | CLOSED / 미병합 |
| [#142](https://github.com/bongbong90/Sorigul/pull/142) | feat: restore honest tray progress tooltip | [파일·patch·검증·주의점](./05-parity-restoration-and-security.md#pr-142) | CLOSED / 미병합 |
| [#143](https://github.com/bongbong90/Sorigul/pull/143) | feat: restore Folders column sorting | [파일·patch·검증·주의점](./05-parity-restoration-and-security.md#pr-143) | CLOSED / 미병합 |
| [#144](https://github.com/bongbong90/Sorigul/pull/144) | fix: restore TXT display encoding fallback | [파일·patch·검증·주의점](./05-parity-restoration-and-security.md#pr-144) | CLOSED / 미병합 |
| [#145](https://github.com/bongbong90/Sorigul/pull/145) | fix: resolve build taskkill by trusted path | [파일·patch·검증·주의점](./05-parity-restoration-and-security.md#pr-145) | CLOSED / 미병합 |
| [#146](https://github.com/bongbong90/Sorigul/pull/146) | test: make Job Object kill-on-close checks deterministic | [파일·patch·검증·주의점](./06-release-governance-and-early-main-candidates.md#pr-146) | CLOSED / 미병합 |
| [#148](https://github.com/bongbong90/Sorigul/pull/148) | docs: lock #127 parity decisions | [파일·patch·검증·주의점](./06-release-governance-and-early-main-candidates.md#pr-148) | CLOSED / 미병합 |
| [#149](https://github.com/bongbong90/Sorigul/pull/149) | audit: re-run full source contract regression | [파일·patch·검증·주의점](./06-release-governance-and-early-main-candidates.md#pr-149) | CLOSED / 미병합 |
| [#152](https://github.com/bongbong90/Sorigul/pull/152) | docs: classify #123 rerun report | [파일·patch·검증·주의점](./06-release-governance-and-early-main-candidates.md#pr-152) | CLOSED / 미병합 |
| [#153](https://github.com/bongbong90/Sorigul/pull/153) | fix: restore packaged Local Runtime CUDA self-test | [파일·patch·검증·주의점](./06-release-governance-and-early-main-candidates.md#pr-153) | CLOSED / 미병합 |
| [#155](https://github.com/bongbong90/Sorigul/pull/155) | test: validate fresh current-head installed artifact | [파일·patch·검증·주의점](./06-release-governance-and-early-main-candidates.md#pr-155) | CLOSED / 미병합 |
| [#157](https://github.com/bongbong90/Sorigul/pull/157) | docs: classify 6A-R3 blocked validation report | [파일·patch·검증·주의점](./06-release-governance-and-early-main-candidates.md#pr-157) | CLOSED / 미병합 |
| [#158](https://github.com/bongbong90/Sorigul/pull/158) | test: lock split-runtime manifest gate | [파일·patch·검증·주의점](./06-release-governance-and-early-main-candidates.md#pr-158) | CLOSED / 미병합 |
| [#160](https://github.com/bongbong90/Sorigul/pull/160) | test: lock Core self-test process observation on PowerShell 5 | [파일·patch·검증·주의점](./06-release-governance-and-early-main-candidates.md#pr-160) | CLOSED / 미병합 |
| [#162](https://github.com/bongbong90/Sorigul/pull/162) | integrate: consolidate Study-Use release candidate through #161 | [파일·patch·검증·주의점](./06-release-governance-and-early-main-candidates.md#pr-162) | CLOSED / 미병합 |
| [#163](https://github.com/bongbong90/Sorigul/pull/163) | integrate: consolidate Study-Use candidate with canonical #113 preflight | [파일·patch·검증·주의점](./07-native-ux-and-session-guards.md#pr-163) | CLOSED / 미병합 |
| [#165](https://github.com/bongbong90/Sorigul/pull/165) | fix: canonical #113 session bootstrap and Single Writer guard (#164) | [파일·patch·검증·주의점](./07-native-ux-and-session-guards.md#pr-165) | CLOSED / 미병합 |
| [#166](https://github.com/bongbong90/Sorigul/pull/166) | integrate: Study-Use candidate with canonical session bootstrap (#164) | [파일·patch·검증·주의점](./07-native-ux-and-session-guards.md#pr-166) | CLOSED / 미병합 |
| [#175](https://github.com/bongbong90/Sorigul/pull/175) | [#167] Emit Local worker stdout protocol as UTF-8 bytes | [파일·patch·검증·주의점](./07-native-ux-and-session-guards.md#pr-175) | CLOSED / 미병합 |
| [#176](https://github.com/bongbong90/Sorigul/pull/176) | [#172] Honor forced re-transcription intent on Retry | [파일·patch·검증·주의점](./07-native-ux-and-session-guards.md#pr-176) | CLOSED / 미병합 |
| [#177](https://github.com/bongbong90/Sorigul/pull/177) | fix: reconcile folder picker immediately and reject stale scans (#170) | [파일·patch·검증·주의점](./07-native-ux-and-session-guards.md#pr-177) | CLOSED / 미병합 |
| [#178](https://github.com/bongbong90/Sorigul/pull/178) | fix: consume confirmations before transcription preflight (#171) | [파일·patch·검증·주의점](./07-native-ux-and-session-guards.md#pr-178) | CLOSED / 미병합 |
| [#179](https://github.com/bongbong90/Sorigul/pull/179) | fix: app-lifetime tray progress observer (#173) | [파일·patch·검증·주의점](./07-native-ux-and-session-guards.md#pr-179) | CLOSED / 미병합 |
| [#181](https://github.com/bongbong90/Sorigul/pull/181) | fix: focus existing desktop instance on second launch (#168) | [파일·patch·검증·주의점](./07-native-ux-and-session-guards.md#pr-181) | CLOSED / 미병합 |
| [#182](https://github.com/bongbong90/Sorigul/pull/182) | fix: guard tray Exit with the active-work close check (#174) | [파일·patch·검증·주의점](./07-native-ux-and-session-guards.md#pr-182) | CLOSED / 미병합 |
| [#183](https://github.com/bongbong90/Sorigul/pull/183) | feat: manual week input + Eduwill no-week normalization (#180) | [파일·patch·검증·주의점](./08-final-stabilization-threads.md#pr-183) | CLOSED / 미병합 |
| [#186](https://github.com/bongbong90/Sorigul/pull/186) | docs: reconcile final Study-Use pre-freeze contract (#184) | [파일·patch·검증·주의점](./08-final-stabilization-threads.md#pr-186) | CLOSED / 미병합 |
| [#187](https://github.com/bongbong90/Sorigul/pull/187) | audit: final #123 source regression and classification closure | [파일·patch·검증·주의점](./08-final-stabilization-threads.md#pr-187) | CLOSED / 미병합 |
| [#188](https://github.com/bongbong90/Sorigul/pull/188) | fix: harden #113 heartbeat reads against replace race (#164) | [파일·patch·검증·주의점](./08-final-stabilization-threads.md#pr-188) | CLOSED / 미병합 |

## 정확성 및 한계

- 74/74 PR 개별 섹션, 원본 변경파일 및 patch 앵커 확인. `pr-inventory.json`에 원래 base/head, 전체 수정파일 목록 및 GitHub 제공 추가/삭제 통계를 보존했다.
- 명시된 Issue 번호는 **제목/원본 PR 본문에 등장한 참조**로서 모든 번호가 직접 해결한 이슈임을 뜻하지 않는다. 관련성은 해당 Issue/PR 본문에서 다시 확인해야 한다.
- 본문 내 PASS/FAIL 문구는 **과거 PR 작성자 기록의 흔적**이며 이번 감사에서 테스트를 재실행한 것이 아니다. 본문에 검증 수치가 없으면 미확인으로 표기했다.
- 새 릴리스 게이트 #123/#191/#47/#114는 여전히 독립적으로 완료해야 한다. 원본 GitHub PR의 직접 MERGED 여부를 조작하거나 역사를 다시 쓰지 않았다.
- 감사 변경은 이 디렉터리의 문서/JSON만이며, **제품 코드, Freeze, 설치본, 기본 Runtime, `main` 변경 없음**. 리뷰 후 Integration 반영 시 추가 Source HEAD 변화와 Freeze 재검증 영향을 의식해야 한다.

Refs [#203](https://github.com/bongbong90/Sorigul/issues/203), [#7](https://github.com/bongbong90/Sorigul/issues/7), [#185](https://github.com/bongbong90/Sorigul/pull/185).