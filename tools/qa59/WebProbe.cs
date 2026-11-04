using System;
using System.IO;
using System.Threading.Tasks;
using System.Windows.Automation;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

public static class WebProbe
{
    public static async Task<string> Run(Form form, string work) {
        using (var view = new WebView2 { Dock = DockStyle.Fill }) {
            form.Controls.Add(view);
            // Fresh synthetic profile. No debugging port, external account or remote page.
            var options = new CoreWebView2EnvironmentOptions();
            options.AdditionalBrowserArguments = "--disable-background-networking";
            var environment = await CoreWebView2Environment.CreateAsync(null, Path.Combine(work, "synthetic-profile"), options);
            await view.EnsureCoreWebView2Async(environment);
            string version = view.CoreWebView2.Environment.BrowserVersionString;
            File.WriteAllText(Path.Combine(work, "runtime-version.txt"), version);
            view.CoreWebView2.Settings.AreDevToolsEnabled = false;
            view.CoreWebView2.Settings.AreDefaultContextMenusEnabled = false;
            view.CoreWebView2.Settings.IsStatusBarEnabled = false;
            view.CoreWebView2.NavigationStarting += delegate(object sender, CoreWebView2NavigationStartingEventArgs e) {
                if (!e.Uri.StartsWith("about:blank", StringComparison.Ordinal)) e.Cancel = true;
            };
            view.CoreWebView2.AddWebResourceRequestedFilter("*", CoreWebView2WebResourceContext.All);
            view.CoreWebView2.WebResourceRequested += delegate(object sender, CoreWebView2WebResourceRequestedEventArgs e) {
                if (e.Request.Uri.StartsWith("http", StringComparison.OrdinalIgnoreCase))
                    e.Response = environment.CreateWebResourceResponse(new MemoryStream(new byte[0]), 403, "Blocked", "");
            };
            bool trustedClick = false;
            view.CoreWebView2.WebMessageReceived += delegate(object sender, CoreWebView2WebMessageReceivedEventArgs e) {
                if (e.TryGetWebMessageAsString() == "QA59 trusted button input" && e.Source == "about:blank") trustedClick = true;
            };
            view.CoreWebView2.NavigateToString("<!doctype html><meta charset='utf-8'><meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'\"><title>QA59 synthetic</title><button style='margin:80px;width:240px;height:80px' onclick=\"if(event.isTrusted)window.chrome.webview.postMessage('QA59 trusted button input')\">QA59 WebView input</button>");
            form.Activate(); view.Focus();
            bool clicked = await Task.Run(async delegate {
                var e = await ProbeInput.WaitFor(AutomationElement.FromHandle(form.Handle), "QA59 WebView input");
                return ProbeInput.Click(e, false);
            });
            await Task.Delay(750);
            return clicked && trustedClick ? "PASS" : "WebView created; trusted OS button interaction not proven";
        }
    }
}
