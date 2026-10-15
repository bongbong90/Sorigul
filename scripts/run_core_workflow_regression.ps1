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

$Frontend = Join-Path $RepoRoot 'frontend'
$Tauri = Join-Path $Frontend 'src-tauri'
$OriginalCargoNetOffline = [Environment]::GetEnvironmentVariable('CARGO_NET_OFFLINE', 'Process')

try {
    # Existing environments only. Cargo cache misses are blockers and must
    # never trigger an automatic dependency download.
    $env:CARGO_NET_OFFLINE = 'true'

    Write-Host '[1/10] Root release/readiness tests'
    Invoke-Checked -WorkingDirectory $RepoRoot -Command $Python -Arguments @('-m', 'pytest', 'tests', '-q')

    Write-Host '[2/10] Backend full pytest'
    Invoke-Checked -WorkingDirectory (Join-Path $RepoRoot 'backend') -Command $Python -Arguments @('-m', 'pytest', 'tests', '-q')

    Write-Host '[3/10] Frontend lint'
    Invoke-Checked -WorkingDirectory $Frontend -Command 'npm.cmd' -Arguments @('run', 'lint')

    Write-Host '[4/10] Frontend typecheck'
    Invoke-Checked -WorkingDirectory $Frontend -Command 'npm.cmd' -Arguments @('run', 'typecheck')

    Write-Host '[5/10] Frontend production build'
    Invoke-Checked -WorkingDirectory $Frontend -Command 'npm.cmd' -Arguments @('run', 'build')

    Write-Host '[6/10] Rust format'
    Invoke-Checked -WorkingDirectory $Tauri -Command 'cargo.exe' -Arguments @('fmt', '--check')

    Write-Host '[7/10] Rust check (locked, offline)'
    Invoke-Checked -WorkingDirectory $Tauri -Command 'cargo.exe' -Arguments @('check', '--locked')

    Write-Host '[8/10] Rust clippy (locked, offline, warnings denied)'
    Invoke-Checked -WorkingDirectory $Tauri -Command 'cargo.exe' -Arguments @('clippy', '--locked', '--all-targets', '--', '-D', 'warnings')

    Write-Host '[9/10] Rust tests (locked, offline)'
    Invoke-Checked -WorkingDirectory $Tauri -Command 'cargo.exe' -Arguments @('test', '--locked')

    Write-Host '[10/10] Git whitespace/status summary'
    Invoke-Checked -WorkingDirectory $RepoRoot -Command 'git.exe' -Arguments @('diff', '--check')
    Invoke-Checked -WorkingDirectory $RepoRoot -Command 'git.exe' -Arguments @('status', '--short')

    Write-Host 'CORE WORKFLOW SOURCE REGRESSION: LOCAL PASS'
}
finally {
    if ($null -eq $OriginalCargoNetOffline) {
        [Environment]::SetEnvironmentVariable('CARGO_NET_OFFLINE', $null, 'Process')
    }
    else {
        [Environment]::SetEnvironmentVariable('CARGO_NET_OFFLINE', $OriginalCargoNetOffline, 'Process')
    }
}
