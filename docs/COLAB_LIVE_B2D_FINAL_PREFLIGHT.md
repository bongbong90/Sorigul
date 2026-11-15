# LIVE-B2D: final offline coordinator, cleanup evidence and deadline gates (#262)

Parent: #261 / `fix/260-colab-live-b2c-safety-review` @
`b31f096da882ca307a6bccc079887b29df856ca5` (verified before work; #261 OPEN,
Draft, unmerged). Only the five expected user helper files were untracked. All
35 B2C-preserved files (user helpers, original LIVE-B2/A/B/C evidence and
scripts, OAuth/credential/settings/jobs files — hash only, contents not read)
matched their B2C hashes before and after work. None is in Git.

Scope is QA-only and offline. No Google OAuth/API, Runtime, Jupyter, GPU,
model/package download, real MP3 or Drive request was made. Product code,
DEFAULT OFF, cost/policy gates and engine selection are unchanged.

## What was added

| Module | Role |
|---|---|
| `backend/qa/colab_qa_deadline.py` | `RunDeadline` (monotonic, fake-clock testable), 25 min work / 30 min Runtime limits, 240 s cleanup reserve, `authorize_runtime_creation` (max one Runtime, any non-CLEANED record blocks) |
| `backend/qa/colab_qa_cleanup.py` | Read-only `NativeContentsPresenceProbe` / `NativeRuntimePresenceProbe` and the evidence bridge `confirm_file_cleanup` / `confirm_runtime_cleanup` |
| `backend/qa/colab_qa_writer.py` | `QAResultWriter`: allowlisted schema, QA-only directory, exclusive temp + fsync, no-overwrite publish, re-read verification |
| `backend/qa/colab_qa_coordinator.py` | `TrustedSources`, `TrustedObserver` (store + lease + account + owned Runtime + OWNED transfer record), single-use `QACoordinator` over the unchanged `run_qa()` |

### TASK A — trusted observer and lease

`TrustedSources.from_owner(store, owner, client, transfer)` accepts only the
product objects of one execution (exact types, `owner.store is store`,
`owner.client is client`). The owned-Runtime GET runs inside
`store.transaction()` because its `RUNTIME_CONFIRMED` checkpoint must persist
under the store lock.

Every observation re-checks:
- the lease is held by this process's `RuntimeOwnership`
- exactly one durable record exists for the execution, and no other record is unresolved
- the request ID matches
- the verified account binding matches
- the Runtime name matches
- the state is `ACTIVE_OWNED` with `cleanup_required`
- the OWNED/VERIFIED/CONTENT_SHA256 transfer record matches (size, SHA256, chunks)
- the connection matches the transfer and has not expired
- the HTTPS origin matches the approved base, and the Contents path is the exact pinned one

The existing `OwnedReadbackAdapter` enforces the pin.

Lease check: the owner must hold `_lease`, and an independent probe of
`store.execution_lease()` must fail to acquire it. If the probe does acquire
it, the lease was not held: it is released immediately and the run BLOCKS.
Lease files are never deleted or force-released. Lease release is never
treated as remote cleanup.

A preflight failure BLOCKS with no Jupyter request, no DELETE and no result
file. The following also block:
- a result file already exists for this execution, or a second `run()` is attempted
- the runtime probe is bound to another Runtime name
- the transfer or Runtime client timeout is unbounded (> 20 s; the product transfer default is 30 s)

Before each cleanup DELETE, ownership is re-authorized (lease, identity, state,
account). A mid-run change stops every subsequent DELETE.

### TASK B — cleanup evidence bridge

File cleanup is PASS only when all of these hold:
- the product `CleanupReport` is clean, and the owned target is in `deleted_paths`
- `run_dir_deleted` is true, with nothing failed or skipped
- no CONFLICT/UNCERTAIN record exists
- an independent GET `?content=0` of the file returns 404
- an independent GET of the run directory returns 404

The proxy token for the probes is re-derived from a fresh trusted owned-Runtime
observation.

