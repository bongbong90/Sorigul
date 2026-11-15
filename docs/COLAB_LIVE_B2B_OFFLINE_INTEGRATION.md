# LIVE-B2B: QA integration and regression triage (#258)

Parent PR #257 / `a8e34b3ab98617a1bce0ea7f492e78d149aa59ca` was verified
before branching. Original LIVE-B2 evidence/scripts, five user helper files and
OAuth artifacts remain hash-identical and excluded from Git. This work executes
no Google/OAuth/Jupyter/Runtime/GPU/Drive operation. Operational services,
uploader, account scopes, cost/policy gates and DEFAULT OFF are unchanged.

## Review status and findings

This is the implementing agent's source review, **not a completed independent
review by another reviewer**. Independent review remains BLOCKED/pending.
The findings below were checked against preserved parent source and synthetic
fixtures; they do not establish the historical LIVE-B2 failure cause.

| Finding | Classification | Evidence and change |
|---|---|---|
| HTTPError response close can raise outside the error handler | CONFIRMED DEFECT | Parent helper propagates a synthetic close exception. Both readback and cleanup now retain the primary error and a safe `response_close_failed` boolean. |
| Invalid response limit leaves a previous PASS receipt | CONFIRMED DEFECT | Parent raises before replacing the receipt. Configuration validation now resets the current attempt and reports CONFIG_INVALID without requesting anything. |
| Accidental string assignment can leak through snapshot | CONFIRMED DEFECT | Parent `asdict` includes a synthetic private marker assigned to a typed field. Snapshot now emits only allowlisted strings and primitive booleans/integers, without deepcopy or exception formatting. |
| Bare CR accepted as a Base64 line wrap | CONFIRMED DEFECT | Parent strips every CR, including one without LF. Normalize CRLF to LF and remove LF only; a lone CR remains invalid. LF/CRLF success and bare-CR rejection are tested. |
| Request attempt versus response observed | NO ISSUE FOUND | Attempt is set before open; observed access is set after response/HTTPError. A timeout before response does not imply access. A fresh run gets fresh diagnostics. |
| HTTP 200 through JSON/model/size/hash/bytes stages | NO ISSUE FOUND | Distinct stages remain recorded. Exact bytes are checked independently of SHA256 (a test-only forced hash collision exercises this branch). |
| Response byte cap | NO ISSUE FOUND | Read requests cap + 1; overflow and Content-Length mismatch fail. The injected transport must return bytes and case-insensitive HTTP headers, as the native HTTP response does. |
| Cleanup independence | NO ISSUE FOUND | New orchestration uses nested finally blocks; Runtime cleanup and result persistence follow even a file-cleanup cancellation. Primary receipt is not overwritten. |
| Future live adapter and real cleanup evidence | POTENTIAL RISK | Not supplied/executed here. Typed evidence is a contract, not independent proof of remote ownership or deletion. Future adapter must obtain real confirmations, never copy caller declarations. |

Exception text/class names outside an allowlist, proxy URLs, paths, accounts,
headers, raw response bodies and media content never enter the safe snapshot.
No product defect was reproduced. Historical LIVE-B2 root cause remains
**NOT DETERMINED**; new findings must not be retroactively asserted as its cause.

## Integrated QA path

`backend/qa/colab_qa_run.py` now connects the validator to one QA run:

1. Consume explicit `UploadEvidence` (verified/hash/size/counts); no upload occurs.
2. If upload evidence passes, ask the injected transport for one owned readback,
   with a 20-second timeout and a default 2 MiB response cap. Never retry.
3. Validate response and retain the safe readback receipt.
4. Invoke file cleanup, then Runtime cleanup independently, even on readback error.
5. Compute the final verdict and pass only `QADiagnostics.snapshot()` to the
   injected result writer. Writer failure raises a fixed redacted error after
   both cleanup callbacks. It is not reported as a successful completed run.

`checks(snapshot)` exposes four separate results:

