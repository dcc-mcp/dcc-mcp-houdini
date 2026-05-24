#!/usr/bin/env sh
# Launch Houdini (Unix/macOS). Set HOUDINI_APP to the houdini binary if needed.
set -eu
VERSION="${1:-20.5}"
APP="${HOUDINI_APP:-}"
if [ -z "$APP" ]; then
  echo "Set HOUDINI_APP to your houdini executable path"
  exit 1
fi
exec "$APP"
