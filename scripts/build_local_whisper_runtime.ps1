#Requires -Version 5.1
<#
.SYNOPSIS
    Builds, validates, manifests, and installs Local Whisper Runtime v1.

.DESCRIPTION
    This is an explicit prepare/install step. It never downloads a runtime at
    app startup. The Whisper model itself is not bundled or downloaded here.
#>

$ErrorActionPreference = "Stop"
$SelfTestTimeoutSeconds = 300
$SelfTestStdoutLimitBytes = 16KB
$SelfTestStderrTailLimitBytes = 16KB
$SelfTestFieldLimitChars = 2048
$RuntimeVersion = 1
$ProtocolVersion = 1
$ExpectedTorch = "torch==2.13.0+cu130"
$ExpectedCuda = "13.0"

function Resolve-TrustedTaskkill {
    # Resolve from the OS-backed system directory only; never PATH or env vars.
    $SystemDirectory = [System.Environment]::SystemDirectory
    if ([string]::IsNullOrWhiteSpace($SystemDirectory) -or
        -not [System.IO.Path]::IsPathRooted($SystemDirectory) -or
        -not (Test-Path -LiteralPath $SystemDirectory -PathType Container)) {
        throw "TRUSTED_SYSTEM_DIRECTORY_UNAVAILABLE"
    }
    $TaskkillPath = Join-Path $SystemDirectory "taskkill.exe"
    if (-not [System.IO.Path]::IsPathRooted($TaskkillPath) -or
        -not (Test-Path -LiteralPath $TaskkillPath -PathType Leaf)) {
        throw "TRUSTED_TASKKILL_UNAVAILABLE"
    }
    return $TaskkillPath
}

function Write-Step($Message) {
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Read-BoundedUtf8Text($Path, [int]$MaxBytes, [bool]$Tail) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return ""
    }
    $Stream = [System.IO.File]::Open(
        $Path,
        [System.IO.FileMode]::Open,
        [System.IO.FileAccess]::Read,
        [System.IO.FileShare]::ReadWrite
    )
    try {
        $WasTruncated = $Stream.Length -gt $MaxBytes
        if ($Tail -and $WasTruncated) {
            [void]$Stream.Seek(-$MaxBytes, [System.IO.SeekOrigin]::End)
        }
        $BytesToRead = [int][Math]::Min($MaxBytes, $Stream.Length - $Stream.Position)
        $Buffer = New-Object byte[] $BytesToRead
        $BytesRead = $Stream.Read($Buffer, 0, $BytesToRead)
        $Text = [System.Text.Encoding]::UTF8.GetString($Buffer, 0, $BytesRead)
        if ($WasTruncated) {
            if ($Tail) { return "...[tail]$Text" }
            return "$Text...[truncated]"
        }
        return $Text
    } finally {
        $Stream.Dispose()
    }
}

function Format-SelfTestDiagnosticValue($Value, [int]$MaxChars = $SelfTestFieldLimitChars) {
    if ($null -eq $Value) { return "<null>" }
    $Text = [string]$Value
    $Text = $Text.Replace("`r", "\r").Replace("`n", "\n")
    if ($Text.Length -gt $MaxChars) {
        return $Text.Substring(0, $MaxChars) + "...[truncated]"
    }
    return $Text
}

function Publish-RuntimeArtifacts($Artifacts) {
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
                try { Remove-Item -LiteralPath $Item.Target -Force } catch { $RollbackErrors += $_.Exception.Message }
            }
        }
        foreach ($Item in $Prepared) {
            if ($Item.BackupCreated -and (Test-Path -LiteralPath $Item.Backup)) {
                try { Move-Item -LiteralPath $Item.Backup -Destination $Item.Target } catch { $RollbackErrors += $_.Exception.Message }
            }
        }
        if ($RollbackErrors.Count -ne 0) {
            throw "LOCAL_RUNTIME_PROMOTION_ROLLBACK_FAILED: $PromotionError; rollback: $($RollbackErrors -join '; ')"
        }
        throw "LOCAL_RUNTIME_PROMOTION_FAILED: $PromotionError"
    } finally {
        foreach ($Item in $Prepared) {
            if (Test-Path -LiteralPath $Item.Temp) { Remove-Item -LiteralPath $Item.Temp -Force }
            if ($Succeeded -and (Test-Path -LiteralPath $Item.Backup)) {
                Remove-Item -LiteralPath $Item.Backup -Force
            }
        }
    }
}

$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path -LiteralPath (Join-Path $RepoRoot "backend\src\local_runtime_main.py"))) {
    Write-Error "Could not confirm repository root."
    exit 1
}
Set-Location $RepoRoot

