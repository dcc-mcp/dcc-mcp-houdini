"""Mock-hou unit tests for the houdini-kinefx skill."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

from skill_loader import skill_script_import_context

_SKILLS_ROOT = Path(__file__).parent.parent / "src" / "dcc_mcp_houdini" / "skills"


def _load_script(script_name: str) -> ModuleType:
    path = _SKILLS_ROOT / "houdini-kinefx" / "scripts" / script_name
    spec = importlib.util.spec_from_file_location(f"kfx_{path.stem}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    with skill_script_import_context(spec):
        spec.loader.exec_module(module)
    return module


class TestCreateRig:
    def test_create_rig_with_joint_chain(self) -> None:
        mod = _load_script("create_rig.py")
        geo = MagicMock()
        geo.path.return_value = "/obj/geo1"

        # rig_sop = geo.createNode("null", node_name=rig_name)
        rig_sop = MagicMock()
        rig_sop.path.return_value = "/obj/geo1/rig1"
        rig_geo = MagicMock()
        rig_sop.geometry.return_value = rig_geo

        geo.createNode.return_value = rig_sop

        mock_hou = MagicMock()
        # Use side_effect to differentiate: rig doesn't exist yet, return None
        mock_hou.node.side_effect = lambda p: None if "rig1" in p else geo

        class MockAttribType:
            Point = "point"

        mock_hou.attribType = MockAttribType()

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.create_rig(
                "/obj/geo1",
                rig_name="rig1",
                joint_chain=[
                    {"name": "hip", "translate": [0, 0, 0]},
                    {"name": "spine", "translate": [0, 0.5, 0]},
                    {"name": "head", "translate": [0, 1.0, 0]},
                ],
            )

        assert result["success"] is True
        assert result["context"]["rig_path"] == "/obj/geo1/rig1"
        assert result["context"]["joint_count"] == 3

    def test_create_rig_with_auto_capture(self) -> None:
        mod = _load_script("create_rig.py")
        geo = MagicMock()
        geo.path.return_value = "/obj/geo1"

        rig_sop = MagicMock()
        rig_sop.path.return_value = "/obj/geo1/rig1"
        rig_geo = MagicMock()
        rig_sop.geometry.return_value = rig_geo

        bone_deform = MagicMock()
        bone_deform.path.return_value = "/obj/geo1/bonedeform_rig1"

        mesh_node = MagicMock()
        mesh_node.path.return_value = "/obj/geo1/body"

        geo.createNode.side_effect = [rig_sop, bone_deform]

        mock_hou = MagicMock()
        mock_hou.node.side_effect = lambda p: {
            "/obj/geo1": geo,
            "/obj/geo1/body": mesh_node,
        }.get(p)

        class MockAttribType:
            Point = "point"

        mock_hou.attribType = MockAttribType()

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.create_rig(
                "/obj/geo1",
                rig_name="rig1",
                joint_chain=[{"name": "root", "translate": [0, 0, 0]}],
                auto_capture=True,
                capture_mesh="body",
            )

        assert result["success"] is True
        assert result["context"]["auto_capture"] is True
        assert len(result["context"]["created_nodes"]) == 2
        bone_deform.setFirstInput.assert_called_once_with(mesh_node)
        bone_deform.setInput.assert_called_with(1, rig_sop)


class TestSetRigPose:
    def test_set_rig_pose_by_index(self) -> None:
        mod = _load_script("set_rig_pose.py")
        pt = MagicMock()
        geo = MagicMock()
        geo.iterPoints.return_value = [pt]
        node = MagicMock()
        node.path.return_value = "/obj/geo1/rig1"
        node.geometry.return_value = geo
        mock_hou = MagicMock()
        mock_hou.node.return_value = node
        mock_hou.Vector3 = lambda *args: list(args) if args else [0.0, 0.0, 0.0]

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.set_rig_pose(
                "/obj/geo1/rig1",
                joint_index=0,
                translate=[0.0, 1.0, 0.0],
            )

        assert result["success"] is True
        assert result["context"]["applied"]["translate"] == [0.0, 1.0, 0.0]
        pt.setPosition.assert_called_once()

    def test_set_rig_pose_with_rotation(self) -> None:
        mod = _load_script("set_rig_pose.py")
        pt = MagicMock()
        geo = MagicMock()
        geo.iterPoints.return_value = [pt]
        geo.points.return_value = [pt]
        geo.findPointAttrib.return_value = None  # rot attr doesn't exist yet
        geo.addAttrib.return_value = "rot"
        node = MagicMock()
        node.path.return_value = "/obj/geo1/rig1"
        node.geometry.return_value = geo
        mock_hou = MagicMock()
        mock_hou.node.return_value = node
        mock_hou.Vector3 = lambda *args: list(args) if args else [0.0, 0.0, 0.0]
        mock_hou.attribType.Point = "point"

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.set_rig_pose(
                "/obj/geo1/rig1",
                rotate=[90.0, 0.0, 0.0],
            )

        assert result["success"] is True
        assert result["context"]["applied"]["rotate"] == [90.0, 0.0, 0.0]
        geo.addAttrib.assert_called_once()

    def test_set_rig_pose_no_geometry_returns_error(self) -> None:
        mod = _load_script("set_rig_pose.py")
        node = MagicMock()
        node.path.return_value = "/obj/geo1/rig1"
        node.geometry.return_value = None
        mock_hou = MagicMock()
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.set_rig_pose("/obj/geo1/rig1")

        assert result["success"] is False


class TestCaptureJoints:
    def test_capture_joints_proximity(self) -> None:
        mod = _load_script("capture_joints.py")
        geo = MagicMock()
        geo.path.return_value = "/obj/geo1"
        mesh = MagicMock()
        mesh.path.return_value = "/obj/geo1/body"
        rig = MagicMock()
        rig.path.return_value = "/obj/geo1/rig1"
        capture_node = MagicMock()
        capture_node.path.return_value = "/obj/geo1/capture_rig1"
        geo.createNode.return_value = capture_node

        parm_max = MagicMock()
        parm_falloff = MagicMock()
        capture_node.parm.side_effect = lambda n: {
            "maxpoints": parm_max,
            "falloff": parm_falloff,
        }.get(n)

        mock_hou = MagicMock()
        mock_hou.node.side_effect = lambda p: {
            "/obj/geo1": geo,
            "/obj/geo1/body": mesh,
            "/obj/geo1/rig1": rig,
        }.get(p)

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.capture_joints(
                "/obj/geo1",
                mesh_name="body",
                rig_name="rig1",
                method="proximity",
                max_joints=4,
                falloff=1.0,
            )

        assert result["success"] is True
        geo.createNode.assert_called_once_with("captureproximity", node_name="capture_rig1")
        capture_node.setFirstInput.assert_called_once_with(mesh)
        parm_max.set.assert_called_once_with(4)
        parm_falloff.set.assert_called_once_with(1.0)

    def test_capture_joints_bones_method(self) -> None:
        mod = _load_script("capture_joints.py")
        geo = MagicMock()
        geo.path.return_value = "/obj/geo1"
        mesh = MagicMock()
        rig = MagicMock()
        capture_node = MagicMock()
        geo.createNode.return_value = capture_node

        mock_hou = MagicMock()
        mock_hou.node.side_effect = lambda p: {
            "/obj/geo1": geo,
            "/obj/geo1/body": mesh,
            "/obj/geo1/rig1": rig,
        }.get(p)

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.capture_joints("/obj/geo1", "body", "rig1", method="bones")

        assert result["success"] is True
        geo.createNode.assert_called_once_with("bonecapture", node_name="capture_rig1")


class TestApplyMocap:
    def test_apply_mocap_bclip(self) -> None:
        mod = _load_script("apply_mocap.py")
        geo = MagicMock()
        geo.path.return_value = "/obj/geo1"
        rig = MagicMock()
        rig.path.return_value = "/obj/geo1/rig1"
        import_node = MagicMock()
        import_node.path.return_value = "/obj/geo1/mocap1"
        bone_deform = MagicMock()
        bone_deform.path.return_value = "/obj/geo1/anim_rig1"
        geo.createNode.side_effect = [import_node, bone_deform]

        mock_hou = MagicMock()
        mock_hou.node.side_effect = lambda p: {
            "/obj/geo1": geo,
            "/obj/geo1/rig1": rig,
        }.get(p)

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.apply_mocap(
                "/obj/geo1",
                rig_name="rig1",
                mocap_file="/tmp/walk.bclip",
            )

        assert result["success"] is True
        assert result["context"]["file_type"] == "bclip"
        geo.createNode.assert_any_call("motionclip", node_name="mocap1")
        bone_deform.setInput.assert_any_call(0, import_node, 0)
        bone_deform.setInput.assert_any_call(1, rig, 0)
