# [SORIGUL] PHASE 01 — Colab 비용·정책 개발 착수 검토

- 검토일: 2026-11-13 KST. 공식 문서·GitHub 확인 시점: 18시대 KST.
- 범위: TASK 01-A/B/C 조사, 문서 1개, 로컬 전용 브랜치·커밋. PHASE 02 자동 착수 금지.
- 기준 Integration: `integration/study-use-final-candidate` / `58d734a64b9f8a7ec3ab4ba82970c1a821ca1158`.
- 최종 마감: 2026-11-14 15:00 KST. 사용자 참여 가능: 11/13 19:00–20:00, 11/14 12:00–15:00.

## 1. 판정

| 항목 | 판정 | 의미 |
|---|---|---|
| COST_GATE | **CONDITIONAL** | 현재 계정의 FREE·0 CU 및 2회 할당 성공을 인정한다. 구매 없는 현금 과금 근거는 발견하지 못했다. 다만 공개 REST만으로 유료 잔액 비소비를 원자적으로 강제하는 조건은 확정되지 않았다. |
| POLICY_GATE | **NOT VERIFIED** | 공식 자동화 지원은 확인했다. FREE·0 CU의 Windows 원클릭 전사에 FAQ 제한이 어떻게 적용되는지 명시적 근거가 부족하다. |
| DEVELOPMENT_GATE | **CONDITIONAL — 구현 착수 보류** | 기술 채널은 입증됐지만 비용 보호와 실제 제품 정책 적용은 미확정이다. 기존 엄격한 사전 검증 원칙을 유지하며 GO로 해석하지 않는다. |
| PHASE 01 작업 상태 | **PARTIAL — 로컬 검토·커밋 완료 후 Push 승인 대기** | 원격 게시 수명주기는 사용자 검토·승인 후 완료한다. 제품 구현·외부 테스트는 이번 범위가 아니다. |

확인되지 않았다는 이유만으로 영구 NO-GO라고 단정하지 않는다. 반대로 공식 API·CLI 존재나 성공한 짧은 Probe를 제품 운영 정책 PASS로 확대하지 않는다. 사용자 승인도 Google 정책 확인이나 무과금 보호 증명을 대체하지 않는다.

## 2. 기준선과 GitHub 최신 상태

현재 작업지시서가 이번 범위·일정·원클릭 계약의 직접 권한이다. 저장소의 [제품 계약](../../docs/project/CURRENT_PRODUCT_CONTRACT.md), [개발 규칙](../../docs/project/DEVELOPMENT_RULES.md), [Source of Truth](../../docs/project/CURRENT_SOURCE_OF_TRUTH.md)를 읽었다. 과거 일정·수동 Notebook 지시·구현 설명은 최신 사용자 정정을 대체하지 않는다. 기존 문서는 수정하지 않는다.

