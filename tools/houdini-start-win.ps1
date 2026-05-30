# Start Houdini (Windows) — optional debugpy hook
#
# Usage:
#   powershell -File tools/houdini-start-win.ps1 -HoudiniVersion 20.5
#   just houdini-version=20.5 houdini-start-win

[CmdletBinding()]
param(
    [Parameter(Mandatory=$false)]
    [string]$HoudiniVersion = "20.5",

    [Parameter(Mandatory=$false)]
    [switch]$EnableDebugpy
)

$ErrorActionPreference = "Stop"

$HoudiniBase = "C:\Program Files\Side Effects Software\Houdini $HoudiniVersion"
$HoudiniExe = "$HoudiniBase\bin\houdini.exe"

if (-not (Test-Path $HoudiniExe)) {
    Write-Error "Houdini not found: $HoudiniExe"
    exit 1
}

if ($EnableDebugpy) {
    $env:DCC_MCP_HOUDINI_DEBUGPY = "1"
}

Write-Host "Starting Houdini $HoudiniVersion..." -ForegroundColor Green
Start-Process $HoudiniExe

if ($EnableDebugpy) {
    Write-Host ""
    Write-Host "After Houdini opens, run in Python Source Editor:" -ForegroundColor Yellow
    Write-Host "  import debugpy; debugpy.listen(('127.0.0.1', 5678))" -ForegroundColor Cyan
}
