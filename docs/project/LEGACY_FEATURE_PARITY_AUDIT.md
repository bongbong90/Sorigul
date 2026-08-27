# Sorigul Legacy Feature Parity Audit

> Audit date: 2026-08-26
>
> Sorigul baseline: `audit/legacy-feature-parity` / `154e550e6aefd4dfecd5e0140d0ff1f69bf17f5c`
>
> Legacy baseline: `bongbong90/jeonsa_doumi` `main` / `fbc86313a179a62a586386551f99384a9fce5fc8`

> **Decision resolution:** 이 문서는 위 baseline에서 수집한 Legacy 증거와 당시의 conflict/open question 기록을 보존한다. 이후 확정된 제품 정책은 `MIGRATION_CONTRACT.md`가 우선한다. 따라서 21–22절의 intentional change candidates/open questions는 Contract에서 해결되었고, Dashboard는 Legacy에서 ACTIVE였다는 증거를 유지하되 Sorigul에서는 D10 `INTENTIONAL_CHANGE`로 제거한다. 23절 B08은 Dashboard 완성이 아니라 독립 Log Screen과 Dashboard 제거 결정의 반영으로 해석한다. 제품 행동이 아닌 D09 Result 탐색/API 구조만 deferred technical decision으로 남는다.

## 1. Audit Scope

이 문서는 `jeonsa_doumi`의 현재 `main`에서 사용자에게 실제 제공되거나 최신 검증으로 확인된 기능 계약을 추출하고, 현재 Sorigul 문서·화면 설계가 이를 수용하는지 판정한다. Sorigul 및 Legacy의 코드는 변경하거나 실행하지 않았고, 외부 API·Whisper·MP3도 실행하지 않았다. Cloud 범위는 Google Drive 단일 지원이며 MYBOX와 다중 provider 설계는 범위 밖이다.

조사 범위는 전사 흐름, Local Whisper, 파일명 정규화, Stop/Cancel/Restart/Resume, Job 저장·복구, Direct Colab HTTP, Google Drive, 폐기된 Drive Queue, Dashboard, Folders, 알림·Tray·종료, 설치형 Tauri runtime이다.

## 2. Evidence Hierarchy

판정 우선순위는 다음과 같다.

1. Legacy `main` 실행 코드: `gui_main.py`, `auto_transcribe.py`, `backend/`, `frontend-tauri/`, 파일명·Drive 모듈
2. probe/test/validation 및 최신 설치형 검증: 특히 Phase 16, 19, 21, 23
3. 최신 inventory/architecture/release 문서
4. `archive/`, old backup, 과거 POC 및 오래된 Phase 문서

코드끼리 동작이 다르면 둘 다 기록하고 근거 없이 하나를 최종 계약으로 선택하지 않았다. 특히 PySide 실행 경로와 설치형 Tauri/FastAPI 경로는 현재 공존하므로 구분한다. 오래된 `current_system_map.md`의 Drive Queue 설명은 Phase 16 조사 및 현재 UI 코드와 충돌하므로 최신 코드·검증을 우선했다.

## 3. Legacy Runtime Overview

Legacy에는 두 개의 유효한 제품 경로가 공존한다.

- PySide 경로: `gui_main.py`가 폴더·선택·Dashboard·Folders·알림·Tray·종료·Local/Direct Colab UX를 제공하고 `auto_transcribe.py` 또는 GUI 내 Colab 흐름을 호출한다.
- 설치형 경로: `frontend-tauri`가 FastAPI sidecar를 자동 시작하고 local job queue 및 Local Whisper를 호출한다. Phase 23E MSI closeout에서 설치, 한국어 경로 선택, 작업 저장/복원, Local Whisper `medium`, TXT/JSON/SRT, Drive 4종 업로드·update, 앱 종료 시 backend 정리까지 검증됐다.

신규 backend 상태는 `WAITING`, `PREPARING`, `NORMALIZING`, `READY`, `UPLOADING`, `RUNNING`, `TRANSCRIBING`, `DOWNLOADING`, `MERGING`, `SAVING`, `VERIFYING`, `BACKING_UP`, `DONE`, `FAILED`, `CANCEL_REQUESTED`, `CANCELLED`, `STOPPED`, `CRASHED`이다. 모든 상태를 UI에 그대로 노출할 필요는 없지만 실패, 중지, 복구 필요, 전사 완료와 Drive 실패의 분리는 사용자에게 보여야 한다.

## 4. Active Feature Inventory

아래 43개 항목을 ACTIVE로 판정했다. 세부 근거와 Sorigul 대응은 6절의 동일 ID를 따른다.

- 기본 전사 8개: `TR-001`–`TR-008`
- 파일명 정규화 4개: `FN-001`–`FN-004`
- 재시작·복구 의미 4개: `RC-001`–`RC-004`
- Job persistence 3개: `JP-001`–`JP-003`
- Local Whisper 4개: `LW-001`–`LW-004`
- Direct Colab HTTP 5개: `CO-001`–`CO-005`
- Google Drive 6개: `GD-001`–`GD-006`
- 사용자 화면·Desktop UX 5개: `UI-001`–`UI-005`
- 설치형 runtime 4개: `RT-001`–`RT-004`

## 5. Deprecated / Experimental / Archived Inventory

