// Compiled only into the user-authorized, local-only QA EXE. Never a DLL gate.
#if QA59_WIN11_LOCAL_TESTS
using System;
using System.IO;
using System.Reflection;
using System.Diagnostics;
using System.Management;
using System.Security.AccessControl;
using System.Security.Principal;
using Microsoft.Win32;
using Qa59Installed;
using Qa59Installed.Runtime;

internal sealed class Windows11Session : IDisposable
{
    internal const string ScratchParent=@"C:\Users\Public";
    private FileStream approval;
    private Windows11Session() { }
    internal static Windows11Session Enter()
    {
        if(!LocalWin11Policy.Verified()) throw new BoundaryException();
        foreach(string name in new[]{"sorigul-desktop","sorigul-backend"})
        {
            var processes=Process.GetProcessesByName(name);
            bool any=processes.Length!=0; foreach(var process in processes) process.Dispose();
            if(any) throw new BoundaryException();
        }
        using(var search=new ManagementObjectSearcher("SELECT CommandLine FROM Win32_Process WHERE Name='msedgewebview2.exe'"))
        using(var found=search.Get())
            foreach(ManagementObject process in found)
            {
                string command=process["CommandLine"] as string;
                if(command==null || command.IndexOf("com.sorigul.desktop",StringComparison.OrdinalIgnoreCase)>=0) throw new BoundaryException();
            }
        foreach(string hive in new[]{"SOFTWARE\\Policies\\Microsoft\\Edge\\WebView2","SOFTWARE\\WOW6432Node\\Policies\\Microsoft\\Edge\\WebView2","SOFTWARE\\Policies\\Microsoft\\EmbeddedBrowserWebView\\LoaderOverride"})
        {
            using(var key=Registry.LocalMachine.OpenSubKey(hive)) if(key!=null) throw new BoundaryException();
            using(var key=Registry.CurrentUser.OpenSubKey(hive)) if(key!=null) throw new BoundaryException();
        }
        if(ProductOwnedJob.Digest(Path.Combine(LocalWin11Policy.Session,"baseline.json"))!=LocalWin11Policy.BaselineHash
            || ProductOwnedJob.Digest(Path.Combine(LocalWin11Policy.Session,"preservation-latest.json"))!=LocalWin11Policy.VerificationHash
            || ProductOwnedJob.Digest(Path.Combine(LocalWin11Policy.Session,"restore.msi"))!="d14deab6031728af9e10652582c6fdc9b3018b350e7818320b1feaaccdcb2f80") throw new BoundaryException();
        var result=new Windows11Session();
        try
        {
            // One exact handle checks and consumes; a second concurrent opener fails.
            var handle=WinFiles.CreateFile(LocalWin11Policy.Approval,0xC0000000,0,IntPtr.Zero,3,0x00200000,IntPtr.Zero);
            try { WinFiles.Check(handle,LocalWin11Policy.Approval,false); result.approval=new FileStream(handle,FileAccess.ReadWrite); }
            catch { handle.Dispose(); throw; }
            byte[] ready=System.Text.Encoding.ASCII.GetBytes("QA59_WIN11_APPROVED_SINGLE_SESSION");
            if(result.approval.Length!=ready.Length) throw new BoundaryException();
            for(int i=0;i<ready.Length;i++) if(result.approval.ReadByte()!=ready[i]) throw new BoundaryException();
            result.approval.Position=0; result.approval.Write(new byte[ready.Length],0,ready.Length); result.approval.Flush(true);
            return result;
        }
        catch { result.Dispose(); throw; }
    }
    public void Dispose() { if(approval!=null) approval.Dispose(); }
    internal static void ProtectScratch(string path)
    {
        var security=new DirectorySecurity(); security.SetAccessRuleProtection(true,false);
        using(var identity=WindowsIdentity.GetCurrent())
            foreach(var sid in new[]{identity.User,new SecurityIdentifier("S-1-5-18"),new SecurityIdentifier("S-1-5-32-544")})
                security.AddAccessRule(new FileSystemAccessRule(sid,FileSystemRights.FullControl,InheritanceFlags.ContainerInherit|InheritanceFlags.ObjectInherit,PropagationFlags.None,AccessControlType.Allow));
        Directory.SetAccessControl(path,security);
        if(!Directory.GetAccessControl(path).AreAccessRulesProtected) throw new BoundaryException();
    }
}

