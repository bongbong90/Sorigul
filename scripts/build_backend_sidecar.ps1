#Requires -Version 5.1
<#
.SYNOPSIS
    Builds and validates an isolated backend sidecar candidate, then stages it.

.DESCRIPTION
    The release transaction is deliberately ordered as build, isolated
    candidate assembly, bounded self-test, manifest generation, and protected
    promotion. A failed candidate never replaces the last validated staged
    sidecar. Only this invocation's unique temp root is removed.
#>

$ErrorActionPreference = "Stop"
$SelfTestTimeoutSeconds = 300

function Write-Step($Message) {
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Get-FileMetadata($Path) {
    $Item = Get-Item -LiteralPath $Path
    [pscustomobject]@{
        size = [long]$Item.Length
        sha256 = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}

function Write-FileReport($Path, $Label) {
    $Metadata = Get-FileMetadata $Path
    Write-Host ("{0}: {1}" -f $Label, $Path)
    Write-Host ("  size:   {0:N0} bytes" -f $Metadata.size)
    Write-Host ("  sha256: {0}" -f $Metadata.sha256)
}

function Publish-StagedArtifacts($Artifacts) {
    $PromotionId = [guid]::NewGuid().ToString("N")
    $Prepared = @()
    foreach ($Artifact in $Artifacts) {
        $TargetDirectory = Split-Path -Parent $Artifact.Target
        $TargetName = Split-Path -Leaf $Artifact.Target
        $Prepared += [pscustomobject]@{
            Candidate = $Artifact.Candidate
            Target = $Artifact.Target
            Temp = Join-Path $TargetDirectory ".$TargetName.$PromotionId.new"
            Backup = Join-Path $TargetDirectory ".$TargetName.$PromotionId.backup"
            HadOriginal = Test-Path -LiteralPath $Artifact.Target -PathType Leaf
            BackupCreated = $false
            Promoted = $false
        }
    }

    $Succeeded = $false
    try {
        foreach ($Item in $Prepared) {
            Copy-Item -LiteralPath $Item.Candidate -Destination $Item.Temp
            if (-not (Test-Path -LiteralPath $Item.Temp -PathType Leaf)) {
                throw "PROMOTION_PREPARE_FAILED: $($Item.Target)"
            }
        }
        foreach ($Item in $Prepared) {
            if ($Item.HadOriginal) {
                Move-Item -LiteralPath $Item.Target -Destination $Item.Backup
                $Item.BackupCreated = $true
            }
        }
        foreach ($Item in $Prepared) {
            Move-Item -LiteralPath $Item.Temp -Destination $Item.Target
            $Item.Promoted = $true
        }
        $Succeeded = $true
    } catch {
        $PromotionError = $_.Exception.Message
        $RollbackErrors = @()
        foreach ($Item in $Prepared) {
            if ($Item.Promoted -and (Test-Path -LiteralPath $Item.Target)) {
                try {
                    Remove-Item -LiteralPath $Item.Target -Force
                } catch {
                    $RollbackErrors += $_.Exception.Message
                }
            }
        }
        foreach ($Item in $Prepared) {
            if ($Item.BackupCreated -and (Test-Path -LiteralPath $Item.Backup)) {
                try {
                    Move-Item -LiteralPath $Item.Backup -Destination $Item.Target
                } catch {
                    $RollbackErrors += $_.Exception.Message
                }
            }
        }
        if ($RollbackErrors.Count -ne 0) {
            throw "CANDIDATE_PROMOTION_ROLLBACK_FAILED: $PromotionError; rollback: $($RollbackErrors -join '; ')"
        }
        throw "CANDIDATE_PROMOTION_FAILED: $PromotionError"
    } finally {
        foreach ($Item in $Prepared) {
            if (Test-Path -LiteralPath $Item.Temp) {
                Remove-Item -LiteralPath $Item.Temp -Force
            }
            if ($Succeeded -and (Test-Path -LiteralPath $Item.Backup)) {
                Remove-Item -LiteralPath $Item.Backup -Force
            }
        }
    }
}

$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path -LiteralPath (Join-Path $RepoRoot "backend\src\main.py"))) {
    Write-Error "Could not confirm repository root (backend\src\main.py not found under '$RepoRoot')."
    exit 1
}
Set-Location $RepoRoot

