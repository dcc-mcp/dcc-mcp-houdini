"""List camera nodes under a network with key lens/resolution fields."""

from __future__ import annotations

from _camlight_common import eval_parm, get_node  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def list_cameras(parent_path: str = "/obj") -> dict:
    """Return camera nodes (type name containing 'cam') under *parent_path*."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        parent = get_node(hou, parent_path)
        cameras = []
        for child in parent.children():
            type_name = child.type().name()
            if "cam" not in type_name.lower():
                continue
            cameras.append(
                {
                    "path": child.path(),
                    "name": child.name(),
                    "type": type_name,
                    "resolution": [eval_parm(child, "resx"), eval_parm(child, "resy")],
                    "focal": eval_parm(child, "focal"),
                }
            )
        return skill_success(
            "Listed cameras",
            parent_path=parent.path(),
            count=len(cameras),
            cameras=cameras,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to list cameras")


@skill_entry
def main(**kwargs) -> dict:
    return list_cameras(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
