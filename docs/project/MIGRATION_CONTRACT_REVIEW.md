# Sorigul Migration Contract Review

## 1. Purpose
이 문서는 Legacy Feature Parity Audit에서 발견된 Legacy PySide와 신규 Tauri/FastAPI 간의 기능 충돌 및 미결 사항을 구조화하고, 사용자가 내린 최종 제품 결정을 기록하는 Decision Review 문서다.
선택 당시 검토한 대안과 영향도(기능/UI/Backend/회귀)는 근거로 보존하며, 확정 계약은 `MIGRATION_CONTRACT.md`에 잠근다.

## 2. Source Baselines
- Sorigul baseline: `audit/legacy-feature-parity` / `154e550e6aefd4dfecd5e0140d0ff1f69bf17f5c`
- Legacy baseline: `bongbong90/jeonsa_doumi` `main` / `fbc86313a179a62a586386551f99384a9fce5fc8`

## 3. Review Rules
- **증거 수집 → 충돌 구조화 → 선택지 작성 → 영향 분석 → 사용자 검토 → 사용자 결정**의 과정을 거친다.
- 본 문서의 최종 결정은 사용자가 내리며, 결정 후에는 선택지와 함께 최종 사용자 계약 문장을 기록한다.
- 각 Decision의 기본 상태는 `UNDECIDED`, `TECHNICAL_DECISION`, `PRODUCT_DECISION`, `USER_DECISION_REQUIRED` 등으로 분류한다.
- `Selected option`은 결정이 내려지기 전까지 `NONE`을 유지한다. 제품 결정이 확정된 항목에는 `NONE`을 남기지 않으며, 아직 제품 결정 대상이 아닌 기술 구현 선택만 명시적으로 deferred 상태로 둘 수 있다.

## 4. Already Locked Contracts
다음 항목들은 Audit 과정에서 충분한 근거가 확인되어, 더 이상 논의가 필요 없는 확정 계약(LOCKED_BY_EVIDENCE)이다.

- **Google Drive 지원**: Google Drive only (MYBOX 및 다중 Cloud Provider 미지원. 단, 단일 계정 여부 등 계정 개수 정책은 새 계약으로 확정하지 않음)
- **Drive Queue 폐기**: Legacy Drive Queue 경로는 DEPRECATED이며 이식하지 않음
- **산출물 Bundle**: TXT, JSON, SRT 3종 생성 및 검증
- **결과물 유효성**: TXT/JSON은 빈 파일 불가(nonempty), JSON은 `text`, `segments` 필수, SRT는 생성되나 0 byte 허용
- **Drive 업로드 4종**: MP3, TXT, JSON, SRT 4종 번들 업로드 확정
- **Drive 업로드 정책**: 동일 경로/이름 존재 시 `update_or_create` 확정
- **상태 분리**: 전사 성공(DONE)과 Drive 업로드 실패(FAILED)는 별개의 상태로 분리 (전사 Job 전체 FAILED 처리 금지)
- **Folders**: 실제 결과 파일을 탐색하는 제품 내 ACTIVE 기능으로 유지 확정
- **Dashboard**: Legacy에서는 ACTIVE였으나, 사용자 결정 D10에 따라 Sorigul의 통계 전용 Dashboard는 `INTENTIONAL_CHANGE`로 제거
- **Tray / Notification / Shutdown**: 완료 후 알림, Tray 아이콘 제어, PC 자동 종료 ACTIVE 기능으로 유지 확정
- **Desktop Runtime**: sidecar lifecycle 자동 시작 및 종료 cleanup 유지 확정
- **Packaging**: MSI 설치, Windows 한국어(Unicode) 경로 및 runtime 지원 요구사항 확정

## 5. Decision Register

### D01 — 선택 없음 상태의 Start 의미

Status:
DECIDED (USER_APPROVED)

Related Audit IDs:
TR-002, B01

Related UI Freeze Blockers:
B01

Legacy Path A (PySide):
`gui_main.py`에서는 리스트에서 체크된 행이 있으면 선택분만 전사하고, 하나도 없으면 전체 목록을 전사한다.

Evidence:
`gui_main.py::run_transcribe_process`

Legacy Path B / Current Sorigul (Mock):
Sorigul Mock UI에서는 아무것도 선택되지 않으면 Start 버튼 자체가 비활성화(disabled)된다.

Evidence:
Sorigul Transcription Mock Interaction 설계

Conflict:
선택이 없을 때 '전체 실행'으로 간주할지, '실행 불가'로 간주할지가 충돌한다.

