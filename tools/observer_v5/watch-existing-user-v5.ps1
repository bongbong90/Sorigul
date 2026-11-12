# Normal-user observer for a V5 preservation baseline.
# Keeps the original contract: OBSERVER_HEARTBEAT.json (pid, start_ticks, sequence,
# at_utc), OBSERVER_STOP_REQUIRED.json on any blocking change, OBSERVER_STOP_REQUEST.json
# to end, OBSERVER_STOPPED.json on a controlled end. V5 adds: baseline path/SHA as
# arguments, path-keyed comparison, Downloads registered/unregistered split, append-only
# raw diffs, and a final full scan bound to the stop-request nonce.
param(
    [Parameter(Mandatory = $true)][string]$BaselinePath,
    [Parameter(Mandatory = $true)][string]$BaselineSha256,
    [Parameter(Mandatory = $true)][string]$StateDir,
    [int]$IntervalSeconds = 15
)
$ErrorActionPreference = 'Stop'
. ([scriptblock]::Create([IO.File]::ReadAllText((Join-Path $PSScriptRoot 'observer-v5-common.ps1'), (New-Object Text.UTF8Encoding($false)))))

$StopRequired = Join-Path $StateDir 'OBSERVER_STOP_REQUIRED.json'
$StopRequest = Join-Path $StateDir 'OBSERVER_STOP_REQUEST.json'
$RawDir = Join-Path $StateDir 'raw'
$Self = [Diagnostics.Process]::GetCurrentProcess()
$StartTicks = $Self.StartTime.ToUniversalTime().Ticks.ToString()
$Sequence = 0

function Write-StopRequired($Record) {
    $Record.pid = $PID; $Record.sequence = $Sequence; $Record.at_utc = [DateTime]::UtcNow.ToString('o')
    $Path = $StopRequired
    if ([IO.File]::Exists($Path)) { $Path = Join-Path $StateDir ('OBSERVER_STOP_REQUIRED_' + [Guid]::NewGuid().ToString('N') + '.json') }
    Write-V5JsonNew $Path $Record
}

