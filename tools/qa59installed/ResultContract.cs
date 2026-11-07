// Result schema and supervisor verdict latch. Pure: no I/O.
// A result document holds only fixed ids, verdict/reason enums, booleans,
// bounded counts and pinned hex identities: no free text, so raw exceptions,
// stdout, paths, environment or screen content cannot be represented.
// Verdicts are derived from evidence; a step may declare worse, never better.
using System;
using System.Collections.Generic;

namespace Qa59Installed
{
    public sealed class EvidenceSpec
    {
        public readonly string Key;
        public readonly bool IsCount;
        public readonly long ExpectedCount;

        private EvidenceSpec(string key, bool isCount, long expected) { Key = key; IsCount = isCount; ExpectedCount = expected; }
        public static EvidenceSpec True(string key) { return new EvidenceSpec(key, false, 0); }
        public static EvidenceSpec Count(string key, long expected) { return new EvidenceSpec(key, true, expected); }
    }

    public sealed class StepSpec
    {
        public readonly string Id;
        public readonly EvidenceSpec[] Evidence;
        public StepSpec(string id, params EvidenceSpec[] evidence) { Id = id; Evidence = evidence; }
    }

    public sealed class ResultValidation
    {
        public readonly Outcome Outcome = new Outcome();
        public Verdict? Overall;
        public Verdict? Cleanup;
        public string QaCommit;

        // An invalid document proves nothing: it is never PASS.
        public Verdict EffectiveOverall
        {
            get { return Outcome.Ok && Overall.HasValue ? Overall.Value : Verdict.NOT_VERIFIED; }
        }
    }

    public static class ResultContract
    {
        public const string Kind = "QA59_INSTALLED_RESULT";
        public const long Schema = 2;
        public const int MaxLength = 64 * 1024;
        public const long MaxCount = 4096;

        public static readonly StepSpec[] Steps =
        {
            new StepSpec("S01_MSI_HASH_SIZE", EvidenceSpec.True("msi_sha256_match"), EvidenceSpec.True("msi_size_match")),
            // 3010/1641 (reboot) are not normal completion: only exit 0 passes.
            new StepSpec("S02_RUNNER_INSTALL", EvidenceSpec.True("clean_runner"), EvidenceSpec.Count("install_exit_code", 0)),
            new StepSpec("S03_PRODUCT_REGISTRATION", EvidenceSpec.True("product_registered"), EvidenceSpec.True("installed_hashes_match"), EvidenceSpec.True("manifest_source_head_match")),
            new StepSpec("S04_DESKTOP_LAUNCH", EvidenceSpec.True("suspended_contained"), EvidenceSpec.True("token_not_inherited")),
            new StepSpec("S05_MAIN_WEBVIEW", EvidenceSpec.True("main_webview_unique"), EvidenceSpec.True("source_unchanged")),
            new StepSpec("S06_IDLE_A", EvidenceSpec.True("fixture_a_valid"), EvidenceSpec.True("ui_folder_a"), EvidenceSpec.True("ui_jobs_a")),
            new StepSpec("S07_BACKEND_OFFLINE", EvidenceSpec.True("backend_only_stopped"), EvidenceSpec.True("descendants_released"), EvidenceSpec.True("ui_offline")),
            // One logical user click = one SendInput down + one up. Requested
            // events and events SendInput reported as inserted are counted
            // separately, so a partial or blocked injection cannot pass.
            // Delivery is not button success: the actual ONLINE recovery is S09.
            new StepSpec("S08_RESTART_CLICK", EvidenceSpec.Count("user_click_count", 1), EvidenceSpec.Count("sendinput_events_requested", 2),
                EvidenceSpec.Count("sendinput_events_inserted", 2), EvidenceSpec.True("foreground_hit_target")),
            new StepSpec("S09_ONLINE_SYNC_B", EvidenceSpec.Count("backend_roots", 1), EvidenceSpec.True("owned_listener"), EvidenceSpec.True("ui_folder_b"), EvidenceSpec.True("ui_jobs_b")),
            new StepSpec("S10_NEGATIVE_MATRIX", EvidenceSpec.True("negative_matrix_pass")),
            new StepSpec("S11_TRAY_EXIT", EvidenceSpec.True("tray_exit_online"), EvidenceSpec.True("tray_exit_offline")),
            new StepSpec("S12_CENTRAL_CLEANUP", EvidenceSpec.True("normal_product_exit"), EvidenceSpec.Count("residual_processes", 0), EvidenceSpec.Count("residual_tcp", 0), EvidenceSpec.Count("residual_udp", 0)),
        };

