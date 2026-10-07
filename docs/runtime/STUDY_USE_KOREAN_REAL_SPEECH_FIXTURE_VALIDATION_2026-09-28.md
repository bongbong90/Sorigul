# Study Use Korean Real-Speech Fixture Validation — 2026-09-28

## Verdict

**CONTROLLED KOREAN REAL-SPEECH = PASS**

**LONG-FORM LOCAL CUDA STRESS = PASS**

**Issue #47 ACTUAL LOCAL STUDY MP3 = PENDING_REAL_AUDIO**

This validation strengthens the prerequisite evidence for Issue #47. It does
not use a personal study recording, does not complete Issue #47, and does not
authorize a `STUDY USE READY` declaration.

Validation branch: `test/korean-real-speech-fixture`

Stacked base: `test/study-use-installed-synthetic`

Tracking issue: #104

## Fixed installed artifact

The exact installed artifact that passed Issue #46 was reused. Nothing was
rebuilt or reinstalled.

| Identity | Expected | Actual | Result |
|---|---|---|---|
| Validation source HEAD | `67fed29ffb5691a513f93beefb7ef00e4df3891f` | `67fed29ffb5691a513f93beefb7ef00e4df3891f` | PASS |
| MSI SHA-256 | `0e623ba30ef6fd33b6b0736ca9e77b5107ffb5856d91437e24ed2a14beb33a90` | same | PASS |
| Installed Core SHA-256 | `c106ddea7ab2e6989d284b2fb93630b6d9f5113f7a2f16f98f4a8d456fdab8b9` | same | PASS |
| Local Runtime SHA-256 | `7504ca7811434e5ba0d633135d445994585ca551a83891eb6b414148f34b302a` | same | PASS |

The installed desktop at `C:\Program Files\Sorigul\sorigul-desktop.exe`
started the installed Core backend. Validation used an isolated
`LOCALAPPDATA`; its versioned runtime executable was a same-volume hard link
to the canonical validated Local Runtime, with the original manifest and the
same verified SHA-256. Existing Sorigul jobs and settings were not modified.

## Licensed speech source and local fixtures

Source page:
<https://commons.wikimedia.org/wiki/File:12%EA%B0%95%EC%9C%BC%EB%A1%9C_%EB%81%9D%EB%82%B4%EB%8A%94_%EA%B8%B0%EC%B4%88_%ED%95%9C%EA%B5%AD%EC%96%B4_-_%EA%B5%90%ED%86%B5.ogg>

License: Creative Commons Attribution 3.0 Unported,
<https://creativecommons.org/licenses/by/3.0/>

Attribution: masterTOPIK. The Commons file description identifies the audio as
a Korean lesson about transportation and records the CC BY 3.0 license. The
original is an Ogg Vorbis human-speech recording. It was downloaded from the
Wikimedia Commons original-file endpoint, not extracted from YouTube.

| Input | Source | License | Original duration | Local fixture duration |
|---|---|---|---:|---:|
| Short real speech | Wikimedia Commons file above | CC BY 3.0 | 443.062857 s | 60.00 s (`00:30`–`01:30`) |
| Long-form stress | Same Wikimedia Commons file | CC BY 3.0 | 443.062857 s | 1,772.26 s (29:32.26) |

The installed bundled FFmpeg converted the source to MP3. The long fixture is
four repetitions of the licensed source.

**LONG FIXTURE = REPEATED REAL SPEECH**

**NOT A REAL STUDY LECTURE**

## Short real-speech execution

| Check | Result |
|---|---|
| Installed desktop and Core backend | PASS |
| Job terminal state | `DONE` |
| Actual job device | `cuda` |
| Wall time | 90.27 s |
| Desktop responsive | PASS; zero failed polls |
| Backend health | PASS; zero failed polls |
| Local worker stability | PASS; one PyInstaller bootloader/payload pair at peak, zero after completion |
| TXT | PASS; non-empty, 373 bytes |
| JSON | PASS; parsed with required `text` and `segments`, 4,968 bytes |
| SRT | PASS; non-empty and timestamp structure valid, 675 bytes |
| Same folder/stem | PASS |
| Folders complete/results | PASS; 1 complete source and 3 results |
| Rescan | PASS; source reported `DONE` |
| Completed skip | PASS; non-force repeat creation rejected as no eligible file |
| Result preservation | PASS; TXT/JSON/SRT SHA-256 values unchanged across the skip check |
| Worker cleanup | PASS; zero Local worker processes |

