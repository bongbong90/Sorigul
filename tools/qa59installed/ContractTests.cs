// Pure unit tests for the #59 installed-QA contracts. No GUI, network,
// process, registry or product access; the only I/O is reading the two
// committed JSON inputs next to this file. Exit code 0 only if every suite passes.
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;

namespace Qa59Installed
{
    public static class ContractTests
    {
        private static readonly Dictionary<string, int[]> suites = new Dictionary<string, int[]>();
        private static readonly List<string> suiteOrder = new List<string>();
        private static string suite;

        private const string Root = "D:\\a\\_temp\\qa59-fixture-0123456789abcdef0123456789abcdef";
        private static readonly string[] Protected =
        {
            "C:\\Users\\runneradmin\\AppData\\Local\\Sorigul",
            "C:\\Users\\runneradmin\\Desktop",
            "C:\\Program Files\\Sorigul",
        };
        private const string QaSha = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";

        public static int Main(string[] args)
        {
            if (args.Length != 1) { Console.WriteLine("usage: ContractTests <tools/qa59installed dir>"); return 2; }
            string dir = args[0];
            string manifestText = File.ReadAllText(Path.Combine(dir, "candidate-manifest.json"), Encoding.UTF8);
            string contextText = File.ReadAllText(Path.Combine(dir, "current-execution-context.json"), Encoding.UTF8);

            Suite("StrictJson"); JsonTests();
            Suite("Manifest Validation"); ManifestTests(manifestText);
            Suite("Context Gate"); GateTests(contextText, manifestText);
            Suite("Result Schema"); ResultTests();
            Suite("Synthetic Fixture"); FixtureTests();

            int failed = 0;
            foreach (string name in suiteOrder)
            {
                int[] c = suites[name];
                failed += c[1];
                Console.WriteLine("SUITE " + name + " = " + (c[1] == 0 && c[0] > 0 ? "PASS" : "FAIL") + " (" + c[0] + " checks, " + c[1] + " failed)");
            }
            Console.WriteLine(failed == 0 ? "ALL PASS" : "FAILED " + failed);
            return failed == 0 ? 0 : 1;
        }

        private static void Suite(string name) { suite = name; suites[name] = new int[2]; suiteOrder.Add(name); }

        private static void Check(string name, bool condition)
        {
            suites[suite][0]++;
            if (!condition) { suites[suite][1]++; Console.WriteLine("FAIL [" + suite + "] " + name); }
        }

        private static bool Throws(Action action, string code)
        {
            try { action(); return false; }
            catch (JsonFormatException e) { return code == null || e.Code == code; }
        }

        private static JsonObject Obj(string text) { return (JsonObject)StrictJson.Parse(text); }

        // ---- StrictJson ---------------------------------------------------

        private static void JsonTests()
        {
            Check("parses nested values", ((JsonObject)StrictJson.Parse("{\"a\":[1,-2.5,true,null,\"\\u00e9\"]}")).Has("a"));
            Check("integer is long", StrictJson.Parse("70606848") is long);
            Check("fraction is double", StrictJson.Parse("1.0") is double);
            Check("null distinct from missing", Obj("{\"a\":null}").Get("a") is JsonNull && Obj("{}").Get("a") == null);
            Check("duplicate key", Throws(() => StrictJson.Parse("{\"a\":1,\"a\":1}"), "JSON_DUPLICATE_KEY"));
            Check("trailing comma", Throws(() => StrictJson.Parse("{\"a\":1,}"), null));
            Check("trailing data", Throws(() => StrictJson.Parse("{} {}"), "JSON_TRAILING_DATA"));
            Check("NaN", Throws(() => StrictJson.Parse("NaN"), null));
            Check("leading zero", Throws(() => StrictJson.Parse("01"), "JSON_TRAILING_DATA"));
            Check("bare minus", Throws(() => StrictJson.Parse("-"), null));
            Check("integer overflow", Throws(() => StrictJson.Parse("9223372036854775808"), "JSON_INTEGER_OUT_OF_RANGE"));
            Check("control character", Throws(() => StrictJson.Parse("\"a\nb\""), "JSON_CONTROL_CHARACTER"));
            Check("lone surrogate", Throws(() => StrictJson.Parse("\"\\ud800\""), "JSON_UNPAIRED_SURROGATE"));
            Check("paired surrogate ok", ((string)StrictJson.Parse("\"\\ud83d\\ude00\"")).Length == 2);
            Check("BOM rejected", Throws(() => StrictJson.Parse("\ufeff{}"), null));
            Check("comment rejected", Throws(() => StrictJson.Parse("{/*x*/}"), null));
            Check("truncated literal", Throws(() => StrictJson.Parse("tru"), "JSON_INVALID_LITERAL"));
            Check("single quotes", Throws(() => StrictJson.Parse("{'a':1}"), null));
            Check("depth limit", Throws(() => StrictJson.Parse(new string('[', 40) + new string(']', 40)), "JSON_TOO_DEEP"));
            Check("size limit", Throws(() => StrictJson.Parse(new string(' ', StrictJson.MaxLength + 1)), "JSON_TOO_LARGE"));
            Check("null input", Throws(() => StrictJson.Parse(null), "JSON_MISSING"));
            Check("error carries no input text", Throws(() => StrictJson.Parse("{\"secret-value\" 1}"), "JSON_EXPECTED_COLON"));
        }

        // ---- Candidate manifest ---------------------------------------------

        private static string Mutate(string text, string key, object value)
        {
            JsonObject obj = Obj(text);
            if (value == null) obj.Remove(key); else if (obj.Has(key)) obj.Replace(key, value); else obj.TryAdd(key, value);
            return JsonText.Write(obj);
        }

        private static string FlipHex(string hex)
        {
            char last = hex[hex.Length - 1];
            return hex.Substring(0, hex.Length - 1) + (last == '0' ? '1' : '0');
        }

