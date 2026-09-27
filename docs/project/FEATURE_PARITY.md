# Sorigul Feature Parity

> **Amendment notice (2026-08-29):** `docs/migration/CORE_WORKFLOW_REFINEMENT_PLAN.md`가 아래 두 항목을 `SUPERSEDED_BY_PRODUCT_DECISION`으로 갱신한다. "Google Drive" 절의 MP3/TXT/JSON/SRT 4종 업로드는 TXT/JSON/SRT 3종으로 축소된다 (D11). "파일명과 결과 bundle" 절의 과정/과목 alias는 사용자 직접 입력으로 대체되며, 주차/강 감지만 그대로 유지된다 (D12). 이 문서의 나머지 내용은 그대로 유효하다.

이 문서는 `MIGRATION_CONTRACT.md`를 따르는 기능 이식 기준 요약이다. Legacy 구현 구조를 복사하는 목록이 아니라, 신규 Sorigul이 보존하거나 승인된 `INTENTIONAL_CHANGE`로 다뤄야 할 사용자 계약을 정리한다. 세부 행동이 충돌하면 `MIGRATION_CONTRACT.md`를 우선한다.

## 전사 흐름과 복구

- 사용자는 전사 폴더를 선택하고 최상위 MP3 목록을 확인할 수 있다.
- 각 MP3는 checkbox로 선택할 수 있으며 긴 파일명도 식별 가능하게 표시한다.
- 사용자가 파일을 선택하면 선택한 미완료 파일을 전사한다.
- no-selection 상태에서도 Start를 사용할 수 있으며, 완료 bundle을 제외한 전체 전사 범위를 확인한 뒤 실행한다.
- 실제 처리 대상이 없으면 Job을 시작하지 않고 처리할 대상이 없음을 알린다.
- 같은 stem의 정상 TXT/JSON/SRT bundle이 있는 파일은 일반 Start와 Retry에서 자동 skip한다.
- 파일 하나가 실패하면 해당 파일을 `FAILED`로 남기고 다음 파일 처리를 계속한다. 공통·치명 오류만 전체 작업을 중단할 수 있다.
- 부분 실패 시 성공 결과를 보존하고 전체 종료 시 성공 수와 실패 수를 구분한다.
- `FAILED`, `STOPPED`, `CANCELLED`, `CRASHED` 파일은 Retry할 수 있으며, Retry는 `DONE` 파일을 유지하고 미완료 파일만 처리한다.
- 완료 파일은 보조 액션 `다시 전사`를 명시적으로 선택한 경우에만 다시 처리한다. 새 bundle의 생성과 검증이 실패하면 기존 정상 bundle을 보존한다.
- `STOPPED`는 실행 중인 전사를 중지한 상태, `CANCELLED`는 대기 또는 작업 자체를 취소한 상태로 구분한다.
- 앱 비정상 종료로 종결되지 않은 작업은 `CRASHED`로 표시하고 자동 재개하지 않는다. 사용자가 수동으로 Retry한다.
- 사용자용 mid-file Resume는 Local과 Colab 모두 지원하지 않는다. 중지·취소·비정상 종료 당시의 현재 파일은 처음부터 다시 처리한다.
- 현재 파일 진행률, 전체 진행률, 처리 대상 기준 분모와 ETA를 구분해 표시한다.

## Local Whisper

- OpenAI Whisper Local과 `medium` 모델을 유지한다.
- CUDA를 우선하고 GPU 또는 model load 실패 시 CPU로 fallback한다.
- fp16 가능 여부를 판단하고 fp16 실패 시 안전하게 fallback한다.
- 추론 옵션은 `language="ko"`, `task="transcribe"`, `temperature=0`, `beam_size=5`, `best_of=5`, `patience=1.0`, `condition_on_previous_text=False`로 고정한다.
- 내부 엔진 이름과 고급 추론 옵션을 일반 사용자 설정으로 노출하지 않는다.
- 결과는 TXT, JSON, SRT로 생성하고 정상 bundle을 검증한다.

## Direct Colab

- 사용자는 Direct Colab을 단순한 Colab 전사로 사용하며 연결·실패·장시간 작업 상태를 확인할 수 있다.
- 긴 파일은 내부적으로 300초 chunking을 사용한다. chunk ON/OFF와 chunk seconds는 UI에 노출하지 않는다.
- retryable 네트워크·일시 오류는 각 chunk의 최초 요청 후 최대 1회 자동 재시도한다.
- 시스템 또는 네트워크 오류로 `FAILED`가 된 경우 정상 완료 chunk를 내부적으로 보존하고 Retry에서 재사용할 수 있다.
- 이 chunk 재사용은 사용자용 Resume가 아니다.
- 사용자가 STOP 또는 CANCEL하면 현재 파일의 chunk progress를 재사용하지 않고 Retry에서 파일 처음부터 처리한다.
- STOP은 `STOPPED`, CANCEL은 `CANCELLED`로 귀결한다.

