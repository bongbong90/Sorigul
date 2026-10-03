#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Backend = Join-Path $RepoRoot 'backend'
$Python = Join-Path $RepoRoot 'venv\Scripts\python.exe'
$CoreRegression = Join-Path $PSScriptRoot 'run_core_workflow_regression.ps1'
$SystemDirectory = [System.Environment]::SystemDirectory
$TrustedPowerShell = Join-Path $SystemDirectory 'WindowsPowerShell\v1.0\powershell.exe'
$TrustedTaskkill = Join-Path $SystemDirectory 'taskkill.exe'

function Write-Step {
    param([Parameter(Mandatory = $true)][string]$Message)
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [Parameter(Mandatory = $true)][string]$Command,
        [Parameter(Mandatory = $false)][string[]]$Arguments = @()
    )
    Push-Location $WorkingDirectory
    try {
        & $Command @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Command failed with exit code $($LASTEXITCODE): $Command $($Arguments -join ' ')"
        }
    }
    finally {
        Pop-Location
    }
}

function Get-GitSingleLine {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)
    $Output = @(& git.exe -C $RepoRoot @Arguments)
    if ($LASTEXITCODE -ne 0 -or $Output.Count -ne 1) {
        throw "Git command did not return exactly one line: git $($Arguments -join ' ')"
    }
    return [string]$Output[0].Trim()
}

function Assert-TrustedWindowsExecutable {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Label
    )
    if (
        [string]::IsNullOrWhiteSpace($SystemDirectory) -or
        -not [System.IO.Path]::IsPathRooted($Path) -or
        -not (Test-Path -LiteralPath $Path -PathType Leaf)
    ) {
        throw "$Label is unavailable at the trusted Windows system path: $Path"
    }

    $Resolved = (Resolve-Path -LiteralPath $Path).Path
    $ResolvedSystem = (Resolve-Path -LiteralPath $SystemDirectory).Path.TrimEnd('\')
    if (-not $Resolved.StartsWith($ResolvedSystem + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "$Label resolved outside the Windows system directory: $Resolved"
    }

    $Signature = Get-AuthenticodeSignature -LiteralPath $Resolved
    if ($Signature.Status -ne [System.Management.Automation.SignatureStatus]::Valid) {
        throw "$Label signature is not valid: $($Signature.Status)"
    }
}

function Assert-TrackedTreeClean {
    $TrackedStatus = @(& git.exe -C $RepoRoot status --porcelain --untracked-files=no)
    if ($LASTEXITCODE -ne 0) {
        throw 'git status failed while checking tracked-tree cleanliness.'
    }
    if ($TrackedStatus.Count -ne 0) {
        throw ("Tracked tree/index is not clean:" + [Environment]::NewLine + ($TrackedStatus -join [Environment]::NewLine))
    }

    & git.exe -C $RepoRoot diff --check
    if ($LASTEXITCODE -ne 0) {
        throw 'git diff --check failed.'
    }
    & git.exe -C $RepoRoot diff --cached --check
    if ($LASTEXITCODE -ne 0) {
        throw 'git diff --cached --check failed.'
    }
}

Write-Host 'Sorigul #113 canonical pre-build rehearsal'
Write-Host 'This script does not build Local/Core/MSI artifacts and does not install/uninstall Sorigul.'

Write-Step '[1/6] Repository identity and tracked-tree preconditions'
if (-not (Test-Path -LiteralPath (Join-Path $RepoRoot 'backend\src\main.py') -PathType Leaf)) {
    throw "Could not confirm repository root: $RepoRoot"
}
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Repository virtual environment Python was not found: $Python"
}
if (-not (Test-Path -LiteralPath $CoreRegression -PathType Leaf)) {
    throw "Canonical core regression script was not found: $CoreRegression"
}
$Head = Get-GitSingleLine -Arguments @('rev-parse', 'HEAD')
$Upstream = Get-GitSingleLine -Arguments @('rev-parse', '@{u}')
if ($Head -cne $Upstream) {
    throw "Local HEAD/upstream mismatch: local=$Head upstream=$Upstream"
}
Assert-TrackedTreeClean
Write-Host "HEAD: $Head"

Write-Step '[2/6] Trusted Windows executable boundary'
Assert-TrustedWindowsExecutable -Path $TrustedPowerShell -Label 'Windows PowerShell 5'
Assert-TrustedWindowsExecutable -Path $TrustedTaskkill -Label 'taskkill.exe'
$PsIdentity = @(
    & $TrustedPowerShell -NoProfile -NonInteractive -Command '[Console]::WriteLine("{0}|{1}" -f $PSVersionTable.PSVersion, $PSVersionTable.PSEdition)'
)
if ($LASTEXITCODE -ne 0 -or $PsIdentity.Count -ne 1 -or -not $PsIdentity[0].StartsWith('5.')) {
    throw "Trusted Windows PowerShell 5 identity check failed: $($PsIdentity -join ', ')"
}
if (-not $PsIdentity[0].EndsWith('|Desktop')) {
    throw "Expected Windows PowerShell Desktop edition: $($PsIdentity[0])"
}
Write-Host "PowerShell: $($PsIdentity[0])"

Write-Step '[3/6] Execution-policy snapshot (read-only)'
$PolicySnapshot = @(
    & $TrustedPowerShell -NoProfile -NonInteractive -Command 'Get-ExecutionPolicy -List | ForEach-Object { "{0}={1}" -f $_.Scope, $_.ExecutionPolicy }'
)
if ($LASTEXITCODE -ne 0) {
    throw 'Could not read Windows PowerShell execution-policy snapshot.'
}
$PolicySnapshot | ForEach-Object { Write-Host $_ }

Write-Step '[4/6] #161/#159 packaging regressions from canonical backend working directory'
$TargetedTests = @(
    'tests/test_release_packaging_contract.py',
    'tests/test_installer_powershell5_restricted_invocation.py',
    'tests/test_core_powershell5_process_observation.py'
)
Invoke-Checked -WorkingDirectory $Backend -Command $Python -Arguments (
    @('-m', 'pytest') + $TargetedTests + @('-q', '-s')
)

Write-Step '[5/6] Canonical full source regression'
Invoke-Checked -WorkingDirectory $RepoRoot -Command $TrustedPowerShell -Arguments @(
    '-NoProfile',
    '-NonInteractive',
    '-ExecutionPolicy',
    'Bypass',
    '-File',
    $CoreRegression
)

Write-Step '[6/6] Final source identity and cleanliness'
$FinalHead = Get-GitSingleLine -Arguments @('rev-parse', 'HEAD')
$FinalUpstream = Get-GitSingleLine -Arguments @('rev-parse', '@{u}')
if ($FinalHead -cne $Head -or $FinalUpstream -cne $Head) {
    throw "Source identity changed during preflight: start=$Head final=$FinalHead upstream=$FinalUpstream"
}
Assert-TrackedTreeClean

Write-Host ''
Write-Host 'Sorigul #113 PRE-BUILD REHEARSAL: PASS' -ForegroundColor Green
Write-Host "Frozen-source candidate: $Head"
Write-Host 'Only after this PASS may a new #113 artifact run_id and Single Writer session be created.'
