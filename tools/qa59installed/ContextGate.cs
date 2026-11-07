// Execution context gate. Pure: the caller supplies the context JSON (repo,
// run, approval record, pre-dispatch cost evidence, external controls).
// Unknown = deny. Cost evidence must predate dispatch; a job checking its own
// cost is too late. Booleans and IDs in the context are claims, not proof:
// execution additionally needs the approval consumption and the budget to be
// enforced by external pre-dispatch controls on a reviewed, compiled-in
// allowlist. That allowlist is empty today, so every context is denied.
using System;
using System.Collections.Generic;
using System.Globalization;

namespace Qa59Installed
{
    public sealed class GateDecision
    {
        public readonly bool ExecutionAllowed;
        public readonly bool MsiDownloadAllowed;
        public readonly bool MsiInstallAllowed;
        public readonly IList<string> Reasons;
        // Bound identities, set only when execution is allowed.
        public readonly string QaCommit;
        public readonly long? RunId;

        internal GateDecision(Outcome outcome, bool downloadApproved, bool installApproved, string qaCommit, long? runId)
        {
#if !QA59_CONTRACT_TESTS
            outcome.Add("EXTERNAL_CONTROL_NOT_IMPLEMENTED");
#endif
            Reasons = outcome.Snapshot().Reasons;
            ExecutionAllowed = outcome.Ok;
            MsiDownloadAllowed = ExecutionAllowed && downloadApproved;
            // Install never stands alone: it needs the download permit too.
            MsiInstallAllowed = MsiDownloadAllowed && installApproved;
            QaCommit = ExecutionAllowed ? qaCommit : null;
            RunId = ExecutionAllowed ? runId : null;
        }
    }

    public static class ContextGate
    {
        public const string Kind = "QA59_EXECUTION_CONTEXT";
        public const string AllowedEvent = "workflow_dispatch";
        private const string RefPrefix = "refs/heads/";
        public static readonly TimeSpan MaxCostEvidenceAge = TimeSpan.FromHours(1);

        // External pre-dispatch controls trusted to (a) atomically consume a
        // single-use approval for exactly one run and (b) enforce 0 KRW before
        // dispatch. None exists yet. Adding one is a reviewed code change,
        // never a context value.
        private static readonly string[] TrustedApprovalControls = new string[0];
        private static readonly string[] TrustedBudgetControls = new string[0];

        private static readonly string[] RootKeys = { "schema", "kind", "repository", "run", "approval", "cost", "controls" };
        private static readonly string[] RepositoryKeys = { "full_name", "id", "owner", "visibility" };
        private static readonly string[] RunKeys = { "run_id", "ref", "sha", "event_name", "run_attempt", "dispatched_at" };
        private static readonly string[] ApprovalKeys =
        {
            "approval_id", "state", "consumed_by_run_id", "repository_id", "repository_full_name", "qa_commit", "ref",
            "event_name", "execution_approved", "msi_download_approved", "msi_install_approved",
        };
        private static readonly string[] CostKeys =
        {
            "maximum_allowed_cost_krw", "paid_usage_approved",
            "free_allowance_verified", "paid_overage_block_verified", "verified_at",
        };
        private static readonly string[] ControlKeys = { "approval_consumption_control", "budget_control" };

        public static GateDecision Evaluate(string text)
        {
            return EvaluateCore(text, TrustedApprovalControls, TrustedBudgetControls);
        }

