"""Capture the current Scene Viewer to an image file (flipbook, single frame)."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from _render_common import clamp_resolution, scene_viewer  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def _rgb_statistics(data: bytes, width: int, height: int, bytes_per_line: int) -> Dict[str, Any]:
    """Return exact RGB extrema for a packed RGB888 image buffer."""
    row_bytes = width * 3
    required_bytes = bytes_per_line * height
    if width < 1 or height < 1 or bytes_per_line < row_bytes or len(data) < required_bytes:
        raise ValueError("Invalid RGB888 image buffer")

    rgb_min = [255, 255, 255]
    rgb_max = [0, 0, 0]
    for row_index in range(height):
        offset = row_index * bytes_per_line
        row = data[offset : offset + row_bytes]
        for channel in range(3):
            values = row[channel::3]
            rgb_min[channel] = min(rgb_min[channel], min(values))
            rgb_max[channel] = max(rgb_max[channel], max(values))

    return {
        "rgb_min": rgb_min,
        "rgb_max": rgb_max,
        "single_color": rgb_min == rgb_max,
        "all_black": rgb_max == [0, 0, 0],
    }


def _inspect_capture(output_path: str) -> Dict[str, Any]:
    """Decode *output_path* with Houdini's Qt runtime and inspect every pixel."""
    try:
        from PySide6.QtGui import QImage  # type: ignore[import-not-found]  # noqa: PLC0415
    except ImportError:
        try:
            from PySide2.QtGui import QImage  # type: ignore[import-not-found]  # noqa: PLC0415
        except ImportError as exc:
            raise RuntimeError("Houdini Qt image decoder is unavailable") from exc

    image = QImage(output_path)
    if image.isNull():
        raise ValueError("Captured file is not a decodable image")
    rgb888 = getattr(QImage, "Format_RGB888", None)
    if rgb888 is None:
        rgb888 = QImage.Format.Format_RGB888
    image = image.convertToFormat(rgb888)
    byte_count = image.sizeInBytes() if hasattr(image, "sizeInBytes") else image.byteCount()
    pointer = image.constBits()
    if hasattr(pointer, "setsize"):
        pointer.setsize(byte_count)
    data = bytes(pointer)
    width = int(image.width())
    height = int(image.height())
    statistics = _rgb_statistics(data, width, height, int(image.bytesPerLine()))
    return {"dimensions": [width, height], **statistics}


def _node_path(node: Any) -> Optional[str]:
    try:
        path = node.path()
    except Exception:  # noqa: BLE001
        return None
    return path if isinstance(path, str) else None


def _viewer_context(viewer: Any, viewport: Any) -> Dict[str, Optional[str]]:
    """Collect bounded, JSON-safe Scene Viewer diagnostics."""
    try:
        viewer_type = viewer.type().name()
    except Exception:  # noqa: BLE001
        viewer_type = None
    if not isinstance(viewer_type, str):
        viewer_type = None
    try:
        pwd = viewer.pwd()
    except Exception:  # noqa: BLE001
        pwd = None
    try:
        display_node = pwd.displayNode() if pwd is not None else None
    except Exception:  # noqa: BLE001
        display_node = None
    try:
        camera = viewport.camera()
    except Exception:  # noqa: BLE001
        camera = None
    return {
        "type": viewer_type,
        "pwd": _node_path(pwd),
        "camera": _node_path(camera),
        "display_node": _node_path(display_node),
    }


