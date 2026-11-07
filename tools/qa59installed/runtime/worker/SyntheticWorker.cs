// Compiled locally, NEVER executed by Invoke-RuntimeTests. No product/API/UIA,
// settings, media or endpoint access. Execution requires a provisioned QA account.
using System;
using System.Diagnostics;
using System.Threading;

internal static class SyntheticWorker
{
    public static int Main(string[] args)
    {
        if (args.Length != 1) return 64;
        if (args[0] == "--exit") return 0;
        if (args[0] == "--crash") return 23;
        if (args[0] == "--child")
        {
            using (Process current = Process.GetCurrentProcess())
            using (var child = Process.Start(new ProcessStartInfo(current.MainModule.FileName, "--hang")
                { UseShellExecute = false, CreateNoWindow = true }))
            { if (child == null) return 24; }
            return 0; // child remains in the inherited owned Job until cleanup
        }
        if (args[0] != "--hang") return 64;
        Thread.Sleep(Timeout.Infinite); // models a UIA/native provider hang
        return 25;
    }
}
