# Sorigul — LOCKED decision: Google reply is not a dependency / Colab optional / Local-first

**Status: LOCKED — explicit user decision, reconfirmed 2026-11-15 KST**  
**Issue:** #264  
**Authority:** [CURRENT_PRODUCT_CONTRACT.md](CURRENT_PRODUCT_CONTRACT.md) (current canonical product contract)  
**Context:** The user already said this on 2026-09-28 and 2026-11-13; the same rule was reconfirmed after LIVE-B2D on 2026-11-15. Repeated proposals to wait for a Google response contradicted the user's decision.

> **Do not wait for Google's official policy reply to continue Sorigul development. Free Google Colab is optional/best-effort. When a zero-cost or policy condition is restricted, ambiguous or unverified, do not spend money or bypass a restriction: hold the Colab-specific action and proceed with fully Local transcription work and validation.**

## Exact meaning — do not reinterpret in a new chat

1. **No Google reply dependency.** The Google inquiry is informational only; waiting for its reply must not be used as a blocker, prerequisite, new approval gate or recurring work item for **Local** development, build, installed validation or normal study-use preparation. Do not suggest asking Google again merely to keep work moving. If an actual policy prohibition is known, respect it and do not perform the prohibited cloud action.
2. **Cloud and Local gates are independent.** When Colab cost/policy/availability is unknown or incompatible, set **Colab only** to `PENDING_ZERO_COST_EXTERNAL_VALIDATION` / `POLICY_NOT_VERIFIED` / `BLOCKED` as appropriate. This is **not** `LOCAL_BLOCKED`, does not delete the Colab feature and is not a reason to stop Local verification. Prioritize Local OpenAI Whisper `medium` using the separate versioned Local Runtime (local CUDA preferred, CPU fallback under existing contract).
3. **Zero cost is non-negotiable.** No paid API, GPU, Colab credit/CU, billing activation, managed tunnel, or automated paid fallback. Do not claim FREE subscription/T4 eligibility proves zero cost or policy compliance. A failed/uncertain cloud gate is not authorization to create more Runtimes.
4. **Fallback is a workflow priority, not silent execution permission.** A user-selectable Local route may be offered or selected in accordance with the current UI/job contract; do not silently re-run an existing cloud job, replace protected results, make an unapproved external request, or claim Local study-use PASS without evidence. For implementation and testing, move effort to the Local path immediately instead of inventing another cloud-only QA phase.
5. **Safety still applies.** Preserve user MP3/results/OAuth/Drive and all existing runtime ownership, lease, recovery, cleanup and `DEFAULT OFF` controls. An unresolved owned Runtime remains a cloud recovery blocker; it does not authorize ignoring cleanup or deleting another runtime. Real Google OAuth/API/Jupyter/Runtime/GPU/Drive operations, protected user-data tests and actual Windows shutdown still require their own explicit user approval. Main/integration merge stays gated as already documented.
6. **Do not rewrite historical results.** LIVE-B2 upload's 11 chunks / 662,508 bytes / `VERIFIED / CONTENT_SHA256` remain evidence for upload only. B2A–D offline QA PASS and unresolved live checks remain as reported; cost/policy/hard deadline/WinError 5 status is **not** retroactively converted to PASS. Historical LIVE plans that state “wait for Google reply” are superseded **only on the scheduling dependency point** by this LOCKED decision.

## Decision table for agents / new chats

| Condition | Required project decision | Not allowed |
|---|---|---|
| Google has not replied | **Continue Local work now**; record Colab policy as NOT VERIFIED | Waiting for Google as a dependency |
| Free Colab zero-cost cannot be established | **Hold Colab-only run; Local-first**; keep external validation pending | Paid fallback, guessing zero cost |
| Google policy restricts proposed automation | **Do not execute restricted cloud path; Local-first** | Bypass policy, switch to unofficial paid/manual workarounds |
| Colab is demonstrably permissible/free, and the user separately approves a particular LIVE run | Optionally test only that approved scope using owned-runtime cleanup gates | Treating this decision as blanket LIVE approval |
| An owned cloud Runtime is unresolved | Keep cloud recovery BLOCKED; protect existing state and follow authorised recovery | New Runtime create or deletion of someone else's Runtime |
| Local readiness not yet evidenced | Work on the existing Local implementation / installed QA path; report exact blockers | Claiming `STUDY USE READY=YES` without required evidence |

## Next work priority / handoff

1. **Do not open another “Google official reply gate” phase.** Record #48/#60 as independent external pending work if cost or policy is unverified; do not spin up repeated Colab QA phases to resolve an already-recorded uncertainty.
2. **Continue the critical Local path** using the current canonical roadmap and available evidence: Local Runtime/installed artifact validation (#113, #56/#63), actual Local Korean study-audio validation (#47) when separately authorised, recovery (#59), final overall study workflow (#114). Check the actual current-HEAD status before marking anything PASS; the order is not permission to bypass release freezes or protected-data gates.
3. Keep the Colab code and drafts (#255 → #257 → #259 → #261 → #263) unmerged unless existing approval gates are met. They are optional external engineering evidence, not a dependency for starting Local work.
4. If the user later explicitly requests an actual Colab LIVE action, require **that operation's** approval and established cost/policy/safety checks; do **not** ask the user again whether to wait for Google or whether Local is the fallback. That strategic choice is already LOCKED.
5. When reporting, distinguish `LOCAL_STATUS`, `COLAB_EXTERNAL_STATUS`, `COST_GATE`, `POLICY_GATE`, and `EXECUTION_APPROVAL`. Never roll them into a single "everything blocked" label.

## Handoff snippet for a fresh chat

**Read first:** `docs/project/CURRENT_PRODUCT_CONTRACT.md`, this file, `docs/project/DEVELOPMENT_RULES.md`, `docs/project/ROADMAP.md`, and the latest relevant GitHub Issue/PR.  
**Standing decision:** “Do **not** wait for Google. Colab is optional and only when demonstrably free/permitted; when not, hold cloud operations and prioritize fully Local transcription. Do not pay, bypass policy, alter the protected data, or start real external work without its explicit approval. Keep Local and Colab acceptance gates separate. Do not restart the Google-policy discussion.”  
**Git process:** Issue → dedicated branch → exact-file change/test → commit/push → Draft PR → Issue/#7 update; no premature merges.

This is a **decision and planning document only**. It does not change product code, enable Local/Colab execution, certify zero cost, or grant a LIVE approval.
