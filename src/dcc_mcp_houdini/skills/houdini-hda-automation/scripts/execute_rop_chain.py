"""Execute a ROP render with dependencies (full output-driver chain)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _hda_auto_common import get_node, node_summary  # noqa: E402


def execute_rop_chain(
    rop_path: str,
    frame_range: Optional[List[float]] = None,
    ignore_inputs: bool = False,
) -> dict:
    """Render the ROP at *rop_path*, honouring upstream ROP dependencies.

    Set ``ignore_inputs`` to render only this ROP without its input chain.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        node = get_node(hou, rop_path)
        render_fn = getattr(node, "render", None)
        if not callable(render_fn):
            return skill_error(
                "Not a renderable ROP",
                "Node has no render(); expected an output driver",
                node=node_summary(node),
            )

        kwargs: dict = {"verbose": False, "ignore_inputs": bool(ignore_inputs)}
        if frame_range is not None and len(frame_range) >= 2:
            start = float(frame_range[0])
            end = float(frame_range[1])
            step = float(frame_range[2]) if len(frame_range) >= 3 else 1.0
            kwargs["frame_range"] = (start, end, step)

        try:
            render_fn(**kwargs)
        except TypeError:
            # Older signatures may not accept all kwargs.
            render_fn()

        errors = list(node.errors()) if hasattr(node, "errors") else []
        return skill_success(
            "Executed ROP chain" if not errors else "ROP chain executed with errors",
            node=node_summary(node),
            frame_range=frame_range,
            ignored_inputs=bool(ignore_inputs),
            errors=errors,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to execute ROP chain")


@skill_entry
def main(**kwargs) -> dict:
    return execute_rop_chain(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
