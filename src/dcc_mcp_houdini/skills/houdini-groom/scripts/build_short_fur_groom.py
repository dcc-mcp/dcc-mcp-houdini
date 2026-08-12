"""Build a native Houdini 22 short-fur groom network."""

from __future__ import annotations

from typing import Optional, Sequence

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def _node(hou, path: str):
    node = hou.node(path)
    if node is None:
        raise ValueError("Houdini node does not exist: {}".format(path))
    return node


def _find_type(parent, candidates: Sequence[str]) -> str:
    available = parent.childTypeCategory().nodeTypes()
    for candidate in candidates:
        if candidate in available:
            return candidate
    raise ValueError("Required Houdini node type is unavailable: {}".format(", ".join(candidates)))


def _set_first(node, names: Sequence[str], value) -> Optional[str]:
    for name in names:
        parm = node.parm(name)
        if parm is not None:
            parm.set(value)
            return name
    return None


def build_short_fur_groom(
    geo_path: str,
    rest_skin: str,
    animated_skin: Optional[str] = None,
    guides: Optional[str] = None,
    skin_group: str = "",
    density: float = 120000.0,
    length: float = 0.025,
    segments: int = 5,
    clump_strength: float = 0.15,
    deform_method: str = "surface",
    name_prefix: str = "insect_fur",
) -> dict:
    """Create Hair Generate, optional Hair Clump, and Guide Deform SOPs."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    created = []
    try:
        if not 0.001 <= float(density) <= 10000000:
            raise ValueError("density must be between 0.001 and 10000000")
        if not 0 < float(length) <= 10:
            raise ValueError("length must be greater than 0 and at most 10")
        if isinstance(segments, bool) or not 2 <= int(segments) <= 64:
            raise ValueError("segments must be between 2 and 64")
        if not 0 <= float(clump_strength) <= 1:
            raise ValueError("clump_strength must be between 0 and 1")
        if deform_method not in {"surface", "guide_shape", "point"}:
            raise ValueError("deform_method must be surface, guide_shape, or point")

        geo = _node(hou, geo_path)
        rest = _node(hou, "{}/{}".format(geo.path(), rest_skin))
        animated = _node(hou, "{}/{}".format(geo.path(), animated_skin)) if animated_skin else None
        guide_node = _node(hou, "{}/{}".format(geo.path(), guides)) if guides else None

        hair_type = _find_type(geo, ("hairgen::2.0", "hairgen"))
        hair = geo.createNode(hair_type, node_name="{}_generate".format(name_prefix))
        created.append(hair)
        hair.setInput(0, rest, 0)
        if guide_node is not None:
            hair.setInput(1, guide_node, 0)
        configured = {
            "density": _set_first(hair, ("density", "hairdensity"), float(density)),
            "length": _set_first(hair, ("unguidedlength", "length", "hairlength"), float(length)),
            "segments": _set_first(hair, ("unguidedsegments", "segments", "hairsegments"), int(segments)),
            "group": _set_first(hair, ("group",), str(skin_group)),
        }

        current = hair
        clump_path = None
        if clump_strength > 0:
            clump_type = _find_type(geo, ("hairclump::2.0", "hairclump"))
            clump = geo.createNode(clump_type, node_name="{}_clump".format(name_prefix))
            created.append(clump)
            clump.setFirstInput(current)
            clump.setInput(1, rest, 0)
            configured["clump_strength"] = _set_first(
                clump, ("blend", "strength", "clumpstrength"), float(clump_strength)
            )
            current = clump
            clump_path = clump.path()

        deform_path = None
        if animated is not None:
            deform_type = _find_type(geo, ("guidedeform::2.0", "guidedeform"))
            deform = geo.createNode(deform_type, node_name="{}_deform".format(name_prefix))
            created.append(deform)
            deform.setInput(0, current, 0)
            deform.setInput(1, rest, 0)
            deform.setInput(2, animated, 0)
            method_values = {
                "guide_shape": "guideshapeinterpolation",
                "surface": "surfacedeform",
                "point": "pointdeform",
            }
            configured["deform_method"] = _set_first(deform, ("method", "deformmethod"), method_values[deform_method])
            current = deform
            deform_path = deform.path()

        for node in created:
            node.moveToGoodPosition()
        current.setDisplayFlag(True)
        current.setRenderFlag(True)

        return skill_success(
            "Built short-fur groom",
            output_node_path=current.path(),
            hair_generate_path=hair.path(),
            hair_clump_path=clump_path,
            guide_deform_path=deform_path,
            rest_skin=rest.path(),
            animated_skin=animated.path() if animated is not None else None,
            guides=guide_node.path() if guide_node is not None else None,
            deform_method=deform_method if animated is not None else None,
            configured_parameters=configured,
        )
    except Exception as exc:
        for node in reversed(created):
            try:
                node.destroy()
            except Exception:  # noqa: BLE001
                pass
        return skill_exception(exc, message="Failed to build short-fur groom; created nodes were rolled back")


@skill_entry
def main(**kwargs) -> dict:
    return build_short_fur_groom(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
