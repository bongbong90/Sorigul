# Sorigul UI State Matrix

이 문서는 `MIGRATION_CONTRACT.md`의 사용자 계약을 UI에서 빠짐없이 표현하기 위한 기준이다. Backend State Machine 구현이나 enum의 1:1 복사를 확정하지 않는다.

## Core states

| State | 사용자 표시 의미 | 필요한 정보와 action |
| --- | --- | --- |
| `EMPTY` | 전사 폴더가 비었거나 실제 처리 대상이 없음 | 폴더 선택, refresh, 완료 bundle skip 수와 대상 0개 안내 |
| `IDLE` | 실행 가능한 준비 상태 | 선택 전사 또는 no-selection 전체 전사 확인 |
| `WAITING` | 실행 대상으로 대기 중 | 대기 순서, 취소 가능 여부 |
| `PREPARING` | scan, 정규화, 엔진·연결 준비 중 | 현재 준비 단계와 장시간 대기 설명 |
| `TRANSCRIBING` | 현재 파일 전사 중 | 파일명, 파일 진행률, 전체 진행률, ETA, Stop |
| `SAVING` | 결과 bundle 저장 중 | 완료로 오인하지 않도록 저장 단계 표시 |
| `VERIFYING` | TXT/JSON/SRT bundle 검증 중 | 검증 완료 전 100%/`DONE` 금지 |
| `DONE` | 전사와 정상 bundle 검증 완료 | 결과 보기, Folders 열기, 보조 `다시 전사` |
| `FAILED` | 파일 처리 또는 결과 검증 실패 | 원인, 영향 범위, Retry |
| `STOPPED` | 실행 중 전사를 사용자가 중지함 | 현재 파일은 처음부터 Retry |
| `CANCELLED` | 대기 또는 작업 자체를 사용자가 취소함 | `STOPPED`와 다른 문구, 미완료 범위 Retry |
| `CRASHED` | 앱 비정상 종료로 이전 작업이 미종결됨 | 자동 재개 금지, 완료 보존, 수동 Retry |
| `RETRYING` | 사용자 Retry 또는 제한된 자동 재시도 중 | 대상, 시도 이유, 자동/수동 여부 |
| `CANCEL_REQUESTED` | 중지·취소 요청을 처리 중 | 요청 접수와 안전한 종료 대기 표시 |

`STOPPED`와 `CANCELLED`를 하나의 “중지됨” 상태로 합치지 않는다. `FAILED`, `STOPPED`, `CANCELLED`, `CRASHED`는 Retry 가능하지만 사용자용 mid-file Resume는 제공하지 않는다.

## Derived and composite states

| UI 상황 | 표현 기준 |
| --- | --- |
| `DONE + Drive FAILED` | 로컬 저장 완료와 Google Drive 실패를 동시에 표시하고 Local `DONE`을 유지 |
| partial failure | 성공/실패 수, 성공 결과 보존, 실패 파일 Retry |
| completed skip | 정상 완료 bundle의 자동 skip과 처리 대상/분모 제외 |
| filename confirmation required | `원래 이름으로 계속` 또는 후보 이름 수정 |
| Colab connecting | 연결 확인 중과 경과 상태 |
| Colab retrying | retryable 오류와 최대 1회 자동 재시도 상태 |
| Drive pending | Local 상태와 분리된 업로드 대기 |
| Drive uploading | 대상 bundle과 업로드 진행 상태 |
| Drive failed | 오류 원인, 재시도/재인증 등 가능한 다음 행동 |
| backend offline | backend 미연결과 재연결 행동 |
| backend startup failure | 자동 시작 실패 원인과 Retry/종료 행동 |
| result verification failure | `DONE` 금지, 누락·손상 결과와 Retry |
| empty actual target | no-selection 확인 또는 skip 계산 후 실제 대상 0개 안내 |

## Long-running visibility

`NORMALIZING`, `READY`, `UPLOADING`, `DOWNLOADING`, `MERGING`, `BACKING_UP` 같은 내부 상태는 필요한 경우 `PREPARING`, `SAVING`, Drive 상태 등으로 묶을 수 있다. 다만 Colab 연결·재시도, Drive 업로드, 결과 검증, cancel 처리처럼 오래 걸릴 수 있는 단계는 현재 작업과 대기 이유를 계속 보여야 한다.
