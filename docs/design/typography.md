# 소리글 (Sorigul) 타이포그래피 시스템 (v1 Final)

## 1. 기본 글꼴 (System Font)
- **Family**: "Noto Sans KR", sans-serif
- **의존성**: 사용자 시스템에 설치된 로컬 글꼴 사용 (외부 CDN 의존성 없음)

## 2. 두께 체계 (Weights)
- **400 Regular**: 일반 본문, 설명문, 데이터 필드, 파일명
- **500 Medium**: 네비게이션 라벨, 버튼 텍스트, 테이블 헤더
- **600 SemiBold**: 섹션 타이틀, 강조 데이터, 상태 강조
- **700 Bold**: 페이지 타이틀, 핵심 수치

## 3. 크기 체계 (Sizes)
- **12px (XS)**: 보조 정보, 타임스탬프
- **13px (SM)**: 상태 Badge, 캡션, 2차 정보
- **14px (MD)**: 기본 UI, 테이블 데이터, 파일명, 버튼 (Standard)
- **16px (LG)**: 섹션 헤딩, 강조 데이터
- **20px (XL)**: 카드 타이틀
- **24px (2XL)**: 페이지 타이틀

## 4. 숫자 표기 규칙
- **Tabular Numerals**: 진행률, 시간, 수치 데이터에 적용
- **CSS**: `font-variant-numeric: tabular-nums;`

## 5. 행간 (Line Height)
- **Body**: 1.5
- **UI Elements**: 1.3
- **Table Row**: 데이터 수직 정렬 최적화 (Vertical Center)