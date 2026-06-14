"""Shared helpers for Houdini constraint skills."""

from __future__ import annotations

from typing import Any


def get_node(hou: Any, node_path: str) -> Any:
    """Return a Houdini node or raise a useful error."""
    node = hou.node(node_path)
    if node is None:
        raise ValueError("Houdini node not found: {}".format(node_path))
    return node


def find_blend_constraints(hou: Any, context_path: str = "/obj") -> list:
    """Return all blend nodes that act as constraints under *context_path*.

    A blend node is considered a constraint when it has one or more inputs
    connected from other OBJ nodes.
    """
    context = hou.node(context_path)
    if context is None:
        return []
    constraints = []
    for child in context.children():
        if child.type().name() != "blend":
            continue
        inputs = child.inputs()
        if not inputs:
            continue
        target_paths = [inp.path() for inp in inputs if inp is not None]
        constraints.append(
            {
                "path": child.path(),
                "name": child.name(),
                "targets": target_paths,
                "target_count": len(target_paths),
            }
        )
    return constraints


def ensure_not_exists(hou: Any, node_path: str) -> None:
    """Raise if a node already exists at *node_path*."""
    if hou.node(node_path) is not None:
        raise ValueError("Node already exists: {}".format(node_path))


def build_blend_node(
    hou: Any,
    driven_path: str,
    target_paths: list,
    weights: list | None = None,
    blend_name: str | None = None,
) -> Any:
    """Create a ``blend`` OBJ node wiring *driven_path* to *target_paths*.

    The blend node is created as a sibling of *driven_path* under the same
    parent, with each target connected as an input.  The driven object's
    transform parameters are expression-linked to the blend output.

    Returns the created blend node.
    """
    driven_node = get_node(hou, driven_path)
    parent = driven_node.parent()

    name = blend_name or "blend_{}".format(driven_node.name())
    blend_node = parent.createNode("blend", node_name=name)

    # Connect targets as inputs.
    connected = 0
    for target_path in target_paths:
        target_node = hou.node(target_path)
        if target_node is None:
            continue
        blend_node.setInput(connected, target_node)
        connected += 1

    if connected == 0:
        raise ValueError("No valid target paths connected")

    # Set per-target weights.
    if weights:
        for i, w in enumerate(weights[:connected]):
            blend_node.parm("weight{}".format(i + 1)).set(float(w))

    # Drive the driven object's transform from the blend output.
    driven_parms = {
        "tx": "tx",
        "ty": "ty",
        "tz": "tz",
        "rx": "rx",
        "ry": "ry",
        "rz": "rz",
        "sx": "sx",
        "sy": "sy",
        "sz": "sz",
    }
    for driven_parm, blend_parm in driven_parms.items():
        try:
            parm = driven_node.parm(driven_parm)
            if parm is not None:
                parm.setExpression(
                    'ch("{}")'.format(hou.hscriptExpression("{}/{}".format(blend_node.path(), blend_parm)))
                )
        except Exception:  # noqa: BLE001
            pass

    blend_node.moveToGoodPosition()

    return blend_node
