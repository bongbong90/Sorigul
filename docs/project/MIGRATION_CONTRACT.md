# Sorigul Migration Contract

Status: `LOCKED`

## 1. Purpose

이 문서는 Legacy Sorigul에서 신규 Tauri/FastAPI 기반 Sorigul로 이동할 때 지켜야 할 최종 제품 계약이다. Legacy에서 반드시 보존할 기능, 의도적으로 변경하는 동작, Local/Colab 공통 사용자 경험, 결과물과 Google Drive, 실패·중지·취소·복구, Folders와 Log, Desktop Runtime의 경계를 잠근다.

이 문서는 제품 행동의 기준이며 특정 Backend/UI 구현안을 설계하는 문서가 아니다. 구현은 이 계약을 만족해야 하고, 계약에 없는 기술 선택은 제품 정책으로 간주하지 않는다.

## 2. Evidence Baseline

### 2.1 Evidence priority

Legacy 동작 판단에는 다음 우선순위를 적용한다.

1. 현재 Legacy main runtime source
2. probes, tests, installed validation
3. 최신 inventory, architecture, release 문서
4. archive, 과거 계획, POC

증거가 충돌하면 하위 우선순위의 오래된 문서를 임의로 기준으로 삼지 않는다. 관찰된 구현 결함도 제품 정책으로 승격하지 않는다.

### 2.2 Baselines

- Legacy evidence baseline: `bongbong90/jeonsa_doumi` `main` / `fbc86313a179a62a586386551f99384a9fce5fc8`
- Sorigul Feature Parity Audit source baseline: `audit/legacy-feature-parity` / `154e550e6aefd4dfecd5e0140d0ff1f69bf17f5c`
- Migration Contract writing branch: `docs/migration-contract-review`
- Migration Contract writing baseline HEAD: `b7cc7cbeb78a8f96b231687f5615bfa0c0d94350`

Audit source baseline은 기능 증거를 수집한 기준이고, Contract writing HEAD는 이 문서를 작성하기 시작한 저장소 기준이다. 두 기준을 서로 대체하거나 혼동하지 않는다.

## 3. Contract Principles

1. **No silent feature loss**: ACTIVE Legacy 기능은 보존하거나 `INTENTIONAL_CHANGE`로 명시해야 한다. 단순 누락은 허용하지 않는다.
2. **Result integrity first**: 파일 상태보다 결과물 검증을 우선하며, 정상 TXT/JSON/SRT bundle 없이는 `DONE`으로 인정하지 않는다.
3. **Preserve successful work**: 부분 실패, Retry, 앱 재시작, 재전사 과정에서 이미 검증된 결과를 불필요하게 삭제하거나 다시 처리하지 않는다.
4. **Local/Colab user parity**: 내부 엔진과 복구 방식은 달라도 STOP, CANCEL, Retry, 완료 보존, 현재 파일 재시작 단위는 사용자 관점에서 일관되어야 한다.
5. **Local success is independent of Drive**: Google Drive 실패나 분류 차단은 로컬 전사 성공을 무효화하지 않는다.
6. **Disk is the result authority**: 사용자가 보는 Folders/Results와 완료 판정의 최종 기준은 실제 디스크 bundle이다.
7. **Product policy and implementation choice are separate**: 사용자가 확정한 행동은 잠그되, 이를 구현할 내부 구조는 필요한 시점까지 deferred할 수 있다.
8. **Explicit destructive intent**: 정상 완료 결과의 재생성은 사용자가 `다시 전사`를 명시적으로 선택한 경우에만 허용하며 기존 정상 결과를 안전하게 보호한다.

## 4. Locked Legacy Contracts

다음 Legacy 계약은 증거에 의해 잠겨 있으며, 뒤 섹션의 상세 계약과 함께 보존한다.

