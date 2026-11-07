// Passive observations and ownership of a newly launched synthetic worker.
// No process-name search, product termination, arbitrary-PID kill or breakaway.
using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Security.Principal;
using System.Text;
using Microsoft.Win32.SafeHandles;

namespace Qa59Installed.Runtime
{
    internal enum SyntheticMode { Exit, Hang, Crash, Child, Endpoints, MissedChild }
    internal sealed class NativeHandle : SafeHandleZeroOrMinusOneIsInvalid
    {
        internal NativeHandle() : base(true) { }
        internal NativeHandle(IntPtr value) : base(true) { SetHandle(value); }
        protected override bool ReleaseHandle() { return WinProcess.CloseHandle(handle); }
    }

    internal static class QaAccountBoundary
    {
        // Isolation cannot be proven by a caller's bool, name or JSON. A future
        // provisioner must review and pin the separate QA account SID here.
        // Empty today: all synthetic process launches are refused on this host.
        private static readonly string[] ProvisionedQaSids = new string[0];
        internal static bool Verified()
        {
#if QA59_NATIVE_LOCAL_TESTS
            // The generated policy is linked only into the separate test EXE.
            // Loading that build as a library does not grant an execution gate.
            if (System.Reflection.Assembly.GetEntryAssembly() == System.Reflection.Assembly.GetExecutingAssembly()
                && LocalNativePolicy.Verified()) return true;
#endif
            using (WindowsIdentity current = WindowsIdentity.GetCurrent())
            {
                foreach (string sid in ProvisionedQaSids)
                    if (current.User != null && current.User.Value == sid) return true;
            }
            return false;
        }
    }

    internal static class WinProcess
    {
        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
        internal struct Startup
        {
            internal int Size; internal string Reserved, Desktop, Title;
            internal uint X, Y, XSize, YSize, XChars, YChars, Fill, Flags;
            internal ushort Show, ReservedSize; internal IntPtr ReservedBytes, Input, Output, Error;
        }
        [StructLayout(LayoutKind.Sequential)]
        internal struct Created { internal IntPtr Process, Thread; internal uint Pid, Tid; }
        [StructLayout(LayoutKind.Sequential)]
        internal struct StartupEx { internal Startup Startup; internal IntPtr Attributes; }
        [StructLayout(LayoutKind.Sequential)]
        internal struct BasicInfo { internal IntPtr Reserved1, Peb, Reserved2, Reserved3, Pid, ParentPid; }
        [DllImport("kernel32.dll", SetLastError = true)] internal static extern bool CloseHandle(IntPtr handle);
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        internal static extern NativeHandle CreateJobObject(IntPtr security, string name);
        [DllImport("kernel32.dll", SetLastError = true)] internal static extern bool AssignProcessToJobObject(NativeHandle job, NativeHandle process);
        [DllImport("kernel32.dll", SetLastError = true)] internal static extern bool IsProcessInJob(NativeHandle process, IntPtr job, out bool result);
        [DllImport("kernel32.dll", EntryPoint = "IsProcessInJob", SetLastError = true)] internal static extern bool IsCurrentProcessInJob(IntPtr process, IntPtr job, out bool result);
        [DllImport("kernel32.dll")] internal static extern uint GetCurrentProcessId();
        [DllImport("kernel32.dll", SetLastError = true)] internal static extern bool InitializeProcThreadAttributeList(IntPtr list, int count, uint flags, ref IntPtr size);
        [DllImport("kernel32.dll", SetLastError = true)] internal static extern bool UpdateProcThreadAttribute(IntPtr list, uint flags, IntPtr attribute, IntPtr value, IntPtr size, IntPtr previous, IntPtr returned);
        [DllImport("kernel32.dll")] internal static extern void DeleteProcThreadAttributeList(IntPtr list);
        [DllImport("kernel32.dll", SetLastError = true)] internal static extern bool TerminateJobObject(NativeHandle job, uint exitCode);
        [DllImport("kernel32.dll", SetLastError = true)] internal static extern bool TerminateProcess(NativeHandle process, uint exitCode);
        [DllImport("kernel32.dll", SetLastError = true)] internal static extern uint WaitForSingleObject(NativeHandle process, uint milliseconds);
        [DllImport("kernel32.dll", SetLastError = true)] internal static extern bool GetExitCodeProcess(NativeHandle process, out uint code);
        [DllImport("kernel32.dll", SetLastError = true)] internal static extern uint GetProcessId(NativeHandle process);
        [DllImport("kernel32.dll", SetLastError = true)] internal static extern NativeHandle OpenProcess(uint access, bool inherit, uint pid);
        [DllImport("kernel32.dll", SetLastError = true)] internal static extern uint ResumeThread(NativeHandle thread);
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        internal static extern bool CreateProcess(string application, StringBuilder command, IntPtr processSecurity, IntPtr threadSecurity,
            bool inherit, uint flags, IntPtr environment, string directory, ref StartupEx startup, out Created created);
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        internal static extern bool QueryFullProcessImageName(NativeHandle process, uint flags, StringBuilder text, ref uint length);
        [DllImport("kernel32.dll", SetLastError = true)]
        internal static extern bool GetProcessTimes(NativeHandle process, out long created, out long exited, out long kernel, out long user);
        [DllImport("ntdll.dll")]
        internal static extern int NtQueryInformationProcess(NativeHandle process, int kind, out BasicInfo info, int length, out int returned);
        [DllImport("kernel32.dll", SetLastError = true)]
        internal static extern bool QueryInformationJobObject(NativeHandle job, int kind, IntPtr buffer, uint length, out uint returned);
        [DllImport("kernel32.dll", SetLastError = true)]
        internal static extern bool SetInformationJobObject(NativeHandle job, int kind, IntPtr buffer, uint length);
    }

