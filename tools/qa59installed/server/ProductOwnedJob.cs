// Hosted fresh-candidate test only. No name-based kill or arbitrary PID input.
using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using Qa59Installed;
using Qa59Installed.Runtime;

internal sealed class ProductOwnedJob : IDisposable
{
    internal sealed class Item
    {
        internal uint Pid, Parent;
        internal long Created;
        internal string Image;
        internal NativeHandle Handle;
    }
    private NativeHandle job, process;
    private SafeFilePin desktop;
    private readonly Dictionary<uint, Item> known = new Dictionary<uint, Item>();
    private readonly RunnerCandidate candidate;
    private readonly string corePath;
    internal uint RootPid { get; private set; }
    internal long RootCreated { get; private set; }
    internal bool ForcedCleanup { get; private set; }
    internal static string Digest(string path)
    { using (var stream = File.OpenRead(path)) using (var sha = SHA256.Create()) return BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", "").ToLowerInvariant(); }
    private sealed class SafeFilePin : IDisposable
    {
        internal readonly Microsoft.Win32.SafeHandles.SafeFileHandle Handle;
        internal SafeFilePin(string path) { Handle = WinFiles.CreateFile(path,0x80000000,1,IntPtr.Zero,3,0x00200000,IntPtr.Zero); WinFiles.Check(Handle,path,false); }
        public void Dispose() { Handle.Dispose(); }
    }
    internal ProductOwnedJob(string exe, string core, string profile, string work, RunnerCandidate candidate)
    {
        if (candidate == null || Environment.GetEnvironmentVariable("GITHUB_ACTIONS") != "true"
            || Environment.GetEnvironmentVariable("RUNNER_ENVIRONMENT") != "github-hosted"
            || Environment.GetEnvironmentVariable("QA59_PUBLIC_REPOSITORY") != "true" || Environment.GetEnvironmentVariable("ImageOS") != "win22") throw new BoundaryException();
        this.candidate = candidate; corePath = core;
        if (Digest(exe) != candidate.DesktopHash || Digest(core) != candidate.CoreHash) throw new BoundaryException();
        desktop = new SafeFilePin(exe);
        job = WinProcess.CreateJobObject(IntPtr.Zero,null);
        IntPtr limits = Marshal.AllocHGlobal(144);
        try { Marshal.Copy(new byte[144],0,limits,144); Marshal.WriteInt32(limits,16,0x2000); if (!WinProcess.SetInformationJobObject(job,9,limits,144)) throw new BoundaryException(); }
        finally { Marshal.FreeHGlobal(limits); }
        var start = new WinProcess.StartupEx(); start.Startup.Size = Marshal.SizeOf(start);
        IntPtr bytes = IntPtr.Zero; WinProcess.InitializeProcThreadAttributeList(IntPtr.Zero,1,0,ref bytes);
        if (bytes == IntPtr.Zero || bytes.ToInt64() > 65536) throw new BoundaryException();
        start.Attributes = Marshal.AllocHGlobal(bytes); IntPtr value = Marshal.AllocHGlobal(IntPtr.Size);
        IntPtr environment = IntPtr.Zero; bool initialized = false;
        try
        {
            initialized = WinProcess.InitializeProcThreadAttributeList(start.Attributes,1,0,ref bytes);
            Marshal.WriteIntPtr(value,job.DangerousGetHandle());
            if (!initialized || !WinProcess.UpdateProcThreadAttribute(start.Attributes,0,new IntPtr(0x2000D),value,new IntPtr(IntPtr.Size),IntPtr.Zero,IntPtr.Zero)) throw new BoundaryException();
            var entries = new SortedDictionary<string,string>(StringComparer.OrdinalIgnoreCase);
            foreach (DictionaryEntry entry in Environment.GetEnvironmentVariables())
            {
                string key = (string)entry.Key;
                string upper = key.ToUpperInvariant();
                if (upper.Contains("TOKEN") || upper.Contains("SECRET") || upper.Contains("PASSWORD") || upper.Contains("KEY") || upper.StartsWith("ACTIONS_",StringComparison.Ordinal)) continue;
                entries[key] = (string)entry.Value;
            }
            entries["LOCALAPPDATA"] = profile; entries["APPDATA"] = Path.Combine(work,"roaming");
            entries["TEMP"] = Path.Combine(work,"temp"); entries["TMP"] = entries["TEMP"];
            Directory.CreateDirectory(entries["APPDATA"]); Directory.CreateDirectory(entries["TEMP"]);
            var block = new StringBuilder(); foreach (var pair in entries) block.Append(pair.Key).Append('=').Append(pair.Value).Append('\0'); block.Append('\0');
            environment = Marshal.StringToHGlobalUni(block.ToString());
            WinProcess.Created created;
            if (!WinProcess.CreateProcess(exe,new StringBuilder("\"" + exe + "\""),IntPtr.Zero,IntPtr.Zero,false,0x08080404,environment,Path.GetDirectoryName(exe),ref start,out created)) throw new BoundaryException();
            process = new NativeHandle(created.Process); RootPid = created.Pid;
            long birth, exited, kernel, user;
            if(!WinProcess.GetProcessTimes(process,out birth,out exited,out kernel,out user)) throw new BoundaryException();
            RootCreated=birth;
            using (var thread = new NativeHandle(created.Thread))
            {
                bool member;
                if (!WinProcess.IsProcessInJob(process,job.DangerousGetHandle(),out member) || !member) throw new BoundaryException();
                if (WinProcess.ResumeThread(thread) == uint.MaxValue) throw new BoundaryException();
            }
        }
        catch { Dispose(); throw; }
        finally
        {
            if (initialized) WinProcess.DeleteProcThreadAttributeList(start.Attributes);
            Marshal.FreeHGlobal(start.Attributes); Marshal.FreeHGlobal(value);
            if (environment != IntPtr.Zero) Marshal.FreeHGlobal(environment);
        }
    }
    internal List<Item> Snapshot()
    {
        var result = new List<Item>();
        IntPtr buffer = Marshal.AllocHGlobal(32776);
        try
        {
            uint returned;
            if (!WinProcess.QueryInformationJobObject(job,3,buffer,32776,out returned)) throw new BoundaryException();
            int assigned = Marshal.ReadInt32(buffer), count = Marshal.ReadInt32(buffer,4);
            if (count < 0 || count > 4096 || assigned != count) throw new BoundaryException();
            for (int i = 0; i < count; i++)
            {
                uint pid = unchecked((uint)Marshal.ReadIntPtr(buffer,8+i*IntPtr.Size).ToInt64());
                Item item;
                if (!known.TryGetValue(pid,out item))
                {
                    var handle = WinProcess.OpenProcess(0x101401,false,pid);
                    bool member;
                    if (handle.IsInvalid || !WinProcess.IsProcessInJob(handle,job.DangerousGetHandle(),out member) || !member) { handle.Dispose(); throw new BoundaryException(); }
                    long birth, exit, kernel, user;
                    var text = new StringBuilder(32768); uint length = (uint)text.Capacity;
                    WinProcess.BasicInfo basic; int bytes;
                    if (!WinProcess.GetProcessTimes(handle,out birth,out exit,out kernel,out user)
                        || !WinProcess.QueryFullProcessImageName(handle,0,text,ref length)
                        || WinProcess.NtQueryInformationProcess(handle,0,out basic,Marshal.SizeOf(typeof(WinProcess.BasicInfo)),out bytes) != 0) { handle.Dispose(); throw new BoundaryException(); }
                    item = new Item { Pid=pid, Parent=unchecked((uint)basic.ParentPid.ToInt64()), Created=birth, Image=text.ToString(), Handle=handle };
                    known.Add(pid,item);
                }
                if (WinProcess.WaitForSingleObject(item.Handle,0) == 258) result.Add(item);
            }
            return result;
        }
        finally { Marshal.FreeHGlobal(buffer); }
    }
    internal int BackendRoots()
    {
        int roots=0; foreach(var item in Snapshot()) if (SamePath(item.Image,corePath) && item.Parent==RootPid) roots++; return roots;
    }
    internal int BackendProcesses()
    { int count=0; foreach(var item in Snapshot()) if(SamePath(item.Image,corePath)) count++; return count; }
    private static bool SamePath(string first,string second) { return string.Equals(first,second,StringComparison.OrdinalIgnoreCase); }
    internal void StopBackend()
    {
        var targets = Snapshot().FindAll(item=>SamePath(item.Image,corePath));
        if (targets.Count==0 || BackendRoots()!=1 || Digest(corePath)!=candidate.CoreHash) throw new BoundaryException();
        targets.Sort((first,second)=>first.Parent==RootPid ? 1 : second.Parent==RootPid ? -1 : 0);
        foreach(var item in targets)
        {
            long birth,exit,kernel,user; bool member;
            if (!WinProcess.IsProcessInJob(item.Handle,job.DangerousGetHandle(),out member) || !member
                || !WinProcess.GetProcessTimes(item.Handle,out birth,out exit,out kernel,out user) || birth!=item.Created) throw new BoundaryException();
            if (WinProcess.WaitForSingleObject(item.Handle,0)==258 && !WinProcess.TerminateProcess(item.Handle,125)) throw new BoundaryException();
        }
        foreach(var item in targets) if(WinProcess.WaitForSingleObject(item.Handle,5000)!=0) throw new BoundaryException();
    }
    internal bool WaitNormal(int timeout)
    { uint code; return WinProcess.WaitForSingleObject(process,(uint)timeout)==0 && WinProcess.GetExitCodeProcess(process,out code) && code==0 && !ForcedCleanup; }
    internal bool BackendListenerOwned(int port)
    {
        var coreIds = new HashSet<uint>(); foreach(var item in Snapshot()) if(SamePath(item.Image,corePath)) coreIds.Add(item.Pid);
        uint size=0; if(GetExtendedTcpTable(IntPtr.Zero,ref size,false,2,5,0)!=122 || size<4 || size>4194304) return false;
        uint capacity=size; IntPtr data=Marshal.AllocHGlobal((int)size);
        try
        {
            if(GetExtendedTcpTable(data,ref size,false,2,5,0)!=0 || size>capacity) return false;
            int count=Marshal.ReadInt32(data); if(count<0 || count>((long)size-4)/24) return false;
            for(int i=0;i<count;i++)
            {
                int row=4+i*24; int localPort=(Marshal.ReadByte(data,row+8)<<8)|Marshal.ReadByte(data,row+9);
                if(Marshal.ReadInt32(data,row)==2 && localPort==port && coreIds.Contains(unchecked((uint)Marshal.ReadInt32(data,row+20)))) return true;
            }
            return false;
        }
        finally { Marshal.FreeHGlobal(data); }
    }
    internal int Active { get { return Snapshot().Count; } }
    [DllImport("iphlpapi.dll")] private static extern uint GetExtendedTcpTable(IntPtr table,ref uint size,bool order,uint family,int kind,uint reserved);
    [DllImport("iphlpapi.dll")] private static extern uint GetExtendedUdpTable(IntPtr table,ref uint size,bool order,uint family,int kind,uint reserved);
    private int Endpoints(bool tcp,uint family,int stride,int offset)
    {
        uint size=0;
        uint error=tcp?GetExtendedTcpTable(IntPtr.Zero,ref size,false,family,5,0):GetExtendedUdpTable(IntPtr.Zero,ref size,false,family,1,0);
        if(error!=122 || size<4 || size>4194304) throw new BoundaryException();
        uint capacity=size; IntPtr data=Marshal.AllocHGlobal((int)size);
        try
        {
            error=tcp?GetExtendedTcpTable(data,ref size,false,family,5,0):GetExtendedUdpTable(data,ref size,false,family,1,0);
            if(error!=0 || size>capacity) throw new BoundaryException();
            int count=Marshal.ReadInt32(data), owned=0;
            if(count<0 || count>((long)size-4)/stride) throw new BoundaryException();
            for(int i=0;i<count;i++) if(known.ContainsKey(unchecked((uint)Marshal.ReadInt32(data,4+i*stride+offset)))) owned++;
            return owned;
        }
        finally { Marshal.FreeHGlobal(data); }
    }
    internal bool ResidualsZero()
    {
        if(Active!=0) return false;
        foreach(var item in known.Values) if(WinProcess.WaitForSingleObject(item.Handle,0)!=0) return false;
        return Endpoints(true,2,24,20)+Endpoints(true,23,56,52)+Endpoints(false,2,12,8)+Endpoints(false,23,28,24)==0;
    }
    public void Dispose()
    {
        if(job!=null && !job.IsClosed)
        {
            bool active=true; try { active=Active!=0; } catch { }
            if(active) { ForcedCleanup=true; WinProcess.TerminateJobObject(job,124); if(process!=null) WinProcess.WaitForSingleObject(process,5000); }
            job.Dispose();
        }
        foreach(var item in known.Values) item.Handle.Dispose(); known.Clear();
        if(process!=null) process.Dispose(); if(desktop!=null) desktop.Dispose();
    }
}
