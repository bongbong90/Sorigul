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
