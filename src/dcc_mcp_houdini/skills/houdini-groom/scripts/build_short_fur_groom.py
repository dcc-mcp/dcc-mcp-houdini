"""Build a native Houdini 22 short-fur groom network."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Optional, Sequence

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_REGION_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,31}$")
_REGION_KEYS = {"name", "skin_group", "guides", "density", "length", "segments", "clump_strength"}


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


def _geometry_counts(node) -> tuple[int, int]:
    geometry = node.geometry()
    if geometry is None:
        raise ValueError("Node has no cooked geometry: {}".format(node.path()))
    return int(geometry.intrinsicValue("pointcount")), int(geometry.intrinsicValue("primitivecount"))


def _validate_surface_pair(rest, animated) -> None:
    rest_counts = _geometry_counts(rest)
    animated_counts = _geometry_counts(animated)
    if rest_counts != animated_counts:
        raise ValueError(
            "Surface Deform requires matching rest/deformed skin topology; "
            "rest has {} points/{} primitives and deformed has {} points/{} primitives".format(
                rest_counts[0], rest_counts[1], animated_counts[0], animated_counts[1]
            )
        )


def _validate_fur_values(density: float, length: float, segments: int, clump_strength: float) -> None:
    if not 0.001 <= float(density) <= 10000000:
        raise ValueError("density must be between 0.001 and 10000000")
    if not 0 < float(length) <= 10:
        raise ValueError("length must be greater than 0 and at most 10")
    if isinstance(segments, bool) or not 2 <= int(segments) <= 64:
        raise ValueError("segments must be between 2 and 64")
    if not 0 <= float(clump_strength) <= 1:
        raise ValueError("clump_strength must be between 0 and 1")


def _normalize_regions(
    region_profiles,
    *,
    skin_group: str,
    guides: Optional[str],
    density: float,
    length: float,
    segments: int,
    clump_strength: float,
) -> list[dict]:
    if region_profiles is None:
        _validate_fur_values(density, length, segments, clump_strength)
        return [
            {
                "name": None,
                "skin_group": str(skin_group),
                "guides": guides,
                "density": float(density),
                "length": float(length),
                "segments": int(segments),
                "clump_strength": float(clump_strength),
            }
        ]
    if not isinstance(region_profiles, (list, tuple)) or not 1 <= len(region_profiles) <= 16:
        raise ValueError("region_profiles must contain between 1 and 16 region objects")

    normalized = []
    names = set()
    for index, profile in enumerate(region_profiles):
        if not isinstance(profile, Mapping):
            raise ValueError("region profile {} must be an object".format(index))
        unknown = sorted(set(profile) - _REGION_KEYS)
        if unknown:
            raise ValueError("region profile {} contains unsupported keys: {}".format(index, ", ".join(unknown)))
        name = profile.get("name")
        group = profile.get("skin_group")
        if not isinstance(name, str) or _REGION_NAME_RE.fullmatch(name) is None:
            raise ValueError("region name must start with a letter and contain only letters, numbers, or underscores")
        if name in names:
            raise ValueError("region names must be unique: {}".format(name))
        if not isinstance(group, str) or not group.strip():
            raise ValueError("region skin_group must be a non-empty string")
        names.add(name)
        region = {
            "name": name,
            "skin_group": group,
            "guides": profile.get("guides", guides),
            "density": float(profile.get("density", density)),
            "length": float(profile.get("length", length)),
            "segments": int(profile.get("segments", segments)),
            "clump_strength": float(profile.get("clump_strength", clump_strength)),
        }
        if region["guides"] is not None and not isinstance(region["guides"], str):
            raise ValueError("region guides must be a SOP node name")
        _validate_fur_values(region["density"], region["length"], region["segments"], region["clump_strength"])
        normalized.append(region)
    return normalized


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
    region_profiles=None,
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
        if deform_method not in {"surface", "guide_shape", "point"}:
            raise ValueError("deform_method must be surface, guide_shape, or point")
        regions = _normalize_regions(
            region_profiles,
            skin_group=skin_group,
            guides=guides,
            density=density,
            length=length,
            segments=segments,
            clump_strength=clump_strength,
        )

        geo = _node(hou, geo_path)
        rest = _node(hou, "{}/{}".format(geo.path(), rest_skin))
        animated = _node(hou, "{}/{}".format(geo.path(), animated_skin)) if animated_skin else None
        guide_nodes = {
            region["name"]: _node(hou, "{}/{}".format(geo.path(), region["guides"])) if region["guides"] else None
            for region in regions
        }
        if animated is not None and deform_method == "surface":
            _validate_surface_pair(rest, animated)

        hair_type = _find_type(geo, ("hairgen::2.0", "hairgen"))
        region_outputs = []
        region_context = []
        for region in regions:
            suffix = "_{}".format(region["name"]) if region["name"] else ""
            hair = geo.createNode(hair_type, node_name="{}{}_generate".format(name_prefix, suffix))
            created.append(hair)
            hair.setInput(0, rest, 0)
            guide_node = guide_nodes[region["name"]]
            if guide_node is not None:
                hair.setInput(1, guide_node, 0)
            configured = {
                "density": _set_first(hair, ("density", "hairdensity"), region["density"]),
                "length": _set_first(hair, ("unguidedlength", "length", "hairlength"), region["length"]),
                "segments": _set_first(hair, ("unguidedsegments", "segments", "hairsegments"), region["segments"]),
                "group": _set_first(hair, ("group",), region["skin_group"]),
            }

            current = hair
            clump_path = None
            if region["clump_strength"] > 0:
                clump_type = _find_type(geo, ("hairclump::2.0", "hairclump"))
                clump = geo.createNode(clump_type, node_name="{}{}_clump".format(name_prefix, suffix))
                created.append(clump)
                clump.setFirstInput(current)
                clump.setInput(1, rest, 0)
                configured["clump_strength"] = _set_first(
                    clump, ("blend", "strength", "clumpstrength"), region["clump_strength"]
                )
                current = clump
                clump_path = clump.path()
            region_outputs.append(current)
            region_context.append(
                {
                    **region,
                    "guides": guide_node.path() if guide_node is not None else None,
                    "hair_generate_path": hair.path(),
                    "hair_clump_path": clump_path,
                    "configured_parameters": configured,
                }
            )

        merge_path = None
        if len(region_outputs) > 1:
            merge = geo.createNode("merge", node_name="{}_merge".format(name_prefix))
            created.append(merge)
            for index, output in enumerate(region_outputs):
                merge.setInput(index, output, 0)
            current = merge
            merge_path = merge.path()
        else:
            current = region_outputs[0]

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
        current.cook(force=True)
        cook_errors = list(current.errors())
        if cook_errors:
            raise RuntimeError("Groom output failed to cook: {}".format("; ".join(cook_errors)))
        output_counts = _geometry_counts(current)

        return skill_success(
            "Built short-fur groom",
            output_node_path=current.path(),
            hair_generate_path=region_context[0]["hair_generate_path"],
            hair_clump_path=region_context[0]["hair_clump_path"],
            merge_path=merge_path,
            guide_deform_path=deform_path,
            rest_skin=rest.path(),
            animated_skin=animated.path() if animated is not None else None,
            guides=region_context[0]["guides"] if len(region_context) == 1 else None,
            region_count=len(region_context),
            regions=region_context,
            deform_method=deform_method if animated is not None else None,
            configured_parameters=region_context[0]["configured_parameters"],
            output_point_count=output_counts[0],
            output_primitive_count=output_counts[1],
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