        public static readonly StepSpec[] Negatives =
        {
            new StepSpec("N01_DUPLICATE_RESTART", EvidenceSpec.True("second_input_observed"), EvidenceSpec.True("busy_block_observed"), EvidenceSpec.Count("backend_roots_max", 1)),
            new StepSpec("N02_ACTIVE_JOB", EvidenceSpec.True("ui_reason_shown"), EvidenceSpec.Count("spawn_count", 0), EvidenceSpec.True("fixture_preserved")),
            new StepSpec("N03_ACTIVE_DRIVE", EvidenceSpec.True("ui_reason_shown"), EvidenceSpec.Count("spawn_count", 0), EvidenceSpec.True("fixture_preserved"), EvidenceSpec.Count("external_drive_calls", 0)),
            new StepSpec("N04_UNKNOWN_ENUM", EvidenceSpec.True("ui_reason_shown"), EvidenceSpec.Count("spawn_count", 0), EvidenceSpec.True("fixture_preserved")),
            new StepSpec("N05_JOB_STATE_UNKNOWN", EvidenceSpec.True("ui_reason_shown"), EvidenceSpec.Count("spawn_count", 0), EvidenceSpec.True("fixture_preserved")),
            new StepSpec("N06_OTHER_LISTENER", EvidenceSpec.True("ui_reason_shown"), EvidenceSpec.Count("spawn_count", 0), EvidenceSpec.True("own_listener_released")),
            new StepSpec("N07_LIVE_BACKEND", EvidenceSpec.True("restart_hidden_or_disabled"), EvidenceSpec.Count("spawn_count", 0), EvidenceSpec.True("backend_pid_unchanged")),
        };

        public static readonly string[] ReasonCodes =
        {
            "EVIDENCE_MISSING", "EXPECTATION_UNMET", "DEADLINE_EXCEEDED", "UIA_WORKER_HUNG",
            "PROVIDER_FAILED", "FORCED_CLEANUP", "SKIPPED", "PRECONDITION_FAILED",
            "STOPPED_BY_GATE", "SELECTOR_NOT_UNIQUE", "NOT_RUN",
        };

        private static readonly string[] RootKeys =
        {
            "schema", "kind", "product_head", "msi_sha256", "qa_commit",
            "steps", "negatives", "supervisor", "cleanup", "overall",
        };
        private static readonly string[] RecordKeys = { "id", "verdict", "reason", "evidence" };
        private static readonly string[] SupervisorFlags =
        {
            "deadline_exceeded", "uia_worker_hung", "provider_failed", "forced_cleanup_used", "job_close_kill_used",
        };
        private static readonly string[] SupervisorCounts =
        {
            "skipped_steps", "late_results", "residual_processes", "residual_tcp", "residual_udp",
        };
        private static readonly string[] CleanupKeys = { "verdict", "harness_resources_released", "fixtures_restored" };

        public static bool IsReason(string value)
        {
            return value != null && Array.IndexOf(ReasonCodes, value) >= 0;
        }

        public static Verdict? ParseVerdict(object value)
        {
            var text = value as string;
            if (text == "PASS") return Verdict.PASS;
            if (text == "FAIL") return Verdict.FAIL;
            if (text == "NOT_VERIFIED") return Verdict.NOT_VERIFIED;
            return null;
        }

        public static string Name(Verdict verdict)
        {
            return verdict == Verdict.PASS ? "PASS" : verdict == Verdict.FAIL ? "FAIL" : "NOT_VERIFIED";
        }

