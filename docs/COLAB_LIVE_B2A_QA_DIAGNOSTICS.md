# LIVE-B2A: offline QA diagnostics (#256)

Parent: PR #255, `760c62aef68b08ace48a0820d440a639c70b4e91`.
This work makes no Google/OAuth/Jupyter requests and creates or deletes no Runtime.
Product services, scopes, authorizers, gates and DEFAULT OFF are unchanged.

## Preserved evidence and findings

The original ignored files remain byte-identical: `tmp/live-b2-20261115-result.json`,
`tmp/live-b2-20261115-summary.json`, `tmp/live_b2_20261115.py`,
`tmp/live_b2_steps_20261115.py`, and the single-create attempt marker.
They are not copied into Git. User helper files and OAuth artifacts are also excluded.

The observed uploader result is **VERIFIED / CONTENT_SHA256**, 11/11 chunk ACKs,
662,508 bytes. First PUT was 201, intermediate/final PUTs 200. This successful
product-upload evidence is independent of the additional QA full-byte readback.
Do not downgrade that evidence or close #233 based on this investigation.

The historical failing function is bounded to the additional readback block of
`run()` in the ignored steps script, following `probe.upload()` and before the
comparison flags are assigned. The report contains its additional GET 200, but no
`contents_readback_bytes_equal`, `contents_readback_sha256_equal` or
`contents_readback_size_equal` fields. The `finally` file-cleanup report is present.
No provisioning states or transcription outputs exist.

The historical request was GET of the owned Contents path with
`?content=1&format=base64`, using the Runtime proxy token header, without OAuth
Authorization, through an HTTPS opener with redirects and environment proxies
disabled. The code read at most 2 MiB + 1 byte with a 20-second timeout. Neither
the private URL/header nor the raw response is reproduced here.

The expected JSON model had matching `path`, `type=file`, `format=base64`,
string `content`, and final `size`. The old code called `json.loads(raw)`, then
`base64.b64decode(model["content"], validate=True)`, then compared full bytes,
locally computed SHA256 values and sizes. An HTTP 200 alone does not establish
that this model or its content was valid. There is no retained raw model from
this GET; PUT model-key summaries cannot establish the readback structure.

**Historical root cause: NOT DETERMINED.** Exact failed line and exception type
are unavailable. Possible unclassified operations include body read/response
close, JSON parsing, non-object model access, missing content, or Base64 decode.
Explicit size-limit/model mismatch errors had dedicated normalized strings, but
the stored failure is generic. No evidence proves the 2 MiB limit was exceeded.

**Confirmed QA defects:**

- The outer catch discarded unknown exception classes into `QA_STAGE_FAILED`;
  it retained neither the substage nor field-validation outcomes.
- `jupyter_accessed` was initialized false and never updated by the request
  guard. Recorded Jupyter HTTP exchanges prove that historical value stale.
- Strict decoding rejects LF/CRLF-wrapped Base64. The exact old expression
  raises `binascii.Error` on a synthetic `base64.encodebytes` payload. This is
  a **reproduced candidate**, not proof the actual Colab response was wrapped.
- File cleanup retained only a boolean. It could not distinguish an unresolved
  listing, failed deletion or another reason. The later owned Runtime deletion
  was independently confirmed by GET 404/list absence/durable CLEANED.

## QA-only replacement helper

`backend/qa/colab_readback.py` supplies a bounded, single-attempt validator and
redacted receipts. No product module imports it. It has no network client,
credential access, Runtime operation, retry or authorization bypass.

The caller supplies a context-manager response factory from its separately
approved, owned-origin/path-pinned transport. That transport must enforce the
existing GET query, redirect prohibition, scope and account restrictions. Do not
run the preserved old harness or treat this helper as a live execution approval.

The receipt contains fixed stage IDs, normalized error codes, allowlisted
exception categories, HTTP status, bounded byte count and boolean outcomes for
JSON/model fields, Base64, final size, computed SHA256 and exact bytes. Only CR/LF
are removed before strict Base64 validation; arbitrary junk remains rejected.
HTTP errors, timeout, incomplete body, malformed JSON and excess size are distinct.
Unknown exception class names and all exception strings are omitted.

