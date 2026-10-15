# Sorigul Current Release Status

This is the living current release ledger, not a historical validation artifact.

## Source lineage

- Package A: COMPLETE — prior remote verification recorded
- Package B: COMPLETE — prior remote verification recorded
- Package C: COMPLETE — prior remote verification recorded
- Package D: COMPLETE — prior remote verification recorded
- Package E: COMPLETE — canonical source regression LOCAL PASS

`RELEASE READY = NO`

`PRE-BUILD SOURCE READY = REQUIRES PREFLIGHT`

The current source cannot be called release-ready until one fresh Local Runtime / Core / MSI set
from the frozen Release Candidate HEAD passes clean install, installed Core/Local provenance
pairing and installed CUDA synthetic validation, followed by the real Local gate. Prior isolated
or stopped-attempt artifacts are historical evidence only and cannot satisfy fresh #113.

#150, #154, #159 and #161 are complete. The latest #113 attempt stopped before
artifact build because backend pytest was invoked from the wrong working directory; no
product/source defect was established by that STOP.

The current sequence is #55 canonical preflight orchestration → exact source Freeze →
canonical preflight rehearsal PASS → new artifact run_id + Single Writer → #113 Fresh
Artifact / Install Gate. The preflight rehearsal is deliberately outside the artifact session
and must not build Local/Core/MSI artifacts or install/uninstall Sorigul.

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

## Artifact checkpoint / retry policy

A failure is classified by whether artifact identity remains trustworthy, not only by which
stage number failed. A prior PASS stage may be retained when exact source HEAD, artifact
run_id, release-input identity, manifest identity, artifact SHA-256/size and required
self-test evidence are unchanged.

If a later failure is only a harness/invocation error (for example cwd, command construction,
environment forwarding or log collection) and it does not mutate those identities, retry only
the failed stage under the same run_id and record the prior attempt as superseded.

HARD STOP and checkpoint invalidation remain mandatory for source/release-input changes,
artifact content/self-test failure, hash/provenance mismatch, manifest/source ambiguity,
MSI identity ambiguity, install identity ambiguity, protected-user-data mutation,
orphan/port cleanup failure or restoration failure.

## Required official release gate

The order is fixed:

1. source-changing work complete and source regression PASS
2. Release Freeze: exact Release Candidate HEAD
3. canonical #113 preflight rehearsal PASS with no Local/Core/MSI build or install
4. issue new artifact run_id and acquire the Single Writer lock
5. fresh Local Runtime build, isolated CUDA self-test and Local identity/manifest/hash
6. fresh Core build, isolated Core self-test, Core provenance/size/hash and payload exclusions
7. fresh MSI from the same frozen HEAD and current-run Core manifest/hash
8. clean install
9. installed Core/Local provenance pairing and fail-closed Local runtime discovery
10. installed health/process/JobObject
11. installed CUDA synthetic tensor
12. bundled sibling ffmpeg
13. Unicode/temp synthetic scan
14. no-user-data verification
15. only then actual Local MP3 gate
16. optional zero-cost-safe external Colab gate
17. optional zero-cost-safe Drive TXT/JSON/SRT gate
18. Folders/retry/cleanup verification
19. supervised shutdown only with explicit user approval
20. final ledger and #114 Study Workflow Regression

Until the synthetic installed gates pass, the real MP3 gate is blocked. Actual Windows shutdown is
also blocked without immediate explicit user approval.
