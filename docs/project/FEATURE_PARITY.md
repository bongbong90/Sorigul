# Sorigul Feature Parity

## 반드시 계승할 기능

- 전사 폴더 선택
- MP3 목록
- 파일 선택 Checkbox
- 전체/선택 파일 전사
- 긴 파일명 처리
- 파일명 정규화
- 다음 빈 강 번호 자동 배정
- 완료 파일 Skip
- 현재 파일 진행률
- 전체 진행률
- ETA
- 전사 시작
- 전사 중지
- 실패
- 재시도
- TXT
- JSON
- SRT
- Dashboard
- 결과 Preview
- 설정
- Notification
- 전체 완료 후 처리 옵션

## 재설계 대상

- 전사 엔진 선택 UX
- Colab 연결 UX
- 결과 화면
- 설정 화면
- 상태 표현
- 외부 업로드 상태

## Legacy Reference Only

- PySide UI
- gui_main.py
- auto_transcribe.py
- stdout EVENT 통신
- Google Drive Queue 구조
- 기존 session 방식

## 제거 대상

- 내부 개발 용어를 사용자 UI에 직접 노출하는 구조
- Drive Queue 중심 사용자 경험
- 개발자용 설정의 기본 화면 노출

## 미정

구현 방식이 확정되지 않은 사항은
현재 단계에서 임의로 결정하지 않는다.
