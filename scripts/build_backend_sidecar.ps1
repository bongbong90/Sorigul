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
& $VenvPython -m pip install --no-cache-dir -r "tools\requirements-torch-cuda.txt"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $VenvPython -m pip install --no-cache-dir -r "backend\requirements.txt"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $VenvPython -m pip install --no-cache-dir -r "backend\requirements-whisper.txt"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $VenvPython -m pip install --no-cache-dir -r "tools\requirements-packaging.txt"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Step "Validating CUDA release runtime before PyInstaller"
$CudaPreflight = @'
import torch

EXPECTED_TORCH = "2.13.0+cu130"
EXPECTED_CUDA = "13.0"

print("torch.__version__ =", torch.__version__)
print("torch.version.cuda =", torch.version.cuda)
print("torch.cuda.is_available =", torch.cuda.is_available())
print("torch.cuda.device_count =", torch.cuda.device_count())
if torch.cuda.is_available() and torch.cuda.device_count() > 0:
    print("torch.cuda.get_device_name(0) =", torch.cuda.get_device_name(0))

if torch.__version__ != EXPECTED_TORCH or torch.version.cuda != EXPECTED_CUDA:
    raise SystemExit(41)

if torch.version.cuda is None or not torch.cuda.is_available() or torch.cuda.device_count() < 1:
    raise SystemExit(42)
'@
$CudaPreflightId = [guid]::NewGuid().ToString("N")
$CudaPreflightPath = Join-Path `
    $env:TEMP `
    "Sorigul_CudaPreflight_$CudaPreflightId.py"
$CudaPreflightExit = $null
try {
    [System.IO.File]::WriteAllText(
        $CudaPreflightPath,
        $CudaPreflight,
        [System.Text.UTF8Encoding]::new($false)
    )
    & $VenvPython $CudaPreflightPath
    $CudaPreflightExit = $LASTEXITCODE
} finally {
    if (Test-Path -LiteralPath $CudaPreflightPath) {
        Remove-Item -LiteralPath $CudaPreflightPath -Force
    }
}
if ($CudaPreflightExit -eq 41) {
    Write-Error "CUDA_RELEASE_VARIANT_MISMATCH" -ErrorAction Continue
    exit $CudaPreflightExit
}
if ($CudaPreflightExit -eq 42) {
    Write-Error "CUDA_RELEASE_RUNTIME_UNAVAILABLE" -ErrorAction Continue
    exit $CudaPreflightExit
}
if ($CudaPreflightExit -ne 0) {
    Write-Error "CUDA_RELEASE_PREFLIGHT_FAILED" -ErrorAction Continue
    exit $CudaPreflightExit
}

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
$FfmpegResolverScript = @'
import os
from pathlib import Path

import imageio_ffmpeg


result_path = Path(os.environ["SORIGUL_FFMPEG_RESOLVER_RESULT"])
result_path.write_text(imageio_ffmpeg.get_ffmpeg_exe(), encoding="utf-8")
'@
$FfmpegResolverId = [guid]::NewGuid().ToString("N")
$FfmpegResolverPath = Join-Path `
    $env:TEMP `
    "Sorigul_FfmpegResolver_$FfmpegResolverId.py"
$FfmpegResultPath = Join-Path `
    $env:TEMP `
    "Sorigul_FfmpegResolver_$FfmpegResolverId.txt"
$FfmpegResultEnvironmentVariable = "SORIGUL_FFMPEG_RESOLVER_RESULT"
$FfmpegResolverExit = $null
$FfmpegSource = $null
try {
    [System.Environment]::SetEnvironmentVariable(
        $FfmpegResultEnvironmentVariable,
        $FfmpegResultPath,
        [System.EnvironmentVariableTarget]::Process
    )
    [System.IO.File]::WriteAllText(
        $FfmpegResolverPath,
        $FfmpegResolverScript,
        [System.Text.UTF8Encoding]::new($false)
    )
    & $VenvPython $FfmpegResolverPath
    $FfmpegResolverExit = $LASTEXITCODE
    if ($FfmpegResolverExit -eq 0 -and (Test-Path -LiteralPath $FfmpegResultPath -PathType Leaf)) {
        $FfmpegSource = [System.IO.File]::ReadAllText(
            $FfmpegResultPath,
            [System.Text.Encoding]::UTF8
        ).Trim()
    }
} finally {
    [System.Environment]::SetEnvironmentVariable(
        $FfmpegResultEnvironmentVariable,
        $null,
        [System.EnvironmentVariableTarget]::Process
    )
    if (Test-Path -LiteralPath $FfmpegResolverPath) {
        Remove-Item -LiteralPath $FfmpegResolverPath -Force
    }
    if (Test-Path -LiteralPath $FfmpegResultPath) {
        Remove-Item -LiteralPath $FfmpegResultPath -Force
    }
}
if ($FfmpegResolverExit -ne 0) {
    Write-Error "imageio-ffmpeg resolver failed (exit $FfmpegResolverExit)."
    exit $FfmpegResolverExit
}
if ([string]::IsNullOrWhiteSpace($FfmpegSource) -or -not (Test-Path -LiteralPath $FfmpegSource -PathType Leaf)) {
    Write-Error "imageio-ffmpeg did not resolve a usable ffmpeg executable (got '$FfmpegSource')."
    exit 1
}
$StagedFfmpeg = Join-Path $BinariesDir "ffmpeg.exe"
Copy-Item -Force $FfmpegSource $StagedFfmpeg

