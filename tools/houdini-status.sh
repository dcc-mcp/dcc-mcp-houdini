#!/usr/bin/env sh
set -eu
if [ -z "${HOUDINI_PYTHON:-}" ]; then
  echo "Set HOUDINI_PYTHON to Houdini's python executable"
  exit 1
fi
SITE="$("$HOUDINI_PYTHON" -c 'import site; print(site.getsitepackages()[0])')"
TARGET="$SITE/dcc_mcp_houdini"
if [ -L "$TARGET" ] || [ -d "$TARGET" ]; then
  echo "Linked: $TARGET -> $(readlink "$TARGET" 2>/dev/null || echo '(directory)')"
else
  echo "Not linked: $TARGET"
fi
"$HOUDINI_PYTHON" -c "import dcc_mcp_houdini; print('import OK', dcc_mcp_houdini.__version__)" 2>/dev/null || echo "import failed"
