using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Threading;
using System.Runtime.InteropServices;
using System.Text;

namespace Qa59Installed.Runtime
{
    internal static class RuntimeTests
    {
        private static int checks, failed;
        private const string Sha = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
        private static void Check(string name, bool success)
        { checks++; if (!success) { failed++; Console.WriteLine("FAIL " + name); } }
        private static bool Denied(Action action)
        { try { action(); return false; } catch (BoundaryException) { return true; } }
        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool DeviceIoControl(Microsoft.Win32.SafeHandles.SafeFileHandle handle, uint code,
            byte[] input, int inputLength, IntPtr output, int outputLength, out int returned, IntPtr overlap);

        private sealed class FakeWorker : IIsolatedWorker
        {
            internal uint Status = 258;
            internal bool Normal, Throw;
            internal ManualResetEvent CleanupRelease;
            public bool ForcedCleanup { get; private set; }
            public uint Wait(uint ms) { if (Throw) throw new InvalidOperationException("SECRET_DO_NOT_OUTPUT"); Thread.Sleep((int)Math.Min(ms, 2)); return Status; }
            public bool NormalExit() { return Normal; }
            public void ForceCleanup() { ForcedCleanup = true; if (CleanupRelease != null) CleanupRelease.WaitOne(5000); }
        }

        public static int Main(string[] args)
        {
            try
            {
                PureTests();
                Console.WriteLine("RUNTIME_PURE_COMPLETED checks=" + checks);
                if (args.Length == 1 && args[0] == "--containment") ContainmentTests();
                // Never launch a worker or query/kill live processes here.
                Console.WriteLine("SYNTHETIC_PROCESS_JOB_ENDPOINT_TESTS NOT_VERIFIED QA_ACCOUNT_UNPROVEN");
            }
            catch { failed++; Console.WriteLine("FAIL RUNTIME_TEST_BOUNDARY"); }
            Console.WriteLine("RUNTIME checks=" + checks + " failed=" + failed);
            return failed == 0 ? 0 : 1;
        }

        private static void PureTests()
        {
            // Production assembly, no test-only trusted-control injection.
            MethodInfo[] gates = typeof(ContextGate).GetMethods(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static);
            int evaluate = 0;
            foreach (MethodInfo method in gates) if (method.Name == "Evaluate") evaluate++;
            Check("production seam absent", evaluate == 1);
            Check("production friendship absent", typeof(ContextGate).Assembly.GetCustomAttributes(typeof(System.Runtime.CompilerServices.InternalsVisibleToAttribute), false).Length == 0);
            ConstructorInfo constructor = typeof(GateDecision).GetConstructors(BindingFlags.NonPublic | BindingFlags.Instance)[0];
            var gate = (GateDecision)constructor.Invoke(new object[] { new Outcome(), true, true, Sha, 1L });
            Check("production constructor denies even reflected claims", !gate.ExecutionAllowed && !gate.MsiDownloadAllowed && !gate.MsiInstallAllowed);
            Check("public malformed context denied", !ContextGate.Evaluate("{}").ExecutionAllowed);
            foreach (Type type in new[] { typeof(AcceptanceDecision), typeof(ResultValidation), typeof(GateDecision) })
                foreach (FieldInfo field in type.GetFields(BindingFlags.Public | BindingFlags.Instance))
                    Check("result field readonly", field.IsInitOnly);
            var invalid = ResultContract.Validate("{}");
            bool frozen = false;
            try { invalid.Outcome.Add("FORGED"); } catch (InvalidOperationException) { frozen = true; }
            Check("result reasons frozen", frozen);
            StepSpec original = ResultContract.Steps[7];
            StepSpec[] exported = ResultContract.Steps;
            exported[7] = new StepSpec(original.Id);
            EvidenceSpec[] exportedEvidence = original.Evidence;
            exportedEvidence[0] = EvidenceSpec.Count("FORGED", 0);
            Check("fixed schema array cannot be replaced", ResultContract.Steps[7].Evidence.Length == 5);
            Check("evidence array cannot be replaced", ResultContract.Steps[7].Evidence[0].Key == "user_click_count");
            string[] pins = CandidateManifest.Keys; pins[0] = "FORGED";
            Check("manifest key array cannot be replaced", CandidateManifest.Keys[0] == "schema");
            Check("ancestor protected", DisposableRoot.Overlaps(@"D:\qa", @"D:\qa\settings"));
            Check("descendant protected", DisposableRoot.Overlaps(@"D:\qa\x", @"D:\qa"));
            Check("component prefix allowed", !DisposableRoot.Overlaps(@"D:\qax", @"D:\qa"));
            foreach (string bad in new[] { @"\\?\D:\qa", @"\\host\qa", @"D:\a\..\qa", @"D:\qa.", @"D:\qa ", @"D:\qa:ads", @"D:\PROGRA~1\qa", @"D:\AppData\qa", @"D:\Settings\qa", @"D:\Jobs\qa", @"D:\Runtime\qa", "D:/qa" })
                Check("unsafe lexical path", Denied(() => DisposableRoot.Canonical(bad)));
            var first = new ProcessIdentity(10, 1, 100, @"D:\qa\worker.exe", Sha);
            Check("same process identity", first.Same(new ProcessIdentity(10, 1, 100, @"d:\QA\worker.exe", Sha)));
            Check("PID reuse refused", !first.Same(new ProcessIdentity(10, 1, 101, first.Image, Sha)));
            Check("image replacement refused", !first.Same(new ProcessIdentity(10, 1, 100, @"D:\other.exe", Sha)));
            Check("hash mismatch refused", !first.Same(new ProcessIdentity(10, 1, 100, first.Image, new string('b', 64))));
            Check("accounted empty Job model", SyntheticProcessOwner.CompleteAccounting(1, 0, 1, 0));
            Check("missed exited child unknown", !SyntheticProcessOwner.CompleteAccounting(2, 0, 1, 0));
            Check("racing active snapshot unknown", !SyntheticProcessOwner.CompleteAccounting(2, 1, 2, 0));
            Check("invalid accounting unknown", !SyntheticProcessOwner.CompleteAccounting(0, 0, 0, 0));
            Check("missing endpoint ownership unknown", EndpointObserver.Observe(null).Verdict == Verdict.NOT_VERIFIED);
            Check("missing endpoint counts unknown", EndpointObserver.Observe(null).Tcp == null);
            Check("unprovisioned account refuses launch", !QaAccountBoundary.Verified());
            Check("launch refused before root access", Denied(() => SyntheticProcessOwner.Start(null, Sha)));

            StepSpec spec = ResultContract.Steps[7];
            foreach (string mode in new[] { "timeout", "normal", "crash", "query_failure", "provider_exception" })
            {
                var latch = new VerdictLatch(new[] { spec.Id });
                var supervisor = new BoundedSupervisor(latch, mode == "timeout" ? 30 : 1000);
                Check("empty evidence cannot PASS", Denied(() => supervisor.Record(spec.Id, new JsonMap().Parsed())));
                Check("unknown observation id refused", Denied(() => supervisor.Record("FORGED", new JsonMap().Parsed())));
                var worker = new FakeWorker();
                if (mode == "normal") { worker.Status = 0; worker.Normal = true; }
                if (mode == "crash") worker.Status = 0;
                if (mode == "query_failure") worker.Status = uint.MaxValue;
                if (mode == "provider_exception") worker.Throw = true;
                SupervisorObservation observation = supervisor.Run(worker);
                Check("completion freezes", latch.IsFrozen);
                Check("unmeasured remains unknown", latch.Get(spec.Id) == Verdict.NOT_VERIFIED);
                Check("timeout bounded and forced", mode != "timeout" || observation.DeadlineExceeded && observation.ForcedCleanup);
                Check("normal distinct from forced", mode != "normal" || observation.NormalExit && !observation.ForcedCleanup);
                Check("crash fails closed", mode != "crash" || observation.Verdict == Verdict.FAIL);
                Check("provider failure closes", mode != "provider_exception" && mode != "query_failure" || observation.ProviderFailed && observation.ForcedCleanup);
                var evidence = new JsonMap();
                foreach (EvidenceSpec item in spec.Evidence) evidence.TryAdd(item.Key, item.IsCount ? (object)item.ExpectedCount : true);
                Check("late PASS discarded", !supervisor.Record(spec.Id, evidence.Parsed()) && latch.Get(spec.Id) == Verdict.NOT_VERIFIED && latch.LateResults == 1);
                string text = EvidenceBridge.InstalledResult(Sha, observation);
                var validation = ResultContract.Validate(text);
                Check("bridge satisfies schema", validation.Outcome.Ok && validation.EffectiveOverall == Verdict.NOT_VERIFIED && validation.Cleanup == Verdict.NOT_VERIFIED);
                Check("bridge contains no exception/path", !text.Contains("SECRET") && !text.Contains("D:") && !text.Contains("worker.exe"));
                Check("bridge cannot authorize acceptance", AcceptanceGate.Evaluate(text, null, "{}", null).Acceptance != Verdict.PASS);
            }
            var missing = EvidenceBridge.InstalledResult(Sha, null);
            var blockedCleanup = new FakeWorker { CleanupRelease = new ManualResetEvent(false) };
            var cleanupClock = System.Diagnostics.Stopwatch.StartNew();
            var cleanupSupervisor = new BoundedSupervisor(new VerdictLatch(new[] { spec.Id }), 10);
            SupervisorObservation cleanupResult = cleanupSupervisor.Run(blockedCleanup);
            Check("blocked cleanup cannot extend result deadline", cleanupClock.ElapsedMilliseconds < 1000 && cleanupResult.ForcedCleanup && cleanupResult.DeadlineExceeded);
            blockedCleanup.CleanupRelease.Set();
            Check("missing runtime all unknown", ResultContract.Validate(missing).EffectiveOverall == Verdict.NOT_VERIFIED);
            Check("bad identity never free text", Denied(() => EvidenceBridge.InstalledResult("SECRET", null)));
            // Demonstrate why the pure transition is NOT a lock. An external
            // versioned CAS must select one of these proposals, never both.
            ApprovalRecord issued = SingleUseApproval.Issue("CAS-TEST", new Outcome());
            ApprovalRecord a = SingleUseApproval.Consume(issued, 1, new Outcome());
            ApprovalRecord b = SingleUseApproval.Consume(issued, 2, new Outcome());
            Check("stale snapshot makes two proposals", a != null && b != null);
            object durable = issued;
            object won = Interlocked.CompareExchange(ref durable, a, issued);
            object lost = Interlocked.CompareExchange(ref durable, b, issued);
            Check("CAS commits one proposal", ReferenceEquals(won, issued) && ReferenceEquals(lost, a) && ReferenceEquals(durable, a));
        }

        private static void ContainmentTests()
        {
            // Location is the disposable build directory inside this worktree,
            // not the user's OS temp directory (which may live in AppData).
            string build = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
            // Desktop/OneDrive/Documents are refused by the existing fixture
            // contract. Use a newly created QA-only root under the public
            // profile, with no user installation data read or written.
            string publicProfile = Environment.GetEnvironmentVariable("PUBLIC");
            if (string.IsNullOrEmpty(publicProfile)) throw new BoundaryException();
            string scratch = Path.Combine(publicProfile, "qa59-scratch-" + Guid.NewGuid().ToString("N"));
            var publicPin = WinFiles.CreateFile(publicProfile, 0x81, 1, IntPtr.Zero, 3, 0x02200000, IntPtr.Zero);
            WinFiles.Check(publicPin, publicProfile, true);
            var scratchPin = WinFiles.CreateOwnedDirectory(publicPin, Path.GetFileName(scratch));
            WinFiles.Check(scratchPin, scratch, true);
            Check("atomic creation refuses existing directory", Denied(() => {
                using (var duplicate = WinFiles.CreateOwnedDirectory(publicPin, Path.GetFileName(scratch))) { }
            }));
            string root = null;
            try
            {
                string[] protectedPaths = { @"C:\Program Files\Sorigul", @"C:\Users\User\AppData", @"D:\protected\Settings", @"D:\protected\Jobs", @"D:\protected\Runtime" };
                Check("unknown protection refuses", Denied(() => new DisposableRoot(scratch, new string[0])));
                Check("ancestor protection refuses", Denied(() => new DisposableRoot(scratch, new[] { publicProfile })));
                Console.WriteLine("CONTAINMENT_NEGATIVE_COMPLETED");
                using (var disposable = new DisposableRoot(scratch, protectedPaths, scratchPin))
                {
                    root = disposable.Root;
                    Console.WriteLine("CONTAINMENT_ROOT_OPENED");
                    disposable.Recheck();
                    Console.WriteLine("CONTAINMENT_ROOT_RECHECKED");
                    disposable.WriteRevision('A'); disposable.WriteRevision('B');
                    Check("four fixture files", Directory.GetFiles(root).Length == 4);
                    Check("rewrite denied", Denied(() => disposable.WriteRevision('A')));
                    Check("invalid revision denied", Denied(() => disposable.WriteRevision('Z')));
                    bool locked = false;
                    try { Directory.Move(root, root + "-replaced"); } catch (IOException) { locked = true; }
                    Check("root rename blocked by handles", locked);
                    locked = false;
                    try { Directory.Move(scratch, scratch + "-replaced"); } catch (IOException) { locked = true; }
                    Check("ancestor rename blocked by handles", locked);
                    JunctionTest(scratch, scratchPin);
                    AtomicCollisionTest(scratch, scratchPin);
                }
                Check("only fresh QA root", root != null && Path.GetFileName(root).StartsWith(SyntheticFixtures.RootPrefix, StringComparison.Ordinal));
            }
            finally
            {
                // No path-based deletion, even after a test assertion fails.
                bool removed = WinFiles.DeleteOwned(scratchPin);
                scratchPin.Dispose(); publicPin.Dispose();
                Check("owned scratch cleanup", removed);
            }
        }

        private static void JunctionTest(string scratch, Microsoft.Win32.SafeHandles.SafeFileHandle parent)
        {
            string name = "qa59-junction-" + Guid.NewGuid().ToString("N");
            using (var link = WinFiles.CreateOwnedDirectory(parent, name, true))
            {
                try
                {
                    byte[] substitute = Encoding.Unicode.GetBytes(@"\??\" + scratch);
                    byte[] print = Encoding.Unicode.GetBytes(scratch);
                    byte[] data = new byte[20 + substitute.Length + print.Length];
                    Array.Copy(BitConverter.GetBytes(0xA0000003U), 0, data, 0, 4);
                    Array.Copy(BitConverter.GetBytes((ushort)(data.Length - 8)), 0, data, 4, 2);
                    Array.Copy(BitConverter.GetBytes((ushort)substitute.Length), 0, data, 10, 2);
                    Array.Copy(BitConverter.GetBytes((ushort)(substitute.Length + 2)), 0, data, 12, 2);
                    Array.Copy(BitConverter.GetBytes((ushort)print.Length), 0, data, 14, 2);
                    Array.Copy(substitute, 0, data, 16, substitute.Length);
                    Array.Copy(print, 0, data, 18 + substitute.Length, print.Length);
                    int returned;
                    Check("disposable junction created", DeviceIoControl(link, 0x900A4, data, data.Length, IntPtr.Zero, 0, out returned, IntPtr.Zero));
                    WinFiles.Info info;
                    Check("junction is reparse", WinFiles.GetFileInformationByHandle(link, out info) && (info.Attributes & WinFiles.Reparse) != 0);
                    Check("junction handle refused", Denied(() => WinFiles.Check(link, scratch + "\\" + name, true)));
                }
                finally { Check("junction handle cleanup", WinFiles.DeleteOwned(link)); }
            }
        }

        private static void AtomicCollisionTest(string scratch, Microsoft.Win32.SafeHandles.SafeFileHandle parent)
        {
            string name = "qa59-collision-" + Guid.NewGuid().ToString("N");
            WinFiles.Info original;
            using (var first = WinFiles.CreateOwnedDirectory(parent, name))
            {
                if (!WinFiles.GetFileInformationByHandle(first, out original)) throw new BoundaryException();
            }
            try
            {
                Check("unlocked existing directory never adopted", Denied(() => {
                    using (var duplicate = WinFiles.CreateOwnedDirectory(parent, name)) { }
                }));
            }
            finally
            {
                // The deliberate unlocked collision fixture is deleted only
                // after matching its original volume/file ID through a handle.
                using (var cleanup = WinFiles.CreateFile(scratch + "\\" + name, 0x10080, 0, IntPtr.Zero, 3, 0x02200000, IntPtr.Zero))
                {
                    WinFiles.Check(cleanup, scratch + "\\" + name, true);
                    WinFiles.Info after;
                    if (!WinFiles.GetFileInformationByHandle(cleanup, out after) || original.Volume != after.Volume
                        || original.IndexHigh != after.IndexHigh || original.IndexLow != after.IndexLow) throw new BoundaryException();
                    Check("collision identity cleanup", WinFiles.DeleteOwned(cleanup));
                }
            }
        }
    }
}
