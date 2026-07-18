"""Test loader that mirrors the shared skill runner's import contract."""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


@contextmanager
def skill_script_import_context(spec: Any) -> Iterator[None]:
    """Temporarily expose a skill script's directory while it is imported."""
    if not spec.origin:
        raise ValueError("skill module spec has no origin")
    script_dir = str(Path(spec.origin).resolve().parent)
    owns_path = script_dir not in sys.path
    if owns_path:
        sys.path.insert(0, script_dir)
    try:
        yield
    finally:
        if owns_path and script_dir in sys.path:
            sys.path.remove(script_dir)
