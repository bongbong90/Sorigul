# Sorigul UI Freeze Checklist

`MIGRATION_CONTRACT.md`와 `LEGACY_FEATURE_PARITY_AUDIT.md`의 B01–B12를 기준으로 한다. Dashboard 전용 화면은 완성 대상이 아니라 승인된 제거 결정이며, 기존 로그 기능은 독립 Log Screen으로 보존한다.

## Foundation

- [ ] Brand / Color / Typography / Icon
- [ ] App Shell과 기본 navigation: `전사`, `로그`, `Folders`
- [ ] 기본 진입 화면 `전사`
- [ ] Dashboard 제거 결정 반영
- [ ] Transcription Screen과 Mock Interaction
- [ ] Empty / Loading / Error / Progress / Long Filename
- [ ] 접근성, 버튼 상태, 긴 문구와 한국어/Unicode 경로

## Contract blockers

- [ ] **B01 전사 상태와 action:** no-selection 전체 확인, 완료 skip, 처리 대상 0개, `DONE`, `STOPPED`, `CANCELLED`, Retry, 보조 `다시 전사`
- [ ] **B02 실패와 진행:** 개별 실패 후 계속, partial failure, 성공 결과 보존, 파일/전체 진행률, ETA, 오류 원인과 실패 파일 Retry
- [ ] **B03 복구:** `CRASHED` 복구 안내, 자동 재개 금지, 완료 bundle 보존과 수동 Retry
- [ ] **B04 파일명:** 정규화 preview, 충돌·실패 설명, `원래 이름으로 계속`, 후보 이름 수정과 overwrite 보호
- [ ] **B05 Direct Colab:** 연결 중/실패, 장시간 단계, 최대 1회 자동 Retry, `FAILED` chunk 재사용, STOP/CANCEL 후 현재 파일 처음부터
- [ ] **B06 Google Drive 상태:** 사용 여부·분류 실패, pending/uploading/failed, `local DONE + Drive FAILED`
- [ ] **B07 Google Drive 인증:** OAuth 연결, token refresh 실패, 재로그인 action
- [ ] **B08 Log Screen:** 실행 기록, 오류 원인, Retry/Stop/Cancel, Colab, Google Drive, 결과 검증과 runtime 상태의 구조화된 독립 화면
- [ ] **B09 Folders:** 실제 디스크 refresh, 외부 추가·삭제·변경, 필터/표, preview·전체 보기와 폴더 열기
- [ ] **B10 Notification / Tray:** 파일별·전체 알림 설정, 폴더 열기, close-to-tray, 앱 열기와 종료 진입점
- [ ] **B11 Shutdown:** 완료 후 종료 설정, 즉시/지연 선택, countdown과 취소
- [ ] **B12 Backend / runtime failure UX:** starting, offline, startup/health failure, 재연결·Retry, owned/external backend 충돌 설명

## State coverage

- [ ] `EMPTY`, `IDLE`, `WAITING`, `PREPARING`, `TRANSCRIBING`, `SAVING`, `VERIFYING`
- [ ] `DONE`, `FAILED`, `STOPPED`, `CANCELLED`, `CRASHED`, `RETRYING`, `CANCEL_REQUESTED`
- [ ] 결과 검증 실패를 `DONE`과 구분하고 검증 전 100% 완료 표시 금지
- [ ] 사용자용 mid-file Resume 비지원과 현재 파일 처음부터 Retry를 일관되게 표현
- [ ] 사용자가 장시간 현재 작업과 대기 이유를 알 수 없는 상태가 없음

## Freeze approval

- [ ] Contract 항목과 B01–B12의 UI 상태/action이 모두 승인되거나 명시적 후속 구현 경계로 닫힘
- [ ] Final User Approval

현재 승인되지 않은 항목은 unchecked 상태로 둔다.
