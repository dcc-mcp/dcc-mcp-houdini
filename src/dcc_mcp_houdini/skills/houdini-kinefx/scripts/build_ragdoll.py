"""Build a physics ragdoll setup from a biped skeleton (workflow stage 7).

Creates a DOP RBD network: proxy collision volumes per joint (from the biped
skeleton), a cone-twist/point constraint network connecting adjacent joints,
an RBD solver and ground collision. This is a *setup* tool in the spirit of the
``houdini-simulation`` skill: it creates and validates the network; the caller
supplies cook/output wiring for a full simulation. Node parameters are guarded
(``_set_if_present``) so the tool degrades gracefully across Houdini builds.
"""

from __future__ import annotations

from typing import Any

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def _set_if_present(node: Any, name: str, value: Any) -> None:
    parm = node.parm(name)
    if parm is not None:
        parm.set(value)


def build_ragdoll(
    geo_path: str,
    skeleton: str,
    dopnet_path: str = "/obj/ragdoll_dopnet",
    node_prefix: str = "dcc_mcp_ragdoll",
    constraint_type: str = "conetwist",
    add_ground: bool = True,
) -> dict:
    """Build a DOP RBD ragdoll network for *skeleton*.

    Args:
        geo_path: Geometry SOP container holding the biped skeleton.
        skeleton: Path to the biped skeleton SOP (proxy source points).
        dopnet_path: DOP network path to create (parent must exist).
        node_prefix: Prefix for created DOP nodes.
        constraint_type: ``conetwist`` | ``point`` | ``glue``.
        add_ground: Add a static ground collision plane.
    """
    if constraint_type not in ("conetwist", "point", "glue"):
        return skill_error(
            "Unknown constraint_type",
            "constraint_type must be conetwist, point or glue",
            constraint_type=constraint_type,
        )
    if not isinstance(geo_path, str) or not geo_path.strip():
        return skill_error("Invalid geo_path", "geo_path must be a non-empty string")

    try:
        import hou  # Lazy import: requires Houdini's embedded Python.
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        geo = hou.node(geo_path)
        skel = hou.node(skeleton)
        if geo is None or skel is None:
            return skill_error(
                "Node not found",
                "geo_path or skeleton path is invalid",
                geo_path=geo_path,
                skeleton=skeleton,
            )

        # SOP-level proxy volumes: copy a proxy sphere onto each joint point.
        proxy = geo.createNode("sphere", node_name="{}_proxy".format(node_prefix))
        _set_if_present(proxy, "rad", (0.12, 0.12, 0.12))
        _set_if_present(proxy, "scale", 1.0)
        copy = geo.createNode("copytopoints", node_name="{}_colliders".format(node_prefix))
        copy.setInput(0, proxy)
        copy.setInput(1, skel)
        assemble = geo.createNode("assemble", node_name="{}_pack".format(node_prefix))
        assemble.setInput(0, copy)
        _set_if_present(assemble, "create_packed", 1)
        null_out = geo.createNode("null", node_name="{}_colliders_OUT".format(node_prefix))
        null_out.setInput(0, assemble)
        created_sop = [proxy, copy, assemble, null_out]

        # DOP-level RBD network.
        dop_parent_path, dop_name = dopnet_path.rsplit("/", 1)
        dop_parent = hou.node(dop_parent_path or "/obj")
        if dop_parent is None:
            return skill_error("DOP parent not found", dop_parent_path=dop_parent_path)
        existing = hou.node(dopnet_path)
        dopnet = existing if existing is not None else dop_parent.createNode("dopnet", node_name=dop_name)

        def dop(type_name, name):
            return dopnet.createNode(type_name, node_name="{}_{}".format(node_prefix, name))

        solver = dop("rigidbodysolver", "solver")
        rbd = dop("rbdpackedobject", "rbd")
        _set_if_present(rbd, "soppath", null_out.path())
        constraint_rel = dop(
            "conetwistconrel"
            if constraint_type == "conetwist"
            else "pointconrel"
            if constraint_type == "point"
            else "glueconrel",
            "constraint",
        )
        constraint_net = dop("constraintnetwork", "constraintnetwork")
        _set_if_present(constraint_net, "soppath", null_out.path())
        merge = dop("merge", "merge")
        gravity = dop("gravity", "gravity")
        output = dop("output", "output")

        created_dop = [solver, rbd, constraint_rel, constraint_net, merge, gravity, output]
        ground = None
        if add_ground:
            ground = dop("staticobject", "ground")
            _set_if_present(ground, "batch", 1)
            created_dop.append(ground)
        # Wire the solver inputs; guarded to avoid failures on atypical layouts.
        try:
            merge.setInput(0, solver)
            merge.setInput(1, rbd)
            merge.setInput(2, constraint_net)
            merge.setInput(3, gravity)
            if ground is not None:
                merge.setInput(4, ground)
            output.setInput(0, merge)
        except Exception:  # noqa: BLE001 - wiring is best-effort across builds
            pass

        all_nodes = created_sop + created_dop
        failures = []
        for node in all_nodes:
            node.cook(force=True)
            errors = list(node.errors())
            warnings = list(node.warnings())
            if errors or warnings:
                failures.append({"path": node.path(), "errors": errors, "warnings": warnings})
        try:
            geo.layoutChildren()
            dopnet.layoutChildren()
        except Exception:  # noqa: BLE001
            pass

        return skill_success(
            "Built ragdoll RBD setup",
            geo_path=geo.path(),
            skeleton=skel.path(),
            dopnet=dopnet.path(),
            collider_node=null_out.path(),
            solver=solver.path(),
            rbd_object=rbd.path(),
            constraint_relationship=constraint_rel.path(),
            constraint_type=constraint_type,
            ground_requested=add_ground,
            ground_node=ground.path() if ground is not None else None,
            created_sop_nodes=[node.path() for node in created_sop],
            created_dop_nodes=[node.path() for node in created_dop],
            cook_failures=failures,
            validated=not failures,
            next_tools=["houdini_simulation__validate_simulation_setup"],
            note=(
                "Setup network only; supply proxy tuning and an explicit cook/output "
                "to produce a simulated ragdoll, verified by QA on licensed Houdini."
            ),
        )
    except Exception as exc:  # noqa: BLE001
        return skill_exception(exc, message="Failed to build ragdoll")


@skill_entry
def main(**kwargs) -> dict:
    return build_ragdoll(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
