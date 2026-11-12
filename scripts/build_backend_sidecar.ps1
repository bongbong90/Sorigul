#Requires -Version 5.1
<#
.SYNOPSIS
    Builds the standalone Sorigul backend sidecar executable and stages it
    (with a bundled ffmpeg) into frontend/src-tauri/binaries/, ready for
    `tauri build`'s bundle.resources.

.DESCRIPTION
    1. Confirms repository root.
    2. Confirms the Python venv exists (created separately -- this script
       does not create one from scratch, to avoid silently picking a wrong
       system Python).
    3. Installs/verifies packaging + application runtime requirements.
    4. Runs a clean PyInstaller build from backend/packaging/sorigul_backend.spec.
    5. Verifies the produced executable exists.
    6. Copies sorigul-backend.exe into frontend/src-tauri/binaries/.
    7. Stages a bundled ffmpeg.exe (via the imageio-ffmpeg package) next to it.
    8. Prints SHA-256 + size for both.
    9. Runs `sorigul-backend.exe --self-test` from its staged location (so
       the self-test also exercises the bundled ffmpeg it will actually run
       against) and fails the build on a non-zero exit code.

    Only ever deletes the unique temp build/dist root it created itself
    this run (under $env:TEMP\Sorigul_PyInstaller_<guid>) -- never
    backend/packaging/build, backend/packaging/dist, or any other
    unrelated/pre-existing directory.

.EXAMPLE
    pwsh -File scripts/build_backend_sidecar.ps1
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

$VenvPython = Join-Path $RepoRoot "venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Error "Python venv not found at '$VenvPython'. Create it first (python -m venv venv) before running this script."
    exit 1
}

Write-Step "Installing/verifying backend + packaging requirements"
& $VenvPython -m pip install --no-cache-dir -r "backend\requirements.txt"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $VenvPython -m pip install --no-cache-dir -r "backend\requirements-whisper.txt"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $VenvPython -m pip install --no-cache-dir -r "tools\requirements-packaging.txt"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$Uid = [guid]::NewGuid().ToString().Substring(0,8)
$TempRoot = Join-Path $env:TEMP "Sorigul_PyInstaller_$Uid"
$BuildDir = Join-Path $TempRoot "build"
$DistDir = Join-Path $TempRoot "dist"
New-Item -ItemType Directory -Force -Path $BuildDir | Out-Null
New-Item -ItemType Directory -Force -Path $DistDir | Out-Null

Write-Step "Running PyInstaller (backend/packaging/sorigul_backend.spec)"
& $VenvPython -m PyInstaller --clean --noconfirm `
    --distpath $DistDir `
    --workpath $BuildDir `
    "backend\packaging\sorigul_backend.spec"
if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller build failed (exit $LASTEXITCODE)."
    exit $LASTEXITCODE
}

$BuiltExe = Join-Path $DistDir "sorigul-backend.exe"
if (-not (Test-Path $BuiltExe)) {
    Write-Error "Expected build output not found: $BuiltExe"
    exit 1
}

$BinariesDir = Join-Path $RepoRoot "frontend\src-tauri\binaries"
New-Item -ItemType Directory -Force -Path $BinariesDir | Out-Null

$StagedExe = Join-Path $BinariesDir "sorigul-backend.exe"
Write-Step "Staging sorigul-backend.exe -> $StagedExe"
Copy-Item -Force $BuiltExe $StagedExe

Write-Step "Staging bundled ffmpeg (via imageio-ffmpeg)"
$FfmpegSourceScript = @"
import imageio_ffmpeg
print(imageio_ffmpeg.get_ffmpeg_exe())
"@
$FfmpegSource = (& $VenvPython -c $FfmpegSourceScript).Trim()
if (-not (Test-Path $FfmpegSource)) {
    Write-Error "imageio-ffmpeg did not resolve a usable ffmpeg executable (got '$FfmpegSource')."
    exit 1
}
$StagedFfmpeg = Join-Path $BinariesDir "ffmpeg.exe"
Copy-Item -Force $FfmpegSource $StagedFfmpeg

function Write-FileReport($path, $label) {
    $item = Get-Item $path
    $hash = (Get-FileHash -Path $path -Algorithm SHA256).Hash.ToLower()
    Write-Host ("{0}: {1}" -f $label, $path)
    Write-Host ("  size:   {0:N0} bytes" -f $item.Length)
    Write-Host ("  sha256: {0}" -f $hash)
}

Write-FileReport $StagedExe "sorigul-backend.exe"
Write-FileReport $StagedFfmpeg "ffmpeg.exe"

Write-Step "Running staged self-test (sorigul-backend.exe --self-test)"
Push-Location $BinariesDir
try {
    & ".\sorigul-backend.exe" --self-test
    $SelfTestExit = $LASTEXITCODE
} finally {
    Pop-Location
}

$SelfTestLog = Join-Path $BinariesDir "sorigul-backend-selftest.log"
if (Test-Path $SelfTestLog) {
    Write-Host "--- self-test log ---"
    Get-Content $SelfTestLog | Write-Host
}

if ($SelfTestExit -ne 0) {
    Write-Error "Packaged backend self-test failed (exit $SelfTestExit). See log above."
    exit $SelfTestExit
}

Write-Host ""
Write-Host "Sidecar build + self-test PASSED." -ForegroundColor Green

if (Test-Path $TempRoot) { Remove-Item -Recurse -Force $TempRoot }
