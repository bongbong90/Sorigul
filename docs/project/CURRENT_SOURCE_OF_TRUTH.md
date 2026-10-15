# Sorigul Current Source of Truth

## Authority and precedence

For current product decisions, use the following precedence:

1. More recent explicit user-approved product decisions recorded in a current locked document.
2. `docs/project/CURRENT_PRODUCT_CONTRACT.md` and its supersession map.
3. Actual ACTIVE Legacy runtime code and validation evidence.
4. Historical planning and audit documents, including the original D01-D10 and D11+ decision records.
5. Current Sorigul implementation.

Historical evidence can explain a past result but cannot override the current product contract.
Current Sorigul code is not proof that a product difference was intended. `AMBIGUOUS` documents must
not be used to make current implementation decisions. The matrix below contains no unresolved
ambiguous authority.

## Approved post-plan hardening amendments

- Packaged `--self-test` establishes a unique owned temporary app-data environment before importing
  `src.main`, restores environment strings exactly, and fails explicitly if exact-root cleanup fails.
- The base Tauri config depends only on tracked static resources. Generated sidecar, ffmpeg, and
  manifest resources exist only in `frontend/src-tauri/tauri.release.conf.json`.
- Python release tooling requires the Python 3.13 line. Runtime dependencies are exact-pinned from
  the verified local environment, except `python-multipart==0.0.32`, whose pin comes from official
  read-only PyPI metadata and is used only by the Colab artifact.
- A packaged Local release requires `torch==2.13.0+cu130`, `torch.version.cuda == 13.0`, an available
  CUDA device, and a successful real CUDA tensor computation. CPU fallback behavior in development
  or historical artifacts is not acceptable release evidence.
- `scripts/run_core_workflow_regression.ps1` is the canonical local, offline-capable, no-build source
  regression. It never installs dependencies or creates placeholder release artifacts.

## Product-contract routing

`docs/project/CURRENT_PRODUCT_CONTRACT.md` is the single current product-contract entry point. It
integrates preserved Legacy behavior, approved Intentional Changes, the lightweight and zero-cost
constraints, the 2026-10-31 study-use deadline, and the Git/GitHub governance lock.

Unclear cost fails closed: no paid resource or fallback is enabled when zero-cost status cannot be
safely established.

The most important engine guardrail is explicit: Local is OpenAI Whisper `medium`; Colab is
`faster-whisper large-v3` with CUDA `float16` preferred and CPU `int8` fallback. The current Sorigul
Colab `medium` implementation is a defect owned by #106, not product authority.

This ledger classifies evidence; it does not duplicate or replace the product contract. The
completion plan separately defines what is completed when.

## Quick Tunnel operational limit

TryCloudflare Quick Tunnel is used only to connect to a user-started Colab runtime. Existing research
identifies it as a free/accountless path, while Cloudflare documents Quick Tunnels as a
testing/development facility with operational limitations. Sorigul does not automatically provision
a paid or managed replacement. Availability is a best-effort external dependency.

## Document classification matrix

Classification values are exact: `CURRENT CONTRACT`, `SUPERSEDED`, `HISTORICAL EVIDENCE ONLY`,
`STALE`, and `AMBIGUOUS`.

