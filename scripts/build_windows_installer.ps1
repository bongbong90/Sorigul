#Requires -Version 5.1
<#
.SYNOPSIS
    Builds an MSI and reports only the single artifact produced this run.

.DESCRIPTION
    Builds and validates the sidecar transaction first, requires its provenance
    manifest, records MSI inventory before and after Tauri, and refuses stale or
    ambiguous installer artifacts.
#>

$ErrorActionPreference = "Stop"

function Write-Step($Message) {
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Get-MsiInventory($Directory) {
    if (-not (Test-Path -LiteralPath $Directory -PathType Container)) {
        return @()
    }
    return @(
        Get-ChildItem -LiteralPath $Directory -Filter "*.msi" -File |
        Sort-Object -Property FullName |
        ForEach-Object {
            [pscustomobject]@{
                FullName = $_.FullName
                Length = [long]$_.Length
                LastWriteTimeUtc = $_.LastWriteTimeUtc
                SHA256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
            }
        }
    )
}

$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path -LiteralPath (Join-Path $RepoRoot "backend\src\main.py"))) {
    Write-Error "Could not confirm repository root (backend\src\main.py not found under '$RepoRoot')."
    exit 1
}
Set-Location $RepoRoot

Write-Step "Checking required third-party notice/license files"
$RequiredNotices = @(
    "third_party\THIRD_PARTY_NOTICES.txt",
    "third_party\licenses\ffmpeg-gpl-3.0.txt",
    "third_party\licenses\imageio-ffmpeg-bsd-2-clause.txt"
)
$MissingNotices = @(
    $RequiredNotices | Where-Object {
        -not (Test-Path -LiteralPath (Join-Path $RepoRoot $_) -PathType Leaf)
    }
)
if ($MissingNotices.Count -ne 0) {
    Write-Error "Missing required third-party notice/license file(s): $($MissingNotices -join ', ')."
    exit 1
}

Write-Step "Building + validating the isolated backend sidecar candidate"
& (Join-Path $PSScriptRoot "build_backend_sidecar.ps1")
if ($LASTEXITCODE -ne 0) {
    Write-Error "Sidecar build/self-test failed (exit $LASTEXITCODE). Stopping before frontend/Tauri build."
    exit $LASTEXITCODE
}

$BinariesDir = Join-Path $RepoRoot "frontend\src-tauri\binaries"
$ManifestPath = Join-Path $BinariesDir "sorigul-build-manifest.json"
$StagedSidecar = Join-Path $BinariesDir "sorigul-backend.exe"
$StagedFfmpeg = Join-Path $BinariesDir "ffmpeg.exe"
if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) {
    Write-Error "BUILD_MANIFEST_MISSING: $ManifestPath"
    exit 1
}
try {
    $Manifest = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
} catch {
    Write-Error "BUILD_MANIFEST_INVALID: $($_.Exception.Message)"
    exit 1
}
if (-not $Manifest.tracked_tree_clean -or [string]::IsNullOrWhiteSpace($Manifest.source_head)) {
    Write-Error "BUILD_MANIFEST_NOT_RELEASE_ELIGIBLE"
    exit 1
}
$ActualSidecarHash = (Get-FileHash -LiteralPath $StagedSidecar -Algorithm SHA256).Hash.ToLowerInvariant()
$ActualFfmpegHash = (Get-FileHash -LiteralPath $StagedFfmpeg -Algorithm SHA256).Hash.ToLowerInvariant()
if ($ActualSidecarHash -ne $Manifest.sidecar_sha256 -or $ActualFfmpegHash -ne $Manifest.ffmpeg_sha256) {
    Write-Error "BUILD_MANIFEST_ARTIFACT_MISMATCH"
    exit 1
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
    cargo check --locked
    if ($LASTEXITCODE -ne 0) { throw "cargo check failed (exit $LASTEXITCODE)" }
    cargo clippy --locked --all-targets -- -D warnings
    if ($LASTEXITCODE -ne 0) { throw "cargo clippy failed (exit $LASTEXITCODE)" }
    cargo test --locked
    if ($LASTEXITCODE -ne 0) { throw "cargo test failed (exit $LASTEXITCODE)" }
} finally {
    Pop-Location
}

$MsiDir = Join-Path $TauriDir "target\release\bundle\msi"
$PreBuildMsiInventory = @(Get-MsiInventory $MsiDir)
$TauriBuildStartUtc = [DateTime]::UtcNow
Write-Step "Building Windows MSI (release-only Tauri config)"
Push-Location $FrontendDir
try {
    npx.cmd --no-install tauri build --config "src-tauri\tauri.release.conf.json" --bundles msi
    if ($LASTEXITCODE -ne 0) { throw "tauri build failed (exit $LASTEXITCODE)" }
} finally {
    Pop-Location
}
$PostBuildMsiInventory = @(Get-MsiInventory $MsiDir)

$CurrentRunMsiCandidates = @(
    foreach ($PostItem in $PostBuildMsiInventory) {
        $PreItem = @($PreBuildMsiInventory | Where-Object { $_.FullName -eq $PostItem.FullName })
        $IsNew = $PreItem.Count -eq 0
        $IsChanged = $false
        if ($PreItem.Count -eq 1) {
            $IsChanged = (
                $PreItem[0].Length -ne $PostItem.Length -or
                $PreItem[0].LastWriteTimeUtc -ne $PostItem.LastWriteTimeUtc -or
                $PreItem[0].SHA256 -ne $PostItem.SHA256
            )
        }
        if (($IsNew -or $IsChanged) -and $PostItem.LastWriteTimeUtc -ge $TauriBuildStartUtc) {
            $PostItem
        }
    }
)
if ($CurrentRunMsiCandidates.Count -eq 0) {
    Write-Error "MSI_CURRENT_RUN_ARTIFACT_MISSING"
    exit 1
}
if ($CurrentRunMsiCandidates.Count -ne 1) {
    Write-Error "MSI_CURRENT_RUN_ARTIFACT_AMBIGUOUS: $($CurrentRunMsiCandidates.Count) candidates"
    exit 1
}
$Msi = $CurrentRunMsiCandidates[0]

Write-Host ""
Write-Host "Source HEAD: $($Manifest.source_head)"
Write-Host "Manifest sidecar SHA-256: $($Manifest.sidecar_sha256)"
Write-Host "Manifest ffmpeg SHA-256: $($Manifest.ffmpeg_sha256)"
Write-Host "Fresh MSI artifact: $($Msi.FullName)"
Write-Host ("Fresh MSI size: {0:N0} bytes" -f $Msi.Length)
Write-Host "Fresh MSI SHA-256: $($Msi.SHA256)"
Write-Host "Windows installer build PASSED." -ForegroundColor Green
