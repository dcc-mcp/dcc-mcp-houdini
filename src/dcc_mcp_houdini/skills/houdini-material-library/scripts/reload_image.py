"""Reload one or more image texture nodes from disk."""

from __future__ import annotations

from typing import Any, List, Optional

from _library_common import (  # noqa: E402
    find_image_filepath,
    get_node,
    hou_import_error,
    is_image_node,
    iter_nodes_recursive,
)
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def _reload_node(node: Any) -> dict:
    """Attempt to reload a single image node and return result info."""
    info = {"path": node.path(), "name": node.name(), "reloaded": False}
    filepath = find_image_filepath(node)
    if filepath:
        info["file_path"] = filepath

    # Houdini image nodes typically reload by re-setting the file parameter
    # or via node.cook(force=True).
    try:
        # Method 1: Try the parm.pressButton for reload.
        reload_parm = node.parm("reload")
        if reload_parm is not None:
            reload_parm.pressButton()
            info["reloaded"] = True
            info["method"] = "reload_button"
            return info
    except Exception:  # noqa: BLE001
        pass

    try:
        # Method 2: Re-set the filename parameter.
        if filepath:
            for file_parm_name in ("filename", "file", "texturefile"):
                fp = node.parm(file_parm_name)
                if fp is not None:
                    fp.set(filepath)
                    info["reloaded"] = True
                    info["method"] = "reset_filename"
                    return info
    except Exception:  # noqa: BLE001
        pass

    try:
        # Method 3: Force re-cook.
        node.cook(force=True)
        info["reloaded"] = True
        info["method"] = "force_cook"
    except Exception:  # noqa: BLE001
        pass

    return info


def reload_image(
    node_path: Optional[str] = None,
    parent_path: str = "/mat",
    reload_all: bool = False,
) -> dict:
    """Reload image texture nodes from disk.

    Args:
        node_path: Path to a single image node to reload.
        parent_path: Material network to scan (when node_path is None).
        reload_all: Reload every image node under parent_path.

    Returns:
        ToolResult dict.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return hou_import_error()

    try:
        results: List[dict] = []

        if node_path:
            node = get_node(hou, node_path)
            if not is_image_node(node):
                return skill_error(
                    "Not an image node: {}".format(node_path),
                    "Use list_images to find image nodes.",
                )
            results.append(_reload_node(node))
        elif reload_all:
            parent = get_node(hou, parent_path)
            for node in iter_nodes_recursive(parent):
                if is_image_node(node):
                    results.append(_reload_node(node))
        else:
            return skill_error(
                "Specify node_path or set reload_all=True",
                "Use list_images to find available image nodes.",
            )

        reloaded = [r for r in results if r.get("reloaded")]
        failed = [r for r in results if not r.get("reloaded")]

        return skill_success(
            "Reloaded image nodes",
            total=len(results),
            reloaded_count=len(reloaded),
            failed_count=len(failed),
            reloaded=reloaded,
            failed=failed if failed else None,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to reload images")


@skill_entry
def main(**kwargs) -> dict:
    return reload_image(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
