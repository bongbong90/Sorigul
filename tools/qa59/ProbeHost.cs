using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Automation;
using System.Windows.Forms;

// Synthetic, bounded measurements only. Freeze excludes callbacks after the verdict point.
public sealed class WebDiagnostics
{
    readonly object gate = new object();
    readonly Stopwatch watch = Stopwatch.StartNew();
    readonly Dictionary<string, object> values = new Dictionary<string, object>();
    readonly List<object> events = new List<object>();
    bool frozen;
    public WebDiagnostics() {
        values["schema"] = 3;
        foreach (string key in "navigation_permit_armed navigation_permit_closed navigation_content_match navigation_allowlist_pass".Split(' ')) values[key] = null;
        values["navigation_accepted_count"] = 0; values["navigation_blocked_count"] = 0; values["approved_nav_id"] = null;
        foreach (string key in ("initialized navigation_requested navigation_completed_success navigation_source_match navigation_cancelled dom_loaded doc_ready doc_button_exists doc_source_match doc_nonce_match legacy_message_match legacy_source_match click_diag_received click_source_match click_nonce_match event_trusted uia_started uia_found uia_usable uia_name_match uia_offscreen uia_rect_valid focus_view focus_foreground cursor_attempted cursor_success sendinput_attempted clicked legacy_trusted legacy_predicate diagnostic_pass").Split(' ')) values[key] = null;
        foreach (string key in ("navigation_start_count navigation_complete_count dom_count webmessage_count document_ready_count click_diag_count diagnostic_parse_errors uia_polls").Split(' ')) values[key] = 0;
        foreach (string key in ("nav_start_id nav_complete_id dom_nav_id nav_error uia_control_type sendinput_requested sendinput_return struct_size cursor_last_error sendinput_last_error rect_x rect_y rect_width rect_height target_x target_y initialized_ms navigate_ms navigation_start_ms navigation_complete_ms dom_ms document_ready_ms uia_start_ms uia_end_ms input_ms cursor_ms sendinput_ms message_ms click_ms verdict_ms").Split(' ')) values[key] = null;
        values["skip_reason"] = "not_reached"; values["ready_state"] = null;
        values["exception_type"] = null; values["snapshot_reason"] = null;
    }
    public void Put(string key, object value) { lock (gate) { if (!frozen) values[key] = value; } }
    public void Count(string key) { lock (gate) { if (!frozen) values[key] = (int)values[key] + 1; } }
    public void Mark(string phase, string key) {
        lock (gate) {
            if (frozen) return;
            long ms = watch.ElapsedMilliseconds; values[key] = ms;
            if (events.Count < 16) events.Add(new Dictionary<string, object> { { "phase", phase }, { "ms", ms } });
        }
    }
    public bool IsTrue(string key) { lock (gate) { return values[key] is bool && (bool)values[key]; } }
    public bool Equal(string a, string b) { lock (gate) { return values[a] != null && values[a].Equals(values[b]); } }
    public bool IsCount(string key, int n) { lock (gate) { return values[key] != null && Convert.ToInt64(values[key]) == n; } }
    public void FreezeAndWrite(string path, string reason) {
        lock (gate) {
            if (frozen) return;
            values["snapshot_reason"] = reason; values["events"] = events; frozen = true;
            File.WriteAllText(path, new JavaScriptSerializer().Serialize(values));
        }
    }
}