| ID | Item | Status | Evidence | Decision |
| -- | -- | -- | -- | -- |
| NA-001 | Google Drive Queue job/worker/UI 경로 | DEPRECATED | `drive_queue_manager.py`; `drive_queue_backend.py`; `colab_drive_worker.py`; `docs/research/phase16_gdrive_queue_legacy_closeout.md`; `scripts/probe_phase16_gdrive_queue_legacy_closeout.py` | UI 엔진 선택에서 제거됐고 opt-in guard 뒤에 격리됐다. Sorigul로 이식하지 않는다. |
| NA-002 | Backend filename preview/apply stub | EXPERIMENTAL | `backend/services/filename_service.py::preview_normalization`, `apply_normalization` | Phase 2 stub이며 실제 rename을 하지 않는다. 사용자 계약의 근거는 `filename_normalizer.py`와 PySide 코드다. |
| NA-003 | 설치형 Tauri의 Direct Colab 제품 경로 | EXPERIMENTAL | `backend/services/colab_http_service.py`; Phase 23E closeout의 미검증 항목 | adapter/코드는 있으나 최종 MSI closeout은 Local Whisper+Drive를 검증했고 설치형 Colab은 검증하지 않았다. Direct Colab 기능 자체는 PySide 경로에서 ACTIVE다. |
| NA-004 | 과거 Drive Queue 화면 노출 및 Phase J 설계 | ARCHIVED | `docs/drive_queue_phase_j*.md`; `docs/colab_drive_queue_design.md`; Phase 16 inventory | 역사·회귀 자료로만 보존한다. |
| NA-005 | 구 PySide backup 및 icon POC | ARCHIVED | `archive/old_backups/gui_main.backup_texttest_20260414_143239.py`; `archive/icon_tests/` | 현재 계약 판정 근거로 사용하지 않는다. |
| NA-006 | API `outputs` 필드의 최종 제품 노출 계약 | UNKNOWN | Phase 23C/23E validation에서 실제 파일 PASS이나 `outputs=None` 한계 기록 | 실제 산출물 계약은 확인됐지만 API projection을 그대로 유지할지는 증거가 부족하다. |

집계: ACTIVE 43, DEPRECATED 1, EXPERIMENTAL 2, ARCHIVED 2, UNKNOWN 1.

## 6. Feature Parity Matrix

`Freeze Impact`의 `Bxx`는 23절 blocker와 연결된다. Sorigul 집계는 ACTIVE 43개만 대상으로 하며 `COVERED 6 / PARTIAL 13 / MISSING 19 / INTENTIONAL_CHANGE 5 / NOT_APPLICABLE 0`이다.