        private static void ManifestTests(string manifestText)
        {
            var outcome = new Outcome();
            CandidateManifest m = CandidateManifest.Validate(manifestText, outcome);
            Check("committed manifest PASS", m != null && outcome.Ok);
            Check("manifest pins product head", m != null && m.ProductHead == CandidatePins.ProductHead);

            foreach (string key in new[] { "product_head", "release_freeze_sha256", "msi_sha256", "desktop_sha256", "core_sha256", "ffmpeg_sha256", "embedded_manifest_sha256" })
            {
                var o = new Outcome();
                string original = (string)Obj(manifestText).Get(key);
                Check("one-char change rejected: " + key, CandidateManifest.Validate(Mutate(manifestText, key, FlipHex(original)), o) == null && !o.Ok);
                var u = new Outcome();
                Check("uppercase rejected: " + key, CandidateManifest.Validate(Mutate(manifestText, key, original.ToUpperInvariant()), u) == null);
                var d = new Outcome();
                Check("missing rejected: " + key, CandidateManifest.Validate(Mutate(manifestText, key, null), d) == null && d.Has("MANIFEST_MISSING_KEY"));
            }
            Expect("size off by one", Mutate(manifestText, "msi_size_bytes", 70606849L), "MANIFEST_MSI_SIZE_BYTES_MISMATCH");
            Expect("size as string", Mutate(manifestText, "msi_size_bytes", "70606848"), "MANIFEST_MSI_SIZE_BYTES_MISMATCH");
            Expect("size as float", manifestText.Replace("70606848", "70606848.0"), "MANIFEST_MSI_SIZE_BYTES_MISMATCH");
            Expect("other product repo", Mutate(manifestText, "product_repository", "someone/Sorigul"), "MANIFEST_PRODUCT_REPOSITORY_MISMATCH");
            Expect("other PR", Mutate(manifestText, "product_pr", 217L), "MANIFEST_PRODUCT_PR_MISMATCH");
            Expect("other build run", Mutate(manifestText, "original_build_run", "Sorigul_20261101_890364e_000000000000"), "MANIFEST_ORIGINAL_BUILD_RUN_MISMATCH");
            Expect("authorization claim", Mutate(manifestText, "not_execution_authorization", false), "MANIFEST_AUTHORIZATION_CLAIM");
            Expect("qa_commit key forbidden", Mutate(manifestText, "qa_commit", QaSha), "MANIFEST_UNKNOWN_KEY");
            Expect("schema 2", Mutate(manifestText, "schema", 2L), "MANIFEST_SCHEMA_MISMATCH");
            Expect("digest reused", Mutate(manifestText, "core_sha256", CandidatePins.MsiSha256), "MANIFEST_DIGEST_REUSED");
            Expect("duplicate key", manifestText.Replace("\"schema\": 1,", "\"schema\": 1, \"schema\": 1,"), "JSON_DUPLICATE_KEY");
            Expect("not an object", "[]", "ROOT_NOT_OBJECT");
            Expect("empty", "", "JSON_UNEXPECTED_END");

            Check("MSI match PASS", Observation.Msi(m, CandidatePins.MsiSha256, CandidatePins.MsiSizeBytes) == Verdict.PASS);
            Check("MSI Get-FileHash uppercase PASS", Observation.Msi(m, CandidatePins.MsiSha256.ToUpperInvariant(), CandidatePins.MsiSizeBytes) == Verdict.PASS);
            Check("MSI hash mismatch FAIL", Observation.Msi(m, FlipHex(CandidatePins.MsiSha256), CandidatePins.MsiSizeBytes) == Verdict.FAIL);
            Check("MSI size mismatch FAIL", Observation.Msi(m, CandidatePins.MsiSha256, CandidatePins.MsiSizeBytes - 1) == Verdict.FAIL);
            Check("MSI malformed hash FAIL", Observation.Msi(m, "zz", CandidatePins.MsiSizeBytes) == Verdict.FAIL);
            Check("MSI unmeasured hash NOT_VERIFIED", Observation.Msi(m, null, CandidatePins.MsiSizeBytes) == Verdict.NOT_VERIFIED);
            Check("MSI unmeasured size NOT_VERIFIED", Observation.Msi(m, CandidatePins.MsiSha256, null) == Verdict.NOT_VERIFIED);
            Check("MSI without manifest FAIL", Observation.Msi(null, CandidatePins.MsiSha256, CandidatePins.MsiSizeBytes) == Verdict.FAIL);
            Check("installed files PASS", Observation.InstalledFiles(m, CandidatePins.DesktopSha256, CandidatePins.CoreSha256, CandidatePins.FfmpegSha256, CandidatePins.EmbeddedManifestSha256) == Verdict.PASS);
            Check("installed file mismatch FAIL", Observation.InstalledFiles(m, CandidatePins.DesktopSha256, FlipHex(CandidatePins.CoreSha256), CandidatePins.FfmpegSha256, null) == Verdict.FAIL);
            Check("installed file unmeasured NOT_VERIFIED", Observation.InstalledFiles(m, CandidatePins.DesktopSha256, CandidatePins.CoreSha256, null, CandidatePins.EmbeddedManifestSha256) == Verdict.NOT_VERIFIED);
            Check("installed swapped digests FAIL", Observation.InstalledFiles(m, CandidatePins.CoreSha256, CandidatePins.DesktopSha256, CandidatePins.FfmpegSha256, CandidatePins.EmbeddedManifestSha256) == Verdict.FAIL);
        }

        private static void Expect(string name, string manifest, string reason)
        {
            var o = new Outcome();
            Check(name, CandidateManifest.Validate(manifest, o) == null && o.Has(reason));
        }

        // ---- Context gate ---------------------------------------------------

        // Test-only shape of a context that would satisfy every rule. Never
        // committed as a file: a file like this must come from a real approval.
        private static JsonObject AllowedContext()
        {
            return Obj(@"{
  ""schema"": 1, ""kind"": ""QA59_EXECUTION_CONTEXT"",
  ""repository"": { ""full_name"": ""qa-owner/sorigul-qa59-private"", ""id"": 123456789, ""owner"": ""qa-owner"", ""visibility"": ""private"" },
  ""run"": { ""ref"": ""refs/heads/qa59-installed"", ""sha"": """ + QaSha + @""", ""event_name"": ""workflow_dispatch"", ""run_attempt"": 1, ""dispatched_at"": ""2026-11-07T01:00:00Z"" },
  ""approval"": { ""approval_id"": ""APPROVAL-TEST-1"", ""repository_id"": 123456789, ""repository_full_name"": ""qa-owner/sorigul-qa59-private"",
                ""qa_commit"": """ + QaSha + @""", ""ref"": ""refs/heads/qa59-installed"", ""event_name"": ""workflow_dispatch"",
                ""execution_approved"": true, ""msi_download_approved"": true, ""msi_install_approved"": true },
  ""cost"": { ""maximum_allowed_cost_krw"": 0, ""paid_usage_approved"": false, ""free_allowance_verified"": true,
            ""paid_overage_block_verified"": true, ""verified_at"": ""2026-11-07T00:00:00Z"" }
}");
        }

        private static GateDecision GateWith(string section, string key, object value)
        {
            JsonObject ctx = AllowedContext();
            if (section == null) { if (value == null) ctx.Remove(key); else ctx.TryAdd(key, value); }
            else ((JsonObject)ctx.Get(section)).Replace(key, value);
            return ContextGate.Evaluate(JsonText.Write(ctx));
        }

        private static void Deny(string name, GateDecision d, string reason)
        {
            Check(name, !d.ExecutionAllowed && !d.MsiDownloadAllowed && !d.MsiInstallAllowed && d.Reasons.Contains(reason));
        }

