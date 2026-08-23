"""Create a USD scene snapshot for husk rendering — export current stage state."""

from __future__ import annotations

import os
from typing import Optional

from _husk_common import get_node, set_parm_if_exists  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def _node_type_name(node) -> Optional[str]:
    try:
        name = node.type().name().split("::", 1)[0]
    except Exception:  # noqa: BLE001
        return None
    return name if isinstance(name, str) else None


def _is_lop_node(node) -> bool:
    try:
        category_name = node.type().category().name()
    except Exception:  # noqa: BLE001
        return False
    return category_name == "Lop"


def _resolve_lop_source(node):
    path = node.path()
    if path == "/stage" or _node_type_name(node) == "lopnet":
        display_node = node.displayNode()
        return display_node
    if path.startswith("/stage/") or _is_lop_node(node):
        return node
    return None


def create_snapshot(
    source_path: str = "/stage",
    snapshot_path: str = "/tmp/husk_snapshot.usd",
    flatten: bool = False,
    frame: Optional[float] = None,
) -> dict:
    """Export the current stage/LOP network as a USD snapshot for husk."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        node = get_node(hou, source_path)
        source = _resolve_lop_source(node)
        if source is None:
            if node.path() == "/stage" or _node_type_name(node) == "lopnet":
                return skill_error(
                    "Snapshot creation failed",
                    "EMPTY_LOP_NETWORK",
                    code="EMPTY_LOP_NETWORK",
                    source=source_path,
                )
            return skill_error(
                "Snapshot source is not a Solaris LOP",
                "UNSUPPORTED_SNAPSHOT_SOURCE",
                prompt="Export this source with the typed interchange tool before Husk rendering.",
                code="UNSUPPORTED_SNAPSHOT_SOURCE",
                source=node.path(),
                suggested_snapshot=snapshot_path,
                dcc={"next_tools": ["houdini_interchange__export_usd"]},
            )

        output_frame = float(frame) if frame is not None else float(hou.frame())
        expand_at_frame = getattr(getattr(hou, "text", None), "expandStringAtFrame", None)
        if not callable(expand_at_frame):
            expand_at_frame = getattr(hou, "expandStringAtFrame", None)
        expanded_snapshot_path = (
            expand_at_frame(snapshot_path, output_frame)
            if callable(expand_at_frame)
            else hou.expandString(snapshot_path)
        )
        output_dir = os.path.dirname(os.path.abspath(expanded_snapshot_path))
        os.makedirs(output_dir, exist_ok=True)
        previous = os.stat(expanded_snapshot_path) if os.path.isfile(expanded_snapshot_path) else None
        usd_rop = None
        try:
            usd_rop = source.parent().createNode("usd_rop", node_name="snapshot_export")
            usd_rop.setInput(0, source)
            required = {
                "lopoutput": snapshot_path,
                "savestyle": "flattenstage" if flatten else "flattenimplicitlayers",
                "trange": 1 if frame is not None else 0,
            }
            if frame is not None:
                required.update({"f1": float(frame), "f2": float(frame), "f3": 1.0})
            missing = [name for name, value in required.items() if not set_parm_if_exists(usd_rop, name, value)]
            execute = usd_rop.parm("execute")
            if missing or execute is None:
                raise RuntimeError("USD ROP is missing parameters: {}".format(", ".join(missing or ["execute"])))
            execute.pressButton()

            current = os.stat(expanded_snapshot_path) if os.path.isfile(expanded_snapshot_path) else None
            written = (
                current is not None
                and current.st_size > 0
                and (
                    previous is None
                    or (current.st_mtime_ns, current.st_size) != (previous.st_mtime_ns, previous.st_size)
                )
            )
            if not written:
                return skill_error(
                    "Snapshot creation failed",
                    "USD ROP did not write a non-empty snapshot",
                    source=source.path(),
                    snapshot_path=snapshot_path,
                    expanded_snapshot_path=expanded_snapshot_path,
                )
            return skill_success(
                "Created USD snapshot",
                source=source.path(),
                snapshot_path=snapshot_path,
                expanded_snapshot_path=expanded_snapshot_path,
                written=True,
                frame=frame,
                flatten=flatten,
            )
        finally:
            if usd_rop is not None:
                usd_rop.destroy()
    except Exception as exc:
        return skill_exception(exc, message="Failed to create snapshot")


@skill_entry
def main(**kwargs) -> dict:
    return create_snapshot(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