function Compare-V5Root($Base, $Current, $Blocking, $Noncore) {
    if ([bool]$Base.exists -ne [bool]$Current.exists) { $Blocking.Add([pscustomobject]@{ root = $Base.root; kind = 'ROOT_PRESENCE'; before = $Base.exists; after = $Current.exists }); return }
    $C1 = $null; $C2 = $null
    $Old = ConvertTo-V5EntryMap $Base.entries ([ref]$C1)
    $New = ConvertTo-V5EntryMap $Current.entries ([ref]$C2)
    foreach ($Path in $C2) { $Blocking.Add([pscustomobject]@{ root = $Base.root; path = $Path; kind = 'PATH_COLLISION_HOLD' }) }
    $Registered = New-Object 'Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    foreach ($R in @($Base.registered)) { if ($R) { [void]$Registered.Add([string]$R) } }
    $Role = [string]$Base.role
    foreach ($Path in $Old.Keys) {
        $Before = $Old[$Path]
        if (-not $New.ContainsKey($Path)) { $Diff = [pscustomobject]@{ root = $Base.root; path = $Path; kind = 'REMOVED'; before = $Before; after = $null } }
        elseif ((Get-V5EntrySignature $Before) -cne (Get-V5EntrySignature $New[$Path]) -or $New[$Path].path -cne $Before.path) { $Diff = [pscustomobject]@{ root = $Base.root; path = $Path; kind = 'MODIFIED'; before = $Before; after = $New[$Path] } }
        else { continue }
        if ($Role -ceq 'downloads') {
            if ($Registered.Contains($Path)) { $Diff.kind = 'REGISTERED_' + $Diff.kind; $Blocking.Add($Diff) }
            elseif ($null -ne $Diff.after -and $Diff.after.reparse -and -not $Before.reparse) { $Diff.kind = 'REPARSE_CHANGED_HOLD'; $Blocking.Add($Diff) }
            else { $Noncore.Add($Diff) }
        } elseif ($Role -ceq 'core' -and $Base.webview_dir_mtime_exception -and $Diff.kind -ceq 'MODIFIED' -and
            $Before.directory -eq $true -and $Before.reparse -eq $false -and $New[$Path].directory -eq $true -and $New[$Path].reparse -eq $false -and
            $Path -cmatch '^EBWebView(\\[^\\/:]+)*$' -and @($Path.Split('\') | Where-Object { $_ -in @('.', '..') }).Count -eq 0 -and
            (Get-V5EntrySignature ([pscustomobject]@{ directory = $Before.directory; reparse = $Before.reparse; attributes = $Before.attributes; write_ticks = 0; creation_ticks = $Before.creation_ticks; size = $Before.size; sha256 = $Before.sha256 })) -ceq
            (Get-V5EntrySignature ([pscustomobject]@{ directory = $New[$Path].directory; reparse = $New[$Path].reparse; attributes = $New[$Path].attributes; write_ticks = 0; creation_ticks = $New[$Path].creation_ticks; size = $New[$Path].size; sha256 = $New[$Path].sha256 }))) {
            $Diff.kind = 'DIR_MTIME_ONLY_ALLOWED'; $Noncore.Add($Diff)
        } else { $Blocking.Add($Diff) }
    }
    foreach ($Path in $New.Keys) {
        if ($Old.ContainsKey($Path)) { continue }
        $Diff = [pscustomobject]@{ root = $Base.root; path = $Path; kind = 'ADDED'; before = $null; after = $New[$Path] }
        if ($Role -ceq 'downloads' -and -not $New[$Path].reparse) {
            # A new entry under a registered path can only exist if that path was replaced.
            if ($Registered.Contains($Path)) { $Diff.kind = 'REGISTERED_ADDED'; $Blocking.Add($Diff) } else { $Noncore.Add($Diff) }
        } else {
            if ($New[$Path].reparse) { $Diff.kind = 'REPARSE_ADDED_HOLD' }
            $Blocking.Add($Diff)
        }
    }
    # Same name/size/timestamps but a different NTFS file index means the entry was replaced.
    foreach ($Id in @($Base.registered_file_ids)) {
        if ($null -eq $Id -or -not $New.ContainsKey($Id.path) -or -not $Old.ContainsKey($Id.path)) { continue }
        if ((Get-V5EntrySignature $Old[$Id.path]) -cne (Get-V5EntrySignature $New[$Id.path])) { continue }
        try { $Current = Get-V5FileId (Join-Path $Base.root $Id.path) } catch { $Current = 'UNREADABLE' }
        if ($Current -cne $Id.file_id) { $Blocking.Add([pscustomobject]@{ root = $Base.root; path = $Id.path; kind = 'REGISTERED_REPLACED'; before = $Id.file_id; after = $Current }) }
    }
}

function Invoke-V5Scan([bool]$WithHistory) {
    if ((Get-V5Sha256 $BaselinePath) -cne $BaselineSha256) { return [pscustomobject]@{ reason = 'BASELINE_SHA_MISMATCH'; blocking = @([pscustomobject]@{ kind = 'BASELINE_SHA_MISMATCH' }); noncore = @() } }
    $Blocking = New-Object 'Collections.Generic.List[object]'
    $Noncore = New-Object 'Collections.Generic.List[object]'
    foreach ($Base in $Baseline.roots) {
        $Current = Get-V5Inventory $Base.root @($Base.exclude) @($Base.hash_names)
        Compare-V5Root $Base $Current $Blocking $Noncore
    }
    foreach ($Item in $Baseline.preserved) {
        if (-not [IO.File]::Exists($Item.path) -or (New-Object IO.FileInfo($Item.path)).Length -ne [long]$Item.size -or (Get-V5Sha256 $Item.path) -cne $Item.sha256) { $Blocking.Add([pscustomobject]@{ path = $Item.path; kind = 'PRESERVED_HASH_OR_SIZE_CHANGED' }) }
    }
    if ($WithHistory) {
        foreach ($Item in $Baseline.history) {
            if (-not [IO.File]::Exists($Item.path) -or (New-Object IO.FileInfo($Item.path)).Length -ne [long]$Item.size -or (Get-V5Sha256 $Item.path) -cne $Item.sha256) { $Blocking.Add([pscustomobject]@{ path = $Item.path; kind = 'HISTORY_CHANGED' }) }
        }
    }
    if ($null -ne $Baseline.installed_json -and (Get-V5InstalledRegistration) -cne $Baseline.installed_json) { $Blocking.Add([pscustomobject]@{ kind = 'INSTALL_REGISTRATION_CHANGED' }) }
    return [pscustomobject]@{ reason = $(if ($Blocking.Count) { 'PROTECTED_CHANGE' } else { $null }); blocking = @($Blocking.ToArray()); noncore = @($Noncore.ToArray()) }
}

$script:LastNoncoreSignature = ConvertTo-Json -InputObject @() -Compress
# Raw diff first, then the decision. A raw-record failure is an audit failure (blocking).
function Save-V5Scan($Scan, [string]$Stage) {
    $Signature = ConvertTo-Json -InputObject @($Scan.noncore | ForEach-Object { @($_.kind, $_.root, $_.path, (Get-V5EntrySignature $_.after)) }) -Compress -Depth 5
    if (-not $Scan.blocking.Count -and $Signature -ceq $script:LastNoncoreSignature) { return $null }
    $Name = 'RAW_DIFF_{0:D6}_{1}.json' -f $Sequence, $Stage
    Write-V5JsonNew (Join-Path $RawDir $Name) ([ordered]@{
        sequence = $Sequence; stage = $Stage; at_utc = [DateTime]::UtcNow.ToString('o'); baseline_sha256 = $BaselineSha256
        decision = $(if ($Scan.blocking.Count) { 'STOP' } elseif ($Scan.noncore.Count) { 'NONCORE_ACTIVITY_RECORDED' } else { 'NO_CHANGE' })
        blocking = $Scan.blocking; noncore = $Scan.noncore })
    $script:LastNoncoreSignature = $Signature
    return $Name
}

try {
    if ([IO.File]::Exists($StopRequired)) { throw 'PRIOR_STOP_REQUIRED_PRESENT' }
    # Hash and parse the same bytes so a swap between the two cannot load an unverified baseline.
    $BaselineBytes = [IO.File]::ReadAllBytes($BaselinePath)
    $Hasher = [Security.Cryptography.SHA256]::Create()
    try { $LoadedSha = ([BitConverter]::ToString($Hasher.ComputeHash($BaselineBytes))).Replace('-', '').ToLowerInvariant() } finally { $Hasher.Dispose() }
    if ($LoadedSha -cne $BaselineSha256) { Write-StopRequired ([ordered]@{ reason = 'BASELINE_SHA_MISMATCH' }); exit 5 }
    $Baseline = $script:V5Utf8.GetString($BaselineBytes) | ConvertFrom-Json
    if ($Baseline.format -cne 'sorigul-preservation-v5') { Write-StopRequired ([ordered]@{ reason = 'BASELINE_FORMAT_INVALID' }); exit 5 }
    $StateFull = [IO.Path]::GetFullPath($StateDir).TrimEnd('\') + '\'
    foreach ($Base in $Baseline.roots) { if ($StateFull.StartsWith(([IO.Path]::GetFullPath($Base.root).TrimEnd('\') + '\'), [StringComparison]::OrdinalIgnoreCase)) { throw 'STATE_DIR_INSIDE_PROTECTED_ROOT' } }
    if (-not [IO.Directory]::Exists($RawDir)) { [void][IO.Directory]::CreateDirectory($RawDir) }
    Write-V5JsonNew (Join-Path $StateDir ('OBSERVER_START_' + $PID + '.json')) ([ordered]@{
        pid = $PID; start_ticks = $StartTicks; at_utc = [DateTime]::UtcNow.ToString('o'); baseline_path = $BaselinePath; baseline_sha256 = $BaselineSha256
        observer_sha256 = (Get-V5Sha256 $PSCommandPath); common_sha256 = (Get-V5Sha256 (Join-Path $PSScriptRoot 'observer-v5-common.ps1')); interval_seconds = $IntervalSeconds })
    $WithHistory = $true
    while ($true) {
        $Final = [IO.File]::Exists($StopRequest)
        $Nonce = $null
        if ($Final) { try { $Nonce = (Read-V5Json $StopRequest).nonce } catch { $Nonce = $null } }
        $Sequence++
        $Watch = [Diagnostics.Stopwatch]::StartNew()
        $Cpu = $Self.TotalProcessorTime
        $Scan = Invoke-V5Scan ($WithHistory -or $Final)
        $WithHistory = $false
        $Watch.Stop(); $Self.Refresh()
        $Stage = $(if ($Final) { 'FINAL' } else { 'CYCLE' })
        try { $RawName = Save-V5Scan $Scan $Stage }
        catch { Write-StopRequired ([ordered]@{ reason = 'AUDIT_RECORD_FAILED'; error = $_.Exception.Message; blocking_count = $Scan.blocking.Count }); exit 5 }
        if ($Scan.blocking.Count) {
            Write-StopRequired ([ordered]@{ reason = $Scan.reason; classification = 'HARD_STOP'; raw_diff = $RawName; blocking_count = $Scan.blocking.Count; differences = @($Scan.blocking | Select-Object -First 50 | ForEach-Object { [ordered]@{ kind = $_.kind; root = $_.root; path = $_.path } }) })
            exit 5
        }
        if ($Final) {
            Write-V5JsonNew (Join-Path $StateDir 'OBSERVER_STOPPED.json') ([ordered]@{
                pid = $PID; start_ticks = $StartTicks; sequence = $Sequence; controlled = $true; nonce = $Nonce; final_verdict = 'PASS'
                baseline_sha256 = $BaselineSha256; noncore_activity = $Scan.noncore.Count; at_utc = [DateTime]::UtcNow.ToString('o') })
            exit 0
        }
        Write-V5JsonReplace (Join-Path $StateDir 'OBSERVER_HEARTBEAT.json') ([ordered]@{
            pid = $PID; start_ticks = $StartTicks; sequence = $Sequence; at_utc = [DateTime]::UtcNow.ToString('o')
            protected = 'NO_CHANGE'; hashes = 'MATCH'; preserved_file_count = @($Baseline.preserved).Count
            baseline_sha256 = $BaselineSha256; noncore_activity = $Scan.noncore.Count
            scan_ms = $Watch.ElapsedMilliseconds; scan_cpu_ms = [long]($Self.TotalProcessorTime - $Cpu).TotalMilliseconds; working_set_mb = [long]($Self.WorkingSet64 / 1MB) })
        for ($I = 0; $I -lt $IntervalSeconds; $I++) { if ([IO.File]::Exists($StopRequest)) { break }; Start-Sleep -Seconds 1 }
    }
} catch {
    try { Write-StopRequired ([ordered]@{ reason = 'OBSERVER_FAILED'; error = $_.Exception.Message }) } catch { exit 7 }
    exit 6
}
