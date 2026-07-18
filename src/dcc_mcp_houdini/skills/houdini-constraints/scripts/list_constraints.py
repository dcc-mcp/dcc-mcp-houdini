"""List constraint nodes and relationships in the scene."""

from __future__ import annotations

from typing import Optional

from _constraint_common import find_blend_constraints  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def list_constraints(
    context_path: str = "/obj",
    constraint_type: Optional[str] = None,
) -> dict:
    """List constraint relationships under *context_path*.

    Scans for ``blend`` OBJ nodes acting as constraints (connected inputs) and
    for CHOP-based constraints (object CHOPs in ``/ch`` with target-driven
    channels).

    Args:
        context_path: OBJ context to scan (e.g. ``/obj``).
        constraint_type: Optional filter: ``blend``, ``chop``, or ``all``.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        all_constraints = []
        filter_type = (constraint_type or "all").lower()

        # 1. Blend-based constraints (OBJ level).
        if filter_type in ("all", "blend"):
            blends = find_blend_constraints(hou, context_path)
            for b in blends:
                b["type"] = "blend"
            all_constraints.extend(blends)

        # 2. CHOP-based constraints.
        if filter_type in ("all", "chop"):
            chop_context = hou.node("/ch")
            if chop_context is not None:
                for child in chop_context.children():
                    if child.type().name() == "object":
                        target = None
                        try:
                            target = child.parm("target").eval()
                        except Exception:  # noqa: BLE001
                            pass
                        if target:
                            all_constraints.append(
                                {
                                    "path": child.path(),
                                    "name": child.name(),
                                    "type": "chop",
                                    "target": target,
                                }
                            )

        # 3. Enrich with driven-object detection.
        for c in all_constraints:
            c.setdefault("targets", [])
            if not c.get("targets"):
                c["targets"] = [c.get("target")] if c.get("target") else []

        return skill_success(
            "Listed constraints",
            context_path=context_path,
            constraint_type=filter_type,
            count=len(all_constraints),
            constraints=all_constraints,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to list constraints")


@skill_entry
def main(**kwargs) -> dict:
    return list_constraints(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