- Local Whisper `medium`, CUDA 우선, CPU fallback, fp16 판단 및 fallback
- TXT/JSON/SRT 생성과 정상 bundle 검증
- TXT/JSON non-empty, JSON `text`/`segments`, SRT 존재 및 무음 시 0 byte 허용
- Google Drive only, OAuth Drive, MP3/TXT/JSON/SRT 4-file upload
- Drive `update_or_create`, 동일 parent/name 재업로드 중복 방지, preflight validation
- 로컬 전사 상태와 Drive 업로드 상태 분리
- 파일명 정규화, batch number reservation, same-stem bundle rename, overwrite 금지
- Folders 실제 결과 탐색 기능
- packaged FastAPI sidecar lifecycle, owned/external backend 구분과 안전한 cleanup
- Tray, 완료 알림, PC 자동 종료
- MSI, Windows 한국어/Unicode 경로, persistence/recovery

Legacy Drive Queue는 ACTIVE 계약이 아니라 `DEPRECATED` 경로이며 이식 대상이 아니다. Legacy Dashboard는 ACTIVE였지만 D10 사용자 결정에 따라 섹션 5의 `INTENTIONAL_CHANGE`로 제거한다.

## 5. Intentional Changes

다음은 Legacy 보존 누락이 아니라 승인된 `INTENTIONAL_CHANGE`다.

| ID | Intentional change |
| --- | --- |
| D01 | 아무 파일도 선택하지 않은 Start를 즉시 전체 실행하지 않고, 완료 bundle을 제외한 전체 처리 범위를 확인받는다. |
| D03 | 기본 완료 skip은 유지하면서 보조 액션 `다시 전사`를 추가한다. |
| D05 | 파일명 정규화가 불확실할 때 무조건 진행하는 대신 `원래 이름으로 계속` 또는 `이름 수정`을 사용자가 선택한다. |
| D04 | 사용자용 mid-file Resume를 도입하지 않으며 중단 중이던 현재 파일은 처음부터 처리한다. |
| D08 | Direct Colab의 300초 chunking을 내부 정책으로 두고 chunk 설정을 UI에서 제거한다. |
| D10 | 누적 통계 중심 Dashboard 전용 화면을 제거하고 기본 진입 화면을 `전사`로 변경한다. |
| D10 | 기존 전사 화면의 로그를 제거하지 않고 별도의 구조화된 `로그` 화면으로 분리한다. |

## 6. Transcription Contract

### 6.1 Start and selection

- 사용자가 하나 이상의 파일을 선택하면 선택한 미완료 파일을 처리한다.
- 아무 파일도 선택하지 않아도 Start 버튼은 사용할 수 있다.
- no-selection 상태에서 Start를 누르면 전체 전사 여부를 확인한다.
- 확인 UI에는 가능한 범위에서 전체 파일 수, 정상 완료 bundle로 skip되는 수, 실제 처리 대상 수를 표시한다.
- 확인하면 완료 파일을 제외한 미완료 대상 전체를 실행하고, 취소하면 Job이나 파일 상태를 변경하지 않은 채 아무 작업도 시작하지 않는다.
- 실제 처리 대상이 0개이면 전사를 시작하지 않고 처리할 대상이 없음을 안내한다.

### 6.2 Completion and skip

- 완료 판정은 같은 stem의 정상 TXT/JSON/SRT bundle을 기준으로 한다.
- 정상 완료 파일은 일반 Start와 Retry에서 자동 skip한다.
- Job 이력만으로 파일을 `DONE`으로 간주하거나, 기존 완료 파일을 일괄 `WAITING`으로 되돌리지 않는다.
- `DONE`은 전사와 bundle 검증을 모두 통과했음을 뜻한다.

### 6.3 Batch behavior