        private static void GateTests(string currentText, string manifestText)
        {
            GateDecision current = ContextGate.Evaluate(currentText);
            Check("current context DENY", !current.ExecutionAllowed && !current.MsiDownloadAllowed && !current.MsiInstallAllowed);
            Check("current: cost not verified", current.Reasons.Contains("COST_NOT_VERIFIED"));
            Check("current: approval missing", current.Reasons.Contains("APPROVAL_MISSING"));
            Check("current: repository unknown", current.Reasons.Contains("REPOSITORY_UNKNOWN"));

            GateDecision allowed = ContextGate.Evaluate(JsonText.Write(AllowedContext()));
            Check("fully approved synthetic context ALLOW", allowed.ExecutionAllowed && allowed.MsiDownloadAllowed && allowed.MsiInstallAllowed && allowed.Reasons.Count == 0);

            Deny("public repository", GateWith("repository", "visibility", "public"), "REPOSITORY_NOT_PRIVATE");
            Deny("unknown visibility", GateWith("repository", "visibility", JsonNull.Value), "REPOSITORY_NOT_PRIVATE");
            JsonObject product = AllowedContext();
            ((JsonObject)product.Get("repository")).Replace("full_name", "BongBong90/sorigul");
            ((JsonObject)product.Get("repository")).Replace("owner", "bongbong90");
            ((JsonObject)product.Get("approval")).Replace("repository_full_name", "bongbong90/Sorigul");
            Deny("public product repository by name (any case)", ContextGate.Evaluate(JsonText.Write(product)), "REPOSITORY_IS_PRODUCT");
            Deny("other repository id", GateWith("repository", "id", 987654321L), "REPOSITORY_NOT_APPROVED");
            Deny("renamed repository", GateWith("repository", "full_name", "qa-owner/other"), "REPOSITORY_NOT_APPROVED");
            Deny("owner mismatch", GateWith("repository", "owner", "intruder"), "REPOSITORY_OWNER_MISMATCH");
            Deny("unknown repository id", GateWith("repository", "id", JsonNull.Value), "REPOSITORY_UNKNOWN");

            JsonObject productSha = AllowedContext();
            ((JsonObject)productSha.Get("run")).Replace("sha", CandidatePins.ProductHead);
            ((JsonObject)productSha.Get("approval")).Replace("qa_commit", CandidatePins.ProductHead);
            Deny("QA SHA equal to product head", ContextGate.Evaluate(JsonText.Write(productSha)), "QA_COMMIT_IS_PRODUCT_HEAD");
            Deny("unapproved QA SHA", GateWith("run", "sha", "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"), "QA_COMMIT_NOT_APPROVED");
            Deny("short QA SHA", GateWith("run", "sha", "aaaaaaa"), "QA_COMMIT_FORMAT");
            Deny("uppercase QA SHA", GateWith("run", "sha", QaSha.ToUpperInvariant()), "QA_COMMIT_FORMAT");
            Deny("other branch", GateWith("run", "ref", "refs/heads/main"), "REF_NOT_APPROVED");
            Deny("pull request ref", GateWith("run", "ref", "refs/pull/1/merge"), "REF_NOT_APPROVED");
            Deny("push event", GateWith("run", "event_name", "push"), "EVENT_NOT_APPROVED");
            Deny("approved push event", GateWith("approval", "event_name", "push"), "EVENT_NOT_APPROVED");
            Deny("re-run attempt 2", GateWith("run", "run_attempt", 2L), "RERUN_DENIED");
            Deny("unknown attempt", GateWith("run", "run_attempt", JsonNull.Value), "RUN_ATTEMPT_UNKNOWN");
            Deny("execution not approved", GateWith("approval", "execution_approved", false), "APPROVAL_MISSING");
            Deny("empty approval id", GateWith("approval", "approval_id", ""), "APPROVAL_MISSING");
            Deny("whitespace approval id", GateWith("approval", "approval_id", " "), "APPROVAL_MISSING");
            Deny("padded approval id", GateWith("approval", "approval_id", " APPROVAL-TEST-1"), "APPROVAL_MISSING");
            Deny("ancient cost evidence", GateWith("cost", "verified_at", "0001-01-01T00:00:00Z"), "COST_EVIDENCE_STALE");
            Deny("cost evidence older than window", GateWith("cost", "verified_at", "2026-11-06T23:59:59Z"), "COST_EVIDENCE_STALE");
            JsonObject crossMonth = AllowedContext();
            ((JsonObject)crossMonth.Get("cost")).Replace("verified_at", "2026-10-31T23:30:00Z");
            ((JsonObject)crossMonth.Get("run")).Replace("dispatched_at", "2026-11-01T00:10:00Z");
            Deny("cost evidence from previous billing month", ContextGate.Evaluate(JsonText.Write(crossMonth)), "COST_EVIDENCE_STALE");
            Deny("renamed product repository by ID", GateWith("repository", "id", CandidatePins.ProductRepositoryId), "REPOSITORY_IS_PRODUCT");
            Deny("free allowance unverified", GateWith("cost", "free_allowance_verified", false), "COST_NOT_VERIFIED");
            Deny("overage block unverified", GateWith("cost", "paid_overage_block_verified", JsonNull.Value), "COST_NOT_VERIFIED");
            Deny("cost verification time missing", GateWith("cost", "verified_at", JsonNull.Value), "COST_NOT_VERIFIED");
            Deny("cost verified after dispatch", GateWith("cost", "verified_at", "2026-11-07T02:00:00Z"), "COST_NOT_VERIFIED_BEFORE_DISPATCH");
            Deny("cost verified at dispatch", GateWith("cost", "verified_at", "2026-11-07T01:00:00Z"), "COST_NOT_VERIFIED_BEFORE_DISPATCH");
            Deny("non-UTC timestamp", GateWith("cost", "verified_at", "2026-11-07T00:00:00+09:00"), "COST_NOT_VERIFIED");
            Deny("dispatch time unknown", GateWith("run", "dispatched_at", JsonNull.Value), "DISPATCH_TIME_UNKNOWN");
            Deny("cost limit above zero", GateWith("cost", "maximum_allowed_cost_krw", 1L), "COST_LIMIT_NOT_ZERO");
            Deny("paid usage approved", GateWith("cost", "paid_usage_approved", true), "PAID_USAGE_NOT_SUPPORTED");
            Deny("unknown root key", GateWith(null, "override", true), "CONTEXT_UNKNOWN_KEY");
            Deny("missing cost section", GateWith(null, "cost", null), "CONTEXT_MISSING_KEY");
            Deny("malformed JSON", ContextGate.Evaluate("{"), "JSON_UNEXPECTED_END");

            GateDecision noInstall = GateWith("approval", "msi_install_approved", false);
            Check("download without install approval", noInstall.ExecutionAllowed && noInstall.MsiDownloadAllowed && !noInstall.MsiInstallAllowed);
            GateDecision installOnly = GateWith("approval", "msi_download_approved", false);
            Check("install approval needs download approval", installOnly.ExecutionAllowed && !installOnly.MsiDownloadAllowed && !installOnly.MsiInstallAllowed);

            var o = new Outcome();
            CandidateManifest m = CandidateManifest.Validate(manifestText, o);
            Check("msiexec permitted only with all three", InstallerPermit.MayInvokeMsiexec(m, Verdict.PASS, allowed));
            Check("msiexec denied under current context", !InstallerPermit.MayInvokeMsiexec(m, Verdict.PASS, current));
            Check("msiexec denied on hash mismatch", !InstallerPermit.MayInvokeMsiexec(m, Verdict.FAIL, allowed));
            Check("msiexec denied on unmeasured MSI", !InstallerPermit.MayInvokeMsiexec(m, Verdict.NOT_VERIFIED, allowed));
            Check("msiexec denied without manifest", !InstallerPermit.MayInvokeMsiexec(null, Verdict.PASS, allowed));
            Check("msiexec denied without gate", !InstallerPermit.MayInvokeMsiexec(m, Verdict.PASS, null));
        }

        // ---- Result schema --------------------------------------------------