## 파일명과 결과 bundle

- 긴 한글 파일명과 Windows 금지 문자를 안전하게 처리한다.
- Legacy의 page suffix 제거, `+` 변환, 공백·underscore 정리, 과정/과목 alias, 표준명 생성 기능을 유지한다.
- 기존 MP3/TXT/JSON/SRT와 batch 예약 번호를 고려해 preferred number 또는 다음 빈 강 번호를 배정한다.
- MP3와 same-stem TXT/JSON/SRT를 함께 rename하고 기존 파일을 overwrite하지 않는다.
- 정규화가 실패하거나 불확실하면 `원래 이름으로 계속`과 정규화 후보를 먼저 채운 `이름 수정`을 제공한다.
- 원래 이름으로 계속해도 Local 전사를 차단하지 않는다. 분류할 수 없는 파일은 Local 결과를 보존하고 Google Drive 업로드만 차단한다.
- TXT/JSON/SRT는 원본 MP3와 같은 폴더에 같은 stem으로 저장한다.
- 정상 완료에는 TXT/JSON/SRT가 모두 필요하다. TXT와 JSON은 non-empty, JSON은 object이며 `text`와 `segments`를 포함해야 한다. SRT는 존재해야 하며 무음 오디오는 0 byte를 허용한다.
- bundle 검증이 끝나기 전에는 `DONE` 또는 100% 완료로 표시하지 않는다.

## Google Drive

- Cloud storage는 Google Drive만 지원한다.
- OAuth 기반 업로드와 MP3/TXT/JSON/SRT 네 파일의 preflight validation을 유지한다.
- 업로드는 동일 parent/name의 파일을 중복 생성하지 않는 `update_or_create` 의미를 유지한다.
- Local 전사 상태와 Drive 상태를 분리한다. Drive 실패 또는 분류 차단은 Local `DONE`을 무효화하지 않는다.
- `local DONE + Drive FAILED`, Drive pending, uploading, failed를 사용자에게 구분해 표시한다.
- Legacy Drive Queue는 `DEPRECATED`이며 이식하지 않는다.

## Folders, Log, 설정과 Desktop UX

- Folders/Results와 완료 판정의 최종 truth는 전사 폴더의 실제 디스크 상태다.
- 앱 외부에서 파일을 추가·삭제·변경하면 refresh 시 반영한다.
- Folders는 전체/완료/미완료/결과 필터, 파일 정보, 결과 preview·전체 보기와 폴더 열기 흐름을 보존한다.
- 주요 화면은 `전사`, `로그`, `Folders`이며 기본 진입 화면은 `전사`다.
- 독립 Log Screen에서 실행 기록, 파일별 오류 원인, Retry/Stop/Cancel, Colab, Google Drive, 결과 검증, backend/runtime 상태를 구조화해 확인할 수 있어야 한다.
- Log는 raw console dump를 기본 목적으로 삼지 않는다.
- 알림 설정, 파일별·전체 완료 Notification, Tray의 앱 열기·종료, 실행 중 close-to-tray를 유지한다.
- 완료 후 PC 종료 선택과 countdown 취소 흐름을 유지한다.
- packaged FastAPI sidecar 자동 시작·health 확인, owned/external backend 구분, 안전한 process cleanup, MSI, Windows 한국어/Unicode 경로, 상태 persistence/recovery를 보존한다.

## 승인된 변경과 제외 범위

- 통계 전용 Dashboard 제거와 기본 `전사` 진입은 승인된 `INTENTIONAL_CHANGE`다. 기존 로그 기능은 독립 Log Screen으로 보존한다.
- Legacy PySide UI, stdout EVENT 통신, session 구조 같은 구현 방식은 기능 계약이 아니며 신규 구조의 dependency로 사용하지 않는다.
- Legacy Drive Queue, MYBOX, multi-provider cloud abstraction, 사용자용 mid-file Resume, 사용자용 Colab chunk 설정, 사용자용 Local Whisper 고급 옵션, 별도 output folder 설정은 이식 범위가 아니다.

## Deferred technical decisions

실제 디스크 truth를 만족할 Result 탐색/API 구조(D09), 구체 Log 저장 구조, 내부 persistence schema와 atomic bundle 교체 방식은 구현 단계까지 deferred한다. 이 기술 선택으로 위 사용자 계약을 변경하지 않는다.
