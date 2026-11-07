# Local QA only. Compiles production contracts + runtime, runs pure/model tests
# and optional disposable filesystem tests. NEVER starts a synthetic worker.
[CmdletBinding()]
param([switch]$Containment)
Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot
$work = Join-Path $here ('qa59-build-' + [guid]::NewGuid().ToString('N'))
$csc = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
$common = @('/nologo', '/noconfig', '/codepage:65001', '/warnaserror+', '/checked+', '/reference:System.dll', '/reference:System.Core.dll')
$contracts = @(Get-ChildItem -LiteralPath $here -Filter '*.cs' -File | Where-Object { $_.Name -ne 'ContractTests.cs' } | ForEach-Object { $_.FullName })
$runtime = @(Get-ChildItem -LiteralPath (Join-Path $here 'runtime') -Filter '*.cs' -File | Where-Object { $_.Name -ne 'RuntimeTests.cs' } | ForEach-Object { $_.FullName })
New-Item -ItemType Directory -Path $work | Out-Null
try {
    $dll = Join-Path $work 'Qa59Contracts.dll'
    & $csc $common /target:library ('/out:' + $dll) $contracts
    if ($LASTEXITCODE -ne 0) { throw 'CONTRACT_COMPILE_FAILED' }
    & $csc $common /target:library ('/out:' + (Join-Path $work 'Qa59Runtime.dll')) ('/reference:' + $dll) $runtime
    if ($LASTEXITCODE -ne 0) { throw 'RUNTIME_COMPILE_FAILED' }
    & $csc $common /target:exe ('/out:' + (Join-Path $work 'Qa59SyntheticWorker.exe')) (Join-Path $here 'runtime\worker\SyntheticWorker.cs')
    if ($LASTEXITCODE -ne 0) { throw 'SYNTHETIC_WORKER_COMPILE_FAILED' }
    $exe = Join-Path $work 'RuntimeTests.exe'
    & $csc $common /target:exe ('/out:' + $exe) ('/reference:' + $dll) $runtime (Join-Path $here 'runtime\RuntimeTests.cs')
    if ($LASTEXITCODE -ne 0) { throw 'RUNTIME_TEST_COMPILE_FAILED' }
    if ($Containment) { & $exe --containment } else { & $exe }
    if ($LASTEXITCODE -ne 0) { throw 'RUNTIME_TEST_FAILED' }
    Write-Output 'RUNTIME_RESULT PASS'
}
finally {
    $resolvedWork = [IO.Path]::GetFullPath($work)
    if (-not $resolvedWork.StartsWith($here + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase) -or
        [IO.Path]::GetFileName($resolvedWork) -notmatch '^qa59-build-[0-9a-f]{32}$') { throw 'QA_BUILD_CLEANUP_DENIED' }
    # Refuse recursive cleanup if any reparse point appeared in the disposable
    # build tree. Existing files outside this generated root are never removed.
    $entries = @(Get-ChildItem -LiteralPath $work -Recurse -Force)
    if (@($entries | Where-Object { ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 }).Count -gt 0) { throw 'QA_BUILD_REPARSE_CLEANUP_DENIED' }
    Remove-Item -LiteralPath $resolvedWork -Recurse -Force
}
