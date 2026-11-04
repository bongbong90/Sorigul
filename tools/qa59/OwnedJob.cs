using System;
using System.ComponentModel;
using System.Runtime.InteropServices;

// Start suspended: containment is established before any test code can create children.
public sealed class OwnedJob : IDisposable
{
    [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)] struct STARTUPINFO {
        public uint cb; public string reserved, desktop, title;
        public uint x, y, xSize, ySize, xCount, yCount, fill, flags;
        public ushort show, reservedSize; public IntPtr reserved2, stdin, stdout, stderr;
    }
    [StructLayout(LayoutKind.Sequential)] struct PROCESS_INFORMATION {
        public IntPtr process, thread; public uint pid, tid;
    }
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)] static extern IntPtr CreateJobObject(IntPtr a, string n);
    [DllImport("kernel32.dll", SetLastError=true)] static extern bool SetInformationJobObject(IntPtr j, int c, IntPtr p, uint s);
    [DllImport("kernel32.dll", SetLastError=true)] static extern bool QueryInformationJobObject(IntPtr j, int c, IntPtr p, uint s, IntPtr r);
    [DllImport("kernel32.dll", SetLastError=true)] static extern bool AssignProcessToJobObject(IntPtr j, IntPtr p);
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)] static extern bool CreateProcess(string app, string cmd, IntPtr pa, IntPtr ta, bool inherit, uint flags, IntPtr env, string cwd, ref STARTUPINFO si, out PROCESS_INFORMATION pi);
    [DllImport("kernel32.dll")] static extern uint ResumeThread(IntPtr t);
    [DllImport("kernel32.dll")] static extern bool TerminateProcess(IntPtr p, uint code);
    [DllImport("kernel32.dll")] static extern bool TerminateJobObject(IntPtr j, uint code);
    [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr h);
    [DllImport("kernel32.dll")] static extern bool GetExitCodeProcess(IntPtr p, out uint code);
    IntPtr job, process;
    public uint RootId { get; private set; }
    public OwnedJob() {
        job = CreateJobObject(IntPtr.Zero, null);
        if (job == IntPtr.Zero) throw new Win32Exception();
        IntPtr limits = Marshal.AllocHGlobal(144);
        try {
            Marshal.Copy(new byte[144], 0, limits, 144);
            Marshal.WriteInt32(limits, 16, 0x2000); // JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if (!SetInformationJobObject(job, 9, limits, 144)) throw new Win32Exception();
        } finally { Marshal.FreeHGlobal(limits); }
    }
    public void Start(string exe, string directory) {
        STARTUPINFO si = new STARTUPINFO(); si.cb = (uint)Marshal.SizeOf(si);
        PROCESS_INFORMATION pi;
        if (!CreateProcess(exe, "\"" + exe + "\" \"" + directory + "\"", IntPtr.Zero, IntPtr.Zero, false, 4, IntPtr.Zero, directory, ref si, out pi)) throw new Win32Exception();
        process = pi.process; RootId = pi.pid;
        try {
            if (!AssignProcessToJobObject(job, process)) { TerminateProcess(process, 90); throw new Win32Exception(); }
            if (ResumeThread(pi.thread) == 0xffffffff) { TerminateProcess(process, 91); throw new Win32Exception(); }
        } finally { CloseHandle(pi.thread); }
    }
    public uint ExitCode { get { uint code; if (!GetExitCodeProcess(process, out code)) throw new Win32Exception(); return code; } }
    public uint Active {
        get {
            IntPtr data = Marshal.AllocHGlobal(48);
            try {
                if (!QueryInformationJobObject(job, 1, data, 48, IntPtr.Zero)) throw new Win32Exception();
                return (uint)Marshal.ReadInt32(data, 40);
            } finally { Marshal.FreeHGlobal(data); }
        }
    }
    public int[] Pids() {
        IntPtr data = Marshal.AllocHGlobal(4104);
        try {
            if (!QueryInformationJobObject(job, 3, data, 4104, IntPtr.Zero)) throw new Win32Exception();
            int count = Marshal.ReadInt32(data, 4); int[] ids = new int[count];
            for (int i=0; i<count; i++) ids[i] = (int)Marshal.ReadInt64(data, 8 + i*8);
            return ids;
        } finally { Marshal.FreeHGlobal(data); }
    }
    public void Stop() { if (!TerminateJobObject(job, 92)) throw new Win32Exception(); }
    public void Dispose() {
        if (job != IntPtr.Zero) { CloseHandle(job); job = IntPtr.Zero; }
        if (process != IntPtr.Zero) { CloseHandle(process); process = IntPtr.Zero; }
    }
}
