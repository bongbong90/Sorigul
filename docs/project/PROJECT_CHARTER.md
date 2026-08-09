# Sorigul Project Charter

## 프로젝트 목적

소리글(Sorigul)은 Windows용 음성 전사 및
전사 결과 관리 데스크톱 애플리케이션이다.

사용자가 음성 파일을 간단하게 전사하고
진행 상태와 결과를 명확하게 관리할 수 있도록 한다.

## 제품 원칙

- 기능은 계승하고 구조는 계승하지 않는다.
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

Project Foundation
+
UI/UX First

## 현재 범위

- Design System
- App Shell
- Transcription UI
- Mock Interaction
- Dashboard UI
- Results UI
- UI State Model
- UI Freeze

## UI Freeze 이후 범위

- File Scan
- Filename Normalization
- Job Queue
- Local Whisper
- Colab
- Stop / Retry / Restore
- Result Formats
- External Upload
- Real Dashboard Data
- Real Results Data
- QA
- Desktop Packaging

## Legacy 정책

기존 전사도우미는 기능 요구사항 참고자료로만 사용한다.

기존 소스 Copy / Import 금지.
