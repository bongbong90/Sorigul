using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;

namespace Qa59Installed.Runtime
{
    internal sealed class EndpointCounts
    {
        internal readonly Verdict Verdict;
        internal readonly int? Tcp, Udp;
        internal EndpointCounts(Verdict verdict, int? tcp, int? udp) { Verdict = verdict; Tcp = tcp; Udp = udp; }
    }

    internal static class EndpointObserver
    {
        [DllImport("iphlpapi.dll", SetLastError = true)]
        private static extern uint GetExtendedTcpTable(IntPtr table, ref uint size, bool order, uint family, int kind, uint reserved);
        [DllImport("iphlpapi.dll", SetLastError = true)]
        private static extern uint GetExtendedUdpTable(IntPtr table, ref uint size, bool order, uint family, int kind, uint reserved);

        // Only IDs pinned by live owned process handles may be supplied.
        // A query failure has null counts, never zero. Four protocol/family
        // tables are mandatory. No addresses, ports or foreign PIDs escape.
        internal static EndpointCounts Observe(SyntheticProcessOwner owner)
        {
            HashSet<uint> ownedPinnedPids;
            if (owner == null || !owner.TryGetVerifiedPids(out ownedPinnedPids)) return new EndpointCounts(Verdict.NOT_VERIFIED, null, null);
            try
            {
                int tcp = Count(true, 2, 24, 20, ownedPinnedPids) + Count(true, 23, 56, 52, ownedPinnedPids);
                int udp = Count(false, 2, 12, 8, ownedPinnedPids) + Count(false, 23, 28, 24, ownedPinnedPids);
                if (tcp > ResultContract.MaxCount || udp > ResultContract.MaxCount) throw new BoundaryException();
                HashSet<uint> after;
                if (!owner.TryGetVerifiedPids(out after) || !ownedPinnedPids.SetEquals(after)) throw new BoundaryException();
                return new EndpointCounts(Verdict.PASS, tcp, udp);
            }
            catch { return new EndpointCounts(Verdict.NOT_VERIFIED, null, null); }
        }

        private static uint Query(bool tcp, IntPtr buffer, ref uint size, uint family)
        {
            return tcp ? GetExtendedTcpTable(buffer, ref size, false, family, 5, 0)
                : GetExtendedUdpTable(buffer, ref size, false, family, 1, 0);
        }

        private static int Count(bool tcp, uint family, int stride, int pidOffset, ICollection<uint> owned)
        {
            uint size = 0;
            if (Query(tcp, IntPtr.Zero, ref size, family) != 122 || size < 4 || size > 4 * 1024 * 1024) throw new BoundaryException();
            uint capacity = size;
            IntPtr buffer = Marshal.AllocHGlobal((int)capacity);
            try
            {
                if (Query(tcp, buffer, ref size, family) != 0 || size < 4 || size > capacity) throw new BoundaryException();
                int rows = Marshal.ReadInt32(buffer);
                if (rows < 0 || rows > ((long)size - 4) / stride) throw new BoundaryException();
                int matches = 0;
                for (int k = 0; k < rows; k++)
                    if (owned.Contains(unchecked((uint)Marshal.ReadInt32(buffer, 4 + k * stride + pidOffset)))) matches++;
                return matches;
            }
            finally { Marshal.FreeHGlobal(buffer); }
        }
    }
}
