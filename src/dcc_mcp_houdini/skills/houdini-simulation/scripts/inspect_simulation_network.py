"""Inspect a DOP network and its solver children."""

from __future__ import annotations

from _simulation_common import children_summary
from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success

from dcc_mcp_houdini._domain_graph import base_node_type, get_node, hou_missing_error, node_summary, require_category


def inspect_simulation_network(network_path: str) -> dict:
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return hou_missing_error()
    try:
        network = require_category(get_node(hou, network_path), "Dop", children=True)
        children = children_summary(network)
        solvers = [child for child in children if base_node_type(child["type"]).lower().endswith("solver")]
        timeline = None
        try:
            timeline = list(hou.playbar.frameRange())
        except Exception:  # noqa: BLE001
            pass
        return skill_success(
            "Inspected simulation network",
            network=node_summary(network),
            network_path=network.path(),
            children=children,
            solver_count=len(solvers),
            solvers=solvers,
            timeline=timeline,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to inspect simulation network")


@skill_entry
def main(**kwargs) -> dict:
    return inspect_simulation_network(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
