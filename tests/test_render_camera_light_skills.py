"""Mock-hou unit tests for houdini-camera-light and houdini-render skills."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

_SKILLS_ROOT = Path(__file__).parent.parent / "src" / "dcc_mcp_houdini" / "skills"


def _load_script(skill_name: str, script_name: str) -> ModuleType:
    path = _SKILLS_ROOT / skill_name / "scripts" / script_name
    spec = importlib.util.spec_from_file_location(f"{skill_name}_{path.stem}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _node(path: str, name: str, type_name: str = "geo") -> MagicMock:
    node = MagicMock()
    node.path.return_value = path
    node.name.return_value = name
    node.type.return_value.name.return_value = type_name
    return node


def _scalar_parm(value):
    parm = MagicMock()
    parm.eval.return_value = value
    return parm


class TestCameraSkills:
    def test_list_cameras_filters_and_reads_parms(self) -> None:
        mod = _load_script("houdini-camera-light", "list_cameras.py")
        cam = _node("/obj/cam1", "cam1", "cam")
        cam.parmTuple.return_value = None
        cam.parm.side_effect = lambda n: {
            "resx": _scalar_parm(1920),
            "resy": _scalar_parm(1080),
            "focal": _scalar_parm(50.0),
        }.get(n)
        geo = _node("/obj/geo1", "geo1", "geo")
        parent = _node("/obj", "obj")
        parent.children.return_value = [cam, geo]
        mock_hou = MagicMock()
        mock_hou.node.return_value = parent

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.list_cameras("/obj")

        assert result["success"] is True
        assert result["context"]["count"] == 1
        assert result["context"]["cameras"][0]["resolution"] == [1920, 1080]
        assert result["context"]["cameras"][0]["focal"] == 50.0

    def test_create_camera_sets_lens(self) -> None:
        mod = _load_script("houdini-camera-light", "create_camera.py")
        cam = _node("/obj/shotcam", "shotcam", "cam")
        cam.parmTuple.return_value = MagicMock()
        resx, resy, focal = MagicMock(), MagicMock(), MagicMock()
        cam.parm.side_effect = lambda n: {"resx": resx, "resy": resy, "focal": focal}.get(n)
        parent = _node("/obj", "obj")
        parent.createNode.return_value = cam
        mock_hou = MagicMock()
        mock_hou.node.return_value = parent

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.create_camera("/obj", name="shotcam", resolution=[1280, 720], focal=35)

        assert result["success"] is True
        parent.createNode.assert_called_once_with("cam", node_name="shotcam")
        resx.set.assert_called_once_with(1280)
        focal.set.assert_called_once_with(35.0)


class TestLightSkills:
    def test_create_light_sets_core_parms(self) -> None:
        mod = _load_script("houdini-camera-light", "create_light.py")
        light = _node("/obj/keylight", "keylight", "hlight::2.0")
        light.parmTuple.return_value = MagicMock()
        type_parm, intensity_parm, exposure_parm = MagicMock(), MagicMock(), MagicMock()
        light.parm.side_effect = lambda n: {
            "light_type": type_parm,
            "light_intensity": intensity_parm,
            "light_exposure": exposure_parm,
        }.get(n)
        parent = _node("/obj", "obj")
        parent.createNode.return_value = light
        mock_hou = MagicMock()
        mock_hou.node.return_value = parent

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.create_light("/obj", light_type="distant", name="keylight", intensity=2.0, exposure=1.5)

        assert result["success"] is True
        type_parm.set.assert_called_once_with(7)
        intensity_parm.set.assert_called_once_with(2.0)
        exposure_parm.set.assert_called_once_with(1.5)

    def test_create_light_rejects_unknown_type(self) -> None:
        mod = _load_script("houdini-camera-light", "create_light.py")
        with patch.dict(sys.modules, {"hou": MagicMock()}):
            result = mod.create_light("/obj", light_type="laser")
        assert result["success"] is False


class TestViewSkills:
    def test_frame_view_headless(self) -> None:
        mod = _load_script("houdini-camera-light", "frame_view.py")
        mock_hou = MagicMock()
        mock_hou.isUIAvailable.return_value = False
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.frame_view(node_path="/obj/geo1")
        assert result["success"] is True
        assert result["context"]["framed"] is False

    def test_get_view_state_headless(self) -> None:
        mod = _load_script("houdini-camera-light", "get_view_state.py")
        mock_hou = MagicMock()
        mock_hou.isUIAvailable.return_value = False
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.get_view_state()
        assert result["success"] is True
        assert result["context"]["ui_available"] is False


class TestViewportCapture:
    def test_capture_viewport_headless_skips(self, tmp_path: Path) -> None:
        mod = _load_script("houdini-render", "capture_viewport.py")
        mock_hou = MagicMock()
        mock_hou.isUIAvailable.return_value = False
        out = str(tmp_path / "frame.jpg")
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.capture_viewport(out)
        assert result["success"] is True
        assert result["context"]["captured"] is False
        assert result["context"]["skipped"] == [out]

    def test_capture_viewport_with_ui_writes_file(self, tmp_path: Path) -> None:
        mod = _load_script("houdini-render", "capture_viewport.py")
        out = tmp_path / "frame.jpg"
        settings = MagicMock()
        viewer = MagicMock()
        viewer.flipbookSettings.return_value.stash.return_value = settings
        viewer.flipbook.side_effect = lambda vp, s: out.write_bytes(b"img")
        mock_hou = MagicMock()
        mock_hou.isUIAvailable.return_value = True
        mock_hou.frame.return_value = 1.0
        mock_hou.ui.paneTabOfType.return_value = viewer

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.capture_viewport(str(out), resolution=[99999, 720])

        assert result["success"] is True
        assert result["context"]["captured"] is True
        assert result["context"]["written_files"] == [str(out)]
        # resolution clamped to MAX_DIMENSION
        assert result["context"]["resolution"] == [4096, 720]


class TestRenderSettings:
    def test_get_render_settings_reads_fields(self) -> None:
        mod = _load_script("houdini-render", "get_render_settings.py")
        rop = _node("/out/mantra1", "mantra1", "ifd")
        rop.parmTuple.return_value = None
        rop.parm.side_effect = lambda n: {
            "camera": _scalar_parm("/obj/cam1"),
            "vm_picture": _scalar_parm("/tmp/beauty.exr"),
            "res_overridex": _scalar_parm(1280),
            "res_overridey": _scalar_parm(720),
        }.get(n)
        mock_hou = MagicMock()
        mock_hou.node.return_value = rop

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.get_render_settings("/out/mantra1")

        assert result["success"] is True
        assert result["context"]["camera"] == "/obj/cam1"
        assert result["context"]["output_path"] == "/tmp/beauty.exr"
        assert result["context"]["resolution"] == [1280, 720]

    def test_set_render_settings_reports_unsupported(self) -> None:
        mod = _load_script("houdini-render", "set_render_settings.py")
        camera_parm = MagicMock()
        rop = _node("/out/mantra1", "mantra1", "ifd")
        rop.parmTuple.return_value = None
        # Only the camera parm exists; output_path parms are all missing.
        rop.parm.side_effect = lambda n: camera_parm if n == "camera" else None
        mock_hou = MagicMock()
        mock_hou.node.return_value = rop

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.set_render_settings("/out/mantra1", camera="/obj/cam1", output_path="/tmp/x.exr")

        assert result["success"] is True
        camera_parm.set.assert_called_once_with("/obj/cam1")
        assert result["context"]["applied"]["camera"] == "/obj/cam1"
        assert "output_path" in result["context"]["unsupported"]


class TestRenderExecution:
    def test_render_rop_reports_written_and_elapsed(self, tmp_path: Path) -> None:
        mod = _load_script("houdini-render", "render_rop.py")
        out = tmp_path / "beauty.exr"
        picture = _scalar_parm(str(out))
        rop = _node("/out/mantra1", "mantra1", "ifd")
        rop.parmTuple.return_value = None
        rop.parm.side_effect = lambda n: picture if n == "picture" else None
        rop.render.side_effect = lambda verbose=False: out.write_bytes(b"exr")
        rop.errors.return_value = []
        mock_hou = MagicMock()
        mock_hou.node.return_value = rop

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.render_rop("/out/mantra1")

        assert result["success"] is True
        assert result["context"]["rendered"] is True
        assert result["context"]["written_files"] == [str(out)]
        assert "elapsed_secs" in result["context"]
