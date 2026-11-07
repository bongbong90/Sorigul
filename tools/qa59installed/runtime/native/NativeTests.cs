// Executed only by the authorized public hosted-runner test build. No product,
// installation, credentials, media, screenshots or artifact uploads.
using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Security.Cryptography;
using System.Threading;
using Microsoft.Win32.SafeHandles;

namespace Qa59Installed.Runtime
{
    internal sealed class NativeFixture : IDisposable
    {
        internal readonly SafeFileHandle PublicPin, ScratchPin;
        internal readonly DisposableRoot Boundary;
        internal readonly string Scratch;
        internal readonly string Hash;
        internal readonly WinFiles.Info BinaryId;
        internal static readonly string WorkerSource = Path.Combine(Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location), "Qa59SyntheticWorker.exe");
        internal NativeFixture()
        {
            if (!QaAccountBoundary.Verified()) throw new BoundaryException();
            string parent = Environment.GetEnvironmentVariable("PUBLIC");
            PublicPin = WinFiles.CreateFile(parent, 0x81, 1, IntPtr.Zero, 3, 0x02200000, IntPtr.Zero);
            WinFiles.Check(PublicPin, parent, true);
            Scratch = Path.Combine(parent, "qa59-scratch-" + Guid.NewGuid().ToString("N"));
            ScratchPin = WinFiles.CreateOwnedDirectory(PublicPin, Path.GetFileName(Scratch));
            Boundary = new DisposableRoot(Scratch, new[] { @"C:\qa59-protected\Settings", @"C:\qa59-protected\Jobs", @"C:\Program Files\Sorigul" }, ScratchPin);
            byte[] bytes = File.ReadAllBytes(WorkerSource);
            using (var sha = SHA256.Create()) Hash = BitConverter.ToString(sha.ComputeHash(bytes)).Replace("-", "").ToLowerInvariant();
            string image = Path.Combine(Boundary.Root, "Qa59SyntheticWorker.exe");
            using (var file = WinFiles.CreateFile(image, 0x40000080, 0, IntPtr.Zero, 1, 0x00200000, IntPtr.Zero))
            {
                WinFiles.Check(file, image, false);
                if (!WinFiles.GetFileInformationByHandle(file, out BinaryId)) throw new BoundaryException();
                using (var view = new SafeFileHandle(file.DangerousGetHandle(), false))
                using (var stream = new FileStream(view, FileAccess.Write)) { stream.Write(bytes, 0, bytes.Length); stream.Flush(true); }
            }
        }
        internal void Ready()
        {
            var clock = Stopwatch.StartNew();
            while (!File.Exists(Path.Combine(Boundary.Root, "worker-ready")) && clock.ElapsedMilliseconds < 5000) Thread.Sleep(10);
            if (!File.Exists(Path.Combine(Boundary.Root, "worker-ready"))) throw new InvalidOperationException("WORKER_READY_TIMEOUT");
        }
        internal void Stop()
        {
            Boundary.Recheck();
            using (var stream = new FileStream(Path.Combine(Boundary.Root, "worker-stop"), FileMode.CreateNew, FileAccess.Write)) { stream.WriteByte(1); }
        }
        internal static void DeleteFile(string root, string name, WinFiles.Info? expected)
        {
            string path = Path.Combine(root, name);
            using (var handle = WinFiles.CreateFile(path, 0x10080, 0, IntPtr.Zero, 3, 0x00200000, IntPtr.Zero))
            {
                if (handle.IsInvalid && System.Runtime.InteropServices.Marshal.GetLastWin32Error() == 2) return;
                WinFiles.Check(handle, path, false);
                WinFiles.Info actual;
                if (!WinFiles.GetFileInformationByHandle(handle, out actual)) throw new BoundaryException();
                if (expected.HasValue && (actual.Volume != expected.Value.Volume || actual.IndexHigh != expected.Value.IndexHigh || actual.IndexLow != expected.Value.IndexLow)) throw new BoundaryException();
                if (!WinFiles.DeleteOwned(handle)) throw new BoundaryException();
            }
        }
        public void Dispose()
        {
            Boundary.Recheck();
            DeleteFile(Boundary.Root, "worker-ready", null); DeleteFile(Boundary.Root, "worker-stop", null);
            DeleteFile(Boundary.Root, "Qa59SyntheticWorker.exe", BinaryId);
            Boundary.Dispose();
            bool deleted = WinFiles.DeleteOwned(ScratchPin);
            ScratchPin.Dispose(); PublicPin.Dispose();
            if (!deleted) throw new BoundaryException();
        }
    }

    internal static class NativeTests
    {
        private static int checks, failed;
        private static void Check(string id, bool ok)
        { checks++; if (!ok) { failed++; Console.WriteLine("NATIVE_FAIL " + id); } }
        private static void WaitCleanup(SyntheticProcessOwner owner)
        {
            var clock = Stopwatch.StartNew();
            while (!owner.CleanupVerified && clock.ElapsedMilliseconds < 5000) Thread.Sleep(10);
        }
        private static void Normal()
        {
            using (var fixture = new NativeFixture())
            using (var owner = SyntheticProcessOwner.Start(fixture.Boundary, fixture.Hash))
            {
                Check("PROCESS_CREATED_OWN_JOB", owner.OwnershipVerified && owner.Identity.Pid > 0);
                Check("ACTUAL_IDENTITY", owner.MatchesCurrentIdentity(owner.Identity));
                var wrong = new ProcessIdentity(owner.Identity.Pid, owner.Identity.ParentPid, owner.Identity.Created + 1, owner.Identity.Image, owner.Identity.Sha256);
                Check("PID_REUSE_TUPLE_REFUSED", !owner.MatchesCurrentIdentity(wrong));
                wrong = new ProcessIdentity(owner.Identity.Pid, owner.Identity.ParentPid, owner.Identity.Created, owner.Identity.Image, new string('0', 64));
                Check("IMAGE_HASH_MISMATCH_REFUSED", !owner.MatchesCurrentIdentity(wrong));
                fixture.Ready(); int live;
                Check("NORMAL_TREE_ACCOUNTED_BEFORE_EXIT", owner.ObserveTree(out live) == Verdict.PASS && owner.ObservedWorkerCount == 1);
                fixture.Stop();
                bool exited = owner.Wait(5000) == 0;
                var normalClock = Stopwatch.StartNew();
                while (!owner.NormalExit() && normalClock.ElapsedMilliseconds < 3000) Thread.Sleep(10);
                Check("NORMAL_PROCESS_EXIT", exited && owner.NormalExit() && !owner.ForcedCleanup);
                var counts = EndpointObserver.Observe(owner);
                Console.WriteLine("NATIVE_ACCOUNTING " + owner.NativeAccountingSummary());
                Check("NORMAL_RESIDUAL_ENDPOINTS_ZERO", counts.Verdict == Verdict.PASS && counts.Tcp == 0 && counts.Udp == 0);
            }
        }
        private static void EndpointsAndChildren(SyntheticMode mode, bool force = false)
        {
            using (var fixture = new NativeFixture())
            using (var owner = SyntheticProcessOwner.Start(fixture.Boundary, fixture.Hash, mode))
            {
                fixture.Ready();
                int active;
                Verdict tree = owner.ObserveTree(out active);
                Console.WriteLine("NATIVE_ACCOUNTING " + owner.NativeAccountingSummary());
                if (mode == SyntheticMode.MissedChild)
                {
                    Check("MISSED_CHILD_NOT_VERIFIED", tree == Verdict.NOT_VERIFIED);
                    Check("MISSED_CHILD_NOT_NORMAL", !owner.NormalExit());
                    owner.ForceCleanup(); WaitCleanup(owner);
                    Check("MISSED_CHILD_CLEANUP_RELEASED", owner.CleanupVerified && owner.ForcedCleanup);
                    return;
                }
                Check(mode == SyntheticMode.Child ? "ACTUAL_CHILD_ACCOUNTED" : "LIVE_WORKER_ACCOUNTED", tree == Verdict.PASS && owner.ObservedWorkerCount == (mode == SyntheticMode.Child ? 2 : 1) && active >= owner.ObservedWorkerCount);
                var counts = EndpointObserver.Observe(owner);
                Check("OWNED_TCP_UDP_OBSERVED", counts.Verdict == Verdict.PASS && counts.Tcp >= 1 && counts.Udp >= 1);
                EndpointObserver.InvalidFamilyForTest = true;
                try
                {
                    counts = EndpointObserver.Observe(owner);
                    Check("NATIVE_ENDPOINT_QUERY_FAILURE_UNKNOWN", counts.Verdict == Verdict.NOT_VERIFIED && counts.Tcp == null && counts.Udp == null);
                }
                finally { EndpointObserver.InvalidFamilyForTest = false; }
                if (force)
                {
                    owner.ForceCleanup(); WaitCleanup(owner);
                    counts = EndpointObserver.Observe(owner);
                    Check("FORCED_CHILD_TREE_RELEASED", owner.CleanupVerified && owner.ForcedCleanup && !owner.NormalExit()
                        && owner.ObserveTree(out active) == Verdict.PASS && active == 0);
                    Check("FORCED_CHILD_OWNED_ENDPOINTS_ZERO", counts.Verdict == Verdict.PASS && counts.Tcp == 0 && counts.Udp == 0);
                    return;
                }
                fixture.Stop(); Check("TREE_EXITED", owner.Wait(5000) == 0);
                var clock = Stopwatch.StartNew();
                while (!owner.NormalExit() && clock.ElapsedMilliseconds < 3000) Thread.Sleep(10);
                Check("TREE_NORMAL_WITHOUT_FORCED_CLEANUP", owner.NormalExit() && !owner.ForcedCleanup);
                counts = EndpointObserver.Observe(owner);
                Console.WriteLine("NATIVE_ACCOUNTING " + owner.NativeAccountingSummary());
                Check("TREE_RESIDUAL_PROCESSES_PORTS_ZERO", owner.ObserveTree(out active) == Verdict.PASS && active == 0 && counts.Verdict == Verdict.PASS && counts.Tcp == 0 && counts.Udp == 0);
            }
        }
        private sealed class DelayedWorker : IIsolatedWorker
        {
            private readonly SyntheticProcessOwner owner;
            internal readonly ManualResetEvent Release = new ManualResetEvent(false);
            internal DelayedWorker(SyntheticProcessOwner owner) { this.owner = owner; }
            public uint Wait(uint milliseconds) { return owner.Wait(milliseconds); }
            public bool NormalExit() { return owner.NormalExit(); }
            public bool ForcedCleanup { get { return owner.ForcedCleanup; } }
            public void ForceCleanup() { Release.WaitOne(2000); owner.ForceCleanup(); }
        }
        private static void Supervisor(SyntheticMode mode, bool delayed)
        {
            using (var fixture = new NativeFixture())
            using (var owner = SyntheticProcessOwner.Start(fixture.Boundary, fixture.Hash, mode))
            {
                fixture.Ready(); int live;
                Check("SUPERVISOR_TREE_ACCOUNTED", owner.ObserveTree(out live) == Verdict.PASS);
                if (mode != SyntheticMode.Hang) fixture.Stop();
                StepSpec step = ResultContract.Steps[7];
                var latch = new VerdictLatch(new[] { step.Id });
                var bounded = new BoundedSupervisor(latch, mode == SyntheticMode.Hang ? 250 : 3000);
                var delay = new DelayedWorker(owner);
                var clock = Stopwatch.StartNew();
                SupervisorObservation observation = bounded.Run(delayed ? (IIsolatedWorker)delay : new ProcessWorker(owner));
                Check("NATIVE_SUPERVISOR_FREEZES", latch.IsFrozen && latch.Get(step.Id) == Verdict.NOT_VERIFIED);
                Check("NATIVE_HANG_DEADLINE", mode != SyntheticMode.Hang || observation.DeadlineExceeded && clock.ElapsedMilliseconds < 1500);
                Check("NATIVE_CRASH_FAIL", mode != SyntheticMode.Crash || observation.Verdict == Verdict.FAIL && !observation.NormalExit);
                if (mode == SyntheticMode.Exit)
                {
                    Check("SUPERVISOR_NORMAL_EXIT_DISTINCT", observation.NormalExit && !observation.ForcedCleanup && !observation.DeadlineExceeded && owner.NormalExit());
                    return;
                }
                var evidence = new JsonMap();
                foreach (EvidenceSpec item in step.Evidence) evidence.TryAdd(item.Key, item.IsCount ? (object)item.ExpectedCount : true);
                Check("NATIVE_LATE_PASS_REFUSED", !bounded.Record(step.Id, evidence.Parsed()) && latch.Get(step.Id) == Verdict.NOT_VERIFIED);
                if (delayed) Check("CLEANUP_DELAY_RESULT_ALREADY_FROZEN", owner.Wait(0) == 258 && observation.ForcedCleanup);
                delay.Release.Set(); WaitCleanup(owner);
                Check("FORCED_CLEANUP_DISTINCT", owner.CleanupVerified && owner.ForcedCleanup && !owner.NormalExit());
                var counts = EndpointObserver.Observe(owner);
                Check("SUPERVISOR_RESIDUAL_ZERO", counts.Verdict == Verdict.PASS && counts.Tcp == 0 && counts.Udp == 0);
            }
        }

        private static int Vanish()
        {
            // Deliberately do not Dispose: process death must close the sole Job
            // handle and release the worker. Output is captured by the parent.
            var fixture = new NativeFixture();
            var owner = SyntheticProcessOwner.Start(fixture.Boundary, fixture.Hash, SyntheticMode.Endpoints);
            fixture.Ready();
            var counts = EndpointObserver.Observe(owner);
            if (counts.Verdict != Verdict.PASS || counts.Tcp < 1 || counts.Udp < 1) return 72;
            WinFiles.Info rootId, scratchId;
            using (var root = WinFiles.CreateFile(fixture.Boundary.Root, 0x80, 7, IntPtr.Zero, 3, 0x02200000, IntPtr.Zero))
                if (!WinFiles.GetFileInformationByHandle(root, out rootId)) return 73;
            if (!WinFiles.GetFileInformationByHandle(fixture.ScratchPin, out scratchId)) return 74;
            Console.WriteLine(string.Join("|", new[] { owner.Identity.Pid.ToString(), owner.Identity.Created.ToString(), fixture.Boundary.Root, fixture.Scratch,
                rootId.Volume.ToString(), rootId.IndexHigh.ToString(), rootId.IndexLow.ToString(), scratchId.Volume.ToString(), scratchId.IndexHigh.ToString(), scratchId.IndexLow.ToString() }));
            Console.Out.Flush();
            // No console-input dependency in a headless hosted process. The
            // parent acknowledges only after pinning the actual worker handle.
            string acknowledgement = Path.Combine(fixture.Boundary.Root,"supervisor-ack");
            var clock = Stopwatch.StartNew();
            while (!File.Exists(acknowledgement) && clock.ElapsedMilliseconds < 5000) Thread.Sleep(10);
            if (!File.Exists(acknowledgement)) return 75;
            byte[] command = File.ReadAllBytes(acknowledgement);
            if (command.Length != 1 || command[0] != 71) return 75;
            Environment.Exit(37);
            return 76;
        }
        private static void SupervisorDeath()
        {
            var start = new ProcessStartInfo(Assembly.GetExecutingAssembly().Location, "--vanish")
                { UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true, RedirectStandardError = true };
            using (var helper = Process.Start(start))
            {
                try
                {
                    var read = helper.StandardOutput.ReadLineAsync();
                    if (!read.Wait(10000) || read.Result == null) throw new InvalidOperationException("HELPER_READY_TIMEOUT");
                    string[] data = read.Result.Split('|');
                    if (data.Length != 10) throw new BoundaryException();
                    uint pid = uint.Parse(data[0]); long birth = long.Parse(data[1]);
                    string root = data[2], scratch = data[3];
                    string parent = Environment.GetEnvironmentVariable("PUBLIC");
                    if (Path.GetDirectoryName(scratch) != parent || !Path.GetFileName(scratch).StartsWith("qa59-scratch-", StringComparison.Ordinal)
                        || Path.GetDirectoryName(root) != scratch || !Path.GetFileName(root).StartsWith(SyntheticFixtures.RootPrefix, StringComparison.Ordinal)) throw new BoundaryException();
                    using (var witness = WinProcess.OpenProcess(0x101000, false, pid))
                    {
                        long created, exited, kernel, user;
                        WinProcess.BasicInfo info; int returned;
                        if (witness.IsInvalid || !WinProcess.GetProcessTimes(witness, out created, out exited, out kernel, out user) || created != birth
                            || WinProcess.NtQueryInformationProcess(witness, 0, out info, System.Runtime.InteropServices.Marshal.SizeOf(typeof(WinProcess.BasicInfo)), out returned) != 0
                            || info.ParentPid.ToInt64() != helper.Id) throw new BoundaryException();
                        var identity = new ProcessIdentity(pid, (uint)helper.Id, birth, root + "\\Qa59SyntheticWorker.exe", "");
                        using (var acknowledgement = new FileStream(Path.Combine(root,"supervisor-ack-pending"),FileMode.CreateNew,FileAccess.Write))
                        { acknowledgement.WriteByte(71); acknowledgement.Flush(true); }
                        File.Move(Path.Combine(root,"supervisor-ack-pending"),Path.Combine(root,"supervisor-ack"));
                        bool helperExited = helper.WaitForExit(5000);
                        Console.WriteLine("NATIVE_HELPER_EXIT observed=" + helperExited + " code=" + (helperExited ? helper.ExitCode : -1));
                        Check("SUPERVISOR_ABRUPT_EXIT", helperExited && helper.ExitCode == 37);
                        Check("JOB_CLOSE_KILLS_OWNED_WORKER", WinProcess.WaitForSingleObject(witness, 5000) == 0);
                        var counts = EndpointObserver.ExitedWitness(witness, identity);
                        Check("SUPERVISOR_DEATH_RESIDUAL_ENDPOINTS_ZERO", counts.Verdict == Verdict.PASS && counts.Tcp == 0 && counts.Udp == 0);
                    }
                    // Reopen only the two generated identities, then keep both
                    // directory handles pinned while deleting fixed child files.
                    using (var scratchHandle = WinFiles.CreateFile(scratch, 0x10081, 1, IntPtr.Zero, 3, 0x02200000, IntPtr.Zero))
                    using (var rootHandle = WinFiles.CreateFile(root, 0x10081, 1, IntPtr.Zero, 3, 0x02200000, IntPtr.Zero))
                    {
                        WinFiles.Check(scratchHandle, scratch, true); WinFiles.Check(rootHandle, root, true);
                        WinFiles.Info actual;
                        if (!WinFiles.GetFileInformationByHandle(rootHandle, out actual) || actual.Volume != uint.Parse(data[4]) || actual.IndexHigh != uint.Parse(data[5]) || actual.IndexLow != uint.Parse(data[6])) throw new BoundaryException();
                        if (!WinFiles.GetFileInformationByHandle(scratchHandle, out actual) || actual.Volume != uint.Parse(data[7]) || actual.IndexHigh != uint.Parse(data[8]) || actual.IndexLow != uint.Parse(data[9])) throw new BoundaryException();
                        NativeFixture.DeleteFile(root, "worker-ready", null);
                        NativeFixture.DeleteFile(root, "supervisor-ack", null);
                        NativeFixture.DeleteFile(root, "supervisor-ack-pending", null);
                        NativeFixture.DeleteFile(root, "Qa59SyntheticWorker.exe", null);
                        Check("SUPERVISOR_DEATH_ROOT_CLEANUP", WinFiles.DeleteOwned(rootHandle));
                    }
                    using (var scratchHandle = WinFiles.CreateFile(scratch, 0x10081, 0, IntPtr.Zero, 3, 0x02200000, IntPtr.Zero))
                    {
                        WinFiles.Info actual; WinFiles.Check(scratchHandle, scratch, true);
                        if (!WinFiles.GetFileInformationByHandle(scratchHandle, out actual) || actual.Volume != uint.Parse(data[7]) || actual.IndexHigh != uint.Parse(data[8]) || actual.IndexLow != uint.Parse(data[9])) throw new BoundaryException();
                        Check("SUPERVISOR_DEATH_SCRATCH_CLEANUP", WinFiles.DeleteOwned(scratchHandle));
                    }
                }
                finally { if (!helper.HasExited) { helper.Kill(); helper.WaitForExit(5000); } }
            }
        }
        public static int Main(string[] args)
        {
            if (!QaAccountBoundary.Verified()) { Console.WriteLine("NATIVE_GATE_DENY"); return 69; }
            if (args.Length == 1 && args[0] == "--vanish") return Vanish();
            try
            {
                Console.WriteLine("NATIVE_CASE NORMAL"); Normal();
                Console.WriteLine("NATIVE_CASE ENDPOINTS"); EndpointsAndChildren(SyntheticMode.Endpoints);
                Console.WriteLine("NATIVE_CASE CHILD"); EndpointsAndChildren(SyntheticMode.Child);
                Console.WriteLine("NATIVE_CASE FORCED_CHILD"); EndpointsAndChildren(SyntheticMode.Child, true);
                Console.WriteLine("NATIVE_CASE MISSED_CHILD");
                EndpointsAndChildren(SyntheticMode.MissedChild);
                Console.WriteLine("NATIVE_CASE SUPERVISOR");
                Supervisor(SyntheticMode.Exit, false); Supervisor(SyntheticMode.Hang, false); Supervisor(SyntheticMode.Crash, false); Supervisor(SyntheticMode.Hang, true);
                Console.WriteLine("NATIVE_CASE SUPERVISOR_DEATH"); SupervisorDeath();
            }
            catch (Exception error)
            {
                failed++;
                // Only fixed exception types/codes; never Message/StackTrace.
                Console.WriteLine("NATIVE_EXCEPTION " + error.GetType().Name + " WIN32=" + System.Runtime.InteropServices.Marshal.GetLastWin32Error());
            }
            Console.WriteLine("NATIVE_RESULT checks=" + checks + " failed=" + failed);
            return failed == 0 && checks >= 40 ? 0 : 1;
        }
    }
}
