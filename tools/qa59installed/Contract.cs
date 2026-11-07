// Shared vocabulary for the #59 installed-QA contracts. Pure: no I/O.
using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;

// This friendship exists only in an explicitly test-only build. Assembly names
// are not identities: never ship the QA59_CONTRACT_TESTS build as authority.
#if QA59_CONTRACT_TESTS
[assembly: InternalsVisibleTo("ContractTests")]
#endif

namespace Qa59Installed
{
    // Severity order matters: a later record may only move a verdict right.
    public enum Verdict { PASS = 0, NOT_VERIFIED = 1, FAIL = 2 }

    // The candidate tuple fixed by the 2026-11-07 private-preparation review.
    // These are product/build identities; none of them is a QA commit.
    public static class CandidatePins
    {
        public const string ProductRepository = "bongbong90/Sorigul";
        public const long ProductRepositoryId = 1327637229;
        public const long ProductPr = 216;
        public const string ProductHead = "890364e21a4e80d2ff5185332834b4dbb67aeb01";
        public const string ReleaseFreezeSha256 = "9c6c21c08049a36d7c9111a070d3bc0ae4b72e4598bc613dbbbb666e4c637cbd";
        public const string OriginalBuildRun = "Sorigul_20261101_890364e_a00202c7532b";
        public const string MsiSha256 = "002b94e82caeb7d540e4f0834ecfb1b191491fbd226eb6cee457a03062ea0166";
        public const long MsiSizeBytes = 70606848;
        public const string DesktopSha256 = "2bd26d28cba80aceb8fa6b1fa93632c315350fc36f83953d073d434b85da66a5";
        public const string CoreSha256 = "ab4286af74542f03e8da1d3076301f870aed8e8124c899267229b9ee2558b669";
        public const string FfmpegSha256 = "2ce797a0f88d7f067180338fb227f7b1928ea727bd9a4d7a1d022f7c52af71a3";
        public const string EmbeddedManifestSha256 = "beff844e393f0313ef746aaf9658d8a6c81b2c92e1f87c629ebaf390b486e3b7";
    }

    public sealed class Outcome
    {
        private readonly List<string> reasons = new List<string>();
        private bool frozen;
        public Outcome Snapshot()
        {
            var copy = new Outcome();
            copy.reasons.AddRange(reasons);
            copy.frozen = true;
            return copy;
        }
        public bool Ok { get { return reasons.Count == 0; } }
        public IList<string> Reasons { get { return reasons.AsReadOnly(); } }
        public bool Has(string reason) { return reasons.Contains(reason); }

        public void Add(string reason)
        {
            if (frozen) throw new InvalidOperationException("OUTCOME_FROZEN");
            if (!reasons.Contains(reason)) reasons.Add(reason);
        }
    }

    internal static class Fields
    {
        public static JsonObject ParseObject(string text, Outcome outcome)
        {
            try
            {
                var obj = StrictJson.Parse(text) as JsonObject;
                if (obj == null) outcome.Add("ROOT_NOT_OBJECT");
                return obj;
            }
            catch (JsonFormatException e)
            {
                outcome.Add(e.Code);
                return null;
            }
        }

        // Exact allowlist: every expected key present, nothing else.
        public static bool ExactKeys(JsonObject obj, string[] keys, Outcome outcome, string prefix)
        {
            bool ok = true;
            foreach (string key in keys)
            {
                if (!obj.Has(key)) { outcome.Add(prefix + "MISSING_KEY"); ok = false; }
            }
            var allowed = new HashSet<string>(keys, StringComparer.Ordinal);
            foreach (string key in obj.Keys)
            {
                if (!allowed.Contains(key)) { outcome.Add(prefix + "UNKNOWN_KEY"); ok = false; }
            }
            return ok;
        }

        public static bool IsNull(object value) { return value is JsonNull; }

        public static bool IsLowerHex(string value, int length)
        {
            if (value == null || value.Length != length) return false;
            foreach (char c in value)
            {
                if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) return false;
            }
            return true;
        }

        public static bool IsAnyCaseHex(string value, int length)
        {
            // Char-by-char ASCII check: culture lowercasing could fold non-ASCII into hex.
            if (value == null || value.Length != length) return false;
            foreach (char c in value)
            {
                if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F'))) return false;
            }
            return true;
        }

        public static IEnumerable<string> Strings(object value)
        {
            var text = value as string;
            if (text != null) { yield return text; yield break; }
            var obj = value as JsonObject;
            if (obj != null)
            {
                foreach (string key in obj.Keys)
                {
                    yield return key;
                    foreach (string nested in Strings(obj.Get(key))) yield return nested;
                }
                yield break;
            }
            var list = value as List<object>;
            if (list != null)
            {
                foreach (object item in list)
                {
                    foreach (string nested in Strings(item)) yield return nested;
                }
            }
        }
    }
}
