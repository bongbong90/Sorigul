# Sorigul Current Product Contract

Status: `LOCKED`

## 1. Purpose

이 문서는 **현재 Sorigul이 실제로 따라야 하는 제품 계약의 canonical entry point**다. 구현, 검토, 테스트와 defect 판정은 이 문서에서 시작한다.

과거 문서는 삭제하거나 역사 수정하지 않는다. 그 문서들은 결정 provenance와 검증 evidence로 보존하되, 충돌하는 현재 행동은 이 문서의 evidence hierarchy와 supersession map으로 판정한다.

역할은 다음과 같이 분리한다.

- 이 문서: 현재 무엇이 제품 계약인가.
- [`SORIGUL_FULL_LEGACY_PARITY_COMPLETION_PLAN_2026-09-28.md`](SORIGUL_FULL_LEGACY_PARITY_COMPLETION_PLAN_2026-09-28.md): 무엇을 언제 완료하는가.
- [`CURRENT_SOURCE_OF_TRUTH.md`](CURRENT_SOURCE_OF_TRUTH.md): tracked 문서의 분류와 release/source evidence routing.

## 2. Evidence hierarchy

증거가 충돌하면 다음 순서를 적용한다.

1. 전사프로그램에서 사용자가 명시적으로 승인한 더 최근의 제품 결정이 현재 locked 문서에 반영된 내용
2. 이 Current Product Contract와 아래 supersession map
3. Legacy `jeonsa_doumi`의 실제 ACTIVE runtime code와 실제 validation evidence
4. 과거 historical planning 및 audit 문서
5. 현재 Sorigul 구현

현재 Sorigul에 이미 구현되어 있다는 사실만으로 의도된 제품 계약이라고 판단하지 않는다. 새로운 차이가 필요하면 반드시 다음 절차를 거친다.

`Evidence → Conflict → Options → Impact → User Decision → Contract Lock`

## 3. Default parity rule

Legacy ACTIVE user-visible capability와 functional behavior는 기본적으로 보존한다. 예외는 명시적인 user-approved `Intentional Change`뿐이다.

기능 계약은 계승하지만 implementation architecture는 greenfield로 변경할 수 있다. Legacy source Copy 또는 Import는 금지한다.

## 4. Preserved Legacy contracts

### File workflow

- 사용자가 transcription folder를 선택한다.
- 선택 folder의 top-level MP3만 scan한다.
- 선택 파일을 실행하며, 미선택 시 모든 미완료 파일 실행 전 확인한다.
- 정상 TXT/JSON/SRT 완료 bundle은 skip하고, 불완전 bundle은 DONE으로 보지 않는다.
- 결과는 MP3와 같은 위치와 stem을 사용한다.
- 명시적인 re-transcribe를 지원한다.
- replacement 결과가 완전히 검증되기 전까지 기존 정상 결과를 보존한다.
- 파일 하나의 국소 실패가 이후 파일 처리를 막지 않으며 성공 결과를 보존한다.

### Filename

- 긴 한글 및 Unicode filename을 지원한다.
- week/lesson 감지와 적용 가능한 page/download-name cleanup을 유지한다.
- standard-name을 보호한다.
- MP3/TXT/JSON/SRT collision을 인식한다.
- next available lesson allocation과 safe same-stem bundle rename/rollback을 유지한다.

#### Manual week and Eduwill no-week normalization (#180)

