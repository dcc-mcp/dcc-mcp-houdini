#!/usr/bin/env sh
set -eu
VERSION="${1:-20.5}"
if [ -z "${HOUDINI_PYTHON:-}" ]; then
  echo "Set HOUDINI_PYTHON to Houdini's python executable"
  exit 1
fi
SITE="$("$HOUDINI_PYTHON" -c 'import site; print(site.getsitepackages()[0])')"
rm -rf "$SITE/dcc_mcp_houdini"
echo "Removed $SITE/dcc_mcp_houdini"
