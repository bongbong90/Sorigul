# Sorigul 전체 커밋·PR·브랜치 통합 대조 (2026-10-15)

> 범위: GitHub에 존재하는 Sorigul 원격 커밋·PR·브랜치. **실제 실행/설치/회귀 PASS를 선언하는 문서가 아니다.** 개인 사용자 파일, 인증정보, 토큰, MP3, 앱 설치본을 읽거나 변경하지 않았다.

## 1. 판정 요약

| 항목 | 수량 | 의미 |
|---|---:|---|
| GitHub 전체 PR | 89 | MERGED 13 / CLOSED-but-unmerged 74 / OPEN 2 |
| `integration/study-use-final-candidate`에서 도달 가능한 전체 Git 커밋 | **153** | GitHub commits API 페이지 1(100개), 2(53개), 3(0개) |
| 대표 PR의 커밋 포함 | **151 / 153** | #1의 2개 + #6의 71개 + #185의 78개. SHA 중복 없이 합계 151개 |
| 대표 PR 목록에 직접 속하지 않는 커밋 | **2** | 저장소 최초 생성 커밋과 GitHub PR #1 병합 커밋. 둘 다 정상적인 저장소 관리 이력 |
| CLOSED-but-unmerged PR 원본 head | **74 / 74** | 해당 SHA를 `38b856a0dfe18448005a59bf7bb36479f3cd2692`와 직접 compare; behind=0, SHA 일치 전수 확인 |
| 원격 브랜치 | **91** | 과거 작업 브랜치 88개 모두 Integration 조상; 나머지 Integration, main, 독립 감사 브랜치 |
| 역사적 미병합 PR 수정 파일 발생 건수 | **842** | [pr-inventory.json](./pr-inventory.json)에 경로·상태·추가/삭제 수 포함 |
| `main`과 Integration 비교 | **Integration ahead 78 / behind 1** | GitHub compare는 diverged. `main`에서만 존재하는 과거 PR #6의 별도 merge commit 때문에 graph가 단순 fast-forward가 아님 |

### 커밋 2건의 정당한 예외

