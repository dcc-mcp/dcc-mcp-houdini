"""Rig inversion: recover parent-relative local transforms (workflow stage 5).

"Rig inversion" is the inverse of forward kinematics: given a skeleton posed
with world-space joint transforms, compute the local (parent-relative)
transforms a control rig needs. Two modes are supported:

* **headless** -- pass ``world_matrices`` + ``parent_indices``; pure math.
* **scene** -- pass ``rig_node``; read the KineFX skeleton point attributes,
  invert them and author a fresh skeleton SOP stash, writing parent-relative
  transforms to the Float-16 ``localtransform`` matrix4 (verified on licensed
  Houdini 22.0.368).

Matrix convention (both modes, and ``_character_common``): Houdini's
row-vector / row-major 4x4 layout, ``v' = v * M``. The 3x3 rotation block is
the upper-left 9 values and the translation is in the BOTTOM ROW (flat slots
12/13/14). Forward kinematics is ``world[i] = local[i] * world[parent]``, so
inversion is ``local[i] = world[i] * inverse(world[parent])``. Using one
convention end-to-end avoids mirroring the rotation direction (review F3).
"""

from __future__ import annotations

from typing import Any, Optional

from _character_common import compute_local_transforms
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

# KineFX stores parent-relative joint transforms in the ``localtransform``
# point attribute (NOT the world ``transform`` matrix3 read from the source).
# Verified on licensed Houdini 22.0.368: ``kinefx::computetransform`` authors
# ``localtransform`` as a Float-16 matrix4 (full 4x4, Houdini row-vector with
# translation in the bottom row); the joint world position stays in ``P`` and
# the world 3x3 rotation stays in ``transform`` (Float-9 matrix3).
LOCAL_TRANSFORM_ATTRIBUTE = "localtransform"

_IDENTITY_M3 = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)
_IDENTITY_M4 = (
    1.0,
    0.0,
    0.0,
    0.0,
    0.0,
    1.0,
    0.0,
    0.0,
    0.0,
    0.0,
    1.0,
    0.0,
    0.0,
    0.0,
    0.0,
    1.0,
)


def _point_world_from(transform, position):
    """Build a 4x4 world matrix (Houdini row-vector) from a matrix3 and P.

    ``transform`` is a KineFX ``transform`` matrix3 (9 values, Houdini
    row-vector rotation); ``position`` is the point ``P``. Translation is
    placed in the BOTTOM ROW (slots 12/13/14) -- the 3/7/11 last-column layout
    used previously mixed conventions and mirrored rotations on inversion.
    The 3x3 block is copied verbatim (no transpose).
    """
    t = list(transform) if transform is not None else []
    if len(t) == 16:
        t = [t[0], t[1], t[2], t[4], t[5], t[6], t[8], t[9], t[10]]
    if not t:
        t = list(_IDENTITY_M3)
    while len(t) < 9:
        t.append(0.0)
    p = list(position) if position is not None else [0.0, 0.0, 0.0]
    while len(p) < 3:
        p.append(0.0)
    return (
        t[0],
        t[1],
        t[2],
        0.0,
        t[3],
        t[4],
        t[5],
        0.0,
        t[6],
        t[7],
        t[8],
        0.0,
        p[0],
        p[1],
        p[2],
        1.0,
    )


def _rotation3(world):
    """Extract the 3x3 rotation block from a row-vector 4x4 world matrix."""
    return (
        world[0],
        world[1],
        world[2],
        world[4],
        world[5],
        world[6],
        world[8],
        world[9],
        world[10],
    )


def _write_local_skeleton(hou, container, names, worlds, locals_out, parents, output_name, local_attribute):
    """Author a fresh KineFX skeleton SOP stash from inverted local transforms.

    Uses only ``hou.Geometry()`` + explicit ``createPoints`` / ``addAttrib`` /
    ``createPolygon`` -- the established ``_kinefx_common.get_or_create_rig``
    pattern -- instead of the unverified ``hou.Geometry(existing_geo)`` copy
    constructor. Any failure (including a missing ``stash`` parameter) is
    raised so the caller cannot silently report success.

    Verified on licensed Houdini 22.0.368 (``kinefx::computetransform``): ``P``
    keeps the world joint position, ``transform`` is the world Float-9 matrix3,
    and the parent-relative result belongs in ``local_attribute`` as a Float-16
    matrix4 (rotation upper-left, translation in the bottom row). Writing the
    local result to ``transform`` (or as a rotation-only Float-9) is wrong.
    """
    editable = hou.Geometry()
    world_positions = [(world[12], world[13], world[14]) for world in worlds]
    new_points = editable.createPoints(world_positions)
    name_attr = editable.addAttrib(hou.attribType.Point, "name", "")
    transform_attr = editable.addAttrib(hou.attribType.Point, "transform", _IDENTITY_M3)
    local_attr = editable.addAttrib(hou.attribType.Point, local_attribute, _IDENTITY_M4)
    for index, pt in enumerate(new_points):
        pt.setAttribValue(name_attr, str(names[index] or "joint_{}".format(index)))
        pt.setAttribValue(transform_attr, _rotation3(worlds[index]))
        pt.setAttribValue(local_attr, tuple(locals_out[index]))
    for child, parent in enumerate(parents):
        if 0 <= parent < len(new_points):
            edge = editable.createPolygon()
            edge.setIsClosed(False)
            edge.addVertex(new_points[parent])
            edge.addVertex(new_points[child])

    out_node = container.createNode("kinefx::skeleton", node_name=output_name)
    stash = out_node.parm("stash")
    if stash is None:
        raise RuntimeError("KineFX skeleton SOP has no stash parameter")
    stash.set(editable)
    out_node.cook(force=True)
    return out_node, list(out_node.errors()), len(new_points)


