using System;
using System.Collections.Generic;

namespace Qa59Installed.Runtime
{
    internal static class EvidenceBridge
    {
        private static JsonMap EmptyEvidence(StepSpec spec)
        {
            var evidence = new JsonMap();
            foreach (EvidenceSpec item in spec.Evidence) evidence.TryAdd(item.Key, JsonNull.Value);
            return evidence;
        }

        internal static JsonMap Record(StepSpec spec)
        {
            var record = new JsonMap();
            record.TryAdd("id", spec.Id);
            record.TryAdd("verdict", "NOT_VERIFIED");
            record.TryAdd("reason", "EVIDENCE_MISSING");
            record.TryAdd("evidence", EmptyEvidence(spec));
            return record;
        }

        // Supplied JSON is never an observation. Synthetic measurements prove
        // harness behavior only; they cannot populate installed-product PASSes.
        // No public API takes paths, stdout, exceptions, credentials or free text
        // to include in a result. The only identity accepted is a checked SHA.
        internal static string InstalledResult(string qaSha, SupervisorObservation supervisor)
        {
            if (qaSha == null || qaSha.Length != 40 || qaSha == CandidatePins.ProductHead) throw new BoundaryException();
            foreach (char c in qaSha) if (!(c >= '0' && c <= '9') && !(c >= 'a' && c <= 'f')) throw new BoundaryException();
            var result = new JsonMap();
            result.TryAdd("schema", ResultContract.Schema);
            result.TryAdd("kind", ResultContract.Kind);
            result.TryAdd("product_head", CandidatePins.ProductHead);
            result.TryAdd("qa_commit", qaSha);
            result.TryAdd("msi_sha256", CandidatePins.MsiSha256); // identity pin, not observed bytes
            var steps = new List<object>();
            foreach (StepSpec spec in ResultContract.Steps) steps.Add(Record(spec));
            var negatives = new List<object>();
            foreach (StepSpec spec in ResultContract.Negatives) negatives.Add(Record(spec));
            result.TryAdd("steps", steps); result.TryAdd("negatives", negatives);
            var flags = new JsonMap();
            flags.TryAdd("deadline_exceeded", supervisor == null ? (object)JsonNull.Value : supervisor.DeadlineExceeded);
            // A deadline alone does not prove which provider hung.
            flags.TryAdd("uia_worker_hung", JsonNull.Value);
            flags.TryAdd("provider_failed", supervisor == null ? (object)JsonNull.Value : supervisor.ProviderFailed);
            flags.TryAdd("forced_cleanup_used", supervisor == null ? (object)JsonNull.Value : supervisor.ForcedCleanup);
            flags.TryAdd("job_close_kill_used", JsonNull.Value);
            flags.TryAdd("normal_product_exit", JsonNull.Value); // synthetic worker exit is not product exit
            foreach (string key in new[] { "skipped_steps", "late_results", "residual_processes", "residual_tcp", "residual_udp" })
                flags.TryAdd(key, JsonNull.Value);
            result.TryAdd("supervisor", flags);
            var cleanup = new JsonMap();
            cleanup.TryAdd("verdict", "NOT_VERIFIED");
            cleanup.TryAdd("harness_resources_released", JsonNull.Value);
            cleanup.TryAdd("fixtures_restored", JsonNull.Value);
            result.TryAdd("cleanup", cleanup);
            result.TryAdd("overall", "NOT_VERIFIED");
            string text = result.Text();
            ResultValidation validation = ResultContract.Validate(text);
            if (!validation.Outcome.Ok || validation.EffectiveOverall != Verdict.NOT_VERIFIED) throw new BoundaryException();
            return text;
        }
    }
}
