# Builds a new, never-overwritten V5 preservation baseline from a UTF-8 spec.
# Read-only against every protected path. Any ambiguity is HOLD (non-zero exit).
param(
    [Parameter(Mandatory = $true)][string]$SpecPath,
    [Parameter(Mandatory = $true)][string]$OutPath
)
$ErrorActionPreference = 'Stop'
. ([scriptblock]::Create([IO.File]::ReadAllText((Join-Path $PSScriptRoot 'observer-v5-common.ps1'), (New-Object Text.UTF8Encoding($false)))))

function Stop-Hold([string]$Reason) { [Console]::Error.WriteLine('HOLD: ' + $Reason); exit 3 }

if ($PSVersionTable.PSEdition -cne 'Desktop' -or $PSVersionTable.PSVersion.Major -ne 5) { Stop-Hold 'NATIVE_PS51_REQUIRED' }
if ([IO.File]::Exists($OutPath)) { Stop-Hold 'NO_OVERWRITE' }
$Spec = Read-V5Json $SpecPath

$Roots = New-Object 'Collections.Generic.List[object]'
foreach ($Core in @($Spec.core)) {
    $Inventory = Get-V5Inventory $Core.root @($Core.exclude) @($Core.hash_names)
    $Collisions = $null; [void](ConvertTo-V5EntryMap $Inventory.entries ([ref]$Collisions))
    if ($Collisions.Count) { Stop-Hold ('PATH_COLLISION ' + $Core.root) }
    $Roots.Add([pscustomobject][ordered]@{
        role = 'core'; root = $Core.root; exists = $Inventory.exists; exclude = @($Core.exclude); hash_names = @($Core.hash_names)
        webview_dir_mtime_exception = [bool]$Core.webview_dir_mtime_exception; entries = $Inventory.entries })
}

$Transcription = Get-V5Inventory $Spec.transcription_root
if (-not $Transcription.exists) { Stop-Hold 'TRANSCRIPTION_ROOT_MISSING' }
$Collisions = $null; [void](ConvertTo-V5EntryMap $Transcription.entries ([ref]$Collisions))
if ($Collisions.Count) { Stop-Hold 'PATH_COLLISION transcription' }
$Roots.Add([pscustomobject][ordered]@{ role = 'transcription'; root = $Spec.transcription_root; exists = $true; exclude = @(); hash_names = @(); webview_dir_mtime_exception = $false; entries = $Transcription.entries })

$Downloads = Get-V5Inventory $Spec.downloads_root
if (-not $Downloads.exists) { Stop-Hold 'DOWNLOADS_ROOT_MISSING' }
$Collisions = $null; $Map = ConvertTo-V5EntryMap $Downloads.entries ([ref]$Collisions)
if ($Collisions.Count) { Stop-Hold 'PATH_COLLISION downloads' }
$Seen = New-Object 'Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
foreach ($Relative in @($Spec.registered)) {
    if (-not $Seen.Add([string]$Relative)) { Stop-Hold ('REGISTERED_DUPLICATE ' + $Relative) }
    if ([IO.Path]::IsPathRooted($Relative) -or @(([string]$Relative).Split('\') | Where-Object { $_ -in @('', '.', '..') }).Count) { Stop-Hold ('REGISTERED_PATH_INVALID ' + $Relative) }
    if (-not $Map.ContainsKey($Relative)) { Stop-Hold ('REGISTERED_NOT_FOUND ' + $Relative) }
    $Entry = $Map[$Relative]
    if ($Entry.directory -or $Entry.reparse -or $Entry.path -cne $Relative) { Stop-Hold ('REGISTERED_IDENTITY_UNCLEAR ' + $Relative) }
    $Parts = ([string]$Relative).Split('\')
    for ($I = 1; $I -lt $Parts.Count; $I++) {
        $Ancestor = $Map[[string]::Join('\', $Parts[0..($I - 1)])]
        if (-not $Ancestor.directory -or $Ancestor.reparse) { Stop-Hold ('REGISTERED_ANCESTOR_UNSAFE ' + $Relative) }
    }
}
$RegisteredIds = foreach ($Relative in @($Spec.registered)) {
    try { [pscustomobject][ordered]@{ path = [string]$Relative; file_id = (Get-V5FileId (Join-Path $Spec.downloads_root $Relative)) } }
    catch { Stop-Hold ('REGISTERED_FILE_ID_UNREADABLE ' + $Relative) }
}
$Roots.Add([pscustomobject][ordered]@{ role = 'downloads'; root = $Spec.downloads_root; exists = $true; exclude = @(); hash_names = @(); webview_dir_mtime_exception = $false; registered = @($Spec.registered); registered_file_ids = @($RegisteredIds); entries = $Downloads.entries })

$Preserved = foreach ($Item in @($Spec.preserved)) {
    if (-not [IO.File]::Exists($Item.path)) { Stop-Hold ('PRESERVED_MISSING ' + $Item.path) }
    $Hash = Get-V5Sha256 $Item.path
    if ($Item.expected_sha256 -and $Hash -cne $Item.expected_sha256) { Stop-Hold ('PRESERVED_HASH_MISMATCH ' + $Item.path) }
    [pscustomobject][ordered]@{ path = $Item.path; sha256 = $Hash; size = (New-Object IO.FileInfo($Item.path)).Length }
}
$History = foreach ($Item in @($Spec.history)) {
    if (-not [IO.File]::Exists($Item.path) -or (New-Object IO.FileInfo($Item.path)).Length -ne [long]$Item.size -or (Get-V5Sha256 $Item.path) -cne $Item.sha256) { Stop-Hold ('HISTORY_MISMATCH ' + $Item.path) }
    [pscustomobject][ordered]@{ path = $Item.path; sha256 = $Item.sha256; size = [long]$Item.size }
}

$Baseline = [ordered]@{
    format = 'sorigul-preservation-v5'; version = 5; created_utc = [DateTime]::UtcNow.ToString('o')
    native_engine = [ordered]@{ powershell = $PSVersionTable.PSVersion.ToString(); edition = $PSVersionTable.PSEdition }
    policy = [ordered]@{
        core = 'Any add/remove/field change STOP; only EBWebView directory write_ticks on a flagged root is allowed.'
        transcription = 'Any add/remove/field change STOP during the watched window.'
        downloads_registered = 'Registered entries: missing, field change or replacement STOP.'
        downloads_other = 'Unregistered add/modify/delete recorded as NONCORE_ACTIVITY_RECORDED (non-blocking, never promoted); new reparse or path collision HOLD (blocking).'
        preserved = 'SHA256 and size every cycle.'
        history = 'SHA256 and size at start and at the final scan.'
    }
    lineage = $Spec.lineage
    roots = @($Roots.ToArray())
    preserved = @($Preserved)
    history = @($History)
    installed_json = $(if ($Spec.capture_installed) { Get-V5InstalledRegistration } else { $null })
}
Write-V5JsonNew $OutPath $Baseline
Write-Output ('V5_SHA256=' + (Get-V5Sha256 $OutPath))