- [`032f94952e6663d63b4ba210e452c93d02dff1dd`](https://github.com/bongbong90/Sorigul/commit/032f94952e6663d63b4ba210e452c93d02dff1dd): Merge pull request #1 from bongbong90/chore/project-foundation
- [`3b54e1461b86a29c7decfc8d8d70378f5e04b58e`](https://github.com/bongbong90/Sorigul/commit/3b54e1461b86a29c7decfc8d8d70378f5e04b58e): chore: initialize Sorigul repository

위 예외는 기능을 개발했지만 PR을 누락한 커밋이 아니다. 저장소 생성 또는 기존 승인 PR의 GitHub merge commit이므로 임의의 신규 PR을 만들지 않는다.

## 2. 실제 GitHub 반영과 PR 상태를 혼동하지 않는다

- **MERGED 13건**은 해당 대상 브랜치로 GitHub가 정식 병합한 기록이다. 그중 #1/#6은 `main`, #2–#5는 중간 기능 브랜치, #190/#196/#197/#198/#200/#202는 Integration에 병합되었다. #72는 별도 `main` 반영 이력이 있다. 서로 다른 base를 하나로 취급하지 않는다.
- **CLOSED / NOT MERGED 74건**은 GitHub PR 자체를 병합하지 않은 것이다. 하지만 **원본 HEAD 74개가 모두 Integration의 조상임을 확인**했으므로 코드 재병합 대상이 아니다. 원본 PR이 포함됐다고 GitHub `MERGED`로 허위 표기하지 않는다.
- **OPEN #185**는 `integration/study-use-final-candidate` → `main`의 유일한 현행 제품 통합 PR이다. mergeable=true는 기술적 충돌 부재 신호일 뿐 실사용 릴리스 합격이 아니다. 현재 실제 설치 Core/Local Runtime pairing 및 #191, #47, #114 등 확인 필요.
- **OPEN #204**는 이 감사 기록을 검토하는 **Draft 문서 전용 PR**이다. Integration 소스/릴리스 HEAD 및 Freeze가 확정되어 있으므로 현재 이 문서 변경을 Integration에 바로 병합하지 않는다.

### 현재 병합 판단

| 대상 | 결정 | 이유 |
|---|---|---|
| CLOSED 74개 원본 PR | **재병합하지 않음** | 원본 HEAD 74/74가 Integration 조상. 재개/rebase/cherry-pick으로 과거 동작 재도입·중복 위험 |
| MERGED 13개 원본 PR | **추가 조치 없음** | 이미 GitHub에 병합 기록 있음 |
| PR #185 | **OPEN 유지 / 지금 main 병합 금지** | #123 source regression PASS와 실사용 #191/#47/#114 PASS는 다름. fresh installed evidence와 최종 사용자 acceptance 필요 |
| PR #204 | **DRAFT 유지 / Integration 병합 보류** | 감사 문서 변경도 HEAD를 바꿔 현재 source/Freeze의 provenance 계약에 영향; 검증 완료 후 승인된 별도 창에서 처리 |
| 신규 기능 PR | **추가 생성 없음** | 조회한 91개 원격 브랜치·153개 reachable 커밋 기준 별도 누락 기능 HEAD 없음. 감사 기록 보강은 기존 PR #204에 커밋 |

**중요한 범위 제한:** 원격 GitHub 이력은 전수 대조했지만 개인 Windows PC의 아직 commit/push하지 않은 로컬 변경·untracked 파일까지 확인한 것은 아니다. Windows fresh build, Local/Colab 전사, 실제 Drive API, 사용자 설정, MSI install/uninstall은 실행하지 않았다.

## 3. 전체 89개 PR 상태 원장

| PR | GitHub 상태 | 제목 | 상세 이력 |
|---|---|---|---|
| [#1](https://github.com/bongbong90/Sorigul/pull/1) | MERGED | chore: establish Sorigul project foundation | [원본 PR](https://github.com/bongbong90/Sorigul/pull/1) |
| [#2](https://github.com/bongbong90/Sorigul/pull/2) | MERGED | feat: integrate Tauri desktop runtime and OS features | [원본 PR](https://github.com/bongbong90/Sorigul/pull/2) |
| [#3](https://github.com/bongbong90/Sorigul/pull/3) | MERGED | fix: close Tauri desktop runtime smoke gaps | [원본 PR](https://github.com/bongbong90/Sorigul/pull/3) |
| [#4](https://github.com/bongbong90/Sorigul/pull/4) | MERGED | fix: apply Sorigul Windows app branding | [원본 PR](https://github.com/bongbong90/Sorigul/pull/4) |
| [#5](https://github.com/bongbong90/Sorigul/pull/5) | MERGED | feat: package and harden Sorigul Windows installer | [원본 PR](https://github.com/bongbong90/Sorigul/pull/5) |
| [#6](https://github.com/bongbong90/Sorigul/pull/6) | MERGED | feat: Sorigul core workflow refinement and release validation | [원본 PR](https://github.com/bongbong90/Sorigul/pull/6) |
| [#67](https://github.com/bongbong90/Sorigul/pull/67) | CLOSED / NOT MERGED | Package A: harden release packaging gates | [개별 기록](./01-foundation-and-hardening.md#pr-67) |
| [#68](https://github.com/bongbong90/Sorigul/pull/68) | CLOSED / NOT MERGED | Package B: harden process and recovery boundaries | [개별 기록](./01-foundation-and-hardening.md#pr-68) |
| [#69](https://github.com/bongbong90/Sorigul/pull/69) | CLOSED / NOT MERGED | Package C: secure Colab and OAuth boundaries | [개별 기록](./01-foundation-and-hardening.md#pr-69) |
| [#70](https://github.com/bongbong90/Sorigul/pull/70) | CLOSED / NOT MERGED | Package D: harden frontend and filesystem UX integrity | [개별 기록](./01-foundation-and-hardening.md#pr-70) |
| [#71](https://github.com/bongbong90/Sorigul/pull/71) | CLOSED / NOT MERGED | Package E: close pre-build release validation contracts | [개별 기록](./01-foundation-and-hardening.md#pr-71) |
| [#72](https://github.com/bongbong90/Sorigul/pull/72) | MERGED | Frontend foundation: bootstrap Vite React TypeScript | [원본 PR](https://github.com/bongbong90/Sorigul/pull/72) |
| [#73](https://github.com/bongbong90/Sorigul/pull/73) | CLOSED / NOT MERGED | Design system foundation | [개별 기록](./01-foundation-and-hardening.md#pr-73) |
| [#74](https://github.com/bongbong90/Sorigul/pull/74) | CLOSED / NOT MERGED | App shell implementation | [개별 기록](./01-foundation-and-hardening.md#pr-74) |
| [#75](https://github.com/bongbong90/Sorigul/pull/75) | CLOSED / NOT MERGED | Transcription screen static UI | [개별 기록](./01-foundation-and-hardening.md#pr-75) |
| [#76](https://github.com/bongbong90/Sorigul/pull/76) | CLOSED / NOT MERGED | Transcription screen mock interactions | [개별 기록](./01-foundation-and-hardening.md#pr-76) |
| [#77](https://github.com/bongbong90/Sorigul/pull/77) | CLOSED / NOT MERGED | Legacy feature parity audit | [개별 기록](./01-foundation-and-hardening.md#pr-77) |
| [#78](https://github.com/bongbong90/Sorigul/pull/78) | CLOSED / NOT MERGED | Migration contract review and lock | [개별 기록](./02-migration-and-ui-freeze.md#pr-78) |
| [#79](https://github.com/bongbong90/Sorigul/pull/79) | CLOSED / NOT MERGED | Sync project baseline to migration contract | [개별 기록](./02-migration-and-ui-freeze.md#pr-79) |
| [#80](https://github.com/bongbong90/Sorigul/pull/80) | CLOSED / NOT MERGED | Close migration-contract UI gaps | [개별 기록](./02-migration-and-ui-freeze.md#pr-80) |
| [#81](https://github.com/bongbong90/Sorigul/pull/81) | CLOSED / NOT MERGED | Validate UI state and UX for freeze | [개별 기록](./02-migration-and-ui-freeze.md#pr-81) |
| [#82](https://github.com/bongbong90/Sorigul/pull/82) | CLOSED / NOT MERGED | Freeze Sorigul UI v1 | [개별 기록](./02-migration-and-ui-freeze.md#pr-82) |
| [#83](https://github.com/bongbong90/Sorigul/pull/83) | CLOSED / NOT MERGED | Migrate core backend file and job foundation | [개별 기록](./02-migration-and-ui-freeze.md#pr-83) |
| [#84](https://github.com/bongbong90/Sorigul/pull/84) | CLOSED / NOT MERGED | Migrate transcription engines | [개별 기록](./02-migration-and-ui-freeze.md#pr-84) |
| [#85](https://github.com/bongbong90/Sorigul/pull/85) | CLOSED / NOT MERGED | Migrate Drive results and desktop UX | [개별 기록](./02-migration-and-ui-freeze.md#pr-85) |
| [#86](https://github.com/bongbong90/Sorigul/pull/86) | CLOSED / NOT MERGED | Integrate Tauri desktop runtime and sidecar | [개별 기록](./02-migration-and-ui-freeze.md#pr-86) |
| [#87](https://github.com/bongbong90/Sorigul/pull/87) | CLOSED / NOT MERGED | Full feature parity release validation | [개별 기록](./02-migration-and-ui-freeze.md#pr-87) |
| [#88](https://github.com/bongbong90/Sorigul/pull/88) | CLOSED / NOT MERGED | Core workflow refinement plan | [개별 기록](./03-core-workflow-and-provenance.md#pr-88) |
| [#89](https://github.com/bongbong90/Sorigul/pull/89) | CLOSED / NOT MERGED | Core workflow Phase 1: classification and normalization | [개별 기록](./03-core-workflow-and-provenance.md#pr-89) |
| [#90](https://github.com/bongbong90/Sorigul/pull/90) | CLOSED / NOT MERGED | Core workflow Phase 2: Google Drive refinement | [개별 기록](./03-core-workflow-and-provenance.md#pr-90) |
| [#91](https://github.com/bongbong90/Sorigul/pull/91) | CLOSED / NOT MERGED | Core workflow Phase 3A: audio metadata and URL normalization | [개별 기록](./03-core-workflow-and-provenance.md#pr-91) |
| [#92](https://github.com/bongbong90/Sorigul/pull/92) | CLOSED / NOT MERGED | Core workflow Phase 3B: Colab rendezvous and integration | [개별 기록](./03-core-workflow-and-provenance.md#pr-92) |
| [#93](https://github.com/bongbong90/Sorigul/pull/93) | CLOSED / NOT MERGED | Core workflow Phase 4: honest duration, progress and ETA | [개별 기록](./03-core-workflow-and-provenance.md#pr-93) |
| [#94](https://github.com/bongbong90/Sorigul/pull/94) | CLOSED / NOT MERGED | Core workflow Phase 5A: release regression suite | [개별 기록](./03-core-workflow-and-provenance.md#pr-94) |
| [#95](https://github.com/bongbong90/Sorigul/pull/95) | CLOSED / NOT MERGED | Core workflow Phase 5B: installed build validation record | [개별 기록](./03-core-workflow-and-provenance.md#pr-95) |
| [#96](https://github.com/bongbong90/Sorigul/pull/96) | CLOSED / NOT MERGED | CUDA release remediation | [개별 기록](./03-core-workflow-and-provenance.md#pr-96) |
| [#98](https://github.com/bongbong90/Sorigul/pull/98) | CLOSED / NOT MERGED | fix: enforce scalar release manifest provenance | [개별 기록](./03-core-workflow-and-provenance.md#pr-98) |
| [#100](https://github.com/bongbong90/Sorigul/pull/100) | CLOSED / NOT MERGED | refactor: split Local Whisper runtime from Core | [개별 기록](./04-runtime-and-legacy-parity.md#pr-100) |
| [#102](https://github.com/bongbong90/Sorigul/pull/102) | CLOSED / NOT MERGED | fix: harden Local Runtime pre-build provenance | [개별 기록](./04-runtime-and-legacy-parity.md#pr-102) |
| [#103](https://github.com/bongbong90/Sorigul/pull/103) | CLOSED / NOT MERGED | test: validate split runtime installed synthetic gate | [개별 기록](./04-runtime-and-legacy-parity.md#pr-103) |
| [#105](https://github.com/bongbong90/Sorigul/pull/105) | CLOSED / NOT MERGED | test: validate Local CUDA with Korean real-speech fixtures | [개별 기록](./04-runtime-and-legacy-parity.md#pr-105) |
| [#115](https://github.com/bongbong90/Sorigul/pull/115) | CLOSED / NOT MERGED | docs: rebaseline full Legacy parity completion plan (planning/checkpoint only) | [개별 기록](./04-runtime-and-legacy-parity.md#pr-115) |
| [#117](https://github.com/bongbong90/Sorigul/pull/117) | CLOSED / NOT MERGED | docs: lock development governance and current product contract | [개별 기록](./04-runtime-and-legacy-parity.md#pr-117) |
| [#119](https://github.com/bongbong90/Sorigul/pull/119) | CLOSED / NOT MERGED | fix: restore Local and Colab transcription engine parity | [개별 기록](./04-runtime-and-legacy-parity.md#pr-119) |
| [#120](https://github.com/bongbong90/Sorigul/pull/120) | CLOSED / NOT MERGED | feat: restore actionable completion notification | [개별 기록](./04-runtime-and-legacy-parity.md#pr-120) |
| [#121](https://github.com/bongbong90/Sorigul/pull/121) | CLOSED / NOT MERGED | feat: restore live transcription-folder change detection | [개별 기록](./04-runtime-and-legacy-parity.md#pr-121) |
| [#129](https://github.com/bongbong90/Sorigul/pull/129) | CLOSED / NOT MERGED | docs: validate full Legacy and current-contract source regression | [개별 기록](./04-runtime-and-legacy-parity.md#pr-129) |
| [#134](https://github.com/bongbong90/Sorigul/pull/134) | CLOSED / NOT MERGED | fix: restore Legacy week and lesson allocation | [개별 기록](./05-parity-restoration-and-security.md#pr-134) |
| [#135](https://github.com/bongbong90/Sorigul/pull/135) | CLOSED / NOT MERGED | fix: resolve Windows system utilities by trusted paths | [개별 기록](./05-parity-restoration-and-security.md#pr-135) |
| [#137](https://github.com/bongbong90/Sorigul/pull/137) | CLOSED / NOT MERGED | fix: reject untrusted loopback Host headers | [개별 기록](./05-parity-restoration-and-security.md#pr-137) |
| [#139](https://github.com/bongbong90/Sorigul/pull/139) | CLOSED / NOT MERGED | fix: enforce one global transcription run | [개별 기록](./05-parity-restoration-and-security.md#pr-139) |
| [#140](https://github.com/bongbong90/Sorigul/pull/140) | CLOSED / NOT MERGED | fix: protect active work from window close | [개별 기록](./05-parity-restoration-and-security.md#pr-140) |
| [#141](https://github.com/bongbong90/Sorigul/pull/141) | CLOSED / NOT MERGED | feat: restore Colab open convenience | [개별 기록](./05-parity-restoration-and-security.md#pr-141) |
| [#142](https://github.com/bongbong90/Sorigul/pull/142) | CLOSED / NOT MERGED | feat: restore honest tray progress tooltip | [개별 기록](./05-parity-restoration-and-security.md#pr-142) |
| [#143](https://github.com/bongbong90/Sorigul/pull/143) | CLOSED / NOT MERGED | feat: restore Folders column sorting | [개별 기록](./05-parity-restoration-and-security.md#pr-143) |
| [#144](https://github.com/bongbong90/Sorigul/pull/144) | CLOSED / NOT MERGED | fix: restore TXT display encoding fallback | [개별 기록](./05-parity-restoration-and-security.md#pr-144) |
| [#145](https://github.com/bongbong90/Sorigul/pull/145) | CLOSED / NOT MERGED | fix: resolve build taskkill by trusted path | [개별 기록](./05-parity-restoration-and-security.md#pr-145) |
| [#146](https://github.com/bongbong90/Sorigul/pull/146) | CLOSED / NOT MERGED | test: make Job Object kill-on-close checks deterministic | [개별 기록](./06-release-governance-and-early-main-candidates.md#pr-146) |
| [#148](https://github.com/bongbong90/Sorigul/pull/148) | CLOSED / NOT MERGED | docs: lock #127 parity decisions | [개별 기록](./06-release-governance-and-early-main-candidates.md#pr-148) |
| [#149](https://github.com/bongbong90/Sorigul/pull/149) | CLOSED / NOT MERGED | audit: re-run full source contract regression | [개별 기록](./06-release-governance-and-early-main-candidates.md#pr-149) |
| [#152](https://github.com/bongbong90/Sorigul/pull/152) | CLOSED / NOT MERGED | docs: classify #123 rerun report | [개별 기록](./06-release-governance-and-early-main-candidates.md#pr-152) |
| [#153](https://github.com/bongbong90/Sorigul/pull/153) | CLOSED / NOT MERGED | fix: restore packaged Local Runtime CUDA self-test | [개별 기록](./06-release-governance-and-early-main-candidates.md#pr-153) |
| [#155](https://github.com/bongbong90/Sorigul/pull/155) | CLOSED / NOT MERGED | test: validate fresh current-head installed artifact | [개별 기록](./06-release-governance-and-early-main-candidates.md#pr-155) |
| [#157](https://github.com/bongbong90/Sorigul/pull/157) | CLOSED / NOT MERGED | docs: classify 6A-R3 blocked validation report | [개별 기록](./06-release-governance-and-early-main-candidates.md#pr-157) |
| [#158](https://github.com/bongbong90/Sorigul/pull/158) | CLOSED / NOT MERGED | test: lock split-runtime manifest gate | [개별 기록](./06-release-governance-and-early-main-candidates.md#pr-158) |
| [#160](https://github.com/bongbong90/Sorigul/pull/160) | CLOSED / NOT MERGED | test: lock Core self-test process observation on PowerShell 5 | [개별 기록](./06-release-governance-and-early-main-candidates.md#pr-160) |
| [#162](https://github.com/bongbong90/Sorigul/pull/162) | CLOSED / NOT MERGED | integrate: consolidate Study-Use release candidate through #161 | [개별 기록](./06-release-governance-and-early-main-candidates.md#pr-162) |
| [#163](https://github.com/bongbong90/Sorigul/pull/163) | CLOSED / NOT MERGED | integrate: consolidate Study-Use candidate with canonical #113 preflight | [개별 기록](./07-native-ux-and-session-guards.md#pr-163) |
| [#165](https://github.com/bongbong90/Sorigul/pull/165) | CLOSED / NOT MERGED | fix: canonical #113 session bootstrap and Single Writer guard (#164) | [개별 기록](./07-native-ux-and-session-guards.md#pr-165) |
| [#166](https://github.com/bongbong90/Sorigul/pull/166) | CLOSED / NOT MERGED | integrate: Study-Use candidate with canonical session bootstrap (#164) | [개별 기록](./07-native-ux-and-session-guards.md#pr-166) |
| [#175](https://github.com/bongbong90/Sorigul/pull/175) | CLOSED / NOT MERGED | [#167] Emit Local worker stdout protocol as UTF-8 bytes | [개별 기록](./07-native-ux-and-session-guards.md#pr-175) |
| [#176](https://github.com/bongbong90/Sorigul/pull/176) | CLOSED / NOT MERGED | [#172] Honor forced re-transcription intent on Retry | [개별 기록](./07-native-ux-and-session-guards.md#pr-176) |
| [#177](https://github.com/bongbong90/Sorigul/pull/177) | CLOSED / NOT MERGED | fix: reconcile folder picker immediately and reject stale scans (#170) | [개별 기록](./07-native-ux-and-session-guards.md#pr-177) |
| [#178](https://github.com/bongbong90/Sorigul/pull/178) | CLOSED / NOT MERGED | fix: consume confirmations before transcription preflight (#171) | [개별 기록](./07-native-ux-and-session-guards.md#pr-178) |
| [#179](https://github.com/bongbong90/Sorigul/pull/179) | CLOSED / NOT MERGED | fix: app-lifetime tray progress observer (#173) | [개별 기록](./07-native-ux-and-session-guards.md#pr-179) |
| [#181](https://github.com/bongbong90/Sorigul/pull/181) | CLOSED / NOT MERGED | fix: focus existing desktop instance on second launch (#168) | [개별 기록](./07-native-ux-and-session-guards.md#pr-181) |
| [#182](https://github.com/bongbong90/Sorigul/pull/182) | CLOSED / NOT MERGED | fix: guard tray Exit with the active-work close check (#174) | [개별 기록](./07-native-ux-and-session-guards.md#pr-182) |
| [#183](https://github.com/bongbong90/Sorigul/pull/183) | CLOSED / NOT MERGED | feat: manual week input + Eduwill no-week normalization (#180) | [개별 기록](./08-final-stabilization-threads.md#pr-183) |
| [#185](https://github.com/bongbong90/Sorigul/pull/185) | OPEN | integrate: final Study-Use candidate through #202 (main release gates pending) | [원본 PR](https://github.com/bongbong90/Sorigul/pull/185) |
| [#186](https://github.com/bongbong90/Sorigul/pull/186) | CLOSED / NOT MERGED | docs: reconcile final Study-Use pre-freeze contract (#184) | [개별 기록](./08-final-stabilization-threads.md#pr-186) |
| [#187](https://github.com/bongbong90/Sorigul/pull/187) | CLOSED / NOT MERGED | audit: final #123 source regression and classification closure | [개별 기록](./08-final-stabilization-threads.md#pr-187) |
| [#188](https://github.com/bongbong90/Sorigul/pull/188) | CLOSED / NOT MERGED | fix: harden #113 heartbeat reads against replace race (#164) | [개별 기록](./08-final-stabilization-threads.md#pr-188) |
| [#190](https://github.com/bongbong90/Sorigul/pull/190) | MERGED | fix: classify protected WebView directory mtime differences (#189) | [원본 PR](https://github.com/bongbong90/Sorigul/pull/190) |
| [#196](https://github.com/bongbong90/Sorigul/pull/196) | MERGED | #192 공인중개사법/중개사법 파일명·Drive 분류 일치 | [원본 PR](https://github.com/bongbong90/Sorigul/pull/196) |
| [#197](https://github.com/bongbong90/Sorigul/pull/197) | MERGED | #193/#194 전사 단일 스크롤·헤더 작업 버튼·연결 설정 통합 | [원본 PR](https://github.com/bongbong90/Sorigul/pull/197) |
| [#198](https://github.com/bongbong90/Sorigul/pull/198) | MERGED | #195 신규 프로필 유휴 X 종료 기본값과 기존 Tray 설정 보존 | [원본 PR](https://github.com/bongbong90/Sorigul/pull/198) |
| [#200](https://github.com/bongbong90/Sorigul/pull/200) | MERGED | #199 Classify source-validation reports as historical evidence | [원본 PR](https://github.com/bongbong90/Sorigul/pull/200) |
| [#202](https://github.com/bongbong90/Sorigul/pull/202) | MERGED | [#201] QA 예제 Rust fmt 최소 수정 | [원본 PR](https://github.com/bongbong90/Sorigul/pull/202) |
| [#204](https://github.com/bongbong90/Sorigul/pull/204) | OPEN | audit: preserve all 74 closed PR histories and 842 changed-file trace entries | [원본 PR](https://github.com/bongbong90/Sorigul/pull/204) |

## 4. Integration에서 도달 가능한 전체 153개 Git commit 원장

GitHub commit 목록의 원본 SHA·작성된 commit subject를 시간 순서(오래된 것부터)로 보존한다. 각 줄의 `#1/#6/#185`는 해당 커밋을 포함하는 대표 PR을 뜻하며 개별 Closed PR의 GitHub 병합 여부를 뜻하지 않는다. 개별 변경 파일/테스트 근거는 위 74개 감사 문서 및 원본 PR diff를 참고한다.

| # | 날짜(UTC) | Git commit | Git commit subject | 대표 PR |
|---:|---|---|---|---|
| 1 | 2026-08-08 | [`3b54e1461b`](https://github.com/bongbong90/Sorigul/commit/3b54e1461b86a29c7decfc8d8d70378f5e04b58e) | chore: initialize Sorigul repository | INIT |
| 2 | 2026-08-09 | [`37521c17cb`](https://github.com/bongbong90/Sorigul/commit/37521c17cb6438b3d23abeabde46aea0fce1f321) | chore: establish Sorigul project foundation | #1 |
| 3 | 2026-08-09 | [`e5d2bb3370`](https://github.com/bongbong90/Sorigul/commit/e5d2bb33706ee0e7883e5046917d5a4bd842851f) | docs: add Sorigul design system v1 | #1 |
| 4 | 2026-08-09 | [`032f94952e`](https://github.com/bongbong90/Sorigul/commit/032f94952e6663d63b4ba210e452c93d02dff1dd) | Merge pull request #1 from bongbong90/chore/project-foundation | MERGE #1 |
| 5 | 2026-08-09 | [`f13d040cda`](https://github.com/bongbong90/Sorigul/commit/f13d040cdaed1f195c6bdcb55878935b801e820a) | chore: bootstrap frontend with Vite React TypeScript foundation | #6 |
| 6 | 2026-08-25 | [`1ad6ffb54e`](https://github.com/bongbong90/Sorigul/commit/1ad6ffb54eabb9c689bab63554bd8bbae5a66546) | feat: establish Sorigul design system foundation | #6 |
| 7 | 2026-08-26 | [`daa37ef114`](https://github.com/bongbong90/Sorigul/commit/daa37ef11447e39e8211fad356193a13389caa97) | feat: implement Sorigul app shell | #6 |
| 8 | 2026-08-26 | [`5d66771b27`](https://github.com/bongbong90/Sorigul/commit/5d66771b276244ebea7d5a8cf3b481d0ae619389) | chore: ignore Visual Studio workspace files | #6 |
| 9 | 2026-08-26 | [`f37916df86`](https://github.com/bongbong90/Sorigul/commit/f37916df86e20a60287a133cc4802653b69434b6) | feat: implement transcription screen static UI | #6 |
| 10 | 2026-08-26 | [`154e550e6a`](https://github.com/bongbong90/Sorigul/commit/154e550e6aefd4dfecd5e0140d0ff1f69bf17f5c) | feat: implement transcription screen mock interactions | #6 |
| 11 | 2026-08-26 | [`b7cc7cbeb7`](https://github.com/bongbong90/Sorigul/commit/b7cc7cbeb78a8f96b231687f5615bfa0c0d94350) | docs: add legacy feature parity audit | #6 |
| 12 | 2026-08-27 | [`94d83d6a6b`](https://github.com/bongbong90/Sorigul/commit/94d83d6a6be50bde01e6bfa4410e58e16ead3119) | docs: lock migration contract | #6 |
| 13 | 2026-08-27 | [`93fcaa73ac`](https://github.com/bongbong90/Sorigul/commit/93fcaa73ace5011de4c00b005a3f3eec6384c15a) | docs: sync project baseline to migration contract | #6 |
| 14 | 2026-08-27 | [`9005f67596`](https://github.com/bongbong90/Sorigul/commit/9005f67596d26f9325c535a72bd10bb8c79c350c) | feat: close migration contract UI gaps | #6 |
| 15 | 2026-08-27 | [`89180a0aa5`](https://github.com/bongbong90/Sorigul/commit/89180a0aa5c68bfd115d5e564cf5af1cf12f0afc) | test: validate UI state and UX for freeze | #6 |
| 16 | 2026-08-27 | [`8b20a0836f`](https://github.com/bongbong90/Sorigul/commit/8b20a0836f82d7e4df55e28b1fef1f2fc8a4f0e7) | docs: freeze UI v1 | #6 |
| 17 | 2026-08-27 | [`a2d8b57793`](https://github.com/bongbong90/Sorigul/commit/a2d8b577939660cec634a8fba5eecda1b8eb9348) | feat: migrate core backend file and job foundation | #6 |
| 18 | 2026-08-28 | [`2821107539`](https://github.com/bongbong90/Sorigul/commit/28211075397156fa585ceea27889f3b19a4d1a3b) | feat: migrate transcription engines | #6 |
| 19 | 2026-08-28 | [`2c8b7e5615`](https://github.com/bongbong90/Sorigul/commit/2c8b7e561517963d54a744323075fabf5b4433a1) | feat: migrate drive results and desktop ux | #6 |
| 20 | 2026-08-28 | [`1f9aa64722`](https://github.com/bongbong90/Sorigul/commit/1f9aa647221589543f38ab6e5952d1ac06f04135) | feat: integrate tauri desktop runtime | #6 |
| 21 | 2026-08-28 | [`c665293676`](https://github.com/bongbong90/Sorigul/commit/c6652936768e35a86475181db48419235948f39e) | fix: close tauri desktop runtime smoke gaps | #6 |
| 22 | 2026-08-29 | [`e65dfa2b8d`](https://github.com/bongbong90/Sorigul/commit/e65dfa2b8dcc485faff198be27dc8283e1e1612c) | Merge pull request #3 from bongbong90/fix/tauri-runtime-smoke-closure | #6 |
| 23 | 2026-08-29 | [`2b69d08981`](https://github.com/bongbong90/Sorigul/commit/2b69d08981d7d72b54dbf7a72b8584cc69dba027) | fix: apply Sorigul Windows app branding | #6 |
| 24 | 2026-08-29 | [`7b6215ed11`](https://github.com/bongbong90/Sorigul/commit/7b6215ed119c23d9ea1ac5f749c923d2c50e3535) | fix: apply Sorigul Windows app branding | #6 |
| 25 | 2026-08-29 | [`8d0572ef00`](https://github.com/bongbong90/Sorigul/commit/8d0572ef00459b8a73b7c40f438fdd02b300f1b7) | Merge branch 'feature/tauri-runtime-sidecar-os-integration' into fix/windows-app-icon-branding | #6 |
| 26 | 2026-08-29 | [`b6af9cebc1`](https://github.com/bongbong90/Sorigul/commit/b6af9cebc14d5d913e7ece3c9798ca5b1a690af2) | Merge pull request #4 from bongbong90/fix/windows-app-icon-branding | #6 |
| 27 | 2026-08-29 | [`2b6cbb0a83`](https://github.com/bongbong90/Sorigul/commit/2b6cbb0a8304c1e9e8514a41b6f8568bf7c22ad1) | feat: package Sorigul Windows installer | #6 |
| 28 | 2026-08-29 | [`a1c64ebab1`](https://github.com/bongbong90/Sorigul/commit/a1c64ebab18b52801e152af22e0feaf2c5766a5f) | fix: harden installed Windows runtime | #6 |
| 29 | 2026-08-29 | [`63dda6fede`](https://github.com/bongbong90/Sorigul/commit/63dda6fede650db7a082d95ca599aa8d3c255380) | Merge pull request #5 from bongbong90/feature/installer-installed-runtime-validation | #6 |
| 30 | 2026-08-29 | [`d21ef855ae`](https://github.com/bongbong90/Sorigul/commit/d21ef855ae450212195df202c47432a6d778a57a) | Merge pull request #2 from bongbong90/feature/tauri-runtime-sidecar-os-integration | #6 |
| 31 | 2026-08-29 | [`728902ccf7`](https://github.com/bongbong90/Sorigul/commit/728902ccf7b2ddc837942051a3a9cd911e661c8d) | test: complete full feature parity release validation | #6 |
| 32 | 2026-08-29 | [`79f0794ad1`](https://github.com/bongbong90/Sorigul/commit/79f0794ad18f3b83abd2ab843a81812e99a34f47) | fix: harden final release packaging validation | #6 |
| 33 | 2026-08-29 | [`bbf793b56f`](https://github.com/bongbong90/Sorigul/commit/bbf793b56fa482f4c7342c3286fa3347316dff5c) | fix: correct active parity release matrix | #6 |
| 34 | 2026-08-29 | [`47aa500b54`](https://github.com/bongbong90/Sorigul/commit/47aa500b5453e42f186292b41d9b8054f96bc638) | fix: restore installed backend auto-start | #6 |
| 35 | 2026-08-29 | [`a1188653e6`](https://github.com/bongbong90/Sorigul/commit/a1188653e67a8a40e38c81918ab9fff13d476320) | docs: lock core workflow refinement plan | #6 |
| 36 | 2026-08-29 | [`1399faec2b`](https://github.com/bongbong90/Sorigul/commit/1399faec2b661acead4e36cb916c9276e9e0e24b) | docs: refine core workflow implementation plan | #6 |
| 37 | 2026-08-29 | [`1e5fa5b24a`](https://github.com/bongbong90/Sorigul/commit/1e5fa5b24aac8fb30e9536212991e5e1558c8510) | feat: add transcription classification metadata | #6 |
| 38 | 2026-08-29 | [`a599bcaf16`](https://github.com/bongbong90/Sorigul/commit/a599bcaf1668ec4b3155392d9f514f03b8bbfcce) | feat: simplify filename normalization | #6 |
| 39 | 2026-08-29 | [`932aab52b3`](https://github.com/bongbong90/Sorigul/commit/932aab52b33b298c7f7209bbd9493988e12962d8) | fix: preserve selection across filename rename | #6 |
| 40 | 2026-08-29 | [`5f235ab555`](https://github.com/bongbong90/Sorigul/commit/5f235ab555eda9720255522463fdd0afd1e27658) | feat: add transcription classification inputs | #6 |
| 41 | 2026-08-29 | [`05394c9dcc`](https://github.com/bongbong90/Sorigul/commit/05394c9dccf6c247f1edd06115572da4aa2be71e) | fix: close pre-job normalization flow | #6 |
| 42 | 2026-08-29 | [`ec8bd40a35`](https://github.com/bongbong90/Sorigul/commit/ec8bd40a35fed4c68d7aa7d35c4d04ceb2be3faf) | fix: harden classification and rename inputs | #6 |
| 43 | 2026-08-29 | [`ef5140403e`](https://github.com/bongbong90/Sorigul/commit/ef5140403e072909742ed2e34799eea631b61a4d) | fix: lock preflight targets before job creation | #6 |
| 44 | 2026-08-30 | [`cfeca3a49b`](https://github.com/bongbong90/Sorigul/commit/cfeca3a49b9807c99b831c65d08298b766536804) | fix: lock active preflight lifecycle | #6 |
| 45 | 2026-08-30 | [`14027aef13`](https://github.com/bongbong90/Sorigul/commit/14027aef136c28acc202efcefe947c97e55bae2e) | feat: Google Drive workflow refinement (Phase 2) | #6 |
| 46 | 2026-08-30 | [`128b5f0968`](https://github.com/bongbong90/Sorigul/commit/128b5f0968ffcf98c0cdfd9345605421f358046a) | fix: restore and complete Phase 2 Drive refinement | #6 |
| 47 | 2026-08-30 | [`bbc0df2f03`](https://github.com/bongbong90/Sorigul/commit/bbc0df2f0361c0ce016d8ce7bd52ecab93017058) | test: lock Phase 2 Google Drive contracts | #6 |
| 48 | 2026-08-30 | [`1010adfc99`](https://github.com/bongbong90/Sorigul/commit/1010adfc997f5a183cb2a28ed94f9b7248db2d5b) | feat: implement Phase 3A audio metadata fallback and URL normalization | #6 |
| 49 | 2026-08-30 | [`89a15decd6`](https://github.com/bongbong90/Sorigul/commit/89a15decd6f11dd67a2cf5bfa679d55d7852776f) | fix: harden Phase 3A runtime validation | #6 |
| 50 | 2026-08-30 | [`635f138be5`](https://github.com/bongbong90/Sorigul/commit/635f138be58454661f983b10f00d2983f236386d) | feat: add Google Drive Colab rendezvous | #6 |
| 51 | 2026-08-30 | [`1e51f28a0a`](https://github.com/bongbong90/Sorigul/commit/1e51f28a0a6baa12e681c79e16044b4aa0282e87) | feat: add Sorigul Colab bootstrap writer | #6 |
| 52 | 2026-08-30 | [`fc19a5b204`](https://github.com/bongbong90/Sorigul/commit/fc19a5b204c911e29969787fd21ca0f0216ab2d9) | feat: add Colab engine connection UI | #6 |
| 53 | 2026-09-05 | [`6ebb40fe53`](https://github.com/bongbong90/Sorigul/commit/6ebb40fe53e520e8df1369da93a120a90c5238f1) | fix: complete Phase 3B Colab integration | #6 |
| 54 | 2026-09-05 | [`6764ce1f8c`](https://github.com/bongbong90/Sorigul/commit/6764ce1f8cabe698b7549e80385766704b557589) | test: lock Phase 3B Colab contracts | #6 |
| 55 | 2026-09-05 | [`5c7ccd78b0`](https://github.com/bongbong90/Sorigul/commit/5c7ccd78b013863741370c36a7fc54cfec8366b3) | test: correct Phase 3B contract locks | #6 |
| 56 | 2026-09-05 | [`0e61f19242`](https://github.com/bongbong90/Sorigul/commit/0e61f19242fae173f19ec73f87ad084af4c70dd6) | test: finalize Phase 3B contract locks | #6 |
| 57 | 2026-09-05 | [`bb8d386307`](https://github.com/bongbong90/Sorigul/commit/bb8d386307bd6c816c0751ddc7cc0ab17cf27768) | feat: show real audio duration in queue | #6 |
| 58 | 2026-09-05 | [`31c9eb4475`](https://github.com/bongbong90/Sorigul/commit/31c9eb44758bb37929d5d8dada4be30a51ce3c3d) | feat: add honest Local elapsed time and ETA | #6 |
| 59 | 2026-09-05 | [`790ae597f9`](https://github.com/bongbong90/Sorigul/commit/790ae597f9984563d711fb8917c29d2cb4cc5614) | feat: add honest Colab progress and ETA | #6 |
| 60 | 2026-09-05 | [`e20c7a906c`](https://github.com/bongbong90/Sorigul/commit/e20c7a906c6049b25fbf6dd603fe9cd6aadf0874) | fix: use Job denominator for overall progress | #6 |
| 61 | 2026-09-05 | [`57b9d46825`](https://github.com/bongbong90/Sorigul/commit/57b9d468253515b7989932ee67b49d1ca7be4d0e) | test: add core workflow release regression suite | #6 |
| 62 | 2026-09-05 | [`9db695b6dc`](https://github.com/bongbong90/Sorigul/commit/9db695b6dcc9140086e42e1114c872aa32acf801) | docs: record Phase 5B installed build validation | #6 |
| 63 | 2026-09-05 | [`16dd25e8fc`](https://github.com/bongbong90/Sorigul/commit/16dd25e8fcade3afa5f49d16bc313873aea6857f) | fix: require CUDA runtime in Windows release packaging | #6 |
| 64 | 2026-09-05 | [`58348c408a`](https://github.com/bongbong90/Sorigul/commit/58348c408ad9a7bd380abcdb545aace5c67a95af) | fix: lock CUDA torch wheel variant | #6 |
| 65 | 2026-09-05 | [`dc2d08b588`](https://github.com/bongbong90/Sorigul/commit/dc2d08b5883e68960851c104b8ab8598bbf57f60) | fix: make CUDA preflight PowerShell-safe | #6 |
| 66 | 2026-09-25 | [`47a4e7037b`](https://github.com/bongbong90/Sorigul/commit/47a4e7037b8760338f759e2d0a5f056fae5f59e3) | fix:ffmpeg-path-resolution | #6 |
| 67 | 2026-09-25 | [`94a08f51fb`](https://github.com/bongbong90/Sorigul/commit/94a08f51fb5ee6f273fbb2ce5a38b7b557c5d75f) | fix: wait for packaged self-test completion | #6 |
| 68 | 2026-09-25 | [`3181b8f57d`](https://github.com/bongbong90/Sorigul/commit/3181b8f57d7825b2b412dc7b77966cce5d4773be) | fix: harden release packaging gates | #6 |
| 69 | 2026-09-25 | [`047632058c`](https://github.com/bongbong90/Sorigul/commit/047632058c00cc6334934944216845eeeba4ebf4) | fix: harden process and recovery boundaries | #6 |
| 70 | 2026-09-25 | [`57ac69e583`](https://github.com/bongbong90/Sorigul/commit/57ac69e58335f31545c2e778791e8f9f62ae0e68) | fix: make recovery state persistence-atomic | #6 |
| 71 | 2026-09-25 | [`a538a7dbf1`](https://github.com/bongbong90/Sorigul/commit/a538a7dbf15a8f50ec2ca9789b58019847c3d5b1) | fix:secure-colab-and-oauth-boundaries | #6 |
| 72 | 2026-09-25 | [`c393303924`](https://github.com/bongbong90/Sorigul/commit/c393303924f202d6c0045365331ed0a73a49479f) | fix: close package c pairing and token migration gaps | #6 |
| 73 | 2026-09-26 | [`3a6084cb7b`](https://github.com/bongbong90/Sorigul/commit/3a6084cb7b7170ec3132e1ba9edc70a58a8810d8) | fix: harden frontend and filesystem ux integrity | #6 |
| 74 | 2026-09-26 | [`9a26ef3690`](https://github.com/bongbong90/Sorigul/commit/9a26ef36904c0641ad279707bf60240a839314d1) | fix: recover colab ui after verify timeout | #6 |
| 75 | 2026-09-26 | [`e5a523e7e3`](https://github.com/bongbong90/Sorigul/commit/e5a523e7e3e5b19ab73d272bccfd59b6eeabec42) | chore: close pre-build release validation contracts | #6 |
| 76 | 2026-09-27 | [`22ebe3d281`](https://github.com/bongbong90/Sorigul/commit/22ebe3d28170386ab1a580ae2f3ed2f533f19269) | fix: enforce scalar release manifest provenance | #185 |
| 77 | 2026-09-28 | [`b34a7cd012`](https://github.com/bongbong90/Sorigul/commit/b34a7cd012403552b0e98376d39e7003e7e4cb2c) | refactor: split local whisper runtime from core | #185 |
| 78 | 2026-09-28 | [`d80a37b569`](https://github.com/bongbong90/Sorigul/commit/d80a37b569d0ccd27faf11fe9dbac7e486cc0ea1) | fix: harden local runtime pre-build provenance | #185 |
| 79 | 2026-09-28 | [`67fed29ffb`](https://github.com/bongbong90/Sorigul/commit/67fed29ffb5691a513f93beefb7ef00e4df3891f) | fix: accept PowerShell JSON integer widths | #185 |
| 80 | 2026-09-28 | [`10f369a15b`](https://github.com/bongbong90/Sorigul/commit/10f369a15bda49c2e3277a1ecac7aace432cd6e7) | test: validate split runtime installed synthetic gate | #185 |
| 81 | 2026-09-28 | [`81acb9dfbb`](https://github.com/bongbong90/Sorigul/commit/81acb9dfbb324719bd7780c432d5aec1da328aab) | test: validate Local CUDA with Korean real-speech fixtures | #185 |
| 82 | 2026-09-28 | [`c9df488757`](https://github.com/bongbong90/Sorigul/commit/c9df48875714dfdcdae87a1b4ca6de9a886966d5) | docs: rebaseline full legacy parity completion plan | #185 |
| 83 | 2026-09-28 | [`5d6b0fba22`](https://github.com/bongbong90/Sorigul/commit/5d6b0fba22c2d557a966557443608f4bbedba7ee) | docs: set November study-use delivery deadline | #185 |
| 84 | 2026-09-28 | [`80bc2f2cd2`](https://github.com/bongbong90/Sorigul/commit/80bc2f2cd2d95e66d52fddc6d091f89df8fa1180) | docs: lock October 31 study-use deadline | #185 |
| 85 | 2026-09-29 | [`c6079bab60`](https://github.com/bongbong90/Sorigul/commit/c6079bab60f67bd8034c821e139b95197be68743) | docs: enforce full GitHub development lifecycle | #185 |
| 86 | 2026-09-29 | [`3d35321c03`](https://github.com/bongbong90/Sorigul/commit/3d35321c03db8304b524909520a7398c6689f73a) | docs: establish canonical current product contract | #185 |
| 87 | 2026-09-29 | [`57e3300658`](https://github.com/bongbong90/Sorigul/commit/57e330065895ea44eed0f00e51a6ac0df0d5ff21) | fix: restore Local Whisper fp16 parity | #185 |
| 88 | 2026-09-29 | [`fc3baf6d03`](https://github.com/bongbong90/Sorigul/commit/fc3baf6d03ee4ebfa125fac5fae3953a0c7679e9) | fix: restore faster-whisper large-v3 Colab runtime | #185 |
| 89 | 2026-09-29 | [`2b36b4da5c`](https://github.com/bongbong90/Sorigul/commit/2b36b4da5c7e275ec5c5112d7d3ec45b8d932c52) | fix: align transcription engine user labels | #185 |
| 90 | 2026-09-29 | [`d95a5d9281`](https://github.com/bongbong90/Sorigul/commit/d95a5d9281b3144f209500f7ff193a4216703c76) | docs: restore zero-cost fail-closed assertion | #185 |
| 91 | 2026-09-29 | [`db89dac8d3`](https://github.com/bongbong90/Sorigul/commit/db89dac8d39bccd546099c0771de61dad16030c3) | feat: add secure notification folder intent | #185 |
| 92 | 2026-09-29 | [`a423ade363`](https://github.com/bongbong90/Sorigul/commit/a423ade363c6ac671862e7fbc706bc0c829874d6) | feat: restore actionable completion toast | #185 |
| 93 | 2026-09-29 | [`8f814bfab9`](https://github.com/bongbong90/Sorigul/commit/8f814bfab94fe1e60a3e0aa68f8a1976540495f6) | feat: add lightweight folder revision detection | #185 |
| 94 | 2026-09-29 | [`71d6920f2d`](https://github.com/bongbong90/Sorigul/commit/71d6920f2ded69868c877916af3095130099e838) | feat: live-refresh transcription and folders views | #185 |
| 95 | 2026-09-29 | [`2e41795619`](https://github.com/bongbong90/Sorigul/commit/2e4179561995dfa1910f75f6d509e8160bac732e) | docs: validate full source contract regression | #185 |
| 96 | 2026-09-29 | [`f61686e69c`](https://github.com/bongbong90/Sorigul/commit/f61686e69c47ab04a6cc8a708df40738ccb12369) | fix: restore Legacy filename lesson allocation | #185 |
| 97 | 2026-09-29 | [`4e9c9db74e`](https://github.com/bongbong90/Sorigul/commit/4e9c9db74eda0c8e53a6408d3f1f5003ad80c519) | fix: resolve backend Windows utilities by trusted paths | #185 |
| 98 | 2026-09-29 | [`05efaae352`](https://github.com/bongbong90/Sorigul/commit/05efaae352ac3d303d3cdd46a7e666782f93a9e9) | fix: resolve desktop Windows utilities by trusted paths | #185 |
| 99 | 2026-09-29 | [`24a4ecd04a`](https://github.com/bongbong90/Sorigul/commit/24a4ecd04aa286c24c2e5b304a0a6ef3e85958d6) | fix: reject untrusted loopback Host headers | #185 |
| 100 | 2026-09-29 | [`8f74d49a88`](https://github.com/bongbong90/Sorigul/commit/8f74d49a88f40372ff5bcf0f7cf8173a497b90ee) | fix: enforce one global transcription run | #185 |
| 101 | 2026-09-29 | [`07a642b701`](https://github.com/bongbong90/Sorigul/commit/07a642b70193b79aea10e30b037f68b68611bfc2) | fix: keep global active run visible | #185 |
| 102 | 2026-09-29 | [`9d44a15dba`](https://github.com/bongbong90/Sorigul/commit/9d44a15dba17b02c1bcd0979f8ab50b376102c4d) | feat: expose active-work close guard | #185 |
| 103 | 2026-09-29 | [`0c3266dd5d`](https://github.com/bongbong90/Sorigul/commit/0c3266dd5de21469878ffbf37119c8dcebe33798) | fix: protect active work from window close | #185 |
| 104 | 2026-09-30 | [`ef48a5a9a7`](https://github.com/bongbong90/Sorigul/commit/ef48a5a9a7dfe3663bf5c4af10489b5c1bc6c251) | feat: restore Colab open convenience | #185 |
| 105 | 2026-09-30 | [`10e56db92a`](https://github.com/bongbong90/Sorigul/commit/10e56db92a6ad5d02f5d77de8cb35a9f3c225707) | feat: add honest tray progress state | #185 |
| 106 | 2026-09-30 | [`c508e8a696`](https://github.com/bongbong90/Sorigul/commit/c508e8a6968068aa45dc6343222552cae567acfd) | feat: sync tray tooltip with active transcription | #185 |
| 107 | 2026-09-30 | [`ec06007e0b`](https://github.com/bongbong90/Sorigul/commit/ec06007e0bbbfbbe2d5a27da311186b0758d6359) | feat: restore Folders column sorting | #185 |
| 108 | 2026-09-30 | [`665fe8f73b`](https://github.com/bongbong90/Sorigul/commit/665fe8f73b545347bd24d92add85d66fbf242f92) | fix: restore TXT display encoding fallback | #185 |
| 109 | 2026-09-30 | [`6833396874`](https://github.com/bongbong90/Sorigul/commit/683339687462043d51ebc54e455eedcf3f546955) | fix: resolve build taskkill by trusted path | #185 |
| 110 | 2026-09-30 | [`e7996d8bbc`](https://github.com/bongbong90/Sorigul/commit/e7996d8bbc932c2b67b3a4ef9f70495bf2a0e6d0) | test: make Job Object kill-on-close checks deterministic | #185 |
| 111 | 2026-09-30 | [`90ed22e19b`](https://github.com/bongbong90/Sorigul/commit/90ed22e19bef41049f2dc0c4418a7368a7755e4a) | docs: lock #127 parity decisions | #185 |
| 112 | 2026-09-30 | [`c8c08b39d1`](https://github.com/bongbong90/Sorigul/commit/c8c08b39d1854f605d38a8b50660c89994431f6a) | audit: re-run full source contract regression | #185 |
| 113 | 2026-10-02 | [`141dec3871`](https://github.com/bongbong90/Sorigul/commit/141dec3871c9daf484fc6f3d41fcdfaa53a45f27) | docs: classify #123 rerun report | #185 |
| 114 | 2026-10-02 | [`0e202516c5`](https://github.com/bongbong90/Sorigul/commit/0e202516c5175e47126a81dae012bb6722c60fa8) | build: preserve Local Runtime self-test diagnostics | #185 |
| 115 | 2026-10-02 | [`d06a74def2`](https://github.com/bongbong90/Sorigul/commit/d06a74def23af7e8a571e3ed9a106cf0ab150f30) | fix: repair packaged Local Runtime CUDA self-test | #185 |
| 116 | 2026-10-02 | [`09bccc82b3`](https://github.com/bongbong90/Sorigul/commit/09bccc82b3d86a72986d6df0bfba32594c662b07) | test: record fresh current-head gate preflight blocker | #185 |
| 117 | 2026-10-03 | [`e52bd39a20`](https://github.com/bongbong90/Sorigul/commit/e52bd39a200b29310c81cf479d2020ef912af347) | docs: classify 6A-R3 blocked validation report | #185 |
| 118 | 2026-10-03 | [`40d721ebb2`](https://github.com/bongbong90/Sorigul/commit/40d721ebb287ec5a1eda60f77ac3f40c99813f37) | test: lock split-runtime manifest gate | #185 |
| 119 | 2026-10-03 | [`a33ac99ee4`](https://github.com/bongbong90/Sorigul/commit/a33ac99ee47c040692e0dd4cf0149795baa4e92a) | test: lock Core self-test process observation on PowerShell 5 | #185 |
| 120 | 2026-10-03 | [`4beebf8680`](https://github.com/bongbong90/Sorigul/commit/4beebf86800300b8af9e7cf5f1d0d9608c410e19) | fix: run nested Core build under Restricted PowerShell | #185 |
| 121 | 2026-10-03 | [`d16a41c9aa`](https://github.com/bongbong90/Sorigul/commit/d16a41c9aa4a5ca95841d6e1e3157f7a9c422d26) | test: make #113 preflight repository-owned | #185 |
| 122 | 2026-10-03 | [`1ec9c2c2f5`](https://github.com/bongbong90/Sorigul/commit/1ec9c2c2f587b8f6010ec714c4b73caef6acf263) | fix: harden #113 preflight contract syntax | #185 |
| 123 | 2026-10-03 | [`6768faf57c`](https://github.com/bongbong90/Sorigul/commit/6768faf57c9bb63479b846306fd9b6d951b7ada7) | fix: preserve PS5 preflight probe arguments | #185 |
| 124 | 2026-10-03 | [`40fcb1a126`](https://github.com/bongbong90/Sorigul/commit/40fcb1a126f4598e92be50da4aeb6367deceeab9) | fix: isolate PS5 regression child process policy | #185 |
| 125 | 2026-10-03 | [`14c72f0db8`](https://github.com/bongbong90/Sorigul/commit/14c72f0db8356cde8b15487d7267061ae13c3a20) | fix: keep preflight probe diagnostics plain text | #185 |
| 126 | 2026-10-03 | [`afba3023cb`](https://github.com/bongbong90/Sorigul/commit/afba3023cb1e468baede58c2df773f54fcbbf886) | fix: own #113 session bootstrap and Single Writer guard (#164) | #185 |
| 127 | 2026-10-03 | [`780dbb1e79`](https://github.com/bongbong90/Sorigul/commit/780dbb1e799fd5eb79f3c13736061ad34223cc1a) | fix: isolate native PS5 module resolution in canonical Python validation (#164) | #185 |
| 128 | 2026-10-06 | [`debabd0670`](https://github.com/bongbong90/Sorigul/commit/debabd06702d0c581c4f40feedba0d8669cc64eb) | fix: emit Local worker protocol as UTF-8 bytes (#167) | #185 |
| 129 | 2026-10-06 | [`8071886e9c`](https://github.com/bongbong90/Sorigul/commit/8071886e9cd5d1ad73e6f6cc3eba06f61616b9d0) | fix: honor forced re-transcription retry intent (#172) | #185 |
| 130 | 2026-10-06 | [`a12b93a1a0`](https://github.com/bongbong90/Sorigul/commit/a12b93a1a03a41576b3581ce68b38ebf31fc3619) | fix: reconcile folder picker immediately and reject stale scans (#170) | #185 |
| 131 | 2026-10-06 | [`82cee4d7c2`](https://github.com/bongbong90/Sorigul/commit/82cee4d7c26621ea76c9b0ef72c2ec774c262375) | fix: consume confirmations before transcription preflight (#171) | #185 |
| 132 | 2026-10-06 | [`ed3d862df9`](https://github.com/bongbong90/Sorigul/commit/ed3d862df9a8167eedc0592f81030746ac70b10b) | fix: move tray progress observer to app lifetime (#173) | #185 |
| 133 | 2026-10-06 | [`a4e46c8214`](https://github.com/bongbong90/Sorigul/commit/a4e46c8214e47ba59ff64f862a33dd76514c555d) | fix: focus existing desktop instance on second launch (#168) | #185 |
| 134 | 2026-10-06 | [`62e96d1c35`](https://github.com/bongbong90/Sorigul/commit/62e96d1c35631ad4b9e2705ee4d60a583dde6eac) | fix: guard tray Exit with the active-work close check (#174) | #185 |
| 135 | 2026-10-06 | [`36ac439c7f`](https://github.com/bongbong90/Sorigul/commit/36ac439c7f631c86e4c5263582d44755ea41c230) | feat: manual week input and Eduwill no-week normalization (#180) | #185 |
| 136 | 2026-10-06 | [`293b4027fb`](https://github.com/bongbong90/Sorigul/commit/293b4027fbac7347eadcb98dc6c20bfb8a1ef4eb) | docs: reconcile final Study-Use pre-freeze contract (#184) | #185 |
| 137 | 2026-10-06 | [`87d7b1e728`](https://github.com/bongbong90/Sorigul/commit/87d7b1e72840335eaa3baa1e7b805a01a8fe329e) | docs: close pre-freeze authority conflicts | #185 |
| 138 | 2026-10-07 | [`cd1cc55071`](https://github.com/bongbong90/Sorigul/commit/cd1cc5507124d36de68d137162e91a527cdd5f21) | audit: rerun final full source contract regression (#123) | #185 |
| 139 | 2026-10-07 | [`035db13260`](https://github.com/bongbong90/Sorigul/commit/035db132609b9ed298f1f4c1d8aacd838bd41056) | audit: classify final #123 regression evidence | #185 |
| 140 | 2026-10-07 | [`28ba869bec`](https://github.com/bongbong90/Sorigul/commit/28ba869bec598e8d436d0877d13a28194c305aff) | fix: tolerate transient heartbeat replacement race (#164) | #185 |
| 141 | 2026-10-13 | [`5c5cf18f68`](https://github.com/bongbong90/Sorigul/commit/5c5cf18f6801f3126026a198c12d531501cee5e1) | fix: classify protected WebView directory mtime differences (#189) | #185 |
| 142 | 2026-10-14 | [`b86cb3b69a`](https://github.com/bongbong90/Sorigul/commit/b86cb3b69af8ab3bf3ab6e94d3b5a04c27dfab66) | Merge pull request #190 from bongbong90/fix/189-protected-dir-mtime-classification | #185 |
| 143 | 2026-10-14 | [`8adb2bc813`](https://github.com/bongbong90/Sorigul/commit/8adb2bc8139e15f59a7c9e08e2ebcc3e950e7b7e) | fix: align exact broker subject filenames and Drive classification (#192) | #185 |
| 144 | 2026-10-14 | [`dc87f5d9e1`](https://github.com/bongbong90/Sorigul/commit/dc87f5d9e149b892fb07d9ad351460fa4d43fbfd) | fix: unify transcription scroll and task-focused workspace (#193 #194) | #185 |
| 145 | 2026-10-14 | [`a46e4d2552`](https://github.com/bongbong90/Sorigul/commit/a46e4d25522cecab0d076d8a883a2619f8aa2cdb) | fix: default new profiles to idle exit and preserve saved tray policy (#195) | #185 |
| 146 | 2026-10-14 | [`9c148877a6`](https://github.com/bongbong90/Sorigul/commit/9c148877a6da161256bce79979a4e26b0a0aacbe) | fix: preserve legacy broker standard names when classifications agree (#192) | #185 |
| 147 | 2026-10-15 | [`473a40a7f1`](https://github.com/bongbong90/Sorigul/commit/473a40a7f137da102f7e12b6eab6c6ba5dfaaeae) | Merge pull request #196 from bongbong90/fix/192-exact-subject-naming | #185 |
| 148 | 2026-10-15 | [`646e564ce6`](https://github.com/bongbong90/Sorigul/commit/646e564ce68b1da5c7daaf604ae98d0c87e5a5ab) | Merge pull request #197 from bongbong90/fix/193-194-transcription-workspace | #185 |
| 149 | 2026-10-15 | [`ade0abb514`](https://github.com/bongbong90/Sorigul/commit/ade0abb51490c91ab7d2fd61f220d8dd6aca8403) | Merge pull request #198 from bongbong90/fix/195-idle-close-default | #185 |
| 150 | 2026-10-15 | [`3ec1bf6cb8`](https://github.com/bongbong90/Sorigul/commit/3ec1bf6cb8cc755858b3a40ba2d2dd16f50f59f1) | fix: classify source-validation reports as historical evidence (#199) | #185 |
| 151 | 2026-10-15 | [`fa6ccd105c`](https://github.com/bongbong90/Sorigul/commit/fa6ccd105c6766e9360b717839708e41e7998b0c) | Merge pull request #200 from bongbong90/fix/199-source-of-truth-classification | #185 |
| 152 | 2026-10-15 | [`5b67e6e4c5`](https://github.com/bongbong90/Sorigul/commit/5b67e6e4c56cc5cd32520baf879ee28004c7392f) | fix(qa): format transcription workspace Rust example (#201) | #185 |
| 153 | 2026-10-15 | [`38b856a0df`](https://github.com/bongbong90/Sorigul/commit/38b856a0dfe18448005a59bf7bb36479f3cd2692) | Merge pull request #202 from bongbong90/fix/201-transcription-qa-rustfmt | #185 |

## 5. 증빙 기준·후속 관리

1. **정보원**: GitHub REST `commits?sha=integration/study-use-final-candidate` 전체 페이지; `pulls/1,6,185/commits`; repository PR search MERGED/CLOSED/OPEN; 74 원본 SHA와 Integration HEAD 간 commit compare; 원격 branches 91개와 Integration HEAD 간 compare. 
2. **정확성 한계**: 커밋 조상 관계와 파일 이력은 제품 기능의 최신 PASS를 보증하지 않는다. 과거 PR의 테스트 기재는 작성 당시 주장일 뿐 현 설치본 결과로 승격하지 않는다.
3. **제품 릴리스 Gate**: [#123](https://github.com/bongbong90/Sorigul/issues/123) 최신 Source PASS, [#191](https://github.com/bongbong90/Sorigul/issues/191) 정상 프로필 Core/Runtime pairing 미완, [#47](https://github.com/bongbong90/Sorigul/issues/47) 실제 강의 MP3, [#114](https://github.com/bongbong90/Sorigul/issues/114) 최종 Study Use 통합 검증 미완. 예전 #113 PASS를 현 새 HEAD 설치 PASS로 바꾸지 않는다.
4. **운영**: 기능 개발은 Issue → branch → commit/push → PR로 별도 관리. 과거 CLOSED-but-unmerged PR은 독립 재병합하지 않고 원본 링크·변경 파일·조상 관계를 유지한다. 문서 감사 #204는 현재 별도 Draft로 유지하고, release Freeze 변경 비용과 검증 영향이 없는 시점에 통합 여부 결정.
