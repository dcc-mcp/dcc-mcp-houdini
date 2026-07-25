"""Semantic inspection of a Houdini node network.

Read-only analysis of the children under a parent network:
broken inputs, orphaned nodes, cycles, disconnected subgraphs,
type-mismatched connections, chain roots and ends.
"""

from __future__ import annotations

from dataclasses import asdict

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def _inspection_to_dict(inspection) -> dict:
    """Convert a NetworkInspection dataclass into a JSON-safe dict."""
    return {
        "parent_path": inspection.parent_path,
        "node_count": inspection.node_count,
        "connection_count": inspection.connection_count,
        "broken_inputs": [asdict(b) for b in inspection.broken_inputs],
        "orphaned_nodes": inspection.orphaned_nodes,
        "cycles": [asdict(c) for c in inspection.cycles],
        "type_mismatches": inspection.type_mismatches,
        "subgraphs": [asdict(s) for s in inspection.subgraphs],
        "chain_ends": inspection.chain_ends,
        "chain_roots": inspection.chain_roots,
    }


def inspect_network(parent_path: str) -> dict:
    """Run full semantic inspection on a Houdini parent network."""
    try:
        __import__("hou")
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        from dcc_mcp_houdini._node_graph_inspection import inspect_network as _inspect
    except ImportError as exc:
        return skill_error("Inspection module unavailable", str(exc))

    try:
        result = _inspect(parent_path)
    except ValueError as exc:
        return skill_error("Invalid network path", str(exc))
    except RuntimeError as exc:
        return skill_error("Houdini runtime error", str(exc))
    except Exception as exc:
        return skill_exception(exc, message="Failed to inspect Houdini network")

    return skill_success(
        "Inspected Houdini node network",
        **{k: v for k, v in _inspection_to_dict(result).items() if k != "parent_path"},
        parent_path=result.parent_path,
    )


@skill_entry
def main(**kwargs) -> dict:
    return inspect_network(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
