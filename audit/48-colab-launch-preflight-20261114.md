# [SORIGUL] PHASE 13 — 공식 Colab 실행 전 사전 검증 게이트

- 작성: 2026-11-14 KST. 범위: 읽기 전용 사전 검증 모듈·Mock 테스트·본 보고서.
- 부모: PR #240 (OPEN / Draft / 미병합) HEAD `8408871ebc786af62901e91339f8a83b56858c2a`.
- 브랜치: `feature/48-colab-launch-preflight`. 관련 Issue: #48, #60, #7. 잔여 기술 Issue: #233.
- **사전 검증 구현 완료 ≠ 실제 Colab 실행 승인.** 실제 Google 계정·Runtime·GPU·MP3 전송·모델 다운로드·Google 문의: **NOT RUN**.

## 1. 판정 요약

| 항목 | 판정 | 근거 |
|---|---|---|
| 기존 인증 계약 | 소스 검토 완료 | §2 |
| UserInfo Scope 호환성 | **NOT VERIFIED (실계정)** / Mock PASS | 현재 Colab 전용 Token의 `openid` 포함 여부 미확인. 모듈은 선언 Scope 부족·401·403 `insufficient_scope`를 구분 |
| Colab REST 접근 | Mock PASS / 실제 **NOT RUN (이번)** | 과거 실측(11/12 readonly)은 §4 |
| FREE 구독·T4 eligible | 과거 실측 FREE / T4 STANDARD eligible, **현재 실측 NOT RUN** | 과거 결과는 이후 실행의 영구 증거가 아님 |
| CU 비소비 보호 | **CONDITIONAL** | 지원 공개 API 없음 → `paid_cu_non_consumption_evidence = NO_SUPPORTED_API` |
| 무료 이용 정책 | **NOT VERIFIED** | Google 확인 없음, 이번에도 문의 미발송 |
| 실제 모델 준비 | **NOT RUN** | |
| 실제 Colab 전사 | **NOT RUN** | |
| 제품 실행 승인 | **BLOCKED** | COST/POLICY 미확정. 코드상 두 Gate에 VERIFIED 값이 없어 GO 도달 불가 |

## 2. 기존 검증 계약 확인 (TASK 13-A)

| 소스 | 확인 내용 | 사전 검증에서의 재사용 |
|---|---|---|
| `colab_account_verifier.py` | 고정 UserInfo endpoint, TLS·무프록시·무리다이렉트, `sub` → sha256(issuer+sub) fingerprint만 반환, 실패는 모두 `None`으로 통합 | 그대로 사용. 실패 원인 구분은 verifier 앞단의 관측 opener가 HTTP 상태·`WWW-Authenticate`만 분류(본문·PII 미보관) |
| `colab_runtime_client.py` | `get_subscription`, `list_runtime_specs`, `check_t4_eligibility`, 오류 분류(`_classify`), POST 1회 제한 | 분류된 GET 경로(`_request`)와 `list_runtime_specs` 재사용. `create_runtime` 등 수명주기 메서드는 호출하지 않음 |
| `colab_runtime_ownership.py` | 검증된 account binding 없이는 모든 원격 작업 차단, POST 전 내구 기록 | 사전 검증은 저장소를 만들지 않고 필요 조건(`OWNERSHIP_REQUIREMENTS`)과 binding 가용성만 판정 |
| `colab_full_file_pipeline.py` | 실행 중 `get_subscription()` 재확인, "FREE is not proof of zero paid-CU usage" | 동일 원칙 유지. 미연결 |
| `transcription_runner.py` | `official_colab_enabled=False` 기본값, RuntimeOwnership 주입 필수 | 변경 없음. DEFAULT OFF 유지 |
| PHASE 01 검토 (`audit/48-colab-gate-20261113` 브랜치, commit `d961c5c`) | COST CONDITIONAL / POLICY NOT VERIFIED / 개발 CONDITIONAL | 두 Gate를 모듈 상수로 고정 |

PHASE 01 문서는 부모 #240 체인에 포함되어 있지 않아 원 브랜치 commit에서 읽었다. 이번 단계에서 공식 문서를 새로 조회하지 않았으며, PHASE 01(2026-11-13) 출처 G1–G14 이후 **새로 확인된 공식 내용 없음**. Scope 부족 판정의 HTTP 신호는 RFC 6750 §3.1(`error="insufficient_scope"`)과 Google ErrorInfo reason `ACCESS_TOKEN_SCOPE_INSUFFICIENT`에 근거한 매핑이며, 실제 Google 응답 형태는 **NOT VERIFIED**.

