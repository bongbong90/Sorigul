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

# 2. Purity: contract sources may not reach I/O, processes, network, native
#    code or the environment. Only ContractTests.cs reads its two inputs.
$forbidden = @('System.IO', 'System.Net', 'System.Diagnostics', 'System.Runtime.InteropServices', 'System.Reflection',
    'Microsoft.Win32', 'DllImport', 'Process', 'Environment', 'Registry', 'Socket', 'File.', 'Thread', 'unsafe')
$contracts = Get-ChildItem -LiteralPath $here -Filter '*.cs' -File | Where-Object { $_.Name -ne 'ContractTests.cs' }
foreach ($source in $contracts) {
    $text = [System.IO.File]::ReadAllText($source.FullName)
    $hits = @($forbidden | Where-Object { $text.Contains($_) })
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
    $exe = Join-Path $work 'ContractTests.exe'
    $sources = @(Get-ChildItem -LiteralPath $here -Filter '*.cs' -File | ForEach-Object { $_.FullName })
    $compilerLog = & $csc /nologo /noconfig /codepage:65001 /target:exe /warnaserror+ /checked+ `
        /reference:System.dll /reference:System.Core.dll ('/out:' + $exe) $sources 2>&1
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