        // Unmeasured evidence (null) can never yield PASS.
        public static Verdict Derive(StepSpec spec, JsonObject evidence)
        {
            Verdict worst = Verdict.PASS;
            foreach (EvidenceSpec e in spec.Evidence)
            {
                object value = evidence.Get(e.Key);
                Verdict v;
                if (value == null || value is JsonNull) v = Verdict.NOT_VERIFIED;
                else if (e.IsCount) v = value is long && (long)value == e.ExpectedCount ? Verdict.PASS : Verdict.FAIL;
                else v = true.Equals(value) ? Verdict.PASS : Verdict.FAIL;
                if (v > worst) worst = v;
            }
            return worst;
        }

        public static ResultValidation Validate(string text)
        {
            var result = new ResultValidation();
            Outcome outcome = result.Outcome;
            if (text != null && text.Length > MaxLength) { outcome.Add("RESULT_TOO_LARGE"); return result; }
            JsonObject root = Fields.ParseObject(text, outcome);
            if (root == null || !Fields.ExactKeys(root, RootKeys, outcome, "RESULT_")) return result;

            // Schema 2: S08 split into click / requested / inserted input counts.
            if (!(root.Get("schema") is long) || (long)root.Get("schema") != Schema) outcome.Add("RESULT_SCHEMA_MISMATCH");
            if (!Kind.Equals(root.Get("kind"))) outcome.Add("RESULT_KIND_MISMATCH");
            if (!CandidatePins.ProductHead.Equals(root.Get("product_head"))) outcome.Add("RESULT_PRODUCT_HEAD_MISMATCH");
            if (!CandidatePins.MsiSha256.Equals(root.Get("msi_sha256"))) outcome.Add("RESULT_MSI_MISMATCH");
            var qaCommit = root.Get("qa_commit") as string;
            if (!Fields.IsLowerHex(qaCommit, 40)) outcome.Add("RESULT_QA_COMMIT_FORMAT");
            else if (qaCommit == CandidatePins.ProductHead) outcome.Add("RESULT_QA_COMMIT_IS_PRODUCT_HEAD");

            Verdict worst = Verdict.PASS;
            bool negativesAllPass, unused;
            Verdict negativeWorst = Records(root.Get("negatives"), Negatives, outcome, null, out negativesAllPass);
            Verdict stepWorst = Records(root.Get("steps"), Steps, outcome, negativesAllPass, out unused);
            if (negativeWorst > worst) worst = negativeWorst;
            if (stepWorst > worst) worst = stepWorst;

            Verdict supervisor = Supervisor(root.Get("supervisor"), outcome);
            if (supervisor > worst) worst = supervisor;
            result.Cleanup = Cleanup(root.Get("cleanup"), outcome);

            Verdict? declared = ParseVerdict(root.Get("overall"));
            if (!declared.HasValue) outcome.Add("RESULT_OVERALL_INVALID");
            else if (declared.Value != worst) outcome.Add("RESULT_OVERALL_MISMATCH");
            if (outcome.Ok) { result.Overall = worst; result.QaCommit = qaCommit; }
            return result;
        }