Option A:
체크된 항목이 없을 때 '전체 전사'를 수행한다 (Legacy PySide 방식 유지).

Option B:
체크된 항목이 없을 때 Start 버튼을 비활성화한다 (Sorigul Mock 방식 채택).

Option C:
선택 항목이 없을 때 명시적인 경고 다이얼로그로 확인을 받는다.

Parity impact:
Option A 선택 시 Legacy UX 완벽 유지. Option B 선택 시 명시적 변경(Intentional Change).

User-visible impact:
Option B의 경우 사용자가 '전체 선택' 버튼을 명시적으로 누르거나 항목을 일일이 선택해야 Start 가능.

UI impact:
Start 버튼의 활성화/비활성화 조건 및 '전체 선택' 체크박스의 필요성 변동.

Backend impact:
Backend Start API로 전달되는 payload 구성 방식의 차이.

Regression risk:
Option B 채택 시 기존 방식에 익숙한 사용자가 Start 버튼이 왜 눌리지 않는지 혼란을 겪을 위험 존재.

Required validation:
빈 리스트 전달 시 Backend 처리 검증, Start 버튼 상태 전이 검증.

Selected option:
**A + C Hybrid**

Final user contract:
아무 파일도 선택하지 않아도 Start는 활성화한다. Start 클릭 시 전체 파일 수, 정상 완료 bundle로 skip되는 파일 수, 실제 처리 대상 수를 가능한 범위에서 표시하고 전체 전사 여부를 확인한다. 사용자가 확인하면 정상 완료 bundle을 제외한 미완료 대상 전체를 실행하며, 취소하면 아무 작업도 시작하지 않는다. 실제 처리 대상이 0개이면 전사를 시작하지 않고 처리할 대상이 없음을 안내한다.


### D02 — 부분 실패 처리

Status:
DECIDED (USER_APPROVED)

Related Audit IDs:
TR-007, LW-004, B02, Open Question 1

Related UI Freeze Blockers:
B02

Legacy Path A (PySide):
한 파일 처리가 실패해도 에러를 기록하고 다음 파일로 계속 진행한다.

Evidence:
`auto_transcribe.py::process_files`

Legacy Path B / Current Sorigul (Tauri):
첫 번째 파일 처리(또는 모델 로드, 파일 저장 등) 실패 시 Job 전체가 FAILED 상태로 종료된다.

Evidence:
`backend/services/local_whisper_service.py::run`

Conflict:
개별 파일 실패가 전체 배치 작업(Job) 중단으로 이어질 것인가에 대한 정책 충돌. 실패의 종류(모델 자체 로드 실패 vs 단일 MP3 실패 vs 저장 실패 vs 결과 검증 실패 등)에 따른 세분화도 필요하다. 서로 같은 policy로 묶어도 될지조차 아직 미정이다.

Option A:
어떤 실패든 발생하면 즉시 Job을 FAILED 처리하고 중단한다. (Tauri 방식)

Option B:
단일 파일 실패(예: 파싱, 변환 오류)는 무시하고 다음 파일로 계속 진행하며, 완료 후 실패 항목을 별도 표시한다. 모델 로드 등 치명적 오류시에만 중단한다. (PySide 방식)

Option C:
기본적으로 다음 파일로 진행하되, 특정 횟수 이상 연속 실패 시 중단하는 하이브리드 정책.

Parity impact:
Option B 선택 시 Legacy 유지. Option A 선택 시 다중 파일 전사 중 중단 경험 발생.

User-visible impact:
대량 작업 걸어놓고 자리 비웠을 때, 중간에 하나 실패로 멈춰 있을지, 끝까지 시도했을지의 차이.

UI impact:
부분 실패를 알리는 'PARTIAL_SUCCESS' 혹은 개별 파일별 에러 상태 표시 UI 필요.

Backend impact:
Job 상태 전이(RUNNING -> FAILED vs PARTIAL/DONE) 및 에러 누적 기록 방식 변경 필요.

Regression risk:
Option A 선택 시 대량 작업 안정성이 떨어졌다고 체감될 수 있음.

Required validation:
다중 파일 중 중간 파일 고의 실패 시나리오 검증.

Selected option:
**Option B — 개별 실패 후 계속 진행**

