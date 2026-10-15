# Sorigul Development Rules

## Current authority

- 모든 제품 행동 결정은 [`CURRENT_PRODUCT_CONTRACT.md`](CURRENT_PRODUCT_CONTRACT.md)에서 시작한다.
- Legacy ACTIVE 기능은 기본적으로 보존하며, 사용자 승인 `Intentional Change`만 예외로 인정한다.
- 현재 Sorigul 코드에 존재하는 동작만으로 의도된 제품 계약이라고 판단하지 않는다.
- UI 설계나 구현 편의가 Legacy 기능을 지우는 근거가 되어서는 안 된다.
- 기존 전사도우미 소스 Copy와 Legacy Python module Import를 금지한다. 기능과 검증 증거만 parity 근거로 사용한다.
- 새로운 차이가 필요하면 `Evidence → Conflict → Options → Impact → User Decision → Contract Lock` 순서로 결정한다.

## Mandatory development lifecycle

모든 development work unit은 다음 전체 수명주기를 완료해야 한다.

`Issue discovery/creation → dedicated branch → implementation → validation/tests → meaningful commit → push → PR create/update → Issue update → #7 Tracker update → approved merge gate`

- commit, push, PR은 마지막 정리 단계가 아니라 각 work unit의 완료 조건이다.
- 완료된 변경을 local working tree에만 남기지 않는다.
- blocker를 발견하면 해당 Issue에 즉시 기록한다.
- blocker를 수정한 뒤 관련 test를 다시 실행하고 commit, push, PR update까지 완료한다.
- 새로운 독립 defect는 수정 전에 독립 Issue를 만든다.
- 현재 work unit과 관련 없는 defect를 같은 commit이나 PR에 포함하지 않는다.
- 하나의 Issue/branch/PR은 검토 가능한 하나의 목적과 atomic commit 경계를 유지한다.

## Branch, staging, and repository safety

- `main`에서 직접 개발하지 않는다. Issue 또는 Phase/Task 단위 dedicated branch를 사용한다.
- staging은 `git add <exact-file-1> <exact-file-2>`처럼 변경 의도가 확인된 정확한 파일만 대상으로 한다.
- commit 전 `git status --short`, `git diff --check`, `git diff --cached --stat`, `git diff --cached --check`를 확인한다.
- 기존 보호 대상 untracked helper 및 사용자 파일을 수정하거나 삭제하지 않는다.
- generated/build/cache/model/install artifact를 commit하지 않는다.
- credential, token, 실제 MP3, 결과물, persistent runtime user data를 commit하지 않는다.

다음 명령과 작업은 금지한다.

- `git add .`
- `git add -A`
- `git reset --hard`
- `git clean`
- `git rebase`
- force push
- `main` 직접 개발
- 관련 없는 변경의 일괄 staging 또는 commit

## Validation and blockers

- 변경 위험에 비례한 test와 validation을 work unit 안에서 실행하고 실제 결과를 PR과 Issue에 기록한다.
- docs-only 작업에서 production test가 불필요하면 `NOT RUN — docs-only`라고 명시한다.
- 실패한 gate를 건너뛰지 않는다. 원인과 영향, 다음 조치를 Issue에 남긴다.
- 외부 zero-cost dependency를 안전하게 검증할 수 없으면 기능을 삭제하거나 paid fallback을 도입하지 않고 `PENDING`으로 기록한다.

## Merge policy

- work unit이 완료되어도 PR은 승인된 merge gate까지 OPEN으로 유지할 수 있다.
- 현재 Sorigul은 [`SORIGUL_FULL_LEGACY_PARITY_COMPLETION_PLAN_2026-09-28.md`](SORIGUL_FULL_LEGACY_PARITY_COMPLETION_PLAN_2026-09-28.md)의 #114 final Study Workflow Regression이 PASS하기 전에는 `main`에 merge하지 않는다.
- stacked work는 bottom-up으로 merge한다.
- stack을 `rebase` 또는 force push로 재작성하지 않는다.
- merge 전에 각 PR의 base, head, diff, validation evidence와 Issue/Tracker 연결을 다시 확인한다.

## Product and storage boundaries

- 사용자 UI에 내부 engine 이름이나 불필요한 구현 세부를 노출하지 않는다.
- DONE 이전에는 100% 완료를 표시하지 않는다.
- Local 전사 결과와 Google Drive 업로드 상태를 분리한다.
- 사용자 데이터와 재생성 가능한 개발 artifact를 구분한다.
- `node_modules`, Rust `target`, `.venv`, `build`/`dist` 같은 재생성 가능한 artifact는 필요 시 로컬에서 사용할 수 있으나 Git에서 추적하지 않는다.
- 사용자 데이터 정리를 개발 artifact 정리와 한꺼번에 수행하지 않는다.