$VenvPython = Join-Path $RepoRoot "venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
    Write-Error "Python venv not found at '$VenvPython'."
    exit 1
}
$PythonVersion = (& $VenvPython -c "import sys; print('.'.join(map(str, sys.version_info[:3])))").Trim()
if ($LASTEXITCODE -ne 0 -or -not $PythonVersion.StartsWith("3.13.")) {
    Write-Error "PYTHON_RELEASE_VERSION_MISMATCH: expected Python 3.13.x, found '$PythonVersion'"
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

Write-Step "Installing pinned Local Runtime requirements"
& $VenvPython -m pip install --no-cache-dir -r "tools\requirements-torch-cuda.txt"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $VenvPython -m pip install --no-cache-dir -r "backend\requirements.txt"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $VenvPython -m pip install --no-cache-dir -r "backend\requirements-whisper.txt"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $VenvPython -m pip install --no-cache-dir -r "tools\requirements-packaging.txt"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$InvocationId = [guid]::NewGuid().ToString("N")
$TempRoot = Join-Path $env:TEMP "Sorigul_LocalRuntime_$InvocationId"
$BuildDir = Join-Path $TempRoot "build"
$DistDir = Join-Path $TempRoot "dist"
$CandidateDir = Join-Path $TempRoot "candidate"
New-Item -ItemType Directory -Path $BuildDir, $DistDir, $CandidateDir | Out-Null

try {
    Write-Step "Validating pinned CUDA runtime"
    $CudaPreflight = @'
import torch
if torch.__version__ != "2.13.0+cu130" or torch.version.cuda != "13.0":
    raise SystemExit(41)
if not torch.cuda.is_available() or torch.cuda.device_count() < 1:
    raise SystemExit(42)
'@
    $CudaPreflightPath = Join-Path $TempRoot "cuda-preflight.py"
    [System.IO.File]::WriteAllText(
        $CudaPreflightPath,
        $CudaPreflight,
        (New-Object System.Text.UTF8Encoding($false))
    )
    & $VenvPython $CudaPreflightPath
    if ($LASTEXITCODE -eq 41) { throw "CUDA_RELEASE_VARIANT_MISMATCH" }
    if ($LASTEXITCODE -eq 42) { throw "CUDA_RELEASE_RUNTIME_UNAVAILABLE" }
    if ($LASTEXITCODE -ne 0) { throw "CUDA_RELEASE_PREFLIGHT_FAILED" }

    Write-Step "Building Local Whisper Runtime"
    & $VenvPython -m PyInstaller --clean --noconfirm `
        --distpath $DistDir `
        --workpath $BuildDir `
        "backend\packaging\sorigul_local_runtime.spec"
    if ($LASTEXITCODE -ne 0) { throw "LOCAL_RUNTIME_BUILD_FAILED" }

    $BuiltExe = Join-Path $DistDir "sorigul-local-whisper.exe"
    if (-not (Test-Path -LiteralPath $BuiltExe -PathType Leaf)) {
        throw "LOCAL_RUNTIME_ARTIFACT_MISSING"
    }
    $CandidateExe = Join-Path $CandidateDir "sorigul-local-whisper.exe"
    Copy-Item -LiteralPath $BuiltExe -Destination $CandidateExe

    $SelfTestStdout = Join-Path $CandidateDir "selftest.stdout"
    $SelfTestStderr = Join-Path $CandidateDir "selftest.stderr"
    $TaskkillPath = Resolve-TrustedTaskkill
    Write-Step "Running bounded Local Runtime CUDA self-test"
    $SelfTestProcess = Start-Process `
        -FilePath $CandidateExe `
        -ArgumentList "--self-test" `
        -WorkingDirectory $CandidateDir `
        -RedirectStandardOutput $SelfTestStdout `
        -RedirectStandardError $SelfTestStderr `
        -WindowStyle Hidden `
        -PassThru
    $Deadline = [DateTime]::UtcNow.AddSeconds($SelfTestTimeoutSeconds)
    while (-not $SelfTestProcess.HasExited -and [DateTime]::UtcNow -lt $Deadline) {
        Start-Sleep -Milliseconds 250
        $SelfTestProcess.Refresh()
    }
    if (-not $SelfTestProcess.HasExited) {
        & $TaskkillPath /PID $SelfTestProcess.Id /T /F | Out-Host
        if ($LASTEXITCODE -ne 0 -or -not $SelfTestProcess.WaitForExit(10000)) {
            throw "LOCAL_RUNTIME_SELFTEST_TIMEOUT_CLEANUP_FAILED"
        }
        throw "LOCAL_RUNTIME_SELFTEST_TIMEOUT"
    }
    $SelfTestExit = $SelfTestProcess.ExitCode
    $SelfTestJson = Read-BoundedUtf8Text $SelfTestStdout $SelfTestStdoutLimitBytes $false
    $SelfTestStderrTail = Read-BoundedUtf8Text $SelfTestStderr $SelfTestStderrTailLimitBytes $true
    $SelfTest = $null
    $SelfTestJsonParsed = $false
    $SelfTestParseError = $null
    try {
        $SelfTest = $SelfTestJson | ConvertFrom-Json
        $SelfTestJsonParsed = $true
    } catch {
        $SelfTestParseError = $_.Exception.Message
    }
    $SelfTestDiagnostic = @(
        "exit=$(Format-SelfTestDiagnosticValue $SelfTestExit)"
        "stdout=$(Format-SelfTestDiagnosticValue $SelfTestJson $SelfTestStdoutLimitBytes)"
        "stderr_tail=$(Format-SelfTestDiagnosticValue $SelfTestStderrTail $SelfTestStderrTailLimitBytes)"
        "json_parsed=$(Format-SelfTestDiagnosticValue $SelfTestJsonParsed)"
        "parse_error=$(Format-SelfTestDiagnosticValue $SelfTestParseError)"
        "protocol=$(Format-SelfTestDiagnosticValue $SelfTest.protocol_version)"
        "ok=$(Format-SelfTestDiagnosticValue $SelfTest.ok)"
        "status=$(Format-SelfTestDiagnosticValue $SelfTest.status)"
        "device=$(Format-SelfTestDiagnosticValue $SelfTest.device)"
        "error_code=$(Format-SelfTestDiagnosticValue $SelfTest.error.code)"
        "error_message=$(Format-SelfTestDiagnosticValue $SelfTest.error.message)"
    ) -join "; "
    if (-not $SelfTestJsonParsed) {
        throw "LOCAL_RUNTIME_SELFTEST_RESPONSE_INVALID: $SelfTestDiagnostic"
    }
    if (
        $SelfTestExit -ne 0 -or
        $SelfTest.protocol_version -ne $ProtocolVersion -or
        $SelfTest.ok -ne $true -or
        $SelfTest.status -cne "DONE" -or
        $SelfTest.device -cne "cuda"
    ) {
        throw "LOCAL_RUNTIME_SELFTEST_FAILED: $SelfTestDiagnostic"
    }

    $RuntimeHash = (Get-FileHash -LiteralPath $CandidateExe -Algorithm SHA256).Hash.ToLowerInvariant()
    $RuntimeSize = [long](Get-Item -LiteralPath $CandidateExe).Length
    $CriticalInputs = [ordered]@{}
    foreach ($RelativePath in @(
        "tools\requirements-torch-cuda.txt",
        "backend\requirements-whisper.txt",
        "tools\requirements-packaging.txt",
        "backend\packaging\sorigul_local_runtime.spec",
        "backend\src\local_runtime_main.py"
    )) {
        $CriticalInputs[$RelativePath] = (Get-FileHash -LiteralPath (Join-Path $RepoRoot $RelativePath) -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    $Manifest = [ordered]@{
        runtime_type = "sorigul-local-whisper"
        runtime_version = $RuntimeVersion
        protocol_version = $ProtocolVersion
        torch_requirement = $ExpectedTorch
        expected_cuda = $ExpectedCuda
        worker_sha256 = $RuntimeHash
        artifact_sha256 = $RuntimeHash
        artifact_size = $RuntimeSize
        source_head = $SourceHead
        generated_at_utc = [DateTime]::UtcNow.ToString("o")
        tracked_tree_clean = $true
        release_input_sha256 = $CriticalInputs
    }
    $ManifestJson = ($Manifest | ConvertTo-Json -Depth 4) + "`n"
    try { $RoundTrippedManifest = $ManifestJson | ConvertFrom-Json } catch { throw "LOCAL_RUNTIME_MANIFEST_INVALID" }
    if (
        -not ($RoundTrippedManifest.torch_requirement -is [string]) -or
        $RoundTrippedManifest.torch_requirement -cne $ExpectedTorch -or
        -not ($RoundTrippedManifest.expected_cuda -is [string]) -or
        $RoundTrippedManifest.expected_cuda -cne $ExpectedCuda
    ) {
        throw "LOCAL_RUNTIME_MANIFEST_INVALID"
    }
    $CandidateManifest = Join-Path $CandidateDir "runtime-manifest.json"
    [System.IO.File]::WriteAllText(
        $CandidateManifest,
        $ManifestJson,
        (New-Object System.Text.UTF8Encoding($false))
    )

    $InstallDir = Join-Path $env:LOCALAPPDATA "Sorigul\runtime\local-whisper\v1"
    if (-not (Test-Path -LiteralPath $InstallDir -PathType Container)) {
        New-Item -ItemType Directory -Path $InstallDir | Out-Null
    }
    Write-Step "Installing validated Local Runtime v1"
    Publish-RuntimeArtifacts @(
        [pscustomobject]@{ Candidate = $CandidateExe; Target = (Join-Path $InstallDir "sorigul-local-whisper.exe") },
        [pscustomobject]@{ Candidate = $CandidateManifest; Target = (Join-Path $InstallDir "runtime-manifest.json") }
    )
    Write-Host "Runtime: $InstallDir"
    Write-Host "SHA-256: $RuntimeHash"
    Write-Host "Local Whisper Runtime build + install PASSED." -ForegroundColor Green
} finally {
    if (Test-Path -LiteralPath $TempRoot) {
        Remove-Item -LiteralPath $TempRoot -Recurse -Force
    }
}