- 단일 파일 실패는 해당 파일을 `FAILED`로 남기고 다음 파일 처리를 계속한다.
- 성공한 파일과 결과물은 부분 실패와 관계없이 보존한다.
- 전체 작업 종료 시 성공 수와 실패 수를 구분해 표시한다.
- 실패한 파일만 다시 시도할 수 있어야 한다.
- 이후 파일도 정상 처리할 수 없는 공통·치명 오류는 전체 작업을 중단할 수 있다. 예시는 모델 로드 자체 실패, 모든 device fallback 실패, Colab 서버/엔진 준비 실패, 결과 디렉터리 전체 쓰기 불가, 저장 공간 부족이다.

### 6.4 Explicit retranscription

- 완료 파일은 사용자가 `다시 전사`를 명시적으로 선택한 경우에만 재전사한다.
- `다시 전사`는 주 작업 버튼이 아니라 우클릭 또는 `⋯` 등의 보조 액션이다.
- 재전사 시작과 동시에 기존 정상 bundle을 삭제하지 않는다.
- 새 bundle을 생성하고 검증한 뒤에만 기존 정상 bundle을 교체한다.
- 재전사가 실패하면 기존 정상 bundle을 보존한다.

## 7. Failure / Retry / Recovery Contract

### 7.1 User-visible states

| State | Contract |
| --- | --- |
| `WAITING` | 실행 대상으로 대기 중이며 아직 전사를 시작하지 않았다. |
| `TRANSCRIBING` | 현재 전사 중이다. |
| `DONE` | TXT/JSON/SRT 정상 bundle 검증까지 통과했다. |
| `FAILED` | 파일 처리 또는 결과 검증에 실패했다. 오류 이유를 확인할 수 있어야 한다. |
| `STOPPED` | 실행 중이던 전사를 사용자가 중지했다. |
| `CANCELLED` | 대기 또는 작업 자체를 사용자가 취소했다. |
| `CRASHED` | 앱 비정상 종료로 이전 실행이 정상 종결되지 않았다. |

`STOPPED`와 `CANCELLED`는 의미와 UI 상태를 합치지 않는다. 기존 chunk cancel이 `FAILED`로 끝나는 관찰 동작은 제품 정책이 아니라 수정 대상 결함이다.

### 7.2 Retry eligibility and scope

- `FAILED`, `STOPPED`, `CANCELLED`, `CRASHED` 파일은 사용자가 다시 시도할 수 있다.
- Retry 시 `DONE` 파일과 정상 bundle을 그대로 유지하고 skip한다.
- Retry는 미완료 파일만 처리하며 전체 파일을 `WAITING`으로 초기화하지 않는다.
- 일반 Retry는 정상 완료 파일을 다시 처리하지 않는다. 완료 파일 재생성은 명시적 `다시 전사` 계약을 따른다.

### 7.3 Stop, cancel, and current file

- 사용자용 mid-file Resume는 Local과 Colab 모두 제공하지 않는다.
- `STOPPED` 또는 `CANCELLED` 당시 처리 중이던 현재 파일은 Retry 시 처음부터 전사한다.
- 이미 완료된 다른 파일과 정상 bundle은 보존한다.
- Local과 Colab의 내부 처리 차이가 이 사용자 계약을 바꾸어서는 안 된다.

### 7.4 Crash recovery

- 앱 시작 시 종결되지 않은 이전 Job을 `CRASHED`로 표시한다.
- 앱 시작만으로 전사를 자동 재개하지 않는다.
- 완료 파일과 정상 bundle은 보존한다.
- 사용자가 `다시 시도`를 눌렀을 때 미완료 파일만 처리하고, 비정상 종료 당시 처리 중이던 파일은 처음부터 전사한다.

### 7.5 Mid-file Resume decision background

현재 OpenAI Whisper Local의 `clip_timestamps`를 사용하면 특정 timestamp부터 전사 자체는 가능하지만, 공식 API에는 제품 수준의 안전한 중간 segment/checkpoint callback이 없다. stdout parsing과 monkey patch는 안정적인 제품 계약을 만들 근거가 아니다. `faster-whisper`는 generator 기반 checkpoint 구현 가능성이 있지만 현재 사용 환경에서 PC 성능과 사용성에 적절하지 않다.

