# #195 유휴 X 종료 — Source 정책 및 검증

## 읽기 전용 관찰

2026-10-15 정상 사용자 프로필에 저장된 close_behavior는 `tray`였다.
현재 Native callback은 이 값이면 즉시 창을 숨기므로 관찰된 X 동작은
현재 설정으로 설명된다. 당시 Native cache/Backend close-guard의 실시간
값은 앱을 실행하지 않았으므로 확인하지 않았다. `exit`+확정 유휴에서의
종료 실패를 재현한 것으로 주장하지 않는다.

과거 기본값을 저장한 Tray와 사용자가 직접 선택한 Tray를 구분하는 필드는
없다. 기존 저장값을 자동으로 변경하거나 마이그레이션하지 않는다.

## 최소 변경

- 신규/close_behavior가 없는 설정은 `exit`. 유효한 저장값 `tray`/`exit` 보존.
- Frontend 표시 기본값도 `exit`이나 Backend 설정 확인 이전에는 Native에
  임시 값을 동기화하지 않는다.
- App startup hook은 Native 적용 성공 후에만 동기화 완료로 기록한다.
  Backend/Native 실패는 재시도하며, 해제 뒤 늦은 응답으로 적용하지 않는다.
- Native 초기 캐시 `tray`는 설정 확인 전의 안전한 동작으로 유지한다.
  실제 저장값을 받아야 Exit 정책을 적용한다. 설정/작업 상태 불확실 시
  종료하지 않는다는 사용자 요구와 일치한다.
- #128/#174 경로 유지: idle Exit → close guard → `app.exit(0)` → 중앙 cleanup;
  active Local/Drive 또는 guard 실패 → 안전한 Tray 이동. 명시적 Tray 종료도
  같은 guard를 사용하고 복원 중 늦은 유휴 응답은 종료시키지 않는다.

## 검증

- Backend/settings/close guard/기존 metadata·Drive/Native wiring pytest **72 PASS**.
  신규 기본값, 기존 Tray/Exit byte 보존 및 unrelated 설정 저장 후 유지,
  명시적 신규 Tray, 소유 Future/Drive 보호, 불확실 상태 계약 포함.
- Rust `close_guard::tests` **15 PASS**: idle Exit, idle Tray, 전사/Drive,
  Backend 불가/지연/잘못된 응답, Tray 명시 종료, 복원 중 늦은 응답 보호.
- Rust `sidecar::tests::cleanup` **4 PASS**: owned synthetic 프로세스 정리,
  이중 cleanup, unrelated synthetic 프로세스 보존, trusted taskkill 경로.
- production startup hook 실행 harness **4 PASS**: 저장 Tray, Native 실패
  재시도, Backend 실패 재시도, 해제 후 늦은 응답.
- Frontend typecheck/lint **PASS**.
- 실제 PC 종료/사용자 설정 변경/제품 설치본 실행/Runtime 교체 **NOT RUN**.
  변경된 최종 Integration의 실제 X 종료 후 Desktop/Backend/Worker/Owned
  WebView=0 및 TCP 8000 FREE Acceptance는 다음 계획된 설치형 검증에서 수행한다.

이 결과는 종료 정책/보호/cleanup Source 검증이다. 새 기본값을 가진 제품
설치본의 종합 종료 PASS로 확대하지 않는다. PR 승인/Integration 반영 및
별도 릴리스 주기까지 Issue를 OPEN으로 유지한다.
