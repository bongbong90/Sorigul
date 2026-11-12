# Drive / Results / Desktop UX Migration

## Baseline

- Branch: `feature/drive-results-desktop-ux`
- Baseline HEAD: `28211075397156fa585ceea27889f3b19a4d1a3b`
- UI Freeze v1: `LOCKED`
- Migration Contract: unchanged
- Result architecture: `Filesystem Truth + Job API`

## Google Drive architecture

Google Drive is the only cloud target. `DriveUploadService` owns classification, preflight, folder resolution and the four-file update-or-create operation. `GoogleOAuthService` owns OAuth state and token refresh. Google SDK imports are lazy so backend startup and automated tests never start OAuth or call Google.

The Legacy trigger is preserved: Drive upload is opt-in and, when enabled on a Job, runs after each local file reaches verified `DONE`. A Drive-only retry reuses the local bundle and never creates or reruns a transcription Job.

### OAuth and runtime data

- Scope: `https://www.googleapis.com/auth/drive` (full Drive scope, unchanged from Legacy)
- Provisioned client credential boundary: `%LOCALAPPDATA%\Sorigul\auth\google_oauth_client.json`
- Token: `%LOCALAPPDATA%\Sorigul\auth\google_drive_token.json`
- Auth states: unauthenticated, authorizing, connected, refresh failed and re-auth required
- Token writes use a same-directory temporary file followed by atomic replace.
- Credentials, authorization codes and tokens are not logged and are never stored in the repository.

The backend returns an authorization URL and accepts the completion code at the OAuth service boundary. Packaged credential injection and the Tauri browser/callback handoff remain a release decision.

### Classification and folder hierarchy

Classification accepts a validated standard stem and known subject aliases. It does not reinterpret arbitrary filenames. The preserved Legacy hierarchy is:

```text
2026 제37회 공인중개사 자격시험
└─ 전사자료
   └─ {과정}
      └─ {[1차] 또는 [2차] 과목}
         └─ {과정_과목_N주차}
```

`공인중개사법` uses the Legacy `중개사법` spelling in the week folder. Classification failure sets `CLASSIFICATION_FAILED`, blocks only Drive, and leaves local `DONE` unchanged.

### Preflight and upload bundle

Before the first file upload the service verifies:

1. Authentication and refresh.
2. Standard-name classification.
3. MP3 existence and readability.
4. The existing `OutputBundleValidator` result for TXT, JSON and SRT.
5. Readability of all four files.
6. Exact-name folder lookup/create for the complete target hierarchy.

The upload list is exactly MP3, TXT, JSON and SRT. For every file, lookup is restricted to the exact parent and filename. An existing remote file is updated; otherwise it is created. A partial failure is not rolled back. Retry repeats update-or-create, converging on one four-file bundle without duplicate names.

### Drive state isolation

Drive state is stored per local file in the persisted Job under a separate enum:

```text
DISABLED
AUTH_REQUIRED
CLASSIFICATION_FAILED
PENDING
UPLOADING
DONE
FAILED
```

Drive errors update only this state and structured Drive events. They do not mutate `FileStatus`, delete TXT/JSON/SRT, or reset local progress. `Local DONE + Drive FAILED` and Drive-only retry are covered by fake-client tests.

## D09 filesystem truth and Folders API

`ResultsService` rescans the selected top-level folder for every refresh. It does not reconcile completion from Job history. A removed TXT or JSON immediately clears complete status on the next refresh; an externally added valid bundle is complete even without a Job.

The API provides:

- `POST /api/folders/scan`: fresh scan and filter metadata
- `GET /api/folders/{scan_id}/items/{item_id}/preview`: bounded UTF-8 TXT preview
- `GET /api/folders/{scan_id}/items/{item_id}/text`: full TXT read with a 5 MiB safety limit
- `POST /api/folders/{scan_id}/open-intent`: validated Desktop open-folder intent

The four filters mean:

- `all`: physical MP3/TXT/JSON/SRT entries.
- `complete`: MP3 entries with a valid same-stem TXT/JSON/SRT bundle.
- `incomplete`: MP3 entries without a valid complete bundle.
- `results`: physical TXT/JSON/SRT entries, including result-only stems without MP3.

Preview and open-intent requests accept an opaque scan/item ID, not an arbitrary path. The backend revalidates that the item is a known top-level entry, remains under the scanned root and has an expected extension. There is no `os.startfile()` or shell invocation.

## Frontend API binding

`frontend/src/api/client.ts` is the single backend URL and error-normalization boundary. `VITE_BACKEND_URL` can override the development default, while components never repeat a literal backend URL.

- Transcription: actual scan, selection, no-selection confirmation, create/start, 1.5-second Job polling, Stop, Cancel, Retry, retranscribe, local partial failure, CRASHED and separate Drive state.
- Folders: actual filesystem refresh, four server-side filters, preview, full text and open-folder intent.
- Log: Job and application structured events with four UI filters and visible-text-only clipboard copy.
- Settings: persisted notification, close behavior and shutdown policy.
- Health/runtime UX: 4-second health polling with starting, offline, reconnecting and connected presentation; component unmount clears every poll timer.

