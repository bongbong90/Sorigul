# #59 Stage 2A 결과 — 2026-11-07 KST

기준 #220: `64063193704ebb262a4f56db73531d9e03924e26`.
전용 브랜치: `qa/59-stage2a-local-runtime`.
제품·설치형 QA 실행 권한은 추가하지 않았다.

| 항목 | 결과 |
|---|---|
| STAGE 1.1 CONTRACT HARDENING | PASS — 7건 처리, production gate 항상 DENY |
| FILESYSTEM CONTAINMENT | PASS — 새 폐기 루트, atomic create, final handle path, junction 거부, 조상/루트 교체 거부, handle cleanup 로컬 검사 |
| PROCESS OWNERSHIP OBSERVER | NOT VERIFIED — 구현·컴파일 및 identity/accounting 모델 검사 완료; 실제 process/Job/endpoint 실행 안 함 |
| BOUNDED SUPERVISOR | NOT VERIFIED — deadline/freeze/late PASS/cleanup 지연 모델 PASS; 실제 worker 상호 장애 검증 안 함 |
| EVIDENCE BRIDGE | PASS — schema 3 검증, 합성 증거로 installed PASS 승격 불가, 미측정 null 유지 |
| SINGLE-USE EXTERNAL CONTROL | DESIGN ONLY — 외부 durable CAS/단일 dispatch/응답 Run ID 결합 미구현, 전부 DENY |
| LOCAL SYNTHETIC TESTS | 순수 계약 415 PASS, Runtime 모델+폐기 경로 131 PASS, 결함 변이 8/8 검출; 실제 합성 process/Job/endpoint SKIPPED |
| INDEPENDENT REVIEW | PASS — 독립 읽기 전용 최종 재리뷰, 잔여 blocking 0건 |
| PRODUCT SOURCE PRESERVED | PASS — QA 폴더 외 source 변경 없음 |
| USER INSTALLATION PRESERVED | PASS — 사용자 설치·AppData·Settings·Jobs·Runtime·Program Files 접근/실행/기록 없음; 사용자 파일 hash 재검사도 하지 않음 |
| ACTIONS RUNS | 0 — 이 작업의 신규 실행 수; 게시 후 원격 readback은 Draft PR 본문에 기록 |
| MSI INSTALLATIONS | 0 |
| COST | 0 KRW — 유료 리소스 사용 안 함; Private 요금/무료 잔여량은 NOT VERIFIED |

## 검증

- C# 5 production contracts / Runtime DLL / synthetic worker / test exe 컴파일 PASS.
  synthetic worker exe는 실행하지 않았다.
- PowerShell AST 오류 0, 계약 purity lint hit 0, lint 회귀 12건 PASS, QA workflow 0.
- 계약: StrictJson 22, Manifest 48, Context Gate 90, Result Schema 110,
  Synthetic Fixture 123, Acceptance Gate 22 = 415 PASS.
- Runtime: production seam 제거와 reflected constructor DENY, 결과 불변성,
  PID 재사용 모델, 누락 자손 accounting, endpoint 미소유 NV, deadline/worker
  실패/late PASS/cleanup 지연, evidence schema 검증 등 115 PASS.
  폐기용 fixture/원자적 충돌 거부/junction/rename/handle cleanup 16 PASS.
- 변이: production DENY 제거, schema 배열 변조, reparse 무시, 기존 root 채택,
  late PASS 수용, 동기 cleanup, endpoint 실패를 0으로 승격, 누락 자손 허용.
  8개 모두 실제 테스트 실패로 검출했다. 컴파일 실패를 검출 성공으로 세지 않는다.

현재 계정은 분리된 QA 계정으로 확인되지 않았다. provisioned QA SID 목록을
비워 둔 채 process/Job/endpoint 테스트는 실행하지 않았다. 파일시스템 검사만
Public profile 바로 아래 새 GUID QA 경로를 만들고 정확한 handle로 정리했다.
기존 사용자 파일을 읽거나 보호 경로의 실제 내용을 조사하지 않았다.

## 독립 리뷰

첫 리뷰의 원자적 root 생성, 임의 spec/가변 배열, 동기 cleanup 지연,
raw PID endpoint, pin 해제 후 경로 삭제 지적을 수정했다.
재리뷰의 관측 사이 종료한 자손 누락도 누적 Job accounting과 보유 identity
수의 비교로 보완했다. 최종 독립 정적 재리뷰는 PASS, 잔여 차단 0건이다.
이 결과는 native 실행 승인이나 설치형 수용을 의미하지 않는다.

## Push 전 Actions 조사

- 원격 기본 브랜치는 `main`, 확인 SHA는 `35328c7d7d90fdcf65a035666ba7fa98c54b25a7`.
  main 및 #220 기준 트리에는 `.github` workflow가 없다.
- 원격에 등록된 QA workflow 3개는 각각 #217~#219의 특정 branch/path에만
  반응한다. Stage 2A branch/path와 일치하지 않는다. workflow를 추가하지 않았다.
- 등록된 `dynamic/dependabot/update-graph`도 조사했다. 기존 실행은 main의
  Python graph update다. 이번 브랜치는 기본 브랜치가 아니며 dependency
  manifest/lock file을 변경하지 않는다. 해당 조사 범위에서 자동 실행 조건에
  해당하지 않는다고 판단했다. 저장소 보안 설정은 변경하지 않았다.
- 게시 전 전체 Actions run은 기존 4개다:
  `37582438896`, `41813116291`, `41818286766`, `41820120841`.
  게시 후 같은 집합/신규 HEAD 0건을 readback한다. 예상 밖 trigger가 보이면
  Push를 계속하지 않는다.

동적 작업 근거:
[dependency graph data](https://docs.github.com/en/code-security/concepts/supply-chain-security/dependency-graph-data),
[automatic submission triggers](https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/secure-your-dependencies/submit-dependencies-automatically).

## 보존한 PR

| PR | HEAD | 상태 |
|---|---|---|
| #216 | `890364e21a4e80d2ff5185332834b4dbb67aeb01` | Draft·미병합 |
| #217 | `94d5ec5da722c7ee0d8f917b029eba167fe34c7b` | Draft·미병합 |
| #218 | `78e755a9cec3ac82880aaa5ff75107c703429108` | Draft·미병합 |
| #219 | `0a1c98478aa8bd5ee7442615836f003ddce6bef4` | Draft·미병합 |
| #220 | `64063193704ebb262a4f56db73531d9e03924e26` | Draft·미병합 |

새 Draft PR의 base는 #220 QA branch다. 새 PR URL/HEAD와 게시 후 원격 확인은
PR 본문과 완료 응답에 기록하여 이 커밋 내부의 자기참조 SHA를 만들지 않는다.

#59 INSTALLED ACCEPTANCE = BLOCKED

#47 PASS

#48 EXTERNAL QA = BLOCKED

STUDY USE READY = NO