        // negativesAllPass (input) is checked against S10's own evidence so the
        // summary step cannot claim a matrix pass the negatives do not show.
        private static Verdict Records(object value, StepSpec[] specs, Outcome outcome, bool? negativesAllPass, out bool allPass)
        {
            allPass = false;
            var list = value as List<object>;
            if (list == null || list.Count != specs.Length) { outcome.Add("RESULT_RECORD_COUNT"); return Verdict.FAIL; }
            Verdict worst = Verdict.PASS;
            for (int k = 0; k < specs.Length; k++)
            {
                // Every structural defect records a reason so the document is invalid, never silently FAIL.
                var record = list[k] as JsonObject;
                if (record == null) { outcome.Add("RESULT_RECORD_NOT_OBJECT"); worst = Verdict.FAIL; continue; }
                if (!Fields.ExactKeys(record, RecordKeys, outcome, "RESULT_RECORD_")) { worst = Verdict.FAIL; continue; }
                if (!specs[k].Id.Equals(record.Get("id"))) { outcome.Add("RESULT_RECORD_ORDER"); worst = Verdict.FAIL; continue; }
                var evidence = record.Get("evidence") as JsonObject;
                if (evidence == null) { outcome.Add("RESULT_EVIDENCE_NOT_OBJECT"); worst = Verdict.FAIL; continue; }
                if (!EvidenceShape(specs[k], evidence, outcome)) { worst = Verdict.FAIL; continue; }

                Verdict derived = Derive(specs[k], evidence);
                Verdict? declared = ParseVerdict(record.Get("verdict"));
                object reason = record.Get("reason");
                if (!declared.HasValue) { outcome.Add("RESULT_VERDICT_INVALID"); worst = Verdict.FAIL; continue; }
                if (declared.Value < derived) outcome.Add("RESULT_VERDICT_PROMOTED");
                if (declared.Value == Verdict.PASS ? !(reason is JsonNull) : !IsReason(reason as string))
                    outcome.Add("RESULT_REASON_INVALID");
                if (negativesAllPass.HasValue && specs[k].Id == "S10_NEGATIVE_MATRIX"
                    && true.Equals(evidence.Get("negative_matrix_pass")) && !negativesAllPass.Value)
                    outcome.Add("RESULT_S10_INCONSISTENT");
                Verdict effective = declared.Value > derived ? declared.Value : derived;
                if (effective > worst) worst = effective;
            }
            allPass = worst == Verdict.PASS && outcome.Ok;
            return worst;
        }

        private static bool EvidenceShape(StepSpec spec, JsonObject evidence, Outcome outcome)
        {
            var keys = new string[spec.Evidence.Length];
            for (int k = 0; k < keys.Length; k++) keys[k] = spec.Evidence[k].Key;
            if (!Fields.ExactKeys(evidence, keys, outcome, "RESULT_EVIDENCE_")) return false;
            bool ok = true;
            foreach (EvidenceSpec e in spec.Evidence)
            {
                object value = evidence.Get(e.Key);
                if (value is JsonNull) continue;
                // install_exit_code is an exit code (3010, negative HRESULTs), not a bounded count.
                bool exitCode = e.Key == "install_exit_code";
                bool typed = e.IsCount
                    ? value is long && (exitCode || ((long)value >= 0 && (long)value <= MaxCount))
                    : value is bool;
                if (!typed) { outcome.Add("RESULT_EVIDENCE_TYPE"); ok = false; }
            }
            return ok;
        }

        private static Verdict Supervisor(object value, Outcome outcome)
        {
            var obj = value as JsonObject;
            var keys = new List<string>(SupervisorFlags);
            keys.AddRange(SupervisorCounts);
            keys.Add("normal_product_exit");
            if (obj == null) { outcome.Add("RESULT_SUPERVISOR_NOT_OBJECT"); return Verdict.NOT_VERIFIED; }
            if (!Fields.ExactKeys(obj, keys.ToArray(), outcome, "RESULT_SUPERVISOR_")) return Verdict.NOT_VERIFIED;

            Verdict worst = Verdict.PASS;
            foreach (string key in SupervisorFlags)
            {
                object v = obj.Get(key);
                if (v is JsonNull) { if (worst < Verdict.NOT_VERIFIED) worst = Verdict.NOT_VERIFIED; }
                else if (!(v is bool)) outcome.Add("RESULT_SUPERVISOR_TYPE");
                // Timeout, hang, provider failure or forced cleanup cannot be a normal PASS.
                else if ((bool)v && worst < Verdict.NOT_VERIFIED) worst = Verdict.NOT_VERIFIED;
            }
            foreach (string key in SupervisorCounts)
            {
                object v = obj.Get(key);
                if (v is JsonNull) { if (worst < Verdict.NOT_VERIFIED) worst = Verdict.NOT_VERIFIED; continue; }
                if (!(v is long) || (long)v < 0 || (long)v > MaxCount) { outcome.Add("RESULT_SUPERVISOR_TYPE"); continue; }
                long count = (long)v;
                if (key.StartsWith("residual_", StringComparison.Ordinal) && count > 0) worst = Verdict.FAIL;
                else if (key == "skipped_steps" && count > 0 && worst < Verdict.NOT_VERIFIED) worst = Verdict.NOT_VERIFIED;
                // late_results is informational: late records were already discarded by the latch.
            }
            object exit = obj.Get("normal_product_exit");
            if (exit is JsonNull) { if (worst < Verdict.NOT_VERIFIED) worst = Verdict.NOT_VERIFIED; }
            else if (!(exit is bool)) outcome.Add("RESULT_SUPERVISOR_TYPE");
            else if (!(bool)exit) worst = Verdict.FAIL;
            return worst;
        }

