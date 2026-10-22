#Requires -Version 5.1
<# STEP 1-A successor entry point. Fixture only; no operating-profile defaults. #>
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Python,
    [Parameter(Mandatory=$true)][string]$FixtureRoot,
    [Parameter(Mandatory=$true)][string]$RunId,
    [string]$ToolDirectory = $PSScriptRoot
)
$ErrorActionPreference = 'Stop'
try {
    if ($PSVersionTable.PSEdition -cne 'Desktop' -or $PSVersionTable.PSVersion.Major -ne 5) {
        throw 'Native Windows PowerShell 5.1 required'
    }
    $entry = Join-Path $ToolDirectory 'observer_v2.py'
    & $Python $entry --fixture $FixtureRoot --run-id $RunId
    exit $LASTEXITCODE
} catch {
    Write-Error 'Fixture observer could not run' -ErrorAction Continue
    exit 6
}
