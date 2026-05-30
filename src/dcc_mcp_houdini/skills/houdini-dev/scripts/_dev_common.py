"""Shared helpers for the houdini-dev skill (headless-safe, host-agnostic)."""

from __future__ import annotations

import io
import os
import sys
import traceback
from contextlib import redirect_stderr, redirect_stdout
from typing import Any, Callable, List, Optional, Tuple

ENV_DEV_ROOTS = "DCC_MCP_HOUDINI_DEV_ROOTS"


def _path_list(raw: str) -> List[str]:
    sep = ";" if os.name == "nt" else ":"
    return [p for p in raw.split(sep) if p.strip()]


def allowed_roots() -> Optional[List[str]]:
    """Return the configured trusted dev roots, or None when unrestricted."""
    raw = os.environ.get(ENV_DEV_ROOTS)
    if not raw:
        return None
    return [os.path.normcase(os.path.abspath(p)) for p in _path_list(raw)]


def is_root_allowed(path: str) -> bool:
    """Return True when *path* is under a configured trusted root (or none set)."""
    roots = allowed_roots()
    if roots is None:
        return True
    candidate = os.path.normcase(os.path.abspath(path))
    return any(candidate == r or candidate.startswith(r + os.sep) for r in roots)


def capture_call(fn: Callable[[], Any]) -> Tuple[Any, str, str, Optional[str]]:
    """Run *fn* capturing stdout/stderr; return (result, out, err, traceback)."""
    out_buf, err_buf = io.StringIO(), io.StringIO()
    tb: Optional[str] = None
    result: Any = None
    try:
        with redirect_stdout(out_buf), redirect_stderr(err_buf):
            result = fn()
    except Exception:  # noqa: BLE001 - we surface the traceback to the agent
        tb = traceback.format_exc()
    return result, out_buf.getvalue(), err_buf.getvalue(), tb


def reload_by_prefix(prefix: str) -> List[str]:
    """Drop every imported module whose name matches *prefix* from sys.modules.

    Returns the list of purged module names so the next import reloads fresh.
    """
    purged = []
    for name in list(sys.modules.keys()):
        if name == prefix or name.startswith(prefix + "."):
            sys.modules.pop(name, None)
            purged.append(name)
    return purged


def has_ui(hou: Any) -> bool:
    """Best-effort detection of an interactive Houdini UI."""
    is_ui = getattr(hou, "isUIAvailable", None)
    if not callable(is_ui):
        return False
    try:
        return bool(is_ui())
    except Exception:  # noqa: BLE001
        return False
