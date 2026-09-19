"""Bounded HOM graph operations shared by DOP, COP and TOP skills.

These helpers never import hou or cook a node. Category checks and readback
fail explicitly; an inaccessible host property is not an empty success.
"""

from __future__ import annotations

import math
import re
from contextlib import contextmanager

from dcc_mcp_core.skill import skill_error

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_NODE_TYPE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:::[A-Za-z0-9_.]+)*$")


def validate_identifier(value, label="node name"):
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError("Invalid {}: {!r}".format(label, value))
    return value


def validate_node_type(value):
    if not isinstance(value, str) or not _NODE_TYPE.fullmatch(value):
        raise ValueError("Invalid node type: {!r}".format(value))
    return value


def get_node(hou, node_path):
    if not isinstance(node_path, str) or not node_path.startswith("/"):
        raise ValueError("node path must be absolute")
    node = hou.node(node_path)
    if node is None:
        raise ValueError("Houdini node not found: {}".format(node_path))
    return node


def require_category(node, expected, children=False):
    category = node.childTypeCategory() if children else node.type().category()
    if category is None or category.name() != expected:
        raise ValueError("{} must have {} {}category".format(node.path(), expected, "child " if children else ""))
    return node


def validate_parameters(parameters):
    if parameters is None:
        return {}
    if not isinstance(parameters, dict) or len(parameters) > 32:
        raise ValueError("parameters must be an object with at most 32 entries")
    for name, value in parameters.items():
        validate_identifier(name, "Houdini parameter name")
        values = value if isinstance(value, (tuple, list)) else [value]
        if not 1 <= len(values) <= 16:
            raise ValueError("parameter tuples must contain 1 to 16 scalar values")
        for item in values:
            if not isinstance(item, (str, bool, int, float)) or isinstance(item, float) and not math.isfinite(item):
                raise ValueError("parameters must contain finite scalar values")
            if isinstance(item, str) and len(item) > 4096:
                raise ValueError("parameter strings may contain at most 4096 characters")
    return parameters


def parameter_targets(node, parameters):
    targets = []
    seen = set()
    for name, value in validate_parameters(parameters).items():
        if isinstance(value, (list, tuple)):
            parm_tuple = node.parmTuple(name)
            if parm_tuple is None or len(parm_tuple) != len(value):
                raise ValueError("Missing or mismatched parameter tuple: {}".format(name))
            pairs = zip(parm_tuple, value)
        else:
            parm = node.parm(name)
            if parm is None:
                raise ValueError("Parameter not found: {}".format(name))
            pairs = [(parm, value)]
        for parm, item in pairs:
            if parm.name() in seen:
                raise ValueError("Overlapping parameter edits: {}".format(name))
            seen.add(parm.name())
            targets.append((parm, item))
    return targets


@contextmanager
def parameter_edit(node, parameters):
    """Restore values, expressions and animation if any edit/readback fails."""
    targets = parameter_targets(node, parameters)
    snapshots = []
    for parm, _ in targets:
        keys = parm.keyframes()
        value = parm.eval()
        if not keys and isinstance(value, str):
            value = parm.unexpandedString()
        snapshots.append((parm, keys, value))
    changed = []
    try:
        for (parm, value), snapshot in zip(targets, snapshots):
            changed.append(snapshot)
            parm.set(value, follow_parm_reference=False)
        yield {parm.name(): parm.eval() for parm, _ in targets}
    except BaseException:
        failures = []
        for parm, keys, value in reversed(changed):
            try:
                parm.deleteAllKeyframes()
                if keys:
                    parm.setKeyframes(keys)
                else:
                    parm.set(value, follow_parm_reference=False)
            except Exception:
                failures.append(parm.name())
        if failures:
            raise RuntimeError("Parameter rollback failed: {}".format(", ".join(failures))) from None
        raise


def set_parameters(node, parameters):
    with parameter_edit(node, parameters) as applied:
        return applied, []


@contextmanager
def owned_node(parent, node_type, node_name=None):
    """Destroy only the node created by this call if its receipt fails."""
    if node_name is not None:
        validate_identifier(node_name)
    node = parent.createNode(validate_node_type(node_type), node_name=node_name)
    try:
        yield node
    except BaseException:
        node.destroy()
        raise


def resolve_inputs(hou, network, input_nodes):
    if input_nodes is None:
        return []
    if not isinstance(input_nodes, (list, tuple)) or len(input_nodes) > 32:
        raise ValueError("input_nodes must contain at most 32 paths")
    sources = []
    for path in input_nodes:
        if not isinstance(path, str):
            raise ValueError("input paths must be strings")
        source = get_node(hou, path) if path.startswith("/") else network.node(validate_identifier(path))
        if source is None or source.parent() != network:
            raise ValueError("Inputs must be existing nodes in the same network")
        sources.append(source)
    return sources


def next_free_input(node, limit=32):
    """First free input index of a node, bounded so a bad graph cannot loop."""
    used = set()
    for connection in node.inputConnections():
        used.add(connection.inputIndex())
    for index in range(limit):
        if index not in used:
            return index
    raise ValueError("No free input available on {}".format(node.path()))


def node_summary(node):
    return {
        "path": node.path(),
        "name": node.name(),
        "type": node.type().name(),
        "errors": list(node.errors()),
        "warnings": list(node.warnings()),
    }


def input_connections(node):
    return [
        {
            "input_index": connection.inputIndex(),
            "source_path": connection.inputItem().path(),
            "source_output_index": connection.inputItemOutputIndex(),
        }
        for connection in node.inputConnections()
    ]


def hou_missing_error():
    return skill_error("Houdini not available", "hou could not be imported")
