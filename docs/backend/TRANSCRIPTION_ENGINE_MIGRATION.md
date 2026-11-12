# Transcription Engine Migration

## Baseline

- Branch: `feature/transcription-engine-migration`
- Baseline HEAD: `a2d8b577939660cec634a8fba5eecda1b8eb9348`
- UI Freeze v1: unchanged
- Product contract: `docs/project/MIGRATION_CONTRACT.md`

## Architecture

The backend now separates engine adapters, canonical results, output bundle commit, job orchestration, and background execution.

```text
POST /api/jobs/{job_id}/start
  -> BackgroundExecutionService
  -> TranscriptionRunner (files are sequential)
  -> LocalWhisperEngine or DirectColabEngine
  -> TranscriptionResult
  -> OutputBundleWriter staging / validation / replacement / rollback
  -> persisted file and job state
```

`ThreadPoolExecutor` is used because both Whisper and the synchronous Direct Colab call are blocking operations. The request returns immediately with HTTP 202. The Local adapter serializes model use so two jobs cannot execute against the same GPU model concurrently. Job mutations and `jobs.json` persistence are protected by a process `RLock`.

## Local engine

`LocalWhisperEngine` lazy-imports Whisper and Torch and does not load a model during application import. The first Local run loads `medium`; the instance is reused within the process and model loading is lock-protected. CUDA is preferred. CUDA availability or model-load failure falls back to CPU and emits a structured event. CUDA fp16 errors receive one fp16-disabled retry.

### Fixed options

The adapter passes the complete locked option set to `model.transcribe`:

```text
language="ko"
task="transcribe"
temperature=0
beam_size=5
best_of=5
patience=1
condition_on_previous_text=False
```

Compatibility was checked against installed `openai-whisper 20250625` without loading or downloading a model. Its low-level `DecodingTask._verify_options` rejects simultaneous `beam_size` and `best_of`, but the public `transcribe()` path copies the supplied options and removes `best_of` for its `temperature == 0` decode branch before constructing `DecodingOptions`. Therefore the established runtime call can pass the locked option set unchanged. No option was removed or changed in Sorigul code.

### Local stop and progress

Local audio is never physically chunked. OpenAI Whisper has no safe public mid-call cancellation callback, so Stop/Cancel is observed before the call and immediately after it. A result returned after a request is discarded before staging or final commit. Retry starts the file from the beginning. Current-file percentage and ETA remain indeterminate for Local; state, elapsed time at the caller, and completed-file counts are the honest available signals.

## Direct Colab adapter

The adapter follows the repository's ACTIVE Legacy evidence: normalized base URL, synchronous `GET /health`, and synchronous `POST /transcribe`. The request uses a multipart `file` upload and canonicalizes the response before it reaches the runner. The HTTP client is injectable so tests make no external calls.

The current repository contains the parity audit but not the cited Legacy implementation files or their Git history. Consequently, the exact deployed notebook's multipart envelope remains an integration risk and must be smoke-tested with the real endpoint during Desktop integration; the canonical endpoint shape itself is evidence-backed.

### Internal 300-second chunking

`FFmpegAudioSplitter` probes duration with `ffprobe`, creates fixed 300-second MP3 chunks in an OS temporary directory, skips tails shorter than one second or 2048 bytes, leaves the source unchanged, and removes temporary audio after success, failure, Stop, or Cancel. Missing ffmpeg/ffprobe is a structured fatal runtime error. No binary or chunk is stored in the repository.

Chunk results are converted to `TranscriptionResult`, segment timestamps are offset onto the original timeline, segments are sorted, and text is joined in chunk order without rewriting Korean content.

### Retry rules

- Each chunk has one initial network attempt and at most one automatic retry.
- Timeout, temporary network errors, HTTP 408, HTTP 429, and HTTP 5xx are retryable.
- Retryability and fatal scope are independent. A non-retryable error is not automatically fatal.
- HTTP 401/403 authentication failures and HTTP 404/405 endpoint or method mismatches are common fatal failures and may stop the batch immediately.
- Other non-retryable `/transcribe` HTTP errors, including HTTP 400, fail only the current file and allow later files to continue.
- Invalid `/transcribe` response JSON or segments fail only the current file. A protocol incompatibility established by `/health` or another preflight validation may remain common fatal.
- A manual file Retry receives the same per-chunk limit; there is no lifetime manual Retry cap.

### FAILED recovery cache

Successful response JSON is stored under `%LOCALAPPDATA%/Sorigul/cache/colab` (or the platform app-data fallback). The fingerprint includes the resolved source path, size, nanosecond mtime, the fixed 300-second policy, and endpoint/adapter signature. A changed source or signature invalidates and removes the stale file cache.

A retryable system/network `FAILED` preserves completed response JSON. A successful file clears it. STOP or CANCEL always clears the current file cache, so the next run starts at the first chunk. Chunk audio is never a recovery artifact.

## Canonical result

Both engines return `TranscriptionResult` with text, ordered segments, optional language, and internal metadata. Each segment must have finite non-negative `start`/`end`, `end >= start`, and text. Raw engine responses are not exposed through the job API.

