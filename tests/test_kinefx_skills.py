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

        rig_sop = MagicMock()
        rig_sop.path.return_value = "/obj/geo1/rig1"
        rig_geo = MagicMock()
        stash = MagicMock()
        rig_sop.parm.return_value = stash

        geo.createNode.return_value = rig_sop

        mock_hou = MagicMock()
        mock_hou.Geometry.return_value = rig_geo
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
        geo.createNode.assert_called_once_with("kinefx::skeleton", node_name="rig1")
        rig_sop.geometry.assert_not_called()
        stash.set.assert_called_once_with(rig_geo)

    def test_create_rig_with_auto_capture(self) -> None:
        mod = _load_script("create_rig.py")
        geo = MagicMock()
        geo.path.return_value = "/obj/geo1"

        rig_sop = MagicMock()
        rig_sop.path.return_value = "/obj/geo1/rig1"
        rig_geo = MagicMock()
        rig_sop.parm.return_value = MagicMock()

        rest_rig = MagicMock()
        rest_rig.path.return_value = "/obj/geo1/rest_rig1"
        rest_stash = MagicMock()
        rest_rig.parm.return_value = rest_stash
        rest_geo = MagicMock()
        capture = MagicMock()
        capture.path.return_value = "/obj/geo1/capture_rig1"
        joint_deform = MagicMock()
        joint_deform.path.return_value = "/obj/geo1/jointdeform_rig1"

        mesh_node = MagicMock()
        mesh_node.path.return_value = "/obj/geo1/body"

        geo.createNode.side_effect = [rig_sop, rest_rig, capture, joint_deform]

        mock_hou = MagicMock()
        mock_hou.Geometry.side_effect = [rig_geo, rest_geo]
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
        assert len(result["context"]["created_nodes"]) == 4
        rest_stash.set.assert_called_once_with(rest_geo)
        capture.setInput.assert_any_call(0, mesh_node)
        capture.setInput.assert_any_call(1, rest_rig)
        capture.setInput.assert_any_call(2, rig_sop)
        joint_deform.setInput.assert_any_call(0, capture)
        joint_deform.setInput.assert_any_call(1, rest_rig)
        joint_deform.setInput.assert_any_call(2, rig_sop)
        joint_deform.cook.assert_called_once_with(force=True)

    def test_create_rig_validates_joint_chain_before_creating_nodes(self) -> None:
        mod = _load_script("create_rig.py")
        geo = MagicMock()
        geo.path.return_value = "/obj/geo1"
        mock_hou = MagicMock()
        mock_hou.node.side_effect = lambda path: geo if path == "/obj/geo1" else None

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.create_rig(
                "/obj/geo1",
                rig_name="rig1",
                joint_chain=[
                    {"name": "duplicate", "translate": [0, 0, 0]},
                    {"name": "duplicate", "translate": [0, 1, 0]},
                ],
            )

        assert result["success"] is False
        geo.createNode.assert_not_called()

    def test_create_rig_validates_joint_name_before_creating_nodes(self) -> None:
        mod = _load_script("create_rig.py")
        geo = MagicMock()
        geo.path.return_value = "/obj/geo1"
        mock_hou = MagicMock()
        mock_hou.node.side_effect = lambda path: geo if path == "/obj/geo1" else None

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.create_rig(
                "/obj/geo1",
                rig_name="rig1",
                joint_chain=[{"name": None, "translate": [0, 0, 0]}],
            )

        assert result["success"] is False
        geo.createNode.assert_not_called()

    def test_create_rig_auto_capture_requires_joint_chain_before_creating_nodes(self) -> None:
        mod = _load_script("create_rig.py")
        geo = MagicMock()
        geo.path.return_value = "/obj/geo1"
        mesh = MagicMock()
        mock_hou = MagicMock()
        mock_hou.node.side_effect = lambda path: {
            "/obj/geo1": geo,
            "/obj/geo1/body": mesh,
        }.get(path)

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.create_rig("/obj/geo1", auto_capture=True, capture_mesh="body")

        assert result["success"] is False
        geo.createNode.assert_not_called()