Final user contract:
특정 파일의 전사 또는 TXT/JSON/SRT 검증이 실패해도 해당 파일만 `FAILED`로 남기고 다음 파일을 계속 처리한다. 성공 파일과 정상 결과물은 보존하고, 배치 종료 시 성공/실패 수를 구분해 표시하며, 실패 파일만 다시 시도할 수 있어야 한다. 모델 로드, device fallback, Colab 엔진 준비, 결과 디렉터리 쓰기, 저장 공간처럼 이후 파일도 정상 처리할 수 없게 만드는 공통·치명 오류는 전체 작업을 중단할 수 있다. `DONE`은 TXT/JSON/SRT 정상 bundle 검증을 모두 통과한 경우에만 부여한다.


### D03 — DONE / 완료 bundle / 재전사

Status:
DECIDED (USER_APPROVED)

Related Audit IDs:
RC-003, B01, Open Question 2

Related UI Freeze Blockers:
B01

Legacy Path A (PySide):
이미 완료 bundle(TXT/JSON/SRT)이 존재하는 파일은 실행 목록에 있어도 실제 처리 대상에서 제외(skip)된다. 완료된 동일 Job을 다시 실행하는 것은 runner 레벨에서 거부된다.

Evidence:
`auto_transcribe.py::is_transcription_complete`, Job runner runnable set

Legacy Path B / Current Sorigul (Tauri):
신규 Tauri local job은 완료 bundle 존재 여부와 무관하게 대상 파일을 모두 WAITING으로 만들고 다시 전사한다.

Evidence:
Local adapter 코드

Conflict:
완료된 파일을 기본적으로 스킵할지, 덮어쓸지의 문제.
1) 같은 DONE Job 다시 실행
2) 완료 bundle이 존재하는 파일을 새 Job에 추가
3) 사용자가 의도적으로 다시 전사하려는 경우(강제 재전사)

Option A:
완료 파일은 무조건 skip하며, 강제 재전사 기능은 제공하지 않는다.

Option B:
완료 파일은 기본 skip하되, UI에 '강제 재전사' 버튼을 추가하여 선택적으로 덮어쓸 수 있게 한다.

Option C:
새로운 Job으로 실행 시 완료 여부와 무관하게 모두 재전사한다 (현재 Tauri 방식).

Parity impact:
Option B는 Legacy 유지에 명시적 기능 추가, Option C는 큰 Intentional Change.

User-visible impact:
동일 폴더 재실행 시 걸리는 시간(스킵으로 인한 즉시 완료 vs 전체 재수행).

UI impact:
'강제 재전사' 액션 버튼 및 개별 항목 스킵 상태 아이콘 필요 여부 미정.

Backend impact:
Job 생성 단계에서 파일 존재 여부 사전 검사 및 대상 필터링 로직 분리 여부.

Regression risk:
Option C 선택 시 사용자가 원치 않게 긴 전사 시간을 다시 기다려야 하는 불편.

Required validation:
재전사 시 기존 파일 덮어쓰기 동작, 스킵 시 진행률(전체 개수) 계산 보정.

Selected option:
**Option B 변형 — 기본 자동 skip + 보조 `다시 전사` 액션**

Final user contract:
정상 TXT/JSON/SRT bundle이 있는 파일은 일반 Start와 Retry에서 자동 skip한다. 완료 파일은 사용자가 우클릭 또는 `⋯` 등 보조 액션의 `다시 전사`를 명시적으로 선택한 경우에만 재전사한다. 재전사 시작 시 기존 정상 결과를 삭제하지 않으며, 새 bundle 생성과 검증이 성공한 뒤 기존 bundle을 교체한다. 재전사가 실패하면 기존 정상 결과를 보존한다.


### D04 — CANCELLED / STOPPED / Retry

Status:
DECIDED (USER_APPROVED)

Related Audit IDs:
RC-001, RC-002, RC-004, B01, B03, Open Question 3

Related UI Freeze Blockers:
B01, B03

이 항목은 여러 개의 독립적인 정책 축을 포함하고 있다. 하나의 옵션으로 강제하지 않고, 각 축을 개별적으로 결정할 수 있도록 분리한다.