Runtime cleanup is PASS only when all of these hold:
- the account and identity were re-verified before DELETE (otherwise no DELETE)
- `RuntimeOwnership.cleanup()` returned `CLEANED`, `cleanup_required=false` and no error
- an independent GET returns 404
- a complete `runtimes.list` (at most 5 pages) excludes the Runtime and contains no other `sorigul-*` Runtime
- the durable record for the same identity is `CLEANED` with `DELETED`/`ABSENT`
- the account is still verified after the probes

Probe outcomes other than an exact 404 or a complete listing are `UNCERTAIN`.
They map to `None`, so the verdict is NOT_VERIFIED/UNCONFIRMED, never PASS.
Another `sorigul-*` Runtime of unknown ownership is reported and never deleted.
Product cleanup contracts were not changed.

### TASK C — atomic result writer

The root must be absolute, named `sorigul-qa-results`, free of `..`, and
outside product app data. Every path component is checked with `lstat` and
rejected if it is a link, junction or reparse point. A missing root is created
with `mkdir` (no `-p`). The writer creates one file per execution,
`qa-result-<execution_id>.json`, and an existing file is never overwritten.

The record must match exact key sets, built from the
`QADiagnostics.snapshot()` structure plus the coordinator template. Leaves may
only be None, bool, an int from 0 to 1e9, or a string from fixed QA
enumerations, so tokens, URLs, paths, account hashes and media cannot be
represented.

Commit sequence:
1. Create a temp file with `O_EXCL`, write it fully (short writes loop), `fsync`.
2. Publish without overwriting: Windows `rename`, POSIX `link` + unlink.
3. `fsync` the directory (POSIX).
4. Re-read the file and check bytes, size, nlink and the parsed record.

Any failure raises the fixed `QAResultSaveError`. A file that was published but
cannot be verified is renamed aside (`.invalid-*`), never deleted or reported
as committed. Cancellation (BaseException) propagates unchanged. Windows
directory-entry durability across power loss is **NOT VERIFIED**: there is no
directory flush, so the guarantee rests on NTFS metadata journaling.

### TASK D — deadline

The work window runs from work start to cleanup start (≤ 25 min). The Runtime
window runs from the creation mark, taken before the create POST, to confirmed
CLEANED (≤ 30 min). A new step, readback included, may start only if
`work + step ≤ 25 min` and `runtime + step + 240 s reserve ≤ 30 min`. After
any step returns, an overrun is recorded as FAIL. Cleanup is never skipped for
time, because deleting is the safe action.

The verdict is NOT_VERIFIED if the clock is non-monotonic or broken, or if
CLEANED was never observed. The creation gate allows exactly one Runtime per
run. A failed create still consumes it. Any non-CLEANED record, including one
left after a crash, blocks creation, and nothing is recreated automatically.

**Hard deadline enforcement remains NOT VERIFIED.** Measured compliance is
checked, but Python cannot interrupt a blocking call:
- A slow-drip response can exceed the per-read socket timeout.
- An in-flight request is not aborted on cancel.
- Process loss stops the coordinator.

In each case the durable record stays non-CLEANED, which is the recovery
signal. Every result carries `hard_deadline_enforcement: NOT_VERIFIED`.

### TASK E — integrated flow and final verdict

The flow: preflight → deadline/cancel-gated transport → `run_qa()` (readback;
file cleanup + absence; Runtime cleanup + GET/list absence + durable CLEANED,
always attempted after preflight PASS) → sanitized record → atomic write.

Upload evidence is derived from the trusted OWNED transfer record against the
expected bytes, never from caller booleans. A final PASS requires all of:
- all four `run_qa` checks PASS
- lease, observer and bounded operations PASS
- readback gate `ALLOWED` and deadline PASS
- a verified commit

The persisted `pre_commit_verdict` is only a candidate until the commit is
verified. The existing LIVE-B2 product upload evidence (11 chunks / 662,508
bytes / VERIFIED / CONTENT_SHA256) is untouched and independent.

## Tests

