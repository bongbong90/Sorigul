# Sorigul App Shell

**Status: PASS**

> **Contract alignment:** 이 PASS는 당시 App Shell layout 구현 기록이다. 구현 범위에 기록된 당시 navigation(`전사`, `대시보드`, `결과`, `설정`)은 현재 제품 계약이 아니다. `MIGRATION_CONTRACT.md`에 따라 제품 navigation은 `전사`, `로그`, `Folders`와 설정 진입점으로 바뀌며 Dashboard 전용 화면은 제거한다. 실제 component 정렬은 UI Feature Gap Closure에서 수행한다.

## 1. 목적

`app_shell_spec.md`의 고정된 데스크톱 레이아웃을 React 구조와 CSS로 옮긴다.
후속 제품 화면이 같은 Sidebar, Top Bar, Main Content 구조 안에서 구현될 수 있도록 한다.

## 2. 구현 범위

- 240px 고정 너비 Sidebar
- 64px 고정 높이 Top Bar
- 24px padding과 1200px 최대 너비를 적용한 Main Content slot
- 승인된 별도 Brand symbol asset이 없어 text brand로 유지한 `소리글`
- 당시 구현된 전사, 대시보드, 결과, 설정 navigation (현재 Contract gap은 상단 주석 참조)
- 활성 navigation 배경, 색상, 3px 좌측 indicator
- `lucide-react` 기반 20px outline navigation icon (stroke 1.75px)
- keyboard focus와 hover 상태

## 3. 구조

```
frontend/src/
├─ components/
│  ├─ icons/AppIcons.tsx
│  └─ layout/AppShell.tsx
└─ styles/app-shell.css
```

`AppShell`은 현재 navigation과 페이지 제목, Main Content의 `children` slot만 담당한다.
페이지별 콘텐츠와 실제 route 상태는 이 컴포넌트 밖에서 주입한다.

## 4. 비범위

- 전사 화면의 파일 선택, 옵션, 진행 상태 UI
- 당시 계획의 Dashboard와 Results 화면
- navigation route 전환과 mock interaction
- backend, 파일 시스템, API 연동
- 반응형 mobile navigation

## 5. 검증

기존 App Shell은 Navigation/UI icon과 Brand symbol을 직접 작성한 inline SVG로 구현해
아이콘 구현 기준을 충족하지 못했으므로 PASS 판정이 보류되었다.

보류 해소 조건:

- Navigation/UI icon을 `lucide-react` 기반으로 전환
- 직접 작성한 SVG path/rect/circle 제거
- 승인되지 않은 Brand symbol 제거 및 text brand 유지
- App Shell layout 회귀 없이 전체 검증 통과

```
cd frontend
npm run lint
npm run typecheck
npm run build
```

검증 결과:

- `npm run lint` PASS
- `npm run typecheck` PASS
- `npm run build` PASS
- `git diff --check` PASS
- `git status --short` 실행 및 변경 범위 확인 완료
- `AppIcons.tsx` 직접 작성 SVG path/rect/circle 없음
- 신규 dependency는 `lucide-react`만 추가
- Brand는 임의 icon 없이 text brand만 사용
- Sidebar 240px, Top Bar 64px, Navigation/Active state/Main Content 구조 유지
- backend/ 및 desktop/ 변경 없음
- 실제 Feature 구현 없음

## 6. 다음 Phase

Transcription Screen