| Axis | Legacy Evidence | Current Conflict | Options | Selected |
| --- | --- | --- | --- | --- |
| 상태 표현 | `STOPPED`와 `CANCELLED` 분리 존재 | 두 상태를 하나로 통합할지 여부 | 1) 두 상태 분리 유지<br>2) 하나의 중단 상태로 통합 | **1) 분리 유지** |
| Retry 가능 상태 | `CANCELLED`는 API/runner 허용, `STOPPED`는 API 거부 | 사용자 진입점 불일치 해결 및 재시도 허용 범위 | 1) 둘 다 Retry 허용<br>2) CANCELLED만 허용 | **1) 둘 다 Retry 허용** |
| 완료 파일 보존 | 재개 시 기존 완료 번들 스킵/보존 (PySide) | 재시도 시 기존 완료 파일을 초기화할지 여부 | 1) 기존 완료 파일 보존/스킵<br>2) 일괄 WAITING 초기화 (Tauri) | **1) 완료 파일 보존/skip** |
| 중단 파일 재시작 단위 | PySide Local은 중단된 파일 처음부터 | 재시작 시 단일 파일의 이어하기 지원 여부 | 1) 중단된 파일 처음부터 재전사<br>2) 청크 단위/중간 시점 재개 지원 | **1) 현재 파일 처음부터** |
| CRASHED recovery action | 실행 중 비정상 종료 시 `CRASHED` 전환 복구 | 재시작 후 비정상 종료된 작업의 처리 방식 | 1) CRASHED 상태로 두고 수동 재개 대기<br>2) 앱 구동 시 자동 재개 시도 | **1) CRASHED + 수동 Retry** |

Final user contract:
`STOPPED`는 실행 중인 전사를 사용자가 중지한 상태, `CANCELLED`는 대기 또는 작업 자체를 사용자가 취소한 상태로 구분해 표시하며 둘 다 Retry할 수 있다. Retry에서는 `DONE` 파일과 정상 bundle을 유지·skip하고 `FAILED`, `STOPPED`, `CANCELLED` 등 미완료 파일만 처리한다. 사용자용 mid-file Resume는 제공하지 않으므로 중단 중이던 현재 파일은 Local과 Colab 모두 처음부터 다시 처리한다. 앱 비정상 종료 후 이전 작업은 `CRASHED`로 표시하고 자동 재개하지 않으며, 완료 파일을 보존한 채 사용자가 `다시 시도`를 눌렀을 때만 미완료 파일을 처리한다.

Mid-file Resume investigation:
현재 OpenAI Whisper Local은 `clip_timestamps`로 특정 시점부터 전사할 수 있지만, 공식 API에 안전한 중간 segment/checkpoint callback이 없다. stdout parsing이나 monkey patch는 제품 구현에 적합하지 않다. `faster-whisper`는 generator 기반 checkpoint 가능성이 있으나 현재 사용 환경의 PC 성능과 사용성에 맞지 않으므로 엔진을 변경하지 않는다. 사용자용 "중지 지점부터 이어하기"는 Local과 Colab 양쪽에서 일관되게 제공할 수 있을 때만 다시 검토한다. Colab의 완료 chunk 재사용은 사용자용 Resume가 아닌 내부 실패 복구 최적화다.


### D05 — 파일명 정규화 감지 실패

Status:
DECIDED (USER_APPROVED)

Related Audit IDs:
FN-001~FN-004, B04, Open Question 4

Related UI Freeze Blockers:
B04

Legacy Path A (PySide):
정규화 감지(스마트 파일명 추출) 실패 시, 경고를 남기고 원래 파일명으로 전사를 계속한다.

Evidence:
`gui_main.py::_apply_smart_filename_normalization_before_transcribe`

Legacy Path B / Current Sorigul (Docs):
일부 최신 설명 문서에서는 감지 실패 시 작업을 차단(Block)한다고 기술되어 있음.

Evidence:
Sorigul 일부 정책 문서 (Audit B04 충돌)

Conflict:
파일명 정규화 실패 시 작업 강행 vs 사용자 확인 vs 강제 차단.

Option A:
경고 후 원래 이름으로 무조건 전사를 계속한다. (Legacy)

Option B:
감지 실패 시 작업을 차단하고 실패 처리한다. (Docs)

Option C:
실패 항목을 UI에서 하이라이트하고, 사용자가 '원래 이름으로 진행' 또는 '수동으로 이름 변경 후 진행'을 선택하게 한다.

Parity impact:
Option A가 Legacy 유지.

User-visible impact:
파일명 규칙에 맞지 않는 파일을 던졌을 때 에러 발생 여부 및 추가 클릭 필요성.

UI impact:
Option C 선택 시 충돌/실패 항목 리뷰 화면 및 결정 액션 UI 필요 (B04).

Backend impact:
Drive 업로드 분류 기능과의 연동. (Drive는 정규화된 과정을 기준으로 폴더를 찾으므로 원래 이름이면 Drive 업로드 실패 가능성).

