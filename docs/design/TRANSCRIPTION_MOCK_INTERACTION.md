# Sorigul Transcription Screen — Mock Interaction

**Status: PARTIAL**

> **Contract alignment:** 아래의 선택 필요 Start와 Stop→`CANCELLED` 동작은 당시 mock 구현 기록이며 현재 제품 계약이 아니다. `MIGRATION_CONTRACT.md`에 따라 no-selection Start는 전체 범위 확인으로 이어지고, 실행 중 Stop은 `STOPPED`, 대기·작업 Cancel은 `CANCELLED`로 구분한다. 이 작업에서는 mock component를 변경하지 않으며 UI Feature Gap Closure에서 정렬한다.

## 1. 목적

승인된 전사 화면의 정적 구조를 유지하면서 Frontend 내부 mock state로 선택, 시작, 진행,
중지, 완료 흐름을 검증한다. 이 구현은 실제 전사 또는 Backend 계약이 아니다.

## 2. 기준 문서

- `docs/design/TRANSCRIPTION_SCREEN_SPEC.md`
- `docs/design/UI_STATE_MATRIX.md`
- `docs/design/UI_FREEZE_CHECKLIST.md`
- `docs/project/MIGRATION_CONTRACT.md`
- `docs/design/TRANSCRIPTION_SCREEN_IMPLEMENTATION.md`
- 공통 Design System, App Shell, Project 문서

제품 행동은 `MIGRATION_CONTRACT.md`, 상태명과 사용자 표시 문구는 `UI_STATE_MATRIX.md`,
Action 규칙과 화면 구조는 `TRANSCRIPTION_SCREEN_SPEC.md`를 우선한다.

## 3. Mock State 구조

`TranscriptionPage`가 다음 화면 전용 상태를 단일 소유한다.

- 현재 mock 폴더 index
- 4개 `MOCK_FILES`의 최소 UI 정보와 상태
- 선택된 row id 목록
- 당시 mock 화면 실행 상태: `IDLE`, `TRANSCRIBING`, `DONE`, `CANCELLED`
- Start 시점의 mock 처리 대상 id 목록과 현재 index
- 현재 파일 mock progress

하위 컴포넌트는 props로 상태를 표시하고 semantic event를 상위에 전달한다. API response나
Backend job type은 정의하지 않았다.

## 4. 구현 Interaction

- 두 개의 고정 mock 폴더 경로 전환과 화면 상태 초기화
- row 선택/해제, header 전체 선택/해제, 일부 선택 indeterminate 표시
- 선택 수와 `DONE / 전체 대상` 완료 수 표시
- Start/Stop disabled 상태와 click interaction
- 선택한 row의 순차 상태/현재 작업/progress 변경
- 당시 mock은 Stop 후 `CANCELLED → 중지됨`, 완료 후 `DONE → 완료` 표시 (현재 Contract gap)

## 5. Start 흐름

당시 mock은 선택 파일이 있고 실행 중이 아닐 때만 Start가 활성화된다. Start 시 선택 목록을 화면 전용
처리 순서로 복사하고 첫 row를 `TRANSCRIBING`으로 바꾼다. Start는 비활성, Stop은 활성으로
전환되며 Current Task에 현재 파일과 고정 mock ETA 문구를 표시한다.

## 6. Stop 흐름

당시 mock의 Stop은 실행 중에만 활성화된다. 클릭 시 현재 row를 `CANCELLED`로 바꾸고 progress를 현재
값에서 멈춘다. 대기 timer는 effect cleanup으로 제거된다. 선택이 남아 있으면 Start를 다시
사용할 수 있다. 이는 현재 제품 계약이 아니라 UI Feature Gap Closure에서 교정할 Preview 동작이다.

## 7. Complete 흐름

현재 row의 mock 단계가 끝날 때 해당 row를 `DONE`으로 전환한다. 다음 대상이 있으면 Current
Task를 다음 row로 옮기고 progress를 0부터 다시 시작한다. 마지막 대상은 `DONE` 전환과 함께
100%를 표시한다. 따라서 `DONE` 이전에 100%가 노출되지 않는다.

## 8. Queue Selection 흐름

모든 checkbox는 native input과 React controlled state를 사용한다. Header checkbox는 전체
선택/해제를 수행하며 일부 row만 선택되면 DOM `indeterminate` 상태를 표시한다. 선택 수는
Action 영역의 live text로 함께 전달된다.

## 9. Folder Mock 흐름

`폴더 변경`은 `C:\Users\Sorigul\Lectures`와 `C:\Users\Sorigul\CivilLaw` 사이의 화면 문자열만
전환한다. 변경 시 Queue fixture, 선택, 현재 작업, progress를 초기 상태로 되돌린다. Dialog나
File System 접근은 없다.

## 10. Timer

`setTimeout` 하나로 500ms마다 10%씩 증가하는 결정적 mock progression을 사용한다. effect는
매 단계 이전 timer를 cleanup하며 Stop, 폴더 변경, unmount 시에도 `clearTimeout`을 실행한다.
실제 파일 길이, ETA 또는 전사 속도 계산에는 사용하지 않는다.

## 11. 실제 구현하지 않은 기능

- Folder dialog, 파일 탐색, MP3 scan/read, filename normalize
- API, Backend, Tauri, Job Queue, persistence
- Whisper, 실제 전사, 결과 생성/저장/upload
- 실제 duration 분석과 ETA 계산
- Router, 전역 상태관리, mock server

## 12. 검증 결과

- `npm run lint`: PASS
- `npm run typecheck`: PASS
- `npm run build`: PASS
- `git diff --check`: PASS
- Chrome 실제 interaction: row 선택/해제, 전체/일부 선택, Start, progress, Stop,
  progress 정지, 재시작, Complete, folder reset PASS
- 1440×900: App Shell 240px/64px 및 page overflow 없음, table layout PASS
- 1024×768: page overflow/Sidebar 침범 없음, 긴 filename ellipsis PASS
- 금지 source/API, 직접 SVG path, 추가 dependency 없음

## 13. Contract gaps for UI Feature Gap Closure

- no-selection Start는 비활성화하지 않고 완료 bundle을 제외한 전체 범위를 확인한다.
- Stop은 `STOPPED`, Cancel은 `CANCELLED`로 구분한다.
- `FAILED`, `STOPPED`, `CANCELLED`, `CRASHED`는 완료 bundle을 보존한 채 미완료 파일만 Retry한다.
- 일반 Start와 Retry는 `DONE`을 skip하며, 완료 파일은 보조 `다시 전사`로만 다시 처리한다.

3–12절의 기존 mock 동작과 검증 결과는 구현 증거로 보존한다. 위 gap은 제품 정책의 미정 사항이 아니라 후속 UI 변경 대상이다.

## 14. 다음 Phase

UI State / UX Validation