| Run | Result |
|---|---|
| New unit tests (deadline + writer) | 40 PASS |
| New integration Mock tests (coordinator, bridge, probes) | 48 PASS |
| Existing QA tests | 138 PASS (unchanged) |
| Backend full regression (Git Bash), first run after implementation | 1,811 PASS / 2 SKIP / 1 existing WARNING, 144.6 s |
| Backend full regression after review fixes (final) | **1,813 PASS / 2 SKIP / 1 existing WARNING**, 0 failures/errors, 134.8 s (= 1,725 + 88 new) |

The integration tests use the real `OwnershipStore`, `RuntimeOwnership`,
`ColabRuntimeClient` (httpx MockTransport) and `ColabJupyterFileTransfer`
(FakeContents), on a temporary store and a fake clock. Socket, DNS and httpx
network access are denied. Covered scenarios:
- every TASK B error scenario
- lease lost, held elsewhere, or a stale in-memory claim
- identity mismatches and another unresolved record
- an existing result file, and repeat runs
- an unbounded timeout
- ownership changes mid-run and at Runtime cleanup
- deadline cases: work limit nearly reached, overrun, and the Runtime limit reached during cleanup
- cancellation, cancellation together with save failure, and save failure after successful cleanup
- a readback timeout, and an upload mismatch

A mutation check confirmed the tests catch removal of the list, file-probe,
other-Runtime, durable, delete-authorization, lease-probe, deadline and reserve
checks.

WinError 5 did not recur in either run (0 occurrences). Its root cause remains
**NOT DETERMINED**; one passing run does not prove the intermittent issue
fixed. The local ignored receipts `tmp/live-b2d-full.log` and
`tmp/live-b2d-full.xml` and the `-r2` final receipts are not committed.

## Independent review

Reviewer: a separate AI reviewer subagent, launched with **no implementation
conversation history**. It is an AI technical review, not human approval. It
read the new modules and tests and the product services they wire, ran the 5
QA test files and 9 memory-only, network-free checks, and made no edits. Its
first run was interrupted by a session end and then resumed.

| Finding | Classification | Disposition |
|---|---|---|
| F1: the Runtime absence probe's httpx client was caller-wired and not bound to the verified account or TLS config. A foreign-account client could return 404 or an empty list, which would read as "absent" | CONFIRMED DEFECT (blocking) | Fixed. The coordinator no longer accepts a probe. `TrustedSources.from_owner` captures the verified `ColabRuntimeClient`'s own httpx session, preflight requires `runtime_http is owner.client._http`, and the coordinator builds the probe for the pinned name. A regression test with a foreign session expects BLOCKED, and the mutation check fails when the binding is removed. |
| F2: a list `200 {"error":…}` without `runtimes` was read as a complete empty listing | POTENTIAL RISK | Fixed. Keys outside `{runtimes, nextPageToken}` → UNCERTAIN. Regression test added. |
| F3: the lease probe treats any `RuntimeClientError` as "held". On POSIX, an unlinked and recreated lease file held by another process is indistinguishable | POTENTIAL RISK (POSIX only) | Documented limit. It also requires the in-process `owner._lease`. On Windows, the target platform, the msvcrt lock handle cannot be lost while open. Product `_file_lock` is unchanged. |
| F4: the 240 s cleanup reserve is an estimate; the real worst case can exceed it | POTENTIAL RISK (pass-rate only) | Documented as an estimate in code. An overrun is recorded as FAIL and cleanup is never skipped. |
| F5: an `UploadEvidence` construction failure outside `run_qa`'s finally would have skipped cleanup | NOTE | Fixed. It falls back to all-None (NOT_VERIFIED) evidence and cleanup still runs. Also noted: a BLOCKED preflight cleans nothing, so the caller owns recovery; and `authorize_runtime_creation` is a time-of-check gate, so `RuntimeOwnership.create` remains the authority. |