    internal sealed class ProcessIdentity
    {
        internal readonly uint Pid, ParentPid;
        internal readonly long Created;
        internal readonly string Image, Sha256;
        internal ProcessIdentity(uint pid, uint parent, long created, string image, string hash)
        { Pid = pid; ParentPid = parent; Created = created; Image = image; Sha256 = hash; }
        internal bool Same(ProcessIdentity other)
        {
            return other != null && Pid == other.Pid && Created == other.Created
                && string.Equals(Image, other.Image, StringComparison.OrdinalIgnoreCase) && Sha256 == other.Sha256;
        }
    }

    internal sealed class SyntheticProcessOwner : IDisposable
    {
        private readonly DisposableRoot root;
        private readonly Dictionary<uint, ProcessIdentity> identities = new Dictionary<uint, ProcessIdentity>();
        private readonly Dictionary<uint, NativeHandle> observed = new Dictionary<uint, NativeHandle>();
        private readonly HashSet<uint> currentPids = new HashSet<uint>();
        private SafeFileHandle imagePin;
        private string expectedWorkerHash;
        private NativeHandle job, process;
        private string launchPhase = "ROOT";
        internal string NativeLaunchPhase { get { return launchPhase; } }
        internal string ObservationCode { get; private set; }
        internal string NativeAccountingSummary()
        {
            int total, active;
            bool ok = Accounting(out total, out active);
            uint exit = uint.MaxValue; bool hasExit = process != null && WinProcess.GetExitCodeProcess(process, out exit);
            if (!hasExit) exit = uint.MaxValue;
            return "ok=" + ok + " total=" + total + " active=" + active + " known=" + identities.Count + " tree=" + ObservationCode
                + " wait=" + Wait(0) + " exit=" + exit;
        }
        internal ProcessIdentity Identity { get; private set; }
        internal bool ForcedCleanup { get; private set; }
        internal bool CleanupVerified { get; private set; }
        internal bool OwnershipVerified { get; private set; }
        internal int ObservedWorkerCount
        {
            get { int count = 0; foreach (var item in identities.Values) if (string.Equals(item.Image, root.Root + "\\Qa59SyntheticWorker.exe", StringComparison.OrdinalIgnoreCase)) count++; return count; }
        }

