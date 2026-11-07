// Windows-only local QA boundary. No product paths are opened. The caller
// supplies a designated disposable parent, never a Settings/Jobs target.
using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using Microsoft.Win32.SafeHandles;

namespace Qa59Installed.Runtime
{
    internal sealed class BoundaryException : Exception
    {
        internal BoundaryException() : base("QA_BOUNDARY_DENIED") { }
    }

    internal static class WinFiles
    {
        [StructLayout(LayoutKind.Sequential)]
        private struct UnicodeName { internal ushort Length, MaximumLength; internal IntPtr Buffer; }
        [StructLayout(LayoutKind.Sequential)]
        private struct ObjectAttributes
        {
            internal int Length; internal IntPtr RootDirectory, ObjectName;
            internal uint Attributes; internal IntPtr SecurityDescriptor, SecurityQualityOfService;
        }
        [StructLayout(LayoutKind.Sequential)]
        private struct IoStatus { internal IntPtr Status, Information; }
        [DllImport("ntdll.dll")]
        private static extern int NtCreateFile(out SafeFileHandle file, uint access, ref ObjectAttributes attributes,
            out IoStatus status, IntPtr allocation, uint fileAttributes, uint share, uint disposition,
            uint options, IntPtr ea, uint eaLength);

        internal static SafeFileHandle CreateOwnedDirectory(SafeFileHandle parent, string name, bool writable = false)
        {
            var unicode = new UnicodeName();
            unicode.Buffer = Marshal.StringToHGlobalUni(name);
            unicode.Length = checked((ushort)(name.Length * 2));
            unicode.MaximumLength = checked((ushort)(unicode.Length + 2));
            IntPtr nameBuffer = Marshal.AllocHGlobal(Marshal.SizeOf(unicode));
            try
            {
                Marshal.StructureToPtr(unicode, nameBuffer, false);
                var attributes = new ObjectAttributes();
                attributes.Length = Marshal.SizeOf(attributes);
                attributes.RootDirectory = parent.DangerousGetHandle();
                attributes.ObjectName = nameBuffer;
                attributes.Attributes = 0x40; // OBJ_CASE_INSENSITIVE
                SafeFileHandle handle; IoStatus status;
                // FILE_CREATE atomically refuses an existing entry and returns
                // the newly created directory handle. No create/open race.
                int result = NtCreateFile(out handle, writable ? 0x40110081U : 0x110081U, ref attributes, out status,
                    IntPtr.Zero, 16, 1, 2, 0x00200021, IntPtr.Zero, 0);
                if (result < 0) { if (handle != null) handle.Dispose(); throw new BoundaryException(); }
                return handle;
            }
            finally { Marshal.FreeHGlobal(nameBuffer); Marshal.FreeHGlobal(unicode.Buffer); }
        }
        internal const uint Reparse = 0x400;
        [StructLayout(LayoutKind.Sequential)]
        internal struct Info
        {
            internal uint Attributes;
            internal System.Runtime.InteropServices.ComTypes.FILETIME Created, Accessed, Written;
            internal uint Volume, SizeHigh, SizeLow, Links, IndexHigh, IndexLow;
        }
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        internal static extern SafeFileHandle CreateFile(string name, uint access, uint share, IntPtr security, uint creation, uint flags, IntPtr template);
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        internal static extern bool CreateDirectory(string name, IntPtr security);
        [DllImport("kernel32.dll", SetLastError = true)]
        internal static extern bool GetFileInformationByHandle(SafeFileHandle handle, out Info info);
        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool SetFileInformationByHandle(SafeFileHandle handle, int kind, ref int info, uint size);
        internal static bool DeleteOwned(SafeFileHandle handle)
        {
            int delete = 1;
            return handle != null && !handle.IsInvalid && !handle.IsClosed
                && SetFileInformationByHandle(handle, 4, ref delete, 4);
        }
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern uint GetFinalPathNameByHandle(SafeFileHandle handle, StringBuilder path, uint length, uint flags);

