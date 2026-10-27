# Focused TEMP-fixture tests for the V5 baseline/observer/final gate.
# Touches only a fresh directory under %TEMP%; no real user path is read or written.
# -RunAsBuildPath points at the existing runner whose monitoring loop is reused verbatim (AST).
param(
    [Parameter(Mandatory = $true)][string]$RunAsBuildPath,
    [Parameter(Mandatory = $true)][string]$ReportPath
)
$ErrorActionPreference = 'Stop'
$Tools = $PSScriptRoot
. ([scriptblock]::Create([IO.File]::ReadAllText((Join-Path $Tools 'observer-v5-common.ps1'), (New-Object Text.UTF8Encoding($false)))))
$PS5 = Join-Path ([Environment]::SystemDirectory) 'WindowsPowerShell\v1.0\powershell.exe'
function U([string]$Text) { return [regex]::Unescape($Text) }
$NameTrans = U '\uC804\uC0AC'
$NameLecture = U '\uAE30\uBCF8\uC774\uB860_\uBBFC\uBC95_1\uC8FC\uCC28_1\uAC15.mp3'
$NameRegMp3 = U '1\uAC15_[1\uC8FC\uCC28]_\uD14C\uC2A4\uD2B8.mp3'
$NameRegDir = U '[2\uCC28] \uBD80\uB3D9\uC0B0\uC138\uBC95'
$NameRegSrt = U '\uAC1C\uB150_1\uAC15.srt'
$NameRegTxt = U '\uAC1C\uB150_1\uAC15.txt'
$NameNewPdf = U '\uC0C8\uC790\uB8CC.pdf'
$Results = New-Object 'Collections.Generic.List[object]'
$Fixtures = New-Object 'Collections.Generic.List[string]'

function Quote([string]$Value) { return "'" + $Value.Replace("'", "''") + "'" }
function Start-PS5([string]$Script, [string]$Arguments) {
    $Command = '$ErrorActionPreference=''Stop'';$t=$null;$e=$null;$a=[Management.Automation.Language.Parser]::ParseFile(' + (Quote (Join-Path $Tools $Script)) + ',[ref]$t,[ref]$e);if($e.Count){exit 90};& $a.GetScriptBlock() ' + $Arguments + ';exit $LASTEXITCODE'
    $Info = New-Object Diagnostics.ProcessStartInfo
    $Info.FileName = $PS5; $Info.Arguments = '-NoProfile -NonInteractive -Command "' + $Command.Replace('"', '\"') + '"'
    $Info.UseShellExecute = $false; $Info.CreateNoWindow = $true; $Info.RedirectStandardOutput = $true; $Info.RedirectStandardError = $true
    $Process = [Diagnostics.Process]::Start($Info); [void]$Process.Handle
    return $Process
}
function Wait-PS5($Process, [int]$Seconds = 120) {
    $Out = $Process.StandardOutput.ReadToEndAsync(); $Err = $Process.StandardError.ReadToEndAsync()
    if (-not $Process.WaitForExit($Seconds * 1000)) { $Process.Kill(); throw 'CHILD_TIMEOUT' }
    $Process.WaitForExit()
    return [pscustomobject]@{ exit = $Process.ExitCode; out = $Out.Result; err = $Err.Result }
}
function Wait-Until([scriptblock]$Condition, [int]$Seconds = 30) {
    $Deadline = [DateTime]::UtcNow.AddSeconds($Seconds)
    while ([DateTime]::UtcNow -lt $Deadline) { if (& $Condition) { return $true }; Start-Sleep -Milliseconds 200 }
    return $false
}
function Write-Bytes([string]$Path, [int]$Count) { $B = New-Object byte[] $Count; (New-Object Random($Count)).NextBytes($B); [IO.File]::WriteAllBytes($Path, $B) }