if (-not (Test-Path -LiteralPath $StagedExe -PathType Leaf)) {
    Write-Error "Staged backend executable not found: $StagedExe"
    exit 1
}
if (-not (Test-Path -LiteralPath $StagedFfmpeg -PathType Leaf)) {
    Write-Error "Staged ffmpeg executable not found: $StagedFfmpeg"
    exit 1
}

function Write-FileReport($path, $label) {
    $item = Get-Item $path
    $hash = (Get-FileHash -Path $path -Algorithm SHA256).Hash.ToLower()
    Write-Host ("{0}: {1}" -f $label, $path)
    Write-Host ("  size:   {0:N0} bytes" -f $item.Length)
    Write-Host ("  sha256: {0}" -f $hash)
}

Write-FileReport $StagedExe "sorigul-backend.exe"
Write-FileReport $StagedFfmpeg "ffmpeg.exe"

$SelfTestLog = Join-Path `
    $BinariesDir `
    "sorigul-backend-selftest.log"
if (Test-Path -LiteralPath $SelfTestLog) {
    Remove-Item -LiteralPath $SelfTestLog -Force
}

Write-Step "Running staged self-test (sorigul-backend.exe --self-test)"
$SelfTestProcess = Start-Process `
    -FilePath $StagedExe `
    -ArgumentList "--self-test" `
    -WorkingDirectory $BinariesDir `
    -Wait `
    -PassThru
$SelfTestExit = $SelfTestProcess.ExitCode

if (-not (Test-Path -LiteralPath $SelfTestLog -PathType Leaf)) {
    Write-Error "PACKAGED_SELFTEST_LOG_MISSING" -ErrorAction Continue
    exit 1
}

$SelfTestContent = [System.IO.File]::ReadAllText(
    $SelfTestLog,
    [System.Text.Encoding]::UTF8
)
Write-Host "--- self-test log ---"
Write-Host $SelfTestContent

$RequiredSelfTestChecks = @(
    "fastapi_app_import",
    "uvicorn_import",
    "google_drive_runtime_import",
    "whisper_import",
    "torch_import",
    "torch_cuda_build",
    "torch_cuda_available",
    "ffmpeg_availability",
    "audio_metadata_service_import",
    "runtime_path_initialization"
)
$SelfTestLines = @($SelfTestContent -split "\r?\n")
$IncompleteSelfTestChecks = @(
    foreach ($Check in $RequiredSelfTestChecks) {
        $ExpectedLine = "[self-test] ${Check}: PASS"
        $CheckPrefix = "[self-test] ${Check}:"
        $MatchingLines = @($SelfTestLines | Where-Object { $_.StartsWith($CheckPrefix) })
        if ($MatchingLines.Count -ne 1 -or $MatchingLines[0] -ne $ExpectedLine) {
            $Check
        }
    }
)
if ($IncompleteSelfTestChecks.Count -ne 0) {
    Write-Error (
        "PACKAGED_SELFTEST_INCOMPLETE: {0}" -f ($IncompleteSelfTestChecks -join ", ")
    ) -ErrorAction Continue
    exit 1
}

if ($SelfTestExit -ne 0) {
    Write-Error "Packaged backend self-test failed (exit $SelfTestExit)." -ErrorAction Continue
    exit $SelfTestExit
}

Write-Host ""
Write-Host "Sidecar build + self-test PASSED." -ForegroundColor Green

if (Test-Path $TempRoot) { Remove-Item -Recurse -Force $TempRoot }