        private static JsonObject Record(StepSpec spec)
        {
            var evidence = new JsonObject();
            foreach (EvidenceSpec e in spec.Evidence) evidence.TryAdd(e.Key, e.IsCount ? (object)e.ExpectedCount : true);
            var r = new JsonObject();
            r.TryAdd("id", spec.Id);
            r.TryAdd("verdict", "PASS");
            r.TryAdd("reason", JsonNull.Value);
            r.TryAdd("evidence", evidence);
            return r;
        }

        private static JsonObject PassingResult()
        {
            var steps = new List<object>();
            foreach (StepSpec s in ResultContract.Steps) steps.Add(Record(s));
            var negatives = new List<object>();
            foreach (StepSpec s in ResultContract.Negatives) negatives.Add(Record(s));
            var supervisor = new JsonObject();
            foreach (string k in new[] { "deadline_exceeded", "uia_worker_hung", "provider_failed", "forced_cleanup_used", "job_close_kill_used" }) supervisor.TryAdd(k, false);
            foreach (string k in new[] { "skipped_steps", "late_results", "residual_processes", "residual_tcp", "residual_udp" }) supervisor.TryAdd(k, 0L);
            supervisor.TryAdd("normal_product_exit", true);
            var cleanup = new JsonObject();
            cleanup.TryAdd("verdict", "PASS");
            cleanup.TryAdd("harness_resources_released", true);
            cleanup.TryAdd("fixtures_restored", true);
            var root = new JsonObject();
            root.TryAdd("schema", 1L);
            root.TryAdd("kind", ResultContract.Kind);
            root.TryAdd("product_head", CandidatePins.ProductHead);
            root.TryAdd("msi_sha256", CandidatePins.MsiSha256);
            root.TryAdd("qa_commit", QaSha);
            root.TryAdd("steps", steps);
            root.TryAdd("negatives", negatives);
            root.TryAdd("supervisor", supervisor);
            root.TryAdd("cleanup", cleanup);
            root.TryAdd("overall", "PASS");
            return root;
        }

        private static JsonObject StepOf(JsonObject doc, string list, int index) { return (JsonObject)((List<object>)doc.Get(list))[index]; }
        private static JsonObject EvidenceOf(JsonObject doc, string list, int index) { return (JsonObject)StepOf(doc, list, index).Get("evidence"); }
        private static ResultValidation Run(JsonObject doc) { return ResultContract.Validate(JsonText.Write(doc)); }

        private static void SetStep(JsonObject doc, string list, int index, string verdict, object reason)
        {
            StepOf(doc, list, index).Replace("verdict", verdict);
            StepOf(doc, list, index).Replace("reason", reason);
        }

