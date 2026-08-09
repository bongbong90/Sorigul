# 소리글 (Sorigul) 앱 셸 규격 (v1 Final)

## 1. 구조 (Layout)
- **Sidebar**: 고정 너비 240px (좌측)
- **Top Bar**: 고정 높이 64px (우측)
- **Main Content**: 유동적 너비 (사이드바 제외 영역 전체)

## 2. 사이드바 (Sidebar)
- **배경색**: `#FAFBFA` (Surface)
- **로고 영역**: 상단 [브랜드 심볼 + 소리글] 표시. (Subtitle 없음)
- **네비게이션 아이템**:
  - 높이: 48px
  - 폰트: 14px, Medium (500)
  - 활성 상태: 배경 `#DCE9E9`, 텍스트/아이콘 `#3E6874`, 좌측 3px 인디케이터.
  - 설정: 사이드바 최하단 고정.

## 3. 상단 바 (Top Bar)
- **배경색**: `#FAFBFA` (Surface)
- **구분선**: 하단 1px 실선 (`#D6DEDC`)
- **내용**: 좌측에 현재 페이지 타이틀 (24px, Bold) 표시.
- **제거**: 알림, 설정 아이콘 (Sidebar 이동 및 최소화).

## 4. 본문 영역 (Main Content)
- **배경색**: `#F3F5F4` (Background)
- **패딩**: 24px (Standard)
- **최대 해상도**: 1440px 이상에서 콘텐츠 가독성을 위한 레이아웃 제한 권장.