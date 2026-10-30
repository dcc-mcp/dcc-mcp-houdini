"""Pack an APEX biped character and report the FBX export (workflow stage 8).

Fills the "KineFx APEX FBX biped template" stage: takes a biped skeleton (and
optionally a skinned mesh / imported FBX) and packs a Houdini 22 APEX character
with the base biped rig, then reports the exact ``export_fbx`` arguments needed
to write an engine-ready FBX biped. This ties the whole workflow together:
biped template -> retarget -> rig inversion -> APEX -> FBX.
"""

from __future__ import annotations

from typing import Any, Optional

from _character_common import CONVENTIONS, convention_names
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def _set_if_present(node: Any, name: str, value: Any) -> None:
    parm = node.parm(name)
    if parm is not None:
        parm.set(value)


def build_apex_fbx_biped(
    geo_path: str,
    skeleton: str,
    skinned_mesh: Optional[str] = None,
    character_name: str = "biped_character",
    convention: str = "kinefx",
    skel_path: str = "Base.skel",
    rig_path: str = "Base.rig",
    output_fbx: Optional[str] = None,
    node_prefix: str = "dcc_mcp_apex_biped",
) -> dict:
    """Pack an APEX biped character and return the FBX export contract.

    Args:
        geo_path: Geometry SOP container holding skeleton + mesh.
        skeleton: Path to the biped skeleton SOP.
        skinned_mesh: Optional path to a skinned/captured mesh SOP.
        character_name: APEX character name.
        convention: Biped naming convention (used for the FBX joint map).
        skel_path: APEX skeleton path inside the character.
        rig_path: APEX rig path inside the character.
        output_fbx: Desired FBX output path; used to build the export contract.
        node_prefix: Prefix for created nodes.
    """
    if convention not in CONVENTIONS:
        return skill_error(
            "Unknown naming convention",
            "convention must be one of {}".format(", ".join(CONVENTIONS)),
            convention=convention,
        )
    if not isinstance(geo_path, str) or not geo_path.strip():
        return skill_error("Invalid geo_path", "geo_path must be a non-empty string")

    try:
        import hou  # Lazy import: requires Houdini's embedded Python.
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        container = hou.node(geo_path)
        skel = hou.node(skeleton)
        if container is None or skel is None:
            return skill_error(
                "Node not found",
                "geo_path or skeleton path is invalid",
                geo_path=geo_path,
                skeleton=skeleton,
            )
        mesh = hou.node(skinned_mesh) if skinned_mesh else None

        def create(type_name, name):
            node = container.createNode(type_name, node_name="{}_{}".format(node_prefix, name))
            node.setComment("DCC-MCP typed APEX FBX biped template")
            return node

        created = []
        pack = create("apex::packcharacter", "pack")
        pack.setInput(2, skel)
        if mesh is not None:
            try:
                pack.setInput(0, mesh)
                pack.setInput(1, mesh)
            except Exception:  # noqa: BLE001
                pass
        _set_if_present(pack, "isscene", 1)
        _set_if_present(pack, "charname", character_name)
        _set_if_present(pack, "skelpath", skel_path)
        _set_if_present(pack, "rigpath", rig_path)
        _set_if_present(pack, "addbaserig", 1)
        created.append(pack)

        # A biped autorig graph node, guarded so the tool works on builds where
        # the dedicated biped graph SOP is named differently / absent.
        try:
            biped_graph = create("apex::addgraph", "biped_graph")
            biped_graph.setInput(0, pack)
            _set_if_present(biped_graph, "graphname", "Base.rig")
            created.append(biped_graph)
            scene_output = biped_graph
        except Exception:  # noqa: BLE001
            scene_output = pack

        output_node = create("null", "OUT")
        output_node.setInput(0, scene_output)
        created.append(output_node)

        failures = []
        for node in created:
            node.cook(force=True)
            errors = list(node.errors())
            warnings = list(node.warnings())
            if errors or warnings:
                failures.append({"path": node.path(), "errors": errors, "warnings": warnings})
        try:
            container.layoutChildren()
        except Exception:  # noqa: BLE001
            pass

        names = convention_names(convention)
        export_contract = {
            "tool": "houdini_interchange__export_fbx",
            "arguments": {
                "output_path": output_fbx or "<set output_fbx>",
                "root_node": output_node.path(),
                "convert_units": True,
            },
            "unit_note": (
                "Keep convert_units=True so a meter-authored biped is not 100x "
                "too small when the FBX declares centimeters; verify physical "
                "world bounds and pivot in the target engine."
            ),
        }

        return skill_success(
            "Packed APEX FBX biped template",
            geo_path=container.path(),
            skeleton=skel.path(),
            skinned_mesh=mesh.path() if mesh is not None else None,
            character_name=character_name,
            convention=convention,
            skel_path=skel_path,
            rig_path=rig_path,
            apex_scene=scene_output.path(),
            output_node=output_node.path(),
            joint_names=list(names.values()),
            joint_count=len(names),
            created_nodes=[node.path() for node in created],
            cook_failures=failures,
            validated=not failures,
            export_fbx=export_contract,
            next_tools=["houdini_interchange__export_fbx", "houdini_interchange__probe_file"],
        )
    except Exception as exc:  # noqa: BLE001
        return skill_exception(exc, message="Failed to build APEX FBX biped")


@skill_entry
def main(**kwargs) -> dict:
    return build_apex_fbx_biped(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