        private static void ResultTests()
        {
            ResultValidation pass = Run(PassingResult());
            Check("all evidence PASS", pass.Outcome.Ok && pass.Overall == Verdict.PASS && pass.EffectiveOverall == Verdict.PASS && pass.Cleanup == Verdict.PASS);
            Check("12 steps / 7 negatives", ResultContract.Steps.Length == 12 && ResultContract.Negatives.Length == 7);

            JsonObject unmeasured = PassingResult();
            EvidenceOf(unmeasured, "steps", 4).Replace("main_webview_unique", JsonNull.Value);
            ResultValidation promoted = Run(unmeasured);
            Check("unmeasured evidence cannot be declared PASS", !promoted.Outcome.Ok && promoted.Outcome.Has("RESULT_VERDICT_PROMOTED") && promoted.EffectiveOverall == Verdict.NOT_VERIFIED);
            SetStep(unmeasured, "steps", 4, "NOT_VERIFIED", "SELECTOR_NOT_UNIQUE");
            unmeasured.Replace("overall", "NOT_VERIFIED");
            ResultValidation nv = Run(unmeasured);
            Check("unmeasured evidence -> NOT_VERIFIED", nv.Outcome.Ok && nv.Overall == Verdict.NOT_VERIFIED);

            JsonObject reboot = PassingResult();
            EvidenceOf(reboot, "steps", 1).Replace("install_exit_code", 3010L);
            SetStep(reboot, "steps", 1, "FAIL", "EXPECTATION_UNMET");
            reboot.Replace("overall", "FAIL");
            ResultValidation rebootResult = Run(reboot);
            Check("install exit 3010 is FAIL", rebootResult.Outcome.Ok && rebootResult.Overall == Verdict.FAIL);
            reboot.Replace("overall", "PASS");
            Check("declared overall PASS over FAIL rejected", Run(reboot).Outcome.Has("RESULT_OVERALL_MISMATCH") && Run(reboot).EffectiveOverall == Verdict.NOT_VERIFIED);

            JsonObject downgrade = PassingResult();
            EvidenceOf(downgrade, "steps", 7).Replace("native_input_count", 2L);
            SetStep(downgrade, "steps", 7, "NOT_VERIFIED", "EXPECTATION_UNMET");
            downgrade.Replace("overall", "NOT_VERIFIED");
            Check("FAIL evidence cannot be declared NOT_VERIFIED", Run(downgrade).Outcome.Has("RESULT_VERDICT_PROMOTED"));

            JsonObject worse = PassingResult();
            SetStep(worse, "steps", 0, "FAIL", "DEADLINE_EXCEEDED");
            worse.Replace("overall", "FAIL");
            Check("step may declare worse than evidence", Run(worse).Outcome.Ok && Run(worse).Overall == Verdict.FAIL);

            JsonObject passWithReason = PassingResult();
            StepOf(passWithReason, "steps", 0).Replace("reason", "NOT_RUN");
            Check("PASS with reason rejected", Run(passWithReason).Outcome.Has("RESULT_REASON_INVALID"));
            JsonObject freeText = PassingResult();
            SetStep(freeText, "steps", 0, "FAIL", "System.IO.IOException at C:\\Users\\x");
            freeText.Replace("overall", "FAIL");
            Check("free-text reason rejected", Run(freeText).Outcome.Has("RESULT_REASON_INVALID"));

            JsonObject extra = PassingResult();
            extra.TryAdd("stderr", "trace");
            Check("raw output key rejected", Run(extra).Outcome.Has("RESULT_UNKNOWN_KEY"));
            JsonObject extraEvidence = PassingResult();
            EvidenceOf(extraEvidence, "steps", 0).TryAdd("screen", "base64");
            Check("unknown evidence key rejected", Run(extraEvidence).Outcome.Has("RESULT_EVIDENCE_UNKNOWN_KEY"));
            JsonObject stringEvidence = PassingResult();
            EvidenceOf(stringEvidence, "steps", 0).Replace("msi_sha256_match", "true");
            Check("string evidence rejected", Run(stringEvidence).Outcome.Has("RESULT_EVIDENCE_TYPE"));
            JsonObject pathEvidence = PassingResult();
            EvidenceOf(pathEvidence, "steps", 8).Replace("backend_roots", "C:\\Users\\x");
            Check("path in count rejected", Run(pathEvidence).Outcome.Has("RESULT_EVIDENCE_TYPE"));

            JsonObject order = PassingResult();
            var steps = (List<object>)order.Get("steps");
            object first = steps[0]; steps[0] = steps[1]; steps[1] = first;
            Check("step order enforced", Run(order).Outcome.Has("RESULT_RECORD_ORDER"));
            JsonObject missingStep = PassingResult();
            ((List<object>)missingStep.Get("negatives")).RemoveAt(6);
            Check("skipped negative case rejected", Run(missingStep).Outcome.Has("RESULT_RECORD_COUNT"));

            JsonObject negativeFail = PassingResult();
            EvidenceOf(negativeFail, "negatives", 1).Replace("spawn_count", 1L);
            SetStep(negativeFail, "negatives", 1, "FAIL", "EXPECTATION_UNMET");
            negativeFail.Replace("overall", "FAIL");
            Check("S10 cannot claim matrix pass over failing negative", Run(negativeFail).Outcome.Has("RESULT_S10_INCONSISTENT"));
            EvidenceOf(negativeFail, "steps", 9).Replace("negative_matrix_pass", false);
            SetStep(negativeFail, "steps", 9, "FAIL", "EXPECTATION_UNMET");
            Check("negative spawn -> FAIL", Run(negativeFail).Outcome.Ok && Run(negativeFail).Overall == Verdict.FAIL);

            foreach (string flag in new[] { "deadline_exceeded", "uia_worker_hung", "provider_failed", "forced_cleanup_used", "job_close_kill_used" })
            {
                JsonObject doc = PassingResult();
                ((JsonObject)doc.Get("supervisor")).Replace(flag, true);
                Check(flag + " blocks declared PASS", Run(doc).Outcome.Has("RESULT_OVERALL_MISMATCH"));
                doc.Replace("overall", "NOT_VERIFIED");
                Check(flag + " -> NOT_VERIFIED", Run(doc).Outcome.Ok && Run(doc).Overall == Verdict.NOT_VERIFIED);
            }
            JsonObject skipped = PassingResult();
            ((JsonObject)skipped.Get("supervisor")).Replace("skipped_steps", 1L);
            skipped.Replace("overall", "NOT_VERIFIED");
            Check("skip -> NOT_VERIFIED", Run(skipped).Outcome.Ok && Run(skipped).Overall == Verdict.NOT_VERIFIED);
            JsonObject residual = PassingResult();
            ((JsonObject)residual.Get("supervisor")).Replace("residual_tcp", 1L);
            residual.Replace("overall", "FAIL");
            Check("residual TCP -> FAIL", Run(residual).Outcome.Ok && Run(residual).Overall == Verdict.FAIL);
            JsonObject abnormal = PassingResult();
            ((JsonObject)abnormal.Get("supervisor")).Replace("normal_product_exit", false);
            abnormal.Replace("overall", "FAIL");
            Check("abnormal product exit -> FAIL", Run(abnormal).Outcome.Ok && Run(abnormal).Overall == Verdict.FAIL);
            JsonObject unknownSup = PassingResult();
            ((JsonObject)unknownSup.Get("supervisor")).Replace("residual_udp", JsonNull.Value);
            unknownSup.Replace("overall", "NOT_VERIFIED");
            Check("unmeasured residual -> NOT_VERIFIED", Run(unknownSup).Outcome.Ok && Run(unknownSup).Overall == Verdict.NOT_VERIFIED);

            JsonObject cleanupOnly = PassingResult();
            EvidenceOf(cleanupOnly, "steps", 11).Replace("normal_product_exit", false);
            SetStep(cleanupOnly, "steps", 11, "FAIL", "FORCED_CLEANUP");
            ((JsonObject)cleanupOnly.Get("supervisor")).Replace("forced_cleanup_used", true);
            ((JsonObject)cleanupOnly.Get("supervisor")).Replace("normal_product_exit", false);
            cleanupOnly.Replace("overall", "FAIL");
            ResultValidation sep = Run(cleanupOnly);
            Check("successful harness cleanup does not upgrade FAIL", sep.Outcome.Ok && sep.Overall == Verdict.FAIL && sep.Cleanup == Verdict.PASS);
            JsonObject cleanupFail = PassingResult();
            ((JsonObject)cleanupFail.Get("cleanup")).Replace("fixtures_restored", false);
            Check("cleanup verdict must match its evidence", Run(cleanupFail).Outcome.Has("RESULT_CLEANUP_MISMATCH"));
            ((JsonObject)cleanupFail.Get("cleanup")).Replace("verdict", "FAIL");
            Check("cleanup FAIL reported separately", Run(cleanupFail).Outcome.Ok && Run(cleanupFail).Cleanup == Verdict.FAIL && Run(cleanupFail).Overall == Verdict.PASS);

            foreach (object bad in new object[] { JsonNull.Value, "PASS", 1L, new List<object>() })
            {
                JsonObject noCleanup = PassingResult();
                noCleanup.Replace("cleanup", bad);
                ResultValidation c = Run(noCleanup);
                Check("non-object cleanup invalid: " + bad, c.Outcome.Has("RESULT_CLEANUP_NOT_OBJECT") && c.EffectiveOverall == Verdict.NOT_VERIFIED);
                JsonObject noSupervisor = PassingResult();
                noSupervisor.Replace("supervisor", bad);
                noSupervisor.Replace("overall", "NOT_VERIFIED");
                Check("non-object supervisor invalid: " + bad, Run(noSupervisor).Outcome.Has("RESULT_SUPERVISOR_NOT_OBJECT"));
                JsonObject badRecord = PassingResult();
                ((List<object>)badRecord.Get("steps"))[0] = bad;
                badRecord.Replace("overall", "FAIL");
                Check("non-object record invalid: " + bad, Run(badRecord).Outcome.Has("RESULT_RECORD_NOT_OBJECT"));
                JsonObject badEvidence = PassingResult();
                StepOf(badEvidence, "steps", 0).Replace("evidence", bad);
                badEvidence.Replace("overall", "FAIL");
                Check("non-object evidence invalid: " + bad, Run(badEvidence).Outcome.Has("RESULT_EVIDENCE_NOT_OBJECT"));
            }
            JsonObject noSteps = PassingResult();
            noSteps.Replace("steps", JsonNull.Value);
            Check("missing step list invalid", Run(noSteps).Outcome.Has("RESULT_RECORD_COUNT") && Run(noSteps).EffectiveOverall == Verdict.NOT_VERIFIED);

            JsonObject productQa = PassingResult();
            productQa.Replace("qa_commit", CandidatePins.ProductHead);
            Check("QA commit equal to product head rejected", Run(productQa).Outcome.Has("RESULT_QA_COMMIT_IS_PRODUCT_HEAD"));
            JsonObject otherMsi = PassingResult();
            otherMsi.Replace("msi_sha256", FlipHex(CandidatePins.MsiSha256));
            Check("other MSI rejected", Run(otherMsi).Outcome.Has("RESULT_MSI_MISMATCH"));
            Check("oversize document rejected", ResultContract.Validate(new string(' ', ResultContract.MaxLength + 1)).Outcome.Has("RESULT_TOO_LARGE"));
            Check("malformed document never PASS", ResultContract.Validate("{").EffectiveOverall == Verdict.NOT_VERIFIED);

            LatchTests();
        }

