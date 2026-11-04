# #59 Windows runner capability probe

## Authorized second diagnostic run (this branch)

Branch `qa/59-webview2-input-diagnostic-once` starts from the immutable original
QA HEAD `94d5ec5da722c7ee0d8f917b029eba167fe34c7b`. Original run `41813116291`,
attempt 1, its workflow and original QA branch remain unchanged. The historical
sections below describe that baseline. This branch runs only the new
`.github/workflows/qa59-webview2-diagnostic.yml`, at branch creation push, exact
repository/ref, non-forced/before-zero and attempt 1. The PowerShell context guard
also names this branch. Do not publish the remote branch before the final reviewed
commit: the first push must contain the entire implementation. No automatic rerun.

This adds diagnostics, not a repair: the Name-only UIAutomation selector, 30 polls
at 200 ms, real native mouse input, 750 ms callback sampling and all WebView2
security settings/dependency versions remain unchanged. The normal inline HTML
adds a button ID (no visual/selector change), document-ready telemetry and an
actual-click observation alongside the original trusted legacy message. No
automation-side JavaScript call, dispatchEvent, InvokePattern, driver or IPC input.

`WebDiagnostics` records nullable stage booleans, bounded numeric values and at
most 16 timestamped events using a monotonic clock. Capture occurs at the original
verdict boundary; later callbacks cannot overwrite the frozen snapshot. A separate
owned `webview-diagnostic.json` is schema-whitelisted by PowerShell before printing.
Missing/partial/malformed diagnostics stay NOT VERIFIED and cannot produce PASS.
Hard timeout may prevent finally/snapshot completion; parent timeout and owned
cleanup remain the independent evidence. Exceptions export only a bounded type.

Measurements include initialization, navigation requested/starting/completed with
IsSuccess/WebErrorStatus/navigation IDs, DOMContentLoaded, same-document readyState
and button existence, UIA candidate/ControlType/rectangle/offscreen, view focus and
foreground at input, cursor and SendInput attempted/result/count/size/error code,
and message counts/kind/source+nonce match/trust. Native inputs that were skipped
stay unmeasured, with a reason. UIA found means the expected Name candidate was
observed; the final UIA BUTTON FOUND verdict additionally requires Button type,
usable visible rectangle and successful completion of the lookup.

No raw message, URI, nonce, UIA tree, screenshot, profile, command line or environment
is emitted. Coordinates belong to the synthetic element and are finite/bounded.
Message-kind counters distinguish document-ready and click-observed; source and
nonce are exposed only as match booleans. Legacy payload-match is any observed
legacy match; legacy source-match is measured only for the matching legacy payload.
No legacy payload observed leaves source-match unknown. Message count zero at a
normal completed sampling point is measured failure; unvisited stages stay null.
SendInput return 2 means insertion into the OS input stream, not DOM delivery.
Win32 last-error cannot establish or exclude UIPI as a cause.

The legacy `clicked && trustedClick` is retained independently. Diagnostic PASS
requires it plus navigation success/DOM navigation-ID agreement, same-document
ready evidence, visible Button/rectangle, SendInput return 2 and a matching-source,
matching-nonce click observation with event.isTrusted=true. A document-ready or
untrusted message can never set legacy trust or interaction PASS. A safe host exit
does not mean WebView interaction PASS. ROOT CAUSE stays NOT VERIFIED in the raw
report pending evidence analysis; a later success cannot diagnose the first run.

Standard public GitHub-hosted `windows-2022`, one job/concurrency 1, 15 minutes,
contents:read, same SHA-pinned checkout and no persisted credentials. Repository
visibility and current public standard compute free policy are checked before
push. No new action, Secrets/PAT, cache/artifact/Release/Packages, billing settings,
runtime/driver installation or product/MSI use. Public logs keep the existing
selected OS/version/resource fields plus the synthetic diagnostic schema; GitHub's
own setup/checkout logs can disclose disposable runner paths. No retention changes.

Only WebProbe.cs, ProbeHost.cs, Invoke-Probe.ps1, this README and the new workflow
are changed relative to the original QA HEAD. OwnedJob and product code are not
changed. #216 and #217 remain Draft/unmerged. #59 installed acceptance BLOCKED,
#47 PASS / #48 BLOCKED / STUDY USE READY = NO remain unchanged regardless of probe.

Primary references: https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/navigation-events
and https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput
and https://docs.github.com/en/billing/concepts/product-billing/github-actions

This QA-only harness uses no Sorigul executable, MSI, runtime, user data or product build.
Base: Integration `257e61e0fddc6b1fb0f83a97f0c9fd2300c4adbf`.
Product PR #216 remains draft/unmerged at `890364e21a4e80d2ff5185332834b4dbb67aeb01`.