- `PRODUCT_UPLOAD_VERIFIED`: verified + SHA256 + size + all chunks acknowledged.
- `QA_READBACK_PASSED`: the separate full-byte readback result.
- `QA_FILE_CLEANUP_CONFIRMED`: explicit file and run-directory absence evidence.
- `QA_RUNTIME_CLEANUP_CONFIRMED`: DELETE confirmation, GET/list absence and
  durable ownership CLEANED evidence.

Final PASS requires all four. One PASS never grants another. Missing evidence
is NOT VERIFIED and prevents final PASS. Bare HTTP 200, `True`, `None` or a
`CLEANED` string is not accepted as cleanup evidence. Explicit false evidence
is FAIL; incomplete evidence is UNCONFIRMED. The runtime contract never grants
permission to delete any existing unrelated Runtime.

The updated `python -m qa.colab_readback_fixture` (run from `backend`) executes
this entire path on **synthetic** 662,508-byte content with 11 mocked Chunk ACKs
and mocked cleanup confirmations. Its PASS is an offline simulation, not a live
upload, file deletion or Runtime cleanup. This supersedes the earlier B2A
fixture behavior; the B2A document retains the historical results.

### Transport boundary for a future separately approved run

No live HTTP adapter, OAuth loader or Runtime creator is included. A future
adapter implementing `ReadbackTransport.open_readback` must:

- Validate the approved Google account, existing ownership and this run's exact
  Runtime identity before obtaining/using connectionInfo.
- Pin the official HTTPS connectionInfo origin and the exact QA-owned Contents
  file path and GET `?content=1&format=base64`; prohibit arbitrary caller URLs.
- Send only the required proxy header, never forward OAuth Authorization to
  the proxy. Disable redirects, environment proxies and automatic retry.
- Enforce the passed timeout, bounded byte read and normal case-insensitive
  HTTP headers. It must return a context-managed byte response.
- Construct cleanup evidence from actual owned DELETE and independent
  absence/ownership observations. HTTP 200 alone is insufficient.
- Use a QA-owned output path and persist only the sanitized snapshot, never
  a transport/response/exception object. Review the adapter before executing it.

These QA contracts do not bypass or enable any product gate. Existing ignored
LIVE-B2 scripts are preserved and are **not** the new execution entry point.

## WinError 5 investigation

Historical failures occur at Python `subprocess.Popen` / `_winapi.CreateProcess`
before the PowerShell child starts: installer `_run()` and Core `observe_core()`.
This is distinct from PowerShell module-loading failure after a successful spawn.
The latter was addressed in B2A only with a process-local PS5 module search path.

LIVE-B2B uses the same local Python environment, native System32 PS5 and serial
pytest invocation (no xdist/parallel option). It observes only executable kind,
test/function, launch order, creation flags, start success and numeric WinError;
never command text, environment values or child payloads. Socket/DNS connections
are denied except local loopback needed by existing tests. Test user-data
isolation remains in the existing conftest.

Both originally affected nodes passed individual runs. The diagnostic reports
confirm Python 3.13.14 from WindowsApps, non-admin token, System32 PS5 and
creation flags 0. No global execution policy, security software, ACL, credential
or user configuration is changed. No retries or new skips are added.

The specific OS denial mechanism and any scheduling/security-policy cause are
**NOT DETERMINED**. A successful run does not prove that the old intermittent
failure is fixed. #257 only added QA/tests/docs and does not modify either PS5
fixture or the subprocess launcher; no causal link is established. Potential
environment explanations must not be presented as confirmed root causes.

Final-run observations: 33 native PS5 launch attempts, 30 started and 3 failed
with WinError 5 at launch order 1, 5 and 15 (creation flags 0, non-admin token).
Failures were Core `test_core_ps5_retains_exact_synthetic_child_exit_code`,
Core `test_core_ps5_bounded_timeout_reaps_synthetic_process_tree`, and installer
`test_nested_invocation_preserves_file_identity_and_exit_zero`. All failed
before PowerShell executed the child command. Static absence of PS5 or a
uniform denied executable is not supported by the other successful launches.
Serial invocation and changing failed nodes do not prove a parallelism cause.

