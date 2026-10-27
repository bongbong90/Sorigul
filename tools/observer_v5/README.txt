Observer V5 candidate (#208) - NOT ACTIVATED

Purpose
  Minimal successor of the Phase B normal-user observer. The existing observer is
  pinned to one baseline file and compares entries by list position, so one new
  unrelated download shifts every later entry and HARD_STOPs. V5 keeps the same
  heartbeat/STOP file contract and changes only what is listed below.

Files
  observer-v5-common.ps1      Shared read-only helpers (UTF-8 JSON, SHA256, metadata inventory, path-keyed maps).
  build-preservation-v5.ps1   Builds a new create-new baseline from a UTF-8 spec. Any ambiguity exits 3 (HOLD).
  watch-existing-user-v5.ps1  Observer. Arguments: -BaselinePath -BaselineSha256 -StateDir [-IntervalSeconds 15].
  observer-final-gate-v5.ps1  Success gate after the watched child exits 0. Exit 0 only on a nonce-bound final PASS.
  test-observer-v5.ps1        Focused %TEMP% fixture tests. Needs -RunAsBuildPath (existing runner, loop reused via AST) and -ReportPath.

Changes versus the existing observer
  1. Baseline path and expected SHA256 are arguments; the SHA is checked before load and every cycle.
  2. Comparison is keyed by root-relative path (case-insensitive NTFS semantics), not list position.
  3. Roles: core (strict; only the existing EBWebView directory write_ticks exception), transcription
     (strict), downloads (registered entries strict; other add/modify/delete recorded, non-blocking).
     New or changed reparse entries and path collisions are blocking (HOLD).
  4. Raw diffs are written create-new under StateDir\raw before any decision; a write failure is blocking.
     Unchanged non-blocking activity is not re-recorded every cycle.
  5. OBSERVER_STOP_REQUEST.json may carry a nonce. The observer then runs a final full scan (including
     history) and either writes OBSERVER_STOPPED.json {final_verdict: PASS, nonce} and exits 0, or STOPs.
     The final gate reads PASS only after the observer has exited, so no later STOP can race the verdict.

Unchanged contract
  OBSERVER_HEARTBEAT.json keeps pid, start_ticks, sequence, at_utc (plus extra fields), replaced atomically.
  OBSERVER_STOP_REQUIRED.json is created on any blocking change; exit 5 (change) / 6 (failure).

Launch (Windows PowerShell 5.1, execution policy unchanged)
  powershell.exe -NoProfile -NonInteractive -Command "$t=$null;$e=$null;$a=[Management.Automation.Language.Parser]::ParseFile('<path>\watch-existing-user-v5.ps1',[ref]$t,[ref]$e);& $a.GetScriptBlock() -BaselinePath '<v5>' -BaselineSha256 '<sha>' -StateDir '<dir>'"

Limits
  Content is hashed only for top-level hash_names (settings.json, jobs.json) and preserved files. Every other
  file (media, nested core files, registered SRT/TXT/JSON) is checked by metadata (size, write/creation time,
  attributes) and, for registered Downloads entries, NTFS file id: an in-place edit that keeps the size and
  restores the write time is not detected. Changes that revert between two polls are outside the guarantee.
  History is hashed at start and at the final scan only. Reparse directories (e.g. cloud-file placeholders)
  are recorded but not traversed. Every cycle hashes all preserved files; the cycle must stay well below the
  runner's 90 s heartbeat limit (measure before use). Activation for a real build needs separate approval.
