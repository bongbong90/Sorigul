# Static checks and pure unit tests for tools/qa59installed. No GUI, network,
# MSI, product launch or user data: compiles the contract sources with the
# .NET Framework csc into a fresh temp folder, runs the tests, deletes it.
[CmdletBinding()]
param()
Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$here = $PSScriptRoot
$failures = 0

# 1. PowerShell AST parse of every script in this folder.
foreach ($script in Get-ChildItem -LiteralPath $here -Filter '*.ps1' -File) {
    $tokens = $null
    $errors = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile($script.FullName, [ref]$tokens, [ref]$errors)
    Write-Output ('AST {0} errors={1}' -f $script.Name, @($errors).Count)
    if (@($errors).Count -ne 0) { $failures++ }
}

# 2. Purity lint (an accident guard, not a sandbox): contract sources may not
#    name I/O, process, network, native, reflection or environment APIs.
#    Matched as whole identifiers after removing comments and whitespace
#    around '.' and '(' (so 'System . IO' still matches). The contracts compile
#    into their own library, so they cannot call into ContractTests.cs, the
#    only file that reads its two inputs.
$forbidden = @('System.IO', 'System.Net', 'System.Diagnostics', 'System.Runtime.InteropServices', 'System.Reflection',
    'Microsoft.Win32', 'DllImport', 'extern', 'Process', 'Environment', 'Registry', 'Socket', 'File.', 'Directory.',
    'Thread', 'Task', 'unsafe', 'Console', 'AppDomain', 'Activator', 'Assembly.', 'GetType(', 'GetMethod', 'Invoke', 'Marshal')
function Get-PurityHits([string]$text) {
    # One left-to-right pass, so '//' inside "http://x" is a string, not a
    # comment: verbatim strings, regular strings, char literals, comments.
    $lexer = '@"(?:[^"]|"")*"|"(?:\\.|[^"\\\n])*"|''(?:\\.|[^''\\\n])*''|/\*.*?\*/|//[^\n]*'
    $text = [regex]::Replace($text, $lexer, { param($m) if ($m.Value.StartsWith('/')) { ' ' } else { '""' } }, 'Singleline')
    $text = [regex]::Replace($text, '\s*([.(])\s*', '$1')
    return @($forbidden | Where-Object {
            $suffix = if ($_ -match '\w$') { '(?![A-Za-z0-9_])' } else { '' }
            $text -cmatch ('(?<![A-Za-z0-9_])' + [regex]::Escape($_) + $suffix)
        })
}

# Lint self-test: known bypasses must hit, known identifiers/strings must not.
$lintCases = @(
    @{ text = 'var u = "http://x"; System.Console.WriteLine(u);'; hit = $true },
    @{ text = 'var u = @"C:\a\"" //"; Console.Beep();'; hit = $true },
    @{ text = 'char c = ''"''; Console.Beep();'; hit = $true },
    @{ text = 'using System /* x */ . IO;'; hit = $true },
    @{ text = '// Console.WriteLine();'; hit = $false },
    @{ text = 'string s = "Process File. Console";'; hit = $false },
    @{ text = 'bool MayInvokeMsiexec; int external_drive_calls;'; hit = $false }
)
foreach ($case in $lintCases) {
    $actual = @(Get-PurityHits $case.text).Count -gt 0
    if ($actual -ne $case.hit) { Write-Output ('LINT SELFTEST FAIL: ' + $case.text); $failures++ }
}
Write-Output ('LINT SELFTEST cases={0}' -f $lintCases.Count)

$contracts = @(Get-ChildItem -LiteralPath $here -Filter '*.cs' -File | Where-Object { $_.Name -ne 'ContractTests.cs' })
foreach ($source in $contracts) {
    $hits = @(Get-PurityHits ([System.IO.File]::ReadAllText($source.FullName)))
    Write-Output ('PURITY {0} forbidden={1}' -f $source.Name, $hits.Count)
    if ($hits.Count -ne 0) { $failures++ }
}

# 3. No executable workflow in this stage.
# (PS 5.1 ignores -Include together with -LiteralPath, so filter explicitly.)
$workflows = @(Get-ChildItem -LiteralPath $here -Recurse -File | Where-Object { @('.yml', '.yaml') -contains $_.Extension.ToLowerInvariant() })
Write-Output ('WORKFLOW files={0}' -f $workflows.Count)
if ($workflows.Count -ne 0) { $failures++ }

# 4. Compile (C# 5, warnings as errors, checked arithmetic, UTF-8 sources) and run.
$csc = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
$work = Join-Path ([System.IO.Path]::GetTempPath()) ('qa59installed-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $work | Out-Null
try {
    $dll = Join-Path $work 'Qa59Contracts.dll'
    $exe = Join-Path $work 'ContractTests.exe'
    $common = @('/nologo', '/noconfig', '/codepage:65001', '/warnaserror+', '/checked+', '/reference:System.dll', '/reference:System.Core.dll')
    $compilerLog = & $csc $common /target:library ('/out:' + $dll) @($contracts | ForEach-Object { $_.FullName }) 2>&1
    if ($LASTEXITCODE -eq 0) {
        $compilerLog = & $csc $common /target:exe ('/reference:' + $dll) ('/out:' + $exe) (Join-Path $here 'ContractTests.cs') 2>&1
    }
    Write-Output ('COMPILE exit={0}' -f $LASTEXITCODE)
    if ($LASTEXITCODE -ne 0) {
        $compilerLog | ForEach-Object { Write-Output ('  ' + $_) }
        $failures++
    }
    else {
        & $exe $here | ForEach-Object { Write-Output $_ }
        Write-Output ('TESTS exit={0}' -f $LASTEXITCODE)
        if ($LASTEXITCODE -ne 0) { $failures++ }
    }
}
finally {
    Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Output ('RESULT {0}' -f $(if ($failures -eq 0) { 'PASS' } else { 'FAIL' }))
exit $(if ($failures -eq 0) { 0 } else { 1 })