Verified as correct by the reviewer:
- Uncertainty maps to None.
- HTTP 204/404 alone, or product CLEANED alone, is never PASS.
- Lease files are never deleted or force-released.
- DELETE runs only after a fresh lease/identity/state/account authorization.
- The writer enforces the allowlist and no-overwrite rules, quarantines unverified published files, and preserves BaseException.
- KeyboardInterrupt still reaches cleanup and the save, then propagates.
- A save failure is final FAIL.
- No raw transport error is chained.

Re-verification of the fixes, by the same reviewer: 7 checks, all PASS. The
88 new tests pass. Six of the reviewer's own memory-only tests cover:
- a foreign session with the same token → BLOCKED with no effects (the check is object identity, not matching config);
- a look-alike sources object → BLOCKED;
- `client._http` swapped after binding → BLOCKED;
- the normal flow still PASSes, and its probe uses `owner.client._http`;
- F2 error and extra-key listings → UNCERTAIN;
- an F5 construction failure → FAIL, and cleanup still runs.

No new defect was found. **Final disposition: INDEPENDENT REVIEW PASS**
within this offline scope. F3 and F4 remain documented low risks.

## LIVE-B2 RETEST approval preparation

### Offline gate status

| Gate | Status |
|---|---|
| Observer + lease (Mock/real store) | PASS offline; POSIX lease identity limit (F3) documented |
| File / Runtime cleanup evidence bridge | PASS offline (Mock) |
| Atomic sanitized writer | PASS offline; Windows directory durability NOT VERIFIED |
| 25/30 min deadline control | PASS offline (fake clock); hard enforcement NOT VERIFIED |
| Integrated coordinator + full regression | PASS |
| Independent AI review of new code | PASS after F1/F2/F5 fixes |
| WinError 5 root cause | NOT DETERMINED |
| Cost-zero guarantee | NOT VERIFIED |
| Google policy compliance | NOT VERIFIED (Colab API feedback still pending) |
| User LIVE execution approval | NOT APPROVED |

### Must be verified in a real LIVE run (cannot be shown offline)

- The real `runtimes.list` response shape and pagination. The probe expects `{"runtimes":[{"name"}], "nextPageToken"}`, as seen in the #48 read-only probe; pagination has not been observed live.
- Real GET-after-DELETE behaviour: an exact 404 for the Runtime, and Contents 404 for the file and run directory.
- That the trusted account verifier binds to the live OAuth token.
- Real TLS, no-redirect and no-proxy behaviour of `NativeReadbackWire` and of the verified client's httpx session used for absence probes.
- Real end-to-end timing against the 25/30 min limits, and real blocking or slow-drip behaviour.
- That `ColabJupyterFileTransfer` is constructed with `request_timeout <= 20`. The coordinator blocks otherwise.
- Writer durability on the actual QA result path, which must be outside product app data.

### Recommended default LIVE scope (requires explicit user approval)

1. Official-API pre-check of account, FREE subscription, T4 eligibility and existing runtimes. There must be zero `sorigul-*` runtimes and zero unresolved local records.
2. At most **one** new Runtime, through `authorize_runtime_creation`. No automatic recreation.
3. Synthetic data only.
4. Jupyter Contents upload, then a full-byte owned readback (size, SHA256 and exact bytes).
5. File cleanup, then independent file and run-directory GET 404.
6. Runtime cleanup, then GET 404, a complete list without the Runtime, and a durable CLEANED record.
7. A sanitized atomic result in a QA-only `sorigul-qa-results` directory (for example under the repo's ignored `tmp/`).
8. Stop and clean on any failure or ownership doubt. Unresolved evidence → `RECOVERY_REQUIRED` and STOP.

**Excluded from the default scope.** Each needs its own separate, explicit approval:
- GPU execution
- CUDA installation
- model or package download
- faster-whisper
- synthetic audio transcription

**Always prohibited:**
- real user MP3
- Google Drive changes
- paid or unverified-free resources and automatic paid fallback
- production gate activation
- DEFAULT OFF changes
- PR merges

Cost and policy status stay NOT VERIFIED until Google's reply is received.

LIVE-B2D ends with **STOP**. It grants no live execution or release approval,
and no follow-up feature QA stage is created automatically.