        // The seam is absent from the production assembly. A test assembly name
        // is forgeable; a test build is never an execution authority.
#if QA59_CONTRACT_TESTS
        internal static GateDecision Evaluate(string text, IList<string> approvalControls, IList<string> budgetControls)
        {
            return EvaluateCore(text, approvalControls, budgetControls);
        }
#endif
        private static GateDecision EvaluateCore(string text, IList<string> approvalControls, IList<string> budgetControls)
        {
            var outcome = new Outcome();
            bool downloadApproved = false;
            bool installApproved = false;
            string qaCommit = null;
            long? runId = null;
            JsonObject root = Fields.ParseObject(text, outcome);
            if (root != null && Fields.ExactKeys(root, RootKeys, outcome, "CONTEXT_"))
            {
                if (!(root.Get("schema") is long) || (long)root.Get("schema") != 2) outcome.Add("CONTEXT_SCHEMA_MISMATCH");
                if (!Kind.Equals(root.Get("kind"))) outcome.Add("CONTEXT_KIND_MISMATCH");
                JsonObject repo = Section(root, "repository", RepositoryKeys, outcome);
                JsonObject run = Section(root, "run", RunKeys, outcome);
                JsonObject approval = Section(root, "approval", ApprovalKeys, outcome);
                JsonObject cost = Section(root, "cost", CostKeys, outcome);
                JsonObject controls = Section(root, "controls", ControlKeys, outcome);
                if (repo != null && run != null && approval != null && cost != null && controls != null)
                {
                    CheckRepository(repo, approval, outcome);
                    CheckRun(run, approval, outcome);
                    CheckApproval(approval, run, outcome);
                    CheckCost(cost, run, outcome);
                    CheckControls(controls, approvalControls, budgetControls, outcome);
                    downloadApproved = true.Equals(approval.Get("msi_download_approved"));
                    installApproved = true.Equals(approval.Get("msi_install_approved"));
                    qaCommit = run.Get("sha") as string;
                    if (run.Get("run_id") is long) runId = (long)run.Get("run_id");
                }
            }
            return new GateDecision(outcome, downloadApproved, installApproved, qaCommit, runId);
        }

        private static JsonObject Section(JsonObject root, string key, string[] keys, Outcome outcome)
        {
            var obj = root.Get(key) as JsonObject;
            if (obj == null) { outcome.Add("CONTEXT_" + key.ToUpperInvariant() + "_NOT_OBJECT"); return null; }
            return Fields.ExactKeys(obj, keys, outcome, "CONTEXT_" + key.ToUpperInvariant() + "_") ? obj : null;
        }

        private static void CheckRepository(JsonObject repo, JsonObject approval, Outcome outcome)
        {
            var fullName = repo.Get("full_name") as string;
            var owner = repo.Get("owner") as string;
            object id = repo.Get("id");
            if (fullName == null || owner == null || !(id is long) || (long)id <= 0)
            {
                outcome.Add("REPOSITORY_UNKNOWN");
                return;
            }
            if (!"private".Equals(repo.Get("visibility"))) outcome.Add("REPOSITORY_NOT_PRIVATE");
            // By ID as well as name: a renamed product repository keeps its ID.
            if (string.Equals(fullName, CandidatePins.ProductRepository, StringComparison.OrdinalIgnoreCase)
                || (long)id == CandidatePins.ProductRepositoryId)
                outcome.Add("REPOSITORY_IS_PRODUCT");
            int slash = fullName.IndexOf('/');
            if (slash <= 0 || slash != fullName.LastIndexOf('/') || slash == fullName.Length - 1
                || !string.Equals(fullName.Substring(0, slash), owner, StringComparison.OrdinalIgnoreCase))
                outcome.Add("REPOSITORY_OWNER_MISMATCH");
            object approvedId = approval.Get("repository_id");
            var approvedName = approval.Get("repository_full_name") as string;
            // ID is authoritative (names can be renamed/recreated); name must agree too.
            if (!(approvedId is long) || (long)approvedId != (long)id
                || approvedName == null || !string.Equals(approvedName, fullName, StringComparison.OrdinalIgnoreCase))
                outcome.Add("REPOSITORY_NOT_APPROVED");
        }

        private static void CheckRun(JsonObject run, JsonObject approval, Outcome outcome)
        {
            var sha = run.Get("sha") as string;
            var approvedSha = approval.Get("qa_commit") as string;
            if (!Fields.IsLowerHex(sha, 40)) outcome.Add("QA_COMMIT_FORMAT");
            else if (sha == CandidatePins.ProductHead) outcome.Add("QA_COMMIT_IS_PRODUCT_HEAD");
            if (sha == null || approvedSha == null || !string.Equals(sha, approvedSha, StringComparison.Ordinal))
                outcome.Add("QA_COMMIT_NOT_APPROVED");

            var gitRef = run.Get("ref") as string;
            var approvedRef = approval.Get("ref") as string;
            if (gitRef == null || !gitRef.StartsWith(RefPrefix, StringComparison.Ordinal) || gitRef.Length == RefPrefix.Length
                || approvedRef == null || !string.Equals(gitRef, approvedRef, StringComparison.Ordinal))
                outcome.Add("REF_NOT_APPROVED");

            var eventName = run.Get("event_name") as string;
            if (eventName != AllowedEvent || !AllowedEvent.Equals(approval.Get("event_name")))
                outcome.Add("EVENT_NOT_APPROVED");

            // attempt 1 stops re-runs of one run; it cannot stop a second
            // dispatch, which also starts at attempt 1. The single-use approval
            // consumption below covers that.
            object attempt = run.Get("run_attempt");
            if (!(attempt is long)) outcome.Add("RUN_ATTEMPT_UNKNOWN");
            else if ((long)attempt != 1) outcome.Add("RERUN_DENIED");
        }