Regression risk:
Option A 선택 시 Drive 폴더 분류 불능으로 Drive 업로드 단계에서 추가 에러 발생 가능성. Option B 선택 시 정상 전사되던 파일이 갑자기 거부되는 문제.

Required validation:
비표준 파일명 처리 전체 파이프라인(특히 Drive 업로드까지) 테스트.

Selected option:
**Option C — 사용자 선택**

Final user contract:
정규화가 실패하거나 확신하기 어려우면 `원래 이름으로 계속`과 `이름 수정`을 제공한다. 이름 수정에서는 Sorigul이 분석한 후보를 먼저 보여 주고 사용자가 그대로 적용하거나 직접 수정할 수 있게 하며, 적용 전 금지문자·충돌·중복을 검증한다. 원래 이름을 선택해도 로컬 전사는 차단하지 않는다. 표준 분류가 불가능하면 로컬 전사 결과는 정상 보존하고 Google Drive 업로드만 차단하며, 이를 로컬 전사 실패로 취급하지 않는다.


### D06 — 결과 저장 위치

Status:
DECIDED (USER_APPROVED)

Related Audit IDs:
Open Question 5

Related UI Freeze Blockers:
N/A

Legacy Path A (PySide):
전사 결과를 항상 원본 MP3 파일과 동일한 위치(옆)에 저장한다.

Evidence:
Legacy PySide 파일 저장 로직

Legacy Path B / Current Sorigul (Backend):
신규 백엔드는 API 호출 시 명시된 output folder를 지원하도록 설계됨.

Evidence:
Tauri local adapter 요청 구조

Conflict:
'작업 위치(Local working)'와 '사용자 결과 탐색 위치'의 결합 여부.
MP3 위치 강제 vs 전용 결과 폴더 지정 기능 제공 여부.

Option A:
무조건 MP3 파일 옆에 결과를 저장한다 (Legacy 유지).

Option B:
전역 설정에서 '전사 결과 저장 폴더'를 지정할 수 있게 하고 그곳에 모아 저장한다.

Option C:
기본은 MP3 옆이되, 설정에서 특정 출력 폴더를 덮어쓸 수 있도록 지원한다.

Parity impact:
Option A가 Legacy. B, C는 기능 추가.

User-visible impact:
결과물(TXT, SRT 등)을 찾을 위치 변경.

UI impact:
설정(Settings) 화면에 결과 저장 경로 지정 옵션 추가.

Backend impact:
저장 경로 분리 로직 및 Job 데이터에 output_dir 보존 여부. Drive 업로드 시 source 위치 탐색 로직 변경.

Regression risk:
MP3 옆에 파일이 생성되는 것에 의존하는 사용자들의 혼란.

Required validation:
output 폴더 지정 시 쓰기 권한, 디스크 용량, 원본 삭제 시나리오 검증.

Selected option:
**Option A — 항상 원본 MP3와 같은 폴더**

Final user contract:
TXT, JSON, SRT는 항상 원본 MP3와 같은 폴더에 같은 stem으로 저장한다. 사용자용 별도 output folder 설정은 제공하지 않는다.


### D07 — Whisper 옵션 parity

Status:
DECIDED (USER_APPROVED)

Related Audit IDs:
LW-004

Related UI Freeze Blockers:
N/A

**Locked / Migration Requirement**
다음 항목은 Audit을 통해 확정된 필수 구현 요구사항이며 선택 대상이 아니다. Fallback 보존 자체는 Option에서 제외된다.
- Local Whisper model = `medium`
- CUDA 우선
- GPU/model load 실패 시 CPU fallback
- fp16 실패 fallback

**Undecided Inference Options**
다음 추론(Inference) 옵션들은 Legacy 최적화 값과 Whisper 기본값 간에 차이가 있어 정책 결정이 필요하다.
- `language=ko`
- `task=transcribe`
- `temperature` (Legacy: 0)
- `beam_size` (Legacy: 5)
- `best_of` (Legacy: 5)
- `patience` (Legacy: 1)
- `condition_on_previous_text` (Legacy: false)

Conflict:
기존에 최적화 목적으로 지정된 추론 옵션을 신규 adapter에 어떻게 적용할 것인가?

Option A:
위 나열된 추론 옵션들을 신규 Backend에 Legacy와 동일하게 고정하여 완벽한 품질 파리티를 유지한다.

Option B:
Whisper 라이브러리의 기본 설정(plain 기본값)을 사용한다.

