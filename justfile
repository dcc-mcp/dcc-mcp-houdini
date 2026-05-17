# dcc-mcp-houdini justfile
# Requires: https://github.com/casey/just
#
# Quick reference:
#   just                                    — show this help
#   just dev                                — pip install -e ".[dev]"
#   just test                               — pytest
#   just lint                               — ruff check + format check
#   just houdini-version=20.5 houdini-dev-build-link-core-win  — build core + symlink (Windows)
#
# Cross-platform: uses sh on Unix/macOS, pwsh on Windows for dev-* commands.

# Default shell (Unix/macOS). Windows dev commands below override to pwsh.
set shell := ["sh", "-cu"]
set windows-shell := ["pwsh.exe", "-NoProfile", "-Command"]

# Default Houdini version — override with: just houdini-version=20.5 <recipe>
houdini-version := "20.5"

# Default Python interpreter — override with: just python="hython" <recipe>
python := "hython"

# ── Basics ─────────────────────────────────────────────────────────────────────

@default:
    just --list

# ── Development (install in editable mode) ────────────────────────────────────

# Unix/macOS: symlink src/dcc_mcp_houdini into Houdini's Python site-packages
houdini-link:
    ./tools/houdini-link.sh {{houdini-version}}

# Windows: symlink src/dcc_mcp_houdini into Houdini's Python site-packages
houdini-link-win:
    powershell -NoProfile -ExecutionPolicy Bypass -File tools/houdini-link-win.ps1 -HoudiniVersion {{houdini-version}}

# Remove symlinks (Unix/macOS)
houdini-unlink:
    ./tools/houdini-unlink.sh {{houdini-version}}

# Remove symlinks (Windows)
houdini-unlink-win:
    powershell -NoProfile -ExecutionPolicy Bypass -File tools/houdini-unlink-win.ps1 -HoudiniVersion {{houdini-version}}

# Show link status (Unix/macOS)
houdini-status:
    ./tools/houdini-status.sh {{houdini-version}}

# Show link status (Windows)
houdini-status-win:
    powershell -NoProfile -ExecutionPolicy Bypass -File tools/houdini-status-win.ps1 -HoudiniVersion {{houdini-version}}

# Full local dev setup: link + verify
houdini-dev: houdini-link
    @echo ""
    @echo "📋 Dev environment linked. Now start Houdini."
    @echo "   Then in Houdini: verify dcc_mcp_houdini can be imported"
    @echo ""

# ============================================================================
# Houdini + Core Development (with dcc-mcp-core build)
# ============================================================================

# Windows: build dcc-mcp-core with Houdini's Python (hython), then symlink both
# `dcc_mcp_core` (from core's `python/dcc_mcp_core`) and `dcc_mcp_houdini`
# (from `src/dcc_mcp_houdini`) into Houdini's Python site-packages.
# Then start Houdini for debugging.
#
# After run, use MCP URL printed below; see Houdini MCP setup docs for VS Code + debugpy.
# Default core repo: sibling directory `../dcc-mcp-core` or env `DCC_MCP_CORE_REPO`.
#
#   just houdini-version=20.5 houdini-dev-build-link-core-win
#   just houdini-version=20.5 houdini-dev-debug-win
@houdini-dev-build-link-core-win: (houdini-version)
    powershell -NoProfile -ExecutionPolicy Bypass -File tools/houdini-dev-build-link-core-win.ps1 -HoudiniVersion {{houdini-version}}

@houdini-dev-debug-win: (houdini-version)
    powershell -NoProfile -ExecutionPolicy Bypass -File tools/houdini-dev-build-link-core-win.ps1 -HoudiniVersion {{houdini-version}} -LaunchHoudini

# Windows: only refresh symlinks (skip maturin develop) after you already built core.
@houdini-dev-relink-core-win: (houdini-version)
    powershell -NoProfile -ExecutionPolicy Bypass -File tools/houdini-dev-build-link-core-win.ps1 -HoudiniVersion {{houdini-version}} -SkipBuild

# ── Houdini startup (for debug) ───────────────────────────────────────────────

# Start Houdini with debugpy support (Unix/macOS)
houdini-start:
    ./tools/houdini-start.sh {{houdini-version}}

# Start Houdini with debugpy support (Windows)
houdini-start-win:
    powershell -NoProfile -ExecutionPolicy Bypass -File tools/houdini-start-win.ps1 -HoudiniVersion {{houdini-version}}

# ── Run ───────────────────────────────────────────────────────────────────────

# Start the MCP server (inside Houdini's Python)
serve:
    {{python}} -m dcc_mcp_houdini

# ── Test & Lint ───────────────────────────────────────────────────────────────

test:
    pytest tests/ -v --tb=short

test-cov:
    pytest tests/ -v --tb=short --cov=src/dcc_mcp_houdini --cov-report=term-missing

lint:
    ruff check src/ tests/

lint-format:
    ruff format --check src/ tests/

fix:
    ruff check --fix src/ tests/

format:
    ruff format src/ tests/

lint-all: lint lint-format

# ── Build ─────────────────────────────────────────────────────────────────────

build:
    python -m build

clean:
    python -c "import shutil, pathlib; [shutil.rmtree(p, ignore_errors=True) for p in ['dist', 'build', 'src/dcc_mcp_houdini.egg-info']]"
    @echo "Cleaned dist/, build/, and egg-info"

# ── CI helper ─────────────────────────────────────────────────────────────────

ci: test lint-all
    @echo "All CI checks passed"
