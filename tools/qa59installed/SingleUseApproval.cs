// Single-use execution approval. Pure state machine: ISSUED -> CONSUMED(run)
// or REVOKED; CONSUMED -> REVOKED. Nothing ever returns to ISSUED and a
// consumed approval never binds a second run, so a new workflow_dispatch
// (which also starts at run_attempt 1) cannot reuse it.
//
// This only defines the transitions. Real enforcement needs an external
// controller using durable versioned compare-and-swap BEFORE dispatch, outside the job
// it authorizes. Until such a control is reviewed and added to
// ContextGate's trusted list, execution stays BLOCKED.
using System;

namespace Qa59Installed
{
    public sealed class ApprovalRecord
    {
        public readonly string ApprovalId;
        public readonly string State;
        public readonly long? ConsumedByRunId;

        internal ApprovalRecord(string approvalId, string state, long? consumedByRunId)
        {
            ApprovalId = approvalId;
            State = state;
            ConsumedByRunId = consumedByRunId;
        }
    }

    public static class SingleUseApproval
    {
        public const string Issued = "ISSUED";
        public const string Consumed = "CONSUMED";
        public const string Revoked = "REVOKED";
        public const int MaxIdLength = 64;

        // Printable ASCII only: Trim() keeps zero-width and other invisible
        // characters, so an allowlist is the only reliable "non-blank" check.
        public static bool IsValidId(string id)
        {
            if (id == null || id.Length == 0 || id.Length > MaxIdLength) return false;
            foreach (char c in id)
            {
                if (!((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '.' || c == '_' || c == '-'))
                    return false;
            }
            return true;
        }

        public static ApprovalRecord Issue(string approvalId, Outcome outcome)
        {
            if (!IsValidId(approvalId)) { outcome.Add("APPROVAL_ID_INVALID"); return null; }
            return new ApprovalRecord(approvalId, Issued, null);
        }

        // Pure proposal only: calling twice with the same stale ISSUED snapshot
        // can return two proposals. External storage MUST compare-and-swap the
        // expected state AND version; exactly one proposal may be committed.
        // A run ID exists only after dispatch. Stage 2A design adds a reserved
        // state before dispatch; this legacy transition grants no authority.
        public static ApprovalRecord Consume(ApprovalRecord record, long runId, Outcome outcome)
        {
            if (record == null || !IsValidId(record.ApprovalId)) { outcome.Add("APPROVAL_ID_INVALID"); return null; }
            if (runId <= 0) { outcome.Add("RUN_ID_UNKNOWN"); return null; }
            if (record.State == Consumed) { outcome.Add("APPROVAL_ALREADY_CONSUMED"); return null; }
            if (record.State == Revoked) { outcome.Add("APPROVAL_REVOKED"); return null; }
            if (record.State != Issued || record.ConsumedByRunId.HasValue) { outcome.Add("APPROVAL_STATE_UNKNOWN"); return null; }
            return new ApprovalRecord(record.ApprovalId, Consumed, runId);
        }

        public static ApprovalRecord Revoke(ApprovalRecord record, Outcome outcome)
        {
            if (record == null || !IsValidId(record.ApprovalId)) { outcome.Add("APPROVAL_ID_INVALID"); return null; }
            if (record.State == Revoked) { outcome.Add("APPROVAL_REVOKED"); return null; }
            if (record.State != Issued && record.State != Consumed) { outcome.Add("APPROVAL_STATE_UNKNOWN"); return null; }
            return new ApprovalRecord(record.ApprovalId, Revoked, record.ConsumedByRunId);
        }
    }
}
