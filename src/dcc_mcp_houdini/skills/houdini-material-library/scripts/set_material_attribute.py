"""Set an attribute on a material/shader node with type coercion."""

from __future__ import annotations

from typing import Any

from _library_common import get_node, hou_import_error, node_summary, set_node_parameter  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def set_material_attribute(
    material_path: str,
    attribute_name: str,
    value: Any,
) -> dict:
    """Set a parameter/attribute on a material/shader node.

    Args:
        material_path: Path to the material/shader node.
        attribute_name: Name of the parameter to set.
        value: Value to set (scalar or list/tuple for tuple params).

    Returns:
        ToolResult dict.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return hou_import_error()

    try:
        node = get_node(hou, material_path)

        # Check if the parameter exists.
        parm = node.parm(attribute_name)
        parm_tuple = node.parmTuple(attribute_name)
        if parm is None and parm_tuple is None:
            # List available parameter names for diagnostics.
            available = [p.name() for p in node.parms()]
            return skill_error(
                "Parameter {!r} not found on {}".format(attribute_name, material_path),
                "Available parameters (first 20): {}".format(", ".join(available[:20])),
            )

        old_value = None
        try:
            if isinstance(value, (list, tuple)):
                if parm_tuple is not None:
                    old_value = list(parm_tuple.eval())
            elif parm is not None:
                old_value = parm.eval()
        except Exception:  # noqa: BLE001
            pass

        coerced = set_node_parameter(node, attribute_name, value)

        return skill_success(
            "Set material attribute",
            material=node_summary(node),
            attribute=attribute_name,
            set_value=coerced,
            previous_value=old_value,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to set material attribute")


@skill_entry
def main(**kwargs) -> dict:
    return set_material_attribute(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
