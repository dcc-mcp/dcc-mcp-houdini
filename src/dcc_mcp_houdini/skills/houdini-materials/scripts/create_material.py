"""Create a Houdini material node."""

from __future__ import annotations

from typing import Any, Dict, Optional

from _material_common import get_node, hou_import_error, node_summary, set_parm_value
from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success


def _shader_candidates(shader_type: str) -> list:
    candidates = [shader_type]
    if shader_type == "principledshader::2.0":
        candidates.append("principledshader")
    return candidates


def create_material(
    parent_path: str = "/mat",
    shader_type: str = "principledshader::2.0",
    material_name: Optional[str] = None,
    parameters: Optional[Dict[str, Any]] = None,
    exact_type_name: bool = False,
    set_current: bool = False,
) -> dict:
    """Create a material/shader node and set optional parameters."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return hou_import_error()

    try:
        parent = get_node(hou, parent_path)
        last_error = None
        material = None
        created_type = shader_type
        for candidate in _shader_candidates(shader_type):
            try:
                material = parent.createNode(
                    candidate,
                    node_name=material_name,
                    run_init_scripts=True,
                    load_contents=True,
                    exact_type_name=exact_type_name,
                )
                created_type = candidate
                break
            except Exception as exc:  # noqa: BLE001
                last_error = exc
        if material is None:
            raise last_error or RuntimeError("Could not create material")

        for name, value in (parameters or {}).items():
            set_parm_value(material, name, value)
        if set_current and hasattr(material, "setCurrent"):
            material.setCurrent(True, clear_all_selected=True)

        return skill_success(
            "Created Houdini material",
            parent_path=parent.path(),
            requested_shader_type=shader_type,
            shader_type=created_type,
            material=node_summary(material),
            parameters=list((parameters or {}).keys()),
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to create Houdini material")


@skill_entry
def main(**kwargs) -> dict:
    return create_material(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
