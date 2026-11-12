# Sorigul Project Charter

## 프로젝트 목적

소리글(Sorigul)은 Windows용 음성 전사 및
전사 결과 관리 데스크톱 애플리케이션이다.

사용자가 음성 파일을 간단하게 전사하고
진행 상태와 결과를 명확하게 관리할 수 있도록 한다.

## 제품 원칙

- Sorigul은 UI와 architecture를 현대화하되 Legacy ACTIVE 기능과 확정된 `MIGRATION_CONTRACT.md`를 보존한다.
- 기능은 계승하고 구현 구조는 계승하지 않는다.
- Legacy ACTIVE 기능의 변경은 승인된 `INTENTIONAL_CHANGE`로 명시하며, UI 설계를 이유로 기능을 조용히 누락하지 않는다.
- 사용자 경험을 기술 구조보다 우선한다.
- 사용자가 내부 전사 엔진 구조를 알 필요가 없어야 한다.
- 작업 진행 상태를 명확하게 표시한다.
- 긴 한글 파일명을 안정적으로 처리한다.
- 실패 원인을 사용자 관점에서 구분한다.
- 차분하고 집중하기 쉬운 업무용 UI를 유지한다.

## 개발 방식

Greenfield

기존 전사도우미 구현 소스는
신규 Sorigul 프로젝트의 dependency가 아니다.

## 현재 단계

UI Feature Gap Closure

## 현재 범위

- `전사`, `로그`, `Folders` 구조의 UI Feature Gap Closure
- 독립 Log Screen의 상태와 action 계약
- 전사·Retry·STOPPED·CANCELLED·CRASHED 상태와 action 계약
- 파일명, Direct Colab, Google Drive, Folders, Desktop UX의 UI 진입점
- UI State / UX Validation과 UI Freeze

## UI Freeze 이후 범위

- File Scan
- Filename Normalization
- Job Queue
- Local Whisper
- Colab
- Stop / Retry / Restore
- Result Formats
- Google Drive
- 실제 디스크 기반 Folders/Results
- Tray / Notification / Shutdown
- QA
- Desktop Packaging

## Legacy 정책

기존 전사도우미의 ACTIVE 기능과 검증 증거는 Migration Contract와 함께 기능 parity의 근거로 사용한다. Dashboard 제거처럼 Contract에서 승인된 `INTENTIONAL_CHANGE`만 보존 예외로 인정한다.

기존 소스 Copy / Import 금지.
