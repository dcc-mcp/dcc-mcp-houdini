"""Create an orient constraint — constrain only rotation channels."""

from __future__ import annotations

from _constraint_common import get_node  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def create_orient_constraint(
    driven_path: str,
    target_path: str,
    maintain_offset: bool = True,
    constraint_name: str = "orient_constraint1",
) -> dict:
    """Constrain only rotation channels of *driven_path* to *target_path*.

    Creates a CHOP network that extracts *target_path*'s world-space rotation
    and drives *driven_path*'s ``rx``, ``ry``, ``rz`` parameters via channel
    referencing.  Translation and scale remain free.

    Args:
        driven_path: Path to the object whose rotation is constrained.
        target_path: Path to the target object.
        maintain_offset: Preserve the current rotational offset.
        constraint_name: Name for the constraint CHOP network.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        driven_node = get_node(hou, driven_path)
        target_node = get_node(hou, target_path)

        # Use object CHOP to extract world rotation from the target.
        obj_context = hou.node("/ch")
        if obj_context is None:
            obj_context = hou.node("/obj").createNode("chopnet", node_name=constraint_name)

        object_chop = obj_context.createNode("object", node_name="obj_rot_{}".format(target_node.name()))
        object_chop.parm("target").set(target_path)

        # Drive rotation channels via channel reference expressions.
        offset_rx = offset_ry = offset_rz = 0.0
        if maintain_offset:
            try:
                dr = driven_node.worldTransform().extractRotates()
                tr = target_node.worldTransform().extractRotates()
                offset_rx = dr[0] - tr[0]
                offset_ry = dr[1] - tr[1]
                offset_rz = dr[2] - tr[2]
            except Exception:  # noqa: BLE001
                pass

        for axis, offset in [("rx", offset_rx), ("ry", offset_ry), ("rz", offset_rz)]:
            parm = driven_node.parm(axis)
            if parm is not None:
                try:
                    chop_path = "{}/{}".format(object_chop.path(), axis.upper())
                    if abs(offset) > 1e-9:
                        expr = 'chop("{}") + {}'.format(chop_path, offset)
                    else:
                        expr = 'chop("{}")'.format(chop_path)
                    parm.setExpression(expr, language=hou.exprLanguage.Hscript)
                except Exception:  # noqa: BLE001
                    pass

        object_chop.moveToGoodPosition()

        return skill_success(
            "Created orient constraint",
            constraint_chop=object_chop.path(),
            driven_path=driven_path,
            target_path=target_path,
            maintain_offset=maintain_offset,
            offset={"rx": offset_rx, "ry": offset_ry, "rz": offset_rz},
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to create orient constraint")


@skill_entry
def main(**kwargs) -> dict:
    return create_orient_constraint(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
