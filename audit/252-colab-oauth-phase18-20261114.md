# [SORIGUL PHASE 18 결과]

- 작업 판정: 제품 구현·Mock·필수 Backend/Frontend 검증 PASS. 실제 계정/GPU 사용은 미실행.
- 작업 Issue: #252. 관련 #48 #60 #233 #114 #7.
- 부모 PR: #251 / 부모 HEAD `f3c5fdbc6495beafc25c6bfa9788203ce69d5a74` — 착수 및 완료 전 로컬·원격 일치.
- Branch: `feature/252-official-colab-oauth`
- Draft PR base: `feature/48-colab-automatic-model-provisioning`
- 완료 Commit·Push·Draft PR 및 Issue 기록 링크는 #252 완료 댓글에 기록한다.

## 구현 및 보안

별도 ColabOAuthService, 고정 Google provider, 단일 사용 loopback callback, 사용자별 DPAPI 저장소와 설정 UI를 추가했다. Authorization Code + S256 PKCE, state, 정확한 callback Host/peer/path, 중복/재사용 응답, signed ID Token의 nonce/audience/issuer/expiry/발급시각, 정확한 access token의 UserInfo 계정을 확인한다. Token 응답에서 실제 부여 Scope를 확인하고 요청/Settings/callback의 Scope 선언은 신뢰하지 않는다.

요청 Scope는 openid + https://www.googleapis.com/auth/colaboratory뿐이다. 부족·Drive·readonly-only·추가 Scope·불완전 발급은 거부한다. Scope 증명은 TOKEN_RESPONSE_VERIFIED, Runtime 생성 권한은 NOT_VERIFIED다. subscription/runtimespecs GET 성공은 생성 권한·무료 GPU 확보·비용 0원 증명이 아니다.

Drive OAuth/service/token과 Colab OAuth/service/token은 분리했다. Colab token은 현재 Windows 사용자 DPAPI와 전용 entropy로 암호화하여 전용 ACL 파일에 저장하며 plaintext fallback은 없다. Drive의 공개 client 설정이 있으면 같은 client/project를 거부한다. Google 철회가 프로젝트 전체 grant에 영향을 주므로 실제 provisioning은 반드시 별도 프로젝트/Desktop client로 해야 한다.

인증 상태 polling은 Google 요청을 하지 않는다. 사용자 check 또는 static gate를 통과한 서버 launch 경로에서만 안전하게 refresh/계정 확인한다. refresh Scope 누락/다른 계정은 실패한다. 인증 취소·늦은 callback·동시 refresh/revoke·변조 저장소는 기존 인증정보를 잘못 대체하지 않는다. 진행 중 공식 Job·미정리 Runtime은 계정 연결 변경/철회를 차단하고 원격 작업을 임의 삭제하지 않는다.

제품 routes는 인증 서비스를 기존 OfficialColabLauncher에 공급하되 Resolver는 DEFAULT OFF다. GoogleAccountVerifier·기존 read-only preflight·RuntimeOwnership·공식 Job 엔진·PHASE 17 모델 준비는 유지한다. 클라이언트 body의 token/scope/config/approval/redirect field와 외부 Origin·form 요청은 거부한다. 로그/Job/일반 Settings/상태 API에는 인증정보·계정 신원을 기록하지 않는다.

Desktop 설정에 Google Drive와 구분된 Colab 카드, 연결·다시 인증·연결 확인·취소·연결 해제를 추가했다. 연결 안 됨, 인증 진행 중, 연결됨, 권한 부족, 인증 갱신 필요, 계정 확인 실패와 별도 실행 조건 미확인·차단 사유를 표시한다. 브라우저 실패 시 진행 중 listener를 취소한다.

## 검증 결과

| 검증 | 결과 |
| --- | --- |
| 신규 OAuth 외부 네트워크 차단 Mock | 56 PASS |
| OAuth + 기존 Desktop API 계약 집중 회귀 | 64 PASS |
| 기존 PHASE 17 + 공식 launch/adapter 집중 회귀 | 111 PASS |
| 최종 Backend 전체 | 1556 PASS / 2 SKIP / 0 FAIL / 0 ERROR / 기존 warning 1 |
| PHASE 17 모델 준비 (최종 전체에 포함) | 46 PASS |
| Frontend lint | PASS |
| Frontend typecheck | PASS |
| Frontend build | PASS |
| 추가 문서/릴리스 계약 검사 | 12 PASS / 부모에도 존재하는 불일치 2개 |
| 실제 OAuth/Google 계정·API 조회 | NOT RUN |
| 실제 Runtime/GPU/모델 다운로드 | NOT RUN |

