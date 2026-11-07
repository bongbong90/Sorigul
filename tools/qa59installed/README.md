# #59 installed-QA harness — Stage 2A: local Runtime boundaries

QA-only code, separate from the product. Stage 1.1 contracts are hardened and
the Windows local Runtime boundary modules are implemented in `runtime/`.
There is no workflow or installed-product executor. No external control or
isolated QA account SID is enabled, so execution remains denied.

See [STAGE2A_DESIGN.md](STAGE2A_DESIGN.md) for containment, process ownership,
deadlines, evidence provenance and the single-dispatch external-control design.

Private repository creation, MSI transfer, Actions runs, MSI install and the
installed QA run remain BLOCKED behind separate approval. The 0 KRW cost
condition is still NOT VERIFIED. No trusted external pre-dispatch control
exists yet, so the public `ContextGate.Evaluate` denies every context.

## Run

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\qa59installed\Invoke-ContractTests.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File tools\qa59installed\Invoke-RuntimeTests.ps1 -Containment
python tools\qa59installed\Check-Mutations.py
```

1. AST-parses the PowerShell.
2. Runs a purity lint on the contract sources, preceded by self-tests of the
   lint itself. In one pass the lint recognizes string literals, char
   literals and comments, so `"http://x"` is not read as a comment. It then
   matches whole identifiers and fails on I/O, process, network, native,
   reflection, console or environment APIs. The lint guards against
   accidents; it is not a sandbox.
3. Checks that this directory holds no workflow files.
4. Compiles with the .NET Framework `csc` (C# 5, `/warnaserror+`,
   `/checked+`, `/codepage:65001`) into a fresh temp folder. The contracts
   build as production `Qa59Contracts.dll`. A separate `test-only` build defines
   `QA59_CONTRACT_TESTS` for `ContractTests.exe`. Never deploy that test DLL.
5. Runs `ContractTests.exe`, then deletes the folder. Exit code 0 means every
   suite passed.

The Runtime script compiles against the production contract DLL and compiles
the synthetic worker without launching it. It runs model tests and, with
`-Containment`, fixed fixture/junction tests in a newly created QA-only directory
directly under the public profile. Desktop/AppData/Documents roots are refused.
Cleanup uses the exact held file/directory handles. No installed files are read.
Process/Job/endpoint integration tests remain NOT_VERIFIED until an isolated QA
account is provisioned and independently checked. The mutation script uses only
source copies and the same permitted local tests.

## Contracts

| File | Contract |
|---|---|
| `StrictJson.cs` | Bounded RFC 8259 reader. Rejects duplicate keys, BOM, NaN, trailing data and unpaired surrogates. Errors carry fixed codes and never echo input text. |
| `CandidateManifest.cs` + `candidate-manifest.json` | Exact 14-key allowlist, pinned to product #216 HEAD `890364e`, the Freeze, the MSI (SHA256 + 70,606,848 bytes) and the Desktop/Core/FFmpeg/manifest digests. It holds no QA commit, so it cannot reference its own commit. `Observation.Msi`/`InstalledFiles` give PASS, FAIL or NOT_VERIFIED (unmeasured). `InstallerPermit` allows msiexec only when the manifest is valid, the MSI observation is PASS and the gate grants install. |
| `ContextGate.cs` + `current-execution-context.json` (schema 2) | The context's IDs and booleans are **claims**. Execution also needs approval consumption and budget enforcement by external pre-dispatch controls on a reviewed, compiled-in allowlist. That allowlist is empty, so `Evaluate` denies everything. The injection seam and assembly friendship exist only with QA59_CONTRACT_TESTS. Assembly names are forgeable; test builds are never execution authorities. Production GateDecision construction denies unconditionally, and the public gate always uses separate empty approval/budget allowlists. The remaining rules:<ul><li>**Repository:** private, with an ID and name that match the approval. The public product repo is refused by name and by its pinned ID (1327637229).</li><li>**QA SHA:** lowercase 40-hex, different from the product HEAD and equal to the approved SHA.</li><li>**Run:** the approved `refs/heads/` ref, `workflow_dispatch`, attempt 1 only.</li><li>**Approval:** a printable-ASCII ID of `[A-Za-z0-9._-]{1,64}`, so zero-width and non-ASCII characters fail. It must be in state `CONSUMED` with `consumed_by_run_id` equal to this run's `run_id`. ISSUED, REVOKED, unknown states or a different run are denied.</li><li>**Cost:** 0 KRW with no paid usage. Free allowance and the overage block must be verified before dispatch, at most 1 hour earlier and in the same UTC month.</li><li>Install needs download approval too. Unknown means deny.</li></ul> |
| `SingleUseApproval.cs` | State machine: ISSUED goes to CONSUMED(run) or REVOKED, and CONSUMED can go to REVOKED. Nothing ever returns to ISSUED, and a consumed approval never binds a second run. This matters because a new `workflow_dispatch` also starts at attempt 1, so `run_attempt` alone cannot stop reuse. The contract defines only the transitions. Real enforcement needs an external control that performs `Consume` atomically **before** dispatch, outside the job it authorizes. |
| `ResultContract.cs` (schema 3) | Fixed order of 12 steps and 7 negative cases, each with its own evidence allowlist (bool or bounded count). Verdicts come from the evidence: unmeasured gives NOT_VERIFIED, and a step may declare a worse verdict, never a better one. **S08** separates one user click (`user_click_count`=1), the two SendInput events requested (`sendinput_events_requested`=2, down+up) and the events SendInput reported as inserted (`sendinput_events_inserted`=2), plus separately measured `foreground_confirmed` and `hit_target_confirmed`. Delivering the input is not button success: the actual ONLINE recovery and B sync are S09. Install exit 3010/1641 is FAIL. Supervisor timeout, UIA hang, provider failure, forced cleanup, Job-close kill or skips give at least NOT_VERIFIED, and residual processes/ports or an abnormal exit give FAIL. Cleanup has its own verdict. No free-text fields. `VerdictLatch`: the worst verdict wins, and `Freeze` turns pending steps into NOT_VERIFIED and discards late records. |
| `AcceptanceGate.cs` | Top-level #59 installed acceptance is the worst of four separately reported parts:<ul><li>**product:** a valid result document whose overall verdict is PASS.</li><li>**cleanup:** the independent cleanup verdict.</li><li>**run:** the gate allowed install, and the run ID and QA SHA observed at execution match the gate and the result.</li><li>**msi:** the observed installed bytes equal the pinned candidate.</li></ul>Cleanup PASS never upgrades a product FAIL, and product PASS never hides a cleanup FAIL. Today this always evaluates to FAIL (`RUN_NOT_AUTHORIZED`). |
| `SyntheticFixtures.cs` | Builds and validates Settings/Jobs revisions A and B against product `RuntimeSettings` (extra=forbid) and the full `JobModel`. A = 2 total / 1 done / 1 failed and B = 3 / 1 / 2, in separate `revision-A`/`revision-B` folders under a runner-owned `qa59-fixture-<32hex>` root. Shutdown is disabled and Drive is off. Media names, credential-like strings, protected roots and real folders are rejected. The root and every protected root must be canonical long paths: no 8.3 `~` aliases, `\\?\`, UNC, `/`, ADS or device names. Device names include COM0–9, LPT0–9 and the superscript ¹²³ forms, with spaces before the extension ignored as Win32 does (`CON .txt`). An empty protected-root list counts as unknown. `Classify(byte[])` decodes strictly, as the product reads raw bytes, so a BOM or invalid UTF-8 is malformed. `Classify` follows the decision order of `recovery.rs` `confirm_saved_idle`. `FixtureWritePolicy` permits replacement only for `OFFLINE_CONFIRMED`. |

## Runtime-boundary requirements (later stages, not implemented here)

- **Reparse points:** before creating or writing any fixture, refuse the
  root if it or any ancestor is a junction or symlink. Then compare the final
  resolved (handle-based) path against the resolved protected roots again.
  The pure `ValidateRoot` checks strings only.
- **Single-use approval:** an external control must consume the approval
  atomically before dispatch. It has to be reviewed and added to
  `ContextGate`'s trusted list before any run.
- **Budget:** an external control must enforce 0 KRW before dispatch.
  Context booleans are not proof.
- **Execution evidence:** `ExecutionEvidence` (run ID, QA SHA, MSI
  digest/size) must come from runtime observation, not from the result
  document.

## Known limits

- The strict reader is stricter than `serde_json`. Duplicate keys, integers
  outside 64 bits, nesting deeper than 32 and input over 1 MiB classify as
  `AMBIGUOUS`, which has no expected product code and cannot be used as a
  fixture.
- The fixtures are synthetic past terminal history. They make no claim of a
  real transcription or result file.
- Missing or exclusively locked `jobs.json` cases are file-system states that
  belong to a later runtime stage. `Classify(null)` covers only the expected
  code for a missing file.
- Not implemented yet: authenticated asset fetch, installer driver,
  native owner/observer, UI driver, scenario controller, runtime supervisor
  and the external approval/budget controls. Each needs its own review before
  any approved run.
