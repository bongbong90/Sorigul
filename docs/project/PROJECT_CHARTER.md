# Sorigul Project Charter

## 프로젝트 목적

소리글(Sorigul)은 Windows에서 실제 개인 학습에 사용할 수 있는 음성 전사 및 결과 관리 데스크톱 애플리케이션이다. 사용자가 음성 파일을 안전하게 전사하고 진행 상태, 결과, 재시도와 복구를 명확하게 관리할 수 있어야 한다.

목표는 public release가 아니라 **2026-10-31 KST까지 `STUDY USE READY = YES`**를 달성하는 것이다.

## 제품 원칙

- Legacy ACTIVE 사용자 기능과 functional behavior는 기본적으로 보존한다.
- Legacy와 다른 동작은 사용자 승인 `Intentional Change`로 명시된 경우에만 허용한다.
- 기능은 계승하되 architecture는 greenfield로 구현한다. Legacy 소스 Copy/Import는 금지한다.
- 현재 Sorigul 구현 자체는 의도된 제품 행동의 증거가 아니다.
- Core는 lightweight하게 유지하고 OpenAI Whisper, torch, CUDA payload는 별도 versioned Local Runtime에 둔다.
- Local, Colab, Drive를 포함한 모든 지원 경로는 zero-cost 계약을 지킨다. paid fallback은 허용하지 않는다.
- 사용자 데이터, 기존 정상 결과와 완료된 작업을 보존하며 실패를 격리한다.
- 사용자 경험을 기술 구조보다 우선하고, 내부 엔진·chunk 같은 구현 세부를 불필요하게 노출하지 않는다.
- 긴 한글 및 Unicode 경로와 파일명을 안정적으로 처리한다.

상세 제품 행동과 승인된 변경은 [`CURRENT_PRODUCT_CONTRACT.md`](CURRENT_PRODUCT_CONTRACT.md)를 따른다.

## 개발 방식

Greenfield implementation, Legacy behavioral parity.

기존 전사도우미 구현 소스는 신규 Sorigul 프로젝트의 dependency가 아니다. Legacy ACTIVE runtime과 실제 검증 evidence는 제품 parity를 판정하는 근거로 사용한다.

모든 work unit은 Issue, dedicated branch, test, commit, push, PR, Issue/#7 update, approved merge gate의 전체 Git/GitHub lifecycle을 완료한다.

## 현재 단계

**Personal Study Use Completion — Full Legacy Parity Remediation / Installed Validation**

현재는 UI foundation 단계가 아니다. canonical governance와 제품 계약을 잠근 뒤 source parity, fresh installed artifact, 실제 Local/외부 경로, recovery/shutdown, final study workflow 순으로 검증한다.

## 현재 완료 범위

- Project/Foundation, Design System, App Shell과 UI Freeze
- Core file/job workflow와 transcription/Drive/Desktop source implementation
- Core와 별도 Local Whisper Runtime의 lightweight packaging 구조
- 이전 source regression 및 installed/synthetic 검증 evidence
- full Legacy parity rebaseline과 completion plan

과거 PASS는 역사적 evidence이며, source 변경 뒤의 current-HEAD installed verdict를 대신하지 않는다.

## 남은 완료 범위

- Local OpenAI Whisper `medium`과 Colab `faster-whisper large-v3` engine parity
- notification folder-open과 live transcription-folder change parity
- 전체 source contract regression
- fresh lightweight current-HEAD build/install과 native integration
- real Local audio 및 안전하게 확인된 zero-cost Colab/Drive validation
- recovery와 승인된 shutdown 검증
- #114 final Study Workflow Regression과 bottom-up merge closeout

실행 순서와 일정은 [`SORIGUL_FULL_LEGACY_PARITY_COMPLETION_PLAN_2026-09-28.md`](SORIGUL_FULL_LEGACY_PARITY_COMPLETION_PLAN_2026-09-28.md)를 따른다.
