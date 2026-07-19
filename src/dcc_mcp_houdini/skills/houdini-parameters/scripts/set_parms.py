"""Set one or many Houdini parameters with type-aware coercion."""

from __future__ import annotations

from typing import Any, Dict

from _parm_common import channel_write_conflict, coerce_scalar, get_node  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def set_parms(node_path: str, parameters: Dict[str, Any]) -> dict:
    """Set the given parameters, reporting per-parameter validation errors.

    Tuple values (lists) target parm tuples; scalars target single parms with
    best-effort coercion to the parm's existing value type. Existing animation
    and expressions are preserved and reported as per-parameter conflicts.
    Errors are collected per parameter rather than aborting the whole call.
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
                    conflicts = []
                    for parm in parm_tuple:
                        conflict = channel_write_conflict(parm)
                        if conflict is not None:
                            conflicts.append(conflict)
                    if conflicts:
                        errors[name] = "Cannot set parameter tuple {!r}: {}".format(name, "; ".join(conflicts))
                        continue
                    parm_tuple.set(tuple(value))
                    applied[name] = list(value)
                else:
                    parm = node.parm(name)
                    if parm is None:
                        errors[name] = "No parameter named {!r}".format(name)
                        continue
                    conflict = channel_write_conflict(parm)
                    if conflict is not None:
                        errors[name] = conflict
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
