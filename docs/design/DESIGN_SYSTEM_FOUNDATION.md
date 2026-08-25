# Sorigul Design System Foundation

**Status: PASS**

## 1. 목적

`docs/design`에 확정된 규칙을 frontend 코드의 Design Token과
최소 공통 UI Primitive로 옮긴다.

실제 제품 화면(App Shell, Transcription Screen 등)은 만들지 않는다.

## 2. 기준 문서

- docs/design/design.md
- docs/design/brand.md
- docs/design/color_system.md
- docs/design/typography.md
- docs/design/icon_system.md
- docs/design/app_shell_spec.md

## 3. 구현한 token 범위

**Color** (`frontend/src/styles/tokens.css`) — `color_system.md` #1, #2를 그대로 이동.
- Core Palette: background / surface / surface-soft / surface-hover / border / border-strong /
  text-primary / text-secondary / text-muted / primary / primary-hover / primary-soft / primary-pressed
- Semantic Status: waiting / preparing / transcribing / saving / done / failed / cancelled
  (각 text / bg 쌍)

**Typography** (`frontend/src/styles/typography.css`) — `typography.md` #1~#5를 그대로 이동.
- font-family, font-weight(400/500/600/700), font-size(12/13/14/16/20/24),
  line-height(body 1.5 / ui 1.3), tabular-nums 유틸리티
- 문서의 크기·두께 조합(용도별)을 `.text-page-title` 등 semantic 클래스로 매핑

**Border width** — `app_shell_spec.md` #3 Top Bar 구분선에 명시된 `1px`을
유일하게 문서상 확인 가능한 값으로 보고 `--border-width`로 재사용.

**Design foundation** (`frontend/src/styles/tokens.css`)
- Spacing / Radius / Motion / Focus — `design.md` #5~#9의 확정 규칙을 token으로 이동
- Icon size / stroke / icon-only button size — `icon_system.md` #1~#3의 확정 규칙을 token으로 이동
- Shadow — `design.md` #7의 none-by-default 정책에 따라 shadow token과 elevation scale을 만들지 않음

## 4. 구현한 primitive

`frontend/src/components/ui/` — Button, Input, Badge, Progress, Card.

모두 위 Design token을 참조하며, 업무 로직(파일 처리, API 호출,
실제 job 상태 계산 등)은 포함하지 않는다. Badge의 7개 tone은
`color_system.md`의 Semantic Status 색상을 그대로 매핑한 시각 variant일 뿐,
실제 Job 상태 전이/backend contract와는 무관하다.

## 5. 구현하지 않은 항목

- App Shell, Sidebar, Navigation, Transcription Screen, Dashboard, Results
- Icon 컴포넌트 (구현체와 라이브러리는 App Shell 단계에서 결정)
- Dark Mode (문서에 명시적 정의 없음)
- Button/Badge size variant, loading visual (문서에 정의 없음)
- Progress indeterminate variant (문서에 정의 없음)

## 6. 확정한 design decisions

- **Spacing**: `design.md` #5의 최소 scale을 Button, Input, Badge, Progress, Card와
  Foundation Preview에 적용했으며 Primitive의 임시 `em` padding/gap을 제거했다.
- **Radius**: `design.md` #6의 기본 control/surface와 상태 Badge 두 역할만 적용했다.
- **Shadow**: `design.md` #7에 따라 기본적으로 사용하지 않는다.
- **Motion**: `design.md` #8에 따라 상호작용 색상 변화만 짧게 허용하고,
  reduced-motion에서는 제거한다. Layout/loading animation은 포함하지 않는다.
- **Icon**: `icon_system.md`에 style, stroke/fill, 기본/작은 크기, Button 정렬과
  접근성 규칙을 확정했다. 실제 구현체 선택은 App Shell 단계로 넘긴다.

## 7. 검증 방법

```
cd frontend
npm run lint
npm run typecheck
npm run build
```

추가로 `frontend/src` 전체에서 hex color / font-size 하드코딩을 검색하여
`styles/tokens.css`, `styles/typography.css` 이외의 위치에 값이 없음을 확인했다.

검증 결과:

- `npm run lint` PASS
- `npm run typecheck` PASS
- `npm run build` PASS
- `git diff --check` PASS
- Primitive 임시 `em` spacing, 반복 hex/radius/spacing/shadow 하드코딩 없음

## 8. 다음 Phase

App Shell
