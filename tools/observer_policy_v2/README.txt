Observer Policy V2 -- STEP 1-A + STEP 1-C fixture implementation
===================================================

Related: GitHub issues #208 and #210. No issue is closed by this tooling.

This standalone successor preserves the external Observer/runner behavior at
the decision and control boundaries without publishing private operating
scripts, credentials, profile paths, historical snapshots or personal data.
The PowerShell entry points require native Windows PowerShell 5.1 and an
explicit Python 3.11+ executable. Only the Python standard library is used.

Scope and activation boundary
-----------------------------
All executable entry points require a random, marked fixture immediately
under the current OS TEMP directory. The observed general/protected/webview
roots and sibling audit directory are fixed inside that fixture. No account
switching, product imports, Runtime, installer, transcription or build adapter
is provided. Production activation requires a separately approved adapter,
real root/ACL/provenance mapping, tests and deployment review. These tests are
not production readiness, artifact readiness or a new Release Freeze.

Fixture creation is confined by the same boundary check used by the observer
and runner. Ancestral reparse points are rejected. Junction entries are
recorded without traversal. Missing/ambiguous file identity fails closed.

Decision behavior
-----------------
Raw ordinal metadata differences are retained against the immutable original
fixture baseline. Separate root/path differences drive policy decisions.
An accepted addition therefore remains a raw change; it is never rewritten
to raw NO_CHANGE. Committed observation state tracks admitted entries, so
their later modification/deletion stops. A stopped/partial run cannot resume.

Priority: HARD_STOP > INVESTIGATE_HOLD > WARN_RECORDED > ALLOW_RECORDED
> NO_CHANGE. Existing-entry changes/deletions stop, except for the literal
#189 EBWebView directory write_ticks-only boundary. New sensitive, reparse,
audio-registration-ambiguous or scope-unverified additions hold. Only the
baseline-pinned noncore general scope can admit plain additions, with intact
synthetic isolation and complete observation. Registered paths and sensitive
prefixes cannot qualify. Extension/name/owner SID do not provide permission.
Creator PID is unnecessary: actor is recorded as UNKNOWN. Conflicting supplied
identity/metadata still holds. Admission records bind identity and metadata;
the original baseline and canonical raw differences are never rewritten.
The fixture isolation assertion does NOT prove real-account ACL isolation.

Audit and runner behavior
-------------------------
Each observation creates new raw, decision, state and hash-chained commit
files with exclusive creation and fsync. Only heartbeat.json is a replaceable
pointer. STOP is a permanent create-new latch. Final request, candidate result
and completion use flushed staging + atomic create-new hard-link publication.
A bounded cross-process journal lock serializes commit publication and reads.
Partial transactions, audit changes or I/O failure cannot reuse permission.
The audit directory is outside observed roots, preventing self-observation.

The runner validates run ID, policy/baseline hashes, integer sequence, complete
audit chain, PID/creation identity, process liveness and heartbeat age (never
more than 90 seconds). It validates before spawning a synthetic-only child,
throughout execution, and after exit 0. A new final request nonce requires
a later committed same-run observation. The observer remains alive until
the sealed candidate and COMPLETION.json are fully validated. Candidate result
existence alone is never success. Completion binds run, nonce, final committed
sequence, snapshot and result hash; reads require an intact fresh audit chain
and no STOP/failure latch. Both sides observe data after the final nonce.
Owned-child cleanup precedes finalization. Any cleanup, observation, staging,
publication or completion-validation failure returns nonzero and latches STOP.
STOP during candidate/completion publication is checked again. Completion is
the finite success boundary; this does not claim to freeze future user actions
or prove absence of transient changes between metadata samples. A later STOP
invalidates completion for subsequent readers, without rewriting history.
Termination uses the retained Popen process handle, never a process-name
filter. The shipped synthetic child has no descendants or build commands.

Exit codes: observer 0 = controlled final handshake, 5 = HARD_STOP,
6 = observation/audit/startup failure, 7 = INVESTIGATE_HOLD.
Runner 0 requires a successful child AND confirmed final observation AND
validated completion; every failure returns 1. An individual fault-test returning
runner 1 is an expected safety result, not a failed test.

Running the approved tests
--------------------------
Use the repository's existing Python, without installing dependencies:

  <python> -B tools/observer_policy_v2/test_step1a.py
    --preservation-manifest <private-evidence>/preservation-before.json
    --report <private-evidence>/test-report-unique.json

For approved C01/C05 changes plus the full 32-test regression, use test_step1c.py
with the same arguments. It runs 13 focused tests first and stops on the first
failure. T12's two creator-evidence cases now expect ALLOW only inside pinned
noncore scope; stale metadata, sensitive roots and executable disguise still
HOLD. Prior STEP 1-A reports/commit remain historical evidence, not rewritten.
Host CPU/process-I/O counters exclude child processes; process I/O is not
physical disk throughput. Small-fixture results are not scale/performance PASS.

The preservation manifest is a private JSON list of path/sha256 records for
the original observer, runner, V1/V2, old STOPs, official bootstrap, Freeze
and original index. It is never committed. Tests hash these artifacts without
writing them. All fault injection and file mutation use synthetic TEMP data.
The suite stops at its first failed safety assertion. Keep failed reports;
do not silently repair/retry after a failure without further authorization.

The native PS5 integration uses the parser's GetScriptBlock invocation under
the existing execution policy; it does not change or bypass that policy via
an ExecutionPolicy setting. No ExecutionPolicy setting is written.

T08 derives a restricted token from the test process and grants a fresh
synthetic restricting SID read/execute on a fixture-only ACL. Native write,
directory-add and create-new attempts must return ACCESS_DENIED. No real
build account, password, account creation or machine-wide ACL is used.
T09 creates an actual TEMP junction; native symlink creation is not required.
Observation races and unavailable identity also use explicit fault injection.

Limits and rollback
-------------------
Metadata polling cannot prove absence of transient changes between samples
or same-size media mutations with restored timestamps. Only configured
synthetic settings/jobs/manifests are hashed, not general media/auth content.
The legacy operational eight-file hash scope is not a whole-Runtime audit.
The hash chain detects accidental/partial changes, not an attacker able to
rewrite all evidence and configuration as the same principal.

There is no production rollback action in STEP 1-A because nothing is
activated. Retain originals and historical baseline/STOP hashes. A future
approved deployment must stop its exact owned process, preserve new events,
restore the pinned original launcher, and read back the protected inventory.
Never delete an old STOP or reclassify it to make a run pass.
