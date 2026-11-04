using System;
using System.Text;

// Pure policy tests: no WebView instance, GUI, network or OS input is created.
public static class SyntheticNavigationPermitTests
{
    static int assertions;
    static void Check(bool condition) { assertions++; if (!condition) throw new Exception("Navigation policy contract failed"); }
    static string Representation(string html) { return "data:text/html;charset=utf-8;base64," + Convert.ToBase64String(Encoding.UTF8.GetBytes(html)); }
    static bool RearmDenied(SyntheticNavigationPermit p, string html) {
        try { p.Arm(html); return false; } catch (InvalidOperationException) { return true; }
    }
    public static void Main() {
        string html = "<!doctype html><button>synthetic</button><script>const nonce='owned-A';</script>";
        string canonical = Representation(html);
        var accepted = new SyntheticNavigationPermit();
        accepted.Arm(html);
        Check(accepted.TryConsume(canonical, false, 7));
        Check(accepted.Accepted == 1 && accepted.ApprovedId == 7 && !accepted.Armed && accepted.Closed);
        Check(!accepted.TryConsume(canonical, false, 7)); // Same ID does not grant another start.
        Check(!accepted.TryConsume(canonical, false, 8));
        Check(RearmDenied(accepted, html));

        string[] rejected = {
            "http://example.invalid/", "https://example.invalid/", "file:///unused",
            "javascript:void(0)", "custom:unknown", "about:blank", "about:blank#fragment",
            "data:text/html;base64," + Convert.ToBase64String(Encoding.UTF8.GetBytes(html)),
            "data:text/plain;charset=utf-8;base64," + Convert.ToBase64String(Encoding.UTF8.GetBytes(html)),
            Representation(html.Replace("owned-A", "owned-B")), Representation(html + " "),
            canonical + "#fragment", canonical + "?query", canonical + "\n",
            "DATA" + canonical.Substring(4), "data:text/html;charset=utf-8;base64,broken", "", null
        };
        foreach (string uri in rejected) {
            var p = new SyntheticNavigationPermit(); p.Arm(html);
            Check(!p.TryConsume(uri, false, 9));
            Check(!p.Armed && p.Closed && p.Accepted == 0 && p.Blocked == 1);
            Check(!p.TryConsume(canonical, false, 10)); // Mismatch consumes the permit.
            Check(RearmDenied(p, html));
        }
        var redirect = new SyntheticNavigationPermit(); redirect.Arm(html);
        Check(!redirect.TryConsume(canonical, true, 11));
        Check(!redirect.TryConsume(canonical, false, 11));
        var unarmed = new SyntheticNavigationPermit();
        Check(!unarmed.TryConsume(canonical, false, 12)); Check(RearmDenied(unarmed, html));
        var closed = new SyntheticNavigationPermit(); closed.Arm(html); closed.Close();
        Check(!closed.TryConsume(canonical, false, 13)); Check(RearmDenied(closed, html));
        var synchronousFailure = new SyntheticNavigationPermit(); synchronousFailure.Arm(html); synchronousFailure.Close();
        Check(!synchronousFailure.TryConsume(canonical, false, 14));
        var independent = new SyntheticNavigationPermit(); independent.Arm(html);
        Check(independent.TryConsume(canonical, false, 15)); // View-local, no global exemption.
        Console.WriteLine("NAVIGATION_POLICY_ASSERTIONS=" + assertions + "; PASS; GUI_NETWORK_INPUT=NOT_RUN");
    }
}
