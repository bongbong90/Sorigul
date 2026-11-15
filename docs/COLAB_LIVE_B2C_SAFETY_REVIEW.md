# LIVE-B2C: independent review and transport safety preflight (#260)

Parent #259 / `705cfd5075898d50ffe72e0136fac1b29154cc38` and its branch were
verified before work. #255, #257 and #259 remained OPEN, Draft and unmerged.
Only the five expected user helper files were untracked. Original LIVE-B2/A/B
evidence/scripts, helpers and OAuth artifacts were hashed before work and
confirmed unchanged afterward; none is included in Git.

## Independent reviewer and scope

Reviewer: separate AI reviewer `/root/independent_review`, launched with **no
implementation conversation history**. This is an AI technical review, not a
human approval. The implementing agent's prior self-review was not reused.

The reviewer read the complete QA/test/docs changes from #257 and #259, the
current correction diff, and product Jupyter client/file-transfer and Runtime
client/ownership services. It did not read credentials, user files or ignored
original evidence; it made no network calls, repository edits or Git mutations.
The reviewer directly ran 13 memory-only, socket/DNS-denied follow-up checks.
It did not claim to rerun the implementing agent's full pytest suite.

Final disposition: **independent QA source / Mock transport design review PASS**;
all reported important defects were corrected and no additional important defect
was found within the stated serial trusted-coordinator contract. LIVE observer,
lease, cleanup evidence, persistence and hard deadline integration remain
BLOCKED/unverified. This condition is part of the review, not an approval to run.

## Findings and minimal corrections

| Finding | Classification | Reproduction / impact / correction |
|---|---|---|
| General response close masks the primary error | CONFIRMED DEFECT in parent QA | HTTP 403 or body TimeoutError plus `__exit__` OSError changes the primary classification. `_response_scope` now preserves the primary error, separately marks close failure and rejects close-only failure. The reviewer reproduced it and checked the fix. |
| Cancellation masked by result-save failure | CONFIRMED DEFECT in parent QA | Parent `run_qa` replaces file-cleanup KeyboardInterrupt with QAResultSaveError if writer fails. Implementer reproduced exact parent code in memory. Explicit internal pending-exception tracking preserves the original cancellation while Runtime cleanup and save are attempted. |
| Ambient caller exception mistaken for internal cancellation | CONFIRMED DEFECT in intermediate correction | Reviewer reproduced a caller's handled ValueError reappearing on writer failure. Removed ambient `sys.exc_info()` inference from orchestration; only exceptions actually leaving its body/cleanup are tracked. Regression checks a caller `except` block. |
| Transport sanitization loses incomplete/transport categories | CONFIRMED DEFECT in intermediate adapter | Reviewer reproduced IncompleteRead becoming ownership-blocked. Safe exceptions now preserve IncompleteRead, timeout, URLError/OSError and HTTP status categories without raw message/partial bytes/URLs. |
| HTTPError close evidence lost during sanitization | CONFIRMED DEFECT in intermediate adapter | Reviewer reproduced close failure becoming false. Carry a boolean only and OR it with existing scope-close evidence. Regression includes simultaneous body HTTPError and context close failure. |
| Base64, size, SHA256, exact byte checks and stale state | NO ISSUE FOUND | LF/CRLF accepted, bare CR/junk rejected, bool sizes excluded; SHA256 and exact bytes remain separate. Each orchestration run has fresh diagnostics. |
| Snapshot and separate upload/readback/cleanup decisions | NO ISSUE FOUND | Primitive/enum allowlists omit private fields and arbitrary exception strings. Existing successful upload evidence is never replaced by a failed extra QA readback. |
| Actual observer and cleanup evidence bridge | POTENTIAL RISK / BLOCKED | Typed facts alone cannot prove real ownership. A trusted coordinator must obtain actual observations under the native lease/store discipline; none was executed here. |
| Storage and overall deadlines | POTENTIAL RISK / BLOCKED | A writer must atomically/durably publish a QA-owned result, with no acceptance of a PASS candidate when writer fails. Socket timeout is not a total work deadline. |

These findings do **not** determine the historical LIVE-B2 `QA_STAGE_FAILED`
cause. That remains NOT DETERMINED. Existing 11 Chunk / 662,508-byte /
`VERIFIED / CONTENT_SHA256` upload evidence remains intact. Product code is
unchanged; no actual product defect was established by these QA findings.

## QA-only adapter and trust boundary

`backend/qa/colab_owned_readback.py` adds a readback-only adapter. It has no OAuth
loader, Runtime creator/deleter, model execution or default live entry point.
The HTTP wire is explicitly injected; tests supply fake responses/openers only.

Before constructing or opening the adapter, a separately approved **trusted
serial coordinator** must provide an observation derived from the native
ownership store, verified account and official owned Runtime API, together with
the current transfer's OWNED record and connection match. Caller/UI/settings
labels or arbitrary JSON must never be accepted as that observer. The coordinator
must bind the expected new execution ID and approved canonical connection base.

The adapter pins execution ID, request ID, account binding, Runtime name, file
index/size/SHA256, origin/base and exact generated Contents file path. A fresh
observation is checked at open: ACTIVE_OWNED, matching account/Runtime/transfer,
unexpired connection, VERIFIED/CONTENT_SHA256 file, acknowledged chunks and no
remote deletion. Changed bindings block before HTTP; an ambiguous attempt is
consumed, never retried. No broader path or unrelated existing Runtime is used.

