#!/usr/bin/env bash
set -euo pipefail

pick_python() {
  for candidate in python3 hython; do
    if command -v "$candidate" >/dev/null 2>&1; then
      if "$candidate" - <<'PY' >/dev/null 2>&1
import hou
print(hou.applicationVersionString())
PY
      then
        echo "$candidate"
        return 0
      fi
    fi
  done
  return 1
}

PYTHON_BIN="$(pick_python)"
echo "Using Houdini Python: $PYTHON_BIN"
"$PYTHON_BIN" - <<'PY'
import hou
print("Houdini:", hou.applicationVersionString())
PY

"$PYTHON_BIN" -m ensurepip --upgrade >/dev/null 2>&1 || true
"$PYTHON_BIN" -m pip install --upgrade pip
"$PYTHON_BIN" -m pip install -e ".[dev]"
"$PYTHON_BIN" .github/scripts/run_houdini_e2e.py