function New-Fixture([scriptblock]$EditSpec = $null) {
    $Base = Join-Path $env:TEMP ('sorigul-observer-v5-' + [Guid]::NewGuid().ToString('N').Substring(0, 12))
    $Fixtures.Add($Base)
    $F = [ordered]@{ base = $Base }
    $F.app = Join-Path $Base 'core\Local\Sorigul'; $F.web = Join-Path $Base 'core\Local\com.sorigul.desktop'; $F.roaming = Join-Path $Base 'core\Roaming\Sorigul'
    $F.trans = Join-Path $Base ('Desktop\' + $NameTrans); $F.dl = Join-Path $Base 'Downloads'; $F.state = Join-Path $Base 'state'
    $F.baseline = Join-Path $Base 'baseline\PRESERVATION_V5.json'
    foreach ($D in @($F.app, (Join-Path $F.app 'runtime\local-whisper\v1'), (Join-Path $F.web 'EBWebView\Default'), $F.trans, (Join-Path $F.dl ('sub\' + $NameRegDir)), $F.state, (Join-Path $Base 'baseline'), (Join-Path $Base 'pf'), (Join-Path $Base 'hist'))) { [void][IO.Directory]::CreateDirectory($D) }
    [IO.File]::WriteAllText((Join-Path $F.app 'settings.json'), '{"transcription_folder":"x"}', $script:V5Utf8)
    [IO.File]::WriteAllText((Join-Path $F.app 'jobs.json'), '[{"id":"a"}]', $script:V5Utf8)
    Write-Bytes (Join-Path $F.app 'runtime\local-whisper\v1\runtime.bin') 4096
    Write-Bytes (Join-Path $F.web 'EBWebView\Default\Cookies') 64
    Write-Bytes (Join-Path $F.trans $NameLecture) 2048
    Write-Bytes (Join-Path $F.dl $NameRegMp3) 3000
    Write-Bytes (Join-Path $F.dl ('sub\' + $NameRegDir + '\' + $NameRegSrt)) 300
    Write-Bytes (Join-Path $F.dl ('sub\' + $NameRegDir + '\' + $NameRegTxt)) 200
    Write-Bytes (Join-Path $F.dl 'other.pdf') 500
    Write-Bytes (Join-Path $F.dl 'sub\note.txt') 50
    Write-Bytes (Join-Path $Base 'pf\sorigul-desktop.exe') 8192
    Write-Bytes (Join-Path $Base 'hist\h1.log') 100
    $F.reg_mp3 = Join-Path $F.dl $NameRegMp3
    $F.reg_srt = Join-Path $F.dl ('sub\' + $NameRegDir + '\' + $NameRegSrt)
    $Spec = [ordered]@{
        core = @(
            [ordered]@{ root = $F.app; exclude = @('runtime'); hash_names = @('settings.json', 'jobs.json'); webview_dir_mtime_exception = $false },
            [ordered]@{ root = $F.web; exclude = @(); hash_names = @(); webview_dir_mtime_exception = $true },
            [ordered]@{ root = $F.roaming; exclude = @(); hash_names = @(); webview_dir_mtime_exception = $false })
        transcription_root = $F.trans; downloads_root = $F.dl
        registered = @($NameRegMp3, ('sub\' + $NameRegDir + '\' + $NameRegSrt), ('sub\' + $NameRegDir + '\' + $NameRegTxt))
        preserved = @([ordered]@{ path = (Join-Path $Base 'pf\sorigul-desktop.exe') }, [ordered]@{ path = (Join-Path $F.app 'runtime\local-whisper\v1\runtime.bin') })
        history = @([ordered]@{ path = (Join-Path $Base 'hist\h1.log'); sha256 = (Get-V5Sha256 (Join-Path $Base 'hist\h1.log')); size = 100 })
        capture_installed = $false; lineage = [ordered]@{ fixture = $true }
    }
    if ($EditSpec) { & $EditSpec $Spec $F }
    $F.spec = Join-Path $Base 'spec.json'
    [IO.File]::WriteAllText($F.spec, (ConvertTo-V5JsonText $Spec), $script:V5Utf8)
    return [pscustomobject]$F
}
function Build-Baseline($F) {
    # Let NTFS settle lazily-updated directory timestamps of the fresh fixture.
    Start-Sleep -Seconds 3
    $R = Wait-PS5 (Start-PS5 'build-preservation-v5.ps1' ('-SpecPath ' + (Quote $F.spec) + ' -OutPath ' + (Quote $F.baseline)))
    if ($R.exit -eq 0) { $F | Add-Member -NotePropertyName sha -NotePropertyValue (Get-V5Sha256 $F.baseline) -Force }
    return $R
}
function Start-Observer($F, [int]$Interval = 1, [string]$Sha = $null) {
    if (-not $Sha) { $Sha = $F.sha }
    $P = Start-PS5 'watch-existing-user-v5.ps1' ('-BaselinePath ' + (Quote $F.baseline) + ' -BaselineSha256 ' + (Quote $Sha) + ' -StateDir ' + (Quote $F.state) + ' -IntervalSeconds ' + $Interval)
    $F | Add-Member -NotePropertyName observer -NotePropertyValue $P -Force
    return $P
}
function Get-Heartbeat($F) { try { return Read-V5Json (Join-Path $F.state 'OBSERVER_HEARTBEAT.json') } catch { return $null } }
function Wait-Heartbeat($F, [int]$MinSequence = 1) { return (Wait-Until { $H = Get-Heartbeat $F; $null -ne $H -and [int]$H.sequence -ge $MinSequence } 60) }
function Get-Stop($F) { $P = Join-Path $F.state 'OBSERVER_STOP_REQUIRED.json'; if ([IO.File]::Exists($P)) { return Read-V5Json $P }; return $null }
function Wait-Stop($F) { [void](Wait-Until { [IO.File]::Exists((Join-Path $F.state 'OBSERVER_STOP_REQUIRED.json')) } 30); return Get-Stop $F }
function Invoke-Gate($F) { return Wait-PS5 (Start-PS5 'observer-final-gate-v5.ps1' ('-StateDir ' + (Quote $F.state) + ' -BaselineSha256 ' + (Quote $F.sha) + ' -TimeoutSeconds 120')) }
function Get-GatePass($F) { return @([IO.Directory]::GetFiles($F.state, 'FINAL_GATE_PASS_*.json')).Count }
function Stop-Observer($F) { if ($F.observer -and -not $F.observer.HasExited) { $F.observer.Kill(); [void]$F.observer.WaitForExit(10000) } }
function Get-StopKinds($Stop) { return @($Stop.differences | ForEach-Object { $_.kind }) }

function Test([string]$Name, [scriptblock]$Body) {
    $Watch = [Diagnostics.Stopwatch]::StartNew()
    try { $Detail = & $Body; $Pass = $Detail.pass; $Info = $Detail.info }
    catch { $Pass = $false; $Info = 'EXCEPTION: ' + $_.Exception.Message + ' @ ' + $_.InvocationInfo.ScriptLineNumber }
    $Results.Add([pscustomobject][ordered]@{ name = $Name; pass = [bool]$Pass; seconds = [Math]::Round($Watch.Elapsed.TotalSeconds, 1); info = $Info })
    [Console]::Out.WriteLine(('{0} {1} ({2}s) {3}' -f $(if ($Pass) { 'PASS' } else { 'FAIL' }), $Name, [Math]::Round($Watch.Elapsed.TotalSeconds, 1), ($Info | ConvertTo-Json -Compress -Depth 6)))
}
function Expect-Stop([scriptblock]$Mutate, [string[]]$Kinds, [string]$Reason = 'PROTECTED_CHANGE') {
    $F = New-Fixture; $B = Build-Baseline $F; if ($B.exit) { return @{ pass = $false; info = $B.err } }
    [void](Start-Observer $F); if (-not (Wait-Heartbeat $F 2)) { return @{ pass = $false; info = 'NO_HEARTBEAT' } }
    & $Mutate $F
    $Stop = Wait-Stop $F
    [void]$F.observer.WaitForExit(30000)
    $Gate = Invoke-Gate $F
    $Got = Get-StopKinds $Stop
    $Pass = $null -ne $Stop -and $Stop.reason -ceq $Reason -and $F.observer.ExitCode -eq 5 -and $Gate.exit -ne 0 -and (Get-GatePass $F) -eq 0 -and
        @($Kinds | Where-Object { $Got -notcontains $_ }).Count -eq 0
    Stop-Observer $F
    return @{ pass = $Pass; info = @{ reason = $Stop.reason; kinds = $Got; observer_exit = $F.observer.ExitCode; gate_exit = $Gate.exit } }
}

# 1. Registered Downloads entries
Test 'T01a_registered_modify_stop' { Expect-Stop { param($F) $S = [IO.File]::Open($F.reg_mp3, 'Append'); $S.WriteByte(1); $S.Dispose() } @('REGISTERED_MODIFIED') }
Test 'T01b_registered_delete_stop' { Expect-Stop { param($F) [IO.File]::Delete($F.reg_srt) } @('REGISTERED_REMOVED') }
Test 'T01c_registered_replace_same_size_and_mtime_stop' { Expect-Stop { param($F)
        $Old = New-Object IO.FileInfo($F.reg_mp3); $Tmp = Join-Path $F.base 'replacement.bin'; Write-Bytes $Tmp 3000
        [IO.File]::SetLastWriteTimeUtc($Tmp, $Old.LastWriteTimeUtc); [IO.File]::Delete($F.reg_mp3); [IO.File]::Move($Tmp, $F.reg_mp3) } @('REGISTERED_REPLACED') }

# 2 + 7. Unregistered activity is recorded, non-blocking; Korean names and order shifts cause no false STOP
Test 'T02_unregistered_add_modify_delete_nonblocking_recorded' {
    $F = New-Fixture; $B = Build-Baseline $F; if ($B.exit) { return @{ pass = $false; info = $B.err } }
    [void](Start-Observer $F); if (-not (Wait-Heartbeat $F 2)) { return @{ pass = $false; info = 'NO_HEARTBEAT' } }
    Write-Bytes (Join-Path $F.dl '0000_sorts_first.pdf') 10
    Write-Bytes (Join-Path $F.dl ('sub\' + $NameNewPdf)) 20
    $S = [IO.File]::Open((Join-Path $F.dl 'other.pdf'), 'Append'); $S.WriteByte(1); $S.Dispose()
    [IO.File]::Delete((Join-Path $F.dl 'sub\note.txt'))
    $Seq = [int](Get-Heartbeat $F).sequence
    [void](Wait-Heartbeat $F ($Seq + 8))
    $Cycles = [int](Get-Heartbeat $F).sequence - $Seq
    $Raw = @([IO.Directory]::GetFiles((Join-Path $F.state 'raw'), 'RAW_DIFF_*.json') | ForEach-Object { Read-V5Json $_ })
    $Paths = @($Raw | ForEach-Object { $_.noncore } | ForEach-Object { $_.path } | Sort-Object -Unique)
    $Gate = Invoke-Gate $F
    $Stopped = Read-V5Json (Join-Path $F.state 'OBSERVER_STOPPED.json')
    $Pass = $null -eq (Get-Stop $F) -and $Raw.Count -ge 1 -and @($Raw | Where-Object { $_.decision -cne 'NONCORE_ACTIVITY_RECORDED' }).Count -eq 0 -and
        $Paths -contains '0000_sorts_first.pdf' -and $Paths -contains ('sub\' + $NameNewPdf) -and $Paths -contains 'other.pdf' -and $Paths -contains 'sub\note.txt' -and
        $Raw.Count -le 3 -and $Cycles -ge 8 -and $Gate.exit -eq 0 -and (Get-GatePass $F) -eq 1 -and [int]$Stopped.noncore_activity -ge 4
    return @{ pass = $Pass; info = @{ raw_files = $Raw.Count; cycles_after_activity = $Cycles; noncore_paths = $Paths.Count; gate_exit = $Gate.exit; stopped_noncore = $Stopped.noncore_activity } }
}

# 3. Core, Runtime (preserved) and EBWebView exception
Test 'T03a_core_jobs_content_change_stop' { Expect-Stop { param($F) [IO.File]::WriteAllText((Join-Path $F.app 'jobs.json'), '[{"id":"b"}]', $script:V5Utf8) } @('MODIFIED') }
Test 'T03b_core_add_stop' { Expect-Stop { param($F) Write-Bytes (Join-Path $F.app 'results.tmp') 5 } @('ADDED') }
Test 'T03c_runtime_preserved_change_stop' { Expect-Stop { param($F) Write-Bytes (Join-Path $F.app 'runtime\local-whisper\v1\runtime.bin') 4097 } @('PRESERVED_HASH_OR_SIZE_CHANGED') }
Test 'T03d_core_missing_root_created_stop' { Expect-Stop { param($F) [void][IO.Directory]::CreateDirectory($F.roaming) } @('ROOT_PRESENCE') }
Test 'T03e_ebwebview_dir_mtime_only_allowed' {
    $F = New-Fixture; $B = Build-Baseline $F; if ($B.exit) { return @{ pass = $false; info = $B.err } }
    [void](Start-Observer $F); if (-not (Wait-Heartbeat $F 2)) { return @{ pass = $false; info = 'NO_HEARTBEAT' } }
    [IO.Directory]::SetLastWriteTimeUtc((Join-Path $F.web 'EBWebView\Default'), [DateTime]::UtcNow.AddMinutes(-3))
    $Seq = [int](Get-Heartbeat $F).sequence; [void](Wait-Heartbeat $F ($Seq + 2))
    $Gate = Invoke-Gate $F
    return @{ pass = ($null -eq (Get-Stop $F) -and $Gate.exit -eq 0); info = @{ gate_exit = $Gate.exit } }
}

# 4. Transcription folder
Test 'T04a_transcription_add_stop' { Expect-Stop { param($F) Write-Bytes (Join-Path $F.trans 'new.mp3') 10 } @('ADDED') }
Test 'T04b_transcription_modify_stop' { Expect-Stop { param($F) $S = [IO.File]::Open((Join-Path $F.trans $NameLecture), 'Append'); $S.WriteByte(1); $S.Dispose() } @('MODIFIED') }
Test 'T04c_transcription_delete_stop' { Expect-Stop { param($F) [IO.File]::Delete((Join-Path $F.trans $NameLecture)) } @('REMOVED') }

# 5. Baseline integrity
Test 'T05a_baseline_tamper_while_running_stop' { Expect-Stop { param($F) [IO.File]::AppendAllText($F.baseline, ' ') } @('BASELINE_SHA_MISMATCH') 'BASELINE_SHA_MISMATCH' }
Test 'T05b_wrong_expected_sha_at_start_stop' {
    $F = New-Fixture; $B = Build-Baseline $F; if ($B.exit) { return @{ pass = $false; info = $B.err } }
    $P = Start-Observer $F 1 ('0' * 64); [void]$P.WaitForExit(60000)
    $Stop = Get-Stop $F
    return @{ pass = ($P.ExitCode -eq 5 -and $Stop.reason -ceq 'BASELINE_SHA_MISMATCH' -and -not [IO.File]::Exists((Join-Path $F.state 'OBSERVER_HEARTBEAT.json'))); info = @{ exit = $P.ExitCode; reason = $Stop.reason } }
}

# 6. Heartbeat contract with the existing runner loop (verbatim AST extract)
$RunnerAst = [Management.Automation.Language.Parser]::ParseFile($RunAsBuildPath, [ref]$null, [ref]$null)
$RunnerLoop = $RunnerAst.Find({ param($N) $N -is [Management.Automation.Language.WhileStatementAst] -and $N.Condition.Extent.Text -ceq '-not $process.HasExited' }, $true).Extent.Text
$RunnerKill = $RunnerAst.Find({ param($N) $N -is [Management.Automation.Language.IfStatementAst] -and $N.Clauses[0].Item1.Extent.Text -ceq '$reason' }, $true).Extent.Text
function Invoke-RunnerLoop($F, [int]$ChildSeconds) {
    $root = $F.state
    $process = Start-PS5 'observer-v5-common.ps1' ('; Start-Sleep -Seconds ' + $ChildSeconds)
    $startTicks = $process.StartTime.ToUniversalTime().Ticks.ToString()
    $deadline = [DateTime]::UtcNow.AddSeconds(300); $reason = $null
    . ([scriptblock]::Create($RunnerLoop))
    . ([scriptblock]::Create($RunnerKill))
    [void]$process.WaitForExit(15000)
    return [pscustomobject]@{ reason = $reason; child_exited = $process.HasExited; child_exit = $(if ($process.HasExited) { $process.ExitCode }) }
}
Test 'T06a_heartbeat_loss_runner_aborts_child' {
    $F = New-Fixture; $B = Build-Baseline $F; if ($B.exit) { return @{ pass = $false; info = $B.err } }
    $P = Start-Observer $F; if (-not (Wait-Heartbeat $F 2)) { return @{ pass = $false; info = 'NO_HEARTBEAT' } }
    $Killer = Start-PS5 'observer-v5-common.ps1' ('; Start-Sleep -Seconds 4; Stop-Process -Id ' + $P.Id + ' -Force')
    $R = Invoke-RunnerLoop $F 120
    [void]$Killer.WaitForExit(10000)
    # The existing runner reports a vanished observer as LOST or VALIDATION_FAILED; both abort the child.
    return @{ pass = ($R.reason -cin @('EXISTING_USER_OBSERVER_LOST', 'EXISTING_USER_OBSERVER_VALIDATION_FAILED') -and $R.child_exited -and $R.child_exit -ne 0); info = $R }
}
Test 'T06b_runner_contract_clean_child_then_final_gate_pass' {
    $F = New-Fixture; $B = Build-Baseline $F; if ($B.exit) { return @{ pass = $false; info = $B.err } }
    [void](Start-Observer $F); if (-not (Wait-Heartbeat $F 2)) { return @{ pass = $false; info = 'NO_HEARTBEAT' } }
    $R = Invoke-RunnerLoop $F 6
    $Gate = Invoke-Gate $F
    return @{ pass = ($null -eq $R.reason -and $R.child_exit -eq 0 -and $Gate.exit -eq 0 -and (Get-GatePass $F) -eq 1); info = @{ runner = $R; gate_exit = $Gate.exit } }
}

# 7. Korean path UTF-8 round trip through the baseline JSON
Test 'T07_korean_path_roundtrip' {
    $F = New-Fixture; $B = Build-Baseline $F; if ($B.exit) { return @{ pass = $false; info = $B.err } }
    $V5 = Read-V5Json $F.baseline
    $T = @($V5.roots | Where-Object { $_.role -ceq 'transcription' })[0]; $D = @($V5.roots | Where-Object { $_.role -ceq 'downloads' })[0]
    $Pass = $T.root -ceq $F.trans -and @($T.entries)[0].path -ceq $NameLecture -and [IO.File]::Exists((Join-Path $T.root @($T.entries)[0].path)) -and
        @($D.registered | Where-Object { -not [IO.File]::Exists((Join-Path $D.root $_)) }).Count -eq 0 -and @($D.registered)[0] -ceq $NameRegMp3
    return @{ pass = $Pass; info = @{ trans_entry_utf16 = (@($T.entries)[0].path.ToCharArray() | ForEach-Object { [int]$_ }) -join ',' } }
}

# 8. Path collision / reparse / audit record failure
Test 'T08a_builder_registered_case_duplicate_hold' {
    $F = New-Fixture { param($S, $F) $S.registered = @($S.registered) + @($S.registered[0].ToUpperInvariant()) }
    $B = Build-Baseline $F
    return @{ pass = ($B.exit -eq 3 -and $B.err -match 'REGISTERED_DUPLICATE' -and -not [IO.File]::Exists($F.baseline)); info = @{ exit = $B.exit; err = $B.err.Trim() } }
}
Test 'T08b_builder_registered_not_found_hold' {
    $F = New-Fixture { param($S, $F) $S.registered = @($S.registered) + @('missing.mp3') }
    $B = Build-Baseline $F
    return @{ pass = ($B.exit -eq 3 -and $B.err -match 'REGISTERED_NOT_FOUND'); info = @{ exit = $B.exit } }
}
Test 'T08c_downloads_new_junction_hold_stop' { Expect-Stop { param($F)
        $Target = Join-Path $F.base 'elsewhere'; [void][IO.Directory]::CreateDirectory($Target)
        & cmd.exe /c mklink /J (Join-Path $F.dl 'link') $Target | Out-Null } @('REPARSE_ADDED_HOLD') }
Test 'T08d_audit_record_failure_stop' { Expect-Stop { param($F)
        [IO.Directory]::Delete((Join-Path $F.state 'raw'), $true); [IO.File]::WriteAllText((Join-Path $F.state 'raw'), 'x')
        Write-Bytes (Join-Path $F.dl 'unregistered.pdf') 10 } @() 'AUDIT_RECORD_FAILED' }
Test 'T08e_registered_parent_replaced_by_junction_stop' { Expect-Stop { param($F)
        $Dir = Join-Path $F.dl ('sub\' + $NameRegDir); $Moved = Join-Path $F.base 'moved'; [IO.Directory]::Move($Dir, $Moved)
        & cmd.exe /c mklink /J $Dir $Moved | Out-Null } @('REGISTERED_REMOVED', 'REPARSE_CHANGED_HOLD') }

# 9. Final race: change just before the final verdict; stale STOP present
Test 'T09a_change_right_before_final_gate_no_pass' {
    $F = New-Fixture; $B = Build-Baseline $F; if ($B.exit) { return @{ pass = $false; info = $B.err } }
    [void](Start-Observer $F 600); if (-not (Wait-Heartbeat $F 1)) { return @{ pass = $false; info = 'NO_HEARTBEAT' } }
    $S = [IO.File]::Open($F.reg_mp3, 'Append'); $S.WriteByte(1); $S.Dispose()
    $Gate = Invoke-Gate $F
    $Stop = Get-Stop $F
    return @{ pass = ($Gate.exit -ne 0 -and (Get-GatePass $F) -eq 0 -and $null -ne $Stop -and (Get-StopKinds $Stop) -contains 'REGISTERED_MODIFIED' -and -not [IO.File]::Exists((Join-Path $F.state 'OBSERVER_STOPPED.json'))); info = @{ gate_exit = $Gate.exit; gate = $Gate.out.Trim() } }
}
Test 'T09b_stop_record_present_gate_refuses' {
    $F = New-Fixture; $B = Build-Baseline $F; if ($B.exit) { return @{ pass = $false; info = $B.err } }
    [void](Start-Observer $F 600); if (-not (Wait-Heartbeat $F 1)) { return @{ pass = $false; info = 'NO_HEARTBEAT' } }
    Write-V5JsonNew (Join-Path $F.state 'OBSERVER_STOP_REQUIRED_external.json') @{ reason = 'SIMULATED' }
    $Gate = Invoke-Gate $F
    Stop-Observer $F
    return @{ pass = ($Gate.exit -ne 0 -and (Get-GatePass $F) -eq 0 -and $Gate.out -match 'STOP_REQUIRED_PRESENT'); info = @{ gate_exit = $Gate.exit } }
}

foreach ($Base in $Fixtures) {
    foreach ($Link in @((Join-Path $Base 'Downloads\link'), (Join-Path $Base ('Downloads\sub\' + $NameRegDir)))) {
        if ([IO.Directory]::Exists($Link) -and ((New-Object IO.DirectoryInfo($Link)).Attributes -band [IO.FileAttributes]::ReparsePoint)) { [IO.Directory]::Delete($Link) }
    }
    if ([IO.Directory]::Exists($Base)) { [IO.Directory]::Delete($Base, $true) }
}
$Failed = @($Results | Where-Object { -not $_.pass }).Count
Write-V5JsonNew $ReportPath ([ordered]@{ at_utc = [DateTime]::UtcNow.ToString('o'); powershell = $PSVersionTable.PSVersion.ToString(); edition = $PSVersionTable.PSEdition; passed = $Results.Count - $Failed; failed = $Failed; results = @($Results.ToArray()) })
[Console]::Out.WriteLine(('TOTAL {0} PASS / {1} FAIL' -f ($Results.Count - $Failed), $Failed))
if ($Failed) { exit 1 }