Option C:
사용자가 설정 화면에서 language, beam_size 등 고급 옵션을 제어할 수 있게 노출한다.

Parity impact:
Option A가 Inference 품질 파리티를 완벽히 유지.

User-visible impact:
옵션에 따른 퀄리티, 환각(hallucination) 발생 빈도 변화.

UI impact:
Option C 선택 시 고급 설정 화면 UI 필요.

Backend impact:
transcribe 파라미터 전달 로직 강제 여부.

Regression risk:
Option B 선택 시 과거에 해결했던 특정 오디오 포맷/무음 구간에서의 품질 이슈(반복 버그 등) 재현 위험.

Required validation:
동일 오디오에 대한 구버전/신버전 전사 결과 텍스트 품질 비교.

Selected option:
**Option A — Legacy Local Whisper 설정 고정**

Final user contract:
Local Whisper는 `medium`, CUDA 우선 및 CPU fallback, fp16 자동 판단과 필요 시 fallback을 유지한다. 추론 옵션은 `language="ko"`, `task="transcribe"`, `temperature=0`, `beam_size=5`, `best_of=5`, `patience=1.0`, `condition_on_previous_text=False`로 고정하고 일반 사용자 설정으로 노출하지 않는다. Resume를 위해 엔진을 `faster-whisper`로 변경하지 않는다.


### D08 — Colab chunk / resume / cancel

Status:
DECIDED (USER_APPROVED)

Related Audit IDs:
CO-001~CO-005, B05, Open Question 6

Related UI Freeze Blockers:
B05

**Implementation Defect (Not a Product Option)**
현재 backend에서 chunk 작업을 취소(cancel)할 때 상태가 `FAILED`로 귀결되는 현상은 제품 옵션이 아닌 '구현 결함(관찰값)'이다. 취소 시에는 `CANCELLED` 상태로 정상 귀결되도록 백엔드를 수정해야 하며, 제품 정책 후보에 포함하지 않는다.

**Decision Axes**
Colab 전사 기능의 세부 정책을 축별로 분리하여 결정한다.

| Axis | Legacy Evidence | Current Conflict | Options | Selected |
| --- | --- | --- | --- | --- |
| chunk 기본값 | 기본 300초 ON (PySide) | Backend는 기본 OFF | 1) OFF 기본<br>2) 300초 ON 기본<br>3) 오디오 길이에 따라 자동 활성화 | **2) 내부 300초 기본값** |
| chunk 길이 UI 노출 | 60~900초 제어 UI 존재 | 설정 복잡도 최소화 관점 | 1) 설정 화면에 제어 노출<br>2) 백엔드 고정값(내부 정책) 사용 | **2) UI 비노출** |
| file-level resume | `progress.json` 파일 단위 재개 | 파일 재개와 청크 재개의 중첩 동작 | 1) 파일 단위 재개 유지<br>2) 파일 단위 재개 지원 안 함 | **2) 사용자용 Resume 미지원** |
| chunk-level resume | 없음 (PySide 미지원) | Backend manifest 기반 청크 단위 재사용 | 1) 지원 안 함<br>2) 완료 청크 재사용 (세밀한 재개) | **2) FAILED 내부 복구에만 재사용** |
| cancel 결과 상태 | 파일 단위 CANCELLED | (버그 수정 전제로 고정됨) | CANCELLED로 고정 (Defect 수정) | **CANCELLED 고정** |
| cancel 시 완료 chunk | 지원 안 함 | 취소 후 기존 청크 유지/재사용 여부 | 1) 전부 폐기<br>2) 완료 청크 보존 및 재개 시 재사용 | **1) 현재 파일 progress 재사용 안 함** |

Final user contract:
Direct Colab은 긴 파일 안정성을 위해 300초 chunking을 내부 기본값으로 사용하되, chunk ON/OFF나 길이를 사용자 UI에 노출하지 않는다. 시스템·네트워크 오류로 동일 작업이 `FAILED`되면 정상 완료 chunk를 내부 보존하여 실패·미완료 chunk부터 처리할 수 있다. retryable 오류에 대한 자동 시도는 chunk당 최초 요청 후 최대 1회만 허용하며, 자동 재시도까지 실패하면 작업을 `FAILED` 처리한다. 수동 Retry에도 같은 상한을 적용한다. 사용자가 `STOP` 또는 `CANCEL`한 경우 현재 미완료 파일의 chunk progress는 다음 실행에 재사용하지 않고 파일 처음부터 처리한다. 기존 cancel이 `FAILED`가 되는 동작은 정책이 아닌 결함이며 `CANCELLED`로 수정해야 한다.


