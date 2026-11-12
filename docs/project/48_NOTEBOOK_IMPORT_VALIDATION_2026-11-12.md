# #48 Notebook / result Import — 2026-11-12 KST

Base Integration: `58d734a64b9f8a7ec3ab4ba82970c1a821ca1158`.
Work branch: `feature/48-notebook-result-import`.
Existing Drive OAuth/CREATE-only LIVE PASS and #224 merge remain accepted; neither was rerun.

## Implementation

- User-operated `colab/Sorigul_large_v3_notebook.ipynb`: explicit free GPU confirmation, exact source package upload, `faster-whisper==1.2.1` large-v3 load, actual CTranslate2 device/compute_type verification, approved MP3 SHA-256 check, one inference, validated results and manual download. No server, tunnel, proxy, Drive mount, OAuth or background control.
- Reuses bootstrap `select_runtime_identity` and extracted `transcribe_model` (Korean, beam_size=5, word_timestamps=False), common transcription schema, timestamp formatter and Bundle writer. CPU identity stays supported by the source contract, but this LIVE Notebook stops when free CUDA is absent.
- Result ZIP has exactly TXT/JSON/SRT plus a manifest, never MP3. Source name/size/SHA-256/duration bind it to the local source. Per-file checksums, strict UTF-8, ordered bounded timestamps, whole-text/segment consistency and canonical SRT are validated. Source changes during inference are rejected.
- Folders UI selects the original MP3 and uploads the result ZIP to the local API using opaque scan/item IDs. Request bytes and decompressed bytes are bounded. No arbitrary archive extraction or caller-supplied destination path is used.
- Import publishes CREATE-only hard links on the target volume, refuses even partial existing results, rolls back only files it owns, and persists a dedicated DONE `notebook_import` Job. It does not invoke an engine or the automatic completion/upload callback and cannot trigger completed-job PC shutdown.
- Existing scanner/TXT preview displays the imported results. Existing Import Job lookup checks current source/result identity before restoring the manual upload controls.
- Drive is a separate button and uses the existing asynchronous execution/upload service. Repeated requests for a completed Import Job do not re-upload. At worker execution, source/result checksums are revalidated and an immutable bounded temporary result snapshot is uploaded, including generic retry paths. Failed uploads preserve local DONE; explicit retry reuses the same Job. No MP3 is sent to Drive.

## Local verification

Unit/integration tests use synthetic MP3 bytes, Fake models and Fake Drive. Covered cases include Bundle roundtrip, original identity mismatch, invalid UTF-8/SRT/timestamps/order/runtime, path traversal/extra/missing/oversize ZIP, existing outputs, racing CREATE conflict, persistence failure rollback, original changes during inference, large existing results, queued result changes and generic retry, snapshot integrity during concurrent edits, HTTP Import/Drive state separation and idempotence.

The production UI component is exercised in a local hook harness: explicit import vs upload, DONE deduplication, unknown POST outcome requiring status check, and explicit recovery when the backend confirms no request. Notebook cells are syntax checked with no stored execution/output; the single inference guard and absence of server/polling calls are checked.

Independent reviewer reproduced and we fixed original identity drift, unbounded result hashing, queued upload identity drift and UI lost-request recovery. Final independent source review: **PASS, no remaining P1/P2 findings**; independent Notebook/contracts tests 24 PASS and production UI harness PASS. Exact final full regression results and commit/PR identity are recorded in #48/PR readback.

Final local results: **backend 830 PASS / 2 existing SKIP**, 171.40s; focused lifecycle/Notebook/UI 83 PASS; Notebook/Import and related root contracts 42 PASS (overlap backend count); frontend lint/typecheck/production build PASS; diff checks PASS. Existing FastAPI/httpx deprecation warning retained. No #59 dedicated test, installed/artifact gate, or accepted Drive LIVE regression was run.

Own Korean speech was generated locally with Windows offline TTS; MP3 size 52,388 bytes, SHA-256 `a4ce6316e71748ee4ea8489e0717bad66196f7202ca618a7c015f1169b92dc27`. It is under ignored local `tmp/48-notebook-live/audio`, not Git. The reference reads:

> 소리글 전사 확인입니다. 오늘은 맑은 하늘 아래에서 한국어 문장을 읽습니다. 첫 번째 숫자는 하나이고 두 번째 숫자는 둘입니다. 이 음성은 자동 전사 기능을 확인하기 위해 직접 만든 시험 자료입니다.

No user lecture or Legacy credentials are used. This is speech, not a sine-wave LIVE fixture. Sine waves remain only local structural-test inputs.

## LIVE gates

COLAB LIVE LARGE-V3 / actual model/device / speech accuracy / actual downloaded result Import remain **NOT VERIFIED** until the user directly executes the Notebook in an approved free Runtime and supplies its result ZIP. Source/Mock PASS is not actual inference PASS. The Notebook cannot independently prove the account does not consume paid Compute Units: user confirmation is required; no paid fallback is offered.

One separate authorization is required for the user-started free GPU Runtime, this one own MP3 upload, large-v3 inference once and TXT/JSON/SRT download. Opening/running the Notebook is performed by the user. On receipt of the downloaded result, local Import/preview can be validated without repeating the accepted Drive LIVE test; Import → Drive remains Source/Mock unless separately authorized.

No new QA infrastructure, issue, paid resource, artifact build/install, #59 revalidation, main merge or deployment is part of this change. #48 stays ACTIVE, #60 OPEN, #114 OPEN, STUDY USE READY NO. Source/Mock readiness does not imply installed-artifact or #113 Release Freeze acceptance.