| ID | Legacy Feature | Legacy Status | Evidence | User-visible Contract | Sorigul Status | Freeze Impact | Migration Phase |
| -- | -- | -- | -- | -- | -- | -- | -- |
| TR-001 | 최상위 MP3 검색 | ACTIVE | `auto_transcribe.py::main`; `gui_main.py::_merge_folder_mp3s_into_queue` | 선택 폴더의 `.mp3`/`.MP3`를 비재귀 검색 | COVERED | No | File Scan |
| TR-002 | 선택/전체 fallback | ACTIVE | `gui_main.py::run_transcribe_process` | 체크가 하나라도 있으면 선택분, 없으면 전체 | INTENTIONAL_CHANGE | Yes (B01) | Pre-Freeze |
| TR-003 | 완료 bundle 사전 제외 | ACTIVE | `auto_transcribe.py::is_transcription_complete`; `gui_main.py` start guards | 완료 파일은 실제 처리 대상·분모에서 제외 | COVERED | Yes (B01) | Queue |
| TR-004 | 순차 처리와 다음 파일 이동 | ACTIVE | `auto_transcribe.py::process_files`; `backend/services/job_runner.py` | 대상 순서대로 처리하고 다음 미완료 파일로 이동 | COVERED | No | Queue |
| TR-005 | 파일/전체 progress와 ETA | ACTIVE | `gui_main.py` progress helpers; `auto_transcribe.py` events | 현재 파일과 전체 완료 기준 진행률 및 ETA 구분 | PARTIAL | Yes (B02) | UX States |
| TR-006 | TXT/JSON/SRT 완료 bundle | ACTIVE | `auto_transcribe.py::is_transcription_complete`; local service verifier | 세 결과를 MP3 stem 기준으로 생성·검증 | COVERED | No | Local Whisper |
| TR-007 | 부분 실패 의미 | ACTIVE | `auto_transcribe.py::process_files`; `backend/services/local_whisper_service.py::run` | PySide는 파일 실패 후 계속, Tauri는 첫 실패로 Job FAILED | INTENTIONAL_CHANGE | Yes (B02) | Contract Approval |
| TR-008 | Start/Stop/실패/재시도 | ACTIVE | `gui_main.py`; job routes/service; Phase 23E future list | 실행 중 Stop, 실패·중지 후 명시적 재시도 | PARTIAL | Yes (B02) | UX States |
| FN-001 | 문자열 정리 | ACTIVE | `filename_normalizer.py` regex/clean helpers | 페이지 범위, `+`, Windows 금지 문자, 공백·underscore 정리 | PARTIAL | Yes (B04) | Filename |
| FN-002 | 과정·과목·주차·강 감지 | ACTIVE | `filename_normalizer.py`; `scripts/test_smart_rename.py` | alias를 표준 과정/과목/주차/강으로 해석 | PARTIAL | Yes (B04) | Filename |
| FN-003 | 표준명과 다음 번호 | ACTIVE | `filename_normalizer.py::build_standard_filename`; probes | `{과정}_{과목}_{N}주차_{M}강.ext`, 선호 번호부터 비어 있는 번호 선택 | PARTIAL | Yes (B04) | Filename |
| FN-004 | rename preview/보호/충돌/실패 UX | ACTIVE | `gui_main.py::_collect_filename_change_previews`, `_apply_smart_filename_normalization_before_transcribe`; smart rename probes | 표준명·완료 파일·기존 4종 충돌 보호, 덮어쓰기 금지, 실패 설명 | MISSING | Yes (B04) | Pre-Freeze + Filename |
| RC-001 | CANCELLED 재실행 | ACTIVE | `job_runner.RUNNABLE_STATUSES`; `job_service.RETRYABLE_STATUSES` | CANCELLED job은 retry로 처음부터 다시 큐잉 가능 | PARTIAL | Yes (B01) | Stop/Restore |
| RC-002 | STOPPED 재실행 | ACTIVE | `job_runner.RUNNABLE_STATUSES`; `job_service.RETRYABLE_STATUSES` | runner는 허용하나 retry API는 거부하여 진입점 정리가 필요 | PARTIAL | Yes (B01) | Stop/Restore |
| RC-003 | DONE 재실행/skip | ACTIVE | runner runnable set; `auto_transcribe.py::is_transcription_complete`; local adapter | PySide는 bundle skip, DONE job runner는 거부, 신규 Tauri job은 완료 bundle도 재처리 | INTENTIONAL_CHANGE | Yes (B01) | Contract Approval |
| RC-004 | 파일 단위 resume | ACTIVE | session/progress code; `docs/session_and_stop_flow.md` | Local은 완료 파일을 복원하고 현재 파일은 처음부터, Colab은 별도 resume 계약 | PARTIAL | Yes (B03) | Stop/Restore |
| JP-001 | jobs.json 영속화 | ACTIVE | `backend/storage/jobs_store.py`; Phase 23E | `%LOCALAPPDATA%/.../runtime/jobs.json`에 Job 저장·앱 재시작 복원 | MISSING | Yes (B03) | Queue |
| JP-002 | atomic/corrupt 방어 | ACTIVE | `backend/storage/jobs_store.py` | tmp→replace, corrupt 파일 격리, event 보존 | MISSING | No | Backend |
| JP-003 | 비정상 종료 복구 | ACTIVE | `jobs_store.py`; `job_service.py` startup recovery | 실행 중 계열 상태는 재시작 시 CRASHED로 전환 | MISSING | Yes (B03) | Stop/Restore |
| LW-001 | Whisper `medium` | ACTIVE | `auto_transcribe.py::MODEL_SIZE`; local service; Phase 23C/E | 기본 모델은 `medium` | PARTIAL | No | Local Whisper |
| LW-002 | CUDA/CPU fallback | ACTIVE | `auto_transcribe.py` device/model load and fp16 fallback | CUDA 우선, GPU load 실패 시 CPU fallback, fp16 실패 재시도 | MISSING | No | Backend |
| LW-003 | 결과 검증 | ACTIVE | auto/local verifiers; output probes | TXT/JSON은 비어 있지 않고 JSON에 `text`,`segments`; SRT는 존재하면 빈 파일 허용 | COVERED | No | Local Whisper |
| LW-004 | Local 옵션·실패 정책 일치 | ACTIVE | `auto_transcribe.py` transcribe options vs local service plain call | 언어/beam/previous-text 및 파일 실패 동작이 두 경로에서 다름 | INTENTIONAL_CHANGE | No | Contract Approval |
| CO-001 | `/health`, `/transcribe`, URL normalize | ACTIVE | `colab_http_service.py`; `gui_main.py` health/transcribe helpers | URL을 정규화하고 연결 확인 후 동기 전사 | PARTIAL | Yes (B05) | Colab |
| CO-002 | 300초 chunk와 timeout/retry | ACTIVE | `audio_chunker.py`; `gui_main.py` constants; long-audio validation | 현재 GUI 기본 300초, 순차 retry; backend 옵션 기본은 chunk off | MISSING | Yes (B05) | Colab |
| CO-003 | manifest/tail skip | ACTIVE | `audio_chunker.py`; tail-skip validation | chunk 상태·attempt·response 기록, 너무 짧거나 작은 tail은 skip | MISSING | No | Backend |
| CO-004 | merge와 segment offset | ACTIVE | `colab_result_merger.py`; long-audio validation | chunk 시작 시간 offset을 적용해 정렬·TXT/JSON/SRT 저장 | MISSING | No | Backend |
| CO-005 | Colab resume/cancel 의미 | ACTIVE | `colab_http_service.py`; PySide `progress.json` flow | PySide는 파일 단위, backend chunk는 opt-in 시 chunk 단위 resume; chunk cancel은 현재 FAILED가 되는 결함 | INTENTIONAL_CHANGE | Yes (B05) | Contract Approval |
| GD-001 | OAuth credential/token 수명주기 | ACTIVE | `google_drive_uploader.py::build_drive_service` | full Drive scope, AppData credential/token, refresh 후 실패 시 재로그인 | MISSING | Yes (B07) | External Upload |
| GD-002 | 과정/과목/주차/강 분류 | ACTIVE | `google_drive_uploader.py::classify_upload_path`; backend preflight | 파일명 정규화 결과로 Drive 경로를 분류하며 실패 시 네트워크 전 차단 | MISSING | Yes (B06) | External Upload |
| GD-003 | 4종 bundle 업로드 | ACTIVE | `upload_transcription_bundle`; Phase 23D/E | MP3/TXT/JSON/SRT를 함께 업로드 | COVERED | Yes (B06) | External Upload |
| GD-004 | 업로드 전 엄격 검증 | ACTIVE | `google_drive_upload_service.py` preflight; Phase 23D2 | MP3·4종 stem, TXT/JSON nonempty, JSON parse/keys, SRT 존재 검사 | MISSING | No | Backend |
| GD-005 | update-or-create | ACTIVE | `google_drive_uploader.py::upload_file`; Phase 23D/E | 같은 parent/name은 update, 없으면 create하여 중복 방지 | MISSING | No | Backend |
| GD-006 | Drive 실패 격리 | ACTIVE | local service drive fields; `DriveUploadStatus.tsx`; Phase 23D2 | 로컬 전사는 DONE, Drive만 FAILED이며 errors/results를 별도 노출 | PARTIAL | Yes (B06) | Pre-Freeze + Upload |
| UI-001 | Dashboard | ACTIVE | `gui_main.py` dashboard refresh/stat settings; inventory | 누적 완료·오디오 시간·오늘 완료·평균 속도·최근 완료 및 새로고침 | PARTIAL | Yes (B08) | Dashboard |
| UI-002 | Folders | ACTIVE | `gui_main.py` folder filters/preview/open | 전체/완료/미완료/결과만, 표, 500자 TXT preview·전체 보기·폴더 열기 | MISSING | Yes (B09) | Pre-Freeze + Results |
| UI-003 | 완료 알림/Toast | ACTIVE | `TrayToastWindow`; notify settings; toast probes | 파일별·전체 완료 알림, Toast에서 폴더 열기 | PARTIAL | Yes (B10) | Pre-Freeze + Desktop |
| UI-004 | Tray | ACTIVE | `gui_main.py::_setup_tray_icon`, close/quit handlers | tray icon, 앱 열기, 종료; 실행 중 close 시 tray로 숨김 | MISSING | Yes (B10) | Desktop |
| UI-005 | 완료 후 PC 종료 | ACTIVE | `SHUTDOWN_WAIT_OPTIONS`; shutdown prompt/request | 즉시/15초/30초, countdown 확인과 취소 | MISSING | Yes (B11) | Pre-Freeze + Desktop |
| RT-001 | backend sidecar 자동 시작/health | ACTIVE | Rust launcher; `backend/sidecar_main.py`; Phase 23B/E | 앱 실행 시 backend 기동 및 health 확인, 외부 기존 backend와 소유권 구분 | MISSING | Yes (B12) | Runtime |
| RT-002 | 종료 시 process tree 정리 | ACTIVE | Rust launcher; Phase 23B/E | X 종료 시 소유 backend/child 정리, port 8000 반환, orphan 없음 | MISSING | No | Runtime |
| RT-003 | 설치형 Job/Drive 복원 | ACTIVE | Phase 23D3C/E | 앱 재시작 후 DONE Job과 Drive DONE 결과 유지 | MISSING | Yes (B03) | Runtime |
| RT-004 | Windows MSI/Unicode/no-console | ACTIVE | build script; Phase 19/23B/E validation | MSI 설치·단독 실행, 한국어 경로, backend console 숨김 | MISSING | No | Packaging |

