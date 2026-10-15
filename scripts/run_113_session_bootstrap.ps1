#Requires -Version 5.1
<# #164: repository-owned bootstrap; Probe never activates an artifact session. #>
[CmdletBinding()]
param(
    [ValidateSet('Probe', 'Start', 'Guard', 'Status', 'Stop', 'Freeze')][string]$Mode = 'Probe',
    [string]$ExpectedBranch,
    [string]$ExpectedHead,
    [string]$FreezeFile,
    [string]$EvidenceRoot,
    [string]$SessionPath,
    [ValidateRange(3, 120)][int]$StableSeconds = 6
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
# JSON is an explicit PS5 capability, never an assumption about module discovery.
# Do not reconstruct PSModulePath, PATH, SystemRoot or the child's environment.
$NativeModules = [IO.Path]::Combine([Environment]::SystemDirectory, 'WindowsPowerShell\v1.0\Modules')
Import-Module ([IO.Path]::Combine($NativeModules, 'Microsoft.PowerShell.Utility\Microsoft.PowerShell.Utility.psd1')) -ErrorAction Stop
Import-Module ([IO.Path]::Combine($NativeModules, 'Microsoft.PowerShell.Management\Microsoft.PowerShell.Management.psd1')) -ErrorAction Stop
Add-Type -AssemblyName System.Management
$Repository = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$ScriptPath = $PSCommandPath
$PowerShell = Join-Path ([Environment]::SystemDirectory) 'WindowsPowerShell\v1.0\powershell.exe'
$Git = (Get-Command git.exe -CommandType Application -ErrorAction Stop).Source
$Utf8 = New-Object Text.UTF8Encoding($false)
[Console]::OutputEncoding = $Utf8

function Write-AtomicJson([string]$Path, $Value) {
    $Temporary = $Path + '.' + [Guid]::NewGuid().ToString('N') + '.tmp'
    try {
        [IO.File]::WriteAllText($Temporary, ($Value | ConvertTo-Json -Depth 30), $Utf8)
        for ($Attempt = 0; $Attempt -lt 10; $Attempt++) {
            try {
                if ([IO.File]::Exists($Path)) { [IO.File]::Replace($Temporary, $Path, [System.Management.Automation.Language.NullString]::Value) }
                else { [IO.File]::Move($Temporary, $Path) }
                break
            } catch [IO.IOException] {
                if (($_.Exception.HResult -band 65535) -notin @(32, 33) -or $Attempt -eq 9) { throw }
                [Threading.Thread]::Sleep(20)
            }
        }
    } finally { if ([IO.File]::Exists($Temporary)) { [IO.File]::Delete($Temporary) } }
}
function Read-Json([string]$Path, [switch]$RetryMissing) {
    # Atomic replacement needs readers to permit delete/rename of the old inode.
    # File.Replace has a transient not-found (Win32 2) gap; only a caller that
    # reads a guard-rewritten file opts in. Missing evidence elsewhere fails fast.
    $Stream = $null
    for ($Attempt = 0; $Attempt -lt 10; $Attempt++) {
        try { $Stream = [IO.File]::Open($Path, 'Open', 'Read', ([IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete)); break }
        catch [IO.IOException] {
            $NativeCode = $_.Exception.HResult -band 65535
            $Retryable = $NativeCode -in @(32, 33) -or ($RetryMissing -and $NativeCode -eq 2)
            if (-not $Retryable -or $Attempt -eq 9) { throw }
            [Threading.Thread]::Sleep(20)
        }
    }
    $Reader = New-Object IO.StreamReader($Stream, $Utf8)
    try { return ($Reader.ReadToEnd() | ConvertFrom-Json) }
    finally { $Reader.Dispose() }
}
function Invoke-Git([string]$Arguments) {
    $Info = New-Object Diagnostics.ProcessStartInfo
    $Info.FileName = $Git
    $Info.Arguments = '-c core.quotepath=false ' + $Arguments
    $Info.WorkingDirectory = $Repository
    $Info.UseShellExecute = $false
    $Info.CreateNoWindow = $true
    $Info.RedirectStandardOutput = $true
    $Info.RedirectStandardError = $true
    $Info.StandardOutputEncoding = $Utf8
    $Process = [Diagnostics.Process]::Start($Info)
    try {
        $Output = $Process.StandardOutput.ReadToEndAsync()
        $Errors = $Process.StandardError.ReadToEndAsync()
        if (-not $Process.WaitForExit(15000)) { $Process.Kill(); $Process.WaitForExit(); throw 'Git observation timed out' }
        if ($Process.ExitCode -ne 0) { throw ('Git observation failed: ' + $Arguments + ': ' + $Errors.Result) }
        return $Output.Result.TrimEnd("`r", "`n")
    } finally { $Process.Dispose() }
}
function Get-Sha256([string]$Path) {
    $Hasher = [Security.Cryptography.SHA256]::Create()
    $Stream = $null
    try {
        $Stream = [IO.File]::Open($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
        return ([BitConverter]::ToString($Hasher.ComputeHash($Stream))).Replace('-', '').ToLowerInvariant()
    } finally { if ($null -ne $Stream) { $Stream.Dispose() }; $Hasher.Dispose() }
}
function Assert-Capabilities {
    if ($PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSEdition -cne 'Desktop') { throw 'Windows PS5 Desktop required' }
    $Hasher = [Security.Cryptography.SHA256]::Create()
    try {
        $Actual = ([BitConverter]::ToString($Hasher.ComputeHash([Text.Encoding]::ASCII.GetBytes('abc')))).Replace('-', '').ToLowerInvariant()
        if ($Actual -cne 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad') { throw 'SHA256 capability failed' }
    } finally { $Hasher.Dispose() }
    return @{ powershell = $PSVersionTable.PSVersion.ToString(); edition = $PSVersionTable.PSEdition; hashing = '.NET SHA256'; script_sha256 = (Get-Sha256 $ScriptPath) }
}
function Assert-Source($Config, [switch]$Live) {
    $Branch = Invoke-Git 'branch --show-current'
    $Head = Invoke-Git 'rev-parse HEAD'
    $Upstream = Invoke-Git 'rev-parse @{u}'
    if ($Branch -cne $Config.branch -or $Head -cne $Config.head -or $Upstream -cne $Config.head) { throw 'Source identity drift: branch/HEAD/upstream' }
    if ((Invoke-Git 'status --porcelain --untracked-files=no').Length -ne 0) { throw 'Tracked tree/index dirty' }
    if ($Live) {
        if ($Branch -notmatch '^[A-Za-z0-9_./-]+$') { throw 'Unsafe branch reference' }
        $Remote = Invoke-Git ("config --get branch.$Branch.remote")
        $Ref = Invoke-Git ("config --get branch.$Branch.merge")
        if ($Remote -notmatch '^[A-Za-z0-9_.-]+$' -or $Ref -notmatch '^refs/heads/[A-Za-z0-9_./-]+$') { throw 'Unsafe/missing upstream reference' }
        $RemoteHead = Invoke-Git "ls-remote --exit-code $Remote $Ref"
        if (($RemoteHead -split '\s+')[0] -cne $Config.head) { throw 'Live upstream identity mismatch' }
    }
    return @{ branch = $Branch; head = $Head; upstream = $Upstream; tracked = 'CLEAN'; live_checked = [bool]$Live }
}
function Assert-ReleaseInputs($Config) {
    $Names = @((Invoke-Git 'ls-files') -split "`n")
    $Properties = @($Config.release_input_sha256.PSObject.Properties)
    if ($Names.Count -ne $Properties.Count) { throw 'Release input inventory mismatch' }
    foreach ($Name in $Names) {
        $Property = $Properties | Where-Object Name -CEQ $Name
        if ($null -eq $Property -or (Get-Sha256 (Join-Path $Repository $Name)) -cne $Property.Value) { throw "Release input SHA256 mismatch: $Name" }
    }
}
function Assert-ProcessPort {
    # Read-only native observation; never terminate unrelated processes.
    $Searcher = New-Object System.Management.ManagementObjectSearcher('SELECT Name,ProcessId,CommandLine FROM Win32_Process')
    try {
        foreach ($Process in $Searcher.Get()) {
            if ([string]$Process.Name -match '^(sorigul.*|ffmpeg|whisper.*|uvicorn|pyinstaller|cargo|rustc|msiexec)\.exe$' -or
                ([string]$Process.Name -match '^python.*\.exe$' -and [string]$Process.CommandLine -match 'uvicorn|local_runtime_main|PyInstaller|backend[\\/]src[\\/]main\.py')) {
                throw ('Target process precondition failed: ' + $Process.Name + ' pid=' + $Process.ProcessId)
            }
        }
    } finally { $Searcher.Dispose() }
    foreach ($Endpoint in [Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners()) {
        if ($Endpoint.Port -eq 8000) { throw 'TCP 8000 is occupied' }
    }
}
function Get-ProtectedInventory([string]$Root, [string[]]$Exclude = @(), [bool]$HashState = $false) {
    $Rows = New-Object 'Collections.Generic.List[object]'
    $Exists = [IO.Directory]::Exists($Root)
    if ([IO.File]::Exists($Root)) { throw "Protected root is a file: $Root" }
    if ($Exists) {
        $RootInfo = New-Object IO.DirectoryInfo($Root)
        if (($RootInfo.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "Protected root is a reparse point: $Root" }
        $Queue = New-Object 'Collections.Generic.Queue[System.IO.DirectoryInfo]'
        $Queue.Enqueue($RootInfo)
        while ($Queue.Count -gt 0) {
            foreach ($Item in ($Queue.Dequeue().GetFileSystemInfos() | Sort-Object Name)) {
                if ($Item.Name -in $Exclude) { continue }
                $Directory = ($Item.Attributes -band [IO.FileAttributes]::Directory) -ne 0
                $Reparse = ($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0
                $Row = [ordered]@{ path = $Item.FullName.Substring($Root.TrimEnd('\').Length + 1); directory = $Directory; reparse = $Reparse; attributes = $Item.Attributes.ToString(); write_ticks = $Item.LastWriteTimeUtc.Ticks }
                if (-not $Directory) { $Row.size = $Item.Length }
                if ($HashState -and -not $Directory -and -not $Reparse -and $Item.Name -in @('settings.json', 'jobs.json')) { $Row.sha256 = Get-Sha256 $Item.FullName }
                $Rows.Add($Row)
                if ($Directory -and -not $Reparse) { $Queue.Enqueue($Item) }
            }
        }
    }
    return [ordered]@{ root = $Root; exists = $Exists; entries = @($Rows.ToArray()); policy = 'metadata only; settings/jobs SHA256; no media/model/auth content reads; no reparse traversal' }
}
function Get-ProtectedBaseline {
    $App = Join-Path $env:LOCALAPPDATA 'Sorigul'
    $Roots = @(
        (Get-ProtectedInventory $App @('runtime') $true),
        (Get-ProtectedInventory (Join-Path $env:LOCALAPPDATA 'com.sorigul.desktop')),
        (Get-ProtectedInventory (Join-Path $env:APPDATA 'Sorigul')),
        (Get-ProtectedInventory (Join-Path $env:APPDATA 'com.sorigul.desktop')),
        (Get-ProtectedInventory (Join-Path $env:USERPROFILE '.cache\whisper')),
        (Get-ProtectedInventory (Join-Path $App 'auth')),
        (Get-ProtectedInventory (Join-Path $App 'logs')),
        (Get-ProtectedInventory (Join-Path $App 'results')),
        (Get-ProtectedInventory (Join-Path $env:LOCALAPPDATA 'Packages\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\LocalCache\Local\Sorigul') @('runtime') $true)
    )
    $Settings = Join-Path $App 'settings.json'
    if ([IO.File]::Exists($Settings)) {
        $Value = Read-Json $Settings
        if ($Value.PSObject.Properties.Name -contains 'transcription_folder' -and $Value.transcription_folder) {
            $Roots += Get-ProtectedInventory $Value.transcription_folder
        }
    }
    return $Roots
}
function Test-LockDenied([string]$Path) {
    $Stream = $null
    try { $Stream = [IO.File]::Open($Path, 'OpenOrCreate', 'ReadWrite', 'None'); return $false }
    catch [IO.IOException] { return $true }
    finally { if ($null -ne $Stream) { $Stream.Dispose() } }
}
function Get-GuardProcess($Config) {
    $Owner = Read-Json (Join-Path $Config.session 'GUARD_OWNER.json')
    if ($Owner.token -cne $Config.token) { throw 'Guard owner token mismatch' }
    $Process = [Diagnostics.Process]::GetProcessById($Owner.pid)
    if ($Process.HasExited -or $Process.StartTime.ToUniversalTime().Ticks.ToString() -cne $Owner.start_ticks) { $Process.Dispose(); throw 'Single Writer lost (PID/start identity)' }
    return $Process
}
function Assert-Healthy($Config) {
    if ([IO.File]::Exists((Join-Path $Config.session 'SESSION_INVALID.json'))) { throw 'Guard invalidated session' }
    $Process = Get-GuardProcess $Config
    try {
        $Heartbeat = Read-Json (Join-Path $Config.session 'LOCK_HEARTBEAT.json') -RetryMissing
        if ($Heartbeat.token -cne $Config.token -or $Heartbeat.pid -ne $Process.Id -or
            ([DateTime]::UtcNow - [DateTime]::Parse($Heartbeat.at_utc)).TotalSeconds -gt 10 -or
            -not (Test-LockDenied $Config.lock_path)) { throw 'Guard heartbeat/lock health failed' }
        return $Heartbeat
    } finally { $Process.Dispose() }
}
function Stop-OwnedGuard($Config, $Child = $null) {
    Write-AtomicJson (Join-Path $Config.session 'STOP_REQUEST.json') @{ token = $Config.token }
    $Process = $Child
    if ($null -eq $Process -and [IO.File]::Exists((Join-Path $Config.session 'GUARD_OWNER.json'))) {
        try { $Process = Get-GuardProcess $Config } catch [ArgumentException] { } catch [InvalidOperationException] { }
    }
    if ($null -ne $Process) {
        try {
            if (-not $Process.WaitForExit(20000)) { $Process.Kill(); $Process.WaitForExit(); throw 'Controlled stop timed out; owned child terminated' }
        } finally { $Process.Dispose() }
    }
    if (Test-LockDenied $Config.lock_path) { throw 'Cleanup lock release failed' }
}
function Write-Invalid($Config, [string]$Reason) {
    # Preserve the first causal failure rather than overwrite it during cleanup.
    if ([IO.File]::Exists((Join-Path $Config.session 'SESSION_INVALID.json'))) { return }
    $Active = [IO.File]::Exists((Join-Path $Config.session 'SESSION_ACTIVE.json'))
    Write-AtomicJson (Join-Path $Config.session 'SESSION_INVALID.json') @{ token = $Config.token; at_utc = [DateTime]::UtcNow.ToString('o'); reason = $Reason; state = $(if ($Active) { 'HARD_STOP' } else { 'BOOTSTRAP_FAILED' }); artifact_session_started = $Active }
}

if ($Mode -eq 'Freeze') {
    $null = Assert-Capabilities
    if (-not $FreezeFile -or [IO.File]::Exists($FreezeFile)) { throw 'FreezeFile must be a new output file' }
    if (-not $ExpectedBranch) { $ExpectedBranch = Invoke-Git 'branch --show-current' }
    if (-not $ExpectedHead) { $ExpectedHead = Invoke-Git 'rev-parse HEAD' }
    $Identity = [pscustomobject]@{ branch = $ExpectedBranch; head = $ExpectedHead }
    $null = Assert-Source $Identity -Live
    $Inputs = [ordered]@{}
    foreach ($Name in ((Invoke-Git 'ls-files') -split "`n")) { $Inputs[$Name] = Get-Sha256 (Join-Path $Repository $Name) }
    $Freeze = [pscustomobject]@{ branch = $ExpectedBranch; head = $ExpectedHead; tree = (Invoke-Git 'rev-parse HEAD^{tree}'); release_input_sha256 = [pscustomobject]$Inputs; at_utc = [DateTime]::UtcNow.ToString('o') }
    Assert-ReleaseInputs $Freeze
    $null = Assert-Source $Identity -Live
    Write-AtomicJson $FreezeFile $Freeze
    Write-Host "EXACT SOURCE FREEZE = PASS; HEAD=$ExpectedHead"
    exit 0
}

if ($Mode -eq 'Guard') {
    $Config = Read-Json (Join-Path $SessionPath 'SESSION_BOOTSTRAPPING.json')
    $Lock = $null
    try {
        $Capability = Assert-Capabilities
        $Lock = [IO.File]::Open($Config.lock_path, 'OpenOrCreate', 'ReadWrite', 'None')
        $Bytes = $Utf8.GetBytes($Config.token)
        $Lock.SetLength(0); $Lock.Write($Bytes, 0, $Bytes.Length); $Lock.Flush()
        $Self = [Diagnostics.Process]::GetCurrentProcess()
        try { $Ticks = $Self.StartTime.ToUniversalTime().Ticks.ToString() } finally { $Self.Dispose() }
        Write-AtomicJson (Join-Path $SessionPath 'GUARD_OWNER.json') @{ token = $Config.token; pid = $PID; start_ticks = $Ticks; capabilities = $Capability; environment = @{ PSModulePath = $env:PSModulePath; SystemRoot = $env:SystemRoot; PATH = $env:PATH } }
        $Sequence = 0
        $LastLive = [DateTime]::MinValue
        while ($true) {
            if ([IO.File]::Exists((Join-Path $SessionPath 'SESSION_INVALID.json'))) { throw 'Session invalidated by canonical Status/bootstrap' }
            $Live = ([DateTime]::UtcNow - $LastLive).TotalSeconds -ge 30
            $Observation = Assert-Source $Config -Live:$Live
            if ($Live) { $LastLive = [DateTime]::UtcNow }
            # Read back the held stream token; exclusive Windows handle owns the lock.
            $Lock.Position = 0; $Read = New-Object byte[] $Bytes.Length
            if ($Lock.Read($Read, 0, $Read.Length) -ne $Bytes.Length -or $Utf8.GetString($Read) -cne $Config.token) { throw 'Lock ownership lost' }
            $Sequence++
            Write-AtomicJson (Join-Path $SessionPath 'LOCK_HEARTBEAT.json') @{ token = $Config.token; pid = $PID; sequence = $Sequence; at_utc = [DateTime]::UtcNow.ToString('o'); observation = $Observation; last_live_utc = $LastLive.ToString('o') }
            $Stop = Join-Path $SessionPath 'STOP_REQUEST.json'
            if ([IO.File]::Exists($Stop)) {
                if ((Read-Json $Stop).token -cne $Config.token) { throw 'Stop token mismatch' }
                Write-AtomicJson (Join-Path $SessionPath 'SESSION_STOPPED.json') @{ token = $Config.token; at_utc = [DateTime]::UtcNow.ToString('o'); controlled = $true; was_active = [IO.File]::Exists((Join-Path $SessionPath 'SESSION_ACTIVE.json')) }
                break
            }
            $Request = Join-Path $SessionPath 'ACTIVATE_REQUEST.json'
            $ActivePath = Join-Path $SessionPath 'SESSION_ACTIVE.json'
            if ([IO.File]::Exists($Request) -and -not [IO.File]::Exists($ActivePath)) {
                $Activation = Read-Json $Request
                if ($Config.probe -or $Activation.token -cne $Config.token) { throw 'Activation forbidden/token mismatch' }
                $null = Assert-Source $Config -Live
                Assert-ReleaseInputs $Config
                Assert-ProcessPort
                $BaselinePath = Join-Path $SessionPath 'PROTECTED_USER_DATA_BASELINE.json'
                if ((Get-Sha256 $BaselinePath) -cne $Activation.baseline_sha256) { throw 'Protected baseline identity changed' }
                if ((Get-ProtectedBaseline | ConvertTo-Json -Depth 30 -Compress) -cne ((Read-Json $BaselinePath).roots | ConvertTo-Json -Depth 30 -Compress)) { throw 'Protected baseline changed before activation' }
                Write-AtomicJson $ActivePath @{ state = 'ACTIVE'; run_id = $Config.run_id; token = $Config.token; guard_pid = $PID; source_head = $Config.head; branch = $Config.branch; at_utc = [DateTime]::UtcNow.ToString('o'); baseline_sha256 = $Activation.baseline_sha256; release_input_sha256 = $Config.release_input_sha256 }
            }
            # A crashed bootstrap parent cannot leave a provisional guard behind.
            if (-not [IO.File]::Exists($ActivePath)) {
                $Parent = [Diagnostics.Process]::GetProcessById($Config.parent_pid)
                try {
                    if ($Parent.HasExited -or $Parent.StartTime.ToUniversalTime().Ticks.ToString() -cne $Config.parent_start_ticks -or
                        ([DateTime]::UtcNow - [DateTime]::Parse($Config.at_utc)).TotalSeconds -gt 180) { throw 'Bootstrap parent lost/lease expired' }
                } finally { $Parent.Dispose() }
            }
            [Threading.Thread]::Sleep(1000)
        }
    } catch { Write-Invalid $Config $_.Exception.Message; exit 1 }
    finally { if ($null -ne $Lock) { $Lock.Dispose() } }
    exit 0
}

if ($Mode -in @('Status', 'Stop')) {
    if (-not $SessionPath) { throw 'SessionPath is required' }
    $Config = Read-Json (Join-Path $SessionPath 'SESSION_BOOTSTRAPPING.json')
    try {
        if ($Mode -eq 'Stop') {
            $null = Assert-Healthy $Config
            Stop-OwnedGuard $Config
            Write-Host 'CONTROLLED STOP = PASS; LOCK RELEASE = PASS; ORPHAN = 0'
        } else {
            if ([IO.File]::Exists((Join-Path $SessionPath 'SESSION_STOPPED.json'))) { throw 'Session is stopped' }
            $null = Assert-Healthy $Config
            $null = Assert-Source $Config -Live
            if ([IO.File]::Exists((Join-Path $SessionPath 'SESSION_ACTIVE.json'))) {
                Assert-ReleaseInputs $Config
                $null = Assert-Healthy $Config
                Write-Host '#113 ARTIFACT SESSION = ACTIVE'
            } else { Write-Host 'BOOTSTRAPPING / ARTIFACT SESSION NOT STARTED' }
        }
    } catch { Write-Invalid $Config $_.Exception.Message; throw }
    exit 0
}

$Child = $null
$Config = $null
try {
    $null = Assert-Capabilities
    if ($Mode -eq 'Start' -and (-not $ExpectedBranch -or $ExpectedHead -notmatch '^[a-f0-9]{40}$' -or -not $FreezeFile -or -not $EvidenceRoot)) { throw 'Start requires exact ExpectedBranch, ExpectedHead, FreezeFile and EvidenceRoot' }
    if (-not $ExpectedBranch) { $ExpectedBranch = Invoke-Git 'branch --show-current' }
    if (-not $ExpectedHead) { $ExpectedHead = Invoke-Git 'rev-parse HEAD' }
    $Identity = [pscustomobject]@{ branch = $ExpectedBranch; head = $ExpectedHead }
    $null = Assert-Source $Identity -Live
    $Inputs = $null
    if ($Mode -eq 'Start') {
        $Freeze = Read-Json $FreezeFile
        if ($Freeze.head -cne $ExpectedHead -or $Freeze.branch -cne $ExpectedBranch) { throw 'Freeze identity mismatch' }
        $Inputs = $Freeze.release_input_sha256
        Assert-ReleaseInputs ([pscustomobject]@{ release_input_sha256 = $Inputs })
        Assert-ProcessPort
    }
    $Token = [Guid]::NewGuid().ToString('N')
    if ($Mode -eq 'Probe') {
        $RunId = $null
        $SessionPath = Join-Path ([IO.Path]::GetTempPath()) ('Sorigul_113_Probe_' + $Token)
        $LockPath = Join-Path $SessionPath 'probe.lock'
    } else {
        $RunId = 'Sorigul_' + [TimeZoneInfo]::ConvertTimeBySystemTimeZoneId([DateTime]::UtcNow, 'Korea Standard Time').ToString('yyyyMMdd') + '_' + $ExpectedHead.Substring(0, 7) + '_' + $Token.Substring(0, 12)
        $SessionPath = Join-Path $EvidenceRoot $RunId
        $GitDirectory = Invoke-Git 'rev-parse --git-common-dir'
        if (-not [IO.Path]::IsPathRooted($GitDirectory)) { $GitDirectory = Join-Path $Repository $GitDirectory }
        $LockPath = Join-Path $GitDirectory 'sorigul-113-single-writer.lock'
        if (Test-LockDenied $LockPath) { throw 'Single Writer lock already held' }
    }
    if ([IO.Directory]::Exists($SessionPath) -or [IO.File]::Exists($SessionPath)) { throw 'Evidence namespace already exists' }
    $null = [IO.Directory]::CreateDirectory($SessionPath)
    $Self = [Diagnostics.Process]::GetCurrentProcess()
    try { $ParentTicks = $Self.StartTime.ToUniversalTime().Ticks.ToString() } finally { $Self.Dispose() }
    $Config = [ordered]@{ state = 'BOOTSTRAPPING'; probe = ($Mode -eq 'Probe'); run_id = $RunId; token = $Token; session = $SessionPath; lock_path = $LockPath; branch = $ExpectedBranch; head = $ExpectedHead; release_input_sha256 = $Inputs; at_utc = [DateTime]::UtcNow.ToString('o'); parent_pid = $PID; parent_start_ticks = $ParentTicks }
    Write-AtomicJson (Join-Path $SessionPath 'SESSION_BOOTSTRAPPING.json') $Config
    $Config = Read-Json (Join-Path $SessionPath 'SESSION_BOOTSTRAPPING.json')
    # Serialize data into EncodedCommand, keeping spaces/Unicode/quotes intact.
    $Command = "& '" + $ScriptPath.Replace("'", "''") + "' -Mode Guard -SessionPath '" + $SessionPath.Replace("'", "''") + "'"
    $Info = New-Object Diagnostics.ProcessStartInfo
    $Info.FileName = $PowerShell
    $Info.Arguments = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand ' + [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($Command))
    $Info.WorkingDirectory = $Repository
    # A hidden, independent Windows console avoids .NET Framework's inheritance
    # of the caller's capture handles. Keep the complete inherited environment.
    $Info.UseShellExecute = $true
    $Info.WindowStyle = [Diagnostics.ProcessWindowStyle]::Hidden
    # No environment clearing: Bypass is scoped to the guard harness child only.
    $Child = [Diagnostics.Process]::Start($Info)
    $Timer = [Diagnostics.Stopwatch]::StartNew()
    $FirstHealthy = $null
    $Sequences = New-Object 'Collections.Generic.HashSet[int]'
    $Denied = $false
    while ($Timer.Elapsed.TotalSeconds -lt ($StableSeconds + 35)) {
        if ($Child.HasExited) { throw 'Guard child early exit' }
        if ([IO.File]::Exists((Join-Path $SessionPath 'LOCK_HEARTBEAT.json'))) {
            $Heartbeat = Assert-Healthy $Config
            $null = $Sequences.Add([int]$Heartbeat.sequence)
            if ($null -eq $FirstHealthy) { $FirstHealthy = $Timer.Elapsed.TotalSeconds }
            $Denied = Test-LockDenied $LockPath
            if ($Sequences.Count -ge 3 -and $Timer.Elapsed.TotalSeconds - $FirstHealthy -ge $StableSeconds) { break }
        }
        [Threading.Thread]::Sleep(200)
    }
    if ($Sequences.Count -lt 3 -or -not $Denied -or $null -eq $FirstHealthy -or $Timer.Elapsed.TotalSeconds - $FirstHealthy -lt $StableSeconds) { throw 'Guard stabilization/competing denial failed' }
    if ($Mode -eq 'Probe') {
        $Owner = Read-Json (Join-Path $SessionPath 'GUARD_OWNER.json')
        Stop-OwnedGuard $Config $Child
        $Child = $null
        $Stopped = Read-Json (Join-Path $SessionPath 'SESSION_STOPPED.json')
        if (-not $Stopped.controlled -or $Stopped.was_active -or [IO.File]::Exists((Join-Path $SessionPath 'SESSION_ACTIVE.json'))) { throw 'Probe lifecycle contract failed' }
        $Result = @{ verdict = 'PASS'; probe_only = $true; guard_pid = $Owner.pid; guard_start = 'PASS'; heartbeats = $Sequences.Count; competing_acquisition = 'DENIED'; monitored_source = 'PASS'; controlled_stop = 'PASS'; lock_release = 'PASS'; orphan = 0; hashing = $Owner.capabilities; evidence = $SessionPath }
        Write-AtomicJson (Join-Path $SessionPath 'PROBE_RESULT.json') $Result
        $Result | ConvertTo-Json -Depth 6
        Write-Host 'CANONICAL SINGLE WRITER BOOTSTRAP PROBE: PASS'
    } else {
        $Baseline = @{ at_utc = [DateTime]::UtcNow.ToString('o'); roots = @(Get-ProtectedBaseline) }
        $BaselinePath = Join-Path $SessionPath 'PROTECTED_USER_DATA_BASELINE.json'
        Write-AtomicJson $BaselinePath $Baseline
        $null = Assert-Source $Config -Live
        Assert-ReleaseInputs $Config
        Assert-ProcessPort
        $null = Assert-Healthy $Config
        Write-AtomicJson (Join-Path $SessionPath 'ACTIVATE_REQUEST.json') @{ token = $Token; baseline_sha256 = (Get-Sha256 $BaselinePath) }
        $ActivationTimer = [Diagnostics.Stopwatch]::StartNew()
        while (-not [IO.File]::Exists((Join-Path $SessionPath 'SESSION_ACTIVE.json'))) {
            $null = Assert-Healthy $Config
            if ($ActivationTimer.Elapsed.TotalSeconds -gt 60) { throw 'Activation timed out' }
            [Threading.Thread]::Sleep(200)
        }
        $Healthy = Assert-Healthy $Config
        Write-Host '#113 ARTIFACT SESSION = ACTIVE'
        Write-Host "run_id=$RunId"
        Write-Host "guard_pid=$($Healthy.pid)"
        Write-Host "session_path=$SessionPath"
        $Child.Dispose(); $Child = $null
    }
} catch {
    $Reason = $_.Exception.Message
    if ($null -ne $Config) {
        Write-Invalid $Config $Reason
        try { Stop-OwnedGuard $Config $Child; $Child = $null } catch { $Reason += '; cleanup: ' + $_.Exception.Message }
    }
    if ($null -ne $Config -and [IO.File]::Exists((Join-Path $SessionPath 'SESSION_ACTIVE.json'))) { Write-Host 'SINGLE WRITER LOSS / HARD STOP' }
    else { Write-Host 'BOOTSTRAP FAILED / ARTIFACT SESSION NOT STARTED' }
    Write-Error $Reason
    exit 1
}