// Public helpers are shared by the optional synthetic WebView2 plugin.
public static class ProbeInput
{
    [StructLayout(LayoutKind.Sequential)] struct INPUT { public uint type; public MOUSEINPUT mouse; }
    [StructLayout(LayoutKind.Sequential)] struct MOUSEINPUT {
        public int dx, dy; public uint mouseData, dwFlags, time; public UIntPtr extra;
    }
    [DllImport("user32.dll", SetLastError=true)] static extern uint SendInput(uint count, INPUT[] input, int size);
    [DllImport("user32.dll", SetLastError=true)] static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr window);
    [DllImport("user32.dll")] static extern IntPtr OpenInputDesktop(uint flags, bool inherit, uint access);
    [DllImport("user32.dll")] static extern bool CloseDesktop(IntPtr desktop);
    public static bool InputDesktop() {
        IntPtr p = OpenInputDesktop(0, false, 1); if (p == IntPtr.Zero) return false;
        CloseDesktop(p); return true;
    }
    public static AutomationElement Find(AutomationElement root, string name) {
        return root.FindFirst(TreeScope.Descendants,
            new PropertyCondition(AutomationElement.NameProperty, name));
    }
    public static async Task<AutomationElement> WaitFor(AutomationElement root, string name, WebDiagnostics d = null) {
        if (d != null) { d.Put("uia_started", true); d.Put("uia_found", false); d.Put("uia_usable", false); d.Mark("uia_start", "uia_start_ms"); }
        for (int i = 0; i < 30; i++) {
            AutomationElement e = Find(root, name);
            if (d != null) {
                d.Count("uia_polls");
                if (e != null) {
                    d.Put("uia_found", true); d.Put("uia_name_match", e.Current.Name == name);
                    d.Put("uia_control_type", e.Current.ControlType.Id);
                    d.Put("uia_offscreen", e.Current.IsOffscreen); RectangleEvidence(e, d);
                }
            }
            if (e != null && !e.Current.IsOffscreen && !e.Current.BoundingRectangle.IsEmpty) {
                if (d != null) { d.Put("uia_usable", true); d.Mark("uia_end", "uia_end_ms"); }
                return e;
            }
            await Task.Delay(200);
        }
        if (d != null) { d.Put("skip_reason", "uia_timeout"); d.Mark("uia_end", "uia_end_ms"); }
        return null;
    }
    static void RectangleEvidence(AutomationElement e, WebDiagnostics d) {
        var r = e.Current.BoundingRectangle;
        bool valid = !r.IsEmpty && r.Width > 0 && r.Height > 0;
        double[] numbers = { r.Left, r.Top, r.Width, r.Height };
        foreach (double n in numbers) if (double.IsNaN(n) || double.IsInfinity(n) || Math.Abs(n) > 65536) valid = false;
        d.Put("uia_rect_valid", valid);
        if (valid) { d.Put("rect_x", r.Left); d.Put("rect_y", r.Top); d.Put("rect_width", r.Width); d.Put("rect_height", r.Height); }
    }
    // Real OS mouse input only. No InvokePattern, window messages, JS clicks or product IPC.
    public static bool Click(AutomationElement e, bool right, WebDiagnostics d = null) {
        if (d != null) { d.Put("cursor_attempted", false); d.Put("sendinput_attempted", false); d.Mark("input", "input_ms"); }
        if (e == null || e.Current.IsOffscreen) {
            if (d != null) d.Put("skip_reason", e == null ? (d.IsTrue("uia_started") ? "uia_timeout" : "null_element") : "offscreen");
            return false;
        }
        var r = e.Current.BoundingRectangle;
        if (d != null) RectangleEvidence(e, d);
        if (r.IsEmpty || r.Width <= 0 || r.Height <= 0) { if (d != null) d.Put("skip_reason", "invalid_rectangle"); return false; }
        int x = (int)(r.Left + r.Width / 2), y = (int)(r.Top + r.Height / 2);
        if (d != null) { d.Put("cursor_attempted", true); if (Math.Abs((long)x) <= 65536 && Math.Abs((long)y) <= 65536) { d.Put("target_x", x); d.Put("target_y", y); } }
        bool cursor = SetCursorPos(x, y);
        int cursorError = cursor ? 0 : Marshal.GetLastWin32Error();
        if (d != null) { d.Put("cursor_success", cursor); d.Mark("cursor", "cursor_ms"); if (!cursor) d.Put("cursor_last_error", cursorError); }
        if (!cursor) { if (d != null) d.Put("skip_reason", "cursor_failed"); return false; }
        INPUT[] a = new INPUT[2];
        a[0].mouse.dwFlags = right ? 0x0008u : 0x0002u;
        a[1].mouse.dwFlags = right ? 0x0010u : 0x0004u;
        int size = Marshal.SizeOf(typeof(INPUT));
        if (d != null) { d.Put("sendinput_attempted", true); d.Put("sendinput_requested", 2); d.Put("struct_size", size); }
        uint sent = SendInput(2, a, size);
        int inputError = sent == 2 ? 0 : Marshal.GetLastWin32Error();
        if (d != null) { d.Put("sendinput_return", sent); d.Mark("sendinput", "sendinput_ms"); d.Put("skip_reason", sent == 2 ? "none" : "sendinput_incomplete"); if (sent != 2) d.Put("sendinput_last_error", inputError); }
        return sent == 2;
    }
}

