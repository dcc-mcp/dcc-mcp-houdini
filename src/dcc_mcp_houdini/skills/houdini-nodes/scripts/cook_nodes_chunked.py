"""Cook several bounded nodes one per Houdini event-loop tick."""

from __future__ import annotations

from dcc_mcp_core import ChunkedRunner, current_cancel_token
from dcc_mcp_core.skill import skill_entry


def _steps(node_paths, force):
    import hou

    for node_path in node_paths:

        def _cook(path=node_path):
            node = hou.node(path)
            if node is None:
                raise ValueError("Houdini node does not exist: {}".format(path))
            node.cook(force=force)
            return "Cooked {}".format(path)

        yield _cook


@skill_entry
def main(node_paths: list, force: bool = False):
    if not node_paths:
        raise ValueError("node_paths must contain at least one node path")
    return ChunkedRunner(
        _steps(list(node_paths), force),
        total=len(node_paths),
        cancel_token=current_cancel_token(),
    )
