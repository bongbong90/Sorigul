# [SORIGUL] PHASE 18 — 공식 Colab 전용 계정 연결

Issue #252 / 부모 PR #251 / 부모 HEAD `f3c5fdbc6495beafc25c6bfa9788203ce69d5a74`. 이 문서는 PHASE 18의 구현·Mock 검증 범위를 기록한다. 실제 계정 연결과 Colab 이용 승인을 입증하지 않는다.

## 제품 흐름

설정의 **공식 Google Colab 계정** 카드에서 `Google Colab 연결` 또는 `다시 인증`을 누르면 Windows 기본 브라우저를 연다. 인증 결과는 임시 `127.0.0.1:<동적 포트>/oauth/colab/callback`에서만 수신한다. 브라우저에는 소리글에서 연결 결과를 확인하라는 문구를 표시하며, 사용자는 코드를 복사·입력하지 않는다. 미완료 인증은 300초 후 종료되고 `인증 취소`로 중단할 수 있다. 재시도는 새로운 state·nonce·PKCE verifier를 사용한다.

연결 안 됨 / 인증 진행 중 / 연결됨 / 권한 부족 / 인증 갱신 필요 / 계정 확인 실패를 표시한다. **실행 조건 미확인**과 전사 차단 사유는 계정 상태와 별도 표시한다. 계정·이메일·sub·token·클라이언트 ID·인증 URL은 상태/Job/일반 Settings에 표시하거나 저장하지 않는다. 인증 URL은 브라우저 handoff 응답과 브라우저에만 전달한다.

`연결 상태 확인`은 명시적으로 Google 계정 및 읽기 전용 Colab 사전 검증을 수행한다. 화면의 자동 상태 polling은 로컬 상태만 조회한다. `연결 해제`는 별도 Colab 프로젝트의 refresh token을 Google에서 철회한 다음 로컬 비밀 저장소를 삭제한다. 철회 실패 시 저장소를 보존하고 재시도를 안내한다. 미정리 Runtime 또는 진행 중인 공식 Colab Job이 있으면 계정 교체·연결 해제를 차단하며 Runtime을 임의 삭제하지 않는다.

## OAuth 및 신뢰 경로

Authorization Code + S256 PKCE와 랜덤 state/nonce를 사용한다. 콜백은 정확한 Host·IPv4 loopback peer·경로·state, 중복 query field 및 단일 code/error를 검사한다. 절대 URL·다른 Host/경로·다른 state·재사용 응답을 거부한다. 느린 로컬 요청의 read timeout은 2초, callback 로그/원격 오류 본문 출력은 차단한다. 취소되거나 오래된 인증 응답이 새 인증정보를 덮어쓰지 못하게 attempt identity와 직렬화된 인증 작업 상태를 확인한다.