        // In-job view of the single-use approval: it must already be consumed
        // by this exact run. ISSUED here means nothing guarded the dispatch.
        private static void CheckApproval(JsonObject approval, JsonObject run, Outcome outcome)
        {
            if (!SingleUseApproval.IsValidId(approval.Get("approval_id") as string) || !true.Equals(approval.Get("execution_approved")))
                outcome.Add("APPROVAL_MISSING");
            object runId = run.Get("run_id");
            if (!(runId is long) || (long)runId <= 0) { outcome.Add("RUN_ID_UNKNOWN"); return; }
            object consumedBy = approval.Get("consumed_by_run_id");
            string state = approval.Get("state") as string;
            if (state == SingleUseApproval.Issued) outcome.Add("APPROVAL_NOT_CONSUMED");
            else if (state == SingleUseApproval.Revoked) outcome.Add("APPROVAL_REVOKED");
            else if (state != SingleUseApproval.Consumed) outcome.Add("APPROVAL_STATE_UNKNOWN");
            else if (!(consumedBy is long) || (long)consumedBy != (long)runId) outcome.Add("APPROVAL_CONSUMED_BY_OTHER_RUN");
        }

        private static void CheckCost(JsonObject cost, JsonObject run, Outcome outcome)
        {
            object limit = cost.Get("maximum_allowed_cost_krw");
            if (!(limit is long) || (long)limit != 0) outcome.Add("COST_LIMIT_NOT_ZERO");
            // Only the 0 KRW path exists; any paid approval is out of contract.
            if (!false.Equals(cost.Get("paid_usage_approved"))) outcome.Add("PAID_USAGE_NOT_SUPPORTED");
            if (!true.Equals(cost.Get("free_allowance_verified")) || !true.Equals(cost.Get("paid_overage_block_verified")))
                outcome.Add("COST_NOT_VERIFIED");

            DateTime verifiedAt, dispatchedAt;
            bool hasVerified = TryUtc(cost.Get("verified_at"), out verifiedAt);
            bool hasDispatched = TryUtc(run.Get("dispatched_at"), out dispatchedAt);
            if (!hasVerified) outcome.Add("COST_NOT_VERIFIED");
            if (!hasDispatched) outcome.Add("DISPATCH_TIME_UNKNOWN");
            if (hasVerified && hasDispatched && verifiedAt >= dispatchedAt) outcome.Add("COST_NOT_VERIFIED_BEFORE_DISPATCH");
            // Included usage resets per monthly cycle: evidence must be recent
            // and from the same UTC calendar month as the dispatch, or it says
            // nothing about this run's cost.
            if (hasVerified && hasDispatched && verifiedAt < dispatchedAt
                && (dispatchedAt - verifiedAt > MaxCostEvidenceAge
                    || verifiedAt.Year != dispatchedAt.Year || verifiedAt.Month != dispatchedAt.Month))
                outcome.Add("COST_EVIDENCE_STALE");
        }

        private static void CheckControls(JsonObject controls, IList<string> approvalControls, IList<string> budgetControls, Outcome outcome)
        {
            if (!IsTrusted(controls.Get("approval_consumption_control") as string, approvalControls)) outcome.Add("APPROVAL_CONTROL_UNTRUSTED");
            if (!IsTrusted(controls.Get("budget_control") as string, budgetControls)) outcome.Add("BUDGET_CONTROL_UNTRUSTED");
        }

        private static bool IsTrusted(string control, IList<string> trusted)
        {
            if (control == null || trusted == null) return false;
            foreach (string t in trusted)
            {
                if (string.Equals(control, t, StringComparison.Ordinal)) return true;
            }
            return false;
        }

        private static bool TryUtc(object value, out DateTime result)
        {
            result = default(DateTime);
            var text = value as string;
            return text != null && DateTime.TryParseExact(
                text, "yyyy-MM-dd'T'HH:mm:ss'Z'", CultureInfo.InvariantCulture,
                DateTimeStyles.AdjustToUniversal | DateTimeStyles.AssumeUniversal, out result);
        }
    }
}
