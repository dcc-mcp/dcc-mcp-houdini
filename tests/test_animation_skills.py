"""Mock-hou unit tests for the houdini-animation skill."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

_SKILLS_ROOT = Path(__file__).parent.parent / "src" / "dcc_mcp_houdini" / "skills"


def _load_script(script_name: str) -> ModuleType:
    path = _SKILLS_ROOT / "houdini-animation" / "scripts" / script_name
    spec = importlib.util.spec_from_file_location(f"anim_{path.stem}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _keyframe(frame, value, expression=None):
    kf = MagicMock()
    kf.frame.return_value = frame
    kf.value.return_value = value
    if expression is None:
        kf.expression.side_effect = Exception("no expression")
    else:
        kf.expression.return_value = expression
    return kf


def _hou_with_keyframe_class():
    """Return a mock hou whose Keyframe() records frame/value/expression."""
    mock_hou = MagicMock()

    class _KF:
        def __init__(self):
            self.frame = None
            self.value = None
            self.expression = None
            self.expression_language = None

        def setFrame(self, f):
            self.frame = f

        def setValue(self, v):
            self.value = v

        def setExpression(self, e, lang):
            self.expression = e
            self.expression_language = lang

    mock_hou.Keyframe.side_effect = _KF
    mock_hou.exprLanguage.Hscript = "hscript"
    mock_hou.exprLanguage.Python = "python"
    return mock_hou


class TestTimeline:
    def test_get_timeline(self) -> None:
        mod = _load_script("get_timeline.py")
        mock_hou = MagicMock()
        mock_hou.frame.return_value = 12.0
        mock_hou.time.return_value = 0.5
        mock_hou.fps.return_value = 24.0
        mock_hou.playbar.frameRange.return_value = (1, 100)
        mock_hou.playbar.playbackRange.return_value = (1, 100)
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.get_timeline()
        assert result["success"] is True
        assert result["context"]["current_frame"] == 12.0
        assert result["context"]["frame_range"] == [1.0, 100.0]
        assert result["context"]["fps"] == 24.0

    def test_set_timeline_applies_and_defaults_playback(self) -> None:
        mod = _load_script("set_timeline.py")
        mock_hou = MagicMock()
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.set_timeline(frame_range=[1, 48], fps=24, current_frame=1)
        assert result["success"] is True
        mock_hou.setFps.assert_called_once_with(24.0)
        mock_hou.playbar.setFrameRange.assert_called_once_with(1.0, 48.0)
        mock_hou.playbar.setPlaybackRange.assert_called_once_with(1.0, 48.0)
        mock_hou.setFrame.assert_called_once_with(1.0)


class TestKeyframes:
    def test_set_keyframe_value(self) -> None:
        mod = _load_script("set_keyframe.py")
        parm = MagicMock()
        node = MagicMock()
        node.path.return_value = "/obj/geo1"
        node.parm.return_value = parm
        mock_hou = _hou_with_keyframe_class()
        mock_hou.node.return_value = node
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.set_keyframe("/obj/geo1", "tx", frame=10, value=5.0)
        assert result["success"] is True
        parm.setKeyframe.assert_called_once()
        applied_kf = parm.setKeyframe.call_args[0][0]
        assert applied_kf.frame == 10.0
        assert applied_kf.value == 5.0
        assert applied_kf.expression is None

    def test_set_keyframe_value_uses_requested_interpolation(self) -> None:
        mod = _load_script("set_keyframe.py")
        for interpolation in ("bezier", "linear", "constant"):
            parm = MagicMock()
            node = MagicMock()
            node.path.return_value = "/obj/geo1"
            node.parm.return_value = parm
            mock_hou = _hou_with_keyframe_class()
            mock_hou.node.return_value = node
            with patch.dict(sys.modules, {"hou": mock_hou}):
                result = mod.set_keyframe(
                    "/obj/geo1",
                    "tx",
                    frame=10,
                    value=5.0,
                    interpolation=interpolation,
                )
            assert result["success"] is True
            applied_kf = parm.setKeyframe.call_args[0][0]
            assert applied_kf.expression == "{}()".format(interpolation)
            assert applied_kf.expression_language == "hscript"

    def test_set_keyframe_requires_value_or_expression(self) -> None:
        mod = _load_script("set_keyframe.py")
        mock_hou = _hou_with_keyframe_class()
        mock_hou.node.return_value = MagicMock()
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.set_keyframe("/obj/geo1", "tx", frame=10)
        assert result["success"] is False

    def test_get_keyframes(self) -> None:
        mod = _load_script("get_keyframes.py")
        parm = MagicMock()
        parm.keyframes.return_value = [_keyframe(1, 0.0), _keyframe(48, 10.0)]
        node = MagicMock()
        node.path.return_value = "/obj/geo1"
        node.parm.return_value = parm
        mock_hou = MagicMock()
        mock_hou.node.return_value = node
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.get_keyframes("/obj/geo1", "tx")
        assert result["success"] is True
        assert result["context"]["count"] == 2
        assert result["context"]["keyframes"][1]["value"] == 10.0

    def test_delete_keyframes_all(self) -> None:
        mod = _load_script("delete_keyframes.py")
        parm = MagicMock()
        parm.keyframes.return_value = [_keyframe(1, 0.0), _keyframe(48, 10.0)]
        node = MagicMock()
        node.path.return_value = "/obj/geo1"
        node.parm.return_value = parm
        mock_hou = MagicMock()
        mock_hou.node.return_value = node
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.delete_keyframes("/obj/geo1", "tx")
        assert result["success"] is True
        parm.deleteAllKeyframes.assert_called_once()
        assert result["context"]["deleted"] == 2

    def test_delete_keyframes_in_range(self) -> None:
        mod = _load_script("delete_keyframes.py")
        parm = MagicMock()
        parm.keyframes.return_value = [_keyframe(1, 0.0), _keyframe(48, 10.0)]
        node = MagicMock()
        node.path.return_value = "/obj/geo1"
        node.parm.return_value = parm
        mock_hou = MagicMock()
        mock_hou.node.return_value = node
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.delete_keyframes("/obj/geo1", "tx", frame_range=[40, 50])
        assert result["success"] is True
        parm.deleteKeyframeAtFrame.assert_called_once_with(48)
        assert result["context"]["deleted"] == 1


class TestChannels:
    def test_list_animated_parms(self) -> None:
        mod = _load_script("list_animated_parms.py")
        animated = MagicMock()
        animated.name.return_value = "tx"
        animated.keyframes.return_value = [_keyframe(1, 0.0)]
        animated.isTimeDependent.return_value = True
        static = MagicMock()
        static.name.return_value = "ty"
        static.keyframes.return_value = []
        static.isTimeDependent.return_value = False
        node = MagicMock()
        node.path.return_value = "/obj/geo1"
        node.parms.return_value = [animated, static]
        mock_hou = MagicMock()
        mock_hou.node.return_value = node
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.list_animated_parms("/obj/geo1")
        assert result["success"] is True
        assert result["context"]["count"] == 1
        assert result["context"]["parameters"][0]["name"] == "tx"

    def test_get_channel_info_with_expression(self) -> None:
        mod = _load_script("get_channel_info.py")
        parm = MagicMock()
        parm.expression.return_value = "$F"
        parm.expressionLanguage.return_value.name.return_value = "Hscript"
        parm.keyframes.return_value = [_keyframe(1, 0.0)]
        parm.isTimeDependent.return_value = True
        parm.eval.return_value = 3.0
        node = MagicMock()
        node.path.return_value = "/obj/geo1"
        node.parm.return_value = parm
        mock_hou = MagicMock()
        mock_hou.node.return_value = node
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.get_channel_info("/obj/geo1", "tx")
        assert result["success"] is True
        assert result["context"]["expression"] == "$F"
        assert result["context"]["is_time_dependent"] is True

    def test_export_then_import_channels_roundtrip(self, tmp_path: Path) -> None:
        export_mod = _load_script("export_channels.py")
        out = tmp_path / "tx.json"
        parm = MagicMock()
        parm.keyframes.return_value = [_keyframe(1, 0.0), _keyframe(48, 10.0)]
        node = MagicMock()
        node.path.return_value = "/obj/geo1"
        node.parm.return_value = parm
        mock_hou = MagicMock()
        mock_hou.node.return_value = node
        with patch.dict(sys.modules, {"hou": mock_hou}):
            export_result = export_mod.export_channels("/obj/geo1", ["tx"], str(out))
        assert export_result["success"] is True
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["channels"]["tx"][1]["value"] == 10.0

        import_mod = _load_script("import_channels.py")
        target_parm = MagicMock()
        target = MagicMock()
        target.path.return_value = "/obj/geo2"
        target.parm.return_value = target_parm
        imp_hou = _hou_with_keyframe_class()
        imp_hou.node.return_value = target
        with patch.dict(sys.modules, {"hou": imp_hou}):
            import_result = import_mod.import_channels(str(out), node_path="/obj/geo2")
        assert import_result["success"] is True
        assert import_result["context"]["applied"]["tx"] == 2
        assert target_parm.setKeyframe.call_count == 2


class TestBake:
    def test_bake_channels_samples_each_frame(self) -> None:
        mod = _load_script("bake_channels.py")
        parm = MagicMock()
        parm.eval.return_value = 2.0
        node = MagicMock()
        node.path.return_value = "/obj/geo1"
        node.parm.return_value = parm
        mock_hou = _hou_with_keyframe_class()
        mock_hou.node.return_value = node
        mock_hou.frame.return_value = 1.0
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.bake_channels("/obj/geo1", ["tx"], frame_range=[1, 5])
        assert result["success"] is True
        assert result["context"]["baked"]["tx"] == 5
        assert parm.setKeyframe.call_count == 5

    def test_bake_channels_rejects_huge_range(self) -> None:
        mod = _load_script("bake_channels.py")
        with patch.dict(sys.modules, {"hou": _hou_with_keyframe_class()}):
            result = mod.bake_channels("/obj/geo1", ["tx"], frame_range=[1, 10_000_000])
        assert result["success"] is False

    def test_cache_simulation_reports_written(self, tmp_path: Path) -> None:
        mod = _load_script("cache_simulation.py")
        out = tmp_path / "cache.bgeo"
        file_parm = MagicMock()
        file_parm.eval.return_value = str(out)
        rop = MagicMock()
        rop.path.return_value = "/out/filecache1"
        rop.parm.side_effect = lambda n: file_parm if n == "file" else None
        rop.parmTuple.return_value = None
        rop.render.side_effect = lambda verbose=False: out.write_bytes(b"c")
        mock_hou = MagicMock()
        mock_hou.node.return_value = rop
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.cache_simulation("/out/filecache1", background=False)
        assert result["success"] is True
        assert result["context"]["cached"] is True
        assert result["context"]["written_files"] == [str(out)]

    def test_cache_simulation_defaults_to_background_in_ui(self, tmp_path: Path) -> None:
        mod = _load_script("cache_simulation.py")
        output = tmp_path / "cache.$F4.bgeo.sc"
        file_parm = MagicMock()
        file_parm.eval.return_value = str(output)
        file_parm.unexpandedString.return_value = str(output)
        rop = MagicMock()
        rop.path.return_value = "/out/filecache1"
        rop.parm.side_effect = lambda name: file_parm if name == "file" else None
        mock_hou = MagicMock()
        mock_hou.node.return_value = rop
        mock_hou.isUIAvailable.return_value = True
        job = {"job_id": "a" * 32, "state": "queued", "pid": 4321}

        with patch.dict(sys.modules, {"hou": mock_hou}), patch.object(
            mod, "launch_background_render", return_value=job
        ) as launch:
            result = mod.cache_simulation("/out/filecache1", frame_range=[1, 120, 1])

        assert result["success"] is True
        assert result["context"]["background"] is True
        launch.assert_called_once_with(
            mock_hou,
            "/out/filecache1",
            [1, 120, 1],
            str(output),
            job_kind="cache",
        )
        rop.render.assert_not_called()

    def test_cache_simulation_defaults_to_foreground_without_ui(self, tmp_path: Path) -> None:
        mod = _load_script("cache_simulation.py")
        output = tmp_path / "cache.bgeo.sc"
        file_parm = MagicMock()
        file_parm.eval.return_value = str(output)
        rop = MagicMock()
        rop.path.return_value = "/out/filecache1"
        rop.parm.side_effect = lambda name: file_parm if name == "file" else None
        rop.parmTuple.return_value = None
        rop.render.side_effect = lambda verbose=False: output.write_bytes(b"cache")
        mock_hou = MagicMock()
        mock_hou.node.return_value = rop
        mock_hou.isUIAvailable.return_value = False

        with patch.dict(sys.modules, {"hou": mock_hou}), patch.object(mod, "launch_background_render") as launch:
            result = mod.cache_simulation("/out/filecache1")

        assert result["success"] is True
        assert result["context"]["background"] is False
        launch.assert_not_called()
        rop.render.assert_called_once_with(verbose=False)
