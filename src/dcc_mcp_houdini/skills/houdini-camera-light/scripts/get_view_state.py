"""Report the active Scene Viewer's camera and viewport state."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def _scene_viewer(hou):
    try:
        return hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
    except Exception:  # noqa: BLE001
        return None


def get_view_state() -> dict:
    """Return active camera path and viewport name (read-only, UI-aware)."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        if not hou.isUIAvailable():
            return skill_success(
                "Viewport not available (headless)",
                ui_available=False,
                active_camera=None,
                viewport_name=None,
            )
        viewer = _scene_viewer(hou)
        if viewer is None:
            return skill_success(
                "No Scene Viewer pane",
                ui_available=True,
                active_camera=None,
                viewport_name=None,
            )
        viewport = viewer.curViewport()
        camera = None
        try:
            cam_node = viewport.camera()
            if cam_node is not None:
                camera = cam_node.path()
        except Exception:  # noqa: BLE001
            camera = None
        viewport_name = None
        try:
            viewport_name = viewport.name()
        except Exception:  # noqa: BLE001
            viewport_name = None
        return skill_success(
            "Read view state",
            ui_available=True,
            active_camera=camera,
            viewport_name=viewport_name,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to read view state")


@skill_entry
def main(**kwargs) -> dict:
    return get_view_state(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
