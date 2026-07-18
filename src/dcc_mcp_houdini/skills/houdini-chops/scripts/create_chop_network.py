"""Create a CHOP network container at a given path."""

from __future__ import annotations

from _chops_common import ensure_chop_network  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def create_chop_network(
    parent_path: str,
    network_name: str = "chopnet1",
) -> dict:
    """Create a CHOP network container under *parent_path*.

    Args:
        parent_path: Path to the parent node or context (e.g. ``/ch``).
        network_name: Name for the new CHOP network node.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        network = ensure_chop_network(hou, parent_path, network_name)
        # Move to default network editor pane for visibility.
        try:
            network.setCurrent(True, clear_all_selected=True)
        except Exception:  # noqa: BLE001
            pass
        return skill_success(
            "Created CHOP network",
            network_path=network.path(),
            parent_path=parent_path,
            network_name=network.name(),
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to create CHOP network")


@skill_entry
def main(**kwargs) -> dict:
    return create_chop_network(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
