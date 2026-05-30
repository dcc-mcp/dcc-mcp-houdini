"""Import and call a Python entrypoint (module:function) with captured output."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _dev_common import capture_call  # noqa: E402


def run_entrypoint(
    entrypoint: str,
    args: Optional[List[Any]] = None,
    kwargs: Optional[Dict[str, Any]] = None,
    reload: bool = True,
) -> dict:
    """Call ``module:function`` (or ``module.function``) and capture output.

    Returns stdout/stderr text, a repr of the return value, and any traceback.
    """
    try:
        sep = ":" if ":" in entrypoint else "."
        module_name, _, func_name = entrypoint.rpartition(sep)
        if not module_name or not func_name:
            return skill_error(
                "Invalid entrypoint",
                "Use 'module:function' or 'module.function', got {!r}".format(entrypoint),
            )

        module = sys.modules.get(module_name)
        if module is not None and reload:
            module = importlib.reload(module)
        elif module is None:
            module = importlib.import_module(module_name)

        func = getattr(module, func_name, None)
        if not callable(func):
            return skill_error(
                "Entrypoint not callable",
                "{}.{} is not callable".format(module_name, func_name),
            )

        call_args = list(args or [])
        call_kwargs = dict(kwargs or {})
        result, out, err, tb = capture_call(lambda: func(*call_args, **call_kwargs))
        if tb is not None:
            return skill_error(
                "Entrypoint raised",
                "Exception while calling {}".format(entrypoint),
                entrypoint=entrypoint,
                stdout=out,
                stderr=err,
                traceback=tb,
            )
        return skill_success(
            "Ran entrypoint",
            entrypoint=entrypoint,
            result_repr=repr(result),
            stdout=out,
            stderr=err,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to run entrypoint")


@skill_entry
def main(**kwargs) -> dict:
    return run_entrypoint(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
