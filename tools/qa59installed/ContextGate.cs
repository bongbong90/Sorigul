// Execution context gate. Pure: the caller supplies the context JSON (repo,
// run, approval record, pre-dispatch cost evidence). Unknown = deny. Cost
// evidence must predate dispatch; a job checking its own cost is too late.
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

        internal GateDecision(Outcome outcome, bool downloadApproved, bool installApproved)
        {
            Reasons = outcome.Reasons;
            ExecutionAllowed = outcome.Ok;
            MsiDownloadAllowed = ExecutionAllowed && downloadApproved;
            // Install never stands alone: it needs the download permit too.
            MsiInstallAllowed = MsiDownloadAllowed && installApproved;
        }
    }

    public static class ContextGate
    {
        public const string Kind = "QA59_EXECUTION_CONTEXT";
        public const string AllowedEvent = "workflow_dispatch";
        private const string RefPrefix = "refs/heads/";

        private static readonly string[] RootKeys = { "schema", "kind", "repository", "run", "approval", "cost" };
        private static readonly string[] RepositoryKeys = { "full_name", "id", "owner", "visibility" };
        private static readonly string[] RunKeys = { "ref", "sha", "event_name", "run_attempt", "dispatched_at" };
        private static readonly string[] ApprovalKeys =
        {
            "approval_id", "repository_id", "repository_full_name", "qa_commit", "ref", "event_name",
            "execution_approved", "msi_download_approved", "msi_install_approved",
        };
        private static readonly string[] CostKeys =
        {
            "maximum_allowed_cost_krw", "paid_usage_approved",
            "free_allowance_verified", "paid_overage_block_verified", "verified_at",
        };

        public static GateDecision Evaluate(string text)
        {
            var outcome = new Outcome();
            bool downloadApproved = false;
            bool installApproved = false;
            JsonObject root = Fields.ParseObject(text, outcome);
            if (root != null && Fields.ExactKeys(root, RootKeys, outcome, "CONTEXT_"))
            {
                if (!(root.Get("schema") is long) || (long)root.Get("schema") != 1) outcome.Add("CONTEXT_SCHEMA_MISMATCH");
                if (!Kind.Equals(root.Get("kind"))) outcome.Add("CONTEXT_KIND_MISMATCH");
                JsonObject repo = Section(root, "repository", RepositoryKeys, outcome);
                JsonObject run = Section(root, "run", RunKeys, outcome);
                JsonObject approval = Section(root, "approval", ApprovalKeys, outcome);
                JsonObject cost = Section(root, "cost", CostKeys, outcome);
                if (repo != null && run != null && approval != null && cost != null)
                {
                    CheckRepository(repo, approval, outcome);
                    CheckRun(run, approval, outcome);
                    CheckApproval(approval, outcome);
                    CheckCost(cost, run, outcome);
                    downloadApproved = true.Equals(approval.Get("msi_download_approved"));
                    installApproved = true.Equals(approval.Get("msi_install_approved"));
                }
            }
            return new GateDecision(outcome, downloadApproved, installApproved);
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
            if (string.Equals(fullName, CandidatePins.ProductRepository, StringComparison.OrdinalIgnoreCase))
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

            object attempt = run.Get("run_attempt");
            if (!(attempt is long)) outcome.Add("RUN_ATTEMPT_UNKNOWN");
            else if ((long)attempt != 1) outcome.Add("RERUN_DENIED");
        }

        private static void CheckApproval(JsonObject approval, Outcome outcome)
        {
            var id = approval.Get("approval_id") as string;
            if (string.IsNullOrEmpty(id) || !true.Equals(approval.Get("execution_approved")))
                outcome.Add("APPROVAL_MISSING");
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
