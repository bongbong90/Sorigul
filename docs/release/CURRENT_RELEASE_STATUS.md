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

The current source cannot be called release-ready until one fresh Local Runtime / Core / MSI set
from the frozen Release Candidate HEAD passes clean install, installed Core/Local provenance
pairing and installed CUDA synthetic validation, followed by the real Local gate. Prior isolated
or stopped-attempt artifacts are historical evidence only and cannot satisfy fresh #113.

The current sequence is 6A-R3b / #154 manifest gate reconciliation → separate 6A-R3c Core
PowerShell 5 process-handle hardening → Release Freeze → #113 Fresh Artifact / Install Gate.
#113 remains BLOCKED until the prerequisites complete. Release Freeze requires one agent,
one branch, one frozen HEAD and one artifact session.

## CUDA release requirement

The required candidate has all of the following:

- Local Runtime manifest exact scalar `torch_requirement = "torch==2.13.0+cu130"`
- Local Runtime manifest exact scalar `expected_cuda = "13.0"`
- `torch.version.cuda == 13.0`
- `torch.cuda.is_available() == true`
- `torch.cuda.device_count() >= 1`
- a successful real CUDA tensor computation

Core build manifest owns Core provenance only; `torch_requirement` / `expected_cuda` must be
absent from Core and must not be consumed by the Core/MSI installer. Local runtime discovery
validates Local identity fail-closed, including installed Local/Core `source_head` equality.

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

1. SOURCE regression PASS and separate 6A-R3c complete
2. Release Freeze: exact Release Candidate HEAD and Single Writer preflight
3. fresh Local Runtime build, isolated CUDA self-test and Local identity/manifest/hash
4. fresh Core build, isolated Core self-test, Core provenance/size/hash and payload exclusions
5. fresh MSI from the same frozen HEAD and current-run Core manifest/hash
6. clean install
7. installed Core/Local provenance pairing and fail-closed Local runtime discovery
8. installed health/process/JobObject
9. installed CUDA synthetic tensor
10. bundled sibling ffmpeg
11. Unicode/temp synthetic scan
12. no-user-data verification
13. only then actual Local MP3 gate
14. optional zero-cost-safe external Colab gate
15. optional zero-cost-safe Drive TXT/JSON/SRT gate
16. Folders/retry/cleanup verification
17. supervised shutdown only with explicit user approval
18. final ledger

Until the synthetic installed gates pass, the real MP3 gate is blocked. Actual Windows shutdown is
also blocked without immediate explicit user approval.
