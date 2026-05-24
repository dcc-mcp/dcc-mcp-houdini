#!/usr/bin/env sh
# Symlink dcc_mcp_houdini into Houdini site-packages (Unix/macOS).
set -eu
VERSION="${1:-20.5}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SOURCE="$ROOT/src/dcc_mcp_houdini"

if [ -z "${HOUDINI_PYTHON:-}" ]; then
  echo "Set HOUDINI_PYTHON to Houdini's python executable, e.g.:"
  echo "  export HOUDINI_PYTHON=/Applications/Houdini/Houdini${VERSION}/Frameworks/Houdini.framework/Versions/Current/Resources/bin/hython"
  exit 1
fi

SITE="$("$HOUDINI_PYTHON" -c 'import site; print(site.getsitepackages()[0])')"
TARGET="$SITE/dcc_mcp_houdini"
rm -rf "$TARGET"
ln -s "$SOURCE" "$TARGET"
echo "Linked $TARGET -> $SOURCE"
