# Sorigul UI State Matrix

상태:

EMPTY
IDLE
WAITING
PREPARING
TRANSCRIBING
SAVING
DONE
FAILED
CANCELLED

사용자 표시:

IDLE → 준비
WAITING → 대기
PREPARING → 준비 중
TRANSCRIBING → 전사 중
SAVING → 저장 중
DONE → 완료
FAILED → 실패
CANCELLED → 중지됨

EMPTY는 화면 상황에 맞는 Empty State를 사용한다.

주의:

이 문서는 UI State 정의 문서다.

Backend State Machine을 구현하지 않는다.
