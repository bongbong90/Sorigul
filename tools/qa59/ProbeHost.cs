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

// Public helpers are shared by the optional synthetic WebView2 plugin.
public static class ProbeInput
{
    [StructLayout(LayoutKind.Sequential)] struct INPUT { public uint type; public MOUSEINPUT mouse; }
    [StructLayout(LayoutKind.Sequential)] struct MOUSEINPUT {
        public int dx, dy; public uint mouseData, dwFlags, time; public UIntPtr extra;
    }
    [DllImport("user32.dll")] static extern uint SendInput(uint count, INPUT[] input, int size);
    [DllImport("user32.dll")] static extern bool SetCursorPos(int x, int y);
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
    public static async Task<AutomationElement> WaitFor(AutomationElement root, string name) {
        for (int i = 0; i < 30; i++) {
            AutomationElement e = Find(root, name);
            if (e != null && !e.Current.IsOffscreen && !e.Current.BoundingRectangle.IsEmpty) return e;
            await Task.Delay(200);
        }
        return null;
    }
    // Real OS mouse input only. No InvokePattern, window messages, JS clicks or product IPC.
    public static bool Click(AutomationElement e, bool right) {
        if (e == null || e.Current.IsOffscreen) return false;
        var r = e.Current.BoundingRectangle;
        if (r.IsEmpty || r.Width <= 0 || r.Height <= 0) return false;
        if (!SetCursorPos((int)(r.Left + r.Width / 2), (int)(r.Top + r.Height / 2))) return false;
        INPUT[] a = new INPUT[2];
        a[0].mouse.dwFlags = right ? 0x0008u : 0x0002u;
        a[1].mouse.dwFlags = right ? 0x0010u : 0x0004u;
        return SendInput(2, a, Marshal.SizeOf(typeof(INPUT))) == 2;
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
