"""Recreate a material from a JSON preset file and optionally assign it to objects."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from _library_common import get_node, hou_import_error, node_summary, set_node_parameter  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def load_material_preset(
    file_path: str,
    material_name: Optional[str] = None,
    parent_path: str = "/mat",
    assign_to: Optional[List[str]] = None,
) -> dict:
    """Recreate a material from a JSON preset file.

    Args:
        file_path: Path to the .json preset file.
        material_name: Override name for the created material node.
        parent_path: Material network to create the node under.
        assign_to: Optional list of OBJ/SOP node paths to assign to.

    Returns:
        ToolResult dict with the created node and assignment info.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return hou_import_error()

    try:
        try:
            with open(file_path, encoding="utf-8") as handle:
                preset_data = json.load(handle)
        except (IOError, ValueError) as exc:
            return skill_error("Cannot read preset {!r}".format(file_path), str(exc))

        node_type = preset_data.get("material_type", "principledshader")
        default_name = preset_data.get("material_path", "").rsplit("/", 1)[-1] or "material_preset"
        name = material_name or default_name

        # Create the material node.
        parent = get_node(hou, parent_path)
        try:
            material = parent.createNode(node_type, node_name=name)
        except Exception:
            # Fallback: try principledshader as a safe default.
            material = parent.createNode("principledshader::2.0", node_name=name)

        # Apply saved parameters.
        parameters: Dict[str, Any] = preset_data.get("parameters", {})
        applied = 0
        errors: Dict[str, str] = {}
        for attr, val in parameters.items():
            try:
                set_node_parameter(material, attr, val)
                applied += 1
            except Exception as exc:  # noqa: BLE001
                errors[attr] = str(exc)

        # Optionally assign to objects.
        assigned_to: List[str] = []
        if assign_to:
            for obj_path in assign_to:
                try:
                    obj_node = get_node(hou, obj_path)
                    parm = obj_node.parm("shop_materialpath")
                    if parm is not None:
                        parm.set(material.path())
                        assigned_to.append(obj_path)
                except Exception:  # noqa: BLE001
                    pass

        return skill_success(
            "Loaded material preset",
            material=node_summary(material),
            preset_type=node_type,
            applied_count=applied,
            error_count=len(errors),
            errors=errors,
            assigned_to=assigned_to,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to load material preset")


@skill_entry
def main(**kwargs) -> dict:
    return load_material_preset(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