## 7. Transcription Contract

1. 전사자료 폴더의 최상위 `.mp3`와 `.MP3`를 검색한다. Legacy 기본 검색은 재귀가 아니다.
2. PySide 선택 의미는 “체크된 행이 있으면 선택 전사, 없으면 전체 전사”다. Sorigul Mock은 선택이 없으면 Start가 비활성화되므로 `CONFLICT`다.
3. 파일명 스마트 정규화 후 완료 bundle을 판정하여 처리 대상에서 제외한다. 처리 대상 수와 전체 진행률 분모도 skip 후 목록을 사용한다.
4. 순차 처리하며 완료/실패/중지 후 다음 동작은 9절 정책을 따른다.
5. 완료 bundle은 같은 stem의 TXT/JSON/SRT다. 결과 위치는 PySide에서 MP3 옆이며 신규 backend는 요청된 output folder를 사용하므로 최종 저장 위치 UX는 확정이 필요하다.
6. PySide는 파일별 예외를 기록하고 다음 파일로 진행한 뒤 전체 루프를 끝낸다. 신규 local adapter는 첫 모델·파일·저장 오류로 Job을 FAILED 처리한다. 이는 승인 전까지 미확정 계약이다.

## 8. Filename Normalization Contract

- `(p.12)` 및 `(p.12~34)` 계열 페이지 표기를 제거하고 `+`는 공백으로 바꾼다. Windows 금지 문자 `< > : " / \\ | ? *`, 연속 공백과 underscore를 정리한다. 확장자는 보존한다.
- 과정은 `개념완성`, `기본이론`, `기초이론`을 감지한다. 과목 alias는 민법, 부동산학개론, 공인중개사법, 부동산공시법, 부동산공법, 부동산세법을 구분하며 공시법을 공법보다 먼저 판정한다.
- 주차·강을 감지해 `{과정}_{과목}_{N}주차_{M}강.ext`를 만든다. 이미 정확한 표준명은 보호한다.
- 같은 주차의 기존 강 번호는 MP3/TXT/JSON/SRT 전부에서 모은다. 선호 강 번호가 있으면 그 번호 이상에서 처음 비는 번호를, 없으면 1부터 처음 비는 번호를 선택한다. 한 batch 안에서도 예약 번호를 공유해 충돌을 막는다.
- PySide 실제 flow는 MP3와 같은 stem의 TXT/JSON/SRT를 함께 `os.replace`하고, target이 존재하면 덮어쓰지 않는다. standalone `apply_rename_plan`과 backend filename service는 실제 적용 근거가 아니다.
- 스마트 정규화 실패 시 현재 PySide 코드는 경고를 남기고 원래 이름으로 전사를 계속한다. 일부 최신 설명 문서의 “감지 실패 시 차단”과 다르므로 최종 정책은 Open Question이다.

