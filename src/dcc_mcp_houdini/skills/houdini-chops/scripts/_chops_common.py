"""Shared helpers for Houdini CHOP skills."""

from __future__ import annotations

from typing import Any, Dict


def get_node(hou: Any, node_path: str) -> Any:
    """Return a Houdini node or raise a useful error."""
    node = hou.node(node_path)
    if node is None:
        raise ValueError("Houdini node not found: {}".format(node_path))
    return node


def get_or_create_network(hou: Any, network_path: str) -> Any:
    """Return the CHOP network at *network_path*, creating it if missing."""
    node = hou.node(network_path)
    if node is not None:
        return node
    # Walk up to find the closest existing parent, then create downwards.
    parts = network_path.strip("/").split("/")
    for i in range(len(parts) - 1, -1, -1):
        parent_path = "/" + "/".join(parts[: i + 1])
        parent = hou.node(parent_path)
        if parent is not None:
            # Create remaining levels as CHOP networks.
            for name in parts[i + 1 :]:
                parent = parent.createNode("chopnet", node_name=name)
            return parent
    raise ValueError("Cannot resolve CHOP network path: {}".format(network_path))


def ensure_chop_network(hou: Any, parent_path: str, network_name: str) -> Any:
    """Create a CHOP network container under *parent_path*."""
    parent = hou.node(parent_path)
    if parent is None:
        raise ValueError("Parent node not found: {}".format(parent_path))
    existing = hou.node("{}/{}".format(parent.path(), network_name))
    if existing is not None:
        return existing
    return parent.createNode("chopnet", node_name=network_name)


def chop_node_info(node: Any) -> dict:
    """Extract summary info from a CHOP node."""
    info: Dict[str, Any] = {
        "path": node.path(),
        "name": node.name(),
        "type": node.type().name(),
    }
    # Sample rate
    try:
        info["sample_rate"] = node.sampleRate()
    except Exception:  # noqa: BLE001
        info["sample_rate"] = None
    # Segment length
    try:
        info["segment_length"] = node.segmentLength()
    except Exception:  # noqa: BLE001
        info["segment_length"] = None
    # Channel names
    try:
        channels = node.channels()
        info["channel_names"] = [c.name() for c in channels]
        info["channel_count"] = len(info["channel_names"])
    except Exception:  # noqa: BLE001
        info["channel_names"] = []
        info["channel_count"] = 0
    # Time range
    try:
        track = node.timeRange()
        info["time_range"] = [track[0], track[1]]
    except Exception:  # noqa: BLE001
        info["time_range"] = None
    return info