## One execution boundary

The workflow listens only to pushes on `qa/59-windows-runner-probe` that change its
own workflow file. The sole job additionally requires branch creation, a non-forced
push, and run attempt 1. Later commits and reruns cannot execute the probe job.
Do not recreate this branch or change these guards to retry without new approval.
The first push containing the workflow starts the one authorized execution;
complete the local review before pushing. No merge into Integration/main.

Standard GitHub-hosted `windows-2022`, one job, concurrency group 1, 15 minute
maximum. Only `contents: read`; no repository secrets, PAT, services, artifacts,
caches, Releases, Packages, settings changes or paid runner selection.

## Dependencies reviewed before push

- Official `actions/checkout` v4.2.2, pinned to
  `11bd71901bbe5b1630ceea73d27597364c9af683`; credentials are not persisted.
  Sparse checkout selects the QA harness; no product executable is run.
  Source: https://github.com/actions/checkout/tree/11bd71901bbe5b1630ceea73d27597364c9af683
- Official Microsoft WebView2 SDK NuGet `1.0.2903.40` (SDK files only; no installer).
  Source: https://www.nuget.org/packages/Microsoft.Web.WebView2/1.0.2903.40
  Download: https://api.nuget.org/v3-flatcontainer/microsoft.web.webview2/1.0.2903.40/microsoft.web.webview2.1.0.2903.40.nupkg
  SHA256: `EF128016DD1E51C59178C827ED5B8AA3322C57AFA8675D930F8109505542AD74`.
  The x64 loader must also have a valid Microsoft Corporation Authenticode signature.
  No runtime or driver is downloaded or installed. Preparation failure leaves
  WebView2 NOT VERIFIED while the independent GUI/tray host remains testable.
- .NET Framework compiler, WinForms, UIAutomation and Windows native APIs supplied
  by the image. No remote script execution or additional package restore.

## Evidence and verdicts

`GUI SESSION ACCESS`: nonzero interactive session, input desktop, Explorer in the
same session, foreground control, UIAutomation-discovered synthetic button and
actual OS mouse input received by the WinForms click handler are all required.
No proven desktop means GUI FAIL and both dependent paths NOT VERIFIED/BLOCKED.

`SYNTHETIC WEBVIEW2 INTERACTION`: creates a real WebView2 control with a fresh
synthetic profile, navigates to inline content with restrictive CSP, discovers
the HTML button using UIAutomation and uses native SendInput. PASS requires the
button's trusted click to reach the native WebMessage handler. Registry/file
inventory and browser version alone never confer GUI PASS. Version evidence
includes installed runtime files and the actual instantiated runtime when reached.
Edge WebDriver version is inventory only; first-three-component comparison is
reported where possible, but driver session compatibility stays NOT VERIFIED.
The chosen interaction path uses no driver/CDP/debug port or security bypass.

`SYNTHETIC TRAY INTERACTION`: creates a synthetic NotifyIcon, finds its displayed
notification-area or overflow icon, right-clicks with native input, discovers the
synthetic menu item and clicks it. PASS requires the actual menu callback.
Failure remains FAIL/BLOCKED with no direct handler/API fallback. Normal host
process exit and any forced descendant cleanup are reported separately.

The host is created suspended and assigned to a dedicated kill-on-close Job
Object before running. Only that job can be terminated. Root execution has a
150 second deadline; child job counts and owned TCP listeners/UDP endpoints are
checked at the end. Provider errors cannot count as zero endpoints. No automatic
rerun, environment repair or manual substitute for a failed interaction.

## Public logging review

This repository and its Actions logs/job summary are public. GitHub's own setup,
checkout and teardown logs may expose disposable runner workspace paths and
image metadata. The harness prints only selected OS/image/version/resource
fields, synthetic booleans/verdicts, exception type names and owned process/port
counts; it does not print personal computer paths, user profiles, raw process
command lines, environment dumps, credentials, screenshots or product data.
Compiler and download diagnostics are captured rather than published. No artifact
upload. The repository's configured log retention is not changed or claimed.

All three capability verdicts must PASS, normal root exit and cleanup must be
verified, for technical feasibility READY. This never changes installed product
acceptance: #59 remains BLOCKED, #47 PASS / #48 BLOCKED / STUDY USE READY = NO.
NEXT GATE: separate approval of the same MSI's public suitability, delivery and
installation; actual product buttons, Backend restart and tray exit require that
later installed test.

References: https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax
and https://learn.microsoft.com/en-us/microsoft-edge/webview2/get-started/winforms