        private static void LatchTests()
        {
            var ids = new[] { "S01_MSI_HASH_SIZE", "S02_RUNNER_INSTALL", "S03_PRODUCT_REGISTRATION" };
            var latch = new VerdictLatch(ids);
            latch.Record("S01_MSI_HASH_SIZE", Verdict.FAIL, "EXPECTATION_UNMET");
            Check("later PASS cannot replace FAIL", !latch.Record("S01_MSI_HASH_SIZE", Verdict.PASS, null) && latch.Get("S01_MSI_HASH_SIZE") == Verdict.FAIL);
            latch.Record("S02_RUNNER_INSTALL", Verdict.PASS, null);
            Check("worse record replaces PASS", latch.Record("S02_RUNNER_INSTALL", Verdict.NOT_VERIFIED, "UIA_WORKER_HUNG") && latch.Get("S02_RUNNER_INSTALL") == Verdict.NOT_VERIFIED);
            latch.Freeze("DEADLINE_EXCEEDED");
            Check("pending step frozen NOT_VERIFIED", latch.Get("S03_PRODUCT_REGISTRATION") == Verdict.NOT_VERIFIED && latch.ReasonOf("S03_PRODUCT_REGISTRATION") == "DEADLINE_EXCEEDED");
            Check("late PASS discarded", !latch.Record("S03_PRODUCT_REGISTRATION", Verdict.PASS, null) && latch.Get("S03_PRODUCT_REGISTRATION") == Verdict.NOT_VERIFIED);
            Check("late FAIL discarded and counted", !latch.Record("S01_MSI_HASH_SIZE", Verdict.FAIL, "EXPECTATION_UNMET") && latch.LateResults == 2 && latch.IsFrozen);
            Check("unknown id rejected", ThrowsArg(() => latch.Record("S99", Verdict.PASS, null)));
            Check("free-text reason rejected", ThrowsArg(() => new VerdictLatch(ids).Record("S01_MSI_HASH_SIZE", Verdict.FAIL, "stack trace")));
            Check("PASS with reason rejected", ThrowsArg(() => new VerdictLatch(ids).Record("S01_MSI_HASH_SIZE", Verdict.PASS, "NOT_RUN")));
            Check("non-PASS without reason rejected", ThrowsArg(() => new VerdictLatch(ids).Record("S01_MSI_HASH_SIZE", Verdict.FAIL, null)));
        }

        private static bool ThrowsArg(Action action)
        {
            try { action(); return false; } catch (ArgumentException) { return true; }
        }

        // ---- Synthetic fixtures ---------------------------------------------

