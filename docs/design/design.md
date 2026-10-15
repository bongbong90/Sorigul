# 소리글 (Sorigul) 디자인 가이드라인 (v1 Final Freeze)

## 1. 개요
소리글(Sorigul)은 '소리를 글로'라는 가치를 담은 Windows 데스크톱용 전문 음성 전사 관리 도구입니다.

## 2. 디자인 원칙
- **Quiet Teal Identity**: 저채도의 Teal 컬러를 통해 눈의 피로를 줄이고 신뢰감을 제공합니다.
- **Pure Korean UI**: 직관적인 한국어 UI를 지향하며 불필요한 영어 병기를 배제합니다.
- **Information Density**: 데스크톱 환경에 최적화된 높은 정보 밀도를 유지하되 정돈된 위계를 통해 사용성을 확보합니다.

## 3. 핵심 에셋
- **App Icon**: 오디오 파형이 텍스트 라인으로 변하는 연속적인 심볼. (문자 미포함)
- **Main Color**: #3E6874 (Quiet Teal)
- **Background**: #F3F5F4
- **Surface**: #FAFBFA

## 4. UI 상태 언어
- **WAITING** -> 대기
- **PREPARING** -> 준비 중
- **TRANSCRIBING** -> 전사 중
- **SAVING** -> 저장 중
- **DONE** -> 완료
- **FAILED** -> 실패
- **CANCELLED** -> 중지됨

## 5. Spacing System

반복 간격은 다음 여섯 단계만 사용한다. 컴포넌트의 글자 크기에 반드시 비례해야 하는
예외를 제외하면 padding과 gap에 `em`을 사용하지 않는다.

| Token | Value | Usage |
| :--- | :--- | :--- |
| `space-tight` | `4px` | 라벨과 도움말처럼 아주 가까운 요소 사이 |
| `space-compact` | `8px` | 작은 내부 간격, Badge padding, 아이콘과 텍스트 사이 |
| `space-control` | `12px` | 일반 control의 가로 padding, 가까운 control 사이 |
| `space-component` | `16px` | 일반 component 간 간격, Button 가로 padding |
| `space-section` | `24px` | Card 내부와 section 간 간격, App Shell 본문 표준 padding |
| `space-page` | `32px` | Foundation Preview와 큰 page/layout 구획 간격 |

새 간격은 실제 화면에서 위 단계로 표현할 수 없는 반복 패턴이 확인될 때만 추가한다.
App Shell의 고정 너비와 높이는 spacing token이 아니라 해당 화면의 layout 규격이다.

## 6. Radius System

- **기본 control/surface (`radius-control`)**: `4px`. Button, Input, Card, Progress처럼
  경계가 있는 기본 요소에 사용한다.
- **상태 Badge (`radius-badge`)**: `999px`. 짧은 상태 텍스트 Badge에만 허용한다.

Badge 이외의 control을 pill 형태로 만들지 않으며, 크기별 radius scale은 두지 않는다.

## 7. Shadow Policy

`shadow policy = none by default`로 확정한다. 기본 surface와 control은 border와 배경색으로
위계를 만들고 `box-shadow`를 사용하지 않는다. Overlay 등 별도 위계가 실제로 필요해지면
해당 component 규격에서 예외를 먼저 문서화하며, 현재 단계에는 elevation scale을 만들지 않는다.

## 8. Motion Policy

- hover, active, disabled 같은 상호작용 상태의 색상 변화에만 `120ms ease-out` transition을 허용한다.
- focus-visible outline은 지연 없이 즉시 표시한다.
- 위치와 크기가 바뀌는 layout transition 및 장식 목적 animation은 사용하지 않는다.
- loading animation은 후속 UI State 구현 단계에서 접근성 기준과 함께 결정한다.
- `prefers-reduced-motion: reduce`에서는 허용된 상태 transition도 제거한다.

## 9. Focus Indicator

Keyboard focus는 Primary 색상의 `2px` outline과 `2px` offset으로 표시한다.
focus 표시를 색상 변화만으로 대체하지 않는다.