def invert_rig(
    rig_node: Optional[str] = None,
    world_matrices: Optional[list] = None,
    parent_indices: Optional[list] = None,
    output_name: str = "inverted_rig",
) -> dict:
    """Invert a rig to local transforms. See module docstring for modes."""
    headless = world_matrices is not None or parent_indices is not None
    if headless:
        if not world_matrices or not parent_indices:
            return skill_error(
                "Incomplete headless input",
                "incomplete_headless_input",
                hint="world_matrices and parent_indices are both required in headless mode",
            )
        try:
            locals_out = compute_local_transforms(world_matrices, parent_indices)
        except (ValueError, TypeError) as exc:
            return skill_error("Rig inversion failed", "rig_inversion_failed", detail=str(exc))
        return skill_success(
            "Inverted rig transforms (headless)",
            mode="headless",
            convention="houdini_row_vector",
            joint_count=len(locals_out),
            local_transforms=locals_out,
        )

    if not rig_node:
        return skill_error(
            "No input",
            "no_input",
            hint="Provide rig_node for scene mode, or world_matrices+parent_indices for headless mode",
        )

    try:
        import hou  # Lazy import: requires Houdini's embedded Python.
    except ImportError:
        return skill_error("Houdini not available", "hou_not_available", hint="hou could not be imported")

    try:
        node = hou.node(rig_node)
        if node is None:
            return skill_error("Rig node not found", "rig_node_not_found", rig_node=rig_node)
        geometry = node.geometry()
        if geometry is None:
            return skill_error("No geometry", "no_geometry", hint="rig node has no geometry")

        points = list(geometry.points())
        if not points:
            return skill_error("No points", "no_points", hint="rig node has no skeleton points")
        transform_attr = geometry.findPointAttrib("transform")
        name_attr = geometry.findPointAttrib("name")
        worlds = []
        names = []
        for pt in points:
            transform = pt.attribValue("transform") if transform_attr is not None else None
            worlds.append(_point_world_from(transform, pt.position()))
            names.append(pt.attribValue("name") if name_attr is not None else "")

        # KineFX stores hierarchy as parent->child edge polygons. Derive parent
        # indices from the first/last vertices of each edge; fall back to a
        # linear chain (previous point) when no edges are present.
        parents = _parent_indices(geometry, len(points))
        try:
            locals_out = compute_local_transforms(worlds, parents)
        except (ValueError, TypeError) as exc:
            return skill_error("Rig inversion failed", "rig_inversion_failed", detail=str(exc))

        # Write local transforms back to a fresh skeleton SOP stash. No silent
        # skip: a missing stash parameter or a failed writeback is an error.
        try:
            out_node, cook_errors, joint_count = _write_local_skeleton(
                hou, node.parent(), names, worlds, locals_out, parents, output_name, LOCAL_TRANSFORM_ATTRIBUTE
            )
        except Exception as exc:  # noqa: BLE001 - surfaced as a structured error
            return skill_error(
                "Local transform writeback failed",
                "writeback_failed",
                detail=str(exc),
                local_attribute=LOCAL_TRANSFORM_ATTRIBUTE,
                hint="Confirm the KineFX local transform attribute and stash parameter on a licensed Houdini host.",
            )
        if cook_errors:
            return skill_error(
                "Inverted skeleton cook failed",
                "cook_failed",
                output_node=out_node.path(),
                errors=[str(err) for err in cook_errors],
            )
        try:
            node.parent().layoutChildren()
        except Exception:  # noqa: BLE001 - layout is cosmetic
            pass

        return skill_success(
            "Inverted rig to local transforms",
            mode="scene",
            convention="houdini_row_vector",
            rig_node=node.path(),
            output_node=out_node.path(),
            joint_count=joint_count,
            parent_indices=parents,
            local_transforms=locals_out,
            local_attribute=LOCAL_TRANSFORM_ATTRIBUTE,
            local_attribute_type="matrix4",
            writeback=True,
            cook_errors=cook_errors,
            validated=not cook_errors,
            note=(
                "Local transforms are authored to the KineFX '{}' Float-16 matrix4 "
                "point attribute on a fresh hou.Geometry() stash; the world matrix3 "
                "stays in 'transform' and the world position in 'P'. Attribute name, "
                "type, stash parameter and cook were verified on licensed Houdini "
                "22.0.368; final whole-scene visual/cook acceptance remains QA."
            ).format(LOCAL_TRANSFORM_ATTRIBUTE),
        )
    except Exception as exc:  # noqa: BLE001
        return skill_exception(exc, message="Failed to invert rig")


def _parent_indices(geometry: Any, point_count: int) -> list:
    """Derive parent indices from skeleton edge polygons, else linear chain."""
    parents = [-1] + [index - 1 for index in range(1, point_count)]
    try:
        prims = list(geometry.prims())
    except Exception:  # noqa: BLE001
        return parents
    if not prims:
        return parents
    derived = {}
    for prim in prims:
        try:
            vertices = list(prim.vertices())
            if len(vertices) >= 2:
                parent_pt = vertices[0].point().number()
                child_pt = vertices[-1].point().number()
                if 0 <= parent_pt < point_count and 0 <= child_pt < point_count:
                    derived[child_pt] = parent_pt
        except Exception:  # noqa: BLE001
            continue
    if derived:
        # Any point that is not a child in an edge polygon is a root. Treat it
        # as -1 rather than keeping the linear-chain fallback (previous point),
        # which is wrong for multi-root skeletons or a root not at index 0.
        for index in range(point_count):
            parents[index] = derived.get(index, -1)
    return parents


@skill_entry
def main(**kwargs) -> dict:
    return invert_rig(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
