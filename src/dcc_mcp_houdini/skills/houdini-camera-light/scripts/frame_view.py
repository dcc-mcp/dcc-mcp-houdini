"""Frame the Scene Viewer on a node and/or look through a camera."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _camlight_common import get_node  # noqa: E402


def _scene_viewer(hou):
    try:
        return hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
    except Exception:  # noqa: BLE001
        return None


def frame_view(
    node_path: Optional[str] = None,
    camera_path: Optional[str] = None,
) -> dict:
    """Look through *camera_path* (optional) and frame *node_path* (optional)."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        warnings: List[str] = []
        if not hou.isUIAvailable():
            return skill_success(
                "Viewport not available (headless)",
                framed=False,
                warnings=["UI is not available; cannot frame a viewport"],
            )
        viewer = _scene_viewer(hou)
        if viewer is None:
            return skill_success(
                "No Scene Viewer pane",
                framed=False,
                warnings=["No Scene Viewer pane is open"],
            )
        viewport = viewer.curViewport()
        framed = False
        if node_path:
            node = get_node(hou, node_path)
            try:
                node.setSelected(True, clear_all_selected=True)
                viewport.frameSelected()
                framed = True
            except Exception as frame_exc:  # noqa: BLE001
                warnings.append("Could not frame node: {}".format(frame_exc))
        elif not camera_path:
            try:
                viewport.frameAll()
                framed = True
            except Exception as frame_exc:  # noqa: BLE001
                warnings.append("Could not frame view: {}".format(frame_exc))

        # Apply the camera last. Framing operations change the viewport view and
        # can disconnect a camera that was selected first.
        active_camera = None
        if camera_path:
            cam = get_node(hou, camera_path)
            try:
                viewport.setCamera(cam)
                active = viewport.camera()
                active_camera = active.path() if active is not None else None
                framed = framed or active_camera == camera_path
                if active_camera != camera_path:
                    warnings.append("Viewport did not activate camera: {}".format(camera_path))
                try:
                    viewport.draw()
                except Exception:  # noqa: BLE001
                    pass
            except Exception as cam_exc:  # noqa: BLE001
                warnings.append("Could not set camera: {}".format(cam_exc))
        return skill_success(
            "Framed view",
            framed=framed,
            camera_path=camera_path,
            active_camera=active_camera,
            node_path=node_path,
            warnings=warnings,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to frame view")


@skill_entry
def main(**kwargs) -> dict:
    return frame_view(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