Output JSON has the stable minimum shape:

```json
{
  "text": "...",
  "segments": []
}
```

## Output bundle writer

TXT is UTF-8 transcription text. JSON is the canonical payload. SRT contains sequential indices and `HH:MM:SS,mmm --> HH:MM:SS,mmm` timestamps; an empty SRT is valid when there are no segments.

For each source MP3 the writer creates all three staged files beside the source, validates the staged bundle, backs up any old finals, replaces all finals, validates the final bundle, and only then removes backups. A failure during replacement or final validation removes newly installed files and restores the previous bundle. Empty TXT, absent SRT, unreadable JSON, missing keys, and invalid canonical segments prevent `DONE`.

## Runner and job transitions

Files run sequentially:

```text
WAITING -> PREPARING -> TRANSCRIBING -> SAVING -> VERIFYING -> DONE
```

Every transition above is persisted. A file-specific engine, decode, request, response, or output problem becomes `FAILED`, while later files continue. A common environment, authentication, endpoint/protocol, or runtime preparation failure may stop the batch immediately. Counts and final job state preserve partial success.

Stop produces `STOPPED` and leaves later waiting files untouched. Active Cancel is first `CANCEL_REQUESTED`; runner acknowledgement converts the current and pending files to `CANCELLED`. Cancellation exceptions are separate from network failures. `CRASHED` startup recovery remains in `JobManager`.

Retry retains filesystem-truth reconciliation: valid existing bundles become/remain `DONE`; only `FAILED`, `STOPPED`, `CANCELLED`, or `CRASHED` files return to `WAITING`. Explicit retranscription is stored on the job and is the only path that processes an existing valid bundle. The old bundle is protected until the replacement bundle passes final validation.

## Progress and ETA

Colab progress is calculated from completed internal chunks and stored only as a user-level percentage; no chunk index, manifest, or chunk setting is exposed. Local progress is indeterminate. The backend does not invent an ETA, so `eta_seconds` remains `null` until a future evidence-based estimator is added.

## API surface

- `POST /api/jobs`: accepts `engine` (`local_whisper` or `direct_colab`), optional `colab_url`, scope, selection, and explicit retranscription.
- `POST /api/jobs/{job_id}/start`: starts background execution and returns HTTP 202 without waiting for transcription.
- `GET /api/jobs` and `GET /api/jobs/{job_id}`: polling surfaces persisted status, counts, events, and progress.
- `POST /api/jobs/{job_id}/action`: `stop`, `cancel`, and `retry` retain the existing action surface.

## Dependencies

- Base `backend/requirements.txt`: unchanged.
- Optional Local runtime: `backend/requirements-whisper.txt` pins `openai-whisper==20250625`.
- ffmpeg/ffprobe: external runtime dependency for audio decoding/splitting; binaries are not copied into the repository.
- Test-only dependencies: unchanged (`pytest`, `pytest-asyncio` remain in the existing base file).

The optional requirements split keeps backend import, Core tests, and fake-engine tests operational when Whisper/Torch is not installed. Installing the optional dependency can install Torch transitively; CUDA-specific packaging remains deferred.

## Contract ambiguity

No `CONTRACT AMBIGUITY` was found between D02 and D08. Section 6.3 explicitly requires a single-file failure to continue, while D08's exhausted automatic retry makes that current Colab file `FAILED`. Only an endpoint/engine preparation failure shared by subsequent files is a common fatal failure.

## Tests

Automated tests use fake models, splitters, clients, cancellation actions, temporary Unicode paths, and injected replacement failures. They cover Local lazy loading/reuse/options/device/fp16/Stop, canonical conversion, all output formats and validation, safe replacement rollback, sequential partial failure, retry preservation, state persistence, non-blocking background start, Colab 300-second merge/retry/cache/fingerprint, and STOP/CANCEL cache invalidation.

No test downloads or runs `medium`, uses a user MP3, calls Colab, or calls Drive.

## Deferred work

- Desktop frontend binding and real folder picker path delivery
- Packaged ffmpeg and CUDA/Torch installer lifecycle
- Real Local medium smoke test on an explicitly prepared machine
- Real deployed Colab notebook envelope/credential smoke test
- Tauri sidecar lifecycle, OS tray/notifications/shutdown, MSI, Drive, and MYBOX
- Evidence-based ETA estimator

## Known risks

- The deployed Colab notebook source is not in this repository; multipart integration requires a real endpoint smoke test without changing the evidence-backed synchronous endpoints.
- A blocking Whisper or HTTP call cannot be safely killed mid-call. Stop/Cancel prevents commit and is acknowledged at the next safe boundary.
- Three filesystem outputs cannot form one native transaction. The backup-and-rollback plan is tested, but an external process or catastrophic filesystem failure can still prevent rollback.
- The existing dependency layout mixes test dependencies into production requirements; it was intentionally not refactored in this work package.

## Final verdict

The implementation and fake-engine acceptance suite satisfy the migration contract. Final readiness also requires the repository-wide validation commands and artifact checks recorded in the completion report.