Mock은 실제 서비스/provider/API/PKCE/GoogleAccountVerifier/preflight 코드를 사용하고 Google Token/UserInfo/인증서/Colab HTTP만 가짜로 대체한다. 실제 loopback HTTP handler 및 테스트 RSA 인증서로 서명한 ID Token 검증, 합성 비밀의 Windows DPAPI roundtrip/변조 거부도 검증했다. Runtime POST는 차단 경로에서 0회다. 실제 계정의 자격증명이나 사용자 MP3는 사용하지 않았다.

최종 전체는 Python 3.13.14와 기존 venv site-packages를 절대 sys.path에 추가해 `pytest.main(['backend/tests','-q','--tb=short','--junitxml=tmp/phase18-backend-regression.xml'])`로 실행했다. 테스트 프로세스에만 PSModulePath를 Windows PowerShell 5.1 기본 모듈 경로로 지정했다. 시스템 설정/실행 정책 변경 없음. pytest 요약 123.99초, XML suite 123.902초/1558 cases다. XML은 ignored tmp 경로에 보존한다. 사용자 앱 데이터는 기존 conftest가 임시 경로로 격리한다.

최초 전체 실행의 유일한 실패는 FastAPI의 지연 중첩 router와 기존 flat route 검사 계약의 불일치였다. 기존 제품 router에 직접 등록하도록 수정하고 집중 회귀 및 최종 전체 회귀가 통과했다. 두 최종 SKIP은 non-Windows HOME fallback과 호스트 symlink 생성 권한 부재, warning은 기존 Starlette/httpx deprecation이다.

추가 root 계약 검사의 실패는 부모 HEAD의 Git 객체로 동일함을 확인했다. 기존 docs/project/48_COLAB_DRIVE_VALIDATION_2026-11-11.md의 원장 누락과 python-multipart==0.0.32를 금지하는 오래된 테스트 기대값 불일치다. 이번 신규 문서 두 개는 원장에 등록했다. 이 두 기존 계약은 변경하지 않았으며 Root 전체 PASS를 주장하지 않는다.

## Google Cloud 준비 및 LIVE 승인

Drive와 별도 Google Cloud 프로젝트, Colab API 제공/활성화 가능 여부, OAuth Branding/Audience/Data Access/test user 또는 심사 조건, Google이 발급한 Desktop installed client JSON의 전용 provisioning이 필요하다. 실제 ID/Secret을 생성·복사·provisioning하지 않았다. 세부 준비는 docs/COLAB_PHASE18_OAUTH.md에 기록했다.

별도 승인 1: 지정 테스트 계정의 실제 OAuth 동의·최소 Scope/신원 확인·공식 subscription/runtimespecs 읽기 전용 검증. 이 단계에 Runtime/GPU/Drive 변경은 포함하지 않는다.

별도 승인 2: 비용·정책·서버 권한 조건 검토 후, 제한된 임시 Runtime 1회·GPU·고정 패키지/모델·합성 MP3·결과 검증·해당 Runtime 정리·비용/사용량 관찰 및 #233 Contents 호환성 확인. 이후 긴 MP3·중단/복구·실제 강의/Drive 업로드는 별도 범위다. docs/COLAB_PHASE18_LIVE_VALIDATION_PLAN.md는 계획이며 실행 승인이 아니다.

COST_GATE=CONDITIONAL / POLICY_GATE=NOT VERIFIED / OFFICIAL_COLAB_LAUNCH=BLOCKED / DEFAULT OFF / STUDY USE READY=NO / MAIN MERGE=HOLD 유지. 결제정보 미연결은 정책 적합성이나 비용 0원 증거가 아니다. Google 정책 문의 답변 대기를 이유로 소스 구현을 중단하지 않았다.

## 변경 파일 및 보존

- backend/src/services/colab_oauth.py
- backend/src/services/colab_oauth_callback.py
- backend/src/services/colab_oauth_store.py
- backend/src/api/colab_oauth_routes.py
- backend/src/api/routes.py
- backend/src/services/official_colab_launcher.py
- backend/src/services/transcription_runner.py
- backend/tests/test_colab_oauth.py
- frontend/src/components/ColabAccountSettings.tsx
- frontend/src/api/client.ts
- frontend/src/pages/SettingsPage.tsx
- docs/COLAB_PHASE18_OAUTH.md
- docs/COLAB_PHASE18_LIVE_VALIDATION_PLAN.md
- docs/project/CURRENT_SOURCE_OF_TRUTH.md (신규 문서 분류 2행)
- audit/252-colab-oauth-phase18-20261114.md

기존 monitor.ps1, smoke.ps1, smoke_desktop.ps1, smoke_qa.ps1, tunnel_log 5개는 수정·실행·스테이징하지 않았고 기존 기준 해시와 동일하다. main/Integration 변경·병합, 기존 Draft PR 병합, 실제 사용자 데이터 변경은 수행하지 않는다.

GitHub 기록 후 PHASE 18 STOP.