Local progress is indeterminate when the engine reports no measurable percentage. The frontend does not synthesize progress with a timer. Backend errors are normalized to `code`, `userMessage` and `retryable`; raw FastAPI payloads and stack traces are not presented.

The web-development folder selection boundary currently accepts a path prompt. Tauri replaces only this boundary with its folder picker; filesystem access remains in the backend.

## Settings and Desktop contracts

Settings are validated Pydantic models stored at `%LOCALAPPDATA%\Sorigul\settings.json`. Writes are atomic. Invalid JSON or schema is quarantined as `settings.corrupt.<timestamp>.json`, then safe defaults are used.

Notification settings create `FILE_COMPLETED` and `JOB_COMPLETED` Desktop intents in the application event source. No Windows notification API is called.

Close behavior persists `tray` or `exit`. No Python tray, hide/show operation or tray icon is created.

The shutdown coordinator derives inactive, counting-down, cancelled or ready-to-shutdown state from the persisted policy (`disabled`, `immediate`, `15_seconds`, `30_seconds`). Cancellation mutates application state, and a later finished Job may create a new countdown. No Windows shutdown command is called.

Drive failure does not block shutdown because Drive is independent of local success: `DesktopCoordinator.job_finished` never inspects `Job.drive`.

Countdown eligibility is derived from `Job.status` together with a `Job.batch_completed` flag set by `TranscriptionRunner` when the file-processing loop reaches its natural end (every file that started `WAITING` reached a terminal state):

- Countdown is created when `Job.status` is `DONE`, or `FAILED` with `batch_completed == True` — i.e. one or more individual files failed but the batch loop ran through to completion (per Migration Contract D02, per-file failure does not stop batch processing).
- Countdown is not created when `Job.status` is `STOPPED`, `CANCELLED` or `CRASHED`, or when `Job.status` is `FAILED` with `batch_completed == False` — a common fatal error (engine/model init failure, unreadable source folder, or a fatal in-loop engine error) that cut the batch short, leaving later files unprocessed (`WAITING`).

No new Job-level status enum was introduced; the existing `FileStatus` values and a single boolean reuse the runner's existing control flow (the same `fatal_error` signal that already distinguished a fatal in-loop break from a per-file failure).

### Policy gap — RESOLVED

The locked contract did not explicitly state whether a locally partial-failure Job should still be eligible for shutdown. This is now resolved: a partial-failure Job that completes its batch is eligible for shutdown countdown; only STOPPED/CANCELLED/CRASHED and fatal-error early termination block it. See `batch_completed` above and `backend/tests/test_transcription_runner.py` / `backend/tests/test_drive_results_desktop.py` for coverage.

## Tests

Automated backend coverage includes:

- exact four-file Drive upload;
- first upload create and second upload update without duplicate count growth;
- classification standard name, alias and failure;
- auth-required, refresh-failed and re-auth states with fake auth;
- `DONE + Drive FAILED`, local bundle preservation and Drive-only retry;
- external MP3 addition, TXT deletion, external/result-only bundle, all four filters;
- bounded preview, full TXT and Korean/Unicode paths;
- corrupt settings quarantine, atomic save, countdown and cancellation;
- shutdown countdown allowed for full success, partial-failure-with-completed-batch, and Drive-failed-independent-of-local;
- shutdown countdown blocked for STOPPED, CANCELLED, CRASHED and fatal-error mid-batch termination, with countdown-cancel regression covered for both full-success and partial-failure batches;
- `TranscriptionRunner` sets `batch_completed` correctly for full success, partial failure, STOPPED, CANCELLED, an in-loop fatal engine error, and a pre-loop fatal error (engine resolution failure skips the finish callback entirely);
- all existing Core and Transcription Engine tests.

Frontend validation uses lint, TypeScript checking and a production build. Browser validation is performed at 1440×900 and 1024×768 against controlled local backend data; it does not use Google credentials.

Actual Google OAuth/login/upload smoke test: `NOT RUN`.

## Deferred Tauri work

- Native folder picker and handling of `OPEN_FOLDER` intents
- OAuth authorization URL browser launch and callback handoff
- Actual OS notifications
- Window close/hide/show and System Tray
- Actual Windows shutdown command after `READY_TO_SHUTDOWN`
- Sidecar lifecycle, owned-process cleanup and MSI validation

## Packaging decisions required

- Secure provisioning of the Desktop OAuth client configuration into `%LOCALAPPDATA%\Sorigul\auth`
- Final packaged OAuth redirect/callback URI and Tauri handoff

## Known risks

- The Legacy root contains the exam-year-specific name `2026 제37회 공인중개사 자격시험`. It is preserved rather than generalized; a future product decision is needed for later exam years.
- Application events are intentionally process-memory bounded history. Long-term global log retention remains deferred.
- Full TXT view is capped at 5 MiB to avoid unbounded browser memory use.

## Final verdict

All scoped automated, browser, whitespace and artifact checks passed. Packaging decisions are deferred to the authorized Tauri/Release stage and do not block this work package.

`DRIVE / RESULTS / DESKTOP UX MIGRATION READY`
