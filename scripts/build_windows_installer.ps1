#Requires -Version 5.1
<#
.SYNOPSIS
    Full reproducible build of the Sorigul Windows MSI installer.

.DESCRIPTION
    1. Builds + self-tests the packaged backend sidecar (build_backend_sidecar.ps1).
    2. Confirms that self-test passed (non-zero exit stops the script).
    3. Builds the frontend production bundle (npm run build).
    4. Validates the Rust/Tauri crate (fmt --check, check, clippy, test).
    5. Builds the Windows MSI via the official Tauri CLI syntax
       (`tauri build --bundles msi`), confirmed against `tauri build --help`
       rather than a guessed flag.
    6. Reports the MSI artifact path, size, and SHA-256.

    Fails fast: any step failing stops the script immediately (no partial
    "ignore and continue"). NSIS is not built here -- MSI is this project's
    required installer artifact (see docs/runtime/
    INSTALLER_INSTALLED_RUNTIME_VALIDATION.md); NSIS stays declared in
    tauri.conf.json's bundle.targets for optional future use but is not
    part of this script's PASS condition.

.EXAMPLE
    pwsh -File scripts/build_windows_installer.ps1
#>

$ErrorActionPreference = "Stop"

function Write-Step($message) {
    Write-Host "==> $message" -ForegroundColor Cyan
}

$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path (Join-Path $RepoRoot "backend\src\main.py"))) {
    Write-Error "Could not confirm repository root (backend\src\main.py not found under '$RepoRoot')."
    exit 1
}
Set-Location $RepoRoot

Write-Step "Building + self-testing the backend sidecar"
& (Join-Path $PSScriptRoot "build_backend_sidecar.ps1")
if ($LASTEXITCODE -ne 0) {
    Write-Error "Sidecar build/self-test failed (exit $LASTEXITCODE). Stopping before touching the frontend/Tauri build."
    exit $LASTEXITCODE
}

$FrontendDir = Join-Path $RepoRoot "frontend"
$TauriDir = Join-Path $FrontendDir "src-tauri"

Write-Step "Building frontend production bundle"
Push-Location $FrontendDir
try {
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "npm run build failed (exit $LASTEXITCODE)" }
} finally {
    Pop-Location
}

Write-Step "Validating Rust/Tauri crate (fmt, check, clippy, test)"
Push-Location $TauriDir
try {
    cargo fmt --check
    if ($LASTEXITCODE -ne 0) { throw "cargo fmt --check failed (exit $LASTEXITCODE)" }

    cargo check
    if ($LASTEXITCODE -ne 0) { throw "cargo check failed (exit $LASTEXITCODE)" }

    cargo clippy --all-targets -- -D warnings
    if ($LASTEXITCODE -ne 0) { throw "cargo clippy failed (exit $LASTEXITCODE)" }

    cargo test
    if ($LASTEXITCODE -ne 0) { throw "cargo test failed (exit $LASTEXITCODE)" }
} finally {
    Pop-Location
}

Write-Step "Building Windows MSI (tauri build --bundles msi)"
Push-Location $FrontendDir
try {
    npx tauri build --bundles msi
    if ($LASTEXITCODE -ne 0) { throw "tauri build failed (exit $LASTEXITCODE)" }
} finally {
    Pop-Location
}

$MsiDir = Join-Path $TauriDir "target\release\bundle\msi"
$Msi = Get-ChildItem -Path $MsiDir -Filter "*.msi" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $Msi) {
    Write-Error "No .msi artifact found under '$MsiDir'."
    exit 1
}

$Hash = (Get-FileHash -Path $Msi.FullName -Algorithm SHA256).Hash.ToLower()
Write-Host ""
Write-Host "MSI artifact: $($Msi.FullName)"
Write-Host ("Size:   {0:N0} bytes" -f $Msi.Length)
Write-Host "SHA-256: $Hash"
Write-Host ""
Write-Host "Windows installer build PASSED." -ForegroundColor Green
