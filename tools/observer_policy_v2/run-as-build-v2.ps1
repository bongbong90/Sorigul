#Requires -Version 5.1
<# No account switching, credential loading, product execution or build adapter. #>
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Python,
    [Parameter(Mandatory=$true)][string]$FixtureRoot,
    [Parameter(Mandatory=$true)][string]$RunId,
    [ValidateSet('success','wait','stop-at-exit')][string]$ChildMode = 'success',
    [string]$ToolDirectory = $PSScriptRoot
)
$ErrorActionPreference = 'Stop'
try {
    if ($PSVersionTable.PSEdition -cne 'Desktop' -or $PSVersionTable.PSVersion.Major -ne 5) {
        throw 'Native Windows PowerShell 5.1 required'
    }
    $entry = Join-Path $ToolDirectory 'runner_v2.py'
    & $Python $entry --fixture $FixtureRoot --run-id $RunId --child-mode $ChildMode
    exit $LASTEXITCODE
} catch {
    Write-Error 'Fixture runner could not run' -ErrorAction Continue
    exit 1
}
