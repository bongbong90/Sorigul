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
- **Navigation**: 전사, 대시보드, 결과, 설정
- **Actions**: 폴더 선택, 시작, 중지, 새로고침, 편집, 삭제
- **Status**: 완료, 실패, 경고, 진행 중, 중지

## 5. 브랜드 심볼

- Lucide icon은 Sorigul의 Brand logo/symbol 대체 용도로 사용하지 않는다.
- 승인된 별도 Brand symbol asset이 없으면 Brand 영역은 text brand만 사용한다.
- Brand symbol은 별도 승인된 asset이 제공된 뒤에만 추가한다.
