# Sorigul Development Rules

## Contract and parity

- 제품 행동은 `MIGRATION_CONTRACT.md`를 최우선 기준으로 따른다.
- Legacy ACTIVE 기능은 보존하거나 승인된 `INTENTIONAL_CHANGE`로 명시한다.
- UI 설계나 구현 편의가 Legacy 기능을 지우는 근거가 되어서는 안 된다.
- 기존 전사도우미 코드 Copy와 Legacy Python module Import를 금지한다.
- Legacy 코드는 dependency가 아니지만 기능·검증 증거는 parity 근거로 사용한다.
- 사용자 UI에 내부 engine 이름이나 불필요한 구현 세부를 노출하지 않는다.
- DONE 이전에는 100% 완료를 표시하지 않는다.
- Local 전사 결과와 Google Drive 업로드 상태를 분리한다.

## Delivery order

- UI Freeze 전 실제 transcription 구현을 금지한다.
- UI Freeze 전 backend 대규모 구조 설계를 금지한다.
- Mock Interaction과 UI 상태/action 계약을 먼저 검증한다.
- 실제 기능은 확정 UI Contract에 연결한다.
- Backend 요구 때문에 확정 UI를 임의 변경하지 않는다.
- D09 Result 탐색/API 방식과 Log 저장 구조 같은 deferred technical decision을 제품 문서 동기화에서 임의 확정하지 않는다.

## Storage hygiene

- 실제 MP3, Whisper model GB 파일, credential/token, persistent runtime user data, 대용량 테스트 결과물을 프로젝트 로컬 폴더에 장기 누적하지 않는다.
- 사용자 데이터와 재생성 가능한 개발 artifact를 구분한다.
- `node_modules`, Rust `target`, `.venv`, `build`/`dist` 같은 재생성 가능한 개발 artifact는 필요하면 프로젝트 내부에서 사용할 수 있다.
- build/dist/cache/generated 파일과 credential/token은 Git에서 추적하지 않는다.
- 사용자 데이터 정리를 개발 artifact 정리와 한꺼번에 수행하지 않는다.
- `git clean -fdx`를 사용하지 않는다.

## Git workflow

- `git add .`를 사용하지 않는다.
- `main`에서 직접 개발하지 않는다.
- Phase/Task 단위 branch를 사용한다.
- 사용자 검토 없이 자동 merge 또는 push하지 않는다.