## Long-form execution

| Check | Result |
|---|---|
| Fixture classification | `REPEATED REAL SPEECH`; not a study lecture |
| Job terminal state | `DONE` |
| Actual job device | `cuda` |
| Wall time | 220.59 s |
| Desktop responsive | PASS; zero failed polls |
| Backend health | PASS; zero failed polls |
| Local worker stability | PASS; one PyInstaller bootloader/payload pair at peak, zero after completion |
| TXT | PASS; non-empty, 12,540 bytes |
| JSON | PASS; parsed with required `text` and `segments`, 177,951 bytes |
| SRT | PASS; non-empty and timestamp structure valid, 24,510 bytes |
| Same folder/stem | PASS |
| Folders complete/results | PASS; 1 complete source and 3 results |
| Rescan | PASS; source reported `DONE` |
| Completed skip | PASS; non-force repeat creation rejected as no eligible file |
| Result preservation | PASS; TXT/JSON/SRT SHA-256 values unchanged across the skip check |
| Worker cleanup | PASS; zero Local worker processes |

The worker's transient two-process count is the expected PyInstaller one-file
bootloader parent plus payload child, not two simultaneous transcription jobs.
Both disappeared after each completed job.

## Validation-harness corrections

Two preliminary harness attempts were stopped without being counted as product
failures:

1. The first monitor treated the normal PyInstaller parent/payload pair as two
   workers and stopped the run. Desktop, backend, and worker cleanup all
   reached zero.
2. The second short job completed `DONE` and persisted an explicit CUDA-use
   event, but Windows PowerShell 5 decoded the Korean event text differently
   from the comparison literal. The final monitor therefore used the event's
   stable category/level structure: two Local info events and no Local warning
   event. This distinguishes CUDA success from the CPU-fallback warning without
   relying on console code-page decoding.

The final evidence run started from fresh isolated job state and fresh output
bundles and completed both fixtures.

## Content-quality boundary

This was a runtime and output-integrity gate, not an ASR benchmark. No WER or
CER threshold was introduced. The generated transcript text was neither
printed in this report nor committed or uploaded to GitHub. Non-empty TXT,
parseable JSON, valid SRT, and absence of runtime corruption were enforced.

## Cleanup and exclusions

- Final desktop processes: 0
- Final installed Core backend processes: 0
- Final Local worker processes: 0
- Orphan processes: none
- Dedicated fixture root, isolated app data, audio, and transcripts: removed
  after all preservation checks passed
- Personal short Korean MP3: not available / not run
- Personal long study lecture MP3: not available / not run
- Colab: not run
- Google Drive: not run
- Windows shutdown: not run
- Rebuild/reinstall: not performed

## Final gate matrix

- FIXED INSTALLED ARTIFACT IDENTITY: PASS
- LICENSED KOREAN HUMAN SPEECH SOURCE: PASS
- SHORT REAL-SPEECH LOCAL CUDA: PASS
- LONG-FORM REPEATED REAL-SPEECH CUDA STRESS: PASS
- TXT / JSON / SRT: PASS
- FOLDERS / RESCAN: PASS
- COMPLETED SKIP / RESULT PRESERVATION: PASS
- DESKTOP / BACKEND HEALTH: PASS
- WORKER CLEANUP / NO ORPHAN: PASS
- TEMPORARY AUDIO AND TRANSCRIPT CLEANUP: PASS
- ISSUE #47 ACTUAL LOCAL STUDY MP3: PENDING_REAL_AUDIO

Issue #47 must remain open until actual personal study audio is available and
validated.