internal static partial class InstalledServerHarness
{
    private static int Windows11Main(string[] args)
    {
        if(args.Length==1 && args[0]=="--probe-ui-owner")
        {
            if(!LocalWin11Policy.Verified()) return 64;
            var info=new ProcessStartInfo(Path.Combine(Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location),"InstalledUiWorker.exe"),"watch-parent 0 IA== unknown 0 none")
                {UseShellExecute=false,CreateNoWindow=true,RedirectStandardOutput=true};
            using(var worker=Process.Start(info))
            {
                var ready=worker.StandardOutput.ReadLineAsync();
                if(!ready.Wait(5000) || ready.Result!="UI_PARENT_WATCH_READY") { if(!worker.HasExited)worker.Kill();return 1; }
                Environment.Exit(37);
            }
        }
        if(args.Length!=0) return 64;
        using(var session=Windows11Session.Enter())
        {
            var outcome=new Outcome();
            var candidate=CandidateManifest.Validate(File.ReadAllText(Path.Combine(LocalWin11Policy.Session,"candidate-manifest.json")),outcome);
            string msi=Path.Combine(LocalWin11Policy.Session,"candidate.msi"), installed=@"C:\Program Files\Sorigul";
            Check("ORIGINAL_PINNED_MSI_CONTRACT",candidate!=null&&outcome.Ok&&ProductOwnedJob.Digest(msi)==CandidatePins.MsiSha256&&new FileInfo(msi).Length==CandidatePins.MsiSizeBytes);
            string exe=Path.Combine(installed,"sorigul-desktop.exe"), core=Path.Combine(installed,@"binaries\sorigul-backend.exe");
            using(var registration=Registry.LocalMachine.OpenSubKey(@"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{6761C62F-6F13-4906-9BF7-77EDC0EB9BBB}"))
                Check("CANDIDATE_REGISTERED",registration!=null&&string.Equals((string)registration.GetValue("InstallLocation"),installed+"\\",StringComparison.OrdinalIgnoreCase));
            Check("INSTALLED_PAYLOAD_HASHES",ProductOwnedJob.Digest(exe)==candidate.DesktopSha256&&ProductOwnedJob.Digest(core)==candidate.CoreSha256
                &&ProductOwnedJob.Digest(Path.Combine(installed,@"binaries\ffmpeg.exe"))==candidate.FfmpegSha256&&ProductOwnedJob.Digest(Path.Combine(installed,"sorigul-build-manifest.json"))==candidate.EmbeddedManifestSha256);
            Check("PRODUCTION_CONTEXT_STILL_DENY",!ContextGate.Evaluate("{}").ExecutionAllowed);
            desktopHash=candidate.DesktopSha256;
            uiExe=Path.Combine(Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location),"InstalledUiWorker.exe");
            using(var parent=WinFiles.CreateFile(Windows11Session.ScratchParent,0x81,1,IntPtr.Zero,3,0x02200000,IntPtr.Zero))
            {
                WinFiles.Check(parent,Windows11Session.ScratchParent,true);
                string scratch=Path.Combine(Windows11Session.ScratchParent,"qa59-scratch-"+Guid.NewGuid().ToString("N"));
                using(var scratchPin=WinFiles.CreateOwnedDirectory(parent,Path.GetFileName(scratch)))
                {
                    Windows11Session.ProtectScratch(scratch);
                    using(var boundary=new DisposableRoot(scratch,LocalWin11Policy.ProtectedRoots,scratchPin))
                    {
                        string profile=Path.Combine(boundary.Root,"profile"); Directory.CreateDirectory(profile);
                        Test(exe,core,boundary.Root,profile,candidate);
                    }
                }
            }
            Console.WriteLine("WINDOWS11_INSTALLED_SCENARIOS PASS checks="+checks+" restoration=PENDING");
            return 0;
        }
    }
}
#endif
