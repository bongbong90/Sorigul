# Sorigul Current Release Status

This is the living current release ledger, not a historical validation artifact.

## Source lineage

- Package A: COMPLETE — prior remote verification recorded
- Package B: COMPLETE — prior remote verification recorded
- Package C: COMPLETE — prior remote verification recorded
- Package D: COMPLETE — prior remote verification recorded
- Package E: COMPLETE — canonical source regression LOCAL PASS

`RELEASE READY = NO`

`PRE-BUILD SOURCE READY = YES`

The current source cannot be called release-ready because a fresh current-HEAD CUDA sidecar has not
been built, a fresh current-HEAD MSI has not been built, current installed-runtime validation has not
run, and the current real Local gate has not run.

## CUDA release requirement

The required candidate has all of the following:

- `torch==2.13.0+cu130`
- `torch.version.cuda == 13.0`
- `torch.cuda.is_available() == true`
- `torch.cuda.device_count() >= 1`
- a successful real CUDA tensor computation

The Phase5B CPU-only installer artifact is historical evidence only and is not a final Local GPU
candidate. Its actual Local gate result (`CUDA unavailable` followed by CPU fallback) is
`INVALID RELEASE EVIDENCE`.

## Zero-cost status

No billable external operation has been run during A-E source remediation. No paid CI is part of the
canonical validation. If possible paid-credit consumption cannot be safely excluded for a real Colab
gate, that gate remains `PENDING_ZERO_COST_EXTERNAL_VALIDATION`. The Local engine is the primary
release path that can be validated without external paid-credit consumption.

TryCloudflare Quick Tunnel is only a best-effort connection to a user-started Colab runtime. It is an
existing free/accountless research path with testing/development operational limitations. Sorigul
does not automatically provision a paid or managed replacement.

## Required post-E official release gate

The order is fixed:

1. SOURCE regression PASS
2. fresh current-HEAD CUDA sidecar build
3. isolated self-test
4. current-run manifest/hash
5. deterministic current-run MSI
6. install
7. installed health/process/JobObject
8. installed CUDA synthetic tensor
9. bundled sibling ffmpeg
10. Unicode/temp synthetic scan
11. no-user-data verification
12. only then actual Local MP3 gate
13. optional zero-cost-safe external Colab gate
14. optional zero-cost-safe Drive TXT/JSON/SRT gate
15. Folders/retry/cleanup verification
16. supervised shutdown only with explicit user approval
17. final ledger

Until the synthetic installed gates pass, the real MP3 gate is blocked. Actual Windows shutdown is
also blocked without immediate explicit user approval.
