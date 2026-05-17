# Houdini + dcc-mcp-core local dev helper (Windows)
# Usage:
#   powershell -File tools/houdini-dev-build-link-core-win.ps1 -HoudiniVersion 20.5
#   just houdini-version=20.5 houdini-dev-build-link-core-win
#
# 1) Build dcc-mcp-core with Houdini's Python (hython)
# 2) Symlink dcc_mcp_core into Houdini's site-packages
# 3) Symlink dcc_mcp_houdini into Houdini's site-packages
# 4) Optionally launch Houdini

[CmdletBinding()]
param(
    [Parameter(Mandatory=$false)]
    [string]$HoudiniVersion = "20.5",

    [Parameter(Mandatory=$false)]
    [switch]$LaunchHoudini,

    [Parameter(Mandatory=$false)]
    [switch]$SkipBuild,

    [Parameter(Mandatory=$false)]
    [string]$CoreRepo = ""
)

$ErrorActionPreference = "Stop"

# ── Resolve paths ──────────────────────────────────────────────────────────────
if ([string]::IsNullOrEmpty($CoreRepo)) {
    $CoreRepo = Resolve-Path "$PSScriptRoot\..\..\dcc-mcp-core" -ErrorAction SilentlyContinue
    if (-not $CoreRepo) {
        $CoreRepo = Resolve-Path "$PSScriptRoot\..\..\..\dcc-mcp-core" -ErrorAction SilentlyContinue
    }
    if (-not $CoreRepo) {
        Write-Error "Cannot find dcc-mcp-core repo. Please set DCC_MCP_CORE_REPO or place it as a sibling directory."
        exit 1
    }
}

$CoreRepo = Resolve-Path $CoreRepo
Write-Host "[1/5] Core repo: $CoreRepo" -ForegroundColor Cyan

# ── Find Houdini Python (hython) ──────────────────────────────────────────────
$HoudiniBase = "C:\Program Files\Side Effects Software\Houdini $HoudiniVersion"
if (-not (Test-Path $HoudiniBase)) {
    Write-Error "Houdini $HoudiniVersion not found at: $HoudiniBase"
    Write-Host "Please install Houdini $HoudiniVersion or specify correct -HoudiniVersion" -ForegroundColor Yellow
    exit 1
}

# Find hython executable (Python version may vary)
$HythonCandidates = @(
    "$HoudiniBase\bin\hython.exe",
    Get-ChildItem "$HoudiniBase\python*\python.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
)

$Hython = $null
foreach ($candidate in $HythonCandidates) {
    if ($candidate -and (Test-Path $candidate)) {
        $Hython = $candidate
        break
    }
}

if (-not $Hython) {
    Write-Error "Cannot find hython in: $HoudiniBase"
    exit 1
}

Write-Host "[2/5] Houdini Python: $Hython" -ForegroundColor Cyan

# ── Houdini site-packages ──────────────────────────────────────────────────────
# Houdini's Python site-packages is typically in:
# C:\Program Files\Side Effects Software\Houdini X.Y\pythonXX\lib\site-packages
$PythonDir = Split-Path $Hython -Parent
$PythonVersion = & $Hython -c "import sys; print(f'{sys.version_info.major}{sys.version_info.minor}')"
$SitePackages = "$HoudiniBase\python$PythonVersion\lib\site-packages"

if (-not (Test-Path $SitePackages)) {
    Write-Error "Site-packages not found: $SitePackages"
    exit 1
}

Write-Host "[3/5] Site-packages: $SitePackages" -ForegroundColor Cyan

# ── Build dcc-mcp-core (unless SkipBuild) ────────────────────────────────────
if (-not $SkipBuild) {
    Write-Host "[4/5] Building dcc-mcp-core with Houdini Python..." -ForegroundColor Cyan

    Push-Location $CoreRepo
    try {
        # Install maturin if needed
        & $Hython -m pip install maturin --quiet

        # Build core with maturin
        & $Hython -m maturin develop --release -m crates/dcc-mcp-core/Cargo.toml
        if ($LASTEXITCODE -ne 0) {
            Write-Error "maturin develop failed"
            exit 1
        }

        # Install Python package in editable mode
        & $Hython -m pip install -e "$CoreRepo\python\dcc_mcp_core" --quiet
        if ($LASTEXITCODE -ne 0) {
            Write-Error "pip install dcc_mcp_core failed"
            exit 1
        }
    }
    finally {
        Pop-Location
    }
}
else {
    Write-Host "[4/5] Skipping build (SkipBuild specified)" -ForegroundColor Yellow
}

# ── Symlink dcc_mcp_houdini ──────────────────────────────────────────────────
Write-Host "[5/5] Linking dcc_mcp_houdini..." -ForegroundColor Cyan

$ProjectRoot = Resolve-Path "$PSScriptRoot\.."
$SourceDir = "$ProjectRoot\src\dcc_mcp_houdini"
$TargetLink = "$SitePackages\dcc_mcp_houdini"

if (Test-Path $TargetLink) {
    Write-Host "  Removing existing: $TargetLink" -ForegroundColor Yellow
    Remove-Item $TargetLink -Recurse -Force
}

# Create junction (works without admin)
cmd /c mklink /J "$TargetLink" "$SourceDir"
if ($LASTEXITCODE -eq 0) {
    Write-Host "  Linked: $TargetLink -> $SourceDir" -ForegroundColor Green
}
else {
    Write-Error "Failed to create junction for dcc_mcp_houdini"
    exit 1
}

# ── Verify ────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "Verifying import..." -ForegroundColor Cyan
& $Hython -c "import dcc_mcp_houdini; print(f'dcc_mcp_houdini {dcc_mcp_houdini.__version__}')"
if ($LASTEXITCODE -ne 0) {
    Write-Error "Import verification failed"
    exit 1
}

& $Hython -c "import dcc_mcp_core; print('dcc_mcp_core OK')"
if ($LASTEXITCODE -ne 0) {
    Write-Warning "dcc_mcp_core import failed - you may need to run without -SkipBuild first"
}

# ── Launch Houdini (optional) ────────────────────────────────────────────────
if ($LaunchHoudini) {
    Write-Host ""
    Write-Host "Starting Houdini $HoudiniVersion..." -ForegroundColor Green
    $HoudiniExe = "$HoudiniBase\bin\houdini.exe"
    Start-Process $HoudiniExe
}

Write-Host ""
Write-Host "Done! MCP URL will be printed when you start Houdini and run:" -ForegroundColor Green
Write-Host "  import dcc_mcp_houdini; dcc_mcp_houdini.start_server()" -ForegroundColor Yellow