따라서 사용자용 "중지 지점부터 이어하기"는 도입하지 않는다. Local과 Colab 양쪽에서 일관된 기능으로 제공할 수 있을 때만 향후 변경 관리 대상으로 검토한다. Colab 내부 chunk 재사용은 사용자용 Resume가 아니라 `FAILED` 복구 최적화다.

## 8. Local Whisper Contract

- Engine: 기존 OpenAI Whisper Local을 유지한다.
- Model: `medium`
- Device: CUDA를 우선하고 GPU/model load 실패 시 CPU로 fallback한다.
- Precision: fp16 가능 여부를 자동 판단하고 필요 시 안전하게 fallback한다.
- `language="ko"`
- `task="transcribe"`
- `temperature=0`
- `beam_size=5`
- `best_of=5`
- `patience=1.0`
- `condition_on_previous_text=False`
- 이 추론 옵션은 일반 사용자 설정으로 노출하지 않는다.
- Resume 구현을 목적으로 Local 엔진을 `faster-whisper`로 변경하지 않는다.

## 9. Direct Colab Contract

### 9.1 Internal chunking

- 긴 파일 안정성을 위해 300초 chunking을 내부 기본값으로 사용한다.
- 사용자는 이를 단순한 `Colab 전사`로 인식한다.
- chunk ON/OFF나 chunk seconds 설정을 사용자 UI에 노출하지 않는다.

### 9.2 FAILED recovery

- 시스템 또는 네트워크 오류로 동일 작업이 `FAILED`되면 이미 정상 완료된 chunk 결과를 내부적으로 보존할 수 있다.
- 사용자가 다시 시도하면 완료 chunk를 재사용하고 실패·미완료 chunk부터 처리할 수 있다.
- 이 동작은 내부 복구 최적화이며 사용자용 mid-file Resume가 아니다.

### 9.3 Automatic retry limit

- retryable 네트워크·일시 오류에 한해 각 chunk의 최초 요청 후 자동 재시도를 최대 1회 허용한다.
- 무한 자동 재시도는 금지한다.
- 자동 재시도까지 실패하면 해당 작업을 `FAILED` 처리한다.
- 사용자가 명시적으로 다시 시도한 실행에도 같은 chunk별 자동 재시도 상한을 적용한다.

### 9.4 User STOP/CANCEL

- 사용자가 직접 STOP 또는 CANCEL한 경우 해당 미완료 파일의 chunk progress를 다음 실행에 재사용하지 않는다.
- Retry 시 현재 파일을 처음부터 처리한다.
- STOP은 `STOPPED`, CANCEL은 `CANCELLED`로 귀결해야 한다.

## 10. Filename Contract

### 10.1 Preserved normalization behavior

파일명 정규화는 다음 Legacy 기능을 보존한다.

- page suffix 제거
- `+`를 space로 변환
- Windows forbidden character 처리
- space/underscore 정리
- extension 유지
- course/subject alias 적용
- 표준명 생성
- 기존 lesson number 탐색
- preferred number 또는 first-free number 선택
- batch 내 number reservation
- MP3와 same-stem TXT/JSON/SRT를 함께 rename
- 기존 파일 overwrite 금지

### 10.2 Uncertain or failed normalization

- 정규화가 실패하거나 결과를 확신하기 어려우면 `원래 이름으로 계속`과 `이름 수정`을 제공한다.
- `이름 수정`에는 Sorigul이 분석한 정규화 후보를 먼저 표시한다.
- 사용자는 후보를 그대로 적용하거나 직접 수정할 수 있다.
- 적용 전에 Windows 금지문자, 경로/이름 충돌, 중복을 검증한다.
- `원래 이름으로 계속`을 선택해도 로컬 전사를 차단하지 않는다.
- 표준 분류가 불가능하면 로컬 결과를 정상 보존하고 Google Drive 업로드만 차단한다.
- Drive 분류 차단을 로컬 전사 `FAILED`로 취급하지 않는다.

