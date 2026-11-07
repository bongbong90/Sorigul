# Fresh public-hosted source build and installed QA. No local-PC execution.
[CmdletBinding()]
param([string]$ProductRoot,[switch]$CompileOnly)
Set-StrictMode -Version 2.0
$ErrorActionPreference='Stop'
$here=$PSScriptRoot
$csc=Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
$common=@('/nologo','/noconfig','/codepage:65001','/warnaserror+','/checked+','/reference:System.dll','/reference:System.Core.dll')
$contracts=@(Get-ChildItem -LiteralPath $here -Filter '*.cs' -File | Where-Object Name -ne 'ContractTests.cs' | ForEach-Object FullName)
$runtime=@(Get-ChildItem -LiteralPath (Join-Path $here 'runtime') -Filter '*.cs' -File | Where-Object Name -ne 'RuntimeTests.cs' | ForEach-Object FullName)
function Compile([object[]]$arguments) {
    $messages=& $csc @arguments 2>&1
    if($LASTEXITCODE -ne 0) {
        foreach($message in $messages) { if([string]$message -match '(CS[0-9]+)') { Write-Output ('SERVER_COMPILE_ERROR '+$matches[1]) } }
        throw 'SERVER_COMPILE_FAILED'
    }
}
if(-not $CompileOnly) {
    if($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted' -or $env:ImageOS -ne 'win22' -or
        $env:QA59_PUBLIC_REPOSITORY -ne 'true' -or $env:GITHUB_REPOSITORY -ne 'bongbong90/Sorigul' -or
        $env:GITHUB_REF -ne 'refs/heads/qa/59-stage2a-local-runtime' -or $env:GITHUB_EVENT_NAME -ne 'push') { throw 'HOSTED_PRODUCT_CONTEXT_DENIED' }
    if([string]::IsNullOrEmpty($ProductRoot)) { throw 'PRODUCT_CHECKOUT_REQUIRED' }
}
$workParent=if($CompileOnly){$here}else{$env:RUNNER_TEMP}
$work=Join-Path $workParent ('qa59-server-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $work | Out-Null
$dll=Join-Path $work 'Qa59Contracts.dll'
Compile ($common+@('/target:library',('/out:'+$dll))+$contracts)
$hostExe=Join-Path $work 'InstalledServerHarness.exe'
Compile ($common+@('/target:exe',('/out:'+$hostExe),('/reference:'+$dll))+$runtime+@((Join-Path $here 'server\ProductOwnedJob.cs'),(Join-Path $here 'server\InstalledServerHarness.cs')))
$candidateTests=Join-Path $work 'RunnerCandidateTests.exe'
Compile ($common+@('/target:exe',('/out:'+$candidateTests),('/reference:'+$dll))+$runtime+@((Join-Path $here 'server\RunnerCandidateTests.cs')))
& $candidateTests $here
if($LASTEXITCODE -ne 0) { throw 'RUNNER_CANDIDATE_TESTS_FAILED' }
$wpf=Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\WPF'
$uiRefs=@('UIAutomationClient.dll','UIAutomationTypes.dll','WindowsBase.dll') | ForEach-Object { '/reference:'+(Join-Path $wpf $_) }
Compile ($common+$uiRefs+@('/target:exe',('/out:'+(Join-Path $work 'InstalledUiWorker.exe')),(Join-Path $here 'server\InstalledUiWorker.cs')))
Write-Output 'SERVER_HARNESS_COMPILE PASS'
if($CompileOnly) {
    $resolved=[IO.Path]::GetFullPath($work)
    if(-not $resolved.StartsWith($here+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase) -or [IO.Path]::GetFileName($resolved) -notmatch '^qa59-server-[0-9a-f]{32}$') { throw 'SERVER_BUILD_CLEANUP_DENIED' }
    Remove-Item -LiteralPath $resolved -Recurse -Force
    return
}
$ProductRoot=[IO.Path]::GetFullPath($ProductRoot)
$sourceHead=(& git -C $ProductRoot rev-parse HEAD).Trim()
if($LASTEXITCODE -ne 0 -or $sourceHead -ne '890364e21a4e80d2ff5185332834b4dbb67aeb01') { throw 'PRODUCT_SOURCE_HEAD_MISMATCH' }
& git -C $ProductRoot diff --quiet
if($LASTEXITCODE -ne 0) { throw 'PRODUCT_SOURCE_DIRTY' }
$pyCandidates=@(Get-ChildItem -LiteralPath (Join-Path $env:RUNNER_TOOL_CACHE 'Python') -Directory | Where-Object Name -like '3.13.*' | Sort-Object Name -Descending)
if($pyCandidates.Count -eq 0) { throw 'PYTHON_313_TOOLCACHE_MISSING' }
$python=Join-Path $pyCandidates[0].FullName 'x64\python.exe'
if(-not (Test-Path -LiteralPath $python)) { throw 'PYTHON_313_TOOLCACHE_INVALID' }
$env:QA59_PRODUCT_SOURCE=$ProductRoot
$env:QA59_BUILD_PYTHON=$python
$env:CARGO_PROFILE_DEV_DEBUG='0'
$env:CARGO_PROFILE_TEST_DEBUG='0'
$env:CARGO_INCREMENTAL='0'
$buildScript=Join-Path $work 'Build-CurrentCandidate.ps1'
$buildText=@'
$ErrorActionPreference='Stop'
Set-Location $env:QA59_PRODUCT_SOURCE
& $env:QA59_BUILD_PYTHON -m venv venv
if($LASTEXITCODE -ne 0){throw 'VENV_FAILED'}
Push-Location frontend
try { npm.cmd ci; if($LASTEXITCODE -ne 0){throw 'NPM_CI_FAILED'} } finally { Pop-Location }
& ./scripts/build_windows_installer.ps1
if($LASTEXITCODE -ne 0){throw 'CANONICAL_INSTALLER_BUILD_FAILED'}
'@
[IO.File]::WriteAllText($buildScript,$buildText,[Text.UTF8Encoding]::new($false))
$powershell=Join-Path ([Environment]::SystemDirectory) 'WindowsPowerShell\v1.0\powershell.exe'
$build=Start-Process -FilePath $powershell -ArgumentList @('-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',('"'+$buildScript+'"')) -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $work 'build.out') -RedirectStandardError (Join-Path $work 'build.err')
# Keep the actual process handle before it exits. A Start-Process object whose
# handle was never cached can lose ExitCode after a redirected child exits.
$buildHandle=$build.Handle
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class Qa59BuildExit {
 [DllImport("kernel32.dll",SetLastError=true)] private static extern bool GetExitCodeProcess(IntPtr process,out uint code);
 public static uint Read(IntPtr process) { uint code; if(!GetExitCodeProcess(process,out code)) throw new InvalidOperationException("BUILD_EXIT_QUERY_FAILED"); return code; }
}
'@
$phase='DEPENDENCIES'
$clock=[Diagnostics.Stopwatch]::StartNew()
while(-not $build.WaitForExit(30000)) {
    $tail=(Get-Content -LiteralPath (Join-Path $work 'build.out') -Tail 200 -ErrorAction SilentlyContinue) -join "`n"
    $phase=if($tail -match 'Building Windows MSI'){'RELEASE_MSI'}elseif($tail -match 'Validating Rust/Tauri'){'RUST_REGRESSION'}elseif($tail -match 'Building frontend production'){'FRONTEND'}elseif($tail -match 'Running PyInstaller'){'CORE_PACKAGE'}else{'DEPENDENCIES'}
    Write-Output ('SERVER_BUILD_RUNNING seconds='+[int]$clock.Elapsed.TotalSeconds+' phase='+$phase)
    if($clock.Elapsed.TotalMinutes -ge 45) { $build.Kill(); throw 'SERVER_BUILD_DEADLINE' }
}
$build.WaitForExit()
$buildExit=[Qa59BuildExit]::Read($buildHandle)
$build.Dispose()
Write-Output ('SERVER_BUILD_EXIT '+$buildExit)
if($buildExit -ne 0) {
    # Raw text never leaves the runner. Derive only fixed codes and public
    # compiler code numbers from bounded tails, not arbitrary redacted lines.
    Write-Output ('SERVER_BUILD_FAILURE_PHASE '+$phase)
    $knownIssues=[ordered]@{
        'cargo fmt --check failed'='RUSTFMT'
        'cargo check failed'='RUST_CHECK'
        'cargo clippy failed'='RUST_CLIPPY'
        'cargo test failed'='RUST_TEST'
        'tauri build failed'='MSI_BUNDLE'
        'npm run build failed'='FRONTEND_BUILD'
        'PyInstaller build failed'='CORE_PACKAGE'
        'No matching distribution found'='DEPENDENCY_DISTRIBUTION'
        'PACKAGED_SELFTEST_FAILED'='CORE_SELFTEST'
        'PYTHON_RELEASE_VERSION_MISMATCH'='PYTHON_VERSION'
        'TRACKED_TREE_DIRTY'='SOURCE_DIRTY'
    }
    foreach($log in @('build.err','build.out')) {
        $lines=@(Get-Content -LiteralPath (Join-Path $work $log) -Tail 300)
        foreach($line in $lines) {
            foreach($pattern in $knownIssues.Keys) {
                if(([string]$line).Contains($pattern)){Write-Output ('SERVER_BUILD_DIAG '+$knownIssues[$pattern])}
            }
            if([string]$line -match 'error(?:\[(E[0-9]{4})\]| (CS[0-9]+|C[0-9]+|LNK[0-9]+))') {
                $compilerCode=if($matches[1]){$matches[1]}else{$matches[2]}
                Write-Output ('SERVER_BUILD_COMPILER_CODE '+$compilerCode)
            }
        }
    }
    throw 'SERVER_CANONICAL_BUILD_FAILED'
}
& git -C $ProductRoot diff --quiet
if($LASTEXITCODE -ne 0) { throw 'BUILT_SOURCE_DIRTY' }
$msis=@(Get-ChildItem -LiteralPath (Join-Path $ProductRoot 'frontend\src-tauri\target\release\bundle\msi') -Filter '*.msi' -File)
if($msis.Count -ne 1) { throw 'FRESH_MSI_NOT_UNIQUE' }
$msi=Join-Path $work 'candidate.msi'
Copy-Item -LiteralPath $msis[0].FullName -Destination $msi
$binaries=Join-Path $ProductRoot 'frontend\src-tauri\binaries'
$manifestPath=Join-Path $binaries 'sorigul-build-manifest.json'
$manifest=Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if($manifest.source_head -ne $sourceHead -or $manifest.tracked_tree_clean -ne $true) { throw 'FRESH_MANIFEST_SOURCE_MISMATCH' }
$desktop=Join-Path $ProductRoot 'frontend\src-tauri\target\release\sorigul-desktop.exe'
function Hash([string]$path) { return (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() }
$candidate=[ordered]@{
    schema=1; kind='QA59_RUNNER_SOURCE_CANDIDATE'; source_head=$sourceHead; qa_head=$env:GITHUB_SHA; run_id=[long]$env:GITHUB_RUN_ID
    origin='FRESH_HOSTED_SOURCE'; source_clean=$true; original_candidate=$false
    msi_sha256=(Hash $msi); msi_size_bytes=(Get-Item -LiteralPath $msi).Length; desktop_sha256=(Hash $desktop)
    core_sha256=(Hash (Join-Path $binaries 'sorigul-backend.exe')); ffmpeg_sha256=(Hash (Join-Path $binaries 'ffmpeg.exe')); manifest_sha256=(Hash $manifestPath)
}
if($candidate.core_sha256 -ne $manifest.sidecar_sha256 -or $candidate.ffmpeg_sha256 -ne $manifest.ffmpeg_sha256) { throw 'FRESH_MANIFEST_BYTES_MISMATCH' }
[IO.File]::WriteAllText((Join-Path $work 'candidate.json'),($candidate|ConvertTo-Json -Depth 4),[Text.UTF8Encoding]::new($false))
Write-Output ('SERVER_MSI_PROVENANCE source='+$sourceHead+' qa='+$env:GITHUB_SHA+' run='+$env:GITHUB_RUN_ID+' sha256='+$candidate.msi_sha256+' bytes='+$candidate.msi_size_bytes)
$installed=Join-Path $work 'installed'
$install=Start-Process -FilePath (Join-Path ([Environment]::SystemDirectory) 'msiexec.exe') -ArgumentList @('/i',('"'+$msi+'"'),'/qn','/norestart',('INSTALLDIR="'+$installed+'"'),'/l*v',('"'+(Join-Path $work 'msi-install.log')+'"')) -WindowStyle Hidden -PassThru
$installHandle=$install.Handle
if(-not $install.WaitForExit(180000)) { $install.Kill(); throw 'SERVER_INSTALL_DEADLINE' }
$installExit=[Qa59BuildExit]::Read($installHandle)
$install.Dispose()
if($installExit -ne 0) { Write-Output ('SERVER_INSTALL_EXIT '+$installExit); throw 'SERVER_INSTALL_FAILED' }
Write-Output 'SERVER_MSI_INSTALL PASS'
& $hostExe $work $msi $installed
if($LASTEXITCODE -ne 0) { throw 'SERVER_INSTALLED_QA_FAILED' }
Write-Output 'SERVER_TEST_MSI_EPHEMERAL_ONLY NO_UPLOAD NO_CACHE'