`jupyter_request_attempted` is set before opening; `jupyter_accessed` is set on an
observed response, including HTTP errors. Neither implies readback PASS. Existing
upload verification is kept in separate fields and never changed by readback.

Use `record_cleanup` in the caller's `finally` for both file and Runtime cleanup.
Each callback must return literal `True` only after its own required confirmations;
Runtime confirmation includes deletion, GET/list absence and durable CLEANED.
Cleanup failure is recorded separately and cannot overwrite the primary failure.
No raw cleanup result, file path or exception string enters the receipt.
Persist `diagnostics.snapshot()` in the QA-owned result through the caller's safe
writer. Do not serialize response objects, headers, URLs, raw models or media.

Example integration outline (not an executable live runner):

```python
diagnostics = QADiagnostics(
    upload_verified=upload_verified,
    upload_content_sha256_verified=upload_hash_verified,
)
try:
    passed = verify_readback(
        approved_owned_response_factory,
        expected=synthetic_bytes,
        expected_path=owned_remote_path,
        diagnostics=diagnostics,
    )
    # Continue only if passed AND all required prior checks succeeded.
finally:
    record_cleanup(diagnostics, runtime=False, cleanup=confirmed_file_cleanup)
    record_cleanup(diagnostics, runtime=True, cleanup=confirmed_owned_runtime_cleanup)
    persist_redacted_receipt(diagnostics.snapshot())
```

## Offline verification and live boundary

From `backend`, `python -m qa.colab_readback_fixture` validates a generated binary
payload of 662,508 bytes with line-wrapped Base64 and prints a safe receipt.
It performs no upload and claims no real file/Runtime cleanup or upload PASS.
Tests in `backend/tests/test_colab_qa_readback.py` additionally deny sockets and
cover normal/wrapped Base64, missing fields, invalid format/Base64/JSON, sizes,
computed hash mismatch, HTTP errors, timeouts, incomplete body, bounds, flags,
redaction and cleanup error isolation. No original MP3 is used by these tests.

No product defect has been reproduced; only QA/test/docs changes are justified.
This helper is ready for integration into a separately reviewed and approved live
harness; no corrected end-to-end live run has been executed. Before a future run,
explicit approval must cover account/subscription/ownership preflight, at most
one new Runtime, mandatory Contents probe, conditional pinned CUDA preparation
and synthetic transcription, a 25-minute work/30-minute Runtime bound, cleanup
and final observations. Existing user files/credentials, gates and DEFAULT OFF
remain protected. Cost-zero guarantee, policy compliance and Drive project
separation remain NOT VERIFIED. LIVE-B2A finishes with STOP.

## Validation record (2026-11-15)

- New synthetic QA tests: **49 passed** with socket connections forbidden.
- Synthetic 662,508-byte CLI fixture: PASS for size, computed SHA256 and exact
  bytes; no network, media upload or cleanup claim.
- Backend full regression, allowing only local loopback and denying external
  DNS/connections: **1,634 passed, 2 skipped, 1 failed, 1 error, 1 warning**.
  The failure/error occur while starting existing PowerShell 5 child processes
  (`PermissionError / WinError 5`), before their assertions execute.
- Rechecked both affected existing files: **19 passed, 1 failed**. The original
  two affected cases passed; another child-process launch hit the same WinError 5.
  This is a remaining intermittent execution-environment limitation, not a
  clean full-suite PASS. No retry was added to product or test logic.
- An earlier full run had 1,629 passed / 2 skipped / 7 setup errors from inherited
  PowerShell 7 module paths. Narrowing `PSModulePath` for the Python child only
  resolved that module-loading problem. No global policy/configuration changed.
  An initial overbroad socket block was also stopped because it prevented the
  Windows event loop's required loopback traffic.
- Original evidence, private QA scripts, user helpers and OAuth artifacts:
  preservation hashes match. Diff contains QA/tests/docs only.

Ignored local regression receipts: `tmp/live-b2a-backend-final.xml`,
`tmp/live-b2a-backend-final.log`, `tmp/live-b2a-ps5-retry.xml`.
The remaining Windows process-launch issue must not be hidden by claiming the
entire regression suite passed.