## 11. Output Bundle Contract

### 11.1 Location and naming

TXT, JSON, SRT는 항상 원본 MP3와 같은 폴더에 같은 stem으로 저장한다. 사용자용 별도 output folder 설정은 제공하지 않는다.

```text
lecture.mp3
lecture.txt
lecture.json
lecture.srt
```

### 11.2 Validation

정상 완료 bundle은 TXT, JSON, SRT 세 파일 모두를 포함한다.

- TXT: 존재하고 non-empty여야 한다.
- JSON: 존재하고 non-empty이며 JSON object여야 한다.
- JSON: `text`와 `segments` 필드를 포함해야 한다.
- SRT: 반드시 존재해야 한다.
- SRT: 무음 오디오에서는 0 byte를 허용한다.

일부 파일 생성만 성공했거나 검증이 실패한 bundle은 정상 완료가 아니다. 이 경우 파일을 `DONE`으로 표시하지 않으며 결과 검증 실패를 사용자 상태와 Log에 드러내야 한다.

## 12. Google Drive Contract

- Sorigul의 cloud storage는 Google Drive만 지원한다.
- MYBOX를 지원하지 않으며 multi-provider abstraction을 제품 범위로 두지 않는다.
- Legacy Drive Queue는 `DEPRECATED`이며 이식하지 않는다.
- OAuth 기반 Google Drive 기능을 유지한다.
- 업로드 bundle은 정확히 MP3, TXT, JSON, SRT 네 파일이다.
- 업로드 전 4-file bundle과 Drive 분류에 대한 preflight validation을 유지한다.
- 업로드는 `update_or_create` 의미를 유지한다.
- 동일 parent/name으로 다시 업로드할 때 중복 파일을 만들지 않는다.
- Drive 업로드 실패나 분류 차단은 정상 로컬 전사 결과를 삭제하거나 로컬 상태를 `FAILED`로 바꾸지 않는다.
- `local DONE + Drive FAILED`를 동시에 표현할 수 있어야 한다.
- Drive pending, uploading, failed 상태는 로컬 전사 상태와 별도로 표현할 수 있어야 한다.
- 단일 Google 계정만 허용할지 같은 계정 개수 정책은 이 계약에서 새로 고정하지 않는다.

## 13. Folders / Results Contract

- Folders/Results의 최종 source of truth는 전사 폴더의 실제 디스크 상태다.
- 사용자가 앱 외부에서 파일을 추가, 삭제, 변경하면 새로고침 시 Sorigul 화면에 반영한다.
- Job history와 실제 디스크 상태가 충돌하면 사용자가 보는 결과 상태는 실제 파일 상태를 따른다.
- 완료 판정은 MP3와 같은 stem의 실제 TXT/JSON/SRT 정상 bundle을 기준으로 한다.
- 기존 API의 `outputs=None`은 사용자 정책이 아니라 해결해야 할 구현/API 문제다.
- filesystem scan, Job API outputs, separate Results API, hybrid reconcile 중 어느 방식을 사용할지는 섹션 17의 deferred technical decision이다.

## 14. Log Screen Contract

### 14.1 Navigation and role

- 기본 주요 화면은 `전사`, `로그`, `Folders`로 구성한다.
- 기본 진입 화면은 `전사`다.
- Legacy 전사 화면 내부의 로그 기능은 제거하지 않고 별도 `로그` 화면으로 분리한다.
- 로그는 raw 개발자 console이 아니라 사용자가 실행 결과와 문제를 이해할 수 있는 구조화된 기록이다.

### 14.2 Required event coverage

로그는 적어도 다음 사건을 의미 있게 표현할 수 있어야 한다.

- 전사 시작과 완료
- 파일별 `DONE`과 `FAILED`
- `STOPPED`, `CANCELLED`
- Retry
- `CRASHED` 감지
- Colab 연결 성공과 실패
- Colab 자동 재시도
- Google Drive 업로드 시작, 성공, 실패
- 결과 bundle 검증 실패
- backend/runtime 오류

