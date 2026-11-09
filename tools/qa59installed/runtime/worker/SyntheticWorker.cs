// Compiled locally, NEVER executed by Invoke-RuntimeTests. No product/API/UIA,
// settings, media or endpoint access. Execution requires a provisioned QA account.
using System;
using System.Diagnostics;
using System.Threading;
using System.IO;
using System.Net;
using System.Net.Sockets;

internal static class SyntheticWorker
{
    public static int Main(string[] args)
    {
        if (args.Length != 1) return 64;
        if (args[0] == "--exit") { File.WriteAllText("worker-ready", "1"); Hold(); return 0; }
        if (args[0] == "--exit-fast") return 0;
        if (args[0] == "--crash") { File.WriteAllText("worker-ready", "1"); Hold(); return 23; }
        if (args[0] == "--child" || args[0] == "--short-child")
        {
            using (Process current = Process.GetCurrentProcess())
            using (var child = Process.Start(new ProcessStartInfo(current.MainModule.FileName, args[0] == "--child" ? "--endpoints" : "--exit-fast")
                { UseShellExecute = false, CreateNoWindow = true }))
            {
                if (child == null) return 24;
                if (args[0] == "--short-child")
                {
                    if (!child.WaitForExit(5000)) return 26;
                    File.WriteAllText("worker-ready", "1");
                }
                Hold();
                if (!child.WaitForExit(5000) || child.ExitCode != 0) return 27;
            }
            return 0; // child remains in the inherited owned Job until cleanup
        }
        if (args[0] == "--endpoints")
        {
            var tcp = new TcpListener(IPAddress.Loopback, 0);
            using (var udp = new UdpClient(new IPEndPoint(IPAddress.Loopback, 0)))
            {
                tcp.Start();
                try { File.WriteAllText("worker-ready", "1"); Hold(); }
                finally { tcp.Stop(); }
            }
            return 0;
        }
        if (args[0] != "--hang") return 64;
        File.WriteAllText("worker-ready", "1");
        Thread.Sleep(Timeout.Infinite); // models a UIA/native provider hang
        return 25;
    }
    private static void Hold()
    {
        var clock = Stopwatch.StartNew();
        while (!File.Exists("worker-stop") && clock.ElapsedMilliseconds < 20000) Thread.Sleep(10);
    }
}
