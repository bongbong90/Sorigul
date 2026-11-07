// Candidate manifest validation and MSI/installed-file observation. Pure: the
// caller supplies the text and the digests it measured; nothing is read here.
// A valid manifest identifies bytes. It never authorizes download or install.
using System;
using System.Collections.Generic;

namespace Qa59Installed
{
    public sealed class CandidateManifest
    {
        public const string Kind = "QA59_CANDIDATE_MANIFEST";

        // A QA commit is deliberately absent: the QA SHA is bound by the
        // execution context/approval, never by a file inside that commit.
        public static readonly string[] Keys =
        {
            "schema", "kind", "not_execution_authorization",
            "product_repository", "product_pr", "product_head",
            "release_freeze_sha256", "original_build_run",
            "msi_sha256", "msi_size_bytes",
            "desktop_sha256", "core_sha256", "ffmpeg_sha256", "embedded_manifest_sha256",
        };

        private static readonly string[] DigestKeys =
        {
            "release_freeze_sha256", "msi_sha256", "desktop_sha256",
            "core_sha256", "ffmpeg_sha256", "embedded_manifest_sha256",
        };

        public readonly string ProductHead;
        public readonly string MsiSha256;
        public readonly long MsiSizeBytes;
        public readonly string DesktopSha256;
        public readonly string CoreSha256;
        public readonly string FfmpegSha256;
        public readonly string EmbeddedManifestSha256;

        private CandidateManifest(JsonObject obj)
        {
            ProductHead = (string)obj.Get("product_head");
            MsiSha256 = (string)obj.Get("msi_sha256");
            MsiSizeBytes = (long)obj.Get("msi_size_bytes");
            DesktopSha256 = (string)obj.Get("desktop_sha256");
            CoreSha256 = (string)obj.Get("core_sha256");
            FfmpegSha256 = (string)obj.Get("ffmpeg_sha256");
            EmbeddedManifestSha256 = (string)obj.Get("embedded_manifest_sha256");
        }

        // Returns null unless every field is present, typed, well-formed and
        // equal to the pinned candidate. outcome lists fixed reason codes.
        public static CandidateManifest Validate(string text, Outcome outcome)
        {
            JsonObject obj = Fields.ParseObject(text, outcome);
            if (obj == null) return null;
            if (!Fields.ExactKeys(obj, Keys, outcome, "MANIFEST_")) return null;

            RequireLong(obj, "schema", 1, outcome);
            RequireString(obj, "kind", Kind, outcome);
            if (!true.Equals(obj.Get("not_execution_authorization"))) outcome.Add("MANIFEST_AUTHORIZATION_CLAIM");
            RequireString(obj, "product_repository", CandidatePins.ProductRepository, outcome);
            RequireLong(obj, "product_pr", CandidatePins.ProductPr, outcome);
            RequireString(obj, "original_build_run", CandidatePins.OriginalBuildRun, outcome);
            RequireLong(obj, "msi_size_bytes", CandidatePins.MsiSizeBytes, outcome);

            if (!Fields.IsLowerHex(obj.Get("product_head") as string, 40)) outcome.Add("MANIFEST_PRODUCT_HEAD_FORMAT");
            RequireString(obj, "product_head", CandidatePins.ProductHead, outcome);

            var seen = new HashSet<string>(StringComparer.Ordinal);
            foreach (string key in DigestKeys)
            {
                var digest = obj.Get(key) as string;
                if (!Fields.IsLowerHex(digest, 64)) { outcome.Add("MANIFEST_DIGEST_FORMAT"); continue; }
                if (!seen.Add(digest)) outcome.Add("MANIFEST_DIGEST_REUSED");
            }
            RequireString(obj, "release_freeze_sha256", CandidatePins.ReleaseFreezeSha256, outcome);
            RequireString(obj, "msi_sha256", CandidatePins.MsiSha256, outcome);
            RequireString(obj, "desktop_sha256", CandidatePins.DesktopSha256, outcome);
            RequireString(obj, "core_sha256", CandidatePins.CoreSha256, outcome);
            RequireString(obj, "ffmpeg_sha256", CandidatePins.FfmpegSha256, outcome);
            RequireString(obj, "embedded_manifest_sha256", CandidatePins.EmbeddedManifestSha256, outcome);

            return outcome.Ok ? new CandidateManifest(obj) : null;
        }

        private static void RequireString(JsonObject obj, string key, string expected, Outcome outcome)
        {
            var value = obj.Get(key) as string;
            if (value == null || !string.Equals(value, expected, StringComparison.Ordinal))
                outcome.Add("MANIFEST_" + key.ToUpperInvariant() + "_MISMATCH");
        }

        private static void RequireLong(JsonObject obj, string key, long expected, Outcome outcome)
        {
            object value = obj.Get(key);
            if (!(value is long) || (long)value != expected)
                outcome.Add("MANIFEST_" + key.ToUpperInvariant() + "_MISMATCH");
        }
    }

    public static class Observation
    {
        // observedSha256 is a digest the caller computed from the bytes it
        // holds (Get-FileHash style, any case). Null = not measured.
        public static Verdict Msi(CandidateManifest manifest, string observedSha256, long? observedSize)
        {
            if (manifest == null) return Verdict.FAIL;
            if (observedSha256 == null || !observedSize.HasValue) return Verdict.NOT_VERIFIED;
            if (!Fields.IsAnyCaseHex(observedSha256, 64)) return Verdict.FAIL;
            if (observedSize.Value != manifest.MsiSizeBytes) return Verdict.FAIL;
            return string.Equals(observedSha256, manifest.MsiSha256, StringComparison.OrdinalIgnoreCase)
                ? Verdict.PASS : Verdict.FAIL;
        }

        // Step 3: installed Desktop/Core/FFmpeg/manifest bytes. Every digest
        // must be measured; one unmeasured file keeps the step NOT_VERIFIED.
        public static Verdict InstalledFiles(CandidateManifest manifest, string desktop, string core, string ffmpeg, string embeddedManifest)
        {
            if (manifest == null) return Verdict.FAIL;
            var pairs = new[]
            {
                new[] { manifest.DesktopSha256, desktop },
                new[] { manifest.CoreSha256, core },
                new[] { manifest.FfmpegSha256, ffmpeg },
                new[] { manifest.EmbeddedManifestSha256, embeddedManifest },
            };
            Verdict worst = Verdict.PASS;
            foreach (string[] pair in pairs)
            {
                Verdict v;
                if (pair[1] == null) v = Verdict.NOT_VERIFIED;
                else if (!Fields.IsAnyCaseHex(pair[1], 64)) v = Verdict.FAIL;
                else v = string.Equals(pair[0], pair[1], StringComparison.OrdinalIgnoreCase) ? Verdict.PASS : Verdict.FAIL;
                if (v > worst) worst = v;
            }
            return worst;
        }
    }

    public static class InstallerPermit
    {
        // msiexec may be invoked only when all three independent facts hold.
        public static bool MayInvokeMsiexec(CandidateManifest manifest, Verdict msiObservation, GateDecision gate)
        {
            return manifest != null
                && msiObservation == Verdict.PASS
                && gate != null
                && gate.MsiInstallAllowed;
        }
    }
}