        private SyntheticProcessOwner(DisposableRoot root) { this.root = root; }

        internal static SyntheticProcessOwner Start(DisposableRoot root, string expectedSha256, SyntheticMode mode = SyntheticMode.Exit)
        {
            if (!QaAccountBoundary.Verified()) throw new BoundaryException();
            var owner = new SyntheticProcessOwner(root);
            try { owner.Launch(expectedSha256, mode); return owner; }
            catch
            {
#if QA59_NATIVE_LOCAL_TESTS
                Console.WriteLine("NATIVE_LAUNCH_FAILURE " + owner.launchPhase + " WIN32=" + Marshal.GetLastWin32Error());
#endif
                owner.Dispose(); throw new BoundaryException();
            }
        }

        private void Launch(string expectedHash, SyntheticMode mode)
        {
            root.Recheck();
            // Fixed arguments, no inherited handles or shell. Only a worker in
            // the fresh pinned QA root. Its hash comes from trusted build output.
            string image = root.Root + "\\Qa59SyntheticWorker.exe";
            string argument;
            switch (mode)
            {
                case SyntheticMode.Exit: argument = "--exit"; break;
                case SyntheticMode.Hang: argument = "--hang"; break;
                case SyntheticMode.Crash: argument = "--crash"; break;
                case SyntheticMode.Child: argument = "--child"; break;
                case SyntheticMode.Endpoints: argument = "--endpoints"; break;
                case SyntheticMode.MissedChild: argument = "--short-child"; break;
                default: throw new BoundaryException();
            }
            launchPhase = "IMAGE_PIN";
            imagePin = WinFiles.CreateFile(image, 0x80000000, 1, IntPtr.Zero, 3, 0x00200000, IntPtr.Zero);
            WinFiles.Check(imagePin, image, false);
            launchPhase = "HASH";
            string hash = Hash(imagePin);
            if (expectedHash == null || expectedHash.Length != 64 || hash != expectedHash) throw new BoundaryException();
            expectedWorkerHash = hash;
            launchPhase = "JOB";
            job = WinProcess.CreateJobObject(IntPtr.Zero, null);
            if (job.IsInvalid) throw new BoundaryException();
            // JOBOBJECT_EXTENDED_LIMIT_INFORMATION, KILL_ON_JOB_CLOSE. Native
            // layouts are 144 bytes on x64, 112 on x86; LimitFlags offset 16.
            launchPhase = "JOB_LIMIT";
            int size = IntPtr.Size == 8 ? 144 : 112;
            IntPtr limits = Marshal.AllocHGlobal(size);
            try
            {
                Marshal.Copy(new byte[size], 0, limits, size);
                Marshal.WriteInt32(limits, 16, 0x2000);
                if (!WinProcess.SetInformationJobObject(job, 9, limits, (uint)size)) throw new BoundaryException();
            }
            finally { Marshal.FreeHGlobal(limits); }
            launchPhase = "HOST_JOB";
            bool nested;
            if (!WinProcess.IsCurrentProcessInJob(new IntPtr(-1), IntPtr.Zero, out nested)) throw new BoundaryException();
            // Hosted runners already own an outer Job. Windows 2022 supports
            // nested Jobs; JOB_LIST atomically adds our own non-breakaway Job.
            // Exact membership is verified below, with no uncontained fallback.
            launchPhase = "JOB_ATTRIBUTE";
            var startup = new WinProcess.StartupEx(); startup.Startup.Size = Marshal.SizeOf(startup);
            WinProcess.Created child;
            IntPtr bytes = IntPtr.Zero;
            WinProcess.InitializeProcThreadAttributeList(IntPtr.Zero, 1, 0, ref bytes);
            if (bytes == IntPtr.Zero || bytes.ToInt64() > 65536) throw new BoundaryException();
            startup.Attributes = Marshal.AllocHGlobal(bytes);
            IntPtr jobValue = Marshal.AllocHGlobal(IntPtr.Size);
            bool initialized = false;
            try
            {
                initialized = WinProcess.InitializeProcThreadAttributeList(startup.Attributes, 1, 0, ref bytes);
                Marshal.WriteIntPtr(jobValue, job.DangerousGetHandle());
                // PROC_THREAD_ATTRIBUTE_JOB_LIST: assignment occurs as part of
                // process creation. Supervisor death cannot leave an unowned
                // suspended child in the create/AssignProcessToJobObject gap.
                if (!initialized || !WinProcess.UpdateProcThreadAttribute(startup.Attributes, 0, new IntPtr(0x2000D),
                    jobValue, new IntPtr(IntPtr.Size), IntPtr.Zero, IntPtr.Zero)) throw new BoundaryException();
                launchPhase = "CREATE_PROCESS";
                if (!WinProcess.CreateProcess(image, new StringBuilder("\"" + image + "\" " + argument), IntPtr.Zero, IntPtr.Zero, false,
                        0x08080004, IntPtr.Zero, root.Root, ref startup, out child)) throw new BoundaryException();
            }
            finally
            {
                if (initialized) WinProcess.DeleteProcThreadAttributeList(startup.Attributes);
                Marshal.FreeHGlobal(startup.Attributes); Marshal.FreeHGlobal(jobValue);
            }
            process = new NativeHandle(child.Process);
            using (var thread = new NativeHandle(child.Thread))
            {
                launchPhase = "OWN_JOB_MEMBERSHIP";
                bool member;
                if (!WinProcess.IsProcessInJob(process, job.DangerousGetHandle(), out member) || !member)
                {
                    ForcedCleanup = true;
                    CleanupVerified = WinProcess.TerminateProcess(process, 125) && WinProcess.WaitForSingleObject(process, 1000) == 0;
                    throw new BoundaryException();
                }
                launchPhase = "IDENTITY";
                Identity = Observe(process);
                if (Identity == null || Identity.Pid != child.Pid || Identity.ParentPid != WinProcess.GetCurrentProcessId()
                    || !string.Equals(Identity.Image, image, StringComparison.OrdinalIgnoreCase) || Identity.Sha256 != hash)
                    throw new BoundaryException();
                identities.Add(Identity.Pid, Identity);
                OwnershipVerified = true;
                launchPhase = "RESUME";
                if (WinProcess.ResumeThread(thread) == uint.MaxValue) throw new BoundaryException();
            }
        }

