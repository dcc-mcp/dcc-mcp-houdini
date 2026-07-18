"""Query which renderable objects a material/shader is assigned to (read-only)."""

from __future__ import annotations

from typing import List

from _library_common import get_node, hou_import_error, node_summary  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success

# Parameter names that carry material assignment on renderable nodes.
_ASSIGN_PARMS = ("shop_materialpath", "shop_materialpath1", "material")


def get_shader_assignment(
    material_path: str,
    search_root: str = "/obj",
) -> dict:
    """Query which renderable objects use *material_path*.

    Searches OBJ/SOP nodes under *search_root* for material-path parameters
    that reference the given material.

    Args:
        material_path: Path to the material/shader node.
        search_root: Root path to search for assignments.

    Returns:
        ToolResult dict with a list of assigned objects.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return hou_import_error()

    try:
        material_node = get_node(hou, material_path)
        mat_path = material_node.path()
        root = get_node(hou, search_root)

        assigned: List[dict] = []
        other_assignments: List[dict] = []

        # Walk all descendant nodes looking for material assignments.
        for child in root.allSubChildren():
            assigned_material = None
            parm_name_used = None

            for pname in _ASSIGN_PARMS:
                parm = child.parm(pname)
                if parm is None:
                    continue
                try:
                    value = parm.eval()
                except Exception:  # noqa: BLE001
                    continue
                if value and isinstance(value, str) and value.strip():
                    assigned_material = value
                    parm_name_used = pname
                    break

            if assigned_material is None:
                continue

            entry = {
                "object_path": child.path(),
                "object_name": child.name(),
                "object_type": child.type().name() if hasattr(child.type(), "name") else str(child.type()),
                "assigned_material": assigned_material,
                "parameter": parm_name_used,
            }

            if assigned_material == mat_path:
                assigned.append(entry)
            else:
                other_assignments.append(entry)

        return skill_success(
            "Queried shader assignment",
            material=node_summary(material_node),
            material_path=mat_path,
            search_root=root.path(),
            assigned_count=len(assigned),
            assigned_objects=assigned,
            other_objects_count=len(other_assignments),
            other_objects=other_assignments[:50] if other_assignments else None,  # Limit for large scenes
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to get shader assignment")


@skill_entry
def main(**kwargs) -> dict:
    return get_shader_assignment(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