### 14.3 Presentation principles

- 기본 로그에 raw tqdm, stdout spam, 전체 내부 stack trace, chunk 구현 세부를 과도하게 노출하지 않는다.
- 필요한 상세 진단 정보는 오류 상세보기 같은 제한된 경로에서 제공할 수 있다.
- `전체`, `성공`, `경고`, `오류` 수준의 필터와 로그 복사 기능은 후속 UI 설계에서 검토할 수 있으며 구체 UI는 아직 고정하지 않는다.

## 15. Desktop Runtime Contract

기존 설치형 제품의 다음 기능을 보존한다.

- packaged FastAPI sidecar
- Desktop 앱의 backend 자동 시작
- `/api/health` 기반 readiness 확인
- 앱이 소유한 backend와 사용자가 외부에서 실행한 backend 구분
- 앱 종료 시 owned backend process tree cleanup
- external backend process 보호
- port conflict의 안전한 처리
- backend console 비노출
- MSI 설치 패키지
- Windows 한국어/Unicode 경로 지원
- 실행 상태 persistence와 비정상 종료 recovery
- 종료 후 port 8000 orphan process를 남기지 않음
- Tray 아이콘 제어
- 완료 알림
- 사용자 선택에 따른 PC 자동 종료

Tray, 알림, 종료의 구체 UI는 후속 UI Gap Closure에서 설계하되 기능을 누락하지 않는다.

## 16. Deprecated / Excluded Features

다음은 이번 마이그레이션의 지원 범위가 아니다.

- Legacy Google Drive Queue (`DEPRECATED`)
- MYBOX
- multi-provider cloud abstraction
- 통계 Dashboard 전용 화면과 Dashboard 전용 통계 카드
- 사용자용 mid-file Resume
- Resume 목적의 `faster-whisper` 전환
- 사용자용 Colab chunk ON/OFF 및 chunk seconds 설정
- 사용자용 Local Whisper 고급 추론 옵션 설정
- 사용자용 별도 output folder 설정

이 목록은 관련 구현을 조용히 누락할 수 있다는 뜻이 아니다. 보존 계약은 구현해야 하며, 제외·변경 항목은 사용자 경험과 문서에서 일관되어야 한다.

## 17. Technical Decisions Deferred

다음은 제품 행동이 아니라 구현 단계에서 결정할 기술 선택이다.

- D09 실제 디스크 source of truth를 만족할 결과 탐색 구조
  - filesystem scan
  - Job API outputs
  - separate Results API
  - hybrid reconcile
- Backend Result API의 구체 endpoint, schema, reconciliation 계약
- Log persistence의 저장 위치, 포맷, 보존 기간
- Log 필터의 구체 UI와 검색/복사 동작
- 재전사 시 검증된 bundle을 atomic하게 교체하는 구체 방식
- 상태 및 Drive 상태를 영속화하는 내부 schema

Deferred 항목은 구현자가 선택할 수 있지만 섹션 3~16의 사용자 계약을 바꿀 수 없다. 선택 결과가 사용자 행동을 변경한다면 기술 결정이 아니라 Contract 변경으로 다시 검토해야 한다.

## 18. UI Freeze Requirements

UI Freeze 전에 다음 상태와 흐름이 설계·검증되어야 한다.

- `WAITING`, `TRANSCRIBING`, `DONE`, `FAILED`, `STOPPED`, `CANCELLED`, `CRASHED`
- Retry eligibility와 미완료 파일만 처리하는 범위
- 개별 실패 후 다음 파일 계속 진행 및 배치 성공/실패 수
- 결과 bundle 검증 실패
- Drive pending, uploading, failed와 local `DONE`의 동시 표현
- Colab 연결 성공/실패와 제한된 자동 재시도
- 파일명 정규화 후보 확인, 원래 이름 진행, 이름 수정
- 정상 완료 파일 자동 skip과 보조 `다시 전사`
- no-selection 전체 전사 confirmation 및 처리 대상 0개 안내
- 독립된 구조화 `로그` 화면
- Folders의 actual-file refresh와 외부 변경 반영
- Tray, 알림, PC 자동 종료 진입점

