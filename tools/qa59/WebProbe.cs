using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Automation;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

// One view, one host-owned document, one callback. No URI is trusted by scheme alone.
public sealed class SyntheticNavigationPermit
{
    string expected;
    bool everArmed, closed;
    public bool Armed { get; private set; }
    public bool Closed { get { return closed; } }
    public bool ContentMatch { get; private set; }
    public int Accepted { get; private set; }
    public int Blocked { get; private set; }
    public ulong? ApprovedId { get; private set; }
    public void Arm(string html) {
        if (everArmed || closed) throw new InvalidOperationException("Permit cannot be rearmed");
        if (string.IsNullOrEmpty(html) || Encoding.UTF8.GetByteCount(html) > 2 * 1024 * 1024) throw new ArgumentException("Invalid synthetic size");
        // Supported representation, not a claim about any unknown runtime's actual URI.
        // Exact equality includes the entire host-owned HTML and this document's fresh nonce.
        expected = "data:text/html;charset=utf-8;base64," + Convert.ToBase64String(Encoding.UTF8.GetBytes(html));
        everArmed = true; Armed = true;
    }
    public bool TryConsume(string uri, bool redirected, ulong navigationId) {
        bool eligible = Armed && !closed;
        string candidate = expected;
        Close(); // A mismatch, redirect or unexpected first callback also burns the permit.
        ContentMatch = eligible && uri != null && candidate != null && uri.Length == candidate.Length &&
            string.Equals(uri, candidate, StringComparison.Ordinal);
        if (!eligible || redirected || !ContentMatch) { Blocked++; return false; }
        Accepted++; ApprovedId = navigationId;
        return true;
    }
    public void Close() { Armed = false; closed = true; expected = null; }
    public void Observe(WebDiagnostics d) {
        d.Put("navigation_permit_armed", Armed); d.Put("navigation_permit_closed", Closed);
        d.Put("navigation_content_match", ContentMatch);
        d.Put("navigation_accepted_count", Accepted); d.Put("navigation_blocked_count", Blocked);
        d.Put("approved_nav_id", ApprovedId.HasValue ? (object)ApprovedId.Value : null);
    }
}

