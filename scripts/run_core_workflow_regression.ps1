Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Python = Join-Path $RepoRoot 'venv\Scripts\python.exe'

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
            throw "Command failed with exit code $LASTEXITCODE`: $Command $($Arguments -join ' ')"
        }
    }
    finally {
        Pop-Location
    }
}

if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Repository virtual environment Python was not found: $Python"
}

Write-Host '[1/7] Root release contract tests'
Invoke-Checked -WorkingDirectory $RepoRoot -Command $Python -Arguments @('-m', 'pytest', 'tests', '-q')

Write-Host '[2/7] Backend full pytest'
Invoke-Checked -WorkingDirectory (Join-Path $RepoRoot 'backend') -Command $Python -Arguments @('-m', 'pytest', 'tests', '-q')

$Frontend = Join-Path $RepoRoot 'frontend'
Write-Host '[3/7] Frontend lint'
Invoke-Checked -WorkingDirectory $Frontend -Command 'npm.cmd' -Arguments @('run', 'lint')

Write-Host '[4/7] Frontend typecheck'
Invoke-Checked -WorkingDirectory $Frontend -Command 'npm.cmd' -Arguments @('run', 'typecheck')

Write-Host '[5/7] Frontend build'
Invoke-Checked -WorkingDirectory $Frontend -Command 'npm.cmd' -Arguments @('run', 'build')

$Tauri = Join-Path $Frontend 'src-tauri'
Write-Host '[6/7] Rust cargo test'
Invoke-Checked -WorkingDirectory $Tauri -Command 'cargo.exe' -Arguments @('test')

Write-Host '[7/7] Regression summary'
Write-Host 'CORE WORKFLOW AUTOMATED REGRESSION: PASS'
