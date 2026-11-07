// Top-level #59 installed acceptance. Pure. Four independent parts, each
// reported on its own, and acceptance is the worst of them:
//   product   - validated result document, every step/negative/supervisor PASS
//   cleanup   - the independent harness cleanup verdict
//   run       - the gate allowed MSI install for this run, and the run ID and
//               QA SHA observed at execution match the gate and the result
//   msi       - the bytes actually installed are the pinned candidate MSI
// Cleanup never upgrades a product failure, and a product PASS never hides
// a cleanup failure. Under today's empty trusted-control list the run part
// cannot pass, so acceptance cannot pass either.
using System;
using System.Collections.Generic;

namespace Qa59Installed
{
    // Facts observed by the runtime at execution time (not read from the
    // result document). Null = not measured.
    public sealed class ExecutionEvidence
    {
        public long? RunId;
        public string QaCommit;
        public string MsiSha256;
        public long? MsiSizeBytes;
    }

    public sealed class AcceptanceDecision
    {
        public Verdict Product = Verdict.NOT_VERIFIED;
        public Verdict Cleanup = Verdict.NOT_VERIFIED;
        public Verdict Run = Verdict.NOT_VERIFIED;
        public Verdict Msi = Verdict.NOT_VERIFIED;
        public readonly Outcome Outcome = new Outcome();

        public Verdict Acceptance
        {
            get
            {
                Verdict worst = Product;
                foreach (Verdict v in new[] { Cleanup, Run, Msi })
                {
                    if (v > worst) worst = v;
                }
                return worst;
            }
        }
    }

    public static class AcceptanceGate
    {
        public static AcceptanceDecision Evaluate(string resultText, string manifestText, string contextText, ExecutionEvidence evidence)
        {
            return Evaluate(resultText, manifestText, ContextGate.Evaluate(contextText), evidence);
        }

        internal static AcceptanceDecision Evaluate(string resultText, string manifestText, GateDecision gate, ExecutionEvidence evidence)
        {
            var decision = new AcceptanceDecision();
            Outcome reasons = decision.Outcome;

            ResultValidation result = ResultContract.Validate(resultText);
            if (!result.Outcome.Ok || !result.Overall.HasValue) reasons.Add("RESULT_INVALID");
            else
            {
                decision.Product = result.Overall.Value;
                if (result.Cleanup.HasValue) decision.Cleanup = result.Cleanup.Value;
            }
            if (decision.Product != Verdict.PASS) reasons.Add("PRODUCT_" + ResultContract.Name(decision.Product));
            if (decision.Cleanup != Verdict.PASS) reasons.Add("CLEANUP_" + ResultContract.Name(decision.Cleanup));

            decision.Run = RunVerdict(gate, evidence, result, reasons);

            CandidateManifest manifest = CandidateManifest.Validate(manifestText, new Outcome());
            if (manifest == null) { reasons.Add("MANIFEST_INVALID"); decision.Msi = Verdict.FAIL; }
            else if (evidence == null) { reasons.Add("MSI_NOT_MEASURED"); decision.Msi = Verdict.NOT_VERIFIED; }
            else
            {
                decision.Msi = Observation.Msi(manifest, evidence.MsiSha256, evidence.MsiSizeBytes);
                if (decision.Msi == Verdict.FAIL) reasons.Add("MSI_NOT_CANDIDATE");
                else if (decision.Msi == Verdict.NOT_VERIFIED) reasons.Add("MSI_NOT_MEASURED");
            }
            return decision;
        }

        private static Verdict RunVerdict(GateDecision gate, ExecutionEvidence evidence, ResultValidation result, Outcome reasons)
        {
            // An unauthorized run is a FAIL, not a gap: it should not have happened.
            if (gate == null || !gate.MsiInstallAllowed || gate.QaCommit == null || !gate.RunId.HasValue)
            {
                reasons.Add("RUN_NOT_AUTHORIZED");
                return Verdict.FAIL;
            }
            if (evidence == null || !evidence.RunId.HasValue || evidence.QaCommit == null)
            {
                reasons.Add("EXECUTION_EVIDENCE_MISSING");
                return Verdict.NOT_VERIFIED;
            }
            Verdict verdict = Verdict.PASS;
            if (evidence.RunId.Value != gate.RunId.Value) { reasons.Add("RUN_ID_MISMATCH"); verdict = Verdict.FAIL; }
            if (!string.Equals(evidence.QaCommit, gate.QaCommit, StringComparison.Ordinal)) { reasons.Add("QA_COMMIT_MISMATCH"); verdict = Verdict.FAIL; }
            if (result.QaCommit == null)
            {
                if (verdict == Verdict.PASS) verdict = Verdict.NOT_VERIFIED;
            }
            else if (!string.Equals(result.QaCommit, gate.QaCommit, StringComparison.Ordinal))
            {
                reasons.Add("RESULT_QA_COMMIT_MISMATCH");
                verdict = Verdict.FAIL;
            }
            return verdict;
        }
    }
}