The only request is GET of that exact path with `?content=1&format=base64`.
The explicit native wire constructs only the proxy-token header, not OAuth
Authorization. TLS hostname/certificate checks are enabled; environment proxies
and redirects are disabled. Changed response URL is also rejected. Response
read is one bounded call up to 2 MiB + 1; raw wire values and errors are private.

`timeout <= 20` is a **socket-operation/inactivity timeout**, not a guaranteed
20-second wall-clock request deadline. A separately reviewed coordinator must
enforce 25-minute work and 30-minute Runtime hard deadlines, cancel subsequent
work and reserve cleanup time. Such an actual coordinator was not run/validated
here; Mock timeout arguments do not establish the hard deadline.

## Cleanup, recovery and persistence limits

The adapter implements **no delete**. It never turns product cleanup receipts
into automatic True evidence. Product file cleanup treats DELETE 204/404 as
success without independent file/directory absence GET; native Runtime cleanup
checkpoints CLEANED on DELETE without providing the extra QA GET/list proof.
Those are product contracts, not newly asserted product defects.

The future QA coordinator must preserve this run's exact owned identities, then
obtain independent file/directory absence and Runtime DELETE/GET/list absence,
same-account and durable CLEANED observations before confirming QA evidence.
Uncertainty keeps recovery required/BLOCKED and cannot authorize another create.
No existing other Runtime or user/Drive file may be removed.

Ordinary errors and cancellation preserve primary failure information. Nested
finally blocks attempt Runtime cleanup and safe persistence even after file
cleanup cancellation. Writer failure is a fixed redacted error unless preserving
an already propagating internal cancellation. A PASS snapshot is a candidate
until the trusted writer successfully commits it; no report may treat partial
output or a failed/cancelled writer as overall success. Only sanitized snapshots
are passed to the writer, never transport/response/exception objects.

## Tests and WinError 5 classification

- Existing QA tests unchanged: **96 PASS** (49 + 47).
- New safety Mock tests: **42 PASS**. Combined QA: **138 PASS**.
- Reviewer independent memory checks: **13 PASS**, no full-suite claim.
- Final Backend suite, run once after source review/fixes: **1,725 PASS /
  2 SKIP / 1 existing WARNING**, zero failures/errors, 131.03 seconds.
- Existing test user-data isolation and external DNS/socket block were active;
  loopback was allowed for existing local tests. No test retry, removal, new skip
  or product-launch workaround was added.
- Final diagnostic: **33/33** native System32 PS5 starts succeeded, non-admin
  token, serial pytest, native PS5 module path in the child process only.

WinError 5 root classification: **NOT DETERMINED**, neither CONFIRMED ENVIRONMENT
FAILURE nor CONFIRMED CODE DEFECT. Historical B2B launch orders 1/5/15 failed
before the child started; the failure was not reproduced in this final run.
Current passing tests do not prove the intermittent issue fixed.

Limited experiment: one read-only PS5 launch through WindowsApps Python and one
through the existing venv Python both exited zero (Python 3.13.14). This is not
a separately installed interpreter/control-machine comparison and cannot prove
or eliminate WindowsApps as a cause. Existing subprocess calls inherit the
workspace cwd, and were not changed; static/native executable paths, launch
flags and serial order observations do not identify an OS denial mechanism.
No administrator elevation, global policy/security/ACL change or unconditional
retry was used. Prior logs are retained rather than replaced with a PASS claim.

Local ignored receipts: `tmp/live-b2c-full.log`, `tmp/live-b2c-full.xml`,
`tmp/live-b2c-full-launches.json`, `tmp/live-b2c-limited-process-check.json` and
preservation/reproduction records. They are not committed.

## LIVE-B2 RETEST gate reassessment

| Gate | Decision |
|---|---|
| Independent code review | PASS, separate AI reviewer and stated limits |
| Discovered important QA defects resolved | PASS within reviewed scope |
| Existing QA 96 tests | PASS |
| New security Mock tests | PASS, 42 |
| Backend full regression | PASS for this recorded run |
| WinError 5 root classification | NOT DETERMINED |
| Actual transport design review | BLOCKED for complete LIVE integration; readback adapter/Mock design reviewed PASS |
| Actual transport execution | NOT RUN |
| User information / original evidence preservation | PASS |
| Cost-zero guarantee | NOT VERIFIED |
| Google policy compliance | NOT VERIFIED |
| User LIVE execution approval | NOT APPROVED |

**Overall readiness remains BLOCKED.** The actual trusted observer/lease,
independent cleanup/absence and durable proof bridge, atomic durable writer and
hard-deadline coordinator require review/validation before a real run. Current
account/FREE/T4/credential expiry were not queried here. Historical WinError 5
remains unresolved despite this passing full regression.

Any future LIVE approval must explicitly cover approved-account preflight, at
most one new Runtime, Contents first, stop-and-clean on failure/ownership
uncertainty, no automatic recreation, 25-minute work/30-minute Runtime limit,
and cleanup of only the newly owned Runtime with absence confirmation. GPU,
packages/model and synthetic transcription require explicit inclusion. Real
user MP3/Drive modification, paid fallback, production gate activation and PR
merges remain prohibited. COST/POLICY conditions and DEFAULT OFF are unchanged.
LIVE-B2C ends with STOP; it grants no real execution or release approval.