$VenvPython = Join-Path $RepoRoot "venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
    Write-Error "Python venv not found at '$VenvPython'. Create it first before running this script."
    exit 1
}

$SourceHead = (& git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($SourceHead)) {
    Write-Error "SOURCE_HEAD_UNAVAILABLE"
    exit 1
}
& git diff --quiet -- .
$UnstagedTrackedDirty = $LASTEXITCODE
& git diff --cached --quiet -- .
$StagedTrackedDirty = $LASTEXITCODE
if ($UnstagedTrackedDirty -gt 1 -or $StagedTrackedDirty -gt 1) {
    Write-Error "TRACKED_TREE_CHECK_FAILED"
    exit 1
}
if ($UnstagedTrackedDirty -ne 0 -or $StagedTrackedDirty -ne 0) {
    Write-Error "TRACKED_TREE_DIRTY"
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

$InvocationId = [guid]::NewGuid().ToString("N")
$TempRoot = Join-Path $env:TEMP "Sorigul_PyInstaller_$InvocationId"
$BuildDir = Join-Path $TempRoot "build"
$DistDir = Join-Path $TempRoot "dist"
$CandidateDir = Join-Path $TempRoot "candidate"
New-Item -ItemType Directory -Path $TempRoot | Out-Null

try {
    New-Item -ItemType Directory -Path $BuildDir | Out-Null
    New-Item -ItemType Directory -Path $DistDir | Out-Null
    New-Item -ItemType Directory -Path $CandidateDir | Out-Null

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
    $CudaPreflightPath = Join-Path $TempRoot "Sorigul_CudaPreflight_$CudaPreflightId.py"
    $CudaPreflightExit = $null
    try {
        [System.IO.File]::WriteAllText(
            $CudaPreflightPath,
            $CudaPreflight,
            (New-Object System.Text.UTF8Encoding($false))
        )
        & $VenvPython $CudaPreflightPath
        $CudaPreflightExit = $LASTEXITCODE
    } finally {
        if (Test-Path -LiteralPath $CudaPreflightPath) {
            Remove-Item -LiteralPath $CudaPreflightPath -Force
        }
    }
    if ($CudaPreflightExit -eq 41) { throw "CUDA_RELEASE_VARIANT_MISMATCH" }
    if ($CudaPreflightExit -eq 42) { throw "CUDA_RELEASE_RUNTIME_UNAVAILABLE" }
    if ($CudaPreflightExit -ne 0) { throw "CUDA_RELEASE_PREFLIGHT_FAILED" }

    Write-Step "Running PyInstaller into isolated current-run output"
    & $VenvPython -m PyInstaller --clean --noconfirm `
        --distpath $DistDir `
        --workpath $BuildDir `
        "backend\packaging\sorigul_backend.spec"
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller build failed (exit $LASTEXITCODE)."
    }

    $BuiltExe = Join-Path $DistDir "sorigul-backend.exe"
    if (-not (Test-Path -LiteralPath $BuiltExe -PathType Leaf)) {
        throw "Expected build output not found: $BuiltExe"
    }
    $CandidateExe = Join-Path $CandidateDir "sorigul-backend.exe"
    Copy-Item -LiteralPath $BuiltExe -Destination $CandidateExe

    Write-Step "Resolving bundled ffmpeg into isolated candidate"
    $FfmpegResolverScript = @'
import os
from pathlib import Path

import imageio_ffmpeg

result_path = Path(os.environ["SORIGUL_FFMPEG_RESOLVER_RESULT"])
result_path.write_text(imageio_ffmpeg.get_ffmpeg_exe(), encoding="utf-8")
'@
    $FfmpegResolverId = [guid]::NewGuid().ToString("N")
    $FfmpegResolverPath = Join-Path $TempRoot "Sorigul_FfmpegResolver_$FfmpegResolverId.py"
    $FfmpegResultPath = Join-Path $TempRoot "Sorigul_FfmpegResolver_$FfmpegResolverId.txt"
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
            (New-Object System.Text.UTF8Encoding($false))
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
        throw "imageio-ffmpeg resolver failed (exit $FfmpegResolverExit)."
    }
    if ([string]::IsNullOrWhiteSpace($FfmpegSource) -or -not (Test-Path -LiteralPath $FfmpegSource -PathType Leaf)) {
        throw "imageio-ffmpeg did not resolve a usable executable."
    }
    $CandidateFfmpeg = Join-Path $CandidateDir "ffmpeg.exe"
    Copy-Item -LiteralPath $FfmpegSource -Destination $CandidateFfmpeg

    $SelfTestLog = Join-Path $CandidateDir "sorigul-backend-selftest.log"
    if (Test-Path -LiteralPath $SelfTestLog) {
        Remove-Item -LiteralPath $SelfTestLog -Force
    }

    Write-Step "Running isolated candidate self-test (timeout: $SelfTestTimeoutSeconds seconds)"
    $SelfTestProcess = Start-Process `
        -FilePath $CandidateExe `
        -ArgumentList "--self-test" `
        -WorkingDirectory $CandidateDir `
        -PassThru
    $SelfTestDeadline = [DateTime]::UtcNow.AddSeconds($SelfTestTimeoutSeconds)
    $SelfTestTimedOut = $false
    while (-not $SelfTestProcess.HasExited) {
        if ([DateTime]::UtcNow -ge $SelfTestDeadline) {
            $SelfTestTimedOut = $true
            break
        }
        Start-Sleep -Milliseconds 250
        $SelfTestProcess.Refresh()
    }
    if ($SelfTestTimedOut) {
        Write-Error "PACKAGED_SELFTEST_TIMEOUT" -ErrorAction Continue
        & taskkill.exe /PID $SelfTestProcess.Id /T /F | Out-Host
        $TaskKillExit = $LASTEXITCODE
        $Stopped = $SelfTestProcess.WaitForExit(10000)
        if ($TaskKillExit -ne 0 -or -not $Stopped) {
            throw "PACKAGED_SELFTEST_TIMEOUT_CLEANUP_FAILED: PID $($SelfTestProcess.Id)"
        }
        throw "PACKAGED_SELFTEST_TIMEOUT"
    }
    $SelfTestExit = $SelfTestProcess.ExitCode

    if (-not (Test-Path -LiteralPath $SelfTestLog -PathType Leaf)) {
        throw "PACKAGED_SELFTEST_LOG_MISSING"
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
        "torch_cuda_compute",
        "bundled_ffmpeg_execution",
        "audio_metadata_service_import",
        "runtime_path_initialization"
    )
    $SelfTestLines = @($SelfTestContent -split "\r?\n")
    $IncompleteSelfTestChecks = @(
        foreach ($Check in $RequiredSelfTestChecks) {
            $ExpectedPass = "[self-test] ${Check}: PASS"
            $PassLines = @($SelfTestLines | Where-Object { $_ -eq $ExpectedPass })
            $TerminalPrefix = "[self-test] ${Check}: "
            $TerminalLines = @(
                $SelfTestLines | Where-Object {
                    $_.StartsWith($TerminalPrefix) -and -not $_.EndsWith(": START")
                }
            )
            if ($PassLines.Count -ne 1 -or $TerminalLines.Count -ne 1) {
                $Check
            }
        }
    )
    if ($IncompleteSelfTestChecks.Count -ne 0) {
        throw "PACKAGED_SELFTEST_INCOMPLETE: $($IncompleteSelfTestChecks -join ', ')"
    }
    if ($SelfTestExit -ne 0) {
        throw "PACKAGED_SELFTEST_FAILED: exit $SelfTestExit"
    }

    $CandidateExeMetadata = Get-FileMetadata $CandidateExe
    $CandidateFfmpegMetadata = Get-FileMetadata $CandidateFfmpeg
    $TorchRequirement = (
        Get-Content -LiteralPath (Join-Path $RepoRoot "tools\requirements-torch-cuda.txt") |
        Where-Object { $_ -match '^torch==' } |
        Select-Object -First 1
    )
    if ([string]::IsNullOrWhiteSpace($TorchRequirement)) {
        throw "BUILD_MANIFEST_TORCH_REQUIREMENT_MISSING"
    }
    $CriticalInputs = [ordered]@{}
    $CriticalInputPaths = [ordered]@{
        requirements_torch_cuda = "tools\requirements-torch-cuda.txt"
        backend_requirements = "backend\requirements.txt"
        whisper_requirements = "backend\requirements-whisper.txt"
        packaging_requirements = "tools\requirements-packaging.txt"
        pyinstaller_spec = "backend\packaging\sorigul_backend.spec"
    }
    foreach ($InputName in $CriticalInputPaths.Keys) {
        $InputPath = Join-Path $RepoRoot $CriticalInputPaths[$InputName]
        $CriticalInputs[$InputName] = (Get-FileHash -LiteralPath $InputPath -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    $Manifest = [ordered]@{
        schema_version = 1
        source_head = $SourceHead
        generated_at_utc = [DateTime]::UtcNow.ToString("o")
        tracked_tree_clean = $true
        torch_requirement = $TorchRequirement
        expected_cuda = "13.0"
        sidecar_size = $CandidateExeMetadata.size
        sidecar_sha256 = $CandidateExeMetadata.sha256
        ffmpeg_size = $CandidateFfmpegMetadata.size
        ffmpeg_sha256 = $CandidateFfmpegMetadata.sha256
        release_input_sha256 = $CriticalInputs
    }
    $CandidateManifest = Join-Path $CandidateDir "sorigul-build-manifest.json"
    [System.IO.File]::WriteAllText(
        $CandidateManifest,
        ($Manifest | ConvertTo-Json -Depth 4) + "`n",
        (New-Object System.Text.UTF8Encoding($false))
    )
    if (-not (Test-Path -LiteralPath $CandidateManifest -PathType Leaf)) {
        throw "BUILD_MANIFEST_GENERATION_FAILED"
    }

    $BinariesDir = Join-Path $RepoRoot "frontend\src-tauri\binaries"
    if (-not (Test-Path -LiteralPath $BinariesDir -PathType Container)) {
        New-Item -ItemType Directory -Path $BinariesDir | Out-Null
    }
    $StagedExe = Join-Path $BinariesDir "sorigul-backend.exe"
    $StagedFfmpeg = Join-Path $BinariesDir "ffmpeg.exe"
    $StagedManifest = Join-Path $BinariesDir "sorigul-build-manifest.json"
    Write-Step "Promoting validated candidate artifacts as one protected set"
    Publish-StagedArtifacts @(
        [pscustomobject]@{ Candidate = $CandidateExe; Target = $StagedExe },
        [pscustomobject]@{ Candidate = $CandidateFfmpeg; Target = $StagedFfmpeg },
        [pscustomobject]@{ Candidate = $CandidateManifest; Target = $StagedManifest }
    )

    Write-FileReport $StagedExe "sorigul-backend.exe"
    Write-FileReport $StagedFfmpeg "ffmpeg.exe"
    Write-Host "Manifest: $StagedManifest"
    Write-Host "Sidecar build + self-test PASSED." -ForegroundColor Green
} finally {
    if (Test-Path -LiteralPath $TempRoot) {
        Remove-Item -LiteralPath $TempRoot -Recurse -Force
    }
}
