# UI Freeze v1 Record

## Status
**LOCKED**

## Baseline
- **Branch**: `freeze/ui-v1`
- **HEAD**: `89180a0aa5c68bfd115d5e564cf5af1cf12f0afc`
- **Migration Contract baseline**: `MIGRATION_CONTRACT.md`

---

## Frozen Navigation
- 전사 (기본 진입)
- 로그
- Folders
- 설정
- Dashboard 제거 (경로 및 뷰 없음)

## Frozen Screens
- **TranscriptionScreen**: 전사 대기열 관리, 파일명 정규화, Colab/Drive 연결 상태 분리, 현재 작업 진행 상태, 실패 원인과 부분 실패 요약 배너 표시 등
- **LogScreen**: Dashboard 역할을 대체하는 독립된 로그 화면 (전체/성공/경고/오류 필터, 로그 텍스트 복사)
- **FoldersScreen**: 실제 디스크 상태를 최종 기준으로 하는 Folders UX와 TXT 미리보기 UI를 제공하며, 실제 File Scan / refresh / reconcile 구현은 Post-Freeze로 이관
- **SettingsScreen**: 파일/전체 완료 알림, Tray 동작 명확화 및 PC 종료(즉시/지연 선택 및 카운트다운/취소) 지원, Backend 연결 상태 표시

## Frozen Major Actions
- **시작**: 선택 시 해당 파일 전사, 미선택 시 전체 미완료 대상 전사 확인 후 일괄 실행 (처리 대상 0개 시 경고)
- **재시도**: 실패 파일(FAILED/STOPPED/CANCELLED/CRASHED)만 대상이며 처음부터 다시 실행. 완료된 결과(DONE)는 건너뜀
- **중지 (Stop)**: 현재 진행 중 파일 중단 (`STOPPED`). 대기 파일은 보존
- **취소 (Cancel)**: 대기 중인 전체 작업 취소 (`CANCELLED`)
- **다시 전사**: DONE 항목에 한해 개별 메뉴를 통해 기존 결과 보존한 상태로 재전사

## Frozen States
- `EMPTY`, `IDLE`, `WAITING`, `PREPARING`, `TRANSCRIBING`, `SAVING`, `VERIFYING`
- `DONE`, `FAILED`, `STOPPED`, `CANCELLED`, `CRASHED`, `RETRYING`, `CANCEL_REQUESTED`

---

## Deferred Implementation
다음 항목은 기능의 UI 상태를 지원하지만, 실제 구현 로직은 향후 작업(Post-Freeze)으로 이관됨.

- 실제 File Scan
- D09 Result API 및 reconcile
- 실제 Local Whisper 연동
- 실제 Colab 연결
- 실제 Google Drive API 연동
- Log / Job / CRASHED Persistence (데이터 영속성 보장 로직)
- OS Tray API
- Notification OS API
- Windows OS 레벨의 Shutdown 명령 호출
- Tauri sidecar 연동 로직
- MSI 인스톨러 빌드

---

## Allowed Post-Freeze Changes
사용자 승인(Change Control) 없이 진행 가능한 변경 사항:

- 문구 수정
- 작은 spacing
- icon 미세 조정
- 접근성 개선
- bug fix
- 실제 backend data binding
- loading/error 실제 데이터 연결

## Restricted Post-Freeze Changes
사용자 승인 없이 진행할 수 **없는** 변경 사항:

- Navigation 변경 또는 화면 제거
- 주요 Action 제거
- STOPPED와 CANCELLED 통합
- Dashboard 재도입
- Output folder 기능 추가
- Whisper 고급 설정(beam_size 등) 노출
- Colab chunk 설정 노출
- 파일 중간부터 재개하는 Resume 기능 추가
- Google Drive 외의 Cloud Provider 추가

---

## Validation References
- `UI_STATE_UX_VALIDATION.md`
- `UI_FREEZE_CHECKLIST.md`

## Remaining Polish
- 없음

---

## Final User Approval
[x] **Approved by User** (사용자 승인 완료)