고정 Google Token endpoint에 코드·원래 redirect URI·PKCE verifier를 전송한다. **실제 부여 Scope는 이 요청에 대한 TLS Token 응답의 scope 필드로만 확인**한다. callback query·요청 JSON·Settings의 Scope 선언을 신뢰하지 않는다. 정확히 `openid` 및 `https://www.googleapis.com/auth/colaboratory`만 허용하며 Drive·readonly-only·추가 권한·누락된 scope 응답은 거부한다. Google의 [Desktop OAuth 문서](https://developers.google.com/identity/protocols/oauth2/native-app)는 PKCE·loopback 및 Token 응답의 scope 검사를 설명한다.

초기 연결에는 Google 인증서로 검증한 서명된 ID Token이 필요하다. 기존 google-auth 검증기를 사용하고 인증서 요청 URL을 고정한다. audience/authorized party·issuer·만료·발급시각·nonce·sub를 확인한다. at_hash가 있으면 access token과 대조한다. 같은 access token을 기존 `GoogleAccountVerifier`의 고정 UserInfo endpoint에서 검증하고 issuer+sub fingerprint가 ID Token과 일치해야 저장한다. 공개 프로필/이메일로 계정을 대체하지 않는다. [Google OIDC 문서](https://developers.google.com/identity/openid-connect/openid-connect).

scope_evidence의 TOKEN_RESPONSE_VERIFIED는 Token 응답에서 확인했다는 뜻이다. **Runtime 생성 권한은 NOT_VERIFIED**, launch_approval은 BLOCKED다. 읽기 전용 subscription/runtimespecs 성공을 생성 권한 또는 비용 보장으로 확대하지 않는다. Google은 [runtimes.create의 Scope](https://developers.google.com/colab/api/reference/rest/v1beta/runtimes/create)에 colaboratory를 명시하지만, 실제 토큰의 생성 권한 검증은 이번에 수행하지 않았다.

## 안전한 저장·갱신·분리

Colab 전용 경로는 `%LOCALAPPDATA%\Sorigul\auth\google_colab_credentials.dpapi`다. Windows 현재 사용자 DPAPI + Colab 전용 entropy로 암호화한 뒤 사용자 전용 ACL의 파일에 원자적으로 저장한다. LOCAL_MACHINE 보호와 plaintext fallback은 없다. 다른 OS에서는 기본 비밀 저장소를 사용할 수 없으며 안전하게 실패한다. 테스트는 임시 파일과 가짜 암호화 계층 및 합성 데이터 DPAPI roundtrip을 사용한다.

저장 필드는 client/project binding, access/refresh token, 만료시각, Google 응답에서 확인한 Scope 및 계정 fingerprint다. 인증 code·state·nonce·PKCE verifier·ID Token·이메일은 지속 저장하지 않는다. encrypted file이 손상되거나 보호·ACL·저장에 실패하면 연결을 활성화하지 않는다. 이 저장소는 현재 사용자 계정으로 실행되는 악성 로컬 프로세스의 접근을 방어하는 경계가 아니다. 기존 #53 로컬 프로세스 신뢰 문제는 별도다.

만료 60초 전부터 로컬 상태는 인증 갱신 필요로 표시한다. 명시적 check 또는 승인된 서버 launch의 credential 준비 경로에서만 refresh한다. Google Token 응답 Scope와 정확한 access token의 계정을 다시 확인하고, refresh 시 계정 변경은 거부한다. 새 ID Token이 있으면 그 서명·issuer·audience·만료도 확인한다. refresh 응답에서 scope가 빠지면 기존 선언을 대입하지 않고 재인증을 요구한다. 동일한 인증정보를 동시에 갱신/교체/철회하지 않는다.

Drive의 서비스·OAuth client·token 파일·Scope·rendezvous는 변경하지 않았다. Google은 token 철회가 프로젝트의 모든 Scope/client에 영향을 준다고 설명한다. 따라서 **Drive와 별도 Google Cloud 프로젝트 및 Desktop client**를 사용해야 한다. Drive의 공개 client 설정이 있으면 같은 project_id/client_id를 로컬에서 거부하며, token 파일은 읽지 않는다. 연결 해제 시에도 다시 검사한다. [Google token revocation 설명](https://developers.google.com/identity/protocols/oauth2/native-app#tokenrevoke).

## 서버 연결과 API

| API (기본 `/api` prefix) | 동작 |
| --- | --- |
| GET /colab/auth/status | 네트워크 없는 상태 조회 |
| POST /colab/auth/start | 새 설치형 인증 시작·브라우저 URL 반환 |
| POST /colab/auth/cancel | 현재 인증 취소 |
| POST /colab/auth/check | 필요 시 refresh → 계정 → 읽기 전용 기존 preflight |
| POST /colab/auth/disconnect | 미정리 소유권 확인 → Colab token 철회 → 암호화 저장소 삭제 |

POST는 빈 JSON 객체만 받으며 extra field는 거부한다. token·scope·redirect·client config·실행 승인 값을 요청으로 받지 않는다. 알려진 Desktop/dev Origin만 허용하며 외부 Origin과 단순 form POST는 거부한다. API를 통해 code를 직접 제출하는 complete endpoint는 없다.

제품 `routes.py`는 `ColabOAuthService`를 `OfficialColabLauncher`의 credential provider로 주입한다. provider의 일반 호출과 launcher status는 로컬 읽기만 한다. launch는 static gate를 먼저 검사하고, 허용된 경우에만 for_launch의 갱신/계정 확인 후 기존 preflight·RuntimeOwnership·공식 Job 엔진으로 이어진다. 제품 Resolver는 launcher를 연결한 상태에서도 명시적으로 DEFAULT OFF다. Phase 17 `ColabModelProvisioner` 승인과 launch 승인도 별개이며 이번에 부여하지 않았다.

## Google Cloud 준비 항목

1. Drive와 **별도 프로젝트**를 준비하고 Colab API의 해당 프로젝트 사용 가능 여부와 quota를 확인한다. 자동 API 활성화·결제 연결·CU 구매는 하지 않는다.
2. Google Auth Platform의 Branding, Audience, Data Access를 구성한다. 개인 시험이면 대상 계정을 test user로 제한하고, 외부 배포/Scope 심사 필요사항은 Console과 Google의 답변으로 확인한다. 현재 프로젝트/계정에서 해당 Scope 등록을 허용하는지는 실환경 NOT VERIFIED다.
3. OAuth client의 Application type을 **Desktop app**으로 만들고 Google에서 받은 installed client JSON을 `%LOCALAPPDATA%\Sorigul\auth\google_colab_oauth_client.json`에 별도로 배치한다. `installed.client_id/client_secret/project_id/auth_uri/token_uri`를 사용한다. Web/Drive client를 복사하거나 가짜 ID·Secret을 만들지 않는다. 이 파일은 Job/일반 Settings에서 설정하지 않는다.
4. 요청 Scope는 위 두 개다. UserInfo 접근이 실제 계정에서 거부되면 실패로 기록하고 Scope를 자동 확장하지 않는다. 추가 권한이 필요하면 근거·승인을 별도로 받는다. API 접근 승인과 OAuth client 발급은 무료 자원/정책 승인과 다르다.
5. 기본 브라우저와 임시 IPv4 loopback 반환을 허용하는 Windows 환경을 확인한다. Client Secret은 Desktop 앱의 서버 신뢰 근거로 사용하지 않으며 PKCE·state·서명 검증을 생략하지 않는다.

이번 작업에서는 Google Cloud 프로젝트/클라이언트를 생성·변경하거나 실제 파일을 provisioning하지 않았다. [Google OAuth 개요](https://developers.google.com/identity/protocols/oauth2), [Scope/심사 안내](https://developers.google.com/identity/protocols/oauth2/scopes).

## 남은 게이트

COST_GATE=CONDITIONAL / POLICY_GATE=NOT VERIFIED / OFFICIAL_COLAB_LAUNCH=BLOCKED / DEFAULT OFF / STUDY USE READY=NO / MAIN MERGE=HOLD 유지. 정책 문의 답변 대기로 소스 구현을 중단하지 않았으며 실환경 권한은 해제하지 않았다. 결제정보 미연결은 비용 0원·정책 적합성 증거가 아니다. 실제 OAuth·Google 계정 조회·Runtime·GPU·모델 다운로드·Drive 변경은 NOT RUN.

별도 LIVE 승인 계획: [PHASE 18 LIVE 검증 준비](COLAB_PHASE18_LIVE_VALIDATION_PLAN.md).