## 3. 모듈 설계 (TASK 13-B/C)

파일: `backend/src/services/colab_launch_preflight.py` — `run_launch_preflight(access_token, *, network_approved, expected_account_binding=None, granted_scopes=None, ...)`.

순서와 fail-closed 규칙:

1. `network_approved is True`가 아니면 원격 요청 0회, `NETWORK_NOT_APPROVED`.
2. Token 형식 오류 → 요청 0회 `AUTH_EXPIRED`. 잘못된 기대 binding → 요청 0회.
3. 선언 Scope(`granted_scopes`)는 **하향만** 가능: Drive scope 포함 시 `DRIVE_TOKEN_REFUSED`(Drive Token 재사용 차단), `openid` 없음 → 신원 `AUTH_SCOPE_REQUIRED`, Colab scope 없음 → `AUTH_SCOPE_REQUIRED`. 선언값을 권한 증거로 쓰지 않는다.
4. 신원: GoogleAccountVerifier → `VERIFIED` / `AUTH_EXPIRED`(401) / `AUTH_SCOPE_REQUIRED`(insufficient_scope) / `ACCESS_DENIED`(403) / `NETWORK_ERROR` / `RESPONSE_INVALID` / `ACCOUNT_MISMATCH`. 만료·불일치·네트워크 오류면 Colab 조회 없이 중단(다른 계정의 Colab 데이터를 읽지 않음).
5. `GET /v1beta/subscription` → `COLAB_ACCESS_VERIFIED`, 등급 `FREE` / `PAID`(PRO·PRO_PLUS) / `UNKNOWN`. FREE가 아니면 spec 조회 생략.
6. `GET /v1beta/runtimespecs` → T4 STANDARD `ELIGIBLE` / `NOT_ELIGIBLE`(없음·false) / `UNKNOWN`(중복·타입 오류·조회 실패).
7. 생성용 `colaboratory` 전체 scope 미확인 → `LAUNCH_SCOPE_*` (readonly만으로는 이후 create 불가).
8. `COST_GATE_CONDITIONAL`, `POLICY_GATE_NOT_VERIFIED`는 상수. 실행 승인 = 기술 차단 사유와 두 Gate 사유가 모두 없을 때만 GO → 현재 항상 **BLOCKED**.

보안 경계: 읽기 전용 guard transport가 위 2개 GET 외 모든 method/host/path/query를 네트워크 도달 전에 거부(Runtime POST/DELETE, kernel, Jupyter contents, `/tun/m/ccu-info` 포함). UserInfo opener도 고정 URL·GET만 허용. 로깅 없음. 결과는 enum·카운트만 보관하며 `to_safe_dict()`에는 binding도 포함하지 않는다. 예외 chaining 없음.

결과는 지시서 라벨(`IDENTITY_VERIFIED`, `AUTH_SCOPE_REQUIRED`, `COLAB_ACCESS_VERIFIED`, `FREE_TIER_VERIFIED`, `T4_ELIGIBLE`, `TECHNICAL_PRECHECK_BLOCKED`, `COST_GATE_CONDITIONAL`, `POLICY_GATE_NOT_VERIFIED`)의 해당 부분집합을 `labels`로 제공하고, 최종 `launch_approval`을 별도 필드로 둔다.

## 4. 과거 실측과 현재 실측 구분

