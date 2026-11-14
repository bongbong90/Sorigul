# [SORIGUL PHASE 18A 결과]

- 작업 판정: auth_uri metadata 호환성 수정·합성 Mock·Backend 전체 회귀·실제 로컬 JSON 읽기 전용 검증 PASS. LIVE OAuth/API는 NOT RUN.
- Issue: #254 / 부모 PR: #253.
- 부모 HEAD: `8d750824d08e2567e397fbc4be31aad39ae87db9` — 착수·완료 전 원격 일치 확인.
- Branch: `fix/254-colab-oauth-json-compatibility`.
- Draft PR base: `feature/252-official-colab-oauth`.
- 최종 Commit·Push·Draft PR 링크와 #254·#252·#48·#7 기록은 완료 댓글에 남긴다.

## 수정 범위

`load_client()`의 metadata 검사에만 다음 두 문자열을 정확한 허용 목록으로 적용했다.

- https://accounts.google.com/o/oauth2/v2/auth
- https://accounts.google.com/o/oauth2/auth

실제 인증 URL은 기존 AUTH_URL인 **https://accounts.google.com/o/oauth2/v2/auth**로 생성한다. JSON의 auth_uri를 실행 주소로 사용하지 않는다. 그 외 URL·HTTP·다른 도메인·위장 호스트·사용자정보·query/fragment·경로/포트 변형은 거부한다.

Google Token endpoint, installed 구조, client_id·project_id·client_secret, reparse/symlink, Drive 프로젝트/client 분리, OAuth Scope, 실행 승인 조건은 유지했다. 실제 사용자 JSON을 수정하거나 코드/테스트에 복사하지 않았다.

## 검증

| 항목 | 결과 |
| --- | --- |
| 신규 metadata 회귀 | 31 PASS |
| 기존 포함 OAuth Mock 전체 | 87 PASS |
| 최종 Backend 전체 | 1587 PASS / 2 SKIP / 0 FAIL / 0 ERROR / 기존 warning 1 |
| diff 및 staged whitespace check | PASS |
| Frontend 검사 | NOT RUN — Frontend 변경 없음 |
| 실제 Google OAuth/계정/API | NOT RUN / 실제 요청 0회 |

회귀는 합성 JSON만 사용했다. 두 auth_uri 정상 통과와 양쪽의 v2 URL 생성, 다른 URL 거부, token_uri/필수 필드 검증 유지, Drive 동일 project/client 거부를 확인했다. 실제 Google 전송을 차단한 기존 Mock provider/callback을 사용했으며 신규 검사에서 Google/Colab 요청과 실패 시 callback 생성이 없음을 검증했다.

Backend 전체는 기존 conftest의 사용자 앱 데이터 격리, venv site-packages 및 backend의 절대 sys.path, 테스트 프로세스 전용 PS5 모듈 경로를 사용했다. `pytest.main(['backend/tests','-q','--tb=short','--junitxml=tmp/phase18a-backend-regression.xml'])` 결과 216.37초다. XML은 ignored tmp에만 보존한다. SKIP은 non-Windows HOME fallback과 호스트 symlink 권한 부재, warning은 기존 Starlette/httpx deprecation이다. 시스템 실행 정책을 변경하지 않았다.

## 로컬 발급 JSON 재점검

착수 시 정확한 `google_colab_oauth_client.json` 파일이 존재했고 이전의 `.json.json` 파일은 없었다. 사용자가 정정한 파일명은 그대로 두었다. 수정된 제품 load_client로 `%LOCALAPPDATA%\Sorigul\auth\google_colab_oauth_client.json`을 읽기 전용 검증하여 PASS했다. CONFIG_REQUIRED 및 CONFIG_INVALID가 해소됐다. 검사 전후 원본 파일 SHA-256을 메모리에서 비교하여 바이트 동일함을 확인했으며 hash·client ID·project ID·Secret 원문은 출력/보고서에 남기지 않았다.

로컬 재점검 프로세스는 socket connect와 urllib opener를 차단했고 실제 OAuth 서비스 start/check/revoke를 호출하지 않았다. Token endpoint·최소 Scope·COST/POLICY 차단 조건 유지, 원본 JSON의 저장소 외부 위치, Colab token 파일 부재를 확인했다. Token 내용은 읽지 않았다.

**Drive 프로젝트 분리: NOT VERIFIED.** 기본 경로의 Drive 공개 client JSON이 없어 실제 project/client를 대조할 수 없다. 비교 파일 부재나 load_client 통과를 분리 PASS로 보고하지 않는다. 별도 로컬 비교 경로를 문의했으며 추가 자료가 없는 현재 결과는 미검증이다. 합성 JSON의 동일 project/client 거부 회귀는 양쪽 auth_uri 모두 PASS다.

**Google Cloud OAuth 설정 유효성: 로컬 Desktop JSON 형식과 고정 endpoint 검사만 PASS.** 실제 Cloud 프로젝트/API 활성화·consent/test user·클라이언트 유효성·실제 부여 Scope·신원은 Google API나 OAuth 없이 확인할 수 없으므로 NOT VERIFIED다.

## 보존 및 다음 조건

변경 파일은 colab_oauth.py, test_colab_oauth.py 및 이 보고서 3개다. 기존 미추적 monitor.ps1, smoke.ps1, smoke_desktop.ps1, smoke_qa.ps1, tunnel_log는 기존 기준 해시와 동일하며 수정·실행·Stage하지 않았다. 사용자 OAuth JSON·Token은 Git 포함 0건이다. 원본 JSON·토큰·사용자 데이터 변경이나 Integration/main·기존 Draft PR 병합은 없다.

남은 LIVE-A 준비 조건은 Drive project/client 분리 대조, 실제 Google Cloud 설정 확인 및 사용자 별도 LIVE-A 승인이다. 승인 전에는 실제 OAuth 동의·Google 계정/API 요청을 하지 않는다. Runtime/GPU·모델·MP3·Drive 변경·유료 자원은 이번 범위에서 실행하지 않는다.

COST_GATE=CONDITIONAL / POLICY_GATE=NOT VERIFIED / OFFICIAL_COLAB_LAUNCH=BLOCKED / DEFAULT OFF / STUDY USE READY=NO / MAIN MERGE=HOLD 유지. PHASE 18A 완료 후 STOP.
