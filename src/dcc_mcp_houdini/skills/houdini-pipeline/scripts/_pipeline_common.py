"""Shared helpers for the houdini-pipeline skill (adapter-owned, filesystem-first)."""

from __future__ import annotations

import os
from typing import Any, List, Optional

# Adapter-owned metadata key prefix stored as Houdini node user data / hip
# file metadata. Kept generic so it never leaks a private production service.
META_PREFIX = "dcc_mcp_meta:"


def get_node(hou: Any, node_path: str) -> Any:
    """Return a Houdini node or raise a useful error."""
    node = hou.node(node_path)
    if node is None:
        raise ValueError("Houdini node not found: {}".format(node_path))
    return node


def node_summary(node: Any) -> dict:
    """Return a small, JSON-safe node summary."""
    type_obj = node.type()
    return {
        "path": node.path(),
        "name": node.name(),
        "type": type_obj.name() if hasattr(type_obj, "name") else str(type_obj),
    }


def is_file_parm(hou: Any, parm: Any) -> bool:
    """Best-effort detection of a file-reference parameter."""
    try:
        template = parm.parmTemplate()
    except Exception:  # noqa: BLE001
        return False
    string_type = getattr(getattr(hou, "parmTemplateType", None), "String", None)
    if string_type is not None and template.type() != string_type:
        return False
    # hou.StringParmType.FileReference when available.
    string_kind = getattr(template, "stringType", None)
    file_ref = getattr(getattr(hou, "stringParmType", None), "FileReference", None)
    if callable(string_kind) and file_ref is not None:
        try:
            return string_kind() == file_ref
        except Exception:  # noqa: BLE001
            return False
    return False


def iter_file_parms(hou: Any, node: Any) -> List[Any]:
    """Return file-reference parms on *node* with a non-empty evaluated value."""
    found = []
    try:
        parms = node.parms()
    except Exception:  # noqa: BLE001
        return found
    for parm in parms:
        if not is_file_parm(hou, parm):
            continue
        try:
            value = parm.eval()
        except Exception:  # noqa: BLE001
            continue
        if isinstance(value, str) and value.strip():
            found.append(parm)
    return found


def expand_path(hou: Any, raw: str) -> str:
    """Expand Houdini variables in a path string, falling back to os.path."""
    try:
        return hou.text.expandString(raw)
    except Exception:  # noqa: BLE001
        return os.path.expandvars(raw)


def resolve_nodes(hou: Any, node_paths: Optional[List[str]]) -> List[Any]:
    """Resolve explicit node paths, or fall back to the whole node tree.

    When *node_paths* is falsy, walk from ``/`` collecting all nodes.
    """
    if node_paths:
        nodes = []
        for path in node_paths:
            node = hou.node(path)
            if node is not None:
                nodes.append(node)
        return nodes
    root = hou.node("/")
    if root is None or not hasattr(root, "allSubChildren"):
        return []
    try:
        return list(root.allSubChildren())
    except Exception:  # noqa: BLE001
        return []