public static class WebProbe
{
    public static async Task<string> Run(Form form, string work) {
        var d = new WebDiagnostics();
        var permit = new SyntheticNavigationPermit();
        string snapshotReason = "exception";
        try {
            using (var view = new WebView2 { Dock = DockStyle.Fill }) {
                form.Controls.Add(view);
                // Existing isolation/security settings, selector and timing are preserved.
                var options = new CoreWebView2EnvironmentOptions();
                options.AdditionalBrowserArguments = "--disable-background-networking";
                var environment = await CoreWebView2Environment.CreateAsync(null, Path.Combine(work, "synthetic-profile"), options);
                await view.EnsureCoreWebView2Async(environment);
                d.Put("initialized", true); d.Mark("initialized", "initialized_ms");
                string version = view.CoreWebView2.Environment.BrowserVersionString;
                File.WriteAllText(Path.Combine(work, "runtime-version.txt"), version);
                view.CoreWebView2.Settings.AreDevToolsEnabled = false;
                view.CoreWebView2.Settings.AreDefaultContextMenusEnabled = false;
                view.CoreWebView2.Settings.IsStatusBarEnabled = false;
                view.CoreWebView2.NavigationStarting += delegate(object sender, CoreWebView2NavigationStartingEventArgs e) {
                    if (!permit.TryConsume(e.Uri, e.IsRedirected, e.NavigationId)) e.Cancel = true;
                    permit.Observe(d);
                    d.Count("navigation_start_count"); d.Put("nav_start_id", e.NavigationId);
                    d.Put("navigation_source_match", e.Uri == "about:blank"); d.Put("navigation_cancelled", e.Cancel);
                    d.Mark("navigation_start", "navigation_start_ms");
                };
                view.CoreWebView2.NavigationCompleted += delegate(object sender, CoreWebView2NavigationCompletedEventArgs e) {
                    permit.Close(); permit.Observe(d);
                    d.Count("navigation_complete_count"); d.Put("nav_complete_id", e.NavigationId);
                    d.Put("navigation_completed_success", e.IsSuccess); d.Put("nav_error", (int)e.WebErrorStatus);
                    d.Mark("navigation_complete", "navigation_complete_ms");
                };
                view.CoreWebView2.DOMContentLoaded += delegate(object sender, CoreWebView2DOMContentLoadedEventArgs e) {
                    d.Count("dom_count"); d.Put("dom_loaded", true); d.Put("dom_nav_id", e.NavigationId); d.Mark("dom", "dom_ms");
                };
                view.CoreWebView2.AddWebResourceRequestedFilter("*", CoreWebView2WebResourceContext.All);
                view.CoreWebView2.WebResourceRequested += delegate(object sender, CoreWebView2WebResourceRequestedEventArgs e) {
                    if (e.Request.Uri.StartsWith("http", StringComparison.OrdinalIgnoreCase))
                        e.Response = environment.CreateWebResourceResponse(new MemoryStream(new byte[0]), 403, "Blocked", "");
                };
                string nonce = Guid.NewGuid().ToString("N");
                bool trustedClick = false;
                view.CoreWebView2.WebMessageReceived += delegate(object sender, CoreWebView2WebMessageReceivedEventArgs e) {
                    d.Count("webmessage_count"); d.Mark("message", "message_ms");
                    try {
                        string message = e.TryGetWebMessageAsString();
                        bool legacyMatch = message == "QA59 trusted button input";
                        bool sourceMatch = e.Source == "about:blank";
                        if (legacyMatch || !d.IsTrue("legacy_message_match")) d.Put("legacy_message_match", legacyMatch);
                        // Preserve the original predicate; diagnostics cannot set this flag.
                        if (legacyMatch && sourceMatch) trustedClick = true;
                        if (legacyMatch) { d.Put("legacy_message_match", true); d.Put("legacy_source_match", sourceMatch); return; }
                        if (message == null || message.Length > 2048) { d.Count("diagnostic_parse_errors"); return; }
                        var p = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(message);
                        if (p == null || !p.ContainsKey("schema") || !(p["schema"] is int) || (int)p["schema"] != 1 ||
                            !p.ContainsKey("kind") || !(p["kind"] is string) || !p.ContainsKey("nonce") || !(p["nonce"] is string)) {
                            d.Count("diagnostic_parse_errors"); return;
                        }
                        bool nonceMatch = (string)p["nonce"] == nonce;
                        if ((string)p["kind"] == "document-ready" && p.Count == 5 && p.ContainsKey("readyState") && p["readyState"] is string && p.ContainsKey("buttonExists") && p["buttonExists"] is bool) {
                            string state = (string)p["readyState"];
                            if (state != "loading" && state != "interactive" && state != "complete") { d.Count("diagnostic_parse_errors"); return; }
                            d.Count("document_ready_count");
                            d.Put("doc_source_match", sourceMatch); d.Put("doc_nonce_match", nonceMatch);
                            d.Put("ready_state", state); d.Put("doc_button_exists", p["buttonExists"]);
                            d.Put("doc_ready", sourceMatch && nonceMatch && (bool)p["buttonExists"] && (state == "interactive" || state == "complete"));
                            d.Mark("document_ready", "document_ready_ms");
                        } else if ((string)p["kind"] == "click-observed" && p.Count == 4 && p.ContainsKey("trusted") && p["trusted"] is bool) {
                            d.Count("click_diag_count");
                            d.Put("click_diag_received", true); d.Put("click_source_match", sourceMatch); d.Put("click_nonce_match", nonceMatch);
                            d.Put("event_trusted", p["trusted"]); d.Mark("click", "click_ms");
                        } else { d.Count("diagnostic_parse_errors"); }
                    } catch { d.Count("diagnostic_parse_errors"); }
                };
                // Ordinary inline page code: no automation-side JS invocation or synthetic events.
                string clickDiagnostic = "try{window.chrome.webview.postMessage(JSON.stringify({schema:1,kind:'click-observed',nonce:'" + nonce + "',trusted:event.isTrusted}));}catch(_){}";
                string readyScript = "<script>document.addEventListener('DOMContentLoaded',()=>{window.chrome.webview.postMessage(JSON.stringify({schema:1,kind:'document-ready',nonce:'" + nonce + "',readyState:document.readyState,buttonExists:document.getElementById('qa59-input')!==null}));});</script>";
                string html = "<!doctype html><meta charset='utf-8'><meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'\"><title>QA59 synthetic</title><button id='qa59-input' style='margin:80px;width:240px;height:80px' onclick=\"if(event.isTrusted)window.chrome.webview.postMessage('QA59 trusted button input');" + clickDiagnostic + "\">QA59 WebView input</button>" + readyScript;
                d.Put("navigation_requested", true); d.Mark("navigate", "navigate_ms");
                permit.Arm(html); permit.Observe(d);
                try { view.CoreWebView2.NavigateToString(html); }
                catch { permit.Close(); permit.Observe(d); throw; }
                form.Activate(); view.Focus();
                d.Put("focus_view", view.ContainsFocus);
                IntPtr root = form.Handle; // Capture on UI thread, before worker observation.
                bool clicked = await Task.Run(async delegate {
                    var e = await ProbeInput.WaitFor(AutomationElement.FromHandle(root), "QA59 WebView input", d);
                    d.Put("focus_foreground", ProbeInput.GetForegroundWindow() == root);
                    return ProbeInput.Click(e, false, d);
                });
                await Task.Delay(750); // Original sampling boundary; no readiness wait added.
                d.Put("clicked", clicked); d.Put("legacy_trusted", trustedClick); d.Put("legacy_predicate", clicked && trustedClick);
                bool allowlist = permit.Accepted == 1 && permit.Closed && !permit.Armed &&
                    d.Equal("approved_nav_id", "nav_complete_id") && d.IsTrue("navigation_completed_success");
                d.Put("navigation_allowlist_pass", allowlist);
                bool pass = allowlist && clicked && trustedClick && d.IsTrue("navigation_completed_success") && d.IsTrue("dom_loaded") &&
                    d.Equal("nav_complete_id", "dom_nav_id") && d.IsTrue("doc_ready") && d.IsTrue("uia_usable") &&
                    d.IsCount("uia_control_type", ControlType.Button.Id) && d.IsTrue("uia_rect_valid") &&
                    d.IsCount("sendinput_return", 2) && d.IsTrue("click_diag_received") && d.IsTrue("click_source_match") &&
                    d.IsTrue("click_nonce_match") && d.IsTrue("event_trusted");
                d.Put("diagnostic_pass", pass); d.Mark("verdict", "verdict_ms"); snapshotReason = "verdict";
                // Freeze before control disposal can deliver any later callback.
                d.FreezeAndWrite(Path.Combine(work, "webview-diagnostic.json"), snapshotReason);
                return pass ? "PASS" : "WebView created; diagnostic interaction gates not all proven";
            }
        } catch (Exception e) {
            d.Put("exception_type", e.GetType().Name); d.Put("skip_reason", "exception");
            throw;
        } finally {
            permit.Close(); permit.Observe(d);
            // Hard process termination cannot guarantee finally; absence stays NOT VERIFIED.
            d.FreezeAndWrite(Path.Combine(work, "webview-diagnostic.json"), snapshotReason);
        }
    }
}