| 항목 | 과거 (재실행 안 함) | PHASE 13 |
|---|---|---|
| readonly OAuth, FREE, T4 STANDARD eligible | PASS — [#48 readonly 2차](https://github.com/bongbong90/Sorigul/issues/48#issuecomment-6821595053) | NOT RUN |
| T4 create/delete 2회, 0 CU UI 확인 | PASS — [#48 2차 Probe](https://github.com/bongbong90/Sorigul/issues/48#issuecomment-6822040442) | NOT RUN |
| UserInfo + Colab scope 동시 Token | 미검증 | NOT RUN |

## 5. 테스트 (TASK 13-D)

외부 네트워크 차단(socket monkeypatch) 상태에서 실행.

| 명령 | 결과 |
|---|---|
| `pytest tests/test_colab_launch_preflight.py` | **53 passed** |
| 위 + `test_colab_account_verifier.py`, `test_colab_runtime_client.py`, `test_colab_runtime_ownership.py`, `test_colab_full_file_pipeline.py`, `test_official_colab_job_adapter.py`, `test_colab_engine.py` | **357 passed**, 1 warning(기존 starlette deprecation) |

지시서 검증 범위 1–14 대응: 동일 계정·정상 Scope(1), 선언/원격 Scope 부족(2), 401 만료(3), 다른 계정(4), FREE(5), PRO/PRO_PLUS(6), T4 eligible(7), T4 false·누락·중복·타입 오류·조회 실패(8), DNS·연결·timeout(9), 비JSON·잘못된 name·UNSPECIFIED tier·500·손상 UserInfo(10), 전 항목 PASS 시에도 BLOCKED(11), guard의 POST/DELETE/기타 GET 거부 및 수명주기 메서드 미호출(12), Jupyter·업로드·모델·GPU 의존성 부재(13), repr·dict·로그에 Token·sub·email·binding 미노출(14).

## 6. 변경 범위

- 신규: `backend/src/services/colab_launch_preflight.py`, `backend/tests/test_colab_launch_preflight.py`, 본 보고서.
- 기존 소스 수정 없음. Job/Runtime 실행 경로·Desktop UI 미연결. `official_colab` DEFAULT OFF 유지. Local Whisper·DirectColab·Drive·Output Writer·Scanner·Job Manager 무변경.
- 새로운 독립 결함: 발견 없음.

## 7. 남은 실사용 차단 조건

1. POLICY_GATE: Google의 무료 정책 적용 확인 (문의는 별도 사용자 승인 필요, 이번 미발송).
2. COST_GATE: 유료 CU 비소비를 증명·강제하는 지원 API 또는 공식 확인 부재.
3. 실계정에서 `openid` + `colaboratory` 동시 동의 Token으로 사전 검증 실측 (별도 승인 필요).
4. 실제 T4 장치 식별·large-v3 준비·장시간 전사·정리 LIVE 검증.
5. #233 Jupyter Contents 중간 모델 신뢰 문제.
6. 사전 검증을 Job/UI에 연결하는 작업 (별도 단계).

**PHASE 13 종료 후 STOP.**

---

## 8. PHASE 14 정정 — 상태값 근거 정확성 (#242, 2026-11-14 KST)

위 §1–§7은 PHASE 13 원 기록으로 보존한다. 독립 리뷰 [#242](https://github.com/bongbong90/Sorigul/issues/242)가 지적한 두 필드가 실제 근거보다 확정적이었다. PHASE 13 결과 중 다음 두 판정은 **정정**한다.

- 생성 Scope: 선언된 `colaboratory` Scope만으로 `launch_scope=VERIFIED`가 될 수 있었다.
- 소유권: UserInfo 성공만으로 `ownership_preconditions=VERIFIED`가 될 수 있었다.

`launch_approval`은 당시에도 무조건 BLOCKED였다. 모듈도 Job/Runtime/UI에 연결되지 않았으므로, 실제 무승인 실행 경로는 없었다. 이것은 향후 연결 시 상태값을 오해할 위험을 정정하는 것이다.

### 8.1 Scope 선언과 실제 검증의 차이

| 구분 | 의미 | PHASE 14 상태값 |
|---|---|---|
| 선언 Scope (`granted_scopes`) | 호출자가 전달한 목록. 모듈은 이 목록이 현재 Access Token에 실제로 묶여 있는지 확인하지 않는다 | `declared_launch_scope`: 전체 `colaboratory` 포함 → `DECLARED_ONLY`, 부족 → `AUTH_SCOPE_REQUIRED`, 미제공 → `NOT_VERIFIED` |
| 실제 생성 권한 | `runtimes.create`에는 전체 `colaboratory` Scope가 필요하다. 허용된 읽기 전용 GET 두 개(subscription·runtimespecs)는 readonly Scope로도 성공하므로 생성 권한을 증명하지 못한다 | `launch_scope`: 선언 부족 시 `AUTH_SCOPE_REQUIRED`, 그 외 항상 `NOT_VERIFIED`. **VERIFIED 경로 없음** |
| Colab 읽기 접근 | 실제 Google API 200 응답으로 확인한 읽기 권한 | `colab_access=VERIFIED`는 읽기 접근만 의미하고 생성 권한으로 확대하지 않는다 |

선언 Scope는 실행을 배제하는 데만 쓰고, 승격하는 데는 쓰지 않는다. 새 인증·동의 기능은 구현하지 않았다.

### 8.2 계정 확인과 Runtime 소유권 확인의 차이

| 구분 | 사전 검증에서의 확인 여부 | 상태값 |
|---|---|---|
| Google 계정 신원 (UserInfo issuer+sub fingerprint) | 확인한다 (Mock) | `identity` (기존과 동일) |
| Runtime 생성 전 요구조건 (`OWNERSHIP_REQUIREMENTS`) | 목록만 제시. 생성 Scope·내구 기록을 확인하지 않음 | `create_preconditions=NOT_VERIFIED` |
| 실제 내구 소유권 기록 | OwnershipStore를 열지 않음 | `durable_ownership_record=NOT_CHECKED` |
| 현재 Runtime 소유권 | Runtime 조회 금지 범위 | `runtime_ownership=NOT_CHECKED` |
| 실행 Lease | 확보·조회하지 않음 | `execution_lease=NOT_CHECKED` |

계정 fingerprint는 소유권의 필요조건일 뿐 충분조건이 아니다. 위 네 필드는 생성자 인자가 아니어서(`init=False`) 외부에서 VERIFIED로 주입할 수 없다. 각각 `launch_blocking_reasons`에 차단 사유로 들어간다. `RuntimeOwnership`/`OwnershipStore`의 기록 형식과 동작은 변경하지 않았다.

### 8.3 변경된 상태값 요약

| PHASE 13 | PHASE 14 |
|---|---|
| `launch_scope`: VERIFIED / AUTH_SCOPE_REQUIRED / NOT_VERIFIED | `declared_launch_scope`: DECLARED_ONLY / AUTH_SCOPE_REQUIRED / NOT_VERIFIED, `launch_scope`: AUTH_SCOPE_REQUIRED / NOT_VERIFIED |
| `ownership_preconditions`: VERIFIED / NOT_VERIFIED | 필드 제거. `create_preconditions=NOT_VERIFIED`, `durable_ownership_record`·`runtime_ownership`·`execution_lease=NOT_CHECKED` |
| 정상 Mock 시 `technical_blocking_reasons=()` | 항상 `LAUNCH_SCOPE_NOT_VERIFIED` 이상. 라벨에 `TECHNICAL_PRECHECK_BLOCKED` 포함 |
| `launch_blocking_reasons` = COST + POLICY | 기술 사유 + `CREATE_PRECONDITIONS_NOT_VERIFIED`, `DURABLE_OWNERSHIP_RECORD_NOT_CHECKED`, `RUNTIME_OWNERSHIP_NOT_CHECKED`, `EXECUTION_LEASE_NOT_CHECKED` + COST + POLICY |

`OWNERSHIP_VERIFIED` 같은 확정 상태는 사용하지 않는다.

### 8.4 미검증 실계정 범위

실제 Google 계정 테스트는 이번에도 **NOT RUN**이다. 다음 항목을 실측하지 않았다.

- 실계정 Token의 실제 Scope 구성 (`openid`·`colaboratory` 동시 동의 여부)
- Google의 실제 401/403 `insufficient_scope` 응답 형태
- 생성 권한 (POST 금지 범위라 사전 검증으로는 확인 불가)
- 소유권 기록·Lease와의 연동

### 8.5 COST/POLICY BLOCKED 유지 근거

다음 근거는 PHASE 13과 같고, 이번에 바뀐 것은 없다.

- 유료 CU 비소비를 확인하는 지원 공개 API가 없다 (PHASE 01 G5/G7/G14).
- Google의 무료 정책 적용 확인이 없다 (문의 미발송).
- `CostGate`·`PolicyGate`에 VERIFIED 멤버가 없고 `_VERIFIED_*_GATES`가 비어 있다.

이번 정정은 차단 사유를 늘리기만 했으므로 GO 경로는 새로 생기지 않았다. 다음 안전장치도 그대로다.

- DEFAULT OFF
- `network_approved` 없이 요청 0회
- UserInfo + 허용된 GET 두 개 외 요청 차단
- Drive Token 거부

### 8.6 테스트

외부 소켓을 차단한 상태에서 실행했다.

| 명령 | 결과 |
|---|---|
| `pytest tests/test_colab_launch_preflight.py` | **80 passed** (PHASE 13 53 + PHASE 14 27) |
| 위 + verifier / RuntimeClient / ownership / full-file pipeline / job adapter / engine | **384 passed**, 1 warning (기존 starlette deprecation) |

PHASE 14에서 추가한 시나리오:

- 임의 선언한 전체 Scope로는 생성 권한이 VERIFIED가 되지 않음
- readonly Scope만 있으면 차단
- UserInfo 성공이 소유권 VERIFIED를 뜻하지 않음
- 소유권 필드를 생성자로 주입할 수 없음
- OwnershipStore·RuntimeOwnership 생성 0회
- 8개 시나리오 모두 GO·VERIFIED 생성/소유권 상태 없음
- Scope 부족·만료·계정 불일치 회귀
- POST·DELETE·커널·Contents 요청의 네트워크 도달 0회
- 새 필드에 민감정보 미노출

**PHASE 14 종료 후 STOP.**
