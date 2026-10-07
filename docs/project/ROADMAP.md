# Sorigul Roadmap

현재 제품 행동은 [`CURRENT_PRODUCT_CONTRACT.md`](CURRENT_PRODUCT_CONTRACT.md)에서 시작한다. 이 roadmap은 과거 completed baseline을 보존하면서 [`SORIGUL_FULL_LEGACY_PARITY_COMPLETION_PLAN_2026-09-28.md`](SORIGUL_FULL_LEGACY_PARITY_COMPLETION_PLAN_2026-09-28.md)의 현재 실행 순서를 요약한다.

## Completed baseline

- Project Foundation
- Design System v1
- App Shell, Transcription Screen과 Mock Interaction foundation
- Contract Baseline Sync, UI State/UX Validation과 UI Freeze
- Core Backend/File/Job, transcription, Drive/Results/Desktop source implementation
- Tauri runtime과 Core/Local Runtime packaging split
- 이전 full source regression과 installed/synthetic validation evidence
- 5A full Legacy parity rebaseline and completion plan

이 항목들은 완료 이력이다. 과거 PASS나 당시 Dashboard/Results 전제는 current-HEAD installed verdict 또는 현재 navigation을 뜻하지 않는다.

## Current stage

**Personal Study Use Completion — Full Legacy Parity Remediation / Installed Validation**

## Current execution order (Pre-Freeze, 2026-10-06 KST)

1. **Source remediation — #167/#172/#170/#171/#173/#168/#174/#180:** SOURCE PASS.
2. **Pre-Freeze Plan Reconciliation:** current product contract, execution plan, merge policy와 GitHub gate를 정합화한다(docs-only).
3. **FULL #123:** full source regression.
4. **Canonical `run_113_preflight` + bootstrap Probe:** 결과 검수 후에만 다음 단계로 간다.
5. **NEW RELEASE FREEZE:** 기존 `780dbb1` #113 artifact는 historical evidence only다.
6. **One fresh #113:** Local → Core → MSI → install.
7. **#56/#63 full installed QA:** 같은 artifact에서 cold/warm Local startup을 measurement-only로 측정한다(threshold 없음, packaging 변경 없음).
8. **#47 real Korean study MP3:** 같은 artifact로 실제 인터넷 강의 동시 재생 중 Local 전사를 검증한다.
9. **#48/#60:** zero-cost-safe external validation. 확인할 수 없으면 기능 삭제 없이 PENDING.
10. **#59 recovery.**
11. **#58 shutdown:** 실제 shutdown은 그 시점의 즉시 명시적 사용자 승인 후에만 실행한다.
12. **#114 final Study Workflow Regression.**
13. **One consolidated integration PR merge:** constituent stacked PR은 개별 merge하지 않는다.

FULL #123보다 먼저 #113 artifact build를 시작하지 않는다. #169 Local Runtime size optimization은 OPEN / NON-BLOCKING / POST-DEADLINE OPTIMIZATION이며 이 sequence의 blocker가 아니다. Process priority 변경과 Colab retry interval 변경은 채택하지 않았다([`CURRENT_PRODUCT_CONTRACT.md`](CURRENT_PRODUCT_CONTRACT.md) §9).

## Historical execution order (superseded by the Pre-Freeze order above)

1. **Governance/source of truth — #107/#112:** mandatory Git/GitHub lifecycle과 canonical current product contract를 잠근다.
2. **Engine parity — #106:** Local OpenAI Whisper `medium`/Legacy-compatible fp16과 Colab `faster-whisper large-v3`/CUDA float16/CPU int8을 복구한다.
3. **Auxiliary parity — #110/#111:** notification folder-open과 live transcription-folder change detection을 독립 work unit으로 복구한다.
4. **Source regression:** preserved Legacy contracts, approved Intentional Changes, lightweight, zero-cost와 security boundary를 전체 검증한다.
5. **Fresh installed gate — #113:** 하나의 current HEAD에서 Local Runtime/Core/MSI를 새로 build/install하고 provenance, payload exclusion, `<=250 MiB`, CUDA synthetic, health, FFmpeg, Unicode와 cleanup을 검증한다.
6. **Native/integration — #56/#63:** 같은 artifact에서 Tray, close behavior, picker/reveal, notification, Folders, retry/recovery와 process cleanup을 검증한다.
7. **Real Local/external — #47/#48/#60:** 실제 personal Local study audio와 안전하게 zero-cost로 확인된 Colab/Drive path를 검증한다. 확인할 수 없는 외부 gate는 기능 삭제 없이 PENDING으로 둔다.
8. **Recovery — #59:** backend failure 후 OFFLINE/reconnect/restart와 job/result 보존 정책을 잠그고 검증한다.
9. **Shutdown — #58:** countdown/cancel을 먼저 검증하고 실제 shutdown은 그 시점의 즉시 명시적 사용자 승인 후에만 실행한다.
10. **Final workflow — #114:** 하나의 installed artifact로 전체 study workflow를 실행하여 `STUDY WORKFLOW REGRESSION = PASS`를 달성한다.
11. **Closeout/main merge — #54/#55/#7:** 문서·test command·Tracker를 동기화하고 PR base/diff를 확인한 뒤 merge한다. (merge 방식은 현재 single consolidated integration PR 정책으로 대체됨)

각 gate가 실패하면 고친 뒤 통과하기 전까지 다음 단계로 진행하지 않는다. 새 독립 defect는 별도 Issue/commit/PR로 분리한다. #114 PASS 전에는 main merge하지 않으며, main merge는 final source ancestry를 모두 포함하는 하나의 consolidated integration PR로만 한다. rebase, force push와 squash를 사용하지 않는다.

## Deadline

**2026-10-31 KST — `STUDY USE READY = YES`**

#116이 고정 deadline과 checkpoint를 추적한다. public GitHub Release는 목표가 아니며 deadline을 맞추기 위해 parity, zero-cost, lightweight, security 또는 user-data safety를 축소하지 않는다.
