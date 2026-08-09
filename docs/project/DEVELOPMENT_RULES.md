# Sorigul Development Rules

- 기존 전사도우미 코드 Copy 금지
- Legacy Python module Import 금지
- Legacy 코드는 dependency가 아님
- UI Freeze 전 실제 transcription 구현 금지
- UI Freeze 전 backend 대규모 구조 설계 금지
- Backend 요구 때문에 확정 UI를 임의 변경하지 않음
- 사용자 UI에 내부 engine 이름 노출 금지
- Mock Interaction을 먼저 검증
- 실제 기능은 확정 UI Contract에 연결
- DONE 이전에는 100% 완료 표시 금지
- 전사 결과와 외부 업로드 상태를 분리
- build/dist/cache/generated 파일 Git 추적 금지
- credential/token Git 추적 금지
- git add . 사용 금지
- main 직접 개발 금지
- Phase/Task 단위 branch 사용
- 사용자 검토 없이 자동 merge 금지
- 사용자 검토 없이 자동 push 금지
