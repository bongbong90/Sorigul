// Fresh, separately identified hosted MSI only. This is never built into Sorigul.
using System;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Reflection;
using System.Text;
using System.Threading;
using Qa59Installed;
using Qa59Installed.Runtime;
using Microsoft.Win32.SafeHandles;
#if QA59_WIN11_LOCAL_TESTS
using InstalledCandidate = Qa59Installed.CandidateManifest;
#else
using InstalledCandidate = Qa59Installed.RunnerCandidate;
#endif

internal static partial class InstalledServerHarness
{
    private static int checks;
    private static string uiExe, desktopHash;
    private static void Check(string id,bool ok)
    {
        checks++; Console.WriteLine("SERVER_CHECK " + id + " " + (ok?"PASS":"FAIL"));
        if(!ok) throw new InvalidOperationException("SERVER_CHECK_FAILED");
    }
    private static bool Flag(JsonObject obj,string key) { return obj!=null && true.Equals(obj.Get(key)); }
    private static long Count(JsonObject obj,string key) { return obj!=null && obj.Get(key) is long ? (long)obj.Get(key) : -1; }
    private static JsonObject Ui(string mode,ProductOwnedJob owner,string folder,string guard)
    {
        string encoded=Convert.ToBase64String(Encoding.UTF8.GetBytes(folder??""));
        // '-' is a non-empty base64 representation of an unused synthetic field.
        if(encoded.Length==0) encoded=Convert.ToBase64String(new byte[]{32});
        var start=new ProcessStartInfo(uiExe,mode+" "+owner.RootPid+" "+encoded+" "+guard+" "+owner.RootCreated+" "+desktopHash)
            {UseShellExecute=false,CreateNoWindow=true,RedirectStandardOutput=true,RedirectStandardError=true};
        using(var process=Process.Start(start))
        {
            var read=process.StandardOutput.ReadToEndAsync();
            if(!process.WaitForExit(15000)) { process.Kill(); process.WaitForExit(5000); throw new InvalidOperationException("UI_WORKER_DEADLINE"); }
            if(!read.Wait(1000) || read.Result.Length>4096) throw new InvalidOperationException("UI_RESULT_INVALID");
            var obj=StrictJson.Parse(read.Result.Trim()) as JsonObject;
            if(obj==null || !1L.Equals(obj.Get("schema"))) throw new InvalidOperationException("UI_RESULT_INVALID");
            if(process.ExitCode!=0 || !Flag(obj,"ok"))
            {
                string reason=obj.Get("input_failure") as string;
                if(Array.IndexOf(new[]{"NONE","ELEMENT_UNAVAILABLE","FOREGROUND_DENIED","RECT_INVALID","CURSOR_FAILED","HIT_MISMATCH","SENDINPUT_INCOMPLETE","PROVIDER_FAILED"},reason)<0) reason="UNCLASSIFIED";
                Console.WriteLine("SERVER_INPUT_DIAG mode="+mode+" reason="+reason+" foreground="+Flag(obj,"foreground")+" hit="+Flag(obj,"hit_target")+" clicks="+Count(obj,"clicks")+" requested="+Count(obj,"requested")+" inserted="+Count(obj,"inserted")+" exit="+process.ExitCode);
                throw new InvalidOperationException("UI_OBSERVATION_FAILED");
            }
            return obj;
        }
    }
    private static JsonObject WaitUi(ProductOwnedJob owner,string folder,Func<JsonObject,bool> predicate,int deadline=30000,string guard="unknown")
    {
        var clock=Stopwatch.StartNew(); JsonObject last=null;
        while(clock.ElapsedMilliseconds<deadline)
        {
            last=Ui("snapshot",owner,folder,guard);
            if(clock.ElapsedMilliseconds>=deadline) break;
            if(predicate(last)) return last;
            Thread.Sleep(400);
        }
        // Only booleans/counts, never captured UI text or paths.
        if(last!=null) Console.WriteLine("SERVER_UI_DIAG online="+Flag(last,"online")+" offline="+Flag(last,"offline")+" restart="+Flag(last,"restart_visible")+" enabled="+Flag(last,"restart_enabled")+" folder="+Flag(last,"folder")+" files="+Count(last,"files")+" done="+Count(last,"done")+" failed="+Count(last,"failed")+" guard="+Flag(last,"guard"));
        throw new InvalidOperationException("UI_EXPECTATION_DEADLINE");
    }
    private static bool Health()
    {
        try
        {
            var request=(HttpWebRequest)WebRequest.Create("http://127.0.0.1:8000/api/health"); request.Timeout=800; request.ReadWriteTimeout=800; request.Proxy=null;
            using(var response=(HttpWebResponse)request.GetResponse()) return response.StatusCode==HttpStatusCode.OK;
        }
        catch(WebException) { return false; }
    }
    private static void WaitHealth(ProductOwnedJob owner,bool online)
    {
        var clock=Stopwatch.StartNew();
        while(clock.ElapsedMilliseconds<75000)
        {
            bool health=Health();
            bool observed=online ? health && owner.BackendRoots()==1 && owner.BackendListenerOwned(8000) : !health && owner.BackendProcesses()==0;
            if(clock.ElapsedMilliseconds>=75000) break;
            if(observed) return;
            Thread.Sleep(300);
        }
        Console.WriteLine("SERVER_HEALTH_DIAG expected_online="+online+" health="+Health()+" backend_roots="+owner.BackendRoots()+" backend_processes="+owner.BackendProcesses()+" listener_owned="+owner.BackendListenerOwned(8000)+" owned_active="+owner.Active);
        throw new InvalidOperationException("BACKEND_OBSERVATION_DEADLINE");
    }
    private static void Write(string path,string text)
    { File.WriteAllText(path,text,new UTF8Encoding(false,true)); }
    private static void Fixtures(string root,string data,char revision,ProductOwnedJob owner=null,string negative=null)
    {
        if(owner!=null && (Health() || owner.BackendProcesses()!=0)) throw new InvalidOperationException("FIXTURE_BACKEND_NOT_OFFLINE");
        if(!SyntheticFixtures.ValidateRoot(root,new[]{@"C:\qa59-protected\Settings",@"C:\Program Files\Sorigul"}).Ok) throw new InvalidOperationException("FIXTURE_ROOT_INVALID");
        Directory.CreateDirectory(data);
        string settings=SyntheticFixtures.SettingsJson(root,revision);
        string jobs=SyntheticFixtures.JobsJson(root,revision);
        if(negative=="active") jobs=SyntheticFixtures.NegativeJobsJson(root,NegativeFixture.ACTIVE_JOB_WAITING);
        if(negative=="unknown") jobs=SyntheticFixtures.NegativeJobsJson(root,NegativeFixture.UNKNOWN_JOB_ENUM);
        if(negative=="drive") jobs=SyntheticFixtures.NegativeJobsJson(root,NegativeFixture.ACTIVE_DRIVE_UPLOADING);
        if(negative=="corrupt") jobs=SyntheticFixtures.NegativeJobsJson(root,NegativeFixture.CORRUPT_TRUNCATED);
        Write(Path.Combine(data,"settings.json"),settings);
        if(negative=="missing") File.Delete(Path.Combine(data,"jobs.json")); else Write(Path.Combine(data,"jobs.json"),jobs);
    }
    private static void MakeMedia(string root,char revision)
    {
        string folder=SyntheticFixtures.FolderFor(root,revision); Directory.CreateDirectory(folder);
        for(int i=1;i<=SyntheticFixtures.TotalFiles(revision);i++)
        {
            // Invalid, inert bytes; metadata parser returns unknown duration.
            // No transcription, external media, Local Runtime or GPU is used.
            string stem="qa59-synthetic-"+char.ToLowerInvariant(revision)+"-"+i;
            using(var file=new FileStream(Path.Combine(folder,stem+".mp3"),FileMode.CreateNew,FileAccess.Write)) file.Write(new byte[]{73,68,51},0,3);
        }
    }
    private static void Test(string exe,string core,string root,string profile,InstalledCandidate candidate)
    {
        string data=Path.Combine(profile,"Sorigul"); MakeMedia(root,'A'); MakeMedia(root,'B'); Fixtures(root,data,'A');
        using(var owner=new ProductOwnedJob(exe,core,profile,root,candidate))
        {
            WaitHealth(owner,true);
            WaitUi(owner,SyntheticFixtures.FolderFor(root,'A'),v=>Flag(v,"online")&&Flag(v,"folder")&&Count(v,"files")==2&&Count(v,"done")==1&&Count(v,"failed")==1,60000);
            Check("INSTALLED_MAIN_WEBVIEW_FIXTURE_A",true);
            owner.StopBackend(); WaitHealth(owner,false);
            WaitUi(owner,"",v=>Flag(v,"offline")&&Flag(v,"restart_visible")&&Flag(v,"restart_enabled"));
            Check("OWNED_BACKEND_OFFLINE_DETECTED",true);
            foreach(string negative in new[]{"active","unknown","drive","corrupt","missing"})
            {
                Fixtures(root,data,'A',owner,negative);
                string guard=negative=="corrupt"||negative=="missing"?"unknown":negative=="unknown"?"active":negative;
                string path=Path.Combine(data,"jobs.json"); string before=File.Exists(path)?ProductOwnedJob.Digest(path):"MISSING";
                WaitUi(owner,"",v=>Flag(v,"offline")&&Flag(v,"restart_visible")&&!Flag(v,"restart_enabled")&&Flag(v,"guard"),20000,guard);
                Thread.Sleep(500);
                Check("RESTART_GUARD_"+negative.ToUpperInvariant(),owner.BackendProcesses()==0&&!Health()&&(File.Exists(path)?ProductOwnedJob.Digest(path):"MISSING")==before);
            }
            Fixtures(root,data,'A',owner);
            var listener=new TcpListener(IPAddress.Loopback,8000); listener.Start();
            try
            {
                WaitUi(owner,"",v=>Flag(v,"restart_visible")&&!Flag(v,"restart_enabled")&&Flag(v,"guard"),20000,"port");
                Check("FOREIGN_LISTENER_RESTART_BLOCKED",owner.BackendProcesses()==0);
            }
            finally { listener.Stop(); }
            Fixtures(root,data,'B',owner);
            WaitUi(owner,"",v=>Flag(v,"offline")&&Flag(v,"restart_visible")&&Flag(v,"restart_enabled"));
            var click=Ui("click-restart",owner,"","unknown");
            Check("ONE_REAL_RESTART_CLICK",Flag(click,"foreground")&&Flag(click,"hit_target")&&Count(click,"clicks")==1&&Count(click,"requested")==2&&Count(click,"inserted")==2);
            WaitHealth(owner,true);
            WaitUi(owner,SyntheticFixtures.FolderFor(root,'B'),v=>Flag(v,"online")&&Flag(v,"folder")&&Count(v,"files")==3&&Count(v,"done")==1&&Count(v,"failed")==2,60000);
            Check("ONLINE_JOBS_SETTINGS_SYNC_B",owner.BackendRoots()==1);
            WaitUi(owner,"",v=>Flag(v,"online")&&!Flag(v,"restart_visible"));
            Check("LIVE_BACKEND_RESTART_HIDDEN",true);
            var tray=Ui("tray-quit",owner,"","unknown");
            Check("ONLINE_OWNED_TRAY_INPUT",Flag(tray,"foreground")&&Flag(tray,"hit_target")&&Count(tray,"clicks")>=2&&Count(tray,"inserted")==Count(tray,"requested"));
            Check("ONLINE_REAL_TRAY_NORMAL_EXIT",owner.WaitNormal(15000));
            var clock=Stopwatch.StartNew(); while(owner.Active!=0&&clock.ElapsedMilliseconds<10000) Thread.Sleep(100);
            Check("ONLINE_OWNED_RESIDUAL_ZERO",owner.ResidualsZero()&&!owner.ForcedCleanup);
        }
        // A second real installed launch checks the offline tray path separately.
        using(var owner=new ProductOwnedJob(exe,core,profile,root,candidate))
        {
            WaitHealth(owner,true); WaitUi(owner,"",v=>Flag(v,"online"),60000);
            owner.StopBackend(); WaitHealth(owner,false); WaitUi(owner,"",v=>Flag(v,"offline"));
            var tray=Ui("tray-quit",owner,"","unknown");
            Check("OFFLINE_OWNED_TRAY_INPUT",Flag(tray,"foreground")&&Flag(tray,"hit_target")&&Count(tray,"clicks")>=2&&Count(tray,"inserted")==Count(tray,"requested"));
            Check("OFFLINE_REAL_TRAY_NORMAL_EXIT",owner.WaitNormal(15000));
            var clock=Stopwatch.StartNew(); while(owner.Active!=0&&clock.ElapsedMilliseconds<10000) Thread.Sleep(100);
            Check("OFFLINE_OWNED_RESIDUAL_ZERO",owner.ResidualsZero()&&!owner.ForcedCleanup);
        }
    }
    public static int Main(string[] args)
    {
        try
        {
#if QA59_WIN11_LOCAL_TESTS
            return Windows11Main(args);
#else
            if(args.Length!=3 || Environment.GetEnvironmentVariable("GITHUB_REPOSITORY")!="bongbong90/Sorigul" || Environment.GetEnvironmentVariable("GITHUB_REF")!="refs/heads/qa/59-stage2a-local-runtime") return 64;
            string work=Path.GetFullPath(args[0]), msi=Path.GetFullPath(args[1]), installed=Path.GetFullPath(args[2]);
            if(!Path.GetFileName(work).StartsWith("qa59-server-",StringComparison.Ordinal) || !installed.StartsWith(work+"\\",StringComparison.OrdinalIgnoreCase) || !msi.StartsWith(work+"\\",StringComparison.OrdinalIgnoreCase)) return 65;
            var outcome=new Outcome();
            var candidate=RunnerCandidate.Validate(File.ReadAllText(Path.Combine(work,"candidate.json")),ProductOwnedJob.Digest(msi),new FileInfo(msi).Length,Environment.GetEnvironmentVariable("GITHUB_SHA"),long.Parse(Environment.GetEnvironmentVariable("GITHUB_RUN_ID")),outcome);
            Check("FRESH_MSI_PROVENANCE_CONTRACT",candidate!=null&&outcome.Ok);
            string[] executables=Directory.GetFiles(installed,"*.exe",SearchOption.TopDirectoryOnly);
            Check("INSTALLED_DESKTOP_UNIQUE",executables.Length==1);
            string core=Path.Combine(installed,@"binaries\sorigul-backend.exe");
            Check("INSTALLED_PAYLOAD_HASHES",ProductOwnedJob.Digest(executables[0])==candidate.DesktopHash&&ProductOwnedJob.Digest(core)==candidate.CoreHash
                &&ProductOwnedJob.Digest(Path.Combine(installed,@"binaries\ffmpeg.exe"))==candidate.FfmpegHash&&ProductOwnedJob.Digest(Path.Combine(installed,"sorigul-build-manifest.json"))==candidate.ManifestHash);
            Check("PRODUCTION_CONTEXT_STILL_DENY",!ContextGate.Evaluate("{}").ExecutionAllowed);
            desktopHash=candidate.DesktopHash;
            uiExe=Path.Combine(Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location),"InstalledUiWorker.exe");
            string parent=Environment.GetEnvironmentVariable("PUBLIC");
            using(var publicPin=WinFiles.CreateFile(parent,0x81,1,IntPtr.Zero,3,0x02200000,IntPtr.Zero))
            {
                WinFiles.Check(publicPin,parent,true);
                string scratch=Path.Combine(parent,"qa59-scratch-"+Guid.NewGuid().ToString("N"));
                using(var scratchPin=WinFiles.CreateOwnedDirectory(publicPin,Path.GetFileName(scratch)))
                using(var boundary=new DisposableRoot(scratch,new[]{@"C:\qa59-protected\Settings",@"C:\Program Files\Sorigul"},scratchPin))
                {
                    string profile=Path.Combine(boundary.Root,"profile"); Directory.CreateDirectory(profile);
                    Test(executables[0],core,boundary.Root,profile,candidate);
                    // Windows runner is disposed after the job. No recursive
                    // deletion fallback follows product-created reparse points.
                }
            }
            Console.WriteLine("SERVER_INSTALLED_QA PASS checks="+checks);
            return 0;
#endif
        }
        catch(Exception error)
        {
            Console.WriteLine("SERVER_INSTALLED_QA FAIL type="+error.GetType().Name+" checks="+checks);
            return 1;
        }
    }
}