| Path | Classification | Reason | Current replacement / authority |
|---|---|---|---|
| `README.md` | CURRENT CONTRACT | Repository entry point routes product decisions to the Current Product Contract. | Current Product Contract for product behavior. |
| `colab/README.md` | CURRENT CONTRACT | Current Colab runtime usage and connection instructions. | Current Product Contract for engine/model behavior. |
| `frontend/README.md` | CURRENT CONTRACT | Current frontend development commands with links to historical implementation records. | Current Product Contract for product behavior. |
| `docs/README.md` | CURRENT CONTRACT | Current documentation routing entry point. | Current Product Contract and this ledger. |
| `docs/backend/CORE_BACKEND_FILE_JOB_MIGRATION.md` | SUPERSEDED | Pre-refinement migration snapshot includes earlier filename assumptions. | Core workflow plan and current code/tests. |
| `docs/backend/DRIVE_RESULTS_DESKTOP_UX_MIGRATION.md` | SUPERSEDED | Records the old four-file Drive bundle and filename-derived classification. | Core workflow plan D11/D15 and this ledger. |
| `docs/backend/TRANSCRIPTION_ENGINE_MIGRATION.md` | STALE | Requires ffprobe and describes CPU fallback as sufficient without the release CUDA gate. | Core workflow plan D20 and current release status. |
| `docs/design/APP_SHELL_IMPLEMENTATION.md` | HISTORICAL EVIDENCE ONLY | Implementation/validation record for an earlier phase. | Current design specs and executable UI. |
| `docs/design/DESIGN_SYSTEM_FOUNDATION.md` | SUPERSEDED | Foundation scope retained obsolete Dashboard assumptions. | Current design tokens, app-shell spec, and UI Freeze V1. |
| `docs/design/TRANSCRIPTION_MOCK_INTERACTION.md` | HISTORICAL EVIDENCE ONLY | Preserves mock implementation and validation history. | Current screen spec, state matrix, and executable UI. |
| `docs/design/TRANSCRIPTION_SCREEN_IMPLEMENTATION.md` | HISTORICAL EVIDENCE ONLY | Phase implementation record rather than current authority. | Current screen spec and executable UI/tests. |
| `docs/design/TRANSCRIPTION_SCREEN_SPEC.md` | CURRENT CONTRACT | Current transcription-screen behavior and no-Dashboard navigation. | Core workflow plan, then this spec. |
| `docs/design/UI_FREEZE_CHECKLIST.md` | CURRENT CONTRACT | Checklist aligned to the approved navigation and state decisions. | Core workflow plan, then this checklist. |
| `docs/design/UI_FREEZE_V1.md` | CURRENT CONTRACT | Current frozen UI structure and prohibited reintroductions. | Core workflow plan, then this freeze. |
| `docs/design/UI_STATE_MATRIX.md` | CURRENT CONTRACT | Current user-visible state/action contract. | Core workflow plan, then this matrix. |
| `docs/design/UI_STATE_UX_VALIDATION.md` | HISTORICAL EVIDENCE ONLY | Records a past validation run. | Current UI contract tests and source regression. |
| `docs/design/app_shell_spec.md` | CURRENT CONTRACT | Current four-destination shell explicitly excludes Dashboard. | Core workflow plan, then this spec. |
| `docs/design/brand.md` | CURRENT CONTRACT | Current brand rules. | Current assets and executable UI. |
| `docs/design/color_system.md` | CURRENT CONTRACT | Current color tokens. | Current CSS and executable UI. |
| `docs/design/design.md` | CURRENT CONTRACT | Current visual foundation. | More specific current design documents. |
| `docs/design/icon_system.md` | CURRENT CONTRACT | Current icon-system rules. | Current tracked icons and executable UI. |
| `docs/design/typography.md` | CURRENT CONTRACT | Current typography rules. | Current CSS and executable UI. |
| `docs/migration/CORE_WORKFLOW_REFINEMENT_PLAN.md` | CURRENT CONTRACT | Preserves the D11+ decision provenance and implementation planning record. | Current Product Contract for current behavior. |
| `docs/project/CURRENT_PRODUCT_CONTRACT.md` | CURRENT CONTRACT | Canonical current product-contract entry point and supersession map. | This file itself. |
| `docs/project/CURRENT_SOURCE_OF_TRUTH.md` | CURRENT CONTRACT | Current evidence precedence, amendments, and complete document ledger. | Current Product Contract for product behavior. |
| `docs/project/DEVELOPMENT_RULES.md` | CURRENT CONTRACT | Mandatory Git/GitHub lifecycle and repository safety rules. | Current Product Contract where product behavior is involved. |
| `docs/project/FEATURE_PARITY.md` | SUPERSEDED | Summary predates final release-only CUDA hardening and carries amended legacy language. | Core workflow plan and this ledger. |
| `docs/project/FRONTEND_FOUNDATION.md` | STALE | Early foundation document leaves obsolete Dashboard/Results work outstanding. | Current UI freeze/specs and executable UI. |
| `docs/project/LEGACY_FEATURE_PARITY_AUDIT.md` | HISTORICAL EVIDENCE ONLY | Immutable legacy evidence, including claims intentionally removed later. | Core workflow plan and this ledger. |
| `docs/project/MIGRATION_CONTRACT.md` | SUPERSEDED | Earlier contract contains specifically superseded four-file and filename rules. | Core workflow refinement plan. |
| `docs/project/MIGRATION_CONTRACT_REVIEW.md` | HISTORICAL EVIDENCE ONLY | Decision-review evidence for the earlier migration contract. | Core workflow plan and this ledger. |
| `docs/project/PROJECT_CHARTER.md` | CURRENT CONTRACT | Current study-use purpose and implementation boundaries. | Current Product Contract for detailed product behavior. |
| `docs/project/ROADMAP.md` | CURRENT CONTRACT | Current execution order from governance through #114 and closeout. | Completion plan for detailed scheduling. |
| `docs/project/SORIGUL_FULL_LEGACY_PARITY_COMPLETION_PLAN_2026-09-28.md` | CURRENT CONTRACT | Defines completion order, gates, issue map, and 2026-10-31 schedule. | Current Product Contract for product behavior. |
| `docs/release/CORE_WORKFLOW_REFINEMENT_BUILD_VALIDATION.md` | HISTORICAL EVIDENCE ONLY | Immutable Phase 5B artifact from an older source/artifact run. | Current release status and a future current-HEAD ledger. |
| `docs/release/CURRENT_RELEASE_STATUS.md` | CURRENT CONTRACT | Living release/source state; explicitly not historical evidence. | This file itself. |
| `docs/release/FINAL_FEATURE_PARITY_REGRESSION.md` | HISTORICAL EVIDENCE ONLY | Immutable prior regression evidence. | Canonical current source regression and current release status. |
| `docs/release/RELEASE_CHECKLIST.md` | STALE | Claims installer/release verdict completion while current-HEAD artifact gates remain unrun. | Current release status and post-E gate order. |
| `docs/release/RELEASE_NOTES_0.1.0.md` | HISTORICAL EVIDENCE ONLY | Notes for an earlier 0.1.0 state, not a current verdict. | Current release status. |
| `docs/runtime/INSTALLER_INSTALLED_RUNTIME_VALIDATION.md` | HISTORICAL EVIDENCE ONLY | Immutable installed-runtime evidence for an earlier artifact. | Current release status and future current-HEAD validation. |
| `docs/runtime/STUDY_USE_FULL_SOURCE_CONTRACT_REGRESSION_2026-09-29.md` | HISTORICAL EVIDENCE ONLY | #123 (5F) source-level Legacy/current-contract regression at fixed HEAD `71d6920`; verdict FAIL (#124 P1). | Re-run after the pre-artifact burn-down; #113 current-HEAD gate. |
| `docs/runtime/STUDY_USE_FULL_SOURCE_CONTRACT_REGRESSION_2026-09-29_LEGACY_INVENTORY.md` | HISTORICAL EVIDENCE ONLY | Per-file classification of all 337 tracked Legacy files at `fbc86313` for #123. | Current Product Contract for product behavior. |
| `docs/runtime/STUDY_USE_FULL_SOURCE_CONTRACT_REGRESSION_2026-09-30.md` | HISTORICAL EVIDENCE ONLY | #123 fresh source-regression PASS at fixed audit HEAD `c8c08b39`; historical validation evidence that does not approve later source or artifact changes. | Current Product Contract for product behavior; fresh gates for later source/artifact changes. |
| `docs/runtime/STUDY_USE_INSTALLED_SYNTHETIC_VALIDATION_2026-09-28.md` | HISTORICAL EVIDENCE ONLY | Issue #46 installed synthetic PASS for a fixed earlier source/artifact set. | #113 future current-HEAD installed gate. |
| `docs/runtime/STUDY_USE_KOREAN_REAL_SPEECH_FIXTURE_VALIDATION_2026-09-28.md` | HISTORICAL EVIDENCE ONLY | Controlled fixture/stress PASS; explicitly leaves #47 real study audio pending. | #47 real personal Local study gate. |
| `docs/runtime/TAURI_RUNTIME_SIDECAR_OS_INTEGRATION.md` | HISTORICAL EVIDENCE ONLY | Past runtime integration implementation/validation record. | Current code, behavioral tests, and post-E gate order. |
| `docs/runtime/WINDOWS_APP_ICON_BRANDING.md` | HISTORICAL EVIDENCE ONLY | Past icon generation and native verification record. | Current tracked icons and current contract tests. |