A limited read-only check of the most recent 50 events per CodeIntegrity and
AppLocker EXE/DLL channel within 30 minutes found no matching PowerShell event.
That limited observation neither identifies the OS denial mechanism nor proves
security-policy compliance. No security setting was changed and no elevated
token was used. No fixture/launcher workaround is committed without a proven
cause; automatic retries/skips would conceal the observed failure.

## Final offline validation

| Check | Result |
|---|---|
| Existing QA tests | **49 PASS**, unchanged source |
| New integration/review regression tests | **47 PASS** |
| Combined QA tests | **96 PASS** with sockets denied |
| Integrated 662,508-byte / 11 Chunk simulation | PASS, exact bytes and SHA256, separate confirmed cleanup simulation |
| Backend final full suite | **NOT PASS: 1,680 PASS / 2 SKIP / 3 FAIL / 1 WARNING** |
| Earlier full suite before the final bare-CR boundary test | 1,682 PASS / 2 SKIP / 1 WARNING; retained as earlier evidence, not the final verdict |
| Original individually tested PS5 nodes | Core 1 PASS, installer 1 PASS |
| Privacy and original-file preservation | PASS in offline tests and final hash comparison |

The final full run includes all 49 + 47 QA cases passing. Its three failures
are the existing process-start WinError 5 cases above. The suite was rerun once
because the final bare-CR fix/test changed the source; no failed test is retried
until green. Logs and launch receipts are local ignored evidence only:
`tmp/live-b2b-final-full.log`, `tmp/live-b2b-full.xml`,
`tmp/live-b2b-full-launches.json`, and the separate individual/initial receipts.
The four parent defects were also reproduced directly from the parent source
in a memory-only module, with synthetic input and no network/credentials.

## LIVE-B2 RETEST boundary

Regardless of offline PASS, user LIVE approval is **NOT APPROVED** for this work.
The following require separate explicit approval and a reviewed live adapter:

- Same account/FREE/T4/ownership preflight via the official approved APIs.
- At most one new Runtime, never automatic recreation/retry on ambiguous failure.
- Contents probe first; any error stops follow-up work and enters owned cleanup.
- Work ends by 25 minutes; reserve cleanup time within the 30-minute Runtime cap.
- CUDA/GPU, pinned packages/model download and synthetic transcription only if
  separately and explicitly included in that approval.
- No real user MP3 or Drive modification, paid-resource fallback, CU purchase,
  production gate activation or merges. Preserve credentials and user data.
- Delete only the newly owned Runtime and confirm GET/list absence and durable
  CLEANED; uncertain cleanup remains a recovery blocker, never a new creation.

Cost-zero guarantee and Google policy compliance remain NOT VERIFIED. Offline
success is not policy, pricing, product readiness or release authorization.

| Readiness item | Decision |
|---|---|
| QA validator source review | BLOCKED for independent review; implementing-agent review/findings documented above |
| QA execution path integration | PASS (injected Mock flow) |
| Offline integration tests | PASS |
| Existing 49 QA tests | PASS |
| Backend full regression | NOT PASS |
| Sensitive-output blocking | PASS (offline redaction tests) |
| Runtime ownership/cleanup contract | NOT VERIFIED live; typed Mock evidence contract and independent outcomes tested |
| Existing LIVE-B2 evidence preservation | PASS |
| Cost-zero guarantee | NOT VERIFIED |
| Google policy compliance | NOT VERIFIED |
| User LIVE approval | NOT APPROVED |

**LIVE-B2 RETEST readiness: BLOCKED.** Remaining blockers are independent review,
the current full-suite WinError 5 failures, review/validation of a real owned
transport adapter, and a new explicit LIVE execution approval. Credential expiry,
current account/FREE/T4 status and real ownership were not queried in this phase.
No Runtime is recreated. Finish LIVE-B2B with STOP.
