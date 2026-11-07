# The only ALLOW build is a disposable EXE, never the normal Runtime DLL.
[CmdletBinding()]
param([switch]$Run)
Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot
$work = Join-Path $here ('qa59-build-' + [guid]::NewGuid().ToString('N'))
$csc = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
$common = @('/nologo','/noconfig','/codepage:65001','/warnaserror+','/checked+','/reference:System.dll','/reference:System.Core.dll')
$contracts = @(Get-ChildItem -LiteralPath $here -Filter '*.cs' -File | Where-Object Name -ne 'ContractTests.cs' | ForEach-Object FullName)
$runtime = @(Get-ChildItem -LiteralPath (Join-Path $here 'runtime') -Filter '*.cs' -File | Where-Object Name -ne 'RuntimeTests.cs' | ForEach-Object FullName)
function Compile([object[]]$arguments) {
    $messages = & $csc @arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        # Source names/line numbers + compiler codes only; generated SID policy
        # and raw diagnostics are never logged.
        foreach ($message in $messages) {
            if ([string]$message -match '(CS[0-9]+)') { Write-Output ('COMPILE_ERROR ' + $matches[1]) }
        }
        throw 'NATIVE_COMPILE_FAILED'
    }
}
New-Item -ItemType Directory -Path $work | Out-Null
try {
    $dll = Join-Path $work 'Qa59Contracts.dll'
    Compile ($common + @('/target:library',('/out:' + $dll)) + $contracts)
    Compile ($common + @('/target:library',('/out:' + (Join-Path $work 'Qa59Runtime.dll')),('/reference:' + $dll)) + $runtime)
    Compile ($common + @('/target:exe',('/out:' + (Join-Path $work 'Qa59SyntheticWorker.exe')),(Join-Path $here 'runtime\worker\SyntheticWorker.cs')))
    $policy = Join-Path $work 'LocalNativePolicy.cs'
    # Compile-only local checks use a non-SID placeholder and cannot execute.
    $qaSid = 'COMPILE_ONLY_DENY'
    if ($Run) {
        if ($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted' -or $env:ImageOS -ne 'win22' -or
            $env:GITHUB_REPOSITORY -ne 'bongbong90/Sorigul' -or $env:GITHUB_REF -ne 'refs/heads/qa/59-stage2a-local-runtime' -or
            $env:QA59_PUBLIC_REPOSITORY -ne 'true' -or $env:GITHUB_EVENT_NAME -ne 'push') { throw 'HOSTED_NATIVE_CONTEXT_DENIED' }
        $qaSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
        if ($qaSid -notmatch '^S-1-[0-9-]+$') { throw 'TOKEN_FORMAT_DENIED' }
    }
    $template = @'
using System;
using System.Security.Principal;
namespace Qa59Installed.Runtime {
 internal static class LocalNativePolicy {
  internal static bool Verified() {
   using (var identity = WindowsIdentity.GetCurrent()) {
    return identity.User != null && identity.User.Value == "__LOCAL_SID__"
      && Environment.GetEnvironmentVariable("GITHUB_ACTIONS") == "true"
      && Environment.GetEnvironmentVariable("RUNNER_ENVIRONMENT") == "github-hosted"
      && Environment.GetEnvironmentVariable("ImageOS") == "win22"
      && Environment.GetEnvironmentVariable("QA59_PUBLIC_REPOSITORY") == "true"
      && Environment.GetEnvironmentVariable("GITHUB_REPOSITORY") == "bongbong90/Sorigul"
      && Environment.GetEnvironmentVariable("GITHUB_REF") == "refs/heads/qa/59-stage2a-local-runtime"
      && Environment.GetEnvironmentVariable("GITHUB_EVENT_NAME") == "push";
   }
  }
 }
}
'@
    [IO.File]::WriteAllText($policy, $template.Replace('__LOCAL_SID__',$qaSid), [Text.UTF8Encoding]::new($false))
    $exe = Join-Path $work 'NativeTests.exe'
    Compile ($common + @('/define:QA59_NATIVE_LOCAL_TESTS','/target:exe',('/out:' + $exe),('/reference:' + $dll)) + $runtime + @($policy,(Join-Path $here 'runtime\native\NativeTests.cs')))
    # Load both builds as libraries: the native-test ALLOW must not propagate.
    $probe = @'
using System;
using System.Reflection;
using Qa59Installed;
class Probe {
 static int Main(string[] args) {
  if (ContextGate.Evaluate("{}").ExecutionAllowed) return 1;
  foreach (string path in args) {
   var type = Assembly.LoadFile(path).GetType("Qa59Installed.Runtime.QaAccountBoundary", true);
   if ((bool)type.GetMethod("Verified",BindingFlags.NonPublic|BindingFlags.Static).Invoke(null,null)) return 2;
  }
  Console.WriteLine("PRODUCTION_AND_LIBRARY_GATE_DENY PASS"); return 0;
 }
}
'@
    $probeSource = Join-Path $work 'GateProbe.cs'
    [IO.File]::WriteAllText($probeSource,$probe,[Text.UTF8Encoding]::new($false))
    $probeExe = Join-Path $work 'GateProbe.exe'
    Compile ($common + @('/target:exe',('/out:' + $probeExe),('/reference:' + $dll),$probeSource))
    & $probeExe (Join-Path $work 'Qa59Runtime.dll') $exe
    if ($LASTEXITCODE -ne 0) { throw 'TEST_ALLOW_LEAKED' }
    if ($Run) {
        & $exe
        if ($LASTEXITCODE -ne 0) { throw 'NATIVE_TEST_FAILED' }
    }
    Write-Output $(if ($Run) { 'HOSTED_NATIVE PASS' } else { 'NATIVE_COMPILE_ONLY PASS' })
}
finally {
    $resolved = [IO.Path]::GetFullPath($work)
    if (-not $resolved.StartsWith($here + [IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase) -or
        [IO.Path]::GetFileName($resolved) -notmatch '^qa59-build-[0-9a-f]{32}$') { throw 'NATIVE_BUILD_CLEANUP_DENIED' }
    if (@(Get-ChildItem -LiteralPath $work -Recurse -Force | Where-Object { ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 }).Count -gt 0) { throw 'NATIVE_BUILD_REPARSE_DENIED' }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
