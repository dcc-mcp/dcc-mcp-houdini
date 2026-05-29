"""Set one or many Houdini parameters with type-aware coercion."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _parm_common import coerce_scalar, get_node  # noqa: E402


def set_parms(node_path: str, parameters: Dict[str, Any]) -> dict:
    """Set the given parameters, reporting per-parameter validation errors.

    Tuple values (lists) target parm tuples; scalars target single parms with
    best-effort coercion to the parm's existing value type. Errors are collected
    per parameter rather than aborting the whole call.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        node = get_node(hou, node_path)
        applied: Dict[str, Any] = {}
        errors: Dict[str, str] = {}
        for name, value in parameters.items():
            try:
                if isinstance(value, (list, tuple)):
                    parm_tuple = node.parmTuple(name)
                    if parm_tuple is None:
                        errors[name] = "No parameter tuple named {!r}".format(name)
                        continue
                    parm_tuple.set(tuple(value))
                    applied[name] = list(value)
                else:
                    parm = node.parm(name)
                    if parm is None:
                        errors[name] = "No parameter named {!r}".format(name)
                        continue
                    try:
                        current = parm.eval()
                    except Exception:  # noqa: BLE001
                        current = None
                    coerced = coerce_scalar(value, current)
                    parm.set(coerced)
                    applied[name] = coerced
            except Exception as exc:  # noqa: BLE001
                errors[name] = str(exc)
        if not applied and errors:
            return skill_error(
                "No parameters set",
                "All parameters failed validation",
                node_path=node.path(),
                errors=errors,
            )
        return skill_success(
            "Set parameters",
            node_path=node.path(),
            applied=applied,
            errors=errors,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to set parameters")


@skill_entry
def main(**kwargs) -> dict:
    return set_parms(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
