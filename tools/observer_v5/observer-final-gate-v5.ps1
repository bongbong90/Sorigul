# Final success gate, run after the watched child has exited 0.
# Exit 0 only when the observer performed a fresh full scan bound to this nonce,
# ended itself with exit 0 and final_verdict PASS, and no STOP record exists.
# The observer has exited when PASS is read, so no later STOP can race the verdict.
param(
    [Parameter(Mandatory = $true)][string]$StateDir,
    [Parameter(Mandatory = $true)][string]$BaselineSha256,
    [int]$TimeoutSeconds = 900
)
$ErrorActionPreference = 'Stop'
. ([scriptblock]::Create([IO.File]::ReadAllText((Join-Path $PSScriptRoot 'observer-v5-common.ps1'), (New-Object Text.UTF8Encoding($false)))))

function Get-StopRecords { return @([IO.Directory]::GetFiles($StateDir, 'OBSERVER_STOP_REQUIRED*.json')) }
function Finish([string]$Verdict, [string]$Reason, $Extra) {
    $Record = [ordered]@{ verdict = $Verdict; reason = $Reason; at_utc = [DateTime]::UtcNow.ToString('o'); detail = $Extra }
    try { Write-V5JsonNew (Join-Path $StateDir ('FINAL_GATE_' + $Verdict + '_' + [Guid]::NewGuid().ToString('N') + '.json')) $Record }
    catch { [Console]::Error.WriteLine('FINAL_GATE_RECORD_FAILED'); exit 1 }
    $Record | ConvertTo-Json -Compress
    if ($Verdict -ceq 'PASS') { exit 0 } else { exit 1 }
}

try {
    if ((Get-StopRecords).Count) { Finish 'FAIL' 'STOP_REQUIRED_PRESENT' $null }
    if ([IO.File]::Exists((Join-Path $StateDir 'OBSERVER_STOPPED.json'))) { Finish 'FAIL' 'STALE_STOPPED_RECORD' $null }
    $Heartbeat = Read-V5Json (Join-Path $StateDir 'OBSERVER_HEARTBEAT.json')
    $Observer = [Diagnostics.Process]::GetProcessById([int]$Heartbeat.pid)
    [void]$Observer.Handle
    if ($Observer.HasExited -or $Observer.StartTime.ToUniversalTime().Ticks.ToString() -cne $Heartbeat.start_ticks) { Finish 'FAIL' 'OBSERVER_IDENTITY' $null }
    if ($Heartbeat.baseline_sha256 -cne $BaselineSha256) { Finish 'FAIL' 'BASELINE_MISMATCH' $null }
    $Nonce = [Guid]::NewGuid().ToString('N')
    Write-V5JsonNew (Join-Path $StateDir 'OBSERVER_STOP_REQUEST.json') ([ordered]@{ nonce = $Nonce; at_utc = [DateTime]::UtcNow.ToString('o') })
    if (-not $Observer.WaitForExit($TimeoutSeconds * 1000)) { Finish 'FAIL' 'OBSERVER_FINAL_TIMEOUT' $null }
    $Observer.WaitForExit()
    $ExitCode = $Observer.ExitCode
    if ((Get-StopRecords).Count) { Finish 'FAIL' 'STOP_REQUIRED_PRESENT' @{ observer_exit = $ExitCode } }
    if ($ExitCode -ne 0) { Finish 'FAIL' 'OBSERVER_NONZERO_EXIT' @{ observer_exit = $ExitCode } }
    $Stopped = Read-V5Json (Join-Path $StateDir 'OBSERVER_STOPPED.json')
    if ($Stopped.nonce -cne $Nonce -or $Stopped.final_verdict -cne 'PASS' -or $Stopped.controlled -ne $true -or
        [int]$Stopped.pid -ne [int]$Heartbeat.pid -or $Stopped.start_ticks -cne $Heartbeat.start_ticks -or
        [long]$Stopped.sequence -le [long]$Heartbeat.sequence -or $Stopped.baseline_sha256 -cne $BaselineSha256) { Finish 'FAIL' 'FINAL_RECORD_INVALID' $null }
    if ((Get-StopRecords).Count) { Finish 'FAIL' 'STOP_REQUIRED_PRESENT' $null }
    Finish 'PASS' $null @{ observer_pid = $Stopped.pid; final_sequence = $Stopped.sequence; noncore_activity = $Stopped.noncore_activity }
} catch {
    Finish 'FAIL' ('GATE_ERROR: ' + $_.Exception.Message) $null
}