        private static void FixtureTests()
        {
            foreach (char rev in new[] { 'A', 'B' })
            {
                string settings = SyntheticFixtures.SettingsJson(Root, rev);
                string history = SyntheticFixtures.JobsJson(Root, rev);
                Check("settings " + rev + " valid", SyntheticFixtures.ValidateSettings(settings, Root, rev, Protected).Ok);
                Check("jobs " + rev + " valid", SyntheticFixtures.ValidateJobs(history, Root, rev, Protected).Ok);
                Check("jobs " + rev + " terminal idle", SyntheticFixtures.Classify(history) == FixtureClass.TERMINAL_IDLE
                    && SyntheticFixtures.ExpectedProductCode(SyntheticFixtures.Classify(history)) == null);
                Check("jobs " + rev + " is complete JobModel", SyntheticFixtures.ValidateJobModel((JsonObject)Obj(history).Get(SyntheticFixtures.JobId(rev)), new Outcome()));
            }
            string settingsA = SyntheticFixtures.SettingsJson(Root, 'A');
            string jobsA = SyntheticFixtures.JobsJson(Root, 'A');
            Check("settings A is not B", SyntheticFixtures.ValidateSettings(settingsA, Root, 'B', Protected).Has("FIXTURE_FOLDER_MISMATCH"));
            Check("jobs A is not B", !SyntheticFixtures.ValidateJobs(jobsA, Root, 'B', Protected).Ok);
            Check("revisions distinguishable in UI", SyntheticFixtures.FolderFor(Root, 'A') != SyntheticFixtures.FolderFor(Root, 'B')
                && SyntheticFixtures.FailedFiles('A') != SyntheticFixtures.FailedFiles('B')
                && SyntheticFixtures.TotalFiles('A') != SyntheticFixtures.TotalFiles('B'));
            Check("python layout", jobsA.StartsWith("{\n  \"00000000-0000-4000-8000-00000000000a\": {\n    \"job_id\"", StringComparison.Ordinal));
            Check("Korean default kept unescaped", settingsA.Contains(SyntheticFixtures.DriveExamRootDefault));

            ExpectSettings("extra settings key (extra=forbid)", Mutate(settingsA, "theme", "dark"), "SETTINGS_UNKNOWN_KEY");
            ExpectSettings("missing settings key", Mutate(settingsA, "drive_exam_root", null), "SETTINGS_MISSING_KEY");
            ExpectSettings("shutdown armed", Mutate(settingsA, "shutdown", "immediate"), "SETTINGS_SHUTDOWN_NOT_DISABLED");
            ExpectSettings("bad close behavior", Mutate(settingsA, "close_behavior", "minimize"), "SETTINGS_CLOSE_BEHAVIOR_INVALID");
            ExpectSettings("bad engine", Mutate(settingsA, "last_engine", "cloud"), "SETTINGS_ENGINE_INVALID");
            ExpectSettings("real folder", Mutate(settingsA, "transcription_folder", "C:\\Users\\User\\Desktop\\전사"), "FIXTURE_FOLDER_MISMATCH");
            ExpectSettings("nonempty course is not canonical", Mutate(settingsA, "last_course", "민법"), "FIXTURE_NOT_CANONICAL");
            ExpectSettings("credential-like content", Mutate(settingsA, "last_subject", "refresh_token=x"), "FIXTURE_FORBIDDEN_CONTENT");

            JsonObject jobs = Obj(jobsA);
            JsonObject job = (JsonObject)jobs.Get(SyntheticFixtures.JobId('A'));
            ExpectJobs("extra job key", WithJob(j => j.TryAdd("transcript", "x")), "JOB_UNKNOWN_KEY");
            ExpectJobs("missing batch_completed", WithJob(j => j.Remove("batch_completed")), "JOB_MISSING_KEY");
            ExpectJobs("counts inconsistent", WithJob(j => j.Replace("done_files", 2L)), "FIXTURE_COUNTS_INCONSISTENT");
            ExpectJobs("status DONE despite failures", WithJob(j => j.Replace("status", "DONE")), "FIXTURE_STATUS_INCONSISTENT");
            ExpectJobs("drive upload on", WithJob(j => j.Replace("upload_to_drive", true)), "FIXTURE_DRIVE_ENABLED");
            ExpectJobs("active status", WithJob(j => j.Replace("status", "TRANSCRIBING")), "FIXTURE_NOT_TERMINAL");
            ExpectJobs("unknown status enum", WithJob(j => j.Replace("status", SyntheticFixtures.UnknownEnum)), "JOB_STATUS_ENUM");
            ExpectJobs("media file name", WithJob(j => j.Replace("current_file", "lecture.mp3")), "FIXTURE_FORBIDDEN_CONTENT");
            ExpectJobs("folder outside root", WithJob(j => j.Replace("folder", "D:\\a\\_temp\\other\\revision-A")), "FIXTURE_FOLDER_MISMATCH");
            ExpectJobs("bad timestamp", WithJob(j => j.Replace("created_at", "yesterday")), "JOB_TIMESTAMP");
            ExpectJobs("bad stage", WithJob(j => j.Replace("stage", "3차")), "JOB_STAGE_INVALID");
            ExpectJobs("float count", WithJob(j => j.Replace("total_files", 2.0)), "JOB_COUNT");
            ExpectJobs("unexpected event", WithJob(j => j.Replace("events", new List<object> { 1L })), "JOB_EVENT_INVALID");
            ExpectJobs("second job", JsonText.Write(AddSecondJob(jobs)), "FIXTURE_JOB_SET");
            Check("CRASHED history is terminal for gate", SyntheticFixtures.Classify(WithJob(j => j.Replace("status", "CRASHED"))) == FixtureClass.TERMINAL_IDLE);
            Check("unchanged fixture parses back canonical", JsonText.DeepEquals(job, Obj(jobsA).Get(SyntheticFixtures.JobId('A'))));

            Check("root under product AppData rejected", SyntheticFixtures.ValidateRoot("C:\\Users\\runneradmin\\AppData\\Local\\Sorigul\\qa59-fixture-0123456789abcdef0123456789abcdef", Protected).Has("FIXTURE_ROOT_PROTECTED"));
            Check("root ancestor of protected rejected", SyntheticFixtures.ValidateRoot("C:\\Users\\runneradmin", new[] { "C:\\Users\\runneradmin\\Desktop" }).Has("FIXTURE_ROOT_PROTECTED"));
            Check("root under Desktop segment rejected", SyntheticFixtures.ValidateRoot("C:\\x\\desktop\\qa59-fixture-0123456789abcdef0123456789abcdef", Protected).Has("FIXTURE_ROOT_PROTECTED"));
            Check("root under 전사 rejected", SyntheticFixtures.ValidateRoot("D:\\전사\\qa59-fixture-0123456789abcdef0123456789abcdef", Protected).Has("FIXTURE_ROOT_PROTECTED"));
            Check("root not runner-owned rejected", SyntheticFixtures.ValidateRoot("D:\\a\\_temp\\fixtures", Protected).Has("FIXTURE_ROOT_NOT_RUNNER_OWNED"));
            Check("relative root rejected", SyntheticFixtures.ValidateRoot("qa59-fixture-0123456789abcdef0123456789abcdef", Protected).Has("FIXTURE_ROOT_FORMAT"));
            Check("dot-dot root rejected", SyntheticFixtures.ValidateRoot("D:\\a\\..\\qa59-fixture-0123456789abcdef0123456789abcdef", Protected).Has("FIXTURE_ROOT_FORMAT"));
            Check("UNC root rejected", SyntheticFixtures.ValidateRoot("\\\\server\\share\\qa59-fixture-0123456789abcdef0123456789abcdef", Protected).Has("FIXTURE_ROOT_FORMAT"));
            Check("ADS root rejected", SyntheticFixtures.ValidateRoot("D:\\a\\qa59-fixture-0123456789abcdef0123456789abcdef:x", Protected).Has("FIXTURE_ROOT_FORMAT"));
            Check("unknown protected roots rejected", SyntheticFixtures.ValidateRoot(Root, null).Has("FIXTURE_PROTECTED_ROOTS_UNKNOWN"));
            Check("empty protected roots rejected", SyntheticFixtures.ValidateRoot(Root, new string[0]).Has("FIXTURE_PROTECTED_ROOTS_UNKNOWN"));
            const string Hex = "qa59-fixture-0123456789abcdef0123456789abcdef";
            Check("8.3 alias of protected Desktop rejected", SyntheticFixtures.ValidateRoot("C:\\Users\\RUNNER~1\\DESKTO~1\\" + Hex, Protected).Has("FIXTURE_ROOT_FORMAT"));
            Check("8.3 alias of protected leaf rejected", SyntheticFixtures.ValidateRoot("C:\\Users\\runneradmin\\DESKTO~1\\" + Hex, Protected).Has("FIXTURE_ROOT_FORMAT"));
            Check("8.3 alias of banned segment rejected", SyntheticFixtures.ValidateRoot("C:\\Users\\u\\AppData\\Local\\SORIGU~1\\" + Hex, Protected).Has("FIXTURE_ROOT_FORMAT"));
            foreach (string device in new[] { "CON", "nul", "COM1", "LPT9", "aux.txt", "CONIN$" })
            {
                Check("device segment rejected: " + device, SyntheticFixtures.ValidateRoot("D:\\a\\" + device + "\\" + Hex, Protected).Has("FIXTURE_ROOT_FORMAT"));
            }
            Check("trailing-space segment rejected", SyntheticFixtures.ValidateRoot("D:\\a \\" + Hex, Protected).Has("FIXTURE_ROOT_FORMAT"));
            foreach (string badProtected in new[] { "C:/Users/runneradmin/Pictures", "\\\\?\\C:\\Users\\runneradmin\\Pictures", "C:\\Users\\RUNNER~1\\Pictures", "C:\\Users\\x\\", "", null, "Pictures" })
            {
                Check("non-canonical protected root rejected: " + (badProtected ?? "null"),
                    SyntheticFixtures.ValidateRoot(Root, new[] { "C:\\Users\\runneradmin\\Desktop", badProtected }).Has("FIXTURE_PROTECTED_ROOTS_INVALID"));
            }
            Check("protected root compared case-insensitively", SyntheticFixtures.ValidateRoot("D:\\A\\_TEMP\\" + Hex, new[] { "d:\\a\\_temp" }).Has("FIXTURE_ROOT_PROTECTED"));
            Check("runner root accepted", SyntheticFixtures.ValidateRoot(Root, Protected).Ok);
            Check("invalid root blocks valid settings", !SyntheticFixtures.ValidateSettings(SyntheticFixtures.SettingsJson("D:\\a\\_temp\\fixtures", 'A'), "D:\\a\\_temp\\fixtures", 'A', Protected).Ok);

            ExpectClass(NegativeFixture.ACTIVE_JOB_WAITING, FixtureClass.ACTIVE_JOB, "ACTIVE_OR_UNKNOWN_JOB");
            ExpectClass(NegativeFixture.ACTIVE_JOB_TRANSCRIBING, FixtureClass.ACTIVE_JOB, "ACTIVE_OR_UNKNOWN_JOB");
            ExpectClass(NegativeFixture.ACTIVE_FILE_CANCEL_REQUESTED, FixtureClass.ACTIVE_JOB, "ACTIVE_OR_UNKNOWN_JOB");
            ExpectClass(NegativeFixture.UNKNOWN_JOB_ENUM, FixtureClass.UNKNOWN_JOB_ENUM, "ACTIVE_OR_UNKNOWN_JOB");
            ExpectClass(NegativeFixture.UNKNOWN_FILE_ENUM, FixtureClass.UNKNOWN_JOB_ENUM, "ACTIVE_OR_UNKNOWN_JOB");
            ExpectClass(NegativeFixture.ACTIVE_DRIVE_PENDING, FixtureClass.ACTIVE_DRIVE, "ACTIVE_OR_UNKNOWN_DRIVE");
            ExpectClass(NegativeFixture.ACTIVE_DRIVE_UPLOADING, FixtureClass.ACTIVE_DRIVE, "ACTIVE_OR_UNKNOWN_DRIVE");
            ExpectClass(NegativeFixture.UNKNOWN_DRIVE_ENUM, FixtureClass.UNKNOWN_DRIVE_ENUM, "ACTIVE_OR_UNKNOWN_DRIVE");
            ExpectClass(NegativeFixture.CORRUPT_TRUNCATED, FixtureClass.MALFORMED, "JOB_STATE_UNKNOWN");
            Check("active fixture keeps full schema", SyntheticFixtures.ValidateJobModel((JsonObject)Obj(SyntheticFixtures.NegativeJobsJson(Root, NegativeFixture.ACTIVE_DRIVE_UPLOADING)).Get(SyntheticFixtures.JobId('A')), new Outcome()));
            Check("active fixture is not a valid idle fixture", !SyntheticFixtures.ValidateJobs(SyntheticFixtures.NegativeJobsJson(Root, NegativeFixture.ACTIVE_JOB_WAITING), Root, 'A', Protected).Ok);

            // Same cases as recovery.rs tests.
            Check("rust: empty history idle", SyntheticFixtures.Classify("{}") == FixtureClass.TERMINAL_IDLE);
            foreach (string state in SyntheticFixtures.TerminalFileStatuses)
            {
                Check("rust: terminal " + state, SyntheticFixtures.Classify("{\"job\":{\"status\":\"" + state + "\",\"files\":{\"f\":\"" + state + "\"},\"drive\":{\"f\":{\"status\":\"DONE\"}}}}") == FixtureClass.TERMINAL_IDLE);
            }
            foreach (string state in new[] { "WAITING", "TRANSCRIBING", "CANCEL_REQUESTED", "NEW_STATE" })
            {
                Check("rust: job " + state + " holds", SyntheticFixtures.ExpectedProductCode(SyntheticFixtures.Classify("{\"job\":{\"status\":\"" + state + "\",\"files\":{}}}")) == "ACTIVE_OR_UNKNOWN_JOB");
                Check("rust: file " + state + " holds", SyntheticFixtures.ExpectedProductCode(SyntheticFixtures.Classify("{\"job\":{\"status\":\"DONE\",\"files\":{\"f\":\"" + state + "\"}}}")) == "ACTIVE_OR_UNKNOWN_JOB");
            }
            foreach (string state in new[] { "PENDING", "UPLOADING", "NEW_STATE" })
            {
                Check("rust: drive " + state + " holds", SyntheticFixtures.ExpectedProductCode(SyntheticFixtures.Classify("{\"job\":{\"status\":\"DONE\",\"files\":{},\"drive\":{\"f\":{\"status\":\"" + state + "\"}}}}")) == "ACTIVE_OR_UNKNOWN_DRIVE");
            }
            foreach (string bad in new[] { "bad", "[]", "{\"job\":{}}", "{\"job\":{\"status\":\"DONE\",\"files\":null}}", "{\"job\":{\"status\":\"DONE\",\"files\":{},\"drive\":null}}", "{\"job\":{\"status\":1,\"files\":{}}}" })
            {
                Check("rust: malformed holds " + bad, SyntheticFixtures.ExpectedProductCode(SyntheticFixtures.Classify(bad)) == "JOB_STATE_UNKNOWN");
            }
            Check("rust: missing file holds", SyntheticFixtures.ExpectedProductCode(SyntheticFixtures.Classify((string)null)) == "JOB_STATE_UNKNOWN"
                && SyntheticFixtures.Classify((byte[])null) == FixtureClass.MISSING);
            byte[] utf8 = Encoding.UTF8.GetBytes(jobsA);
            Check("bytes: valid UTF-8 terminal", SyntheticFixtures.Classify(utf8) == FixtureClass.TERMINAL_IDLE);
            var withBom = new byte[utf8.Length + 3];
            withBom[0] = 0xEF; withBom[1] = 0xBB; withBom[2] = 0xBF;
            Array.Copy(utf8, 0, withBom, 3, utf8.Length);
            Check("bytes: BOM malformed (serde rejects)", SyntheticFixtures.Classify(withBom) == FixtureClass.MALFORMED);
            Check("bytes: invalid UTF-8 malformed", SyntheticFixtures.Classify(new byte[] { 0x7B, 0x22, 0xC3, 0x28, 0x22, 0x3A, 0x7B, 0x7D, 0x7D }) == FixtureClass.MALFORMED);
            Check("oversize history ambiguous, not JOB_STATE_UNKNOWN", SyntheticFixtures.Classify("{}" + new string(' ', StrictJson.MaxLength)) == FixtureClass.AMBIGUOUS);
            Check("rust: malformed later job beats earlier active", SyntheticFixtures.Classify("{\"a\":{\"status\":\"WAITING\",\"files\":{}},\"b\":{}}") == FixtureClass.MALFORMED);
            Check("rust: job state before drive", SyntheticFixtures.Classify("{\"a\":{\"status\":\"WAITING\",\"files\":{},\"drive\":{\"f\":{\"status\":\"UPLOADING\"}}}}") == FixtureClass.ACTIVE_JOB);
            Check("duplicate keys ambiguous, no expectation", SyntheticFixtures.Classify("{\"a\":{\"status\":\"DONE\",\"files\":{}},\"a\":{\"status\":\"DONE\",\"files\":{}}}") == FixtureClass.AMBIGUOUS
                && ThrowsArg(() => SyntheticFixtures.ExpectedProductCode(FixtureClass.AMBIGUOUS)));

            Check("write only when OFFLINE confirmed", FixtureWritePolicy.MayReplace("OFFLINE_CONFIRMED"));
            foreach (string state in new[] { "ONLINE", "OFFLINE", "UNKNOWN", "offline_confirmed", "", null })
            {
                Check("no write when " + (state ?? "null"), !FixtureWritePolicy.MayReplace(state));
            }
        }