## 9. Stop / Cancel / Restart / Resume Contract

| Question | Evidence-based conclusion |
| -- | -- |
| Q1 CANCELLED 재시작 | 가능하다. `CANCELLED`는 runner runnable이자 retry API retryable이며 retry 시 non-SKIPPED 파일을 WAITING으로 초기화한다. |
| Q2 STOPPED 재시작 | runner 내부에서는 가능하지만 retry API의 retryable set에는 없다. 사용자 진입점/API 불일치이므로 그대로 확정할 수 없다. |
| Q3 DONE 재실행 | 같은 Job은 runner가 거부한다. 새 실행에서는 PySide가 완료 bundle을 skip하지만 신규 Tauri local job은 사전 skip이 없어 재전사할 수 있다. |
| Q4 DONE 파일 포함 | PySide는 skip한다. 신규 Tauri job은 입력 파일을 모두 WAITING으로 만들어 재전사한다. `CONFLICT`. |
| Q5 Stop 후 대상 | PySide Local은 완료 bundle을 복원/skip하고 중단된 현재 파일과 미완료 파일만 처리한다. backend retry는 non-SKIPPED 전부를 초기화하므로 동일하지 않다. |
| Q6 중간 resume | Local Whisper는 불가하며 현재 파일 처음부터다. PySide Colab `progress.json`은 파일 단위, backend chunk resume는 활성화한 동일 manifest의 완료 chunk 단위다. |

`auto_transcribe.py`는 parent folder의 `stop.flag`를 파일 시작 전과 전사 후 저장 전에 확인한다. 전사 후 stop이면 결과를 버린다. `transcribe_session_state.json`은 `running`, `completed`, `stopped_by_user`, `crashed`, `corrupt_session`을 기록한다. Sorigul Mock의 선택 유지·`CANCELLED` 후 Start 가능 동작은 방향상 Q1과 맞지만 실제 retry/reset/skip 의미를 표현하지 않는다.

## 10. Job Persistence / Recovery Contract

- 신규 backend는 `%LOCALAPPDATA%\전사도우미\runtime\jobs.json`을 `jobs.json.tmp`에 쓴 뒤 replace한다.
- 손상된 JSON은 `jobs.corrupt.<timestamp>.<uuid>.json`으로 격리하며 event history를 보존한다.
- 시작 시 실행 중 계열(`RUNNING`, `TRANSCRIBING`, upload/download/merge/save/verify/backup 및 `CANCEL_REQUESTED`)은 `CRASHED`로 전환한다.
- PySide session은 `transcribe_session_state.json`을 flush/fsync 후 atomic replace하고 stale tmp를 정리한다. `running` session에 `stop.flag`가 있으면 `stopped_by_user`, 없으면 `crashed`로 복구한다. 완료 목록도 실제 결과 bundle이 여전히 완전한 경우만 복원한다.
- 취소·재시도 시 파일 상태 reset 범위와 완료 결과 skip은 두 runtime이 다르므로 Sorigul queue contract로 별도 확정해야 한다.

## 11. Local Whisper Contract

- 기본 모델은 `medium`이다. PySide worker는 CUDA 가능 시 CUDA, GPU 모델 load 실패 시 CPU로 fallback하고 fp16 오류도 fp16 false로 재시도한다.
- PySide transcribe 옵션은 한국어, `task=transcribe`, temperature 0, beam/best-of 5, patience 1, `condition_on_previous_text=false`다. 신규 local adapter는 plain `model.transcribe(path)`라 동일하지 않다.
- 결과는 TXT, 원본 결과 dict JSON, nonblank segment 기반 SRT다. TXT/JSON은 0 byte면 실패이고 JSON은 object이며 `text`, `segments`가 필요하다. SRT는 존재해야 하지만 음성이 없으면 0 byte도 완료다.
- PySide는 완료 bundle을 선제 skip하고 파일 실패 후 계속한다. 신규 adapter는 skip하지 않고 첫 실패에서 Job FAILED다. 최종 기능 계약은 사용자 승인이 필요하다.

## 12. Direct Colab Contract

