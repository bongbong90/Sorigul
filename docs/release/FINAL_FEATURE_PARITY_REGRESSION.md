# Final Feature Parity Regression

| ID | Legacy Contract | Final Sorigul Contract | Final Status | Evidence | Automated Test | Installed Manual Test | Notes |
|---|---|---|---|---|---|---|---|
| TR-001 | 최상위 MP3 검색 | Contract enforced | PASS | Backend Pytest (88 passed) | PASS | NOT RUN | |
| TR-002 | 선택/전체 fallback | Intentional change approved | APPROVED_INTENTIONAL_CHANGE | Contract spec | N/A | N/A | |
| TR-003 | 완료 bundle 사전 제외 | Contract enforced | PASS | Backend Pytest (88 passed) | PASS | NOT RUN | |
| TR-004 | 순차 처리와 다음 파일 이동 | Contract enforced | PASS | Backend Pytest (88 passed) | PASS | NOT RUN | |
| TR-005 | 파일/전체 progress와 ETA | Contract enforced | PASS | Backend Pytest (88 passed) | PASS | NOT RUN | |
| TR-006 | TXT/JSON/SRT 완료 bundle | Contract enforced | PASS | Backend Pytest (88 passed) | PASS | NOT RUN | |
| TR-007 | 부분 실패 의미 | Intentional change approved | APPROVED_INTENTIONAL_CHANGE | Contract spec | N/A | N/A | |
| TR-008 | Start/Stop/실패/재시도 | Contract enforced | PASS | Backend Pytest (88 passed) | PASS | NOT RUN | |
| FN-001 | 문자열 정리 | Contract enforced | PASS | Backend Pytest (88 passed) | PASS | NOT RUN | |
| FN-002 | 과정·과목·주차·강 감지 | Contract enforced | PASS | Backend Pytest (88 passed) | PASS | NOT RUN | |
| FN-003 | 표준명과 다음 번호 | Contract enforced | PASS | Backend Pytest (88 passed) | PASS | NOT RUN | |
| FN-004 | rename preview/보호/충돌/실패 UX | Contract enforced | PASS | Backend Pytest (88 passed) | PASS | NOT RUN | |
| RC-001 | CANCELLED 재실행 | Contract enforced | PASS | Backend Pytest (88 passed) | PASS | NOT RUN | |
| RC-002 | STOPPED 재실행 | Contract enforced | PASS | Backend Pytest (88 passed) | PASS | NOT RUN | |
| RC-003 | DONE 재실행/skip | Intentional change approved | APPROVED_INTENTIONAL_CHANGE | Contract spec | N/A | N/A | |
| RC-004 | 파일 단위 resume | Contract enforced | PASS | Backend Pytest (88 passed) | PASS | NOT RUN | |
| JP-001 | jobs.json 영속화 | Contract enforced | PASS | Backend Pytest (88 passed) | PASS | NOT RUN | |
| JP-002 | atomic/corrupt 방어 | Contract enforced | PASS | Backend Pytest (88 passed) | PASS | NOT RUN | |
| JP-003 | 비정상 종료 복구 | Contract enforced | PASS | Backend Pytest (88 passed) | PASS | NOT RUN | |
| LW-001 | Whisper `medium` | Contract enforced | PENDING_USER_INPUT | Current final regression NOT RUN — Korean MP3 required | PASS | NOT RUN | |
| LW-002 | CUDA/CPU fallback | Contract enforced | PENDING_USER_INPUT | Current final regression NOT RUN — Korean MP3 required | PASS | NOT RUN | |
| LW-003 | 결과 검증 | Contract enforced | PENDING_USER_INPUT | Current final regression NOT RUN — Korean MP3 required | PASS | NOT RUN | |
| LW-004 | Local 옵션·실패 정책 일치 | Intentional change approved | APPROVED_INTENTIONAL_CHANGE | Contract spec | N/A | N/A | |
| CO-001 | `/health`, `/transcribe`, URL normalize | Contract enforced | PENDING_USER_INPUT | Current final regression NOT RUN — Colab endpoint required | PASS | NOT RUN | |
| CO-002 | 300초 chunk와 timeout/retry | Contract enforced | PENDING_USER_INPUT | Current final regression NOT RUN — Colab endpoint required | PASS | NOT RUN | |
| CO-003 | manifest/tail skip | Contract enforced | PENDING_USER_INPUT | Current final regression NOT RUN — Colab endpoint required | PASS | NOT RUN | |
| CO-004 | merge와 segment offset | Contract enforced | PENDING_USER_INPUT | Current final regression NOT RUN — Colab endpoint required | PASS | NOT RUN | |
| CO-005 | Colab resume/cancel 의미 | Intentional change approved | APPROVED_INTENTIONAL_CHANGE | Contract spec | N/A | N/A | |
| GD-001 | OAuth credential/token 수명주기 | Contract enforced | PENDING_USER_INPUT | Current final regression NOT RUN — Google credentials required | PASS | NOT RUN | |
| GD-002 | 과정/과목/주차/강 분류 | Contract enforced | PENDING_USER_INPUT | Current final regression NOT RUN — Google credentials required | PASS | NOT RUN | |
| GD-003 | 4종 bundle 업로드 | Contract enforced | PENDING_USER_INPUT | Current final regression NOT RUN — Google credentials required | PASS | NOT RUN | |
| GD-004 | 업로드 전 엄격 검증 | Contract enforced | PENDING_USER_INPUT | Current final regression NOT RUN — Google credentials required | PASS | NOT RUN | |
| GD-005 | update-or-create | Contract enforced | PENDING_USER_INPUT | Current final regression NOT RUN — Google credentials required | PASS | NOT RUN | |
| GD-006 | Drive 실패 격리 | Contract enforced | PENDING_USER_INPUT | Current final regression NOT RUN — Google credentials required | PASS | NOT RUN | |
| UI-001 | Dashboard | Intentional change approved | APPROVED_INTENTIONAL_CHANGE | Contract spec | N/A | N/A | |
| UI-002 | Folders | Contract enforced | PASS | Workstream 7 installed validation | PASS | NOT RUN | |
| UI-003 | 완료 알림/Toast | Contract enforced | PASS | Workstream 7 installed validation | PASS | NOT RUN | |
| UI-004 | Tray | Contract enforced | PASS | Workstream 7 installed validation | PASS | NOT RUN | |
| UI-005 | 완료 후 PC 종료 | Contract enforced | PENDING_USER_INPUT | Current final regression NOT RUN — Manual supervised check pending | PASS | NOT RUN | |
| RT-001 | backend sidecar 자동 시작/health | Contract enforced | PASS | Rust Cargo Test (24 passed) / Workstream 7 MSI validation | PASS | NOT RUN | |
| RT-002 | 종료 시 process tree 정리 | Contract enforced | PASS | Rust Cargo Test (24 passed) / Workstream 7 MSI validation | PASS | NOT RUN | |
| RT-003 | 설치형 Job/Drive 복원 | Contract enforced | PASS | Rust Cargo Test (24 passed) / Workstream 7 MSI validation | PASS | NOT RUN | |
| RT-004 | Windows MSI/Unicode/no-console | Contract enforced | PASS | Rust Cargo Test (24 passed) / Workstream 7 MSI validation | PASS | NOT RUN | |
| UI-visible | `WAITING`, `TRANSCRIBING`/`RUNNING`, `DONE`, `FAILED`, `CANCELLED`/`STOPPED`, `CRASHED` | Contract enforced | PASS | Workstream 7 installed validation | PASS | NOT RUN | |
| UI-derived | 파일 완료 수/대상 수, ETA, Local DONE + Drive FAILED, retry 가능 여부 | Contract enforced | PASS | Workstream 7 installed validation | PASS | NOT RUN | |

## Summary
- Total: 45
- PASS: 25
- APPROVED_INTENTIONAL_CHANGE: 6
- PENDING_USER_INPUT: 14
- BLOCKED: 0