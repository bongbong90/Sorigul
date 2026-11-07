using System;
using System.Diagnostics;
using System.Threading;

namespace Qa59Installed.Runtime
{
    // The implementation used in production contains kernel process waits,
    // never UIAutomation/native provider callbacks on the supervisor thread.
    internal interface IIsolatedWorker
    {
        uint Wait(uint milliseconds);
        bool NormalExit();
        void ForceCleanup();
        bool ForcedCleanup { get; }
    }

    internal sealed class ProcessWorker : IIsolatedWorker
    {
        private readonly SyntheticProcessOwner owner;
        internal ProcessWorker(SyntheticProcessOwner owner) { this.owner = owner; }
        public uint Wait(uint milliseconds) { return owner.Wait(milliseconds); }
        public bool NormalExit() { return owner.NormalExit(); }
        public void ForceCleanup() { owner.ForceCleanup(); }
        public bool ForcedCleanup { get { return owner.ForcedCleanup; } }
    }

    internal sealed class SupervisorObservation
    {
        internal readonly bool DeadlineExceeded, ProviderFailed, ForcedCleanup, NormalExit;
        internal readonly Verdict Verdict;
        internal SupervisorObservation(bool deadline, bool failed, bool forced, bool normal, Verdict verdict)
        { DeadlineExceeded = deadline; ProviderFailed = failed; ForcedCleanup = forced; NormalExit = normal; Verdict = verdict; }
    }

    internal sealed class BoundedSupervisor
    {
        private readonly object sync = new object();
        private readonly VerdictLatch latch;
        private readonly Stopwatch elapsed = new Stopwatch();
        private readonly int deadlineMs;
        private bool closed;
        private SupervisorObservation snapshot;

        internal BoundedSupervisor(VerdictLatch latch, int deadlineMs)
        {
            if (latch == null || deadlineMs < 1 || deadlineMs > 60000) throw new BoundaryException();
            this.latch = latch; this.deadlineMs = deadlineMs;
            elapsed.Start();
        }

        // A caller cannot supply a verdict or an input-JSON evidence object.
        // Observations arriving after the deadline freeze pending results first.
        internal bool Record(string id, JsonObject measured)
        {
            lock (sync)
            {
                if (elapsed.ElapsedMilliseconds >= deadlineMs && !closed) Freeze(true, false, false, false);
                StepSpec spec = null;
                foreach (StepSpec known in ResultContract.Steps) if (known.Id == id) spec = known;
                foreach (StepSpec known in ResultContract.Negatives) if (known.Id == id) spec = known;
                if (spec == null || measured == null || measured.Count != spec.Evidence.Length) throw new BoundaryException();
                foreach (EvidenceSpec item in spec.Evidence)
                {
                    object value = measured.Get(item.Key);
                    if (value == null || (!(value is JsonNull) && (item.IsCount ? !(value is long) : !(value is bool)))) throw new BoundaryException();
                }
                Verdict verdict = ResultContract.Derive(spec, measured);
                if (elapsed.ElapsedMilliseconds >= deadlineMs && !closed) Freeze(true, false, false, false);
                // This is an internal trusted-observer boundary, not a JSON RPC.
                return latch.Record(id, verdict, verdict == Verdict.PASS ? null : "EVIDENCE_MISSING");
            }
        }

        internal SupervisorObservation Run(IIsolatedWorker worker)
        {
            if (worker == null) return Freeze(false, true, false, false);
            bool deadline = false, failed = false, normal = false, forced = false;
            try
            {
                while (true)
                {
                    long left = deadlineMs - elapsed.ElapsedMilliseconds;
                    if (left <= 0) { deadline = true; break; }
                    uint wait = worker.Wait((uint)Math.Min(left, 25));
                    if (wait == 0) { normal = worker.NormalExit(); break; }
                    if (wait != 258) { failed = true; break; }
                }
            }
            catch { failed = true; }
            if (elapsed.ElapsedMilliseconds >= deadlineMs) { deadline = true; normal = false; }
            // Freeze BEFORE cleanup. Cleanup never promotes the result.
            SupervisorObservation result = Freeze(deadline, failed, deadline || failed || !normal, normal);
            if (deadline || failed || !normal)
            {
                forced = true;
                // Cleanup is on a background thread. Native cleanup/observation
                // can stall; it cannot extend the supervisor's result deadline.
                // No cleanup success is claimed here. Process death closes our
                // non-inherited job handle and kills the contained worker.
                ThreadPool.QueueUserWorkItem(delegate { try { worker.ForceCleanup(); } catch { } });
            }
            lock (sync)
            {
                // Timeout from Record may have frozen earlier: preserve its
                // failure flags and then record actual forced cleanup as well.
                snapshot = new SupervisorObservation(result.DeadlineExceeded || deadline, result.ProviderFailed || failed,
                    result.ForcedCleanup || forced, result.NormalExit && normal,
                    result.Verdict);
                return snapshot;
            }
        }

        private SupervisorObservation Freeze(bool deadline, bool failed, bool forced, bool normal)
        {
            lock (sync)
            {
                if (closed) return snapshot;
                closed = true;
                latch.Freeze(deadline ? "DEADLINE_EXCEEDED" : failed ? "PROVIDER_FAILED" : "EVIDENCE_MISSING");
                // Exit alone proves no installed step; missing evidence remains
                // NOT_VERIFIED. Abnormal exit is a failure, independently.
                snapshot = new SupervisorObservation(deadline, failed, forced, normal,
                    !normal && !deadline && !failed ? Verdict.FAIL : Verdict.NOT_VERIFIED);
                return snapshot;
            }
        }
    }
}
