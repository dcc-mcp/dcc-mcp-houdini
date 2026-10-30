"""Rig inversion: recover parent-relative local transforms (workflow stage 5).

"Rig inversion" is the inverse of forward kinematics: given a skeleton posed
with world-space joint transforms, compute the local (parent-relative)
transforms that a control rig needs. Two modes are supported:

* **headless** — pass ``world_matrices`` (list of 16-value 4x4 row-major
  matrices) and ``parent_indices``; pure linear algebra, no Houdini required.
* **scene** — pass ``rig_node``; read the KineFX skeleton's ``transform`` /
  ``P`` point attributes, invert them and write the local transforms back to a
  new skeleton SOP's stash (guarded across Houdini builds).
"""

from __future__ import annotations

from typing import Any, Optional

from _character_common import compute_local_transforms
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_IDENTITY = (
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
    """Build a 4x4 world matrix from a matrix3 transform and a translation."""
    t = list(transform) if transform is not None else [1, 0, 0, 0, 1, 0, 0, 0, 1]
    if len(t) == 16:
        t = [t[0], t[1], t[2], t[4], t[5], t[6], t[8], t[9], t[10]]
    while len(t) < 9:
        t.append(0.0)
    p = list(position) if position is not None else [0.0, 0.0, 0.0]
    while len(p) < 3:
        p.append(0.0)
    return (
        t[0],
        t[1],
        t[2],
        p[0],
        t[3],
        t[4],
        t[5],
        p[1],
        t[6],
        t[7],
        t[8],
        p[2],
        0.0,
        0.0,
        0.0,
        1.0,
    )


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
                "world_matrices and parent_indices are both required in headless mode",
            )
        try:
            locals_out = compute_local_transforms(world_matrices, parent_indices)
        except (ValueError, TypeError) as exc:
            return skill_error("Rig inversion failed", str(exc))
        return skill_success(
            "Inverted rig transforms (headless)",
            mode="headless",
            joint_count=len(locals_out),
            local_transforms=locals_out,
        )

    if not rig_node:
        return skill_error(
            "No input",
            "Provide rig_node for scene mode, or world_matrices+parent_indices for headless mode",
        )

    try:
        import hou  # Lazy import: requires Houdini's embedded Python.
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        node = hou.node(rig_node)
        if node is None:
            return skill_error("Rig node not found", rig_node=rig_node)
        geometry = node.geometry()
        if geometry is None:
            return skill_error("No geometry", "rig node has no geometry")

        points = list(geometry.points())
        transform_attr = geometry.findPointAttrib("transform")
        worlds = []
        for pt in points:
            transform = pt.attribValue("transform") if transform_attr is not None else None
            worlds.append(_point_world_from(transform, pt.position()))

        # KineFX stores hierarchy as parent->child edge polygons. Derive parent
        # indices from the first two vertices of each line/polygon; fall back to
        # a linear chain (previous point) when no edges are present.
        parents = _parent_indices(geometry, len(points))
        try:
            locals_out = compute_local_transforms(worlds, parents)
        except (ValueError, TypeError) as exc:
            return skill_error("Rig inversion failed", str(exc))

        # Write local transforms back to a fresh skeleton SOP stash, guarded.
        editable = hou.Geometry(geometry)
        out_node = node.parent().createNode("kinefx::skeleton", node_name=output_name)
        stash = out_node.parm("stash")
        if stash is not None:
            local_attr = editable.findPointAttrib("transform")
            if local_attr is not None:
                for index, pt in enumerate(list(editable.points())):
                    local = locals_out[index]
                    matrix3 = (
                        local[0],
                        local[1],
                        local[2],
                        local[4],
                        local[5],
                        local[6],
                        local[8],
                        local[9],
                        local[10],
                    )
                    pt.setAttribValue(local_attr, matrix3)
            stash.set(editable)
        out_node.cook(force=True)
        try:
            node.parent().layoutChildren()
        except Exception:  # noqa: BLE001
            pass

        return skill_success(
            "Inverted rig to local transforms",
            mode="scene",
            rig_node=node.path(),
            output_node=out_node.path(),
            joint_count=len(locals_out),
            parent_indices=parents,
            local_transforms=locals_out,
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
        for index in range(point_count):
            parents[index] = derived.get(index, -1 if index == 0 else parents[index])
    return parents


@skill_entry
def main(**kwargs) -> dict:
    return invert_rig(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
