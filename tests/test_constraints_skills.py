"""Mock-hou unit tests for the houdini-constraints skill."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

_SKILLS_ROOT = Path(__file__).parent.parent / "src" / "dcc_mcp_houdini" / "skills"


def _load_script(script_name: str) -> ModuleType:
    path = _SKILLS_ROOT / "houdini-constraints" / "scripts" / script_name
    spec = importlib.util.spec_from_file_location(f"ctr_{path.stem}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _make_obj_node(path, name, node_type="geo"):
    node = MagicMock()
    node.path.return_value = path
    node.name.return_value = name
    node.type.return_value.name.return_value = node_type
    return node


class TestParentConstraint:
    def test_create_parent_constraint(self) -> None:
        mod = _load_script("create_parent_constraint.py")
        driven = _make_obj_node("/obj/geo2", "geo2")
        target = _make_obj_node("/obj/geo1", "geo1")
        blend = _make_obj_node("/obj/blend_geo2", "blend_geo2", "blend")
        parent = MagicMock()
        parent.path.return_value = "/obj"
        parent.createNode.return_value = blend
        driven.parent.return_value = parent

        # World transforms for offset calc.
        driven_mat = MagicMock()
        driven_mat.inverted.return_value = MagicMock()
        driven.worldTransform.return_value = driven_mat
        target.worldTransform.return_value = MagicMock()

        mock_hou = MagicMock()
        mock_hou.node.side_effect = lambda p: {
            "/obj/geo2": driven,
            "/obj/geo1": target,
            "/obj": parent,
        }.get(p)
        mock_hou.hscriptExpression.return_value = "ch_test"

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.create_parent_constraint("/obj/geo2", "/obj/geo1")

        assert result["success"] is True
        assert result["context"]["driven_path"] == "/obj/geo2"
        assert result["context"]["target_path"] == "/obj/geo1"
        assert "blend_node_path" in result["context"]


class TestBlendConstraint:
    def test_create_blend_constraint(self) -> None:
        mod = _load_script("create_blend_constraint.py")
        driven = _make_obj_node("/obj/geo3", "geo3")
        t1 = _make_obj_node("/obj/geo1", "geo1")
        t2 = _make_obj_node("/obj/geo2", "geo2")
        blend = _make_obj_node("/obj/blend_geo3", "blend_geo3", "blend")
        parent = MagicMock()
        parent.path.return_value = "/obj"
        parent.createNode.return_value = blend
        driven.parent.return_value = parent

        mock_hou = MagicMock()
        mock_hou.node.side_effect = lambda p: {
            "/obj/geo3": driven,
            "/obj/geo1": t1,
            "/obj/geo2": t2,
            "/obj": parent,
        }.get(p)
        mock_hou.hscriptExpression.return_value = "ch_test"

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.create_blend_constraint("/obj/geo3", ["/obj/geo1", "/obj/geo2"], weights=[0.3, 0.7])

        assert result["success"] is True
        assert result["context"]["target_count"] == 2
        assert result["context"]["target_paths"] == ["/obj/geo1", "/obj/geo2"]

    def test_create_blend_constraint_empty_targets_returns_error(self) -> None:
        mod = _load_script("create_blend_constraint.py")
        mock_hou = MagicMock()

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.create_blend_constraint("/obj/geo3", [])

        assert result["success"] is False

    def test_create_blend_constraint_weight_mismatch_returns_error(self) -> None:
        mod = _load_script("create_blend_constraint.py")
        mock_hou = MagicMock()

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.create_blend_constraint("/obj/geo3", ["/obj/geo1", "/obj/geo2"], weights=[1.0])

        assert result["success"] is False


class TestPositionConstraint:
    def test_create_position_constraint(self) -> None:
        mod = _load_script("create_position_constraint.py")
        driven = _make_obj_node("/obj/geo2", "geo2")
        target = _make_obj_node("/obj/geo1", "geo1")
        object_chop = MagicMock()
        object_chop.path.return_value = "/ch/pos_constraint1/obj_geo1"
        chop_ctx = MagicMock()
        chop_ctx.createNode.return_value = object_chop

        driven_parm = MagicMock()
        driven.parm.return_value = driven_parm

        # Transform mocks for offset calculation.
        dt = MagicMock()
        dt.extractTranslates.return_value = [1.0, 2.0, 3.0]
        tt = MagicMock()
        tt.extractTranslates.return_value = [0.0, 0.0, 0.0]
        driven.worldTransform.return_value = dt
        target.worldTransform.return_value = tt

        mock_hou = MagicMock()
        mock_hou.node.side_effect = lambda p: {
            "/obj/geo2": driven,
            "/obj/geo1": target,
            "/ch": chop_ctx,
        }.get(p)

        class MockExprLang:
            Hscript = "hscript"

        mock_hou.exprLanguage = MockExprLang()

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.create_position_constraint("/obj/geo2", "/obj/geo1")

        assert result["success"] is True
        assert result["context"]["driven_path"] == "/obj/geo2"
        assert result["context"]["offset"] == {"tx": 1.0, "ty": 2.0, "tz": 3.0}


class TestOrientConstraint:
    def test_create_orient_constraint(self) -> None:
        mod = _load_script("create_orient_constraint.py")
        driven = _make_obj_node("/obj/geo2", "geo2")
        target = _make_obj_node("/obj/geo1", "geo1")
        object_chop = MagicMock()
        object_chop.path.return_value = "/ch/orient_constraint1/obj_rot_geo1"
        chop_ctx = MagicMock()
        chop_ctx.createNode.return_value = object_chop

        driven_parm = MagicMock()
        driven.parm.return_value = driven_parm

        dt = MagicMock()
        dt.extractRotates.return_value = [30.0, 45.0, 0.0]
        tt = MagicMock()
        tt.extractRotates.return_value = [0.0, 0.0, 0.0]
        driven.worldTransform.return_value = dt
        target.worldTransform.return_value = tt

        mock_hou = MagicMock()
        mock_hou.node.side_effect = lambda p: {
            "/obj/geo2": driven,
            "/obj/geo1": target,
            "/ch": chop_ctx,
        }.get(p)

        class MockExprLang:
            Hscript = "hscript"

        mock_hou.exprLanguage = MockExprLang()

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.create_orient_constraint("/obj/geo2", "/obj/geo1")

        assert result["success"] is True
        assert result["context"]["offset"] == {"rx": 30.0, "ry": 45.0, "rz": 0.0}


class TestListConstraints:
    def test_list_constraints_empty(self) -> None:
        mod = _load_script("list_constraints.py")
        obj_ctx = MagicMock()
        obj_ctx.children.return_value = []
        chop_ctx = MagicMock()
        chop_ctx.children.return_value = []
        mock_hou = MagicMock()
        mock_hou.node.side_effect = lambda p: {"/obj": obj_ctx, "/ch": chop_ctx}.get(p)

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.list_constraints("/obj")

        assert result["success"] is True
        assert result["context"]["count"] == 0
        assert result["context"]["constraints"] == []

    def test_list_constraints_finds_blend(self) -> None:
        mod = _load_script("list_constraints.py")
        inp = MagicMock()
        inp.path.return_value = "/obj/geo1"
        blend = MagicMock()
        blend.path.return_value = "/obj/blend1"
        blend.name.return_value = "blend1"
        blend.type.return_value.name.return_value = "blend"
        blend.inputs.return_value = [inp]
        obj_ctx = MagicMock()
        obj_ctx.children.return_value = [blend]
        chop_ctx = MagicMock()
        chop_ctx.children.return_value = []
        mock_hou = MagicMock()
        mock_hou.node.side_effect = lambda p: {"/obj": obj_ctx, "/ch": chop_ctx}.get(p)

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.list_constraints("/obj")

        assert result["success"] is True
        assert result["context"]["count"] == 1
        assert result["context"]["constraints"][0]["type"] == "blend"


class TestDeleteConstraint:
    def test_delete_constraint_blend(self) -> None:
        mod = _load_script("delete_constraint.py")
        blend = _make_obj_node("/obj/blend1", "blend1", "blend")
        child = _make_obj_node("/obj/geo1", "geo1")
        child_parm = MagicMock()
        child_parm.rawValue.return_value = "ch('/obj/blend1/tx')"
        child.parms.return_value = [child_parm]
        parent = MagicMock()
        parent.children.return_value = [blend, child]
        blend.parent.return_value = parent
        child.parent.return_value = parent

        mock_hou = MagicMock()
        mock_hou.node.return_value = blend

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.delete_constraint("/obj/blend1")

        assert result["success"] is True
        assert result["context"]["deleted_node"]["path"] == "/obj/blend1"
        blend.destroy.assert_called_once()