        internal static string Final(SafeFileHandle handle)
        {
            var text = new StringBuilder(32768);
            uint length = GetFinalPathNameByHandle(handle, text, (uint)text.Capacity, 0);
            if (length == 0 || length >= text.Capacity) throw new BoundaryException();
            string path = text.ToString();
            if (!path.StartsWith(@"\\?\", StringComparison.Ordinal)) throw new BoundaryException();
            return path.Substring(4).TrimEnd('\\');
        }

        internal static void Check(SafeFileHandle handle, string expected, bool directory)
        {
            Info info;
            if (handle == null || handle.IsInvalid || !GetFileInformationByHandle(handle, out info)
                || (info.Attributes & Reparse) != 0 || ((info.Attributes & 16) != 0) != directory
                || (!directory && info.Links != 1)
                || !string.Equals(Final(handle), expected.TrimEnd('\\'), StringComparison.OrdinalIgnoreCase))
                throw new BoundaryException();
        }
    }

    internal sealed class DisposableRoot : IDisposable
    {
        private readonly List<SafeFileHandle> pins = new List<SafeFileHandle>();
        private readonly List<SafeFileHandle> files = new List<SafeFileHandle>();
        private SafeFileHandle rootHandle;
        private readonly string[] protectedRoots;
        private bool disposed;
        internal readonly string Root;

        // A component spelling check is conservative on purpose: no UNC,
        // device namespace, ADS, 8.3 aliases, dot segments or trailing aliases.
        internal static string Canonical(string path)
        {
            if (string.IsNullOrEmpty(path) || path.Length > 240 || path.Length < 3
                || !char.IsLetter(path[0]) || path[1] != ':' || path[2] != '\\'
                || path.IndexOf('/') >= 0 || path.IndexOf('~') >= 0 || path.IndexOf(':', 2) >= 0)
                throw new BoundaryException();
            foreach (string part in path.Substring(3).Split('\\'))
            {
                if (part.Length == 0 || part == "." || part == ".." || part.EndsWith(".", StringComparison.Ordinal)
                    || part.EndsWith(" ", StringComparison.Ordinal) || part.IndexOfAny(Path.GetInvalidFileNameChars()) >= 0)
                    throw new BoundaryException();
                string lower = part.ToLowerInvariant();
                if (lower == "appdata" || lower == "settings" || lower == "jobs" || lower == "runtime"
                    || lower == "program files" || lower == "program files (x86)" || lower == "windows")
                    throw new BoundaryException();
            }
            if (!string.Equals(Path.GetFullPath(path), path, StringComparison.OrdinalIgnoreCase)) throw new BoundaryException();
            return path;
        }

        internal static bool Overlaps(string first, string second)
        {
            first = first.TrimEnd('\\'); second = second.TrimEnd('\\');
            return string.Equals(first, second, StringComparison.OrdinalIgnoreCase)
                || first.StartsWith(second + "\\", StringComparison.OrdinalIgnoreCase)
                || second.StartsWith(first + "\\", StringComparison.OrdinalIgnoreCase);
        }

        // Factory never adopts an existing root. All ancestor directory handles
        // stay open without FILE_SHARE_DELETE, preventing rename/replacement.
        internal DisposableRoot(string designatedParent, string[] protectedPaths, SafeFileHandle designatedHandle = null)
        {
            if (protectedPaths == null || protectedPaths.Length == 0) throw new BoundaryException();
            designatedParent = Canonical(designatedParent);
            if (!Path.GetFileName(designatedParent).StartsWith("qa59-scratch-", StringComparison.Ordinal)
                || Path.GetFileName(designatedParent).Length != 45) throw new BoundaryException();
            foreach (char c in Path.GetFileName(designatedParent).Substring(13))
                if (!(c >= '0' && c <= '9') && !(c >= 'a' && c <= 'f')) throw new BoundaryException();
            protectedRoots = (string[])protectedPaths.Clone();
            foreach (string path in protectedRoots)
            {
                // Protected paths are compared lexically, never inspected.
                if (string.IsNullOrEmpty(path) || !Path.IsPathRooted(path)
                    || !string.Equals(Path.GetFullPath(path).TrimEnd('\\'), path.TrimEnd('\\'), StringComparison.OrdinalIgnoreCase)
                    || path.Contains("~") || path.Contains("/") || path.StartsWith(@"\\", StringComparison.Ordinal)
                    || Overlaps(designatedParent, path)) throw new BoundaryException();
            }
            Root = designatedParent + "\\" + SyntheticFixtures.RootPrefix + Guid.NewGuid().ToString("N");
            if (!SyntheticFixtures.ValidateRoot(Root, protectedRoots).Ok) throw new BoundaryException();
            try
            {
                string current = designatedParent.Substring(0, 3);
                Pin(current);
                foreach (string part in designatedParent.Substring(3).Split('\\'))
                {
                    current = Path.Combine(current, part);
                    if (current == designatedParent && designatedHandle != null)
                    {
                        WinFiles.Check(designatedHandle, current, true);
                        pins.Add(new SafeFileHandle(designatedHandle.DangerousGetHandle(), false));
                    }
                    else Pin(current);
                }
                var created = WinFiles.CreateOwnedDirectory(pins[pins.Count - 1], Path.GetFileName(Root));
                try { WinFiles.Check(created, Root, true); pins.Add(created); rootHandle = created; }
                catch { created.Dispose(); throw; }
            }
            catch { Dispose(); throw new BoundaryException(); }
        }

        private void Pin(string path)
        {
            var handle = WinFiles.CreateFile(path, 0x81, 1, IntPtr.Zero, 3, 0x02200000, IntPtr.Zero);
            try { WinFiles.Check(handle, path, true); pins.Add(handle); }
            catch { handle.Dispose(); throw; }
        }

        internal void Recheck()
        {
            if (disposed || pins.Count == 0) throw new BoundaryException();
            // Held handles deny directory replacement. Recheck root identity
            // through the same live handle before each operation.
            WinFiles.Check(pins[pins.Count - 1], Root, true);
        }

        internal void WriteRevision(char revision)
        {
            if (revision != 'A' && revision != 'B') throw new BoundaryException();
            Recheck();
            string settings = SyntheticFixtures.SettingsJson(Root, revision);
            string jobs = SyntheticFixtures.JobsJson(Root, revision);
            if (!SyntheticFixtures.ValidateSettings(settings, Root, revision, protectedRoots).Ok
                || !SyntheticFixtures.ValidateJobs(jobs, Root, revision, protectedRoots).Ok) throw new BoundaryException();
            // Fixed, newly created names only; no replacement of existing files.
            WriteNew("settings-" + revision + ".json", settings);
            WriteNew("jobs-" + revision + ".json", jobs);
        }

        private void WriteNew(string name, string text)
        {
            Recheck();
            string path = Root + "\\" + name;
            var handle = WinFiles.CreateFile(path, 0x40010080, 0, IntPtr.Zero, 1, 0x00200000, IntPtr.Zero);
            try
            {
                WinFiles.Check(handle, path, false);
                files.Add(handle); // hold exact identity, disallow rename/link/replacement
                using (var view = new SafeFileHandle(handle.DangerousGetHandle(), false))
                using (var stream = new FileStream(view, FileAccess.Write))
                {
                    byte[] bytes = new UTF8Encoding(false, true).GetBytes(text);
                    stream.Write(bytes, 0, bytes.Length);
                    stream.Flush(true);
                }
            }
            catch { if (!files.Contains(handle)) handle.Dispose(); throw new BoundaryException(); }
        }

        public void Dispose()
        {
            if (disposed) return;
            disposed = true;
            foreach (SafeFileHandle file in files) { WinFiles.DeleteOwned(file); file.Dispose(); }
            files.Clear();
            // Delete only identities we created, while ancestor pins still live.
            // Failure leaves a QA artifact; it never falls back to path deletion.
            if (rootHandle != null) WinFiles.DeleteOwned(rootHandle);
            for (int k = pins.Count - 1; k >= 0; k--) pins[k].Dispose();
            pins.Clear();
        }
    }
}
