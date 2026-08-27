# UI State / UX Validation

## Baseline
- **Branch**: `validation/ui-state-ux`
- **HEAD**: `9005f67596d26f9325c535a72bd10bb8c79c350c`
- **검증 환경**: Local Dev Server (React, Vite), Code Review (Zustand/Hooks)

## 변경 파일
- `frontend/src/pages/TranscriptionPage.tsx` (취소 시 대기 중인 파일도 CANCELLED 상태로 변경하도록 수정)

## 신규 파일
- `docs/design/UI_STATE_UX_VALIDATION.md` (본 문서)

## Dependency 변경 여부
- 변경 없음

---

## D01 ~ D10 검증 결과

- **D01 no-selection**: `PASS`. 파일 선택 후 Start 시 즉시 실행. 선택 없이 Start 시 미완료 대상(전체 중 일부)을 확인하는 모달 표시. 처리 대상이 없으면 "처리할 파일이 없습니다" 다이얼로그 표시.
- **D02 partial failure**: `PASS`. 일부 실패 시 검증 실패 사유(`detail`)가 표시되며 전사가 중단되지 않고 다음 파일로 계속 진행됨. 실패한 결과 요약 배지 제공. Retry 시 FAILED/STOPPED/CANCELLED/CRASHED 상태만 재시도 대상이 됨.
- **D03 DONE skip / 다시 전사**: `PASS`. 일반 전사나 재시도 시 DONE 상태의 파일은 자동으로 건너뜀. '다시 전사'는 secondary action(`...` 버튼)으로 제공되며 명확한 주의 안내 제공.
- **D04 STOPPED / CANCELLED / CRASHED**: `PASS`. STOPPED("중지됨")와 CANCELLED("취소됨")가 구분됨. 작업 취소 시 실행 대기 중이던 파일도 CANCELLED로 명확히 전환됨. "이어하기" 문구 없이 처음부터 처리됨을 안내. CRASHED의 경우 "이전 작업이 비정상 종료됨" 경고 배너가 표시됨.
- **D05 filename choice**: `PASS`. 원본 파일명과 추천 파일명을 비교하는 UI 제공. 금지 문자, 중복 등의 검증 제공. Drive 분류 실패 시 "원래 이름으로 Local 전사를 계속합니다" 안내가 표시됨.
- **D06 output UI**: `PASS`. 별도 저장 위치 선택 UI가 노출되지 않으며 결과는 MP3 옆에 저장됨을 내포함. (폴더 변경은 입력 폴더 기준)
- **D07 Whisper settings non-exposure**: `PASS`. Settings 화면에 `beam_size`, `temperature` 등 고급 추론 옵션이 노출되지 않음.
- **D08 Colab UX**: `PASS`. `RETRYING`, `CONNECTED`, `FAILED` 상태가 직관적으로 제공됨. `chunk_seconds`, `manifest` 등 내부 기술 용어 노출 없음.
- **D09 Folders**: `PASS`. 파일 목록에서 폴더 새로고침을 통해 실제 디스크 상태를 반영하는 흐름 제공. 전체/완료/미완료/결과만 필터 제공.
- **D10 Log / Dashboard removal**: `PASS`. Dashboard 대신 Log 화면이 제공됨. 성공/경고/오류 필터 적용, 복사 기능 존재. Tqdm 등 불필요한 스팸 로그 없음.

---

## Cross-state 검증 결과
- **Case 1 (전사 DONE, Drive FAILED)**: `PASS`. 파일 상태는 DONE으로 유지되고 Drive 카드에만 실패로 표시되어 파일이 초기화되지 않음.
- **Case 2 (일부 DONE, 일부 FAILED)**: `PASS`. 요약 배너로 부분 실패 안내를 명확하게 제공.
- **Case 3 (일부 DONE, 현재 STOPPED)**: `PASS`. 모순 없음.
- **Case 4 (CRASHED, 기존 DONE 존재)**: `PASS`. 완료 파일 유지 후 재시도 가능.
- **Case 5 (Filename 분류 실패, Local 가능)**: `PASS`. Local 전사 가능함을 설명함.
- **Case 6 (Colab 연결 재시도, 사용자 Stop)**: `PASS`. 모순 없음.
- **Case 7 (Shutdown countdown, 사용자 종료 취소)**: `PASS`. 카운트다운 도중 종료 취소 정상 동작 확인.

## Button state 결과
- `PASS`. `isProcessing` 및 `runState`에 따라 Start, Stop, Cancel 버튼의 활성/비활성화가 올바르게 작동. 중복 실행 방지 처리 확인.

## Modal 결과
- `PASS`. 다이얼로그(전체 실행 확인, 다시 전사, 빈 대상)가 화면 중앙에 오버레이되며, 확인/취소 시 UI Block 없이 닫힘.

## Accessibility 결과
- `PASS`. `aria-live` 및 `aria-hidden` 속성이 적절히 사용되었고 상태가 색상뿐만 아니라 Badge Text와 아이콘으로도 구분됨.

## 1440×900 / 1024×768 검증
- `PASS`. `app-shell.css`, `transcription-screen.css`, `feature-pages.css` 리뷰 결과, 1024 해상도에서 Action이 잘리거나 레이아웃이 무너지지 않음. 가로가 부족한 테이블에 대해 `overflow-x: auto;` 적용 확인.

---

## 결함 목록
- **BLOCKER**: 없음.
- **MAJOR**: 없음.
- **POLISH**:
  - 취소 시 현재 파일뿐만 아니라 `WAITING` 상태인 대기열 파일도 명시적으로 `CANCELLED` 처리하도록 `TranscriptionPage.tsx` 수정 적용 (수정 완료).

---

## 자동 검증 상태
- **lint**: `PASS`
- **typecheck**: `PASS`
- **build**: `PASS`
- **git diff --check**: `PASS`
- **git status --short**: `PASS`

## 특이 사항
- 실제 Backend/API 호출 없음 (MOCK 환경 유지).
- 코드 변경(POLISH 1건)은 적용했으나 `commit`/`push`는 수행하지 않음.

---

## Final Verdict
`UI STATE / UX VALIDATION READY FOR FREEZE`
