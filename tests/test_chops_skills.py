"""Mock-hou unit tests for the houdini-chops skill."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

_SKILLS_ROOT = Path(__file__).parent.parent / "src" / "dcc_mcp_houdini" / "skills"


def _load_script(script_name: str) -> ModuleType:
    path = _SKILLS_ROOT / "houdini-chops" / "scripts" / script_name
    spec = importlib.util.spec_from_file_location(f"chops_{path.stem}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _make_channel(name, value=0.0):
    ch = MagicMock()
    ch.name.return_value = name
    ch.eval.return_value = value
    return ch


class TestChopNetwork:
    def test_create_chop_network(self) -> None:
        mod = _load_script("create_chop_network.py")
        child = MagicMock()
        child.path.return_value = "/ch/chopnet1"
        child.name.return_value = "chopnet1"
        parent = MagicMock()
        parent.path.return_value = "/ch"
        parent.createNode.return_value = child
        mock_hou = MagicMock()
        mock_hou.node.side_effect = lambda p: parent if p == "/ch" else None

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.create_chop_network("/ch", network_name="chopnet1")

        assert result["success"] is True
        parent.createNode.assert_called_once_with("chopnet", node_name="chopnet1")
        assert result["context"]["network_path"] == "/ch/chopnet1"

    def test_create_chop_network_returns_existing(self) -> None:
        mod = _load_script("create_chop_network.py")
        existing = MagicMock()
        existing.path.return_value = "/ch/chopnet1"
        existing.name.return_value = "chopnet1"
        mock_hou = MagicMock()
        mock_hou.node.return_value = existing

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.create_chop_network("/ch", network_name="chopnet1")

        assert result["success"] is True
        assert result["context"]["network_path"] == "/ch/chopnet1"


class TestMotionClip:
    def test_create_motionclip(self) -> None:
        mod = _load_script("create_motionclip.py")
        node = MagicMock()
        node.path.return_value = "/ch/chopnet1/motionclip1"
        node.name.return_value = "motionclip1"
        file_parm = MagicMock()
        start_parm = MagicMock()
        node.parm.side_effect = lambda name: {"file": file_parm, "start": start_parm}.get(name)
        network = MagicMock()
        network.createNode.return_value = node
        mock_hou = MagicMock()
        mock_hou.node.return_value = network

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.create_motionclip("/ch/chopnet1", clip_file="/tmp/clip.bclip", start_frame=10.0)

        assert result["success"] is True
        network.createNode.assert_called_once_with("motionclip", node_name="motionclip1")
        file_parm.set.assert_called_once_with("/tmp/clip.bclip")
        start_parm.set.assert_called_once_with(10.0)

    def test_create_motionclip_minimal(self) -> None:
        mod = _load_script("create_motionclip.py")
        node = MagicMock()
        node.path.return_value = "/ch/chopnet1/motionclip1"
        node.name.return_value = "motionclip1"
        network = MagicMock()
        network.createNode.return_value = node
        mock_hou = MagicMock()
        mock_hou.node.return_value = network

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.create_motionclip("/ch/chopnet1")

        assert result["success"] is True
        assert result["context"]["applied"] == {}


class TestAudioDriven:
    def test_create_audio_driven(self) -> None:
        mod = _load_script("create_audio_driven.py")
        file_node = MagicMock()
        file_node.path.return_value = "/ch/chopnet1/audio_file1"
        envelope = MagicMock()
        envelope.path.return_value = "/ch/chopnet1/envelope1"
        network = MagicMock()
        network.createNode.side_effect = [file_node, envelope]
        mock_hou = MagicMock()
        mock_hou.node.return_value = network

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.create_audio_driven(
                "/ch/chopnet1",
                audio_file="/tmp/music.wav",
                target_parm="/obj/geo1/tx",
                channel_name="amplitude",
            )

        assert result["success"] is True
        assert result["context"]["audio_file"] == "/tmp/music.wav"
        assert result["context"]["target_parm"] == "/obj/geo1/tx"
        envelope.setExportFlag.assert_called_once()


class TestApplyFilter:
    def test_apply_filter_lag(self) -> None:
        mod = _load_script("apply_filter.py")
        src = MagicMock()
        src.path.return_value = "/ch/chopnet1/audio_file1"
        filter_node = MagicMock()
        filter_node.path.return_value = "/ch/chopnet1/lag_1"
        network = MagicMock()
        network.path.return_value = "/ch/chopnet1"
        network.createNode.return_value = filter_node
        parm = MagicMock()
        filter_node.parm.return_value = parm
        mock_hou = MagicMock()
        mock_hou.node.side_effect = lambda p: network if p == "/ch/chopnet1" else src

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.apply_filter("/ch/chopnet1", "audio_file1", "lag", amount=0.8)

        assert result["success"] is True
        network.createNode.assert_called_once_with("lag", node_name="lag_1")
        filter_node.setFirstInput.assert_called_once_with(src)
        parm.set.assert_called_once_with(0.8)
        assert result["context"]["filter_type"] == "lag"

    def test_apply_filter_unknown_type_returns_error(self) -> None:
        mod = _load_script("apply_filter.py")
        mock_hou = MagicMock()
        mock_hou.node.return_value = MagicMock()

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.apply_filter("/ch/chopnet1", "src", "invalid_filter")

        assert result["success"] is False


class TestGetChannelInfo:
    def test_get_channel_info(self) -> None:
        mod = _load_script("get_channel_info.py")
        channels = [_make_channel("tx", 0.5), _make_channel("ty", 2.0)]
        node = MagicMock()
        node.path.return_value = "/ch/chopnet1/lag1"
        node.name.return_value = "lag1"
        node.type.return_value.name.return_value = "lag"
        node.sampleRate.return_value = 60.0
        node.segmentLength.return_value = 200.0
        node.channels.return_value = channels
        node.timeRange.return_value = (1, 200)
        mock_hou = MagicMock()
        mock_hou.node.return_value = node
        mock_hou.frame.return_value = 1.0

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.get_channel_info("/ch/chopnet1/lag1")

        assert result["success"] is True
        assert result["context"]["sample_rate"] == 60.0
        assert result["context"]["channel_count"] == 2
        assert result["context"]["channel_names"] == ["tx", "ty"]
        assert len(result["context"]["channels"]) == 2


class TestExportToKeyframes:
    def test_export_to_keyframes(self) -> None:
        mod = _load_script("export_to_keyframes.py")
        parm = MagicMock()
        target = MagicMock()
        target.path.return_value = "/obj/geo1"
        target.parm.return_value = parm
        chop_node = MagicMock()
        chop_node.path.return_value = "/ch/chopnet1/lag1"
        chop_node.timeRange.return_value = (1, 5)
        chop_node.evalAtFrame.return_value = 2.0

        mock_hou = MagicMock()
        mock_hou.node.side_effect = lambda p: {
            "/ch/chopnet1/lag1": chop_node,
            "/obj/geo1": target,
        }.get(p)
        mock_hou.frame.return_value = 1.0
        mock_hou.Keyframe.return_value = MagicMock()

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.export_to_keyframes(
                "/ch/chopnet1/lag1",
                "/obj/geo1",
                ["tx", "ty"],
            )

        assert result["success"] is True
        assert result["context"]["total_keyframes"] == 10  # 5 frames × 2 parms
        assert parm.setKeyframe.call_count == 10

    def test_export_to_keyframes_with_frame_range(self) -> None:
        mod = _load_script("export_to_keyframes.py")
        parm = MagicMock()
        target = MagicMock()
        target.path.return_value = "/obj/geo1"
        target.parm.return_value = parm
        chop_node = MagicMock()
        chop_node.path.return_value = "/ch/chopnet1/lag1"
        chop_node.evalAtFrame.return_value = 3.0

        mock_hou = MagicMock()
        mock_hou.node.side_effect = lambda p: {
            "/ch/chopnet1/lag1": chop_node,
            "/obj/geo1": target,
        }.get(p)
        mock_hou.frame.return_value = 1.0
        mock_hou.Keyframe.return_value = MagicMock()

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.export_to_keyframes(
                "/ch/chopnet1/lag1",
                "/obj/geo1",
                ["tx"],
                frame_range=[1, 3],
            )

        assert result["success"] is True
        assert result["context"]["frame_range"] == [1.0, 3.0]
        assert result["context"]["total_keyframes"] == 3
