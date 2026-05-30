# Houdini unlink script for Windows
# Removes junctions from Houdini's site-packages

[CmdletBinding()]
param(
    [Parameter(Mandatory=$false)]
    [string]$HoudiniVersion = "20.5"
)

$ErrorActionPreference = "Stop"

# ── Find Houdini Python ──────────────────────────────────────────────────
$HoudiniBase = "C:\Program Files\Side Effects Software\Houdini $HoudiniVersion"
if (-not (Test-Path $HoudiniBase)) {
    Write-Error "Houdini $HoudiniVersion not found at: $HoudiniBase"
    exit 1
}

$Hython = "$HoudiniBase\bin\hython.exe"
if (-not (Test-Path $Hython)) {
    $Hython = Get-ChildItem "$HoudiniBase\python*\python.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $Hython) {
        Write-Error "Cannot find hython in: $HoudiniBase"
        exit 1
    }
    $Hython = $Hython.FullName
}

$PythonVersion = & $Hython -c "import sys; print(f'{sys.version_info.major}{sys.version_info.minor}')"
$SitePackages = "$HoudiniBase\python$PythonVersion\lib\site-packages"

# ── Remove junctions ─────────────────────────────────────────────────────
$TargetLink = "$SitePackages\dcc_mcp_houdini"
if (Test-Path $TargetLink) {
    Write-Host "Removing: $TargetLink" -ForegroundColor Yellow
    Remove-Item $TargetLink -Recurse -Force
    Write-Host "Removed dcc_mcp_houdini" -ForegroundColor Green
}

$CoreTarget = "$SitePackages\dcc_mcp_core"
if (Test-Path $CoreTarget) {
    Write-Host "Removing: $CoreTarget" -ForegroundColor Yellow
    Remove-Item $CoreTarget -Recurse -Force
    Write-Host "Removed dcc_mcp_core" -ForegroundColor Green
}

Write-Host "Done!" -ForegroundColor Green
