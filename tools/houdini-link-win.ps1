# Houdini link script for Windows
# Creates a junction from Houdini's site-packages to src/dcc_mcp_houdini

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

if (-not (Test-Path $SitePackages)) {
    Write-Error "Site-packages not found: $SitePackages"
    exit 1
}

# ── Create junction ───────────────────────────────────────────────────────
$ProjectRoot = Resolve-Path "$PSScriptRoot\.."
$SourceDir = "$ProjectRoot\src\dcc_mcp_houdini"
$TargetLink = "$SitePackages\dcc_mcp_houdini"

if (Test-Path $TargetLink) {
    Write-Host "Removing existing: $TargetLink" -ForegroundColor Yellow
    Remove-Item $TargetLink -Recurse -Force
}

cmd /c mklink /J "$TargetLink" "$SourceDir"
if ($LASTEXITCODE -eq 0) {
    Write-Host "Linked: $TargetLink -> $SourceDir" -ForegroundColor Green
}
else {
    Write-Error "Failed to create junction"
    exit 1
}

# ── Also link dcc_mcp_core if in editable mode ───────────────────────────
$CoreRepo = Resolve-Path "$ProjectRoot\..\dcc-mcp-core" -ErrorAction SilentlyContinue
if ($CoreRepo) {
    $CoreSource = "$CoreRepo\python\dcc_mcp_core"
    $CoreTarget = "$SitePackages\dcc_mcp_core"
    
    if (Test-Path $CoreSource) {
        if (Test-Path $CoreTarget) {
            Remove-Item $CoreTarget -Recurse -Force
        }
        cmd /c mklink /J "$CoreTarget" "$CoreSource"
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Linked core: $CoreTarget -> $CoreSource" -ForegroundColor Green
        }
    }
}

Write-Host "Done! Restart Houdini to load changes." -ForegroundColor Green