기존 Dashboard 관련 UI Freeze blocker는 Dashboard 유지가 아니라 `INTENTIONAL_CHANGE`인 Dashboard 제거, 기본 `전사` 진입, `로그` 화면 분리에 맞게 재작성해야 한다. 실제 UI 문서 변경은 별도 작업에서 수행한다.

## 19. Acceptance Criteria

Contract를 만족하는 구현과 후속 문서는 다음 조건을 모두 충족해야 한다.

- D01~D10의 확정 사용자 결정이 반영되어 있다.
- 제품 결정 영역에 미결정 `NONE`이 남아 있지 않다.
- D09의 내부 구현 방식만 deferred technical decision으로 남는다.
- 기능 누락 금지와 결과물 무결성 우선 원칙을 유지한다.
- no-selection Start가 확인 후 미완료 전체를 처리한다.
- 개별 실패가 다음 파일 진행을 막지 않으며 공통·치명 오류만 전체 중단할 수 있다.
- 일반 Start/Retry는 완료 bundle을 skip하고 명시적 `다시 전사`만 완료 파일을 재처리한다.
- 재전사 실패 시 기존 정상 bundle을 보존한다.
- `STOPPED`, `CANCELLED`, `CRASHED`를 구분하고 수동 Retry 범위를 지킨다.
- 사용자용 mid-file Resume를 제공하지 않고 현재 파일을 처음부터 처리한다.
- Local Whisper `medium`과 고정 추론 옵션을 유지한다.
- Colab 300초 chunking은 UI에 노출하지 않으며 자동 재시도 상한을 지킨다.
- `FAILED`의 완료 chunk 재사용과 사용자 STOP/CANCEL 후 현재 파일 처음부터 처리를 구분한다.
- TXT/JSON/SRT 정상 bundle 검증 없이는 `DONE`으로 인정하지 않는다.
- 결과는 항상 원본 MP3와 같은 폴더에 저장한다.
- Google Drive 4-file bundle, `update_or_create`, preflight validation을 유지한다.
- Drive Queue, MYBOX, multi-provider abstraction을 도입하지 않는다.
- Drive 실패와 로컬 전사 성공을 분리한다.
- 파일명 정규화 실패 시 사용자 선택과 Drive-only 차단을 제공한다.
- Folders/Results가 실제 디스크 상태와 외부 변경을 반영한다.
- Dashboard 제거가 `INTENTIONAL_CHANGE`로 기록되어 있다.
- 기존 로그 기능이 구조화된 독립 화면으로 보존된다.
- Desktop Runtime, Tray, 알림, 종료 계약이 보존된다.

## 20. Change Control

- 이 문서가 승인되면 마이그레이션 제품 행동의 단일 기준으로 사용한다.
- 구현 편의, 기존 mock, 관찰된 defect, 오래된 문서는 이 계약을 암묵적으로 변경할 수 없다.
- Contract와 다른 동작이 필요하면 변경 이유, 사용자 영향, parity 영향, 결과물/복구 위험을 문서화하고 사용자 승인을 받아야 한다.
- 변경은 보존 계약, `INTENTIONAL_CHANGE`, deferred technical decision 중 어느 범주인지 명시한다.
- deferred technical decision의 해소는 사용자 계약을 변경하지 않는 범위에서만 별도 구현 문서로 기록할 수 있다.
- 후속 `FEATURE_PARITY.md`, `ROADMAP.md`, UI 문서와 구현은 이 Contract를 기준으로 정렬한다.
- 이 문서의 작성만으로 제품 코드, UI, Backend 또는 Runtime 구현이 변경된 것으로 간주하지 않는다.
