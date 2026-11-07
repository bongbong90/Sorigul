# #59 installed-QA harness — stage 1: pure contracts

QA-only code, separate from the product. This stage implements four
validators from `IMPLEMENTATION_SCOPE.md` §A and their unit tests. Nothing
here downloads, installs or launches anything. There is no workflow, and
nothing in this directory authorizes execution.

Private repository creation, MSI transfer, Actions runs, MSI install and the
installed QA run remain BLOCKED behind separate approval. The 0 KRW cost
condition is still NOT VERIFIED.

## Run

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\qa59installed\Invoke-ContractTests.ps1
```

1. AST-parses the PowerShell.
2. Checks that the contract sources are pure: no I/O, process, network,
   native, registry or environment APIs.
3. Checks that this directory holds no workflow files.
4. Compiles with the .NET Framework `csc` (C# 5, `/warnaserror+`,
   `/checked+`, `/codepage:65001`) into a fresh temp folder.
5. Runs `ContractTests.exe`, then deletes the folder. Exit code 0 means every
   suite passed.

## Contracts

| File | Contract |
|---|---|
| `StrictJson.cs` | Bounded RFC 8259 reader. Rejects duplicate keys, BOM, NaN, trailing data and unpaired surrogates. Errors carry fixed codes and never echo input text. |
| `CandidateManifest.cs` + `candidate-manifest.json` | Exact 14-key allowlist, pinned to product #216 HEAD `890364e`, the Freeze, the MSI (SHA256 + 70,606,848 bytes) and the Desktop/Core/FFmpeg/manifest digests. It holds no QA commit, so it cannot reference its own commit. `Observation.Msi`/`InstalledFiles` give PASS, FAIL or NOT_VERIFIED (unmeasured). `InstallerPermit` allows msiexec only when the manifest is valid, the MSI observation is PASS and the gate grants install. |
| `ContextGate.cs` + `current-execution-context.json` | Requires a private, non-product repo whose ID and name match the approval. The QA SHA must be lowercase 40-hex, must differ from the product HEAD and must equal the approved SHA. The run must use the approved `refs/heads/` ref and `workflow_dispatch`, with attempt 1 only. The execution approval needs an ID, and the cost limit must be 0 KRW with no paid usage. Free allowance and the overage block must both be verified, at a UTC time **before** dispatch. Install needs download approval too. Unknown means deny. The committed current context evaluates to DENY. |
| `ResultContract.cs` | Fixed order of 12 steps and 7 negative cases, each with its own evidence allowlist (bool or bounded count). Verdicts come from the evidence: unmeasured gives NOT_VERIFIED, and a step may declare a worse verdict, never a better one. Install exit 3010/1641 is FAIL. Supervisor timeout, UIA hang, provider failure, forced cleanup, Job-close kill or skips give at least NOT_VERIFIED, and residual processes/ports or an abnormal exit give FAIL. Cleanup has its own verdict and never upgrades the test verdict. No free-text fields. `VerdictLatch`: the worst verdict wins, and the supervisor's `Freeze` turns pending steps into NOT_VERIFIED and discards late records. |
| `SyntheticFixtures.cs` | Builds and validates Settings/Jobs revisions A and B against product `RuntimeSettings` (extra=forbid) and the full `JobModel`. A = 2 total / 1 done / 1 failed and B = 3 / 1 / 2, in separate `revision-A`/`revision-B` folders under a runner-owned `qa59-fixture-<32hex>` root. Shutdown is disabled and Drive is off. Media names, credential-like strings, protected roots and real folders are rejected. `Classify` follows the decision order of `recovery.rs` `confirm_saved_idle` and maps each fixture to the product code the restart gate must show. `FixtureWritePolicy` permits replacement only for `OFFLINE_CONFIRMED`. |

## Known limits

- The strict reader is stricter than `serde_json`. Duplicate keys, integers
  outside 64 bits and nesting deeper than 32 classify as `AMBIGUOUS`, which
  has no expected product code and cannot be used as a fixture.
- The fixtures are synthetic past terminal history. They make no claim of a
  real transcription or result file.
- Missing or exclusively locked `jobs.json` cases are file-system states that
  belong to a later runtime stage. `Classify(null)` covers only the expected
  code for a missing file.
- Not implemented yet: authenticated asset fetch, installer driver,
  native owner/observer, UI driver, scenario controller and the runtime
  supervisor. Each needs its own review before any approved run.
