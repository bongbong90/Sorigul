# Study Use Current-HEAD Installed Validation — 2026-10-02

## Verdict

**6A-R3 / #113: BLOCKED — stopped during source preflight, before Stage A.**

Blocker: [#154](https://github.com/bongbong90/Sorigul/issues/154), the explicit
Core scalar-manifest / installer-consumer acceptance requirement does not match
the frozen split-runtime source schema. This report records a stopped attempt;
it is not fresh artifact or installed-runtime PASS evidence.

No Local Runtime, Core, or MSI build started. No uninstall, install, canonical
runtime promotion, desktop launch, or installed synthetic validation occurred.
The existing installed product and canonical runtime were left in place.

## Source identity and authority

| Item | Actual state |
|---|---|
| Parent branch | `fix/packaged-local-runtime-cuda-selftest` |
| Exact start / artifact source HEAD | `d06a74def23af7e8a571e3ed9a106cf0ab150f30` |
| Validation branch | `gate/fresh-current-head-artifact-revalidation-r2` |
| Branch creation / initial push | PASS; created at the exact source HEAD and immediately pushed with upstream |
| Parent PR | [#153](https://github.com/bongbong90/Sorigul/pull/153): OPEN / MERGEABLE / NOT MERGED at preflight |
| #150 resolution | [CLOSED / COMPLETED](https://github.com/bongbong90/Sorigul/issues/150); process-handle fix remains historical PASS |
| #123 source gate | [CLOSED / COMPLETED](https://github.com/bongbong90/Sorigul/issues/123); 2026-09-30 report remains historical PASS |
| Full #123 rerun after #150 | NOT REQUIRED; unchanged decision |
| Current-run artifact set | NONE |
| Validation report commit | Later report-only commit; distinct from the fixed artifact source HEAD above |

Authoritative inputs were Git/source, live GitHub Issues/PRs,
`docs/project/CURRENT_PRODUCT_CONTRACT.md`,
`docs/project/DEVELOPMENT_RULES.md`, the #123 PASS report, and #150 final evidence.
No prior agent conversation memory was used.

The original scalar fix `22ebe3d28170386ab1a580ae2f3ed2f533f19269` is an ancestor
of the fixed source HEAD (`git merge-base --is-ancestor`: exit 0).

## Preflight and focused validation

| Check | Result |
|---|---|
| Starting branch / HEAD | Exact expected parent and SHA |
| `git status --short` | No tracked changes; only the five existing untracked helpers |
| Protected untracked files | `monitor.ps1`, `smoke.ps1`, `smoke_desktop.ps1`, `smoke_qa.ps1`, `tunnel_log`: untouched |
| `git diff --check` | PASS |
| Packaging focused | 18 passed |
| Release readiness + trusted Windows utilities | 21 passed |
| Windows PowerShell schema audit | Completed with `powershell.exe`, version `5.1.26100.9444` |
| Source/build scripts/tests/existing docs | Unchanged; only this new audit report is authored |

Commands actually run:

```text
# From backend/:
..\venv\Scripts\python.exe -m pytest tests/test_release_packaging_contract.py -q
# 18 passed in 0.93s

# From repository root:
.\venv\Scripts\python.exe -m pytest tests/test_release_readiness_contracts.py tests/test_trusted_windows_utilities_contracts.py -q
# 21 passed in 0.05s

git diff --check
```

An initial combined invocation from the repository root failed test collection
with `ModuleNotFoundError: src`. Running the backend suite from its required
`backend/` working directory passed without source or test changes. This is a
harness/working-directory failure, not a new product defect.

The execution host denied sandboxed shell creation before any command ran.
The read/check commands were successfully rerun through the permitted elevated
tool route. No Windows Installer elevation or application install was attempted.

## Blocker #154 — exact requirement and source evidence

The explicit restart request, sections 14–15 and 43/56, requires a fresh Core
`sorigul-build-manifest.json` with:

- exact scalar `torch_requirement = "torch==2.13.0+cu130"`;
- exact JSON round-trip type/value and absent provider-object metadata;
- fail-closed installer validation of the same field;
- fresh confirmation before #45 can close.

At the frozen HEAD, the actual Core manifest generator does not emit this field
and the installer does not inspect it. The Local manifest does emit and validate
the scalar. A fresh build cannot provide the requested Core-field evidence from
these unchanged scripts.

| Source location | Observed behavior |
|---|---|
| `scripts/build_backend_sidecar.ps1:371` | Core manifest contains the ten keys below; no `torch_requirement` |
| `scripts/build_backend_sidecar.ps1:389` | Core round-trip checks integral size policy and exact source HEAD, not torch scalar |
| `scripts/build_windows_installer.ps1:80` | Validates size policy, source HEAD, clean flag, and artifact hashes; no torch-field reference |
| `scripts/build_local_whisper_runtime.ps1:305` | Local manifest emits exact torch/CUDA scalars |
| `scripts/build_local_whisper_runtime.ps1:322` | Local manifest checks exact scalar type/value after JSON round-trip |

Windows PowerShell 5.1 parsed the scripts with its AST parser, selected the
`$Manifest` hashtable keys, and inspected the installer source. It did not execute
the build scripts. Exact non-sensitive result:

```json
{
  "powershell_version": "5.1.26100.9444",
  "source_head": "d06a74def23af7e8a571e3ed9a106cf0ab150f30",
  "core_manifest_keys": [
    "schema_version",
    "source_head",
    "generated_at_utc",
    "tracked_tree_clean",
    "core_sidecar_size_limit_mib",
    "sidecar_size",
    "sidecar_sha256",
    "ffmpeg_size",
    "ffmpeg_sha256",
    "release_input_sha256"
  ],
  "core_torch_requirement_present": false,
  "installer_torch_requirement_reference_present": false,
  "local_torch_requirement_present": true,
  "requested_core_scalar_gate": "BLOCKED",
  "fresh_builds_started": false
}
```

Historical source inspection (`git show b34a7cd`) shows that the lightweight
split deliberately removed the Core torch/CUDA metadata and corresponding
installer consumer checks. This finding is a **gate acceptance/schema mismatch**;
it does not establish a lightweight payload violation or reproduce the original
#45 provider-metadata-object defect. No #150 process-handle regression was observed
because its packaged execution was not reached.

The request's first-blocker STOP rule applies. The Local scalar proof was not
silently substituted for the requested Core proof, and no build-script/source
fix was made in this audit branch.

## Process and prior installed product inventory

Read-only inventory observed:

- `sorigul-desktop.exe`: 0;
- `sorigul-backend.exe`: 0;
- `sorigul-local-whisper.exe`: 0;
- TCP port 8000 listeners: 0.

The HKLM native/WOW6432Node and HKCU uninstall roots contained exactly one
Sorigul registration. These values were read from the actual registry, not copied
from historical documentation:

| Property | Prior installed value |
|---|---|
| ProductCode | `{2BA7F9F4-A5A4-4B96-89B3-49989810CD0B}` |
| DisplayVersion | `0.1.0` |
| InstallLocation | `C:\Program Files\Sorigul\` |
| Registered uninstall command | `MsiExec.exe /X{2BA7F9F4-A5A4-4B96-89B3-49989810CD0B}` |
| Uninstall / fresh install | NOT RUN |
| Fresh ProductCode | NONE |

The prior registration is inventory only. It is not current-HEAD installed proof.
No process was killed and no registry entry or Program Files file was changed.

## Artifact and installed validation matrix

| Required gate | Actual result |
|---|---|
| Stage A isolated fresh Local Runtime build | NOT RUN — stopped before Stage A |
| Stage A CUDA preflight / PyInstaller / packaged self-test | NOT RUN |
| Stage A handle retained / exit 0 / protocol 1 / DONE / cuda | NOT RUN |
| Stage A runtime manifest/hash/release-input validation | NOT RUN |
| Stage A isolated candidate cleanup | N/A — candidate was never created |
| Fresh Core build / manifest provenance | NOT RUN |
| Core torch scalar / installer consumer | BLOCKED at source preflight — #154 |
| Core archive exclusion, including numba/llvmlite | NOT RUN |
| Core / MSI 250 MiB ceiling | NOT RUN — no fresh artifact sizes |
| Fresh staged FFmpeg identity | NOT RUN |
| Fresh current-run MSI path/size/hash/version/ProductCode | NONE — build not started |
| MSI Local/torch/CUDA/Whisper payload exclusion | NOT RUN |
| Old product clean uninstall | NOT RUN |
| Fresh MSI install / registry count | NOT RUN |
| Stage C final canonical fresh Local Runtime build | NOT RUN |
| Final Local executable / manifest SHA / source identity | NOT RUN |
| Final canonical CUDA compute/readback self-test | NOT RUN |
| Core / Local exact source pairing / hashes / protocol | NOT RUN |
| Program Files backend/FFmpeg/manifest staged comparison | NOT RUN |
| Installed desktop UI / backend auto-start / `/api/health` | NOT RUN |
| Installed backend Program Files executable / hidden console | NOT RUN |
| No installed Python/Node/Vite/npm/repo-venv dependency | NOT RUN |
| Core startup/health/Colab/Drive availability without Local | NOT RUN |
| Missing-runtime fixture: `LOCAL_RUNTIME_MISSING` | NOT RUN |
| Invalid JSON fixture: `LOCAL_RUNTIME_INVALID` | NOT RUN |
| Wrong protocol: `LOCAL_RUNTIME_VERSION_MISMATCH` | NOT RUN |
| Wrong hash: `LOCAL_RUNTIME_INVALID` | NOT RUN |
| Wrong source HEAD: `LOCAL_RUNTIME_PROVENANCE_MISMATCH` | NOT RUN |
| Installed bundled FFmpeg + Korean/space/Unicode silence MP3 | NOT RUN; no media fixture created |
| Synthetic scan/filename/duration/incomplete classification | NOT RUN |
| Desktop-only forced close / Job Object backend cleanup | NOT RUN |
| Normal idle `WM_CLOSE`, `close_behavior=exit` | NOT RUN |
| Cleanup elapsed / port release / orphan checks after launch | NOT RUN; no launch occurred |
| Unowned external backend protection | NOT RUN; #56/#63 follow-up remains pending |

No #46, #150, or other historical/diagnostic executable was reused as current
artifact evidence. Canonical build scripts were neither bypassed nor executed.

## User-data safety

No installation or Local Runtime update was reached. Therefore the pre-update
protected-state hash inventory and post-update comparison were **NOT RUN**; this
report does not claim measured before/after hash equality.

| Protected state | Action during this attempt |
|---|---|
| `%LOCALAPPDATA%\Sorigul\settings.json` | Not opened or modified |
| `%LOCALAPPDATA%\Sorigul\jobs.json` | Not opened or modified |
| `%LOCALAPPDATA%\Sorigul\auth\` | Not traversed or modified |
| Other real Sorigul user state | Not accessed or modified |
| Whisper model/cache | Not inventoried, downloaded, or modified |
| Existing canonical Local Runtime | Not opened, copied, renamed, deleted, or rebuilt |
| Actual study folder / MP3/TXT/JSON/SRT | NOT ACCESSED |

Only a unique test-owned TEMP directory was created for source-audit script/output
and GitHub body files. It contained no runtime binary or personal study fixture.
User state contents were never printed. Existing untracked helpers were untouched.

**USER DATA TOUCHED = NO**, based on the actions performed; installed-update
preservation proof remains pending.

## Size comparison — historical only, no fresh measurements

| Artifact | Historical #46 bytes | Historical MiB | Fresh current bytes | Delta bytes | Delta MiB | Delta % |
|---|---:|---:|---|---|---|---|
| Local Runtime | 2,004,298,539 | 1,911.45 | NOT BUILT | N/A | N/A | N/A |
| Core sidecar | 36,756,447 | 35.05 | NOT BUILT | N/A | N/A | N/A |
| FFmpeg | 87,638,016 | 83.58 | NOT STAGED | N/A | N/A | N/A |
| Staged Core total, two binaries | 124,394,463 | 118.63 | NOT BUILT | N/A | N/A | N/A |
| MSI | 70,053,888 | 66.81 | NOT BUILT | N/A | N/A | N/A |

The #150 isolated candidate (`2,004,301,544` bytes, SHA prefix `857ed5`) remains
diagnostic history only. It was not read or reused by this attempt.

## Trackers and not-run scope

- #154: independent gate/schema blocker opened; no source fix in this work unit.
- #113: OPEN / BLOCKED; body and checkpoint updated.
- #45: OPEN; fresh confirmation pending, with a checkpoint explaining the
  distinct schema mismatch. Original object-serialization regression not reproduced.
- #116 BODY: live Oct 5–11 section BLOCKED / STARTED EARLY; #113 unchecked;
  #154 must resolve before restart. Deadline remains 2026-10-31 KST.
- PR #115: live checkpoint updated to the same blocker and pending sequence.
- #7: 6A-R3 source-focused PASS / artifact-install BLOCKED checkpoint recorded.
- #56 / #63: OPEN; no exact fresh installed artifact supplied and no 6B work begun.
- #150: CLOSED / COMPLETED; not reopened.
- #123: historical PASS / CLOSED preserved.

Personal MP3, real Local study transcription (#47), actual Colab, actual Drive
OAuth/upload, actual shutdown, paid resources, broad #56/#63 UX, notification
buttons, tray visuals, Folders sort/live-refresh visuals, active-X-close UX, and
retry UI were **NOT RUN**. No PR was merged.

## Final disposition

```text
FOCUSED SOURCE PREFLIGHT = PASS
REQUESTED CORE SCALAR / CONSUMER CONTRACT = BLOCKED (#154)
FRESH LOCAL RUNTIME = NOT RUN
FRESH CORE = NOT RUN
LIGHTWEIGHT SPLIT ARTIFACT PROOF = NOT RUN
FRESH MSI = NOT RUN
CLEAN INSTALL = NOT RUN
INSTALLED CUDA SYNTHETIC = NOT RUN
PROVENANCE ARTIFACT PAIRING = NOT RUN
CLEANUP / ORPHAN INSTALLED PROOF = NOT RUN
USER DATA TOUCHED = NO
CURRENT-HEAD INSTALLED CORE = BLOCKED / NOT VALIDATED
READY FOR #56/#63 = NO
#113 = BLOCKED
```

**STOP.** Resolve #154 in a separate work unit. A source/build fix requires a new
agreed artifact source HEAD and fresh builds of all affected Local/Core/MSI
artifacts; the fixed `d06a74d` identity cannot silently become the identity of a
different source tree. Only a complete #113 PASS can unlock the separate 6B
#56/#63 current-artifact Windows Native / Folders integration QA.