def capture_viewport(
    output_path: str,
    resolution: Optional[List[int]] = None,
    frame: Optional[float] = None,
) -> dict:
    """Flipbook the current viewport to *output_path* for a single frame.

    UI-aware: a headless ``hython`` session returns ``captured: false`` with a
    structured warning rather than failing.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        clamped = clamp_resolution(resolution)
        if not hou.isUIAvailable():
            return skill_success(
                "Viewport capture unavailable (headless)",
                captured=False,
                output_path=output_path,
                written_files=[],
                skipped=[output_path],
                warnings=["UI is not available; cannot capture a viewport"],
            )
        viewer = scene_viewer(hou)
        if viewer is None:
            return skill_success(
                "No Scene Viewer pane",
                captured=False,
                output_path=output_path,
                written_files=[],
                skipped=[output_path],
                warnings=["No Scene Viewer pane is open"],
            )
        target_frame = float(frame) if frame is not None else float(hou.frame())
        parent = os.path.dirname(os.path.abspath(output_path))
        if parent and not os.path.isdir(parent):
            os.makedirs(parent, exist_ok=True)
        warnings: List[str] = []
        settings = viewer.flipbookSettings().stash()
        settings.frameRange((target_frame, target_frame))
        settings.output(output_path)
        try:
            settings.outputToMPlay(False)
        except Exception:  # noqa: BLE001
            pass
        if clamped is not None:
            try:
                settings.useResolution(True)
                settings.resolution(tuple(clamped))
            except Exception as res_exc:  # noqa: BLE001
                warnings.append("Could not set resolution: {}".format(res_exc))
        viewport = viewer.curViewport()
        viewer_context = _viewer_context(viewer, viewport)
        viewer.flipbook(viewport, settings)
        written = [output_path] if os.path.isfile(output_path) else []
        skipped = [] if written else [output_path]
        if not written:
            return skill_error(
                "Viewport capture did not write an image",
                "CAPTURE_NOT_WRITTEN",
                prompt="Confirm the output directory is writable and retry the viewport capture.",
                code="CAPTURE_NOT_WRITTEN",
                captured=False,
                output_path=output_path,
                frame=target_frame,
                resolution=clamped,
                written_files=written,
                skipped=skipped,
                warnings=warnings,
                viewer=viewer_context,
            )
        try:
            validation = _inspect_capture(output_path)
        except Exception as validation_exc:  # noqa: BLE001
            return skill_error(
                "Viewport capture could not be verified",
                "CAPTURE_VALIDATION_FAILED",
                prompt="Use a Qt-decodable image format such as PNG or JPEG, then retry the capture.",
                code="CAPTURE_VALIDATION_FAILED",
                captured=False,
                output_path=output_path,
                frame=target_frame,
                resolution=clamped,
                written_files=written,
                skipped=skipped,
                warnings=warnings,
                viewer=viewer_context,
                validation_error="{}: {}".format(type(validation_exc).__name__, validation_exc),
            )
        if clamped is not None and validation["dimensions"] != clamped:
            return skill_error(
                "Viewport capture has unexpected dimensions",
                "CAPTURE_DIMENSION_MISMATCH",
                prompt="Redraw the Scene Viewer and retry with the requested resolution.",
                code="CAPTURE_DIMENSION_MISMATCH",
                captured=False,
                output_path=output_path,
                frame=target_frame,
                resolution=clamped,
                expected_dimensions=clamped,
                written_files=written,
                skipped=skipped,
                warnings=warnings,
                viewer=viewer_context,
                validation=validation,
            )
        if validation["single_color"]:
            return skill_error(
                "Viewport capture contains no usable visual information",
                "EMPTY_VIEWPORT_CAPTURE",
                prompt="Redraw and frame the active Scene Viewer, confirm its display node and camera, then retry.",
                possible_solutions=[
                    "Set the Scene Viewer pwd to the geometry network and frame the displayed geometry.",
                    "Confirm the intended display node and camera are active before capturing.",
                ],
                code="EMPTY_VIEWPORT_CAPTURE",
                captured=False,
                output_path=output_path,
                frame=target_frame,
                resolution=clamped,
                written_files=written,
                skipped=skipped,
                warnings=warnings,
                viewer=viewer_context,
                validation=validation,
            )
        return skill_success(
            "Captured viewport",
            captured=bool(written),
            output_path=output_path,
            frame=target_frame,
            resolution=clamped,
            written_files=written,
            skipped=skipped,
            warnings=warnings,
            viewer=viewer_context,
            validation=validation,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to capture viewport")


@skill_entry
def main(**kwargs) -> dict:
    return capture_viewport(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
