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

from _kinefx_common import guarded_cook_failures
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def _set_if_present(node: Any, name: str, value: Any) -> None:
    parm = node.parm(name)
    if parm is not None:
        parm.set(value)


def _connect(node: Any, input_index: int, source: Any, label: str, failures: list) -> bool:
    """Wire a single DOP input, recording (never swallowing) any failure."""
    try:
        node.setInput(input_index, source)
    except Exception as exc:  # noqa: BLE001 - surface every wiring failure
        failures.append(
            {
                "path": node.path(),
                "input": input_index,
                "source": source.path(),
                "label": label,
                "error": str(exc),
            }
        )
        return False
    return True


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

        # N3: validate the DOP network path and its parent BEFORE creating any
        # SOP nodes, so a bad path / missing parent cannot leave orphans. A path
        # without "/" used to make str.rsplit raise ValueError directly.
        if not isinstance(dopnet_path, str) or "/" not in dopnet_path:
            return skill_error(
                "Invalid DOP network path",
                "dopnet_path must be an absolute path containing '/', e.g. /obj/ragdoll_dopnet",
                dopnet_path=dopnet_path,
            )
        dop_parent_path, dop_name = dopnet_path.rsplit("/", 1)
        if not dop_name:
            return skill_error(
                "Invalid DOP network path",
                "dopnet_path must end with a network name",
                dopnet_path=dopnet_path,
            )
        dop_parent = hou.node(dop_parent_path or "/obj")
        if dop_parent is None:
            return skill_error("DOP parent not found", "dop_parent_not_found", dop_parent_path=dop_parent_path)

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

        # DOP-level RBD network (parent/name already validated above).
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
        # Wire the solver inputs. Failures are recorded, not swallowed: a
        # disconnected RBD network must never be reported as validated.
        wiring = [
            (merge, 0, solver, "solver"),
            (merge, 1, rbd, "rbd_object"),
            (merge, 2, constraint_net, "constraint_network"),
            (merge, 3, gravity, "gravity"),
            (output, 0, merge, "output"),
        ]
        if ground is not None:
            wiring.append((merge, 4, ground, "ground"))
        wiring_failures = []
        for target, input_index, source, label in wiring:
            _connect(target, input_index, source, label, wiring_failures)
        if wiring_failures:
            return skill_error(
                "Ragdoll DOP wiring failed",
                "ragdoll_wiring_failed",
                wiring_failures=wiring_failures,
                created_sop_nodes=[node.path() for node in created_sop],
                created_dop_nodes=[node.path() for node in created_dop],
            )

        # Cook the top-level networks, NOT individual DOP data nodes. DOP data
        # nodes (constraintnetwork / merge in particular) are not standalone-
        # cookable and raise hou.OperationFailed on 20.5/21/22 when force-cooked
        # in isolation, even though the dopnet cooks cleanly (QA blocking 2).
        # Cooking the dopnet recursively validates the whole DOP network, and
        # the collider output validates the SOP proxy chain. Verified on
        # licensed Houdini 22.0.368 / 20.5.550.
        cook_targets = [null_out, dopnet]
        # Cook validation is best-effort: any raised hou.OperationFailed is
        # recorded as a cook_failure (validated=False), never an uncaught
        # exception that turns the whole tool into success=False.
        failures = guarded_cook_failures(cook_targets)
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
            wiring_failures=wiring_failures,
            cook_failures=failures,
            validated=not failures and not wiring_failures,
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