- Canonical filename은 `{과정명}_{과목명}_{N주차}_{M강}`이다.
- 사용자는 과정명 + 과목명 + 주차를 입력한다. 주차는 1 이상의 정수이며 server-side에서 검증한다.
- 주차는 `RuntimeSettings`에 persist하지 않는다. 실제 folder 변경 시 입력값을 지운다.
- Legacy week/lesson detection precedence는 보존한다: `[N-M]` bracket → `N주차 M강` → `[N주차]`/`N주차` week only. leading `N강`은 course-wide counter이며 주차 내 lesson이 아니다. (#124)
- source filename에 명시적인 주차가 없고 standalone global `N강` counter가 정확히 하나만 있는 Eduwill형 파일은:
  - `N강`을 주차로 해석하지 않는다.
  - `N강`을 주차 내 lesson으로 해석하지 않는다.
  - 사용자가 입력한 주차를 사용한다.
  - 해당 주차에서 first/next available lesson을 배정한다.
- source explicit week == manual week이면 기존 동작과 동일하다.
- source explicit week != manual week이면:
  - silent overwrite를 금지한다.
  - `WEEK_MISMATCH`로 explicit review를 요구한다.
  - 사용자가 명시적으로 선택해야만 typed week(과정명 + 과목명 + manual week)로 rename한다.
- `CONTINUE_ORIGINAL`:
  - unresolved classification으로 원래 이름을 유지한 채 Local 전사는 가능하다.
  - 해당 run의 Drive upload는 강제 OFF다.
  - 계속 진행한 `WEEK_MISMATCH`는 week/lesson을 확정된 metadata로 기록하지 않는다.

### Job and recovery

- `STOPPED`, `CANCELLED`, `CRASHED`를 구분한다.
- 중지·취소·비정상 종료 항목은 수동 Retry할 수 있다.
- Retry에서 `DONE` 파일은 보존하고 skip한다.
- job state는 atomically persist한다.
- 손상된 state는 quarantine하며 정상 결과를 손상시키지 않는다.
- restart 후 완료 결과를 보존한다.

### Local

- engine: OpenAI Whisper
- model: `medium`
- local CUDA preferred
- GPU/model-load 실패 시 CPU fallback
- Legacy-compatible automatic fp16 decision과 fp16 failure fallback
- decoding: `language="ko"`, `task="transcribe"`, `temperature=0`, `beam_size=5`, `best_of=5`, `patience=1.0`, `condition_on_previous_text=False`

### Colab

- engine: `faster-whisper`
- model: `large-v3`
- Colab CUDA preferred, CUDA compute type `float16`
- CPU fallback compute type `int8`
- Korean transcription과 segment timestamp를 TXT/JSON/SRT로 merge
- "Colab 열기" convenience를 현재 Sorigul bootstrap/rendezvous flow 기준으로 제공한다. Legacy notebook/clipboard/Flask 경로의 복구가 아니다. (#127 A1)

현재 Sorigul의 Colab OpenAI Whisper `medium` 구현은 **CURRENT IMPLEMENTATION DEFECT**이며 현재 계약이 아니다. #106이 Local/Colab engine parity를 복구한다.

### Folders and Desktop

- 실제 filesystem이 결과 truth다.
- all/complete/incomplete/results filter와 TXT preview/full view를 제공한다.
- file/folder open 또는 reveal을 제공하고 외부 파일 변경을 반영한다.
- file/job completion notification을 제공한다.
- notification에서 result folder를 open/reveal할 수 있어야 한다.
- Tray, close-to-tray/exit behavior를 유지한다.
- Tray tooltip은 현재 전사 상태를 honest하게 표시한다: 실제 current progress, current file, terminal state만 사용하며 fabricated progress/ETA는 금지한다. (#127 A2)
- Folders 목록은 사용자 조작으로 오름차순/내림차순 정렬한다. Legacy ACTIVE와 동일하게 **파일명/유형만 sortable**이며 상태/수정일은 non-sortable이다. (#127 A3)
- TXT preview/full view는 **display only** bounded encoding fallback을 사용한다: `utf-8-sig → utf-8 → cp949 → euc-kr → utf-8 errors=replace`. Sorigul이 생성하는 TXT는 계속 UTF-8이며 source TXT를 rewrite/transcode하지 않는다. (#127 A5)
- completed-job shutdown은 immediate/15 sec/30 sec, countdown과 cancel을 지원한다.
- backend/process tree를 정리하고 orphan을 남기지 않는다.
- Windows와 Unicode/Korean path를 지원한다.

### #127 parity decision lock

#127 final decision은 5F (#123) inventory의 AMBIGUOUS 5건을 default parity rule(§3)로 판정했다. 아래 결정은 현재 locked 계약이며 #123 regression은 이 분류를 사용한다. #127 이력은 수정하거나 삭제하지 않는다.

| ID | Legacy ACTIVE affordance | Decision | #123 classification | Implementation | Current authority |
|---|---|---|---|---|---|
| A1 | Colab 열기 | RESTORE | PRESERVED | #130 | §4 Colab |
| A2 | Tray progress tooltip | RESTORE | PRESERVED | #131 | §4 Folders and Desktop |
| A3 | Folders column sorting (파일명/유형) | RESTORE | PRESERVED | #132 | §4 Folders and Desktop |
| A4 | Queue clear buttons | APPROVED REMOVAL | APPROVED_INTENTIONAL_CHANGE | 없음 (removal) | §5N |
| A5 | TXT encoding fallback | RESTORE FOR DISPLAY ONLY | PRESERVED | #133 | §4 Folders and Desktop |

#127 기준 AMBIGUOUS 잔여: **0**.

## 5. Approved Intentional Changes

다음 항목은 parity defect가 아니라 승인된 현재 계약이다.

### A. Dashboard

Legacy statistics Dashboard는 제거하고 structured Log를 사용한다. navigation은 Transcription, Log, Folders, Settings다.

### B. Drive bundle

Legacy의 MP3/TXT/JSON/SRT 4종에서 **TXT/JSON/SRT only**로 변경한다. MP3는 업로드, import, copy 또는 move하지 않는다. `update_or_create`, Drive failure와 Local DONE의 분리, local result 보존은 유지한다.

#108은 incomplete context로 생성된 뒤 direct user decision을 회복하여 correction comment와 duplicate close로 정정된 이력이다. 이력은 수정하거나 삭제하지 않는다.

### C. Prompt and corrections

Legacy subject-specific prompt/correction layer와 automatic text substitution은 이식하지 않는다. locked decoding options는 별개로 유지한다.

### D. MP3 import/move

managed folder로 MP3를 import, copy 또는 move하는 기능은 제거한다. 사용자가 OS로 selected folder에 둔 MP3를 Sorigul이 scan한다.

### E. Course and subject

Legacy fixed detection/dropdown primary flow 대신 course와 subject를 user free-text로 입력한다. 주차는 사용자가 입력하고(persist 안 함), filename의 명시적 week/lesson 감지는 Legacy precedence대로 유지한다. 상세 규칙은 §4 Filename의 #180 계약을 따른다.

### F. Drive classification

새 Job은 filename 재파싱이 아니라 Job/file metadata를 classification source of truth로 사용한다. metadata가 없는 legacy persisted Job만 좁은 compatibility fallback을 사용할 수 있다.

### G. Stage mapping

known subject는 stage를 자동 mapping한다. unknown exact subject는 persisted 1차/2차 override를 사용할 수 있다.

### H. Exam root

Google Drive exam root는 configurable이다.

### I. Drive auto-upload

per-run checkbox만 제공하며 app launch마다 `OFF`가 기본이다. 설정으로 persist하지 않는다.

### J. Colab connection

automatic rendezvous가 primary다. manual URL은 fallback이다.

### K. Colab chunk policy

300초 internal chunk를 사용하되 chunk detail은 UI에 노출하지 않는다. FAILED는 검증된 완료 chunk를 내부적으로 재사용할 수 있고 chunk별 initial request와 최대 1회 automatic retry를 허용한다. STOP/CANCEL은 current-file chunk progress를 재사용하지 않으며 CANCEL은 `CANCELLED`로 끝난다.

### L. Duration, progress, and ETA

실제 audio metadata를 사용한다. 현재 승인 구현은 duration에 `mutagen`, 실제 split에 FFmpeg를 사용한다. fabricated duration/progress/ETA를 금지하고 Colab chunk count/duration은 사용자에게 노출하지 않는다.

### M. Security hardening

signed requests, pairing, replay protection, fail-closed behavior, private OAuth/token boundary와 strict local/runtime permission boundary를 유지한다.

### N. Queue clear

Legacy의 display-only queue clear 버튼은 복구하지 않는다. (#127 A4, APPROVED REMOVAL)

현재 queue는 selected folder filesystem truth의 live projection이다. MP3 import/move가 제거되었으므로(§5D) Legacy처럼 imported/moved row를 화면에서만 지우는 "clear row"는 현재 product model과 구조적으로 충돌한다. 이 결정은 실제 파일 삭제 기능을 의미하지 않으며 도입하지도 않는다. 구현 작업은 없다.

## 6. Explicit exclusions

다음은 복구 대상이 아니다.

- deprecated Google Drive Queue product path
- archived backup/POC path
- old experimental engines 또는 UI engines
- public GitHub Release/signing requirement
- paid API, paid GPU, managed paid tunnel 또는 기타 paid fallback

## 7. Lightweight contract

경량화는 기능 축소가 아니라 packaging/runtime 분리다.

- **Core:** torch 없음, CUDA payload 없음, Whisper 없음, Local Runtime payload 없음
- **Local:** 별도 versioned Local Whisper Runtime
- **Colab:** Google Colab runtime
- **Drive:** Core lightweight path

Current regression ceiling은 Core/MSI `<= 250 MiB`다. 단순 크기보다 더 중요한 requirement는 Core/MSI 안의 `torch/CUDA/Whisper/Local Runtime payload = NONE`이다.

Manifest ownership도 이 split-runtime 계약에 고정한다.

- **Core build manifest owns Core provenance only:** schema/version metadata, `source_head`, `tracked_tree_clean`, Core size policy, sidecar/FFmpeg size/hash와 release input hashes.
- **Core manifest MUST NOT own `torch_requirement` / `expected_cuda`.** Core/MSI consumer인 Windows installer도 이 Local-only field를 요구하거나 consume하지 않으며 Local Runtime을 설치하지 않는다.
- **Local Runtime manifest owns Local runtime identity:** `runtime_type`, `runtime_version`, `protocol_version`, exact scalar string `torch_requirement = "torch==2.13.0+cu130"`, `expected_cuda = "13.0"`, worker/artifact hash, artifact size, `source_head`와 tracked clean provenance.
- **Runtime discovery is the fail-closed consumer of Local-only metadata.** exact torch/CUDA identity, runtime/protocol version, artifact hashes와 tracked provenance를 검증한다.
- **Local/Core `source_head` pairing remains mandatory.** installed Core와 Local Runtime의 source identity가 다르면 reject한다.

Historical pre-split Core torch metadata acceptance는 현재 manifest ownership을 override하지 않는다. stale gate를 만족시키기 위해 Local-only metadata를 Core/MSI에 복구하지 않는다.

Local Runtime 자체의 크기(약 2GB)는 현재 lightweight 계약 위반이 아니다. 현재 release blocker는 Core/MSI heavy payload exclusion과 Core/MSI `<= 250 MiB`뿐이다. #169 Local Runtime size optimization은 **OPEN / NON-BLOCKING / POST-DEADLINE OPTIMIZATION**이며 Freeze, #113, #114 또는 main merge의 blocker가 아니다.

## 8. Zero-cost contract

다음을 자동 선택, 구매, 활성화 또는 fallback으로 사용하지 않는다.

- paid API
- paid GPU 또는 managed cloud runtime
- credit 또는 billing activation
- paid/managed tunnel fallback
- 기타 paid resource fallback

무료 사용 여부를 안전하게 확인할 수 없으면 기능을 삭제하거나 paid fallback으로 바꾸지 않는다. validation을 `PENDING_ZERO_COST_EXTERNAL_VALIDATION`으로 남긴다.

## 9. Study-use deadline

Deadline: **2026-10-31 KST**

Target: **`STUDY USE READY = YES`**

Public release는 project goal이 아니다. 일정, acceptance와 final workflow는 #116 및 [`SORIGUL_FULL_LEGACY_PARITY_COMPLETION_PLAN_2026-09-28.md`](SORIGUL_FULL_LEGACY_PARITY_COMPLETION_PLAN_2026-09-28.md)를 따른다.

### Study-use concurrency

같은 Windows PC에서 사용자가 브라우저의 인터넷 강의를 시청하는 동안 Sorigul Local 전사를 병행할 수 있어야 한다. 이 계약은 성능 저하가 전혀 없다는 보장이 아니다.

Acceptance 의미:

- 인터넷 강의 재생 중 Local transcription을 시작할 수 있다.
- Sorigul은 browser/video playback을 의도적으로 pause/close/block하지 않는다.
- Local Job이 정상 진행 및 완료된다.
- browser가 실사용 가능한 상태로 유지된다.
- Sorigul worker/backend process ownership과 cleanup이 정상이다.
- 결과 TXT/JSON/SRT가 정상이다.

이 요구사항은 #47 installed real-study gate에서 실제 환경으로 검증한다. 실제 contention으로 공부가 곤란하면 #47 PASS를 주장하지 않고 evidence와 함께 새 Issue로 분리한다.

### Pre-Freeze decisions (not adopted / measurement only)

- **Process priority:** Local worker `BELOW_NORMAL` 등 scheduler/process-priority 변경은 **NOT ADOPTED by default**. Freeze 전에 예방적으로 우선순위를 낮추지 않는다. #47에서 실제 동시 재생 contention이 재현되고 evidence가 있을 때만 새 Issue로 검토한다.
- **Colab retry interval:** No current retry-interval change. Revisit only if a real zero-cost Colab 524 condition is reproduced with evidence and a safe remediation is justified. 추측에 의한 interval 값을 계약에 넣지 않는다.
- **Local startup:** measurement only. Fresh #113이 PASS한 같은 installed artifact에서 #56/#63 진행 시 COLD/WARM Local startup을 측정한다. 측정 구간은 explicit Local Start부터 기존 app event/log에서 일관되게 관측 가능한 worker/job-ready milestone까지이며, cold/warm 모두 같은 milestone 정의를 evidence에 명시한다. 새 PASS threshold를 만들지 않고, 느리다는 이유만으로 같은 Freeze에서 packaging을 변경하지 않으며 onefile → onedir 자동 전환을 금지한다. 문제가 명백하면 evidence → 새 Issue → 새 source cycle이다.

## 10. Git/GitHub contract

모든 work unit에 다음 lifecycle이 필수다.

`Issue → dedicated branch → implementation/review → test → meaningful commit → push → PR create/update → Issue update → #7 update → approved merge gate`

완료된 작업을 local에만 남기지 않는다. 독립 defect는 독립 Issue로 분리한다. `git add .`, `git add -A`, rebase, force push, `reset --hard`, `git clean`, `main` 직접 개발을 금지한다. #114 PASS 전에는 main merge를 금지한다. constituent stacked PR은 review/evidence surface로 유지하며 main에 하나씩 merge하지 않는다. final source ancestry를 모두 포함하는 하나의 consolidated integration PR만 #114 PASS와 final gate approval 후 main에 merge한다(single consolidated integration merge). rebase, force push 또는 squash로 constituent ancestry를 재작성하지 않는다. 상세 규칙은 [`DEVELOPMENT_RULES.md`](DEVELOPMENT_RULES.md)를 따른다.

## 11. Contract supersession map

| Topic | Legacy / Earlier Contract | Current Contract | Decision Type | Current Authority | Notes |
|---|---|---|---|---|---|
| Dashboard | Legacy statistics Dashboard | Dashboard 제거, structured Log | Approved Intentional Change | §5A | 복구 금지 |
| Drive bundle | MP3/TXT/JSON/SRT 4종 | TXT/JSON/SRT only; MP3 전송 안 함 | Approved Intentional Change | §5B | #108 correction history 유지 |
| Prompt/corrections | subject prompt와 text correction | 미이식 | Approved Intentional Change | §5C | decoding options는 유지 |
| MP3 import/move | managed import/move path | import/copy/move 없음 | Approved Intentional Change | §5D | selected folder scan |
| Course/subject | fixed alias detection/dropdown | user free-text | Approved Intentional Change | §5E | week/lesson 감지는 유지 |
| Week source | filename week detection only | user manual week (not persisted); explicit filename week precedence 유지; Eduwill no-week global `N강` normalization; WEEK_MISMATCH explicit review | Approved Intentional Change | §4 Filename / #180 | silent overwrite 금지; CONTINUE_ORIGINAL은 Drive OFF |
| Study-use concurrency | 명시 계약 없음 | 인터넷 강의 시청 중 Local 전사 병행; 무저하 보장 아님 | Current goal | §9 / #47 | process priority 변경 NOT ADOPTED |
| Drive classification | filename 재파싱 | new Job metadata truth | Approved Intentional Change | §5F | legacy Job만 narrow fallback |
| Stage mapping | fixed mapping 중심 | known auto mapping + unknown exact override | Approved Intentional Change | §5G | override persist |
| Exam root | fixed/root assumption | configurable exam root | Approved Intentional Change | §5H | Drive setting |
| Colab connection UX | manual/clipboard URL 중심 | auto rendezvous primary, manual fallback | Approved Intentional Change | §5J | URL persist 불필요 |
| Colab chunk policy | older mixed recovery descriptions | 300 sec internal, hidden UI, approved retry/recovery/cancel | Approved Intentional Change | §5K | chunk detail 비노출 |
| Audio duration | ffprobe/placeholder history | mutagen metadata, FFmpeg split | Approved Intentional Change | §5L | read failure는 honest unknown |
| Progress/ETA | fixed or fabricated display 가능 | real duration/honest progress/ETA only | Approved Intentional Change | §5L | chunk count 비노출 |
| Drive auto-upload | persistent/global setting proposal | per-run, launch마다 OFF, not persisted | Approved Intentional Change | §5I | Job request only |
| Queue clear rows | Legacy display-only clear | Removed | Approved Intentional Change | #127 A4 / §5N | filesystem-truth consequence; 파일 삭제 아님 |
| Minor UX affordances | Colab 열기, tray progress tooltip, Folders 파일명/유형 sort, TXT encoding fallback | Restored under current constraints | Preserved Legacy parity | #127 A1/A2/A3/A5 / §4 | #130 #131 #132 #133 |
| Security | Legacy connection boundaries | signed, paired, replay-protected, fail closed | Approved hardening | §5M | capability를 축소하지 않음 |
| Local runtime packaging | monolithic heavyweight possibility | separate versioned Local Runtime | Current constraint | §7 | Core payload NONE |
| Zero-cost | external path cost가 명시적이지 않음 | paid/billing/credit/fallback 금지 | Current constraint | §8 | 불명확하면 PENDING |
| Study-use deadline | public release 중심 sequence | 2026-10-31 KST STUDY USE READY | Current goal | §9 / #116 | public release 불필요 |
| Git lifecycle | commit/push/PR이 선택적 정리 단계 | 전체 lifecycle이 work-unit 완료 조건 | Governance lock | §10 / #107 | #7 update 포함 |
| Main merge | stacked PR bottom-up merge | single consolidated integration PR merge after #114 PASS | Governance lock | §10 / Pre-Freeze reconciliation | constituent PR은 review/evidence surface |

## 12. Historical preservation

[`MIGRATION_CONTRACT.md`](MIGRATION_CONTRACT.md), [`FEATURE_PARITY.md`](FEATURE_PARITY.md), [`LEGACY_FEATURE_PARITY_AUDIT.md`](LEGACY_FEATURE_PARITY_AUDIT.md), [`../migration/CORE_WORKFLOW_REFINEMENT_PLAN.md`](../migration/CORE_WORKFLOW_REFINEMENT_PLAN.md)와 과거 validation 문서는 삭제하거나 현재형으로 일괄 재작성하지 않는다. 기존 amendment notice와 원문은 provenance/evidence로 보존하고, 현재 결정은 이 문서에서 판정한다.