        // Harness cleanup is reported on its own; success never upgrades the test verdict.
        private static Verdict? Cleanup(object value, Outcome outcome)
        {
            var obj = value as JsonObject;
            if (obj == null) { outcome.Add("RESULT_CLEANUP_NOT_OBJECT"); return null; }
            if (!Fields.ExactKeys(obj, CleanupKeys, outcome, "RESULT_CLEANUP_")) return null;
            Verdict derived = Verdict.PASS;
            foreach (string key in new[] { "harness_resources_released", "fixtures_restored" })
            {
                object v = obj.Get(key);
                Verdict item = v is JsonNull ? Verdict.NOT_VERIFIED : true.Equals(v) ? Verdict.PASS : Verdict.FAIL;
                if (!(v is JsonNull) && !(v is bool)) outcome.Add("RESULT_CLEANUP_TYPE");
                if (item > derived) derived = item;
            }
            Verdict? declared = ParseVerdict(obj.Get("verdict"));
            if (!declared.HasValue || declared.Value != derived) { outcome.Add("RESULT_CLEANUP_MISMATCH"); return null; }
            return derived;
        }
    }

    // Supervisor-side latch. The supervisor (not the UIA worker) owns Freeze:
    // at the deadline every unrecorded id becomes NOT_VERIFIED and later
    // records are counted and discarded, so a late result cannot turn
    // FAIL or NOT_VERIFIED into PASS. Within an id the worst record wins.
    public sealed class VerdictLatch
    {
        private readonly object sync = new object();
        private readonly HashSet<string> ids;
        private readonly Dictionary<string, Verdict> verdicts = new Dictionary<string, Verdict>(StringComparer.Ordinal);
        private readonly Dictionary<string, string> reasons = new Dictionary<string, string>(StringComparer.Ordinal);
        private bool frozen;
        private int late;

        public VerdictLatch(IEnumerable<string> knownIds)
        {
            ids = new HashSet<string>(knownIds, StringComparer.Ordinal);
        }

        public bool IsFrozen { get { lock (sync) return frozen; } }
        public int LateResults { get { lock (sync) return late; } }

        public bool Record(string id, Verdict verdict, string reason)
        {
            if (id == null || !ids.Contains(id)) throw new ArgumentException("UNKNOWN_RESULT_ID");
            if (verdict == Verdict.PASS ? reason != null : !ResultContract.IsReason(reason))
                throw new ArgumentException("RESULT_REASON_INVALID");
            lock (sync)
            {
                if (frozen) { late++; return false; }
                Verdict existing;
                if (verdicts.TryGetValue(id, out existing) && existing >= verdict) return false;
                verdicts[id] = verdict;
                reasons[id] = reason;
                return true;
            }
        }

        public void Freeze(string pendingReason)
        {
            if (!ResultContract.IsReason(pendingReason)) throw new ArgumentException("RESULT_REASON_INVALID");
            lock (sync)
            {
                if (frozen) return;
                foreach (string id in ids)
                {
                    if (!verdicts.ContainsKey(id)) { verdicts[id] = Verdict.NOT_VERIFIED; reasons[id] = pendingReason; }
                }
                frozen = true;
            }
        }

        public Verdict? Get(string id)
        {
            lock (sync)
            {
                Verdict v;
                return verdicts.TryGetValue(id, out v) ? v : (Verdict?)null;
            }
        }

        public string ReasonOf(string id)
        {
            lock (sync)
            {
                string r;
                return reasons.TryGetValue(id, out r) ? r : null;
            }
        }
    }
}