- `/health`로 연결을 확인하고 정규화된 base URL의 `/transcribe`를 호출한다.
- 현재 PySide 기본 chunk는 300초, retry 2회, retry base delay 10초이며 UI 범위는 60–900초다. backend `ChunkingOptions`의 기본은 disabled, 켤 때 300초·`max_retries=1`·timeout 600초다. non-chunk adapter는 timeout 900초·retries 2다.
- chunk manifest는 status, attempt, start/duration, request/response/partial 경로를 기록한다. 1초 미만 또는 2048 byte 미만 tail은 `skipped`로 기록하고 전송하지 않는다.
- merge는 각 chunk `start_seconds` offset을 segment에 더하고 정렬하여 TXT/JSON/SRT를 만든다. 300초 long-audio와 tail-skip validation은 PASS다.
- 성공 후 `keep_chunks=false`이면 chunk audio만 제거한다. manifest/response/partial은 남으므로 “temp 전체 cleanup”으로 표현하면 안 된다.
- PySide `progress.json`은 파일 완료 단위 resume다. backend chunk resume는 같은 job manifest에서 완료 response를 재사용한다. non-chunk는 중간 resume가 없다.
- non-chunk cancel은 CANCELLED이나 chunk loop의 cancel exception은 현재 FAILED 결과로 합쳐진다. 이 결함을 Sorigul 계약으로 계승하면 안 된다.

## 13. Google Drive Contract

### Authentication

OAuth scope는 `https://www.googleapis.com/auth/drive`다. credential은 `%APPDATA%\전사도우미\google_credentials.json`, token은 같은 위치의 `google_drive_token.json`을 사용한다. 유효 token 재사용, 만료+refresh token refresh, refresh 실패 또는 인증 정보 부재 시 local-server OAuth 재로그인을 수행한다. token 저장 실패는 업로드를 즉시 실패시키기보다 경고한다.

### Classification and folder

과정·과목·주차·강을 표준 파일명에서 분류한다. 분류 실패는 Drive folder/network 작업 전에 upload를 차단한다. 현재 코드 계약은 다음 구조다.

`2026 제37회 공인중개사 자격시험 / 전사자료 / {과정} / {[1차] 또는 [2차] 과목} / {과정_과목_N주차}`

현재 backend 검증 예시는 `[1차] 민법 / 개념완성_민법_99주차`다. Drive 결과명에서는 `공인중개사법`을 `중개사법`으로 정규화하는 별도 규칙이 있다.

### Bundle, verification, duplicate, isolation

- 업로드 대상은 정확히 MP3/TXT/JSON/SRT 4종이다.
- MP3 존재, 결과 3종 존재와 동일 stem, TXT/JSON nonempty, JSON object parse 및 `text`/`segments`, SRT 존재를 네트워크 전에 확인한다. SRT empty는 허용한다.
- 같은 parent/name을 찾으면 update, 없으면 create하는 `update_or_create`다. Phase 23D/E에서 재업로드 후에도 4개만 유지됨이 검증됐다.
- 전사와 로컬 저장 성공 후 Drive 실패는 Job 전체 실패가 아니다. `Job.status=DONE`, `drive_status=FAILED`이며 `drive_results`, `drive_errors`를 별도 보존한다. UI는 “로컬 저장 완료, Drive 업로드 실패”를 명확히 구분해야 한다.

## 14. Dashboard Contract

Dashboard는 ACTIVE 유지 대상이다. PySide 사용자 화면은 누적 완료 파일, 누적 오디오 시간, 오늘 완료 파일, 평균 전사 속도, 최근 완료 파일을 표시하고 `QSettings`의 `ui_settings.ini`에 통계를 저장하며 시작/완료 및 새로고침 시 갱신한다. Sorigul에는 Phase 5/16 계획과 shell 자리만 있어 PARTIAL이다. 카드 구성·empty/loading/error·새로고침 control을 UI Freeze 전에 정해야 한다.

## 15. Folders Contract

Folders도 ACTIVE 유지 대상이다. 전사자료 폴더를 스캔해 전체/완료/미완료/결과만 필터, 파일명/유형/전사 상태/수정일 열, TXT 500자 preview와 전체 보기 dialog, 폴더 열기를 제공한다. 완료는 MP3와 TXT/JSON/SRT bundle로 판정한다. Sorigul의 일반 Results 계획은 이 계약을 구체적으로 포함하지 않으므로 MISSING이며 UI Freeze blocker다.

## 16. Notification / Tray / Shutdown Contract

UI Freeze 전에 파일별/전체 알림 on/off, Toast의 폴더 열기, 완료 후 PC 종료 on/off와 즉시/15초/30초, countdown/취소 control의 자리와 상태를 설계해야 한다. Tray icon, OS notification 전송, 실행 중 창 닫기 시 tray hide, tray의 앱 열기/종료, 실제 Windows shutdown 호출은 Tauri/Desktop 구현 단계에서 구현해도 된다. 기능 자체는 모두 ACTIVE 유지 대상이다.

## 17. Desktop Runtime Contract

