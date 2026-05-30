"""Run a Python file inside Houdini."""

from __future__ import annotations

import contextlib
import io
import os
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _automation_common import existing_file, hou_import_error


@contextlib.contextmanager
def _pushd(path: Optional[str]):
    if not path:
        yield
        return
    old = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)


def run_python_file(
    file_path: str,
    args: Optional[List[Any]] = None,
    context: Optional[Dict[str, Any]] = None,
    working_directory: Optional[str] = None,
) -> dict:
    """Execute a Python file with Houdini globals."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return hou_import_error()

    try:
        path = existing_file(file_path, suffixes={".py"})
        if working_directory is not None and not Path(working_directory).expanduser().is_dir():
            return skill_error("Working directory not found", str(working_directory))
        namespace: Dict[str, Any] = {
            "__file__": str(path),
            "__name__": "__dcc_mcp_houdini_script__",
            "hou": hou,
            "args": list(args or []),
            "context": dict(context or {}),
        }
        namespace.update(context or {})
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        try:
            with _pushd(working_directory), contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(
                stderr_buf
            ):
                exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), namespace)  # noqa: S102
        except Exception:
            error = traceback.format_exc()
            return skill_error(
                "Python file execution failed",
                error,
                stdout=stdout_buf.getvalue(),
                stderr=stderr_buf.getvalue() + error,
            )
        return skill_success(
            "Python file executed successfully",
            file_path=str(path),
            stdout=stdout_buf.getvalue(),
            stderr=stderr_buf.getvalue(),
            result=str(namespace.get("result")) if namespace.get("result") is not None else None,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to run Houdini Python file")


@skill_entry
def main(**kwargs) -> dict:
    return run_python_file(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
