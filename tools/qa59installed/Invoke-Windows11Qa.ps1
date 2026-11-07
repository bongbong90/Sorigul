# User-authorized local Win11 test-only build; never compiles an ALLOW DLL.
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$Session,[switch]$Run)
$ErrorActionPreference='Stop'
Set-StrictMode -Version 2
$Session=[IO.Path]::GetFullPath($Session)
if([IO.Path]::GetFileName($Session) -notmatch '^win11-protected-[0-9a-f]{32}$'){throw 'LOCAL_SESSION_INVALID'}
if(($env:GITHUB_ACTIONS -eq 'true') -or ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){throw 'LOCAL_NONADMIN_REQUIRED'}
$backup=Get-Content -LiteralPath (Join-Path $Session 'backup-result.json') -Raw | ConvertFrom-Json
$verified=Get-Content -LiteralPath (Join-Path $Session 'preservation-latest.json') -Raw | ConvertFrom-Json
if($backup.state -ne 'PASS' -or $verified.state -ne 'PASS'){throw 'BACKUP_NOT_READY'}
$build=Join-Path $Session ('build-'+[guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($build)
$csc=Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
$common=@('/nologo','/noconfig','/codepage:65001','/warnaserror+','/checked+','/reference:System.dll','/reference:System.Core.dll','/reference:System.Management.dll')
$contracts=@(Get-ChildItem -LiteralPath $PSScriptRoot -Filter '*.cs' -File | Where-Object Name -ne 'ContractTests.cs' | ForEach-Object FullName)
$runtime=@(Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'runtime') -Filter '*.cs' -File | Where-Object Name -ne 'RuntimeTests.cs' | ForEach-Object FullName)
function Compile([object[]]$arguments) { $messages=& $csc @arguments 2>&1; if($LASTEXITCODE -ne 0){foreach($message in $messages){if([string]$message -match 'CS[0-9]+'){Write-Output $message}};throw 'LOCAL_COMPILE_FAILED'} }
function Digest([string]$file) { (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant() }
function Literal([string]$value) { '@"'+$value.Replace('"','""')+'"' }
$sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$approval=Join-Path $build 'single-session.approval'
$protected=Get-Content -LiteralPath (Join-Path $Session 'baseline.json') -Raw | ConvertFrom-Json
$rootLiterals=(@($protected|ForEach-Object {Literal $_.root})) -join ','
$policy=@'
using System;
using System.Reflection;
using System.Security.Principal;
using Microsoft.Win32;
internal static class LocalWin11Policy {
 internal const string Session=SESSION_PATH;
 internal const string Approval=APPROVAL_PATH;
 internal const string BaselineHash="BASELINE_HASH";
 internal const string VerificationHash="VERIFY_HASH";
 internal static readonly string[] ProtectedRoots=new[]{PROTECTED_ROOTS};
 internal static bool Verified() {
  if(Assembly.GetEntryAssembly()!=Assembly.GetExecutingAssembly() || !Environment.UserInteractive || Environment.GetEnvironmentVariable("GITHUB_ACTIONS")=="true") return false;
  using(var identity=WindowsIdentity.GetCurrent()) {
   if(identity.User.Value!="ACTUAL_SID" || new WindowsPrincipal(identity).IsInRole(WindowsBuiltInRole.Administrator)) return false;
  }
  using(var os=Registry.LocalMachine.OpenSubKey(@"SOFTWARE\Microsoft\Windows NT\CurrentVersion"))
  using(var kind=Registry.LocalMachine.OpenSubKey(@"SYSTEM\CurrentControlSet\Control\ProductOptions")) {
   int build;return os!=null&&kind!=null&&int.TryParse(os.GetValue("CurrentBuild") as string,out build)&&build>=22000&&"WinNT".Equals(kind.GetValue("ProductType"));
  }
 }
}
'@
$policy=$policy.Replace('SESSION_PATH',(Literal $Session)).Replace('APPROVAL_PATH',(Literal $approval)).Replace('BASELINE_HASH',(Digest (Join-Path $Session 'baseline.json'))).Replace('VERIFY_HASH',(Digest (Join-Path $Session 'preservation-latest.json'))).Replace('PROTECTED_ROOTS',$rootLiterals).Replace('ACTUAL_SID',$sid)
$policyPath=Join-Path $build 'LocalWin11Policy.cs'
[IO.File]::WriteAllText($policyPath,$policy,[Text.UTF8Encoding]::new($false))
$dll=Join-Path $build 'Qa59Contracts.dll'
Compile ($common+@('/target:library',('/out:'+$dll))+$contracts)
$hostExe=Join-Path $build 'InstalledWindows11Harness.exe'
$server=Join-Path $PSScriptRoot 'server'
Compile ($common+@('/define:QA59_WIN11_LOCAL_TESTS','/target:exe',('/out:'+$hostExe),('/reference:'+$dll))+$runtime+@((Join-Path $server 'ProductOwnedJob.cs'),(Join-Path $server 'InstalledServerHarness.cs'),(Join-Path $server 'Windows11Session.cs'),$policyPath))
$wpf=Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\WPF'
$uiRefs=@('UIAutomationClient.dll','UIAutomationTypes.dll','WindowsBase.dll')|ForEach-Object {'/reference:'+(Join-Path $wpf $_)}
$parentPin=Join-Path $build 'LocalUiParentPin.cs'
[IO.File]::WriteAllText($parentPin,('internal static class LocalUiParentPin { internal const string HostHash="'+(Digest $hostExe)+'"; }'),[Text.UTF8Encoding]::new($false))
Compile ($common+$uiRefs+@('/define:QA59_WIN11_LOCAL_TESTS','/target:exe',('/out:'+(Join-Path $build 'InstalledUiWorker.exe')),(Join-Path $server 'InstalledUiWorker.cs'),$policyPath,$parentPin))
# Compile the unchanged hosted branches too, without executing their accepted tests.
Compile ($common+@('/target:exe',('/out:'+(Join-Path $build 'HostedHarnessCompileOnly.exe')),('/reference:'+$dll))+$runtime+@((Join-Path $server 'ProductOwnedJob.cs'),(Join-Path $server 'InstalledServerHarness.cs')))
Compile ($common+$uiRefs+@('/target:exe',('/out:'+(Join-Path $build 'HostedUiCompileOnly.exe')),(Join-Path $server 'InstalledUiWorker.cs')))
# Focused verification of the new gate only; no accepted Native/Server suite rerun.
$probeSource=@'
using System;
using System.Reflection;
using Qa59Installed;
internal static class GateProbe {
 public static int Main(string[] args) {
  int checks=0;
  foreach(string path in new[]{args[0],args[1]}) {
   var gate=Assembly.LoadFrom(path).GetType("LocalWin11Policy").GetMethod("Verified",BindingFlags.Static|BindingFlags.NonPublic);
   if((bool)gate.Invoke(null,null)) return 1;checks++;
  }
  var runtime=Assembly.LoadFrom(args[2]).GetType("Qa59Installed.Runtime.QaAccountBoundary").GetMethod("Verified",BindingFlags.Static|BindingFlags.NonPublic);
  if((bool)runtime.Invoke(null,null)||ContextGate.Evaluate("{}").ExecutionAllowed) return 1;checks+=2;
  var policy=Assembly.LoadFrom(args[0]).GetType("LocalWin11Policy");
  var roots=(string[])policy.GetField("ProtectedRoots",BindingFlags.Static|BindingFlags.NonPublic).GetValue(null);
  string sample=@"C:\Users\Public\qa59-scratch-"+new string('0',32)+@"\qa59-fixture-"+new string('1',32);
  if(!SyntheticFixtures.ValidateRoot(sample,roots).Ok)return 1;checks++;
  Console.WriteLine("WINDOWS11_LIBRARY_DENY_AND_FIXTURE_GATE checks="+checks);return 0;
 }
}
'@
$probePath=Join-Path $build 'GateProbe.cs'; [IO.File]::WriteAllText($probePath,$probeSource,[Text.UTF8Encoding]::new($false))
$runtimeDll=Join-Path $build 'Qa59Runtime.dll'
Compile ($common+@('/target:library',('/out:'+$runtimeDll),('/reference:'+$dll))+$runtime)
$probeExe=Join-Path $build 'GateProbe.exe'
Compile ($common+@('/target:exe',('/out:'+$probeExe),('/reference:'+$dll),$probePath))
& $probeExe $hostExe (Join-Path $build 'InstalledUiWorker.exe') $runtimeDll
if($LASTEXITCODE -ne 0){throw 'LOCAL_GATE_LEAK'}
$identitySource='using System; internal static class IdentityProbe { public static int Main(){return LocalWin11Policy.Verified()?0:1;} }'
$identityPath=Join-Path $build 'IdentityProbe.cs'; [IO.File]::WriteAllText($identityPath,$identitySource,[Text.UTF8Encoding]::new($false))
$identityExe=Join-Path $build 'IdentityProbe.exe'
Compile ($common+@('/target:exe',('/out:'+$identityExe),$identityPath,$policyPath))
& $identityExe
if($LASTEXITCODE -ne 0){throw 'CURRENT_LOCAL_IDENTITY_UNPROVEN'}
$mutantPath=Join-Path $build 'WrongIdentityPolicy.cs'; [IO.File]::WriteAllText($mutantPath,$policy.Replace($sid,'S-1-0-0'),[Text.UTF8Encoding]::new($false))
$mutantExe=Join-Path $build 'WrongIdentityProbe.exe'
Compile ($common+@('/target:exe',('/out:'+$mutantExe),$identityPath,$mutantPath))
& $mutantExe
if($LASTEXITCODE -ne 1){throw 'IDENTITY_MISMATCH_NOT_BLOCKED'}
Write-Output 'WINDOWS11_ACTUAL_IDENTITY_AND_MISMATCH PASS'
$consumeSource=@'
using System;
using System.IO;
internal static class ConsumeProbe {
 public static int Main() {
  bool concurrent=false,reused=false;
  using(var first=Windows11Session.Enter()) {
   try { using(var second=Windows11Session.Enter()){} } catch(Qa59Installed.Runtime.BoundaryException) { concurrent=true; }
  }
  try { using(var third=Windows11Session.Enter()){} } catch(Qa59Installed.Runtime.BoundaryException) { reused=true; }
  if(!concurrent||!reused)return 1;
  Console.WriteLine("WINDOWS11_ATOMIC_SINGLE_CONSUMPTION PASS");return 0;
 }
}
'@
$consumePath=Join-Path $build 'ConsumeProbe.cs'; [IO.File]::WriteAllText($consumePath,$consumeSource,[Text.UTF8Encoding]::new($false))
$probeApproval=Join-Path $build 'probe.approval'
$consumePolicy=Join-Path $build 'ConsumePolicy.cs'; [IO.File]::WriteAllText($consumePolicy,$policy.Replace((Literal $approval),(Literal $probeApproval)),[Text.UTF8Encoding]::new($false))
$consumeExe=Join-Path $build 'ConsumeProbe.exe'
Compile ($common+@('/define:QA59_WIN11_LOCAL_TESTS','/target:exe','/main:ConsumeProbe',('/out:'+$consumeExe),('/reference:'+$dll))+$runtime+@((Join-Path $server 'ProductOwnedJob.cs'),(Join-Path $server 'InstalledServerHarness.cs'),(Join-Path $server 'Windows11Session.cs'),$consumePolicy,$consumePath))
[IO.File]::WriteAllText($probeApproval,'QA59_WIN11_APPROVED_SINGLE_SESSION',[Text.Encoding]::ASCII)
& $consumeExe
if($LASTEXITCODE -ne 0){throw 'SINGLE_CONSUMPTION_FAILED'}
$probeStart=[Diagnostics.ProcessStartInfo]::new($hostExe,'--probe-ui-owner');$probeStart.UseShellExecute=$false;$probeStart.CreateNoWindow=$true
$parentProbe=[Diagnostics.Process]::Start($probeStart)
if(-not $parentProbe.WaitForExit(10000)){ $parentProbe.Kill();throw 'UI_PARENT_PROBE_DEADLINE' }
if($parentProbe.ExitCode -ne 37){throw 'UI_PARENT_PROBE_FAILED'}
$parentProbe.Dispose();$wait=[Diagnostics.Stopwatch]::StartNew()
do {
    $remaining=@(Get-CimInstance Win32_Process -Filter "Name='InstalledUiWorker.exe'" | Where-Object {$_.ExecutablePath -eq (Join-Path $build 'InstalledUiWorker.exe')})
    if($remaining.Count -eq 0){break};Start-Sleep -Milliseconds 100
} while($wait.Elapsed.TotalSeconds -lt 5)
if($remaining.Count -ne 0){throw 'UI_PARENT_PROBE_RESIDUAL'}
Write-Output 'WINDOWS11_UI_PARENT_DEATH_RESIDUAL_ZERO PASS'
# The policy/actual SID stays solely in the protected local build directory.
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'candidate-manifest.json') -Destination (Join-Path $Session 'candidate-manifest.json') -Force
[IO.File]::WriteAllText((Join-Path $Session 'latest-build.txt'),$build,[Text.UTF8Encoding]::new($false))
Write-Output 'WINDOWS11_HARNESS_COMPILE PASS'
if($Run) {
    [IO.File]::WriteAllText($approval,'QA59_WIN11_APPROVED_SINGLE_SESSION',[Text.Encoding]::ASCII)
    $start=[Diagnostics.ProcessStartInfo]::new($hostExe)
    $start.UseShellExecute=$false; $start.CreateNoWindow=$true; $start.RedirectStandardOutput=$true; $start.RedirectStandardError=$true
    $process=[Diagnostics.Process]::Start($start)
    $parentBorn=$process.StartTime.ToUniversalTime(); $parentId=$process.Id
    $uiImage=Join-Path $build 'InstalledUiWorker.exe'; $uiHash=Digest $uiImage
    $stdout=$process.StandardOutput.ReadToEndAsync(); $stderr=$process.StandardError.ReadToEndAsync()
    $clock=[Diagnostics.Stopwatch]::StartNew()
    try {
        while(-not $process.WaitForExit(1000)) {
            if($clock.Elapsed.TotalSeconds -gt 420){$process.Kill();[void]$process.WaitForExit(5000);throw 'WINDOWS11_HARNESS_DEADLINE'}
        }
        if(-not $stdout.Wait(2000) -or -not $stderr.Wait(2000)){throw 'WINDOWS11_OUTPUT_DEADLINE'}
        [IO.File]::WriteAllText((Join-Path $Session 'scenario.out'),$stdout.Result,[Text.UTF8Encoding]::new($false))
        [IO.File]::WriteAllText((Join-Path $Session 'scenario.err'),$stderr.Result,[Text.UTF8Encoding]::new($false))
        foreach($line in ($stdout.Result -split "`n")){if($line -match '^(SERVER_CHECK|SERVER_.*_DIAG|SERVER_INSTALLED_QA|WINDOWS11_INSTALLED_SCENARIOS) '){Write-Output $line.Trim()}}
        $code=$process.ExitCode
    } finally {
        if(-not $process.HasExited){$process.Kill();if(-not $process.WaitForExit(5000)){throw 'OWNED_HOST_RESIDUAL'}}
        # Parent-death watcher is primary. Exact identity cleanup is the fallback.
        $workers=@(Get-CimInstance Win32_Process -Filter "Name='InstalledUiWorker.exe'" | Where-Object ParentProcessId -EQ $parentId)
        foreach($row in $workers) {
            if($row.ExecutablePath -ne $uiImage){throw 'UI_OWNERSHIP_UNVERIFIED'}
            try { $worker=[Diagnostics.Process]::GetProcessById($row.ProcessId) } catch [ArgumentException] { continue }
            try {
                if($worker.StartTime.ToUniversalTime() -lt $parentBorn -or $worker.MainModule.FileName -ne $uiImage -or (Digest $uiImage) -ne $uiHash){throw 'UI_IDENTITY_MISMATCH'}
                if(-not $worker.WaitForExit(500)){$worker.Kill();if(-not $worker.WaitForExit(5000)){throw 'OWNED_UI_RESIDUAL'}}
            } finally { $worker.Dispose() }
        }
        if(@(Get-CimInstance Win32_Process -Filter "Name='InstalledUiWorker.exe'" | Where-Object ParentProcessId -EQ $parentId).Count){throw 'OWNED_UI_RESIDUAL'}
        Write-Output 'WINDOWS11_OWNED_UI_RESIDUAL_ZERO PASS'
        $process.Dispose()
    }
    if($code -ne 0){throw 'WINDOWS11_SCENARIOS_FAILED'}
}
$global:LASTEXITCODE=0