### D09 — 결과 파일 탐색 반영 규칙 (Product vs Technical Decision)

Status:
PRODUCT_DECIDED / TECHNICAL_DECISION_DEFERRED

Related Audit IDs:
NA-006, Open Question 7

Related UI Freeze Blockers:
B09 (Folders/Results)

**Product Decision (사용자 행동 계약)** (USER_APPROVED)
사용자가 탐색기 등 앱 외부에서 TXT/JSON/SRT 파일을 추가·삭제·변경했을 때 Sorigul Folders/Results 화면이 이를 반영해야 하는가?

Option A:
앱 외부의 파일 변경을 Folders 화면 새로고침 시 즉각 반영한다 (Legacy UX와 일치).

Option B:
앱 내에서 수행한 작업(Job 이력)만 보여주고, 외부 수정은 무시한다.

Selected option:
**Option A — 실제 디스크 상태 반영**

Final user contract:
Folders/Results 화면은 전사 폴더의 실제 파일을 최종 기준으로 한다. 사용자가 앱 외부에서 파일을 추가·삭제·변경하면 새로고침 시 반영하며, Job history와 디스크 상태가 충돌하면 사용자가 보는 결과 상태와 완료 판정은 실제 MP3 + TXT/JSON/SRT bundle 상태를 따른다.

**Technical Decision (내부 구현 방식)** (TECHNICAL_DECISION)
위 제품 계약(Product Decision)을 만족시키기 위한 백엔드 구현 기술. `outputs=None` 현상은 기존 API의 한계(UNKNOWN)일 뿐, 사용자가 기술 방식을 직접 선택해야 하는 근거가 아니다.

Option A: Filesystem scan (매번 디렉토리 읽어오기)
Option B: Job / API outputs 기반 노출
Option C: Separate Results API 구축
Option D: Hybrid / Reconcile (DB 이력과 파일 시스템 동기화)

Selected Option: NONE (TECHNICAL_DECISION_DEFERRED)

Deferred reason:
제품 계약은 실제 디스크 상태 반영으로 확정되었지만 이를 만족할 filesystem scan, Job API outputs, separate Results API, hybrid reconcile 중 어느 구조를 사용할지는 Backend 구현 단계의 기술 결정이다. `outputs=None`도 제품 정책이 아니라 기존 API/구현 문제로 남긴다.


### D10 — Dashboard 제거 / Log Screen 분리

Status:
DECIDED (USER_APPROVED, INTENTIONAL_CHANGE)

Related Audit Context:
Legacy Dashboard 및 전사 화면 내부 로그는 ACTIVE 기능이었다.

Selected option:
**통계 Dashboard 제거 + 구조화된 Log 화면 분리**

Final user contract:
Sorigul은 누적 완료 수, 누적 오디오 시간, 오늘 완료, 평균 전사 속도, 통계 카드와 Dashboard 전용 최근 완료 통계를 포함한 전용 Dashboard 화면을 제거한다. 이는 기능 누락이 아니라 `INTENTIONAL_CHANGE`이며 기본 진입 화면은 `전사`다. 기존 로그 기능은 제거하지 않고 별도의 `로그` 화면으로 분리하여 주요 화면을 `전사`, `로그`, `Folders`로 구성한다.

로그는 raw 개발자 console이 아니라 전사 시작·완료, 파일별 `DONE`/`FAILED`, `STOPPED`, `CANCELLED`, Retry, `CRASHED` 감지, Colab 연결과 자동 재시도, Google Drive 업로드, 결과 검증 실패, backend/runtime 오류 등 사용자에게 의미 있는 구조화된 실행 기록을 제공한다. 기본 화면에서 raw tqdm, stdout spam, 전체 stack trace, chunk 구현 세부를 과도하게 노출하지 않으며 필요한 진단 정보는 오류 상세보기 등에 제한할 수 있다. 성공·경고·오류 등의 필터와 로그 복사 기능의 구체 UI는 후속 UI 작업에서 검토한다.


## 6. UI Freeze Blocker Mapping

