# Only execute the synthetic GUI on the authorized GitHub-hosted run.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
function Read-WebDiagnostic {
    param([Parameter(Mandatory=$true)][string]$Path)
    if ((Get-Item -LiteralPath $Path).Length -gt 32768) { throw 'Diagnostic size rejected' }
    $d = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    $boolKeys = 'initialized navigation_requested navigation_completed_success navigation_source_match navigation_cancelled dom_loaded doc_ready doc_button_exists doc_source_match doc_nonce_match legacy_message_match legacy_source_match click_diag_received click_source_match click_nonce_match event_trusted uia_started uia_found uia_usable uia_name_match uia_offscreen uia_rect_valid focus_view focus_foreground cursor_attempted cursor_success sendinput_attempted clicked legacy_trusted legacy_predicate diagnostic_pass'.Split(' ')
    $countKeys = 'navigation_start_count navigation_complete_count dom_count webmessage_count document_ready_count click_diag_count diagnostic_parse_errors uia_polls'.Split(' ')
    $integerKeys = 'nav_start_id nav_complete_id dom_nav_id nav_error uia_control_type sendinput_requested sendinput_return struct_size cursor_last_error sendinput_last_error'.Split(' ')
    $coordinateKeys = 'rect_x rect_y rect_width rect_height target_x target_y'.Split(' ')
    $timeKeys = 'initialized_ms navigate_ms navigation_start_ms navigation_complete_ms dom_ms document_ready_ms uia_start_ms uia_end_ms input_ms cursor_ms sendinput_ms message_ms click_ms verdict_ms'.Split(' ')
    $stringKeys = @('skip_reason','ready_state','exception_type','snapshot_reason')
    $allowed = @('schema','events') + $boolKeys + $countKeys + $integerKeys + $coordinateKeys + $timeKeys + $stringKeys
    $actual = @($d.PSObject.Properties.Name)
    if (($d.schema -isnot [int] -and $d.schema -isnot [long]) -or $d.schema -ne 2 -or $actual.Count -ne $allowed.Count) { throw 'Diagnostic schema rejected' }
    foreach ($key in $actual) { if ($allowed -cnotcontains $key) { throw 'Unknown diagnostic field' } }
    foreach ($key in $boolKeys) { if ($null -ne $d.$key -and $d.$key -isnot [bool]) { throw 'Diagnostic boolean rejected' } }
    foreach ($key in ($countKeys + $integerKeys + $coordinateKeys + $timeKeys)) {
        $v = $d.$key
        if ($null -eq $v) { if ($countKeys -contains $key) { throw 'Missing diagnostic counter' }; continue }
        if ($v -isnot [int] -and $v -isnot [long] -and $v -isnot [double] -and $v -isnot [decimal]) { throw 'Diagnostic number rejected' }
        $n = [double]$v
        if ([double]::IsNaN($n) -or [double]::IsInfinity($n)) { throw 'Nonfinite diagnostic number' }
        if ($coordinateKeys -contains $key) { if ([math]::Abs($n) -gt 65536) { throw 'Coordinate out of range' } }
        elseif ($timeKeys -contains $key) { if ($n -lt 0 -or $n -gt 180000 -or $n -ne [math]::Truncate($n)) { throw 'Time out of range' } }
        else { if ($n -lt 0 -or $n -gt 9007199254740991 -or $n -ne [math]::Truncate($n)) { throw 'Integer out of range' } }
        if ($countKeys -contains $key -and $n -gt 1000000) { throw 'Counter out of range' }
    }
    if (@('not_reached','uia_timeout','null_element','offscreen','invalid_rectangle','cursor_failed','sendinput_incomplete','none','exception') -cnotcontains $d.skip_reason) { throw 'Skip reason rejected' }
    if ($null -ne $d.ready_state -and @('loading','interactive','complete') -cnotcontains $d.ready_state) { throw 'Ready state rejected' }
    if (@('verdict','exception') -cnotcontains $d.snapshot_reason) { throw 'Snapshot reason rejected' }
    if ($null -ne $d.exception_type -and ($d.exception_type -isnot [string] -or $d.exception_type -cnotmatch '^[A-Za-z][A-Za-z0-9]{0,79}$')) { throw 'Exception type rejected' }
    if ($d.events -isnot [array] -or $d.events.Count -gt 16) { throw 'Event list rejected' }
    foreach ($event in $d.events) {
        if (@($event.PSObject.Properties).Count -ne 2 -or @($event.PSObject.Properties.Name | Where-Object { $_ -cnotin @('phase','ms') }).Count -ne 0) { throw 'Event schema rejected' }
        if (@('initialized','navigate','navigation_start','navigation_complete','dom','document_ready','message','uia_start','uia_end','input','cursor','sendinput','click','verdict') -cnotcontains $event.phase) { throw 'Event phase rejected' }
        if (($event.ms -isnot [int] -and $event.ms -isnot [long]) -or $event.ms -lt 0 -or $event.ms -gt 180000) { throw 'Event time rejected' }
    }
    return $d
}
function Get-ObservedVerdict {
    param($Value)
    if ($null -eq $Value) { return 'NOT VERIFIED' }
    if ($Value -eq $true) { return 'PASS' }
    return 'FAIL'
}
if ($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted' -or
    $env:GITHUB_REPOSITORY -ne 'bongbong90/Sorigul' -or $env:GITHUB_EVENT_NAME -ne 'push' -or
    $env:GITHUB_REF -ne 'refs/heads/qa/59-webview2-input-diagnostic-once' -or $env:GITHUB_RUN_ATTEMPT -ne '1') {
    throw 'Authorized hosted push/first-attempt context required.'
}
$report = [ordered]@{
    schema = 2
    run_id = $env:GITHUB_RUN_ID
    commit = $env:GITHUB_SHA
    os_image = $env:ImageOS
    image_version = $env:ImageVersion
    'GUI SESSION ACCESS' = 'FAIL'
    'SYNTHETIC WEBVIEW2 INTERACTION' = 'FAIL'
    'SYNTHETIC TRAY INTERACTION' = 'NOT VERIFIED'
    'CANDIDATE MSI USED' = 'NO'
    'HOST INSTALLATION PRESERVED' = 'PASS'
    cleanup_verified = $false
    'NAVIGATION COMPLETED' = 'NOT VERIFIED'
    'DOCUMENT READY' = 'NOT VERIFIED'
    'UIA BUTTON FOUND' = 'NOT VERIFIED'
    'SENDINPUT COUNT' = 'NOT VERIFIED'
    'WEB MESSAGE RECEIVED' = 'NOT VERIFIED'
    'TRUSTED CLICK VERIFIED' = 'NOT VERIFIED'
    'ROOT CAUSE' = 'NOT VERIFIED'
}
$work = Join-Path $env:RUNNER_TEMP ('qa59-' + [guid]::NewGuid().ToString('N'))
$null = New-Item -ItemType Directory -Path $work
$job = $null
$known = [Collections.Generic.HashSet[int]]::new()
try {
    $os = Get-CimInstance Win32_OperatingSystem
    $report.os_caption = $os.Caption
    $report.os_version = $os.Version
    $report.cpu_logical = [Environment]::ProcessorCount
    $report.ram_gib = [math]::Round($os.TotalVisibleMemorySize / 1MB, 1)
    $report.free_disk_gib = [math]::Round((Get-PSDrive -Name ([IO.Path]::GetPathRoot($work).Substring(0,1))).Free / 1GB, 1)
    $runtimeFiles = @(Get-Item -Path (Join-Path ${env:ProgramFiles(x86)} 'Microsoft/EdgeWebView/Application/*/msedgewebview2.exe') -ErrorAction SilentlyContinue)
    $report.installed_webview_runtime_versions = @($runtimeFiles | ForEach-Object { $_.VersionInfo.ProductVersion })
    $report.installed_webview_runtime_files = $runtimeFiles.Count
    $driver = Get-Command msedgedriver.exe -ErrorAction SilentlyContinue
    if (!$driver -and $env:EDGEWEBDRIVER) {
        $candidateDriver = Join-Path $env:EDGEWEBDRIVER 'msedgedriver.exe'
        if (Test-Path -LiteralPath $candidateDriver) { $driver = [pscustomobject]@{ Source = $candidateDriver } }
    }
    if ($driver) { $report.edge_driver_version = (Get-Item -LiteralPath $driver.Source).VersionInfo.ProductVersion }
    else { $report.edge_driver_version = 'NOT FOUND' }
    $report.driver_compatibility = 'NOT VERIFIED; driver unused; UIAutomation plus native SendInput route'
    $sdkReady = $false
    try {
        $package = Join-Path $work 'webview2.zip'
        Invoke-WebRequest -UseBasicParsing -TimeoutSec 60 -Uri 'https://api.nuget.org/v3-flatcontainer/microsoft.web.webview2/1.0.2903.40/microsoft.web.webview2.1.0.2903.40.nupkg' -OutFile $package
        $hash = (Get-FileHash $package -Algorithm SHA256).Hash
        if ($hash -ne 'EF128016DD1E51C59178C827ED5B8AA3322C57AFA8675D930F8109505542AD74') { throw 'SDK integrity mismatch' }
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $sdk = Join-Path $work 'sdk'
        [IO.Compression.ZipFile]::ExtractToDirectory($package, $sdk)
        $loader = Join-Path $sdk 'runtimes/win-x64/native/WebView2Loader.dll'
        $sig = Get-AuthenticodeSignature $loader
        if ($sig.Status -ne 'Valid' -or $sig.SignerCertificate.Subject -notmatch '^CN=Microsoft Corporation,') { throw 'Microsoft signature unverified' }
        Copy-Item -LiteralPath $loader -Destination $work
        Copy-Item -LiteralPath (Join-Path $sdk 'lib/net462/Microsoft.Web.WebView2.Core.dll') -Destination $work
        Copy-Item -LiteralPath (Join-Path $sdk 'lib/net462/Microsoft.Web.WebView2.WinForms.dll') -Destination $work
        $report.sdk_version = '1.0.2903.40'
        $report.sdk_sha256 = $hash
        $report.loader_signature = 'Valid / Microsoft Corporation'
        $sdkReady = $true
    } catch { $report.sdk_preparation = 'NOT VERIFIED'; $report.sdk_error_type = $_.Exception.GetType().Name }

    $framework = Join-Path $env:WINDIR 'Microsoft.NET/Framework64/v4.0.30319'
    $csc = Join-Path $framework 'csc.exe'
    $uia = Join-Path $env:WINDIR 'Microsoft.NET/Framework64/v4.0.30319/WPF'
    $refs = @('/r:System.Windows.Forms.dll', '/r:System.Drawing.dll', '/r:System.Web.Extensions.dll',
        ('/r:' + (Join-Path $uia 'UIAutomationClient.dll')), ('/r:' + (Join-Path $uia 'UIAutomationTypes.dll')),
        ('/r:' + (Join-Path $uia 'WindowsBase.dll')))
    $hostExe = Join-Path $work 'QA59Synthetic.exe'
    $compilerLog = & $csc /nologo /target:winexe /platform:x64 ('/out:' + $hostExe) $refs (Join-Path $PSScriptRoot 'ProbeHost.cs') 2>&1
    if ($LASTEXITCODE -ne 0) { throw 'Synthetic host compile failed' }
    if ($sdkReady) {
        $pluginRefs = $refs + @(('/r:' + $hostExe), ('/r:' + (Join-Path $work 'Microsoft.Web.WebView2.Core.dll')), ('/r:' + (Join-Path $work 'Microsoft.Web.WebView2.WinForms.dll')))
        $compilerLog = & $csc /nologo /target:library /platform:x64 ('/out:' + (Join-Path $work 'WebProbe.dll')) $pluginRefs (Join-Path $PSScriptRoot 'WebProbe.cs') 2>&1
        if ($LASTEXITCODE -ne 0) { $report.webview_compile = 'NOT VERIFIED' }
    }
    Add-Type -Path (Join-Path $PSScriptRoot 'OwnedJob.cs')
    # Scope these removals to this QA step process and its children. No host settings change.
    foreach ($name in @('WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS', 'WEBVIEW2_BROWSER_EXECUTABLE_FOLDER',
        'WEBVIEW2_USER_DATA_FOLDER', 'WEBVIEW2_PIPE_FOR_SCRIPT_DEBUGGER', 'WEBVIEW2_WAIT_FOR_SCRIPT_DEBUGGER')) {
        [Environment]::SetEnvironmentVariable($name, $null, 'Process')
    }
    $job = [OwnedJob]::new()
    $job.Start($hostExe, $work)
    $watch = [Diagnostics.Stopwatch]::StartNew()
    while ($job.ExitCode -eq 259 -and $watch.Elapsed.TotalSeconds -lt 150) {
        foreach ($processId in $job.Pids()) { $null = $known.Add($processId) }
        Start-Sleep -Milliseconds 250
    }
    $report.host_timed_out = $job.ExitCode -eq 259
    $report.host_exit_code = $job.ExitCode
    $resultFile = Join-Path $work 'host-result.json'
    if (Test-Path -LiteralPath $resultFile) {
        $hostResult = Get-Content -LiteralPath $resultFile -Raw | ConvertFrom-Json
        foreach ($property in $hostResult.PSObject.Properties) { $report[$property.Name] = $property.Value }
    }
    $versionFile = Join-Path $work 'runtime-version.txt'
    if (Test-Path -LiteralPath $versionFile) {
        $version = (Get-Content -LiteralPath $versionFile -Raw).Trim()
        if ($version -match '^\d+\.\d+\.\d+\.\d+(?:\s.*)?$') { $report.webview_runtime_version = $version }
    }
    # Inventory only: native input is the selected route; no WebDriver session or debug port.
    if ($driver) {
        $driverVersion = $report.edge_driver_version
        $report.driver_version_match_first_three = if ($report.webview_runtime_version) { (($driverVersion.Split('.')[0..2] -join '.') -eq ($report.webview_runtime_version.Split('.')[0..2] -join '.')) } else { 'NOT VERIFIED' }
    }
} catch {
    $report.probe_error_type = $_.Exception.GetType().Name
} finally {
    try {
        $diagnosticFile = Join-Path $work 'webview-diagnostic.json'
        if (Test-Path -LiteralPath $diagnosticFile) {
            $d = Read-WebDiagnostic -Path $diagnosticFile
            $report.webview_diagnostic = $d
            $report.diagnostic_collection = 'PASS'
            $report['NAVIGATION COMPLETED'] = Get-ObservedVerdict $d.navigation_completed_success
            $report['DOCUMENT READY'] = Get-ObservedVerdict $d.doc_ready
            if ($d.uia_started -eq $true -and $null -ne $d.uia_end_ms) {
                $report['UIA BUTTON FOUND'] = if ($d.uia_found -eq $true -and $d.uia_usable -eq $true -and $d.uia_control_type -eq 50000 -and $d.uia_name_match -eq $true -and $d.uia_offscreen -eq $false -and $d.uia_rect_valid -eq $true) { 'PASS' } else { 'FAIL' }
            }
            if ($d.sendinput_attempted -eq $true -and $null -ne $d.sendinput_return) { $report['SENDINPUT COUNT'] = $d.sendinput_return }
            if ($d.initialized -eq $true -and $d.snapshot_reason -eq 'verdict') { $report['WEB MESSAGE RECEIVED'] = if ($d.webmessage_count -gt 0) { 'PASS' } else { 'FAIL' } }
            if ($null -ne $d.event_trusted) {
                $report['TRUSTED CLICK VERIFIED'] = if ($d.event_trusted -eq $true -and $d.click_source_match -eq $true -and $d.click_nonce_match -eq $true -and $d.legacy_predicate -eq $true -and $d.sendinput_return -eq 2) { 'PASS' } else { 'FAIL' }
            }
            # No diagnosis is automatically promoted to CONFIRMED from a later run.
        } else { $report.diagnostic_collection = 'NOT VERIFIED' }
    } catch {
        $report.diagnostic_collection = 'NOT VERIFIED'
        $report.diagnostic_error_type = $_.Exception.GetType().Name
        $report['SYNTHETIC WEBVIEW2 INTERACTION'] = 'FAIL'
    }
    if ($report.diagnostic_collection -ne 'PASS' -or $report['NAVIGATION COMPLETED'] -ne 'PASS' -or
        $report['DOCUMENT READY'] -ne 'PASS' -or $report['UIA BUTTON FOUND'] -ne 'PASS' -or
        $report['SENDINPUT COUNT'] -ne 2 -or $report['TRUSTED CLICK VERIFIED'] -ne 'PASS') {
        $report['SYNTHETIC WEBVIEW2 INTERACTION'] = 'FAIL'
    }
    try {
        if ($job) {
            foreach ($processId in $job.Pids()) { $null = $known.Add($processId) }
            for ($i=0; $i -lt 20 -and $job.Active -gt 0; $i++) { Start-Sleep -Milliseconds 250 }
            $report.owned_processes_before_cleanup = $job.Active
            $report.forced_owned_cleanup = $job.Active -gt 0
            if ($job.Active -gt 0) { $job.Stop(); Start-Sleep -Seconds 1 }
            $report.final_owned_processes = $job.Active
            # A provider/query failure is not evidence of zero endpoints.
            $tcp = @(Get-CimInstance -Namespace root/StandardCimv2 -ClassName MSFT_NetTCPConnection -ErrorAction Stop | Where-Object { $_.State -eq 2 -and $known.Contains([int]$_.OwningProcess) })
            $udp = @(Get-CimInstance -Namespace root/StandardCimv2 -ClassName MSFT_NetUDPEndpoint -ErrorAction Stop | Where-Object { $known.Contains([int]$_.OwningProcess) })
            $report.endpoint_queries_succeeded = $true
            $report.final_owned_tcp_listeners = $tcp.Count
            $report.final_owned_udp_endpoints = $udp.Count
            $report.cleanup_verified = $job.Active -eq 0 -and $tcp.Count -eq 0 -and $udp.Count -eq 0
        } else { $report.cleanup_verified = $true; $report.host_started = $false }
    } catch { $report.cleanup_error_type = $_.Exception.GetType().Name }
    finally { if ($job) { $job.Dispose() } }
    $report['WINDOWS RUNNER EXECUTION'] = if ($report.cleanup_verified -and $report.normal_exit -eq $true -and $report.host_exit_code -eq 0 -and !$report.host_timed_out) { 'PASS' } else { 'FAIL' }
    $report['CLOUD INSTALLED QA FEASIBILITY'] = if ($report['GUI SESSION ACCESS'] -ne 'PASS') { 'BLOCKED' }
        elseif ($report['SYNTHETIC WEBVIEW2 INTERACTION'] -eq 'PASS' -and $report['SYNTHETIC TRAY INTERACTION'] -eq 'PASS' -and $report.cleanup_verified -and $report['WINDOWS RUNNER EXECUTION'] -eq 'PASS') { 'READY' }
        else { 'PARTIAL' }
    $json = $report | ConvertTo-Json -Depth 6
    Write-Output 'QA59_RESULT_BEGIN'
    Write-Output $json
    Write-Output 'QA59_RESULT_END'
    @('```json', $json, '```') | Out-File -LiteralPath $env:GITHUB_STEP_SUMMARY -Encoding utf8 -Append
}
if ($report['WINDOWS RUNNER EXECUTION'] -ne 'PASS') { exit 1 }
