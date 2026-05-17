# Houdini status script for Windows
# Shows link status of dcc_mcp_houdini and dcc_mcp_core

[CmdletBinding()]
param(
    [Parameter(Mandatory=$false)]
    [string]$HoudiniVersion = "20.5"
)

$ErrorActionPreference = "Continue"

# ── Find Houdini Python ──────────────────────────────────────────────────
$HoudiniBase = "C:\Program Files\Side Effects Software\Houdini $HoudiniVersion"
if (-not (Test-Path $HoudiniBase)) {
    Write-Host "Houdini $HoudiniVersion not found at: $HoudiniBase" -ForegroundColor Red
    exit 1
}

$Hython = "$HoudiniBase\bin\hython.exe"
if (-not (Test-Path $Hython)) {
    $Hython = Get-ChildItem "$HoudiniBase\python*\python.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $Hython) {
        Write-Host "Cannot find hython in: $HoudiniBase" -ForegroundColor Red
        exit 1
    }
    $Hython = $Hython.FullName
}

$PythonVersion = & $Hython -c "import sys; print(f'{sys.version_info.major}{sys.version_info.minor}')"
$SitePackages = "$HoudiniBase\python$PythonVersion\lib\site-packages"

Write-Host "Houdini $HoudiniVersion" -ForegroundColor Cyan
Write-Host "Site-packages: $SitePackages" -ForegroundColor Cyan
Write-Host ""

# ── Check dcc_mcp_houdini ───────────────────────────────────────────────
$TargetLink = "$SitePackages\dcc_mcp_houdini"
if (Test-Path $TargetLink) {
    $link = Get-Item $TargetLink
    if ($link.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
        $target = (Get-Item $TargetLink).Target.FullName
        Write-Host "dcc_mcp_houdini: " -NoNewline
        Write-Host "LINKED" -ForegroundColor Green -NoNewline
        Write-Host " -> $target"
    }
    else {
        Write-Host "dcc_mcp_houdini: " -NoNewline
        Write-Host "INSTALLED (not linked)" -ForegroundColor Yellow
    }
}
else {
    Write-Host "dcc_mcp_houdini: " -NoNewline
    Write-Host "NOT INSTALLED" -ForegroundColor Red
}

# ── Check dcc_mcp_core ───────────────────────────────────────────────────
$CoreTarget = "$SitePackages\dcc_mcp_core"
if (Test-Path $CoreTarget) {
    $link = Get-Item $CoreTarget
    if ($link.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
        $target = (Get-Item $CoreTarget).Target.FullName
        Write-Host "dcc_mcp_core:     " -NoNewline
        Write-Host "LINKED" -ForegroundColor Green -NoNewline
        Write-Host " -> $target"
    }
    else {
        Write-Host "dcc_mcp_core:     " -NoNewline
        Write-Host "INSTALLED (not linked)" -ForegroundColor Yellow
    }
}
else {
    Write-Host "dcc_mcp_core:     " -NoNewline
    Write-Host "NOT INSTALLED" -ForegroundColor Red
}

# ── Verify imports ───────────────────────────────────────────────────────
Write-Host ""
Write-Host "Import test:" -ForegroundColor Cyan
& $Hython -c "import dcc_mcp_houdini; print('dcc_mcp_houdini OK')" 2>&1
& $Hython -c "import dcc_mcp_core; print('dcc_mcp_core OK')" 2>&1
