# Sorigul Roadmap

`MIGRATION_CONTRACT.md`가 제품 행동과 마이그레이션의 최우선 기준이다. 완료된 UI foundation 이력과 앞으로의 실행 순서를 분리한다.

## Completed Baseline

- Project Foundation
- Design System v1
- App Shell
- Transcription Screen foundation
- Mock Interaction foundation
- Contract Baseline Sync

이 항목들은 초기 UI foundation 작업 이력이다. 당시 Dashboard/Results를 전제로 한 계획은 현재 제품 navigation을 뜻하지 않는다.

## Current Stage

- **UI Feature Gap Closure** — `전사`, `로그`, `Folders` 구조와 누락된 Legacy ACTIVE 기능의 UI 계약 보완

## Migration Sequence

1. **Contract Baseline Sync** — 완료
2. **UI Feature Gap Closure** — 현재

3. **UI State / UX Validation** — 전사·실패·Retry·중지·취소·복구·Colab·Google Drive·runtime 상태 검증
4. **UI Freeze** — Contract의 사용자 흐름과 action 승인
5. **Core Backend / File / Job Migration** — scan, normalization, bundle verification, queue, persistence/recovery
6. **Transcription Engine Migration** — Local Whisper와 Direct Colab 계약 구현
7. **Google Drive / Results / Desktop UX** — Drive, 실제 디스크 기반 Folders, Log, Tray, Notification, Shutdown
8. **Tauri Runtime / Installed Product** — sidecar lifecycle, Windows/Unicode, MSI와 설치 환경 검증
9. **1:1 Parity Regression / Release** — Contract·Audit 기반 회귀, 설치형 통합 QA와 release

세부 Backend 구조, D09 Result 탐색/API 방식과 Log 저장 구조는 해당 구현 단계 전까지 확정하지 않는다.
