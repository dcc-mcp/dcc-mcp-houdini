"""Get basic information about the current Houdini hip file."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def get_scene_info() -> dict:
    """Return hip file path, frame range, and object count."""
    try:
        import hou  # noqa: PLC0415

        obj = hou.node("/obj")
        node_count = len(obj.children()) if obj is not None else 0
        playback = hou.playbar
        return skill_success(
            "Retrieved Houdini scene information",
            hip_file=hou.hipFile.name() if not hou.hipFile.isNewFile() else None,
            hip_has_file=not hou.hipFile.isNewFile(),
            frame=hou.frame(),
            start_frame=playback.playbackRange()[0],
            end_frame=playback.playbackRange()[1],
            obj_node_count=node_count,
        )
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to get scene info")


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`get_scene_info`."""
    return get_scene_info(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
