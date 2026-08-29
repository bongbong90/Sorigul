# 소리글 (Sorigul) 아이콘 시스템 (v1 Final)

## 1. 시각적 스타일

- **구현체**: `lucide-react`
- **적용 범위**: Lucide는 Navigation/UI icon에만 사용
- **스타일**: Outline
- **두께**: 1.75px (동일한 아이콘 세트 안에서 일관되게 유지)
- **형태**: Rounded Geometry (부드러운 곡선)
- **색상**: 기본적으로 `currentColor`를 상속
- **Fill**: `none`
- Component마다 임의 SVG path를 직접 작성하지 않고 Lucide React 제공 icon을 사용한다.

## 2. 크기와 정렬

- **기본 크기**: 20px. Navigation과 일반 Action에 사용
- **작은 크기**: 16px. 조밀한 보조 Action이나 Button 내부에서만 사용
- 아이콘은 정사각형 viewBox를 사용하고, Button 안에서는 16px 아이콘과 텍스트를 수직 중앙 정렬한다.
- Button의 아이콘과 텍스트 사이는 `space-compact`를 사용한다.
- **아이콘 단독 조작 영역**: 최소 40px × 40px를 확보한다.

## 3. 접근성

- 아이콘 단독 Button에는 동작을 설명하는 한국어 accessible name을 `aria-label`로 제공한다.
- 텍스트와 함께 있어 의미가 중복되는 아이콘은 `aria-hidden="true"`로 보조 기술에서 제외한다.
- 상태는 아이콘이나 색상만으로 표현하지 않고 반드시 텍스트와 함께 제공한다.

## 4. 주요 아이콘 분류
- **Navigation**: 전사, 로그, Folders, 설정
- **Actions**: 폴더 선택, 시작, 중지, 취소, Retry, 다시 전사, 새로고침, 편집, 삭제
- **Status**: 완료, 실패, 경고, 진행 중, 중지, 취소, 복구 필요

## 5. 브랜드 심볼

- Lucide icon은 Navigation, Action, Status 등 UI 기능 아이콘에만 사용하며 Sorigul의
  Native App Brand Icon을 대체하지 않는다.
- Sorigul Native App Brand Icon의 canonical master asset은
  `docs/design/reference/app-icon-v1.png`이다.
- canonical master의 색상·심볼은 변경하지 않는다. Windows 투명 배경 생성에는
  `docs/design/reference/app-icon-v1-transparent-runtime.png` 파생본을 사용한다.
- 128px 이상 및 EXE large-icon 표면은 canonical 파형 → 텍스트 모티프의 투명 파생본을
  사용한다.
- 16–64px Window title bar, Taskbar, Tray, EXE/Properties 표면은 같은 브랜드 계약을
  5개의 오디오 파형 막대 → 3개의 텍스트 선으로 pixel-native하게 단순화한다.
- small-surface 심볼은 Quiet Teal `#3E6874` 본체와 1px Primary Soft `#DCE9E9`
  언더레이를 사용한다. 언더레이는 어두운 Windows chrome에서 대비를 확보하기 위한
  브랜드 팔레트 처리이며 배경 타일이 아니다. 나머지 캔버스는 완전 투명하다.
- canonical master와 위 파생 규칙은 Window title bar, Windows Taskbar, Alt+Tab, EXE,
  Tray와 향후 Installer branding의 단일 원본 체계다.
- Native App Brand Icon 적용은 React UI의 Brand 영역에 심볼을 추가한다는 뜻이 아니다.
  UI Freeze에 따라 현재 text brand 구조는 변경하지 않는다.
