using System;
using System.Collections.Generic;
using System.IO;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Automation;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

public static class WebProbe
{
    public static async Task<string> Run(Form form, string work) {
        var d = new WebDiagnostics();
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
                    if (!e.Uri.StartsWith("about:blank", StringComparison.Ordinal)) e.Cancel = true;
                    d.Count("navigation_start_count"); d.Put("nav_start_id", e.NavigationId);
                    d.Put("navigation_source_match", e.Uri == "about:blank"); d.Put("navigation_cancelled", e.Cancel);
                    d.Mark("navigation_start", "navigation_start_ms");
                };
                view.CoreWebView2.NavigationCompleted += delegate(object sender, CoreWebView2NavigationCompletedEventArgs e) {
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
                view.CoreWebView2.NavigateToString(html);
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
                bool pass = clicked && trustedClick && d.IsTrue("navigation_completed_success") && d.IsTrue("dom_loaded") &&
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
            // Hard process termination cannot guarantee finally; absence stays NOT VERIFIED.
            d.FreezeAndWrite(Path.Combine(work, "webview-diagnostic.json"), snapshotReason);
        }
    }
}
