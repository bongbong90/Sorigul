# Phase 19 execution boundary and rollback plan (2026-11-15 KST)

Issue: https://github.com/bongbong90/Sorigul/issues/269
Integration: 58d734a64b9f8a7ec3ab4ba82970c1a821ca1158
Unmerged prerequisite candidate: 6a7320b8bbba189780ad7ecdd9b96a6a7a138b66 (PR #268).
This file grants no build, install, uninstall or merge permission.

## Current gates
Integration official source regression: FAIL, 265 passed / 2 failed.
PR #268 changed readiness tests: 14 passed.
Candidate preflight attempt 1: FAIL, targeted packaging tests 36 passed / 2 failed (CreateProcess WinError 5).
A diagnostic accidentally used root cwd and failed collection; preserve that log as an invocation error. Correct backend-cwd diagnostic and full candidate regression are separate evidence.
Freeze and artifact session must not start while required regression/preflight failures remain.

## Protection
Original checkout and five untracked helpers remain untouched. Candidate worktree is tmp/phase19-269-candidate; all evidence is ignored under tmp/phase19-evidence-269.
Never invoke Local builder with the real LOCALAPPDATA: it publishes runtime/local-whisper/v1. Use a uniquely owned, standard-user, child-process-only LOCALAPPDATA and APPDATA plus isolated WebView data. Do not modify global environment, real Runtime, settings, jobs, OAuth, MP3, results, selected study/staging, model cache or Store-shadow appdata.
Immediately before any approved artifact session, use canonical Start with exact final branch/HEAD/Freeze/evidence root. It captures native protected baseline, hashes only settings/jobs, never media/model/auth contents, and must reach SESSION_ACTIVE. Retain the real protected-profile environment in the canonical guard; isolate only owned build/acceptance children. Use Status before/after every artifact stage; stop on any unexpected protected change, identity/hash mismatch, residual process or port failure. Do not delete an existing lock.

## Build order after source gates and separate execution approval
1. Canonical preflight including Probe PASS on approved exact source; canonical Freeze; independently verify source/tree/all tracked-file SHA256 and Freeze SHA256.
2. Canonical Start, stable heartbeats, competing DENIED and protected baseline; require ACTIVE.
3. Versioned isolated Local Runtime using existing build_local_whisper_runtime.ps1. Validate exact torch==2.13.0+cu130, CUDA 13.0, real CUDA tensor, manifest and SHA256.
4. Existing build_windows_installer.ps1 owns Core build_backend_sidecar.ps1, then Tauri/MSI. Do not create a redundant standalone Core build. Preserve stage-boundary evidence around its owned Core stage. Inspect recursive archive/PYZ for multipart/python_multipart as well as prohibited torch/CUDA/Whisper. Record any intentional transitive multipart payload rather than claiming direct-import absence proves exclusion. Core manifest must lack Local-only fields; Core/MSI must each be <=250 MiB. Record current-attempt manifest, artifact size/hash/source_head pairing.

## Existing-install transition: separate approval required
Read-only discovery found installed ProductCode {021BCE70-EDE5-49E4-B85C-E7AFD1CCA75B}, version 0.1.0, C:\Program Files\Sorigul\. Re-read immediately before any transition; this is not uninstall authorization.
Before requesting execution approval: identify and hash the exact rollback MSI, verify its ProductCode/version and installed provenance; confirm backups/retention of existing Runtime and protected state without reading auth/media/model contents. Rollback artifact availability is NOT YET VERIFIED, so replacement is BLOCKED.
Require Desktop/Backend/owned workers/WebViews/related writers absent, TCP 8000 FREE, no active MSI transaction, valid source/Freeze/guard and protected baseline. Remove only the reverified ProductCode with a detailed MSI log after approval. Install only the hash-verified current MSI with autolaunch disabled and detailed logging. Never infer install identity or disabled autolaunch from /qn alone.
On failure: stop owned processes, preserve all evidence, use only exact hash-verified rollback MSI after approved transition scope covers restoration; restore application binaries only, leave protected user files and original Runtime intact. Never auto-delete user data or issue broad process kills. If protection or installer identity is uncertain, STOP and report rather than proceed.

## Installed acceptance after approved transition
Launch actual installed Desktop in the isolated profile and prove Backend starts automatically. Confirm installed Desktop/Core/ffmpeg/manifest hashes, same-source isolated Local pairing, CUDA tensor, synthetic Korean audio and TXT/JSON/SRT, multiple files/skip, STOP/CANCEL/RETRY/CRASHED, folders/scan/log and Unicode paths. Reuse owned synthetic fixtures; do not repeat the 52:34 lecture and do not execute PC shutdown.
Tray exit must return owned Backend/Worker/WebView process count to zero and release the port. Canonical protected comparison and existing Runtime/helper hash checks must pass; report metadata-only exceptions exactly. Controlled Stop must release guard/lock. Preserve logs and final acceptance before any cleanup; never promote a partial candidate.

Verdict remains BLOCKED until all required source/artifact/installed gates actually pass. Phase 20 #246 remains gated.
