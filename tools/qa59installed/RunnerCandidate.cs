// Separate identity for a fresh hosted source build. Never an amendment to the
// original pinned MSI contract, and never an execution authorization.
using System;

namespace Qa59Installed
{
    public sealed class RunnerCandidate
    {
        public const string Kind = "QA59_RUNNER_SOURCE_CANDIDATE";
        private static readonly string[] Keys = { "schema", "kind", "source_head", "qa_head", "run_id", "origin", "source_clean", "original_candidate", "msi_sha256", "msi_size_bytes", "desktop_sha256", "core_sha256", "ffmpeg_sha256", "manifest_sha256" };
        public readonly string QaHead, MsiHash, DesktopHash, CoreHash, FfmpegHash, ManifestHash;
        public readonly long RunId, MsiSize;
        private RunnerCandidate(JsonObject obj)
        {
            QaHead = (string)obj.Get("qa_head"); RunId = (long)obj.Get("run_id");
            MsiHash = (string)obj.Get("msi_sha256"); MsiSize = (long)obj.Get("msi_size_bytes");
            DesktopHash = (string)obj.Get("desktop_sha256"); CoreHash = (string)obj.Get("core_sha256");
            FfmpegHash = (string)obj.Get("ffmpeg_sha256"); ManifestHash = (string)obj.Get("manifest_sha256");
        }
        public static RunnerCandidate Validate(string text, string measuredMsi, long measuredSize, string expectedQa, long expectedRun, Outcome outcome)
        {
            JsonObject obj = Fields.ParseObject(text, outcome);
            if (obj == null || !Fields.ExactKeys(obj, Keys, outcome, "RUNNER_CANDIDATE_")) return null;
            if (!1L.Equals(obj.Get("schema")) || !Kind.Equals(obj.Get("kind")) || !"FRESH_HOSTED_SOURCE".Equals(obj.Get("origin"))) outcome.Add("RUNNER_CANDIDATE_KIND");
            if (!CandidatePins.ProductHead.Equals(obj.Get("source_head")) || !true.Equals(obj.Get("source_clean")) || !false.Equals(obj.Get("original_candidate"))) outcome.Add("RUNNER_CANDIDATE_SOURCE");
            if (!Fields.IsLowerHex(expectedQa, 40) || expectedQa == CandidatePins.ProductHead || !expectedQa.Equals(obj.Get("qa_head"))) outcome.Add("RUNNER_CANDIDATE_QA");
            if (expectedRun <= 0 || !expectedRun.Equals(obj.Get("run_id"))) outcome.Add("RUNNER_CANDIDATE_RUN");
            foreach (string key in new[] { "msi_sha256", "desktop_sha256", "core_sha256", "ffmpeg_sha256", "manifest_sha256" })
                if (!Fields.IsLowerHex(obj.Get(key) as string, 64)) outcome.Add("RUNNER_CANDIDATE_DIGEST");
            if (measuredMsi == null || !string.Equals(measuredMsi, obj.Get("msi_sha256") as string, StringComparison.Ordinal) || measuredSize <= 0 || !measuredSize.Equals(obj.Get("msi_size_bytes"))) outcome.Add("RUNNER_CANDIDATE_BYTES");
            return outcome.Ok ? new RunnerCandidate(obj) : null;
        }
    }
}