- 설치된 앱 실행만으로 packaged FastAPI sidecar가 자동 시작되고 `/api/health`가 확인돼야 한다.
- launcher가 시작한 process와 이미 떠 있던 외부 backend를 구분하며, 앱이 소유한 process tree만 종료한다.
- X 종료 후 frontend/backend가 남지 않고 port 8000이 반환돼야 한다. backend console window는 노출하지 않는다.
- MSI 설치·실행, Windows 한국어/Unicode 경로의 folder picker·입출력·저장, 재시작 후 Job/Drive 상태 복원을 지원한다.
- Phase 23E에서 MSI, Local Whisper medium, 결과 3종, Drive 4종 create/update, persistence, X cleanup이 PASS다. cancellation/retry/job-record 관리와 설치형 Direct Colab은 최종 제품 검증 범위 밖이었다.

## 18. Sorigul Missing UI States

Backend 상태를 그대로 복사하지 않고 다음처럼 매핑하는 것이 적절하다.

| Class | Backend states | Required UI meaning |
| -- | -- | -- |
| UI-visible | `WAITING`, `TRANSCRIBING`/`RUNNING`, `DONE`, `FAILED`, `CANCELLED`/`STOPPED`, `CRASHED` | 대기, 전사 중, 완료, 실패, 중지됨, 복구 필요 |
| UI-derived | 파일 완료 수/대상 수, ETA, Local DONE + Drive FAILED, retry 가능 여부 | 전체 진행, 남은 시간, 로컬/외부 저장 분리, 다음 행동 |
| Internal transitional | `PREPARING`, `NORMALIZING`, `READY`, `SAVING`, `VERIFYING`, `UPLOADING`, `DOWNLOADING`, `MERGING`, `BACKING_UP`, `CANCEL_REQUESTED` | 준비/마무리/업로드/중지 요청 중 등으로 묶되 장시간이면 현재 단계 표시 |

현재 Sorigul Matrix에는 FAILED가 있으나 Mock은 `IDLE`, `TRANSCRIBING`, `DONE`, `CANCELLED`만 구현한다. 추가로 필요한 것은 복구 필요/CRASHED, retrying, cancel requested, 부분 실패, 결과 검증 실패, backend offline/start failure, Colab 연결 실패/retry, Drive PENDING/UPLOADING/FAILED, 완료 파일 skip, 빈 처리 대상, rename conflict/failure다.

## 19. Sorigul Missing Screens / Controls

- 구체적인 Dashboard 카드·새로고침·empty/error
- Folders/Results 필터 표, TXT preview/전체 보기, 폴더 열기
- 파일명 변경 preview, 충돌·실패 설명, 원명 계속 진행 여부
- Retry/Resume/복구 및 CANCELLED·STOPPED·DONE에서 가능한 action
- Colab URL/연결 확인/chunk 설정 및 장시간 단계
- Google Drive 사용 toggle, OAuth 연결·재로그인·분류 오류, 별도 upload status
- 알림·Tray 동작 및 완료 후 종료 설정/취소
- backend offline/자동 시작 실패/재연결 표현

## 20. Backend-only Migration Requirements

UI Freeze blocker가 아닌 내부 요구사항은 MP3 비재귀 scan, 실제 output verifier, JSON schema/empty SRT 규칙, atomic jobs/session 저장과 corrupt 격리, startup CRASHED 변환, CUDA/CPU/fp16 fallback, Colab manifest/tail skip/segment offset/cleanup, Drive preflight/update-or-create, runtime process ownership·tree cleanup, MSI/Unicode packaging이다. UI 상태와 action contract를 먼저 확정하되 이 내부 보장은 acceptance test로 유지한다.

## 21. Intentional Change Candidates

1. `TR-002`: “선택 없음=전체”를 Sorigul의 “선택 없음=Start 불가”로 바꿀지.
2. `TR-007`: 파일 하나 실패 후 나머지를 계속할지, 즉시 Job FAILED로 끝낼지.
3. `RC-003`: DONE bundle을 새 Job에서도 항상 skip할지, 명시적 강제 재전사를 허용할지.
4. `LW-004`: PySide Whisper 옵션/CUDA fallback과 파일 실패 의미를 신규 adapter에 동일하게 유지할지.
5. `CO-005`: Local·Colab의 resume 단위와 chunk cancel 상태를 일관되게 정의할지.

이 다섯 항목은 구현 편의로 결정하지 않고 사용자 승인을 받아야 한다.

## 22. Open Questions

1. 최종 단일 runtime에서 PySide의 “부분 실패 후 계속”과 Tauri의 “첫 실패 즉시 FAILED” 중 무엇을 채택할 것인가?
2. DONE bundle이 있는 파일을 강제 재전사하는 별도 action이 필요한가?
3. STOPPED를 retry API에서도 허용할지, STOPPED와 CANCELLED를 UI에서 하나로 합칠지?
4. 정규화 감지 실패 시 원명으로 계속할지, 사용자 확인/차단할지?
5. 결과를 항상 MP3 옆에 둘지, 별도 output folder를 지원할지?
6. Direct Colab chunking을 기본으로 켤지와 UI에 노출할 최소 설정은 무엇인가?
7. API `outputs` field를 UI 결과 탐색의 canonical source로 만들지?

### Required Questions Conclusion