        private static string WithJob(Action<JsonObject> change)
        {
            JsonObject jobs = Obj(SyntheticFixtures.JobsJson(Root, 'A'));
            change((JsonObject)jobs.Get(SyntheticFixtures.JobId('A')));
            return JsonText.Write(jobs);
        }

        private static JsonObject AddSecondJob(JsonObject jobs)
        {
            JsonObject copy = Obj(JsonText.Write(jobs));
            copy.TryAdd(SyntheticFixtures.JobId('B'), Obj(SyntheticFixtures.JobsJson(Root, 'B')).Get(SyntheticFixtures.JobId('B')));
            return copy;
        }

        private static void ExpectSettings(string name, string text, string reason)
        {
            Check(name, SyntheticFixtures.ValidateSettings(text, Root, 'A', Protected).Has(reason));
        }

        private static void ExpectJobs(string name, string text, string reason)
        {
            Check(name, SyntheticFixtures.ValidateJobs(text, Root, 'A', Protected).Has(reason));
        }

        private static void ExpectClass(NegativeFixture kind, FixtureClass expected, string code)
        {
            FixtureClass actual = SyntheticFixtures.Classify(SyntheticFixtures.NegativeJobsJson(Root, kind));
            Check("negative " + kind + " -> " + expected, actual == expected && SyntheticFixtures.ExpectedProductCode(actual) == code);
        }
    }
}
