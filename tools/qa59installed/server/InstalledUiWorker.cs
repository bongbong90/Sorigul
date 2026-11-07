// UIAutomation observes; only real SendInput clicks mutate product UI.
// Adapted from #219 ProbeHost.ProbeInput, with foreground/hit target split.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.RegularExpressions;
using System.Security.Cryptography;
using System.IO;
using System.Threading;
using System.Windows;
using System.Windows.Automation;

internal static class InstalledUiWorker
{
    [StructLayout(LayoutKind.Sequential)] private struct Input { internal uint Type; internal Mouse Mouse; }
    [StructLayout(LayoutKind.Sequential)] private struct Mouse { internal int X, Y; internal uint Data, Flags, Time; internal UIntPtr Extra; }
    [DllImport("user32.dll")] private static extern bool SetForegroundWindow(IntPtr handle);
    [DllImport("user32.dll")] private static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr handle,out uint pid);
    [DllImport("user32.dll")] private static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll", SetLastError = true)] private static extern uint SendInput(uint count, Input[] input, int size);
    private static bool foreground, hit;
    private static int clicks, inserted;
    private static AutomationElement Named(AutomationElement root, string name)
    { return root.FindFirst(TreeScope.Descendants, new PropertyCondition(AutomationElement.NameProperty, name)); }
    private static bool Click(AutomationElement element, IntPtr expectedWindow, bool right)
    {
        if (element == null || element.Current.IsOffscreen || !element.Current.IsEnabled) return false;
        if (expectedWindow != IntPtr.Zero) { SetForegroundWindow(expectedWindow); Thread.Sleep(120); }
        foreground = expectedWindow != IntPtr.Zero && GetForegroundWindow() == expectedWindow;
        if (expectedWindow != IntPtr.Zero && !foreground) return false;
        Rect rectangle = element.Current.BoundingRectangle;
        if (rectangle.IsEmpty || rectangle.Width <= 0 || rectangle.Height <= 0) return false;
        int x = (int)(rectangle.Left + rectangle.Width / 2), y = (int)(rectangle.Top + rectangle.Height / 2);
        if (Math.Abs(x) > 65536 || Math.Abs(y) > 65536 || !SetCursorPos(x, y)) return false;
        var under = AutomationElement.FromPoint(new Point(x, y));
        hit = false;
        for (int i = 0; under != null && i < 12; i++, under = TreeWalker.ControlViewWalker.GetParent(under))
            if (Automation.Compare(under, element)) { hit = true; break; }
        if (!hit) return false;
        var input = new Input[2]; input[0].Mouse.Flags = right ? 8U : 2U; input[1].Mouse.Flags = right ? 16U : 4U;
        uint sent = SendInput(2, input, Marshal.SizeOf(typeof(Input)));
        inserted += (int)sent; clicks++;
        return sent == 2;
    }
    private static void Report(bool ok, bool online, bool offline, bool visible, bool enabled, bool folder, int files, int done, int failed, bool guard)
    {
        Console.WriteLine("{\"schema\":1,\"ok\":" + Bool(ok) + ",\"online\":" + Bool(online) + ",\"offline\":" + Bool(offline)
            + ",\"restart_visible\":" + Bool(visible) + ",\"restart_enabled\":" + Bool(enabled) + ",\"folder\":" + Bool(folder)
            + ",\"files\":" + files + ",\"done\":" + done + ",\"failed\":" + failed + ",\"guard\":" + Bool(guard)
            + ",\"foreground\":" + Bool(foreground) + ",\"hit_target\":" + Bool(hit) + ",\"clicks\":" + clicks + ",\"requested\":" + (clicks * 2) + ",\"inserted\":" + inserted + "}");
    }
    private static string Bool(bool value) { return value ? "true" : "false"; }
    [STAThread]
    public static int Main(string[] args)
    {
        try
        {
            if (Environment.GetEnvironmentVariable("GITHUB_ACTIONS") != "true" || Environment.GetEnvironmentVariable("ImageOS") != "win22" || args.Length != 6) return 64;
            string mode = args[0]; int pid = int.Parse(args[1]);
            string folder = Encoding.UTF8.GetString(Convert.FromBase64String(args[2]));
            if(folder==" ") folder=""; // explicit unmeasured folder sentinel
            string guardText = args[3] == "active" ? "완료되지 않았거나" : args[3] == "drive" ? "Drive 작업" : args[3] == "port" ? "포트를 다른" : "저장된 작업 상태";
            using (var app = Process.GetProcessById(pid))
            {
                if(app.StartTime.ToUniversalTime().ToFileTimeUtc()!=long.Parse(args[4])) return 65;
                using(var image=File.OpenRead(app.MainModule.FileName))
                using(var sha=SHA256.Create())
                    if(BitConverter.ToString(sha.ComputeHash(image)).Replace("-","").ToLowerInvariant()!=args[5]) return 65;
                app.Refresh(); IntPtr window = app.MainWindowHandle;
                if (mode == "tray-quit" || mode == "tray-open")
                {
                    var desktop = AutomationElement.RootElement;
                    var shell = desktop.FindFirst(TreeScope.Children,new PropertyCondition(AutomationElement.ClassNameProperty,"Shell_TrayWnd"));
                    if(shell==null) { Report(false,false,false,false,false,false,0,0,0,false); return 1; }
                    int shellPid=shell.Current.ProcessId;
                    var icons=shell.FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.NameProperty,"Sorigul - 대기 중"));
                    AutomationElement icon=icons.Count==1?icons[0]:null;
                    if (icon == null || icon.Current.IsOffscreen)
                    {
                        var chevron = shell.FindFirst(TreeScope.Descendants, new PropertyCondition(AutomationElement.AutomationIdProperty, "1502"));
                        if (!Click(chevron, IntPtr.Zero, false)) { Report(false,false,false,false,false,false,0,0,0,false); return 1; }
                        Thread.Sleep(300);
                        var overflow=desktop.FindFirst(TreeScope.Children,new PropertyCondition(AutomationElement.ClassNameProperty,"NotifyIconOverflowWindow"));
                        if(overflow==null||overflow.Current.ProcessId!=shellPid) { Report(false,false,false,false,false,false,0,0,0,false); return 1; }
                        icons=overflow.FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.NameProperty,"Sorigul - 대기 중"));
                        icon=icons.Count==1?icons[0]:null;
                    }
                    bool ok = icon!=null&&icon.Current.ProcessId==shellPid&&Click(icon, IntPtr.Zero, true);
                    Thread.Sleep(300);
                    var menu=desktop.FindAll(TreeScope.Descendants,new AndCondition(
                        new PropertyCondition(AutomationElement.NameProperty,mode=="tray-quit"?"종료":"앱 열기"),
                        new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.MenuItem),
                        new PropertyCondition(AutomationElement.ProcessIdProperty,pid)));
                    IntPtr foregroundWindow=GetForegroundWindow(); uint foregroundPid;
                    GetWindowThreadProcessId(foregroundWindow,out foregroundPid);
                    ok = ok && menu.Count==1 && foregroundPid==(uint)pid && Click(menu[0],foregroundWindow,false);
                    Report(ok,false,false,false,false,false,0,0,0,false); return ok ? 0 : 1;
                }
                if (window == IntPtr.Zero) { Report(true,false,false,false,false,false,0,0,0,false); return 0; }
                var root = AutomationElement.FromHandle(window);
                var elements = root.FindAll(TreeScope.Descendants, Condition.TrueCondition);
                bool online = false, offline = false, foundFolder = false, guard = false;
                int files = 0, done = 0, failed = 0;
                var names = new HashSet<string>(StringComparer.Ordinal);
                foreach (AutomationElement element in elements)
                {
                    string name = element.Current.Name ?? "";
                    if (name == "Backend 연결됨") online = true;
                    if (name == "Backend 오프라인") offline = true;
                    if (folder.Length > 0 && name.IndexOf(folder, StringComparison.OrdinalIgnoreCase) >= 0) foundFolder = true;
                    if (name.IndexOf(guardText, StringComparison.Ordinal) >= 0) guard = true;
                    if (!names.Add(name)) continue;
                    if (Regex.IsMatch(name,@"^qa59-synthetic-[ab]-\d+\.mp3 선택$")) files++;
                    if (Regex.IsMatch(name,@"^qa59-synthetic-[ab]-\d+\.mp3 다시 전사$")) done++;
                    if (Regex.IsMatch(name,@"^qa59-synthetic-[ab]-\d+\.mp3 다시 시도$")) failed++;
                }
                var buttons = root.FindAll(TreeScope.Descendants, new AndCondition(new PropertyCondition(AutomationElement.NameProperty,"Backend 다시 시작"),new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Button)));
                bool visible = buttons.Count == 1 && !buttons[0].Current.IsOffscreen;
                bool enabled = visible && buttons[0].Current.IsEnabled;
                bool success = true;
                if (mode == "click-restart" || mode == "double-restart")
                {
                    success = enabled && Click(buttons[0],window,false);
                    if (mode == "double-restart" && success) success = Click(buttons[0],window,false);
                }
                else if (mode != "snapshot") return 64;
                Report(success,online,offline,visible,enabled,foundFolder,files,done,failed,guard);
                return success ? 0 : 1;
            }
        }
        catch { Report(false,false,false,false,false,false,0,0,0,false); return 1; }
    }
}