| Question | Conclusion |
| -- | -- |
| Q1 | `CANCELLED`는 runner와 retry API 모두 재시작 가능하다. retry 시 non-SKIPPED 파일 상태를 WAITING으로 초기화한다. |
| Q2 | `STOPPED`는 runner에서는 재실행 가능하지만 retry API에서는 불가능하다. 진입점 불일치 해소가 필요하다. |
| Q3 | 같은 `DONE` Job은 재실행 불가다. 새 Job에서의 동작은 PySide skip과 Tauri 재전사가 충돌한다. |
| Q4 | DONE 파일은 PySide에서는 결과 bundle 판정으로 skip되지만 신규 Tauri local job에서는 재전사될 수 있다. |
| Q5 | PySide Local은 Stop 후 실제 완료 bundle을 제외한 현재/미완료 파일만 처리한다. backend retry reset은 이 의미와 다르다. |
| Q6 | Local은 현재 파일 중간 resume가 없고 파일 처음부터다. PySide Colab은 파일 단위, backend chunk mode는 완료 chunk 단위 resume다. |
| Q7 | 완료에는 같은 stem의 TXT/JSON/SRT가 모두 필요하며 TXT/JSON은 nonempty, JSON은 object와 `text`,`segments`가 필요하다. |
| Q8 | 그렇다. SRT는 존재해야 하지만 0 byte여도 완료다. |
| Q9 | Google Drive 업로드 대상은 MP3/TXT/JSON/SRT 4종이다. |
| Q10 | 전사와 로컬 저장은 `DONE`, Drive만 `FAILED`다. Job 전체를 FAILED로 바꾸지 않는다. |
| Q11 | 파일 scan/선택 뒤, 완료 bundle skip과 실제 전사 대상 확정 전에 스마트 정규화를 수행한다. |
| Q12 | MP3/TXT/JSON/SRT 전체의 기존·batch 예약 번호를 고려해 선호 번호 이상(없으면 1부터)의 첫 빈 강 번호를 쓴다. |
| Q13 | Dashboard는 ACTIVE 유지 대상이다. |
| Q14 | Folders는 ACTIVE 유지 대상이다. |
| Q15 | Tray/Notification/Shutdown은 모두 ACTIVE 유지 대상이다. UI contract는 freeze 전, OS 구현은 Desktop 단계에 둔다. |
| Q16 | 기존 Drive Queue는 DEPRECATED이며 Direct Colab HTTP+직접 Drive 결과 업로드로 대체됐다. 이식하지 않는다. |
| Q17 | 설치형 제품에서 검증된 범위는 MSI/sidecar 자동 시작·health·종료, 한국어 경로, Job persistence, Local Whisper medium, TXT/JSON/SRT, Drive 4종 create/update와 상태 복원까지다. 설치형 Colab 및 cancel/retry 관리는 미검증이다. |

## 23. UI Freeze Blockers

총 12개다.

| ID | Blocker | Exit condition |
| -- | -- | -- |
| B01 | 선택 없음, 완료 skip, CANCELLED/STOPPED/DONE action 의미 | 사용자 승인된 start/restart/force contract와 button states |
| B02 | 실패·부분 실패·retry·progress/ETA | error/retry/partial-success 화면과 상태 문구 |
| B03 | persistence·CRASHED·restore | 앱 재시작 복원 banner/action 및 stale/corrupt 표현 |
| B04 | filename preview/conflict/failure | preview와 보호/충돌/계속·취소 UX |
| B05 | Colab 연결·chunk·resume/cancel | 연결/재시도/장시간 작업 상태와 최소 control |
| B06 | Drive 사용 여부·분류·별도 실패 | upload toggle 및 Local DONE/Drive FAILED 표현 |
| B07 | Drive OAuth·refresh·재로그인 | Settings 연결 상태와 오류/re-auth action |
| B08 | Dashboard | 5개 지표, 최근 완료, refresh, empty/error layout |
| B09 | Folders | 필터/표/preview/full-view/open layout |
| B10 | 알림·Tray | 알림 설정과 close-to-tray/quit 동작의 사용자 제어 |
| B11 | 완료 후 종료 | 즉시/15/30초와 countdown 취소 UI |
| B12 | backend lifecycle 오류 | starting/offline/health failure/retry 표현 |

## 24. Migration Acceptance Criteria

- 43개 ACTIVE 항목이 승인된 parity 상태로 추적되고 5개 intentional change가 명시적으로 승인된다.
- MP3 scan, 선택/전체, normalization, 완료 skip, queue denominator와 restart 규칙이 자동 검증된다.
- Local Whisper `medium`, device fallback, TXT/JSON/SRT verifier 및 empty SRT가 검증된다.
- Stop/Cancel/CRASHED/Retry에서 완료 파일 보존과 현재 파일 재시작 단위가 검증된다.
- Colab health/transcribe, 300초 정책, retry/timeout, manifest/tail skip/offset merge/resume/cancel이 검증된다.
- Drive OAuth, 분류 경로, MP3/TXT/JSON/SRT preflight, update-or-create, Local DONE/Drive FAILED 격리가 검증된다.
- Dashboard, Folders, 알림, Tray, 종료 옵션이 승인된 UI와 실제 데이터로 동작한다.
- MSI 단독 실행, sidecar health/ownership/cleanup, 한국어 경로, Job/Drive 재시작 복원이 설치 환경에서 통과한다.
- Drive Queue와 archive/POC는 제품 navigation·engine·runtime에서 노출되지 않는다.
- UI Freeze 전에 B01–B12가 모두 승인 또는 명시적 후속 구현 경계로 닫힌다.