        private static string Hash(SafeFileHandle handle)
        {
            // FileStream owns a duplicate-safe non-owning view; pin lifetime is
            // retained by the owner. A separate view must not close the pin.
            using (var view = new SafeFileHandle(handle.DangerousGetHandle(), false))
            using (var stream = new FileStream(view, FileAccess.Read))
            using (var sha = SHA256.Create())
            { return BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", "").ToLowerInvariant(); }
        }

        private ProcessIdentity Observe(NativeHandle handle)
        {
            long created, exited, kernel, user;
            var text = new StringBuilder(32768); uint length = (uint)text.Capacity;
            WinProcess.BasicInfo basic; int returned;
            if (!WinProcess.GetProcessTimes(handle, out created, out exited, out kernel, out user)
                || !WinProcess.QueryFullProcessImageName(handle, 0, text, ref length)
                || WinProcess.NtQueryInformationProcess(handle, 0, out basic, Marshal.SizeOf(typeof(WinProcess.BasicInfo)), out returned) != 0)
                return null;
            string image = text.ToString();
            if (!string.Equals(image, root.Root + "\\Qa59SyntheticWorker.exe", StringComparison.OrdinalIgnoreCase))
            { ObservationCode = "IMAGE_NOT_ALLOWLISTED"; return null; }
            // Reopen the pinned image to avoid sharing FileStream offsets.
            using (var pin = WinFiles.CreateFile(image, 0x80000000, 1, IntPtr.Zero, 3, 0x00200000, IntPtr.Zero))
            {
                WinFiles.Check(pin, image, false);
                string actualHash = Hash(pin);
                if (actualHash != expectedWorkerHash) return null;
                return new ProcessIdentity(WinProcess.GetProcessId(handle), unchecked((uint)basic.ParentPid.ToInt64()), created, image, actualHash);
            }
        }

        internal Verdict ObserveTree(out int activeCount)
        {
            ObservationCode = "START";
            activeCount = 0;
            if (!OwnershipVerified || job == null || job.IsClosed) return Verdict.NOT_VERIFIED;
            // Bounded snapshot. Oversize, races, exited children and query errors
            // cannot turn into an empty-tree PASS.
            const int capacity = 4096;
            IntPtr buffer = Marshal.AllocHGlobal(8 + capacity * IntPtr.Size);
            try
            {
                uint returned;
                if (!WinProcess.QueryInformationJobObject(job, 3, buffer, (uint)(8 + capacity * IntPtr.Size), out returned)) { ObservationCode = "JOB_QUERY"; return Verdict.NOT_VERIFIED; }
                int assigned = Marshal.ReadInt32(buffer, 0), listed = Marshal.ReadInt32(buffer, 4);
                if (assigned != listed || listed < 0 || listed > capacity) return Verdict.NOT_VERIFIED;
                var snapshot = new Dictionary<uint, ProcessIdentity>();
                for (int k = 0; k < listed; k++)
                {
                    uint pid = unchecked((uint)Marshal.ReadIntPtr(buffer, 8 + k * IntPtr.Size).ToInt64());
                    NativeHandle handle;
                    if (!observed.TryGetValue(pid, out handle))
                    {
                        if (observed.Count >= capacity) return Verdict.NOT_VERIFIED;
                        handle = WinProcess.OpenProcess(0x101400, false, pid);
                        observed.Add(pid, handle); // bound handle count, prevent PID reuse
                    }
                    if (handle.IsInvalid) { ObservationCode = "OPEN_PROCESS"; return Verdict.NOT_VERIFIED; }
                    bool member;
                    if (!WinProcess.IsProcessInJob(handle, job.DangerousGetHandle(), out member) || !member) { ObservationCode = "MEMBERSHIP"; return Verdict.NOT_VERIFIED; }
                    ProcessIdentity identity = Observe(handle), previous;
                    if (identity == null) { ObservationCode = "IDENTITY"; return Verdict.NOT_VERIFIED; }
                    if (identities.TryGetValue(pid, out previous) && !previous.Same(identity)) return Verdict.FAIL;
                    snapshot.Add(pid, identity);
                }
                foreach (ProcessIdentity item in snapshot.Values)
                {
                    ProcessIdentity parent;
                    if (item.Pid != Identity.Pid &&
                        ((!snapshot.TryGetValue(item.ParentPid, out parent) && !identities.TryGetValue(item.ParentPid, out parent))
                        || parent.Created > item.Created || parent.Sha256 != item.Sha256)) return Verdict.NOT_VERIFIED;
                    identities[item.Pid] = item;
                }
                int total, active;
                // A short-lived descendant may be absent from every PID
                // snapshot. Cumulative Job accounting exposes that gap.
                if (!Accounting(out total, out active) || !CompleteAccounting(total, active, identities.Count, listed))
                    { ObservationCode = "ACCOUNTING_GAP"; return Verdict.NOT_VERIFIED; }
                Verdict exits = KnownChildExits();
                if (exits != Verdict.PASS) return exits;
                currentPids.Clear();
                foreach (uint pid in snapshot.Keys) currentPids.Add(pid);
                activeCount = listed;
                ObservationCode = "PASS";
                return Verdict.PASS;
            }
            catch { return Verdict.NOT_VERIFIED; }
            finally { Marshal.FreeHGlobal(buffer); }
        }

        internal uint Wait(uint milliseconds) { return process == null ? uint.MaxValue : WinProcess.WaitForSingleObject(process, milliseconds); }
        internal bool MatchesCurrentIdentity(ProcessIdentity expected)
        {
            return expected != null && expected.Same(Observe(process));
        }
        internal bool NormalExit()
        {
            uint code;
            return !ForcedCleanup && Wait(0) == 0 && WinProcess.GetExitCodeProcess(process, out code) && code == 0
                && JobEmpty();
        }

        private bool JobEmpty()
        {
            int total, active;
            return Accounting(out total, out active) && CompleteAccounting(total, active, identities.Count, 0)
                && KnownChildExits() == Verdict.PASS;
        }

        internal static bool CompleteAccounting(int total, int active, int known, int snapshot)
        {
            return total > 0 && total <= 4096 && active >= 0 && active <= total
                && total == known && active == snapshot;
        }

        private Verdict KnownChildExits()
        {
            foreach (var pair in observed)
            {
                if (Identity != null && pair.Key == Identity.Pid) continue;
                uint wait = WinProcess.WaitForSingleObject(pair.Value, 0);
                if (wait == 258) continue;
                uint code;
                if (wait != 0 || !WinProcess.GetExitCodeProcess(pair.Value, out code)) return Verdict.NOT_VERIFIED;
                if (code != 0 && !ForcedCleanup) return Verdict.FAIL;
            }
            return Verdict.PASS;
        }

        private bool Accounting(out int total, out int active)
        {
            total = active = 0;
            if (job == null || job.IsInvalid || job.IsClosed) return false;
            IntPtr accounting = Marshal.AllocHGlobal(48);
            try
            {
                uint returned;
                if (!WinProcess.QueryInformationJobObject(job, 1, accounting, 48, out returned)) return false;
                total = Marshal.ReadInt32(accounting, 36);
                active = Marshal.ReadInt32(accounting, 40);
                return total > 0 && total <= 4096 && active >= 0 && active <= total;
            }
            finally { Marshal.FreeHGlobal(accounting); }
        }

        internal bool TryGetVerifiedPids(out HashSet<uint> pids)
        {
            pids = null;
            int count;
            if (ObserveTree(out count) != Verdict.PASS) return false;
            // Include exited identities while their original process handles
            // remain pinned. Cleanup must query their endpoints, not an empty
            // PID set, and a recycled PID must never become owned evidence.
            pids = new HashSet<uint>();
            foreach (var identity in identities)
            {
                NativeHandle held;
                if (Identity != null && identity.Key == Identity.Pid) held = process;
                else if (!observed.TryGetValue(identity.Key, out held)) return false;
                long created, exited, kernel, user;
                if (held == null || held.IsClosed || held.IsInvalid || WinProcess.GetProcessId(held) != identity.Key
                    || !WinProcess.GetProcessTimes(held, out created, out exited, out kernel, out user)
                    || created != identity.Value.Created) return false;
                pids.Add(identity.Key);
            }
            return pids.Count == identities.Count && count <= pids.Count;
        }

        internal void ForceCleanup()
        {
            ForcedCleanup = true;
            if (job == null || job.IsInvalid || job.IsClosed || !WinProcess.TerminateJobObject(job, 124)) return;
            int total, active;
            // Cleanup proves release, independently of forced child exit codes
            // and any previously detected accounting gap. It never means normal.
            CleanupVerified = Wait(1000) == 0 && Accounting(out total, out active) && active == 0;
        }

        public void Dispose()
        {
            if (job != null && !job.IsClosed)
            {
                int remaining;
                if (ObserveTree(out remaining) != Verdict.PASS || remaining != 0) ForceCleanup();
                job.Dispose(); // kill-on-close is forced cleanup, never normal exit
            }
            foreach (NativeHandle handle in observed.Values) handle.Dispose();
            observed.Clear();
            if (process != null) process.Dispose();
            if (imagePin != null) imagePin.Dispose();
        }
    }
}
