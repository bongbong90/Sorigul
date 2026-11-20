# #48 Colab / Drive validation — 2026-11-11 KST

Base: Integration `3406c4ae57945560293fac2fc153c8e417981681`.
Branch: `fix/48-colab-drive-completion`.
Scope: #48, including its shutdown protection defect #223; tunnel limitations remain in #60.
#47 PASS / #59 PASS / #48 ACTIVE / #114 OPEN / STUDY USE READY NO.
#59 dedicated tests and installed/artifact gates were not rerun.

## Changes and reproduced defects

- Drive file and folder lookups previously selected the first duplicate. They now inspect every page (including empty pages with continuation tokens) and fail with `DRIVE_TARGET_AMBIGUOUS` before selecting an ambiguous object. File lookup excludes folders; query escaping and existing create/update behavior are covered.
- Manual/automatic uploads from different Jobs sharing a destination are serialized within the application. Waiting uploads remain registered for exit protection. This is not a distributed lock against other Drive clients.
- Job-finished callbacks observe the actual upload Futures. A FIFO task is insufficient with multiple upload workers and could start shutdown before an earlier upload finished.
- A real synthetic 300.5-second MP3 reproduced loss of the final 0.5 seconds: the old splitter skipped any tail shorter than one second. Short valid tails are now retained. Small outputs are checked for MP3 audio metadata so encoder padding that generates ID3-only output at exactly 300/600 seconds is not sent to Whisper.
- #223: an older Job's completed upload could prepare PC shutdown while a newer transcription/upload remained active. Backend polling cancels that older request; the native shutdown boundary also requires a fresh, confirmed-idle guard. Active/unknown work never invokes the executor or consumes its gate. The same terminal Job's callback/Future-return interval temporarily hides readiness without cancelling its own normal shutdown. Native HTTP inspection runs on a blocking worker.

## Validation boundaries

`backend/tests/test_48_drive_colab_integration.py` uses local HTTP on `127.0.0.1`, the real bootstrap FastAPI app, signed health/transcribe requests, real multipart parsing, synthetic sine-wave MP3s, real FFmpeg splitting/decoding, a Fake Whisper model, and a Fake Drive client. No account, GPU model inference, personal audio, production settings, or production Drive files are used.

The integration exercises Local/Colab DONE → validated TXT/JSON/SRT → actual completion callback → asynchronous Drive worker → independent persisted Drive status. Cases include opt-in OFF/ON, short and >300s input, partial success, auth-required, same-Job upload retry without retranscription, and no MP3 upload. Existing regressions cover network errors, invalid bundles, completed-chunk recovery, authentication/signatures/replay, timestamp order, classification, and queued/manual/automatic upload close guards.

STOP/CANCEL is cooperative: the current HTTP request must return or time out before its token is observed. Tests prove terminal state, no result promotion, preservation of existing bundles, and cleanup; they do not prove immediate cancellation of remote GPU work. FFmpeg preparation itself has token-aware child termination/reaping tests.

Real split/decode matrix: known duration and fallback × 0.1/300/300.5/600 seconds. The fallback segment muxer can retain a decodable padding frame; every retained output is decoded by FFmpeg in the regression. The Fake model alone would not detect invalid MP3 output.

## Test evidence

- Initial existing Drive/Colab regression: 190 PASS.
- New end-to-end test initially failed for 300.5s with upload OFF and ON, reproducing tail loss; fixed and revalidated.
- Final focused lifecycle/Drive/desktop regression: 120 PASS.
- Final full backend: **808 PASS, 2 SKIP**, 117.79s. The two existing skips are not external PASS evidence. Final new #48 module contains 49 cases.
- Additional OAuth/Colab/runner/classification regression: 198 PASS.
- Root #48 release/Colab-open contracts: 17 PASS.
- Rust shutdown tests: 6 PASS; real shutdown executor is never invoked by tests.
- Rust close-guard tests: 15 PASS.
- Frontend lint/typecheck, Rust fmt/clippy (`--locked --all-targets -- -D warnings`, offline): PASS.
- Full backend command: from `backend`, `../venv/Scripts/python.exe -m pytest tests -q`, using the canonical runner's process-only cleanup of inherited `PSModulePath` and `PSExecutionPolicyPreference`. Source/commit identity is recorded in PR/#48 readback.
- An initial broad invocation had 7 PowerShell fixture setup errors because inherited PS7 module paths prevented PS5 module loading. Rerunning with the canonical runner's process-only module/policy environment cleanup resolved all 7; no product/OS policy change was made. Existing FastAPI/httpx deprecation and linker informational warnings are retained.

Independent reviewer found the header-only tail and #223 shutdown races. Both were fixed; final independent review PASS, no remaining P1/P2 findings. Reviewer independently ran 8 split/decode cases, 4 cross-Job shutdown cases, 1 native Fake executor case, and 2 same-Job/concurrency cases. This is an independent agent source review, not a GitHub human approval or a LIVE certification.

## External / zero-cost gate — HOLD

User explicitly chose **external validation deferred; finish local/Mock and Git work** on 2026-11-11. No Google OAuth flow, Drive account API call, Colab account session, tunnel launch, external MP3 transfer, or paid service was executed in this work.

- GOOGLE DRIVE LIVE: NOT RUN. Needs explicit OAuth consent to the current full `https://www.googleapis.com/auth/drive` restricted scope and an isolated, newly created test root. Existing Drive files must not be updated/deleted. Mock create/update tests do not authorize live updates to existing files.
- COLAB LIVE: NOT RUN. Needs account/session evidence of zero paid compute-unit consumption, a compatible use permitted by current service terms, and explicit synthetic-audio transfer approval. No paid fallback or anti-abuse workaround is permitted.
- ZERO-COST GATE: local/Mock incurred no Google/Colab service charges; external gate remains `PENDING_ZERO_COST_EXTERNAL_VALIDATION`. A Drive connector connection would not prove the desktop application's OAuth works.

Official sources checked on 2026-11-11:

- [Google Drive API scopes](https://developers.google.com/workspace/drive/api/guides/api-specific-auth): current full Drive scope is restricted and broader than per-file access.
- [Drive API usage limits](https://developers.google.com/workspace/drive/api/guides/limits): standard API use has no additional charge; account storage/quota conditions still require verification before live execution.
- [Colab FAQ](https://research.google.com/colaboratory/faq.html): free resources are not guaranteed, and free managed runtimes restrict primarily bypassing the notebook through a web UI. Whether Sorigul's desktop-to-tunnel operating mode satisfies the permitted interactive-use boundary is unresolved; this is an external policy gate, not a Mock failure or permission to use a paid workaround. Track in #60.

## Readiness

Source/Mock completion and external acceptance are separate. The changes can be reviewed for Integration merge after final checks and PR readback. #48 stays ACTIVE while LIVE/zero-cost/terms evidence is missing. No main merge, deployment, Release Freeze, installed artifact build, or #114 acceptance is claimed.

The repository-wide canonical release preflight includes #59/full artifact preparation; the user's explicit instruction not to revalidate #59 and this task's source/Mock scope take precedence. No new #113 artifact session is started. Any later artifact gate must use its canonical exact-HEAD preflight/probe/freeze procedure.
