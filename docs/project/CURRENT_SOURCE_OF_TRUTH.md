# Sorigul Current Source of Truth

## Authority and precedence

For current product decisions, use the following precedence:

1. `docs/migration/CORE_WORKFLOW_REFINEMENT_PLAN.md` is the top-level current product contract.
2. Approved post-plan hardening amendments recorded in this document govern release safety,
   validation, packaging isolation, and exact dependency/runtime constraints without reopening the
   plan's product decisions.
3. Current executable code together with current behavioral and release-readiness contract tests
   is the implementation authority.

Historical evidence can explain a past result but cannot override the current product contract.
`AMBIGUOUS` documents must not be used to make current implementation decisions. The matrix below
contains no unresolved ambiguous authority.

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

## Current product contract

- **Navigation:** `전사`, `로그`, `Folders`, `설정`; there is no Dashboard.
- **MP3:** top-level folder scan only. There is no import, upload, copy, or move UI.
- **Classification:** course and subject are user metadata and are the classification truth.
- **Filename:** normalization supplies week and lesson identity only; it is not course/subject truth.
- **Drive:** upload only TXT, JSON, and SRT. MP3 is never uploaded.
- **Local:** Whisper `medium`; a packaged release requires working CUDA.
- **Colab:** Whisper `medium`, fixed internal 300-second units, and a user-started runtime only.
- **Persistence:** `last_engine`, course, and subject may persist. Colab URL and Drive auto-upload do
  not persist.
- **Stop/Cancel:** no user-facing Resume. The interrupted current file starts again when retried.
- **Results:** a valid TXT/JSON/SRT bundle is skipped. Retranscription is explicit only.
- **Runtime:** Tauri v2, one-file packaged backend, bundled ffmpeg, and Windows Job Object ownership.
- **Zero-cost:** the application never automatically selects, purchases, provisions, enables, or
  upgrades a paid API, billable usage service, cloud resource, GPU/runtime, credit, subscription,
  billing setting, or payment method. Unclear cost fails closed.

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
| `docs/README.md` | CURRENT CONTRACT | Current documentation entry point. | This ledger. |
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
| `docs/migration/CORE_WORKFLOW_REFINEMENT_PLAN.md` | CURRENT CONTRACT | Highest current product contract. | This file itself. |
| `docs/project/CURRENT_SOURCE_OF_TRUTH.md` | CURRENT CONTRACT | Current precedence, amendments, and complete document ledger. | This file itself. |
| `docs/project/DEVELOPMENT_RULES.md` | CURRENT CONTRACT | Current engineering and repository hygiene rules. | Core workflow plan where product behavior is involved. |
| `docs/project/FEATURE_PARITY.md` | SUPERSEDED | Summary predates final release-only CUDA hardening and carries amended legacy language. | Core workflow plan and this ledger. |
| `docs/project/FRONTEND_FOUNDATION.md` | STALE | Early foundation document leaves obsolete Dashboard/Results work outstanding. | Current UI freeze/specs and executable UI. |
| `docs/project/LEGACY_FEATURE_PARITY_AUDIT.md` | HISTORICAL EVIDENCE ONLY | Immutable legacy evidence, including claims intentionally removed later. | Core workflow plan and this ledger. |
| `docs/project/MIGRATION_CONTRACT.md` | SUPERSEDED | Earlier contract contains specifically superseded four-file and filename rules. | Core workflow refinement plan. |
| `docs/project/MIGRATION_CONTRACT_REVIEW.md` | HISTORICAL EVIDENCE ONLY | Decision-review evidence for the earlier migration contract. | Core workflow plan and this ledger. |
| `docs/project/PROJECT_CHARTER.md` | CURRENT CONTRACT | Current project purpose and implementation boundaries. | Core workflow plan for detailed product behavior. |
| `docs/project/ROADMAP.md` | SUPERSEDED | Earlier phased roadmap is replaced by completed A-E remediation lineage. | Current release status. |
| `docs/release/CORE_WORKFLOW_REFINEMENT_BUILD_VALIDATION.md` | HISTORICAL EVIDENCE ONLY | Immutable Phase 5B artifact from an older source/artifact run. | Current release status and a future current-HEAD ledger. |
| `docs/release/CURRENT_RELEASE_STATUS.md` | CURRENT CONTRACT | Living release/source state; explicitly not historical evidence. | This file itself. |
| `docs/release/FINAL_FEATURE_PARITY_REGRESSION.md` | HISTORICAL EVIDENCE ONLY | Immutable prior regression evidence. | Canonical current source regression and current release status. |
| `docs/release/RELEASE_CHECKLIST.md` | STALE | Claims installer/release verdict completion while current-HEAD artifact gates remain unrun. | Current release status and post-E gate order. |
| `docs/release/RELEASE_NOTES_0.1.0.md` | HISTORICAL EVIDENCE ONLY | Notes for an earlier 0.1.0 state, not a current verdict. | Current release status. |
| `docs/runtime/INSTALLER_INSTALLED_RUNTIME_VALIDATION.md` | HISTORICAL EVIDENCE ONLY | Immutable installed-runtime evidence for an earlier artifact. | Current release status and future current-HEAD validation. |
| `docs/runtime/TAURI_RUNTIME_SIDECAR_OS_INTEGRATION.md` | HISTORICAL EVIDENCE ONLY | Past runtime integration implementation/validation record. | Current code, behavioral tests, and post-E gate order. |
| `docs/runtime/WINDOWS_APP_ICON_BRANDING.md` | HISTORICAL EVIDENCE ONLY | Past icon generation and native verification record. | Current tracked icons and current contract tests. |