| Blocker | Related Decisions | Product Policy Needed | UI Design Needed | Backend Needed Later | Current State |
| ------- | ----------------- | --------------------- | ---------------- | -------------------- | ------------- |
| B01 | D01, D03, D04 | NO (LOCKED) | YES | YES | POLICY_LOCKED / UI_OPEN |
| B02 | D02 | NO (LOCKED) | YES | YES | POLICY_LOCKED / UI_OPEN |
| B03 | D04 | NO (LOCKED) | YES | YES | POLICY_LOCKED / UI_OPEN |
| B04 | D05 | NO (LOCKED) | YES | YES | POLICY_LOCKED / UI_OPEN |
| B05 | D08 | NO (LOCKED) | YES | YES | POLICY_LOCKED / UI_OPEN |
| B06 | N/A (Locked by Evidence) | NO | YES | YES | OPEN |
| B07 | N/A (Locked by Evidence) | NO | YES | YES | OPEN |
| B08 | N/A (Locked by Evidence) | NO | YES | YES | OPEN |
| B09 | D09 | NO (PRODUCT LOCKED) | YES | YES | TECHNICAL_DEFERRED / UI_OPEN |
| B10 | N/A (Locked by Evidence) | NO | YES | YES | OPEN |
| B11 | N/A (Locked by Evidence) | NO | YES | YES | OPEN |
| B12 | N/A (Locked by Evidence) | NO | YES | YES | OPEN |

D10에 따라 기존 Dashboard 유지 전제를 가진 blocker는 더 이상 유효하지 않다. 후속 UI Gap Closure에서는 전용 Dashboard 제거, 기본 `전사` 진입, 독립 `로그` 화면, `Folders` 구조를 기준으로 관련 blocker를 재작성해야 한다. 이 Review에서는 기존 blocker ID를 임의로 재배정하지 않는다.

### Blocker Type Mapping
- B01: POLICY_BLOCKER, UI_DESIGN_BLOCKER
- B02: STATE_MODEL_BLOCKER
- B03: STATE_MODEL_BLOCKER, BACKEND_CONTRACT_BLOCKER
- B04: POLICY_BLOCKER, UI_DESIGN_BLOCKER
- B05: POLICY_BLOCKER, UI_DESIGN_BLOCKER
- B06: UI_DESIGN_BLOCKER, STATE_MODEL_BLOCKER
- B07: UI_DESIGN_BLOCKER
- B08: UI_DESIGN_BLOCKER
- B09: UI_DESIGN_BLOCKER, DESKTOP_CONTRACT_BLOCKER
- B10: UI_DESIGN_BLOCKER, DESKTOP_CONTRACT_BLOCKER
- B11: UI_DESIGN_BLOCKER, DESKTOP_CONTRACT_BLOCKER
- B12: UI_DESIGN_BLOCKER, DESKTOP_CONTRACT_BLOCKER

## 7. Technical Decisions vs Product Decisions
사용자 경험과 직접 연결되는 D01~D10 제품 정책은 모두 사용자 결정으로 잠겼다. D09의 실제 디스크 반영 방식 등 구현 세부만 Technical Decision으로 분리하여 deferred 상태로 유지한다.

## 8. Decisions That Need User Approval
현재 남아 있는 사용자 제품 결정은 없다. D01~D10은 모두 사용자 결정이 반영되었다. D09 내부 구현 방식은 사용자 선택을 요구하는 제품 정책이 아니라 Backend 구현 단계의 기술 결정이다.

## 9. Decisions That Do Not Need User Approval
섹션 4의 **Already Locked Contracts**와 D09의 deferred 구현 방식은 추가 제품 정책 선택 대상이 아니다. 단, 기술 선택이 확정 사용자 계약을 변경하게 되면 Contract change control을 거쳐야 한다.

## 10. Regression Risks
가장 큰 Regression 위험은 **상태 관리(D04, D02)**와 **파일명 실패 강행(D05)**에 있다.
기존 사용자는 개별 파일 오류 발생 시 다음 작업이 계속 이어지는 것(Batch-friendly)에 익숙할 수 있는데, 이를 단일 Job 실패로 강제 종료하면 사용성이 훼손될 수 있다.
또한 추론 파라미터(D07)를 기본값으로 변경 시 기존에 최적화되었던 노이즈/환각 방지 효과가 유실될 위험이 있다.

## 11. Required Follow-up After Approval
본 문서 승인 후 다음 순서로 작업을 진행한다.

1. **Migration Contract Review** (완료)
2. **User Decisions** (반영 완료)
3. **Migration Contract Lock** (현재 사용자 검토 대기)
4. **FEATURE_PARITY / ROADMAP 등 기준 문서 갱신**
5. **UI Gap Closure**
6. **UI State / UX Validation**
7. **UI Freeze**
8. **Backend / Feature Migration**
