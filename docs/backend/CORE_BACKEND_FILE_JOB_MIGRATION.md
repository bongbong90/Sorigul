# Core Backend / File / Job Migration

## Status
**READY**

## Baseline
- **Branch**: `feature/core-backend-file-job-migration`
- **HEAD**: `8b20a0836f82d7e4df55e28b1fef1f2fc8a4f0e7`
- **Migration Contract baseline**: `MIGRATION_CONTRACT.md`
- **UI Freeze**: `UI_FREEZE_V1.md`

---

## Architecture
FastAPI를 기반으로 하는 Sorigul Core Backend의 기초를 구축했습니다. Sorigul 앱 내에 Domain Model, Service 계층, API Router를 분리하여 구현하였습니다. Python 가상 환경 및 `pytest` 기반의 자동 테스트 구조를 확립했습니다. 실제 무거운 ML/AI 라이브러리(Whisper)는 이번 단계에 포함하지 않았으며, 순수 Python 표준 라이브러리와 Pydantic을 활용하여 상태/비즈니스 로직을 구현했습니다.

## D09 Technical Decision
**결정**: Hybrid reconcile (Filesystem Truth + Job API)
**이유**:
Folders 및 Results 화면의 최종 Truth는 **반드시** 실제 Filesystem(`MP3`, `TXT`, `JSON`, `SRT`)의 상태여야 합니다. Job의 기록상 완료(DONE)로 표시되어 있더라도, 사용자가 앱 외부에서 `JSON` 파일을 삭제하면 이는 미완료로 간주해야 합니다(Truth-first principle). 따라서 Backend는 매 파일 스캔 시 Filesystem을 검사하여 `Completion Bundle` 상태를 동적으로 결정하고 반환하며, Job 모델은 진행 상태 추적 및 재시도 상태 복구 관리에만 집중하도록 역할을 분리했습니다. 이 구조는 성능 최적화와 외부 변경 수용에 유리합니다.

---

## File scan contract
`FileScanner` 구현 완료. 지정된 디렉토리의 최상위 `.mp3` 파일만 스캔(Non-recursive)하며, 각 MP3 파일의 수정일자, 크기 및 완료 번들 유효성(`BundleStatus`)을 확인합니다.

## Completion contract
- `DONE`: TXT 존재(size>0), SRT 존재(0 bytes 허용), JSON 존재(size>0, 유효한 포맷, text/segments 키 포함)
- `INCOMPLETE` / `INVALID_RESULT`: 위 조건을 만족하지 못하면 완료로 간주하지 않습니다. Empty JSON이나 형식이 깨진 결과물은 모두 미완료 처리됩니다.

## Filename implementation
`FilenameNormalizer` 구현 완료. 정규표현식을 통해 금지 문자, `+` 기호 등을 안전하게 제거하고, `<과정>_<과목>_<주차>주차_<강>강.mp3` 패턴을 유추하여 표준명을 생성합니다. 이미 표준명 형식을 갖춘 파일은 불필요하게 변경하지 않도록 보호(UNCHANGED)됩니다.

## Next Lesson / Batch Reservation
다중 파일 선택 시, 동일한 덮어쓰기/충돌을 방지하기 위해 `normalize_batch`를 지원합니다. 특정 번호(예: `1강`)가 이미 디스크에 존재하거나, 배치 작업 내의 선행 파일이 선점(Reservation)한 경우, 자동으로 다음 빈 강 번호(`2강`, `3강` 등)를 할당하도록 Auto-increment 로직을 완비했습니다.

## Rename safety
`BundleRenamer` 구현 완료. `MP3`, `TXT`, `JSON`, `SRT` 확장자를 가진 모든 연관 파일을 함께 이동합니다. Preflight 검사를 통해 대상 경로에 단 하나의 파일이라도 이미 존재하면 작업 전체를 중단하며, 중간 실패 시 Best-effort로 Rollback(원래 이름으로 복구)을 시도하는 원자성을 갖추었습니다.

## Job model
`JobModel`, `FileStatus` Enum을 통해 `WAITING`, `TRANSCRIBING`, `DONE`, `FAILED`, `STOPPED`, `CANCELLED`, `CRASHED` 등의 Lifecycle State를 명확히 정의했습니다. Job 단위 이벤트(`JobEvent`) 기록 기능도 구현되었습니다.

## Persistence / recovery
`JobManager` 구현 완료. 상태는 `%LOCALAPPDATA%\Sorigul\jobs.json` 경로를 기본으로 사용하여 원자적(Atomic) 파일 교체 방식(`.tmp` 저장 후 `replace`)으로 기록됩니다. (비-Windows 환경이나 테스트 시 안전한 Fallback 지원)
- **CRASHED Recovery**: Backend 시작 시 활성 상태(`TRANSCRIBING`, `PREPARING` 등)에 머물러 있는 작업을 `CRASHED`로 일괄 자동 전환하며, 변경된 내용을 다시 Persistence에 저장하고 복구 이벤트를 갱신(중복 방지)합니다.
- **Corrupt Recovery**: JSON 파일이 손상된 경우 앱 충돌을 방지하고 손상 파일을 새로운 이름(격리)으로 Rename 처리하여 빈 상태로 정상 기동되도록 방어 로직을 구현했습니다.

## API surface
`api/routes.py`에 다음 FastAPI 엔드포인트를 정의했습니다.
- `GET /api/health`
- `POST /api/scan`
- `POST /api/normalize/preview`
- `POST /api/rename`
- `POST /api/jobs` (생성: DONE 항목 자동 제외, force_retranscribe 지원)
- `GET /api/jobs`
- `GET /api/jobs/{job_id}`
- `POST /api/jobs/{job_id}/action` (stop, cancel, retry: Retry 시 Filesystem Truth를 재확인하여 DONE은 스킵)

---

## Tests
`backend/tests/test_core.py`를 통해 모든 비즈니스 로직(Scan, Completion, Normalize, Batch Reservation, Rename Safety, Job Retry Reconcile, CRASHED Recovery Persistence, Corrupt Quarantine, Stop/Cancel Consistency)에 대한 테스트 픽스처와 8개의 단위 테스트를 작성하였고 `pytest`를 통해 검증했습니다. 유니코드 및 한국어 경로 테스트(`전사자료/개념완성_민법_8주차_4강.mp3`)도 통과했습니다.

## Deferred Work
- 실제 Local Whisper / Colab / Google Drive API 실행 로직
- Frontend 코드베이스의 Backend Client 연결 및 UI Binding (UI Freeze 유지를 위해 생략)
- OS Tray, Notification, Windows Shutdown 제어

## Known Risks
- Filesystem I/O에 의존하는 Scanner 성능 최적화(추후 비동기 처리 도입 필요 시 검토)
- Rename Rollback 실패 상황(디스크 꽉 참 등)에 대한 UI 엣지 케이스 처리 방안

---

## Final verdict
**CORE BACKEND / FILE / JOB MIGRATION READY**
