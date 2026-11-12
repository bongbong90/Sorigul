# Shared read-only helpers for the V5 preservation baseline and observer.
# Windows PowerShell 5.1 compatible. All JSON is explicit UTF-8 without BOM.
$script:V5Utf8 = New-Object Text.UTF8Encoding($false)

function Get-V5Sha256([string]$Path) {
    $Stream = [IO.File]::Open($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
    try {
        $Hasher = [Security.Cryptography.SHA256]::Create()
        try { return ([BitConverter]::ToString($Hasher.ComputeHash($Stream))).Replace('-', '').ToLowerInvariant() }
        finally { $Hasher.Dispose() }
    } finally { $Stream.Dispose() }
}

function Read-V5Json([string]$Path) {
    return ([IO.File]::ReadAllText($Path, $script:V5Utf8) | ConvertFrom-Json)
}

function ConvertTo-V5JsonText($Value) {
    return (ConvertTo-Json -InputObject $Value -Depth 30)
}

# Create-new publication: a record that already exists is never overwritten.
function Write-V5JsonNew([string]$Path, $Value) {
    $Temp = $Path + '.' + [Guid]::NewGuid().ToString('N') + '.tmp'
    [IO.File]::WriteAllText($Temp, (ConvertTo-V5JsonText $Value), $script:V5Utf8)
    try { [IO.File]::Move($Temp, $Path) }
    catch { [IO.File]::Delete($Temp); throw }
}

# Replaceable pointer (heartbeat only).
function Write-V5JsonReplace([string]$Path, $Value) {
    $Temp = $Path + '.' + [Guid]::NewGuid().ToString('N') + '.tmp'
    [IO.File]::WriteAllText($Temp, (ConvertTo-V5JsonText $Value), $script:V5Utf8)
    if ([IO.File]::Exists($Path)) { [IO.File]::Replace($Temp, $Path, [NullString]::Value) } else { [IO.File]::Move($Temp, $Path) }
}

# Metadata inventory. Reparse entries are recorded but never traversed.
# $Exclude holds root-relative paths (top level only); $HashNames are hashed
# only when they sit directly under the root.
function Get-V5Inventory([string]$Root, [string[]]$Exclude = @(), [string[]]$HashNames = @()) {
    if ([IO.File]::Exists($Root)) { throw "ROOT_IS_FILE: $Root" }
    $Rows = New-Object 'Collections.Generic.List[object]'
    $Exists = [IO.Directory]::Exists($Root)
    if ($Exists) {
        $RootInfo = New-Object IO.DirectoryInfo($Root)
        if (($RootInfo.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "ROOT_REPARSE: $Root" }
        $Prefix = $Root.TrimEnd('\').Length + 1
        $Queue = New-Object 'Collections.Generic.Queue[IO.DirectoryInfo]'
        $Queue.Enqueue($RootInfo)
        while ($Queue.Count -gt 0) {
            $Parent = $Queue.Dequeue()
            # A subdirectory that vanished after it was listed contributes no children; its
            # entries then compare as REMOVED (blocking in protected scopes). The root and any
            # other error (e.g. access denied) still fail closed.
            try { $Children = $Parent.GetFileSystemInfos() }
            catch [IO.DirectoryNotFoundException] { if ($Parent.FullName -ceq $RootInfo.FullName) { throw }; continue }
            foreach ($Item in $Children) {
                $Relative = $Item.FullName.Substring($Prefix)
                if ($Exclude -contains $Relative) { continue }
                $Directory = ($Item.Attributes -band [IO.FileAttributes]::Directory) -ne 0
                $Reparse = ($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0
                $Row = [ordered]@{
                    path = $Relative; directory = $Directory; reparse = $Reparse
                    attributes = $Item.Attributes.ToString()
                    write_ticks = $Item.LastWriteTimeUtc.Ticks; creation_ticks = $Item.CreationTimeUtc.Ticks
                    size = $null; sha256 = $null
                }
                if (-not $Directory) { $Row.size = $Item.Length }
                if (-not $Directory -and -not $Reparse -and $Relative.IndexOf('\') -lt 0 -and $HashNames -contains $Item.Name) {
                    $Row.sha256 = Get-V5Sha256 $Item.FullName
                }
                $Rows.Add([pscustomobject]$Row)
                if ($Directory -and -not $Reparse) { $Queue.Enqueue([IO.DirectoryInfo]$Item) }
            }
        }
    }
    return [pscustomobject][ordered]@{ root = $Root; exists = $Exists; entries = @($Rows.ToArray()) }
}

function Get-V5EntrySignature($Entry) {
    return ('{0}|{1}|{2}|{3}|{4}|{5}|{6}' -f $Entry.directory, $Entry.reparse, $Entry.attributes, $Entry.write_ticks, $Entry.creation_ticks, $Entry.size, $Entry.sha256)
}

# Path-keyed map. NTFS names are case-insensitive, so a case-only duplicate is a
# collision; the caller treats a collision as HOLD (blocking).
function ConvertTo-V5EntryMap($Entries, [ref]$Collisions) {
    $Map = New-Object 'Collections.Generic.Dictionary[string,object]' ([StringComparer]::OrdinalIgnoreCase)
    $Found = New-Object 'Collections.Generic.List[string]'
    foreach ($Entry in @($Entries)) {
        if ($null -eq $Entry) { continue }
        if ($Map.ContainsKey($Entry.path)) { $Found.Add([string]$Entry.path); continue }
        $Map.Add([string]$Entry.path, $Entry)
    }
    $Collisions.Value = @($Found.ToArray())
    return $Map
}

# NTFS file identity (volume serial + file index). The handle is opened with no data
# access and does not follow reparse points, so no content is read. A replacement keeps
# the name and can keep size and all timestamps (file tunneling) but never the file index.
if (-not ('SorigulV5.FileId' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;
namespace SorigulV5 {
    public static class FileId {
        // BY_HANDLE_FILE_INFORMATION: FILETIME is 4-byte aligned, so no padding after Attributes.
        [StructLayout(LayoutKind.Sequential, Pack = 4)]
        struct Info { public uint Attributes; public long Created, Accessed, Written; public uint Volume, SizeHigh, SizeLow, Links, IndexHigh, IndexLow; }
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        static extern SafeFileHandle CreateFileW(string name, uint access, uint share, IntPtr security, uint disposition, uint flags, IntPtr template);
        [DllImport("kernel32.dll", SetLastError = true)]
        static extern bool GetFileInformationByHandle(SafeFileHandle handle, out Info info);
        public static string Get(string path) {
            using (SafeFileHandle handle = CreateFileW(@"\\?\" + path, 0, 7, IntPtr.Zero, 3, 0x02000000 | 0x00200000, IntPtr.Zero)) {
                if (handle.IsInvalid) throw new Win32Exception(Marshal.GetLastWin32Error(), path);
                Info info;
                if (!GetFileInformationByHandle(handle, out info)) throw new Win32Exception(Marshal.GetLastWin32Error(), path);
                return info.Volume.ToString("x8") + ":" + info.IndexHigh.ToString("x8") + info.IndexLow.ToString("x8");
            }
        }
    }
}
'@
}
function Get-V5FileId([string]$Path) { return [SorigulV5.FileId]::Get($Path) }

function Get-V5InstalledRegistration {
    $Installed = @()
    foreach ($Key in @('HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall', 'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall', 'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall')) {
        if (Test-Path -LiteralPath $Key) {
            $Installed += @(Get-ItemProperty -Path ($Key + '\*') | Where-Object { $_.PSObject.Properties.Name -contains 'DisplayName' -and $_.DisplayName -match 'Sorigul' } |
                ForEach-Object { [ordered]@{ PSChildName = $_.PSChildName; DisplayName = $_.DisplayName; DisplayVersion = $_.DisplayVersion; InstallLocation = $_.InstallLocation; WindowsInstaller = $_.WindowsInstaller } })
        }
    }
    return (ConvertTo-Json -InputObject @($Installed) -Compress)
}
