# Sorigul Transcription Screen — Static UI

**Status: PASS**

## 1. 목적

승인된 전사 화면 규격을 기존 App Shell의 Main Content 안에 정적인 React UI로 구현한다.
실제 파일 탐색, Queue 관리, 전사 작업 또는 Mock Interaction은 포함하지 않는다.

## 2. 기준 문서

- `docs/design/TRANSCRIPTION_SCREEN_SPEC.md`
- `docs/design/UI_STATE_MATRIX.md`
- `docs/design/UI_FREEZE_CHECKLIST.md`
- 공통 Design 및 App Shell 문서
- Project Charter, Roadmap, Development Rules

화면 구조와 문구는 `TRANSCRIPTION_SCREEN_SPEC.md`를 최우선 기준으로 적용했다.

## 3. 구현 영역

- 기존 Top Bar의 전사 화면 Header
- 현재 폴더 경로와 폴더 변경 Button
- 전사 시작/중지 Action과 전체 진행률
- 현재 파일, 상태 Badge, 진행률, 예상 남은 시간
- 선택, 파일명, 재생시간, 상태 Column으로 구성된 semantic Queue table

## 4. Component 구조

```text
App
└─ AppShell
   └─ TranscriptionPage
      ├─ FolderSection
      ├─ TranscriptionActions
      ├─ CurrentTaskSection
      └─ QueueTable
```

화면 전용 레이아웃은 `styles/transcription-screen.css`에서 담당한다.

## 5. Static Sample 상태

화면 검증을 위해 `TRANSCRIBING` 상태 하나를 고정 Preview로 사용한다. 현재 진행률은 64%,
전체 진행률은 1 / 4 완료이며 Queue에는 완료, 전사 중, 대기 Badge 예시와 긴 한국어 파일명을
포함한다. 이 값은 frontend 표시용 상수이며 API contract나 업무 model이 아니다.

## 6. Design System 재사용

- Button, Badge, Progress, Card Primitive 재사용
- 기존 color, typography, spacing, radius, border, focus, motion, icon token 재사용
- Action icon은 `lucide-react`의 outline icon을 기존 크기와 1.75px stroke 규칙으로 사용
- 신규 Primitive variant와 dependency 추가 없음

## 7. Table overflow 처리

Table은 고정 layout과 가로 overflow container를 사용한다. 파일명 Column은 남은 폭을 사용하고
긴 이름은 한 줄 ellipsis로 제한한다. 전체 파일명은 native `title`로 확인할 수 있으며,
재생시간과 상태 Column은 고정 폭과 줄바꿈 방지를 적용해 침범을 막는다.

## 8. 구현하지 않은 기능

- Folder dialog와 파일 시스템 접근
- MP3 탐색, 자동 로드, Drag & Drop, Auto Refresh
- Checkbox 선택 상태 계산과 Queue 변경
- Start, Stop, Retry, Remove 동작
- Progress 갱신, ETA 계산, Timer
- API, Backend, Tauri, Whisper, Colab, Google Drive 연결
- Mock Interaction과 업무용 React state

## 9. 검증 결과

- `npm run lint`: PASS
- `npm run typecheck`: PASS
- `npm run build`: PASS
- `git diff --check`: PASS
- App Shell 구조, Main Content scroll 및 직접 SVG 미사용 확인
- fetch, axios, timer, filesystem/Tauri/backend 호출 미사용 확인

## 10. Unresolved

없음.

## 11. 다음 Phase

Transcription Screen — Mock Interaction