class TestSetRigPose:
    def test_set_rig_pose_by_index(self) -> None:
        mod = _load_script("set_rig_pose.py")
        pt = MagicMock()
        cooked_geo = MagicMock()
        editable_geo = MagicMock()
        editable_geo.iterPoints.return_value = [pt]
        editable_geo.points.return_value = [pt]
        node = MagicMock()
        node.path.return_value = "/obj/geo1/rig1"
        node.geometry.return_value = cooked_geo
        stash = MagicMock()
        node.parm.return_value = stash
        mock_hou = MagicMock()
        mock_hou.node.return_value = node
        mock_hou.Geometry.return_value = editable_geo
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
        mock_hou.Geometry.assert_called_once_with(cooked_geo)
        stash.set.assert_called_once_with(editable_geo)

    def test_set_rig_pose_with_rotation(self) -> None:
        mod = _load_script("set_rig_pose.py")
        pt = MagicMock()
        cooked_geo = MagicMock()
        editable_geo = MagicMock()
        editable_geo.iterPoints.return_value = [pt]
        editable_geo.points.return_value = [pt]
        editable_geo.findPointAttrib.return_value = "transform"
        pt.attribValue.return_value = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)
        node = MagicMock()
        node.path.return_value = "/obj/geo1/rig1"
        node.geometry.return_value = cooked_geo
        node.parm.return_value = MagicMock()
        mock_hou = MagicMock()
        mock_hou.node.return_value = node
        mock_hou.Geometry.return_value = editable_geo
        current_matrix = MagicMock()
        current_matrix.extractRotates.return_value = (0.0, 0.0, 0.0)
        current_matrix.extractScales.return_value = (1.0, 1.0, 1.0)
        mock_hou.Matrix4.return_value = current_matrix
        built_matrix = MagicMock()
        result_matrix = MagicMock()
        result_matrix.asTuple.return_value = (1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, -1.0, 0.0)
        mock_hou.hmath.buildTransform.return_value = built_matrix
        mock_hou.Matrix3.side_effect = [MagicMock(), result_matrix]

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.set_rig_pose(
                "/obj/geo1/rig1",
                rotate=[90.0, 0.0, 0.0],
            )

        assert result["success"] is True
        assert result["context"]["applied"]["rotate"] == [90.0, 0.0, 0.0]
        pt.setAttribValue.assert_called_once_with(
            "transform",
            (1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, -1.0, 0.0),
        )
        editable_geo.addAttrib.assert_not_called()

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

    def test_set_rig_pose_rejects_short_vectors(self) -> None:
        mod = _load_script("set_rig_pose.py")
        mock_hou = MagicMock()

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.set_rig_pose("/obj/geo1/rig1", rotate=[90.0, 0.0])

        assert result["success"] is False
        mock_hou.node.assert_not_called()

    def test_set_rig_pose_rejects_negative_joint_index(self) -> None:
        mod = _load_script("set_rig_pose.py")
        mock_hou = MagicMock()

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.set_rig_pose("/obj/geo1/rig1", joint_index=-1, translate=[0.0, 1.0, 0.0])

        assert result["success"] is False
        mock_hou.node.assert_not_called()


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


class TestBuildRetargetMotionMixer:
    def test_builds_and_validates_houdini22_chain(self) -> None:
        mod = _load_script("build_retarget_motion_mixer.py")
        container = MagicMock()
        container.path.return_value = "/obj/anim"
        target = MagicMock()
        target.path.return_value = "/obj/anim/target"
        source_a = MagicMock()
        source_a.path.return_value = "/obj/anim/source_a"
        source_b = MagicMock()
        source_b.path.return_value = "/obj/anim/source_b"
        created = []

        def create_node(type_name: str, node_name: str) -> MagicMock:
            node = MagicMock()
            node.path.return_value = "/obj/anim/{}".format(node_name)
            node.errors.return_value = ()
            node.warnings.return_value = ()
            node.parm.return_value = MagicMock()
            node.type_name = type_name
            created.append(node)
            return node

        container.createNode.side_effect = create_node
        mock_hou = MagicMock()
        mock_hou.node.side_effect = lambda path: {
            "/obj/anim": container,
            "/obj/anim/target": target,
            "/obj/anim/source_a": source_a,
            "/obj/anim/source_b": source_b,
        }.get(path)

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.build_retarget_motion_mixer(
                geo_path="/obj/anim",
                target_skeleton="/obj/anim/target",
                source_skeletons=["/obj/anim/source_a", "/obj/anim/source_b"],
                clip_names=["flight", "landing"],
                character_name="honeybee",
            )

        assert result["success"] is True
        assert result["context"]["validated"] is True
        assert result["context"]["clip_names"] == ["flight", "landing"]
        assert len(result["context"]["clip_nodes"]) == 2
        assert result["context"]["motion_mixer"].endswith("_motion_mixer")
        assert {node.type_name for node in created} >= {
            "kinefx::rigmatchpose",
            "kinefx::mappoints",
            "kinefx::fullbodyik",
            "kinefx::motionclip",
            "apex::packcharacter",
            "apex::animationfromskeleton",
            "kinefx::motionmixer",
            "kinefx::motionmixerfetch",
        }
        assert all(node.cook.called for node in created)

    def test_requires_multiple_source_skeletons(self) -> None:
        mod = _load_script("build_retarget_motion_mixer.py")
        result = mod.build_retarget_motion_mixer(
            geo_path="/obj/anim",
            target_skeleton="/obj/anim/target",
            source_skeletons=["/obj/anim/source_a"],
        )
        assert result["success"] is False
