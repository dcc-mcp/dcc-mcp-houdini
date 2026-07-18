"""Create a parent constraint — drive one object's full transform from another."""

from __future__ import annotations

from _constraint_common import build_blend_node  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def create_parent_constraint(
    driven_path: str,
    target_path: str,
    maintain_offset: bool = True,
) -> dict:
    """Make *driven_path* follow *target_path* transform (parent constraint).

    Creates a ``blend`` OBJ node with *target_path* as the single input and
    expression-links the driven object's transform parameters to the blend
    output. When *maintain_offset* is ``True`` (default), the existing world-
    space offset between the two objects is preserved.

    Args:
        driven_path: Path to the object being constrained (e.g. ``/obj/geo2``).
        target_path: Path to the target/parent object (e.g. ``/obj/geo1``).
        maintain_offset: Retain the current offset between objects.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        blend_node = build_blend_node(
            hou,
            driven_path=driven_path,
            target_paths=[target_path],
        )

        offset_info = None
        if maintain_offset:
            try:
                driven = hou.node(driven_path)
                target = hou.node(target_path)
                if driven and target:
                    dt = driven.worldTransform()
                    tt = target.worldTransform()
                    offset_m = tt.inverted() * dt
                    offset_info = {
                        "tx": offset_m.extractTranslates()[0],
                        "ty": offset_m.extractTranslates()[1],
                        "tz": offset_m.extractTranslates()[2],
                    }
            except Exception:  # noqa: BLE001
                pass

        return skill_success(
            "Created parent constraint",
            blend_node_path=blend_node.path(),
            driven_path=driven_path,
            target_path=target_path,
            maintain_offset=maintain_offset,
            offset=offset_info,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to create parent constraint")


@skill_entry
def main(**kwargs) -> dict:
    return create_parent_constraint(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
