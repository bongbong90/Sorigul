# [SORIGUL] PHASE 15 — #114 최종 STUDY USE 수용 증거 감사 및 GO/NO-GO

**최종 판정: NO-GO.** `STUDY USE READY = NO`, `STUDY WORKFLOW REGRESSION = NOT PASSED`, `OFFICIAL_COLAB_LAUNCH = BLOCKED`, `MAIN_MERGE = HOLD`.

이 문서는 증거 감사와 릴리스 판단만 다룬다. 소스 수정, Runtime·GPU, 모델, MP3, Drive 변경, 빌드, 설치, Freeze 변경, 병합은 하지 않았다. 판정은 2026-11-14 15:00 KST 마감 시점에 실제로 확보한 증거만으로 내렸다.

## 1. 기준 시각·소스 HEAD

조회 시각: 2026-11-14 14:34–14:45 KST (GitHub·원격 ref 읽기 전용 조회).

| 대상 | SHA / 상태 |
|---|---|
| 감사 기준 소스 HEAD | `6da8f085a5e4183798030eb52f2fa92a9ed4b3ac`. [#243](https://github.com/bongbong90/Sorigul/pull/243) OPEN / Draft / 미병합 |
| Integration `integration/study-use-final-candidate` | `58d734a64b9f8a7ec3ab4ba82970c1a821ca1158` |
| main | `35328c7d7d90fdcf65a035666ba7fa98c54b25a7` |
| #243과 Integration의 관계 | ahead 13 / behind 0. Integration이 조상 커밋이며, 13커밋 모두 Integration에 미병합 |
| 마지막 설치형 Core·Runtime 소스 | `257e61e0fddc6b1fb0f83a97f0c9fd2300c4adbf`. Integration보다 7커밋 뒤 (#216 #59 수정, #224 Colab·Drive 소스/Mock), #243보다 20커밋 뒤 |
| [#185](https://github.com/bongbong90/Sorigul/pull/185) (Integration → main) | OPEN / 미병합 |

## 2. 제품 요구사항 및 수용 기준

출처: [#114 본문](https://github.com/bongbong90/Sorigul/issues/114), [11/13 마감 재설정](https://github.com/bongbong90/Sorigul/issues/114#issuecomment-6838943421), [사용자 가용시간 정정](https://github.com/bongbong90/Sorigul/issues/114#issuecomment-6839002706).

- 목표: 설치형 Sorigul이 실제 한국어 MP3를 사용 가능한 TXT/JSON/SRT로 전사하는 것.
- 조건: Local GPU 확인, 안정적인 저장·중지·재시도·정리, 실제 사용자 데이터 보호.
- 최종 범위에는 Local 실제 학습뿐 아니라 **Colab 실제 처리와 Drive 자동 업로드·실패 복구**가 필수다 ([10/18 체크포인트](https://github.com/bongbong90/Sorigul/issues/114#issuecomment-6248989799)).
- 공식 Colab은 0원 무료 원클릭이 계약 조건이다 (#48, #60). 수동 Notebook 경로 [#225](https://github.com/bongbong90/Sorigul/pull/225)는 철회되어 DO NOT MERGE 상태다.
- `STUDY WORKFLOW REGRESSION = PASS`는 필수 비조건부 게이트가 모두 PASS일 때만 선언한다. 이후 명시적 승인이 있어야 main에 병합한다.

## 3. PHASE 01–14 완료 현황

PHASE 01–14는 모두 소스·Mock 범위다. 실제 Google 계정, Runtime, GPU, MP3는 사용하지 않았다.

| PHASE | 내용 | PR (모두 OPEN / Draft / 미병합) | 결과 기록 |
|---|---|---|---|
| 01 | 비용·정책 검토 (문서) | [#226](https://github.com/bongbong90/Sorigul/pull/226) `d961c5c`. #243 계보 밖의 독립 증거 | [c6849735550](https://github.com/bongbong90/Sorigul/issues/48#issuecomment-6849735550) |
| 02 | Runtime 수명주기 클라이언트 | [#227](https://github.com/bongbong90/Sorigul/pull/227) `66a5daa` | [c6850039118](https://github.com/bongbong90/Sorigul/issues/48#issuecomment-6850039118) |
| 03 | Jupyter 전송 | [#228](https://github.com/bongbong90/Sorigul/pull/228) `45c4503` | [c6850340146](https://github.com/bongbong90/Sorigul/issues/48#issuecomment-6850340146) |
| 04 | 소유권 영속화·복구 | [#229](https://github.com/bongbong90/Sorigul/pull/229) `17e15db` | [c6850954512](https://github.com/bongbong90/Sorigul/issues/48#issuecomment-6850954512) |
| 05 | Google 계정 검증 | [#230](https://github.com/bongbong90/Sorigul/pull/230) `85fefc7` | [c6851600096](https://github.com/bongbong90/Sorigul/issues/48#issuecomment-6851600096) |
| 06 | 오디오 chunk 전송 | [#231](https://github.com/bongbong90/Sorigul/pull/231) `16368ab` | [c6851869307](https://github.com/bongbong90/Sorigul/issues/48#issuecomment-6851869307) |
| 07 | #232 업로드 소유권 경합 수정 | [#234](https://github.com/bongbong90/Sorigul/pull/234) `6728ed4` | [c6852209484](https://github.com/bongbong90/Sorigul/issues/48#issuecomment-6852209484) |
| 08 | #233 중간 응답 처리 | [#235](https://github.com/bongbong90/Sorigul/pull/235) `cb5191e` | [c6869967085](https://github.com/bongbong90/Sorigul/issues/48#issuecomment-6869967085) |
| 09 | large-v3 단일 chunk 추론 어댑터 | [#236](https://github.com/bongbong90/Sorigul/pull/236) `b1929c8` | [c6870230626](https://github.com/bongbong90/Sorigul/issues/48#issuecomment-6870230626) |
| 10 | 전체 파일 다중 chunk 파이프라인 | [#237](https://github.com/bongbong90/Sorigul/pull/237) `aceecbd` | [c6870748068](https://github.com/bongbong90/Sorigul/issues/48#issuecomment-6870748068) |
| 11 | 공식 Colab Job 엔진 (DEFAULT OFF) | [#239](https://github.com/bongbong90/Sorigul/pull/239) `a4926d5` | [c6871190442](https://github.com/bongbong90/Sorigul/issues/48#issuecomment-6871190442) |
| 12 | #238 무음 Bundle 수정 | [#240](https://github.com/bongbong90/Sorigul/pull/240) `8408871` | [c6871700001](https://github.com/bongbong90/Sorigul/issues/48#issuecomment-6871700001) |
| 13 | 실행 전 사전 검증 (실행 승인 BLOCKED) | [#241](https://github.com/bongbong90/Sorigul/pull/241) `d2d80ec` | [c6871848574](https://github.com/bongbong90/Sorigul/issues/48#issuecomment-6871848574) |
| 14 | #242 상태값 근거 정정 | [#243](https://github.com/bongbong90/Sorigul/pull/243) `6da8f08` | [c6872236806](https://github.com/bongbong90/Sorigul/issues/48#issuecomment-6872236806) / 독립 검증 [c6872370858](https://github.com/bongbong90/Sorigul/issues/48#issuecomment-6872370858) |

PR 체인은 #227 → #228 → #229 → #230 → #231 → #234 → #235 → #236 → #237 → #239 → #240 → #241 → #243 순으로 쌓여 있고, 바닥 #227의 base가 Integration이다. 이 PR들에는 GitHub CI 상태가 없다 ([PHASE 14 독립 검증](https://github.com/bongbong90/Sorigul/issues/48#issuecomment-6872370858)).

## 4. 실제 설치형 수용 증거

아래는 모두 **역사적 설치본** 증거다. #243은 물론 현재 Integration `58d734a`에 대한 Freeze, Fresh Local/Core/MSI 빌드, 설치 수용 기록도 이번 감사에서 확인하지 못했다.

| Issue | 결과 | 기준 | 판정 |
|---|---|---|---|
| [#113](https://github.com/bongbong90/Sorigul/issues/113) CLOSED | [Fresh artifact·clean install·설치 수용 PASS](https://github.com/bongbong90/Sorigul/issues/113#issuecomment-6166749585). run `Sorigul_20261014_b86cb3b_862190df463f` | Integration `b86cb3b` (2026-10-14) | PASS — HISTORICAL ARTIFACT ONLY |
| [#56](https://github.com/bongbong90/Sorigul/issues/56) / [#63](https://github.com/bongbong90/Sorigul/issues/63) CLOSED | [설치형 UX·워크플로 PASS](https://github.com/bongbong90/Sorigul/issues/56#issuecomment-6167501879). #113과 같은 설치본, synthetic 음성 사용. [Explorer 창 보충 (`257e61e`)](https://github.com/bongbong90/Sorigul/issues/56#issuecomment-6543130625) | `b86cb3b` / `257e61e` | PASS — HISTORICAL ARTIFACT ONLY |
| [#59](https://github.com/bongbong90/Sorigul/issues/59) CLOSED | [Backend 수동 재시작·Tray 종료 PASS](https://github.com/bongbong90/Sorigul/issues/59#issuecomment-6739244416). Windows Server CI run 42348060046 + Windows 11 수동 실측, 575/575 복원 | 제품 #216 HEAD `890364e` | PASS — HISTORICAL ARTIFACT ONLY |

## 5. 실제 Local 전사 증거

[#47](https://github.com/bongbong90/Sorigul/issues/47)은 CLOSED이며 판정은 **PASS — HISTORICAL ARTIFACT ONLY**다.

- 실제 52:34 한국어 민법 강의를 CUDA로 전사했고, TXT/JSON/SRT 생성, 인터넷 강의 동시 시청, 정상 종료를 확인했다 ([근거](https://github.com/bongbong90/Sorigul/issues/47#issuecomment-6543374605)).
- 전체 Job은 560초, 실제 GPU 전사는 약 405초였다 ([성능 보충](https://github.com/bongbong90/Sorigul/issues/47#issuecomment-6543448128)).
- 범위는 설치된 Core·Runtime `257e61e`에 한정된다 ([종료 기록](https://github.com/bongbong90/Sorigul/issues/47#issuecomment-6704412452)).

PHASE 02–14 소스가 들어간 새 설치형에서 재실행하지는 않았다. 전사 정확도(CER)는 별도로 PASS 판정하지 않았다.

## 6. 실제 Google Drive 증거

[#48 Drive LIVE CREATE-only](https://github.com/bongbong90/Sorigul/issues/48#issuecomment-6820088998) ([수용 기록](https://github.com/bongbong90/Sorigul/issues/48#issuecomment-6820181652)): 별도 Drive OAuth로 합성 TXT/JSON/SRT Bundle 1개를 CREATE했고 기존 파일은 보호됐다. 판정은 **PASS — HISTORICAL ARTIFACT ONLY (범위 한정)**다.

- 공식 Colab 전사 결과가 Drive 자동 업로드까지 이어지는 경로는 **NOT RUN**이다.
- 실제 MP3 전사 결과의 자동 업로드는 **NOT RUN**이다.
- Drive update·실패 격리의 LIVE 검증은 **NOT VERIFIED**다.

## 7. 공식 Colab 실사용 차단 조건

과거 실측 (2026-11-12, 사용자 승인 범위):
- readonly OAuth로 FREE와 T4 STANDARD eligible을 확인했다 ([c6821595053](https://github.com/bongbong90/Sorigul/issues/48#issuecomment-6821595053)).
- T4 Runtime create→Jupyter WS→execute→delete를 2회 실행했고 잔류 Runtime은 0개였다 ([1차](https://github.com/bongbong90/Sorigul/issues/48#issuecomment-6821916734), [2차](https://github.com/bongbong90/Sorigul/issues/48#issuecomment-6822040442)).

이 실측은 기술 채널 검증일 뿐 제품 전사 PASS가 아니다.

| 차단 조건 | 상태 | 근거 |
|---|---|---|
| 무료 이용 정책 적합성 | **NOT VERIFIED** | [#60](https://github.com/bongbong90/Sorigul/issues/60), PHASE 01 [#226](https://github.com/bongbong90/Sorigul/pull/226). Google 문의 미발송 |
| 유료 CU 비소비 보호 | **CONDITIONAL** (지원 공개 API 없음) | PHASE 01 G5/G7/G14, PHASE 13 `NO_SUPPORTED_API` |
| 실제 OAuth Scope·계정 검증 | **NOT VERIFIED** | PHASE 13/14 사전 검증은 Mock만. `launch_scope`는 원리상 VERIFIED가 될 수 없음 (#242) |
| 실제 Runtime·GPU·large-v3 준비 | **NOT RUN** | T4 장치 식별과 모델 다운로드 실측 없음 |
| 실제 MP3 업로드·추론·결과 회수 | **NOT RUN** | |
| #233 실환경 Contents 호환성 | **NOT VERIFIED** | [#233](https://github.com/bongbong90/Sorigul/issues/233) OPEN, Mock 수정만 #235 |
| 커널 생성 응답 유실·비정상 종료 후 복구 | **NOT VERIFIED** | Mock 복구만 있음 (PHASE 04/08) |
| 사전 검증 `launch_approval` | **BLOCKED** | COST/POLICY Gate에 VERIFIED 값 없음 |

공식 Colab 실사용 판정은 **BLOCKED**로 유지한다. `official_colab`는 DEFAULT OFF다.

## 8. Issue별 잔여 작업

| Issue | 상태 | 잔여 |
|---|---|---|
| [#114](https://github.com/bongbong90/Sorigul/issues/114) | OPEN | 최신 HEAD 설치형 전체 워크플로 회귀 NOT RUN |
| [#48](https://github.com/bongbong90/Sorigul/issues/48) | OPEN | 공식 Colab 원클릭 LIVE BLOCKED |
| [#60](https://github.com/bongbong90/Sorigul/issues/60) | OPEN | 정책·0원 조건 확인 |
| [#232](https://github.com/bongbong90/Sorigul/issues/232) | OPEN | 소스/Mock 수정 #234 미병합 |
| [#233](https://github.com/bongbong90/Sorigul/issues/233) | OPEN | 실환경 Contents·첫 PUT 소유권 모호성 |
| [#238](https://github.com/bongbong90/Sorigul/issues/238) | OPEN | 소스/Mock 수정 #240 미병합 |
| [#242](https://github.com/bongbong90/Sorigul/issues/242) | OPEN | 소스/Mock 수정 #243 미병합 (기본 브랜치 대상이 아니라 자동 종료 안 됨) |
| [#7](https://github.com/bongbong90/Sorigul/issues/7) | OPEN | 추적 원장 |

## 9. GitHub PR·Integration·main 관계

- main `35328c7` ← [#185](https://github.com/bongbong90/Sorigul/pull/185) (OPEN, 미병합) ← Integration `58d734a`.
- 공식 Colab 체인: Integration ← #227 … #243. Draft 13개, `6da8f08`까지 13커밋. Integration과 main에 병합됐다는 근거는 없다.
- Integration 대상 별도 Draft (병합 금지·보류):
  - #226 PHASE 01 정책 검토
  - #225 수동 Notebook (DO NOT MERGE)
  - #214, #211 Observer
  - #204 감사
  - #217–#221 #59 QA 체인
- **MERGE 판정: BLOCKED.** #185는 #114 PASS와 명시적 main 병합 승인이 있어야 병합할 수 있으며, 두 조건 모두 미충족이다. Draft 체인을 Integration에 편입하려면 별도 리뷰와 승인이 필요하다.

## 10. 테스트 PASS / NOT RUN 구분

| 범위 | 결과 | 판정 |
|---|---|---|
| PHASE 02–14 개발 시 집중·회귀 Mock | 각 PHASE 결과 기록 참조 (PHASE 14: 80 / 384 PASS) | PASS — MOCK ONLY (개발 에이전트 보고) |
| **본 감사 중 exact HEAD `6da8f08` 재실행:** `tests/test_colab_*.py` 11개 파일 + `test_official_colab_job_adapter.py` + `test_48_drive_colab_integration.py` (외부 네트워크 차단·Mock) | **693 passed**, 1 warning (starlette deprecation) | PASS — EXACT HEAD (MOCK ONLY) |
| backend 전체·frontend·Rust·PS5 packaging 테스트 at `6da8f08` | 실행 안 함 | NOT RUN |
| GitHub CI at #243 | 상태 없음 | NOT RUN |
| canonical Preflight / Freeze / Fresh Local·Core·MSI / 보호 데이터 비교 / 설치 수용 at `6da8f08` | 실행 안 함 (금지 범위) | NOT RUN |
| 실제 Colab Runtime·GPU·large-v3·MP3 | 실행 안 함 (금지 범위) | NOT RUN |

## 11. 사용자 데이터 보존 및 금지 작업 준수

- 미추적 사용자 파일 5개의 SHA256이 착수 시점과 일치한다. 읽기·수정·Stage 없음.
  - `monitor.ps1` `f84d9bbf…0d5`
  - `smoke.ps1` `8e51c668…b97`
  - `smoke_desktop.ps1` `9f374df6…7e1`
  - `smoke_qa.ps1` `41a5ef66…cb7`
  - `tunnel_log` `e3b0c442…855` (빈 파일)
- 이번 감사에서 수행하지 않은 작업:
  - Google 계정 접근·동의, Runtime·GPU 생성·종료, 모델 다운로드, MP3 업로드
  - Drive 변경, canonical Artifact Session, Core/MSI 빌드, 설치·제거
  - Windows 종료·재부팅, Freeze 변경, 소스 수정
  - 병합, rebase, force-push, reset, clean
- 원본 MP3, 인증정보, 기존 설치본, 모델 캐시에는 접근하지 않았다.

## 12. 최종 GO/NO-GO

| 수용 영역 | 판정 |
|---|---|
| SOURCE | PASS — EXACT HEAD (`6da8f08` 소스·이력 검토. 보호 기능 Local·Drive·Output Writer·Scanner·Job Manager는 PHASE 13/14에서 무변경, `official_colab` DEFAULT OFF). 단 Integration 미편입 |
| MOCK | PASS — MOCK ONLY (Colab·Drive 693 exact HEAD 재실행. 전체 suite는 NOT RUN) |
| LOCAL LIVE | PASS — HISTORICAL ARTIFACT ONLY (#47, `257e61e`) |
| INSTALLED | PASS — HISTORICAL ARTIFACT ONLY (#113·#56·#63 `b86cb3b`/`257e61e`, #59 `890364e`) |
| DRIVE LIVE | PASS — HISTORICAL ARTIFACT ONLY (합성 Bundle CREATE-only, 자동 업로드 경로 NOT RUN) |
| COLAB LIVE | **BLOCKED** (실제 T4·large-v3·MP3 전사 NOT RUN) |
| ZERO COST | **BLOCKED** (COST_GATE CONDITIONAL, POLICY_GATE NOT VERIFIED) |
| RECOVERY | **NOT VERIFIED** (Local STOP/CANCEL/CRASHED와 #59는 역사적 PASS. 공식 Colab의 FAILED/CRASHED/소유권 불명 복구는 Mock만) |
| RELEASE | **NOT RUN** (exact HEAD의 Freeze·Core·MSI·설치 검증 없음) |
| MERGE | **BLOCKED** (#185 HOLD, Draft 체인 미병합) |

**판정 규칙 적용:** 다음 GO 필수 조건이 BLOCKED 또는 NOT RUN이다.

- 외부 정책·비용
- 공식 Colab 실사용
- 실제 인증·실행·정리
- 최신 HEAD 설치형
- #114 전체 회귀
- 명시적 main 병합 승인

따라서 결과는 다음과 같다.

- `STUDY USE READY = NO`
- `STUDY WORKFLOW REGRESSION = NOT PASSED`
- `OFFICIAL_COLAB_LAUNCH = BLOCKED`
- `MAIN_MERGE = HOLD`

Local 기능의 사용 가능성과 전체 제품 수용은 구분해야 한다. 역사적 설치본 `257e61e`의 Local CUDA 전사는 #47 범위에서 입증됐다. 그러나 공식 Colab과 Drive 자동 업로드를 포함한 전체 제품 수용은 NO-GO다. 사용자 승인만으로 정책 확인이나 무과금 보장을 PASS로 바꾸지 않는다.

## 13. 후속 재개 조건

GO 재심사에는 아래 증거가 모두 필요하다.

1. Google의 무료 정책 적합성 확인 (사용자 승인 후 문의).
2. 유료 CU 비소비를 보장하는 지원 근거.
3. 별도 승인 하의 실계정 `openid`+`colaboratory` 사전 검증 실측과 실제 T4·large-v3 단·장시간 MP3 전사·회수·정리. #233 실환경 Contents 호환성과 비정상 종료 복구 실측도 포함한다.
4. Draft 체인(#227–#243) 리뷰·Integration 편입 승인. 이후 그 exact HEAD에서 canonical Preflight → Freeze → Fresh Local/Core/MSI → 보호 데이터 비교 → 설치 수용.
5. 그 설치본에서 #114 전체 워크플로 회귀 PASS. 범위는 Local·Colab·Drive 자동 업로드·Stop/Retry/Restore·Tray·Unicode·정리.
6. 명시적 main 병합 승인.

**PHASE 15 종료 후 STOP.**