| 확인 대상 | 2026-11-13 읽기 전용 조회 결과 |
|---|---|
| 로컬 시작 HEAD | `58d734a64b9f8a7ec3ab4ba82970c1a821ca1158`, detached HEAD, upstream 없음 |
| 원격 Integration | `58d734a64b9f8a7ec3ab4ba82970c1a821ca1158` — 지시서와 일치 |
| 원격 main | `35328c7d7d90fdcf65a035666ba7fa98c54b25a7` — 지시서와 일치 |
| [#48](https://github.com/bongbong90/Sorigul/issues/48), [#60](https://github.com/bongbong90/Sorigul/issues/60) | OPEN. 원클릭·0원 계약, COST/POLICY FIRST 유지. 과거 본문의 인증 미확인 설명보다 후속 실측 댓글을 우선 |
| [#114](https://github.com/bongbong90/Sorigul/issues/114) | OPEN. 최종 통합 PASS 아님 |
| [#205 최신 감사](https://github.com/bongbong90/Sorigul/issues/205#issuecomment-6838793481) | 과거 74건 중 70건 원래 stacked base에 MERGED, main 대상 4건 HOLD |
| 70건 상태 재조회 | GitHub pulls 전체 페이지에서 감사 댓글의 70개 번호 대조: 70/70 merged_at 있음, main base 0건. 원래 base 불변 여부는 기존 감사 기록을 증거로 인정 |
| [#98](https://github.com/bongbong90/Sorigul/pull/98), [#162](https://github.com/bongbong90/Sorigul/pull/162), [#163](https://github.com/bongbong90/Sorigul/pull/163), [#166](https://github.com/bongbong90/Sorigul/pull/166) | 모두 CLOSED / merged_at=null / base=main, 보류 유지 |
| [#185](https://github.com/bongbong90/Sorigul/pull/185) | OPEN / UNMERGED, Integration → main, head=`58d734a…` |
| [#225](https://github.com/bongbong90/Sorigul/pull/225) | OPEN / Draft / DO NOT MERGE, head=`41816392166598e143d522d921f36331c6963edb` |
| [#214](https://github.com/bongbong90/Sorigul/pull/214) | OPEN / Draft / UNMERGED, 변경 없음 |

루트·상위 경로 및 tracked 파일에서 추가 AGENTS.md를 발견하지 못했다. 시작 시 tracked 변경은 없었으며 다음 미추적 사용자 파일 5개는 읽거나 수정·삭제·Stage하지 않는다: `monitor.ps1`, `smoke.ps1`, `smoke_desktop.ps1`, `smoke_qa.ps1`, `tunnel_log`.

## 3. 기존 실측 — 재실행하지 않고 인정

아래는 기존 GitHub 실행 기록의 결과다. 이번 계정 상태를 새로 조회하거나 실험을 재현했다는 뜻이 아니다.

| 항목 | 기존 결과 | 증거 |
|---|---|---|
| API 활성화 / 별도 readonly OAuth | PASS, readonly 단일 scope, Token 미저장·revoke | [읽기 전용 2차](https://github.com/bongbong90/Sorigul/issues/48#issuecomment-6821595053) |
| 구독 / GPU eligibility | FREE / T4 STANDARD eligible | [동일 기록](https://github.com/bongbong90/Sorigul/issues/48#issuecomment-6821595053) |
| CU / Cloud Billing | 사용자 UI에서 0 CU, 유료 구독 없음, GCP Billing 미연결 보고. PAYG 과거 구매 이력은 화면상 확인 불가 | [UI 확인](https://github.com/bongbong90/Sorigul/issues/48#issuecomment-6821777911) |
| T4 Runtime 생성·삭제 1차 | create 성공, Jupyter HTTP 200, WS 실패, delete 성공·잔류 0 | [1차 Probe](https://github.com/bongbong90/Sorigul/issues/48#issuecomment-6821916734) |
| T4 Runtime 생성·삭제 2차 | create 성공, HTTP 200, WS 101, execute_reply=ok, kernel DELETE 204, runtime DELETE 200, 잔류 0 | [2차 Probe](https://github.com/bongbong90/Sorigul/issues/48#issuecomment-6822040442) |
| 과금 관측 | 두 Probe에서 결제·유료 표시·정책 차단 메시지 없음. 결제 원장 전체 감사와 동일하지 않음 | [2차 Probe](https://github.com/bongbong90/Sorigul/issues/48#issuecomment-6822040442) |
| Google Drive CREATE-only | LIVE PASS, 합성 TXT/JSON/SRT bundle 1개. 실제 전사 완료 자동 callback까지 PASS한 것은 아님 | [Drive LIVE](https://github.com/bongbong90/Sorigul/issues/48#issuecomment-6820088998) |
| Backend 수동 복구 #59 | PASS / Closed, #216 Integration 병합 | [#205 완료 기록](https://github.com/bongbong90/Sorigul/issues/205#issuecomment-6739256490) |

**실제 T4 장치 식별, large-v3 실제 추론, 장시간 원클릭 전사 = NOT VERIFIED. 이번 실행 = NOT RUN.** 2차의 빈 stdout을 GPU 확인 PASS로 바꾸지 않는다. 1차 WS 실패와 2차 성공 기록을 모두 보존한다.

## 4. 공식 자료 목록

아래 출처는 2026-11-13 KST에 확인했다. 문구는 별도 표시가 없으면 요약이다. 공개 문서·공개 소스만 조회했으며 사용자 Colab/Payments/Billing 상태를 새로 열지 않았다.

| ID | 공식 URL | 확인한 내용 및 한계 |
|---|---|---|
| G1 | [Colab FAQ](https://research.google.com/colaboratory/faq.html) | 무료 제공·가변 한도·무료 계정 제한. 비용·정책 적용 세부는 아래 표 |
| G2 | [Colab ToS v6](https://research.google.com/colaboratory/tos_v6.html) | 2026-08-13 개정. FAQ 준수 의무, Google 승인 접근, 계정 공유·제3자 접근 제공 제한. 직접 유료 구매는 Google Payments, One/Workspace 구매는 별도 조건 |
| G3 | [REST runtimes.create](https://developers.google.com/colab/api/reference/rest/v1beta/runtimes/create) | 2026-11-02 갱신. consumer endpoint, OAuth, UUID requestId, 요청 quota. 가격·free-only 요청 옵션 없음 |
| G4 | [REST Runtime](https://developers.google.com/colab/api/reference/rest/v1beta/runtimes) | 2026-11-03 갱신. connectionInfo와 표준 Jupyter 상호작용 명시, proxy token 갱신 방식 |
| G5 | [공개 Discovery v1beta](https://colaboratory.googleapis.com/$discovery/rest?version=v1beta) | Subscription=name/tier, Runtime=name/runtimeSpec/connectionInfo/version, RuntimeSpec=key/eligible. 비용 관련 계약 부재를 스키마로 확인 |
| G6 | [공식 MCP](https://developers.google.com/colab/api/reference/mcp) | runtime·session·코드 실행 도구 및 직접 HTTP 파일 전송 안내. 외부 애플리케이션 제어의 공식 근거 |
| G7 | [MCP get_subscription](https://developers.google.com/colab/api/reference/mcp/tools_list/get_subscription) | 2026-11-02 갱신. FREE/PRO/PRO_PLUS이며 잔액 조회 아님 |
| G8 | [Google CLI README](https://github.com/googlecolab/google-colab-cli/blob/10f442a96fd91143bcbe7675af0272cfba8f2b06/README.md) | headless 자동화·단일 실행/회수/정리, Linux/macOS 지원, Windows 미지원. usage 기능 있음 |
| G9 | [Google CLI 공식 발표](https://developers.googleblog.com/en/introducing-the-google-colab-cli/) | 2026-06-05. T4 할당·의존성 설치·스크립트 실행·산출물 회수·정리 예시. FREE·0 CU 제품 예외 조항은 아님 |
| G10 | [Google VS Code 연동](https://github.com/googlecolab/colab-vscode) | 무료 Colab compute를 VS Code Jupyter 환경에 제공. 브라우저 밖 notebook 개발 사례 |
| G11 | [Google PAYG 발표](https://blog.tensorflow.org/2022/09/colabs-pay-as-you-go-offers-more-access-to-powerful-nvidia-compute-for-machine-learning.html) | 2022-09-29 역사적 공식 설명: 구독 없이 추가 CU 구매, 소진 후 무료 제한으로 복귀. 현행 수치·가격 근거로 사용하지 않음 |
| G12 | [소비자 가격](https://colab.research.google.com/signup), [유료 이용 안내](https://colab.research.google.com/notebooks/pro.ipynb) | 공개 브라우저 조회는 Sign in만 반환. 현재 지역별 가격·팩 크기·만료기간을 독립 확인하지 못해 확정 수치를 적지 않음 |
| G13 | [Colab Enterprise 가격](https://cloud.google.com/colab/pricing) | GCP VM·디스크·가속기·관리 요금의 별도 서비스. 소비자 T4 가격표로 전용하지 않음 |
| G14 | [CLI client.py](https://github.com/googlecolab/google-colab-cli/blob/10f442a96fd91143bcbe7675af0272cfba8f2b06/src/colab_cli/client.py#L255), [consumption.py](https://github.com/googlecolab/google-colab-cli/blob/10f442a96fd91143bcbe7675af0272cfba8f2b06/src/colab_cli/consumption.py#L20) | usage가 `/tun/m/ccu-info`에서 잔액·시간당 사용률을 조회하는 공식 구현. 공개 REST v1beta와 구분 |

ToS v5는 탐색 중 읽었지만 판정 근거는 현행 v6다. 존재하지 않는 Runtime 단독 타입 URL 대신 G4, 접근 실패한 topLevel URL 대신 G5/G7로 검증했다. 인증 화면이나 접근 실패를 해당 기능의 부재로 해석하지 않는다.

## 5. TASK 01-A — 비용 게이트

| 검토 항목 | 공식 문서로 확인된 사실 | 현재 계정 기존 실측 | 기술적 추론 / 미확인 위험 | 판정 |
|---|---|---|---|---|
| 무료 REST Runtime 비용 | G1 무료 제공, G3 consumer runtime 생성·quota 문서. API별 별도 금액·무과금 보장 조항은 확인 못 함 | FREE·0 CU 조건에서 T4 할당·삭제 2회 성공 | API 가격 설명 부재 자체는 무료 보증이 아니다. 성공 결과는 무료 할당이 실제 가능했다는 근거 | CONDITIONAL |
| 0 CU에서 현금 청구 | G2 직접 유료 서비스는 구매에 따른 결제. G11 추가 CU는 선택 구매 | 결제 요청·유료 표시 없음 | 구매·구독·다른 유료 서비스 호출 없이 create만으로 현금 구매가 발생한다는 근거 없음. 위험은 낮다고 추론하나 zero-charge SLA는 아님 | CONDITIONAL |
| 유료 CU 구매·충전·차감 | G11 구독 없이 PAYG 구매 가능, 잔액 소진 후 무료 제한 복귀. G2 구독 갱신 결제 구조. 추가 구매와 구독 갱신을 구분 | UI 0 CU. 과거 구매 이력 미확인 | FREE enum은 유료 구독 없음이며 PAYG 잔액 0을 뜻하지 않는다. 보유 CU가 있으면 무료 하드웨어명만으로 비차감을 보장 못 함. 현행 소비율·만료·팩 가격은 미확정 | CONDITIONAL |
| 소비자 Colab / Cloud Billing | G2 소비자 결제 조건과 G13 Enterprise VM 과금은 별도. G3 consumer 경로에는 project/location Runtime 리소스 경로 없음 | GCP Billing 미연결 상태로 성공 | API 활성화용 Cloud 프로젝트와 소비자 CU 결제는 구분. Cloud Billing 미연결만으로 Colab PAYG 잔액 없음은 증명 불가 | CONDITIONAL |
| 공개 REST CU·가격·무료 시간 | G5/G7에서 tier·eligible만 제공. 잔액·가격·무료 잔여시간·freeOnly/maxCost 필드 없음 | readonly 응답과 부합 | eligible은 가격·가용성 보증이 아니다. API만으로 현 시점 0 CU를 증명하거나 0원 상한을 서버에 강제 못 함 | 미해결 |
| 공식 CLI CU 조회 | G8/G14에 usage와 잔액·사용률 구현 존재 | 이번 계정에서 실행하지 않음 | `/tun/m/ccu-info`는 공식 코드지만 문서화된 consumer REST/MCP 계약과 다름. Windows REST 제품의 안정적 조회 수단으로 승인·검증되지 않음 | NOT VERIFIED |
| 일/주 사용시간·초기화 | G1 한도 비공개·가변 | 짧은 Probe만 성공 | 일/주 GPU 시간, 다음 초기화 시각, 장시간 완주 확률을 계산하지 않음 | NOT VERIFIED |

**비용 결론: COST_GATE = CONDITIONAL.** 0 CU에서 성공한 기존 결과를 무시하지 않는다. 현금 과금과 이미 구매한 CU의 차감을 구분한다. 지금 구매 없이 과금된다는 증거도, 미래 계정 변화까지 API가 무과금을 강제한다는 증거도 없다. 잔액 관측이 가능해져도 관측 직후 다른 클라이언트·구독 지급으로 잔액이 바뀌는 경쟁과 server-side free-only 부재는 별도 문제다.

### 강제 가능한 보호와 아직 확정되지 않은 보호

아래는 향후 설계의 조건 목록이며 이번에 구현하거나 검증하지 않았다.

| 조건 | 강제 가능 범위 | 한계 |
|---|---|---|
| 소비자 공식 REST/Jupyter 경로만 허용, 구매·충전·구독·Cloud VM·유료 fallback 호출 배제 | 애플리케이션의 호출 경로를 제한 가능 | 계정이 외부에서 구매·부여받는 CU는 막지 못함 |
| FREE 및 T4 STANDARD eligible 확인 실패·불명·변경 시 생성 차단 | tier·spec 기반 fail-closed 가능 | FREE/eligible만으로 zero-CU·zero-cost 판정 불가 |
| 단일 사용자 직접 시작, 소유 Runtime 1개, requestId 중복 방지, 종료/취소 시 소유 자원만 정리 | 앱 실행·동시성·수명주기 제한 가능 | 비용 선택 옵션을 대체하지 않음. 네트워크 단절 시 삭제 성공 보장은 별도 검증 필요 |
| CU 0을 신뢰할 수 없거나 유료 잔액·권한이 의심되면 미실행 | 불명 상태에서 기능 차단 가능 | 현재 공개 REST로 완전 자동 검증 불가. 매 실행 수동 UI 확인을 최종 원클릭 제품 대안으로 채택하지 않음 |
| 사용자 0 CU 확인 기록 유지 | 이번 계정의 과거 증거로 인정 | 이후 실행의 영구 인증서가 아니며 새 구매·지급·계정 변경을 자동 감지하지 못함 |

따라서 안전하게 **미실행시키는 보호**는 가능하지만, 계약에 맞는 원클릭 실행을 허용하면서 **유료 CU 비소비까지 보장하는 보호**는 확정되지 않았다. CLI usage를 새 조사 단서로 보존하되 비공개 경로를 즉시 제품에 복제하지 않는다.

## 6. TASK 01-B — 무료 사용 정책

검토 시나리오: 사용자가 자신의 Windows Sorigul에서 Start를 직접 클릭 → FREE·0 CU 계정의 공식 REST로 T4 한 대 생성 → 본인 MP3를 공식 Jupyter로 전송 → faster-whisper large-v3 순차 처리 → 결과 회수 → Runtime 종료. Notebook 수동 셀·수동 업로드·ZIP Import를 요구하는 방식으로 바꾸지 않는다.

| 조건 | 공식 근거 | 해당 시나리오 판정 |
|---|---|---|
| 외부 프로그램 제어 | G3/G4/G6는 생성·표준 Jupyter·코드 실행을 문서화. G8/G9는 자동 작업·회수·정리, G10은 외부 IDE 사례 | 일반 범주 지원 확인. Sorigul 무료 운영 전체 승인은 NOT VERIFIED |
| Notebook UI 우회 | G1 무료 제한은 주로 web UI로 상호작용하는 우회에 적용 | native Windows 앱과 Jupyter 전송이 정확히 해당하는지 불명확. 모든 외부 제어 금지로 확대하거나 native라는 이유로 면제하지 않음 |
| Remote control | G1은 SSH shell·remote desktop 등을 예시로 제한 | SSH/RDP를 쓰지 않는 점은 유리하나 REST/Jupyter 자동 작업의 적용 범위는 NOT VERIFIED |
| 일회성 직접 시작 / 장시간 자동 추론 | G1 interactive 사용 우선. G8/G9는 자동 코드 작업 사례 제공 | 직접 시작·종료가 있는 개인 작업과 상시 무인 서비스는 다름. 최초 클릭만으로 실행 중 전체가 interactive로 인정된다는 보장은 없음 |
| 분산·백그라운드 | G1 무료 분산 worker 제한. G12 유료 background 설명은 현행 본문 독립 조회 제한 | 단일 소유 Runtime·순차 chunk는 분산 구성과 다르다는 추론. 단일 작업이라도 장시간 무인 실행의 무료 허용 여부는 별도 미확인 |
| 공식 proxy / 자체 tunnel | G4 runtime proxy credential은 지정된 공식 접속 수단 | 비공식 공개 FastAPI/Quick Tunnel 서비스와 구분. 공식 proxy 사용만으로 workload 정책까지 면제되지 않음 |
| 제3자 제공 | G2 계정 공유·타인에게 Colab 접근 제공 제한 | 본인 계정·본인 파일의 개인 실행을 전제로 함. 배포 제품이 제3자 접근 제공에 해당하는지 확인 필요. 중앙 Runtime 판매·공유 형태로 확장 금지 |

**정책 결론: POLICY_GATE = NOT VERIFIED.** G2가 FAQ 준수를 약관에 포함하므로 일반 기능 안내를 무료 제한의 예외로 읽지 않는다. 이 시나리오에 대한 명시적 금지 확정도 얻지 못했으므로 NO-GO를 단정하지 않는다. 자체 tunnel을 되살리거나 수동 Notebook 경로를 최종 대안으로 채택할 근거는 없다.

### Google 확인 질문 초안 — 이번에는 발송하지 않음

1. 개인 소비자 FREE·0 CU 계정에서 위 시나리오를 공식 REST/Jupyter만으로 수행하는 것이 허용되는가? 허용 근거 문서와 필요한 조건을 알려 달라.
2. native Windows 프로그램의 단일 Start와 진행률 확인이 FAQ의 notebook UI 우회·remote control 제한에 해당하는가? 공식 CLI/MCP/VS Code의 예외가 있다면 타사 앱에도 적용되는가?
3. 하나의 T4에서 300초 chunk를 순차 전사하고 결과를 받은 즉시 삭제할 때, 시작 후 수십 분 자동 추론은 interactive compute로 인정되는가? 사용자 부재·화면 닫힘·대기열 처리 경계는 무엇인가?
4. 무료 분산 worker·서비스 제공 제한과 개인 desktop client의 경계는 무엇인가? 각 사용자가 본인 OAuth로 자기 Runtime만 사용하는 앱 배포는 제3자 접근 제공에 해당하는가?
5. consumer REST create가 유료 CU를 절대 소비하지 않도록 지정하는 공식 free-only 옵션 또는 원자적 비용 상한이 있는가? FREE·0 CU에서 구매·구독 없이 현금 청구가 발생하는 경로가 있는가?
6. 공개 REST/MCP로 CU 잔액·차감률·가격을 조회하는 지원 계약이 있는가? 공식 CLI의 `/tun/m/ccu-info`를 타사 Windows OAuth client가 사용해도 되는가? 향후 CU 입금·잔액 변경 시 free-only 유지 방법은 무엇인가?

문의 발송·계정 접근은 이번 범위 밖이다. 질문 초안은 허용 답변을 받았다는 증거가 아니다.

## 7. TASK 01-C — 개발 착수와 남은 영향

| 미확인 사항 | 제품 영향 | 현 단계 조치 |
|---|---|---|
| 정확한 무료 정책 적용 | 실행 중 차단·계정 제한 가능, 최종 계약 수용 불명 | NOT VERIFIED 유지, 구현 착수 보류 |
| 자동 zero-CU 검증·free-only 강제 | 향후 보유 유료 CU 차감 가능성을 완전히 차단할 근거 없음 | CONDITIONAL 유지, 사용자 위험 수용만으로 해결 처리 금지 |
| 무료 T4 가용성 | 할당 거절·중단 가능. Start 한 번이 모든 작업 성공을 보장하지 않음 | 유료 fallback·무한 재할당·다계정 우회 금지 |
| T4 장치·large-v3·긴 처리·정리 | 기술 채널 PASS와 제품 전사 LIVE 사이 공백 | 이번 NOT RUN, 기존 PASS 확대 금지 |
| 인증·MP3 외부 전송·설치 승인 | 이후 실행은 별도 범위 지정 필요 | 이번에는 추가 조작 요구 없음 |

**DEVELOPMENT_GATE = CONDITIONAL, 실제 구현 착수 보류.** 기존 최종 계약과 엄격한 사전 검증 원칙은 그대로다. GO에 필요한 무과금 보호와 정책 조건이 모두 확정되지 않았다. 현재 자료만으로 승인된 구현 경로를 확정하지도, 영구 불가능으로 판정하지도 않는다. #48/#60/#114는 미완료이며 #185 병합 근거가 생기지 않는다.

PHASE 02에서 추천하는 최소 작업 **하나**: **사용자가 별도 승인한 경우, 위 시나리오와 6개 질문을 묶어 Google에 정책·free-only 비용 조건 확인을 1건 문의한다.** 공식 CLI 사용량 조회의 타사 지원 여부도 같은 문의에 포함한다. 답변 전에는 정책 PASS나 구현 GO로 전환하지 않는다. 이번에는 발송하지 않으며, 별도 사용자 지시 전에는 이 작업도 시작하지 않는다. 답변 도착 시점은 보장할 수 없고 11/14 마감을 이유로 미확인 조건을 완화하지 않는다.

## 8. 변경·검증·Git 정리

### 변경 범위

- 신규 파일 1개: `audit/48-colab-gate-20261113/PHASE01_COST_POLICY_REVIEW.md`.
- 전용 branch: `audit/48-colab-gate-20261113`, 기준 commit에서 생성. 시작·현재 upstream 없음.
- 기존 source·Freeze·STOP·Observer·감사 기록은 수정하지 않는다. main/Integration branch HEAD도 변경하지 않는다.
- audit 문서 commit도 작업 브랜치 HEAD는 바꾼다. 이를 기존 source/release Freeze PASS로 간주하거나 보호 기준선을 갱신하지 않는다. 향후 Integration 편입·artifact는 별도 승인과 해당 exact HEAD 규칙을 따른다.

### 검증 명령과 판정 범위

| 명령 / 확인 | 결과 |
|---|---|
| `git status --short`, `git branch --show-current`, `git rev-parse HEAD`, upstream 확인 | 시작 tracked clean, detached HEAD / upstream 없음, 기존 untracked 5개 식별 |
| `git ls-remote origin refs/heads/main refs/heads/integration/study-use-final-candidate` | 두 원격 HEAD가 위 기준과 일치 |
| `gh pr view 185/225 --json ...`, GitHub pulls 전체 페이지 상태 대조 | #185 미병합, #225 Draft/DO NOT MERGE, historical 70/70 병합·4건 보류 확인 |
| GitHub connector Issue 본문·전체 댓글 조회 | #48/#60/#114/#205 읽기 완료, 후속 실측 및 정정 기록 우선 |
| 공개 Discovery·공식 CLI 고정 SHA 소스 확인 | tier/eligible와 비용 필드 구분, usage의 별도 session backend 확인 |
| 문서 구조·증거 링크·판정 일관성 검사 | 커밋 전 필수 항목·링크·금지 범위·증거 분류 확인 |
| `git diff --check`, `git diff --cached --check`, `git diff --cached --stat` | 정확한 단일 경로 Stage 후 오류 없음 확인을 커밋 조건으로 적용 |
| production/source/mock/installer/GPU/OAuth/Drive 테스트 | **NOT RUN — docs-only, 기존 검증 반복 금지** |
| Runtime 생성·GPU 실행·MP3 전송·결제 변경·Google 문의 | **NOT RUN — 이번 범위 금지** |

### 원격 게시 승인 경계

작업지시서 §8의 **“사용자 검토 및 승인 절차를 거쳐 Push”**, **“승인 없이 Push나 Merge가 불가능하다면 로컬 Commit까지 마무리하고 필요한 승인 사항과 정확한 Diff를 보고”**에 따라 로컬 commit에서 승인 대기한다. 이는 기술적 Push 실패나 자동 승인 검토 거절이 아니다. 저장소 개발 규칙은 전체 수명주기를 요구하며, 이번 지시서가 그중 Push의 사용자 승인 순서를 정한다.

- 예정 Conventional Commit: `docs(colab): assess free-tier cost and policy gates for #48`.
- commit SHA는 자기 참조를 피하기 위해 최종 응답과 `git log -1`로 보고한다. 문서 자체에 커밋 후 SHA를 삽입하여 추가 커밋하지 않는다.
- 정확한 Diff: 기준 `58d734a…`에 이 문서 전체를 신규 추가하는 단일 파일 diff. 사용자 파일·제품 파일 포함 없음.
- Push: **NOT RUN — 사용자 검토·승인 대기**.
- PR: **NOT CREATED**. 승인 후 `integration/study-use-final-candidate` 대상 Draft, 제목 `docs(colab): assess free-tier cost and policy gates for #48`, 본문에 세 Gate·docs-only·NOT RUN·기존 증거·DO NOT MERGE 명시 예정.
- Issue #48/#60: **원격 변경 NOT RUN**. 승인 후 Draft PR URL·CONDITIONAL/NOT VERIFIED·구현 보류를 연결. 개발 규칙의 #7 Tracker 기록도 동일 범위에 포함.
- 승인 후 Push한 원격 branch SHA와 PR base/head·변경 파일 1개를 재조회해야 전체 정리 완료다. 자동 merge 없음.

**PHASE 01 종료 후 STOP. 다음 단계 구현이나 테스트는 별도 작업지시 전까지 진행하지 않는다.**