public class ProbeHost : Form
{
    readonly Dictionary<string, object> result = new Dictionary<string, object>();
    readonly string output, work;
    NotifyIcon tray;
    bool guiClick, trayClick;
    string trayName = "QA59 synthetic tray";
    public ProbeHost(string directory) {
        work = directory; output = Path.Combine(work, "host-result.json");
        Text = "QA59 synthetic capability"; Size = new Size(640, 480);
        StartPosition = FormStartPosition.CenterScreen;
        result["GUI SESSION ACCESS"] = "FAIL";
        result["SYNTHETIC WEBVIEW2 INTERACTION"] = "NOT VERIFIED";
        result["SYNTHETIC TRAY INTERACTION"] = "NOT VERIFIED";
        result["normal_exit"] = false;
        Shown += async delegate { await Run(); };
        FormClosed += delegate {
            if (tray != null) { tray.Visible = false; tray.Dispose(); }
            File.WriteAllText(output, new JavaScriptSerializer().Serialize(result));
        };
    }
    async Task Run() {
        try {
            int session = Process.GetCurrentProcess().SessionId;
            bool explorer = false;
            foreach (Process p in Process.GetProcessesByName("explorer")) {
                using (p) { if (p.SessionId == session) explorer = true; }
            }
            result["interactive_session"] = Environment.UserInteractive && session != 0;
            result["input_desktop"] = ProbeInput.InputDesktop();
            result["explorer_same_session"] = explorer;
            Button b = new Button { Text = "QA59 GUI input", AccessibleName = "QA59 GUI input", Dock = DockStyle.Top };
            b.Click += delegate { guiClick = true; }; Controls.Add(b);
            Activate(); ProbeInput.SetForegroundWindow(Handle);
            bool focus = ProbeInput.GetForegroundWindow() == Handle;
            result["foreground_control"] = focus;
            bool injected = await Task.Run(async delegate {
                var e = await ProbeInput.WaitFor(AutomationElement.FromHandle(Handle), "QA59 GUI input");
                return ProbeInput.Click(e, false);
            });
            await Task.Delay(500);
            bool gui = (bool)result["interactive_session"] && (bool)result["input_desktop"] && explorer && focus && injected && guiClick;
            result["gui_button_received"] = guiClick;
            result["GUI SESSION ACCESS"] = gui ? "PASS" : "FAIL";
            Controls.Remove(b); b.Dispose();
            if (!gui) {
                result["blocked_reason"] = "No proven interactive desktop/focus/input path; GUI and tray blocked";
            } else {
                string plugin = Path.Combine(work, "WebProbe.dll");
                if (File.Exists(plugin)) {
                    try {
                        var type = Assembly.LoadFrom(plugin).GetType("WebProbe", true);
                        var task = (Task<string>)type.GetMethod("Run").Invoke(null, new object[] { this, work });
                        string verdict = await task;
                        result["SYNTHETIC WEBVIEW2 INTERACTION"] = verdict == "PASS" ? "PASS" : "FAIL";
                        result["webview_evidence"] = verdict;
                    } catch (Exception e) {
                        result["SYNTHETIC WEBVIEW2 INTERACTION"] = "FAIL";
                        result["webview_error_type"] = e.GetType().Name;
                    }
                } else { result["webview_evidence"] = "SDK preparation unverified; no runtime installation attempted"; }
                try { await TrayProbe(); }
                catch (Exception e) {
                    result["SYNTHETIC TRAY INTERACTION"] = "FAIL";
                    result["tray_error_type"] = e.GetType().Name;
                }
            }
            result["normal_exit"] = true;
        } catch (Exception e) { result["host_error_type"] = e.GetType().Name; }
        Close();
    }
    async Task TrayProbe() {
        result["SYNTHETIC TRAY INTERACTION"] = "FAIL";
        var menu = new ContextMenuStrip();
        menu.Items.Add("QA59 finish probe", null, delegate { trayClick = true; });
        tray = new NotifyIcon { Icon = SystemIcons.Application, Text = trayName, ContextMenuStrip = menu, Visible = true };
        bool clicked = await Task.Run(async delegate {
            var shell = AutomationElement.RootElement.FindFirst(TreeScope.Children,
                new PropertyCondition(AutomationElement.ClassNameProperty, "Shell_TrayWnd"));
            if (shell == null) return false;
            var icon = await ProbeInput.WaitFor(shell, trayName);
            if (icon == null) {
                // Expand the real notification overflow via its UI button, if needed.
                var chevron = shell.FindFirst(TreeScope.Descendants,
                    new PropertyCondition(AutomationElement.AutomationIdProperty, "1502"));
                if (!ProbeInput.Click(chevron, false)) return false;
                icon = await ProbeInput.WaitFor(AutomationElement.RootElement, trayName);
            }
            result["tray_icon_visible"] = icon != null;
            if (!ProbeInput.Click(icon, true)) return false;
            var item = await ProbeInput.WaitFor(AutomationElement.RootElement, "QA59 finish probe");
            result["tray_menu_visible"] = item != null;
            return ProbeInput.Click(item, false);
        });
        await Task.Delay(500);
        result["tray_item_received"] = trayClick;
        result["SYNTHETIC TRAY INTERACTION"] = clicked && trayClick ? "PASS" : "FAIL";
        if (!trayClick) result["tray_path"] = "BLOCKED; no API fallback";
        tray.Visible = false; tray.Dispose(); tray = null; menu.Dispose();
    }
    [STAThread] public static void Main(string[] args) {
        Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
        Application.Run(new ProbeHost(args[0]));
    }
}
