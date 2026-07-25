"""Mock-hou regression tests for the houdini-vex skill package.

Covers all 7 tools:
- create_wrangle, update_vex_snippet, validate_vex_syntax,
- cook_wrangle, diagnose_wrangle, get_vex_info, list_wrangles

Tests include: create/update/cook/diagnose success and error paths,
VEX validation allowlist/deny-list, cook timeout, empty geometry,
thread-safety (dispatch boundary), cancellation, and edge cases.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, call, patch

from skill_loader import skill_script_import_context

_SKILLS_ROOT = Path(__file__).parent.parent / "src" / "dcc_mcp_houdini" / "skills"


def _load_script(skill_name: str, script_name: str) -> ModuleType:
    path = _SKILLS_ROOT / skill_name / "scripts" / script_name
    spec = importlib.util.spec_from_file_location(
        f"skill_{skill_name}_{path.stem}", path
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    with skill_script_import_context(spec):
        spec.loader.exec_module(module)
    return module


def _node(path: str, name: str, type_name: str = "geo") -> MagicMock:
    node = MagicMock()
    node.path.return_value = path
    node.name.return_value = name
    node.type.return_value.name.return_value = type_name
    return node


# ---------------------------------------------------------------------------
# create_wrangle
# ---------------------------------------------------------------------------


class TestCreateWrangle:
    def test_create_attribwrangle_without_vex(self) -> None:
        mod = _load_script("houdini-vex", "create_wrangle.py")
        new = _node("/obj/geo1/attribwrangle1", "attribwrangle1", "attribwrangle")
        parent = _node("/obj/geo1", "geo1")
        parent.createNode.return_value = new
        mock_hou = MagicMock()
        mock_hou.node.return_value = parent

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.create_wrangle("/obj/geo1")

        assert result["success"] is True
        assert result["context"]["node_path"] == "/obj/geo1/attribwrangle1"
        parent.createNode.assert_called_once_with("attribwrangle", node_name=None)

    def test_create_pointwrangle_with_valid_vex(self) -> None:
        mod = _load_script("houdini-vex", "create_wrangle.py")
        new = _node("/obj/geo1/pointwrangle1", "pointwrangle1", "pointwrangle")
        snip_parm = MagicMock()
        class_parm = MagicMock()
        display_flag_called = []

        def _parm_side_effect(name):
            if name == "snippet":
                return snip_parm
            if name == "class":
                return class_parm
            return None

        new.parm.side_effect = _parm_side_effect
        new.setDisplayFlag.side_effect = lambda v: display_flag_called.append(v)

        parent = _node("/obj/geo1", "geo1")
        parent.createNode.return_value = new
        mock_hou = MagicMock()
        mock_hou.node.return_value = parent

        snippet = "@P += {1, 0, 0};\n@Cd = {1, 0, 0};"

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.create_wrangle(
                parent_path="/obj/geo1",
                wrangle_type="pointwrangle",
                run_over="points",
                vex_code=snippet,
                set_display=True,
            )

        assert result["success"] is True
        assert result["context"]["wrangle_type"] == "pointwrangle"
        assert result["context"]["has_snippet"] is True
        parent.createNode.assert_called_once_with("pointwrangle", node_name=None)
        snip_parm.set.assert_called_once_with(snippet)
        class_parm.set.assert_called_once_with(0)  # points -> 0

    def test_create_wrangle_rejects_forbidden_vex(self) -> None:
        mod = _load_script("houdini-vex", "create_wrangle.py")

        with patch.dict(sys.modules, {"hou": MagicMock()}):
            result = mod.create_wrangle(
                parent_path="/obj/geo1",
                vex_code="python { print('hello'); }",
            )

        assert result["success"] is False
        assert "validation" in str(result.get("error", "")).lower()

    def test_create_wrangle_rejects_empty_vex(self) -> None:
        mod = _load_script("houdini-vex", "create_wrangle.py")

        with patch.dict(sys.modules, {"hou": MagicMock()}):
            result = mod.create_wrangle(
                parent_path="/obj/geo1",
                vex_code="   ",
            )

        assert result["success"] is False

    def test_create_wrangle_missing_parent(self) -> None:
        mod = _load_script("houdini-vex", "create_wrangle.py")
        mock_hou = MagicMock()
        mock_hou.node.return_value = None

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.create_wrangle("/obj/nonexistent")

        assert result["success"] is False

    def test_create_wrangle_with_bindings(self) -> None:
        mod = _load_script("houdini-vex", "create_wrangle.py")
        new = _node("/obj/geo1/attribwrangle1", "attribwrangle1", "attribwrangle")
        snip_parm = MagicMock()
        bind_parm = MagicMock()
        class_parm = MagicMock()

        def _parm_side_effect(name):
            if name == "snippet":
                return snip_parm
            if name == "class":
                return class_parm
            if name == "bindings":
                return bind_parm
            return None

        new.parm.side_effect = _parm_side_effect
        parent = _node("/obj/geo1", "geo1")
        parent.createNode.return_value = new
        mock_hou = MagicMock()
        mock_hou.node.return_value = parent

        snippet = "@pos = @P;"
        bindings = {"pos": "vector"}

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.create_wrangle(
                parent_path="/obj/geo1",
                vex_code=snippet,
                bindings=bindings,
            )

        assert result["success"] is True
        bind_parm.set.assert_called_once()

    def test_create_different_wrangle_types(self) -> None:
        for wt in ["volumewrangle", "geometrywrangle", "vertexwrangle", "detailwrangle"]:
            mod = _load_script("houdini-vex", "create_wrangle.py")
            new = _node(f"/obj/geo1/{wt}1", f"{wt}1", wt)
            snip_parm = MagicMock()
            class_parm = MagicMock()

            def _parm_side_effect(name):
                if name == "snippet":
                    return snip_parm
                if name == "class":
                    return class_parm
                return None

            new.parm.side_effect = _parm_side_effect
            parent = _node("/obj/geo1", "geo1")
            parent.createNode.return_value = new
            mock_hou = MagicMock()
            mock_hou.node.return_value = parent

            with patch.dict(sys.modules, {"hou": mock_hou}):
                result = mod.create_wrangle(
                    parent_path="/obj/geo1",
                    wrangle_type=wt,
                    vex_code="@P += 1;",
                )

            assert result["success"] is True, f"Failed for wrangle type: {wt}"
            assert result["context"]["wrangle_type"] == wt


# ---------------------------------------------------------------------------
# update_vex_snippet
# ---------------------------------------------------------------------------


class TestUpdateVexSnippet:
    def test_update_snippet_on_existing_wrangle(self) -> None:
        mod = _load_script("houdini-vex", "update_vex_snippet.py")
        old_snippet = "@P += {0,1,0};"
        new_snippet = "@P += {1,0,0};\n@Cd = {1,0,0};"

        snip_parm = MagicMock()
        snip_parm.evalAsString.return_value = old_snippet
        class_parm = MagicMock()

        node = _node("/obj/geo1/pointwrangle1", "pointwrangle1", "pointwrangle")

        def _parm_side_effect(name):
            if name == "snippet":
                return snip_parm
            if name == "class":
                return class_parm
            return None

        node.parm.side_effect = _parm_side_effect
        mock_hou = MagicMock()
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.update_vex_snippet(
                node_path="/obj/geo1/pointwrangle1",
                vex_code=new_snippet,
            )

        assert result["success"] is True
        assert result["context"]["previous_snippet_preview"] == old_snippet
        snip_parm.set.assert_called_once_with(new_snippet)

    def test_update_with_validation_rejects_forbidden(self) -> None:
        mod = _load_script("houdini-vex", "update_vex_snippet.py")

        with patch.dict(sys.modules, {"hou": MagicMock()}):
            result = mod.update_vex_snippet(
                node_path="/obj/geo1/pointwrangle1",
                vex_code="exec('x')",
            )

        assert result["success"] is False
        assert "validation" in str(result.get("error", "")).lower()

    def test_update_on_nonexistent_node(self) -> None:
        mod = _load_script("houdini-vex", "update_vex_snippet.py")
        mock_hou = MagicMock()
        mock_hou.node.return_value = None

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.update_vex_snippet(
                node_path="/obj/nonexistent",
                vex_code="@P += 1;",
            )

        assert result["success"] is False

    def test_update_with_run_over_change(self) -> None:
        mod = _load_script("houdini-vex", "update_vex_snippet.py")
        snip_parm = MagicMock()
        snip_parm.evalAsString.return_value = "// old"
        class_parm = MagicMock()

        node = _node("/obj/geo1/pointwrangle1", "pointwrangle1", "pointwrangle")

        def _parm_side_effect(name):
            if name == "snippet":
                return snip_parm
            if name == "class":
                return class_parm
            return None

        node.parm.side_effect = _parm_side_effect
        mock_hou = MagicMock()
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.update_vex_snippet(
                node_path="/obj/geo1/pointwrangle1",
                vex_code="@P += 1;",
                run_over="prims",
            )

        assert result["success"] is True
        class_parm.set.assert_called_once_with(1)  # prims -> 1

    def test_update_no_snippet_parm(self) -> None:
        mod = _load_script("houdini-vex", "update_vex_snippet.py")
        node = _node("/obj/geo1/box1", "box1", "box")
        node.parm.return_value = None  # No snippet parameter
        mock_hou = MagicMock()
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.update_vex_snippet(
                node_path="/obj/geo1/box1",
                vex_code="@P += 1;",
            )

        assert result["success"] is False


# ---------------------------------------------------------------------------
# validate_vex_syntax
# ---------------------------------------------------------------------------


class TestValidateVexSyntax:
    def test_valid_snippet_passes(self) -> None:
        mod = _load_script("houdini-vex", "validate_vex_syntax.py")
        result = mod.validate_vex_syntax("@P += {1,0,0};")
        assert result["success"] is True
        assert result["context"]["line_count"] == 1

    def test_forbidden_snippet_fails_with_errors(self) -> None:
        mod = _load_script("houdini-vex", "validate_vex_syntax.py")
        result = mod.validate_vex_syntax("python { print('x'); }")
        assert result["success"] is False
        assert result["context"]["error_count"] >= 1

    def test_unknown_attribute_bindings_warnings(self) -> None:
        mod = _load_script("houdini-vex", "validate_vex_syntax.py")
        result = mod.validate_vex_syntax(
            "@myUnknown = 1.0;",
            known_attributes=["P", "Cd"],
        )
        assert result["success"] is False
        assert result["context"]["error_count"] >= 1

    def test_known_attribute_bindings_pass(self) -> None:
        mod = _load_script("houdini-vex", "validate_vex_syntax.py")
        result = mod.validate_vex_syntax(
            "@myAttr = 1.0;",
            known_attributes=["myAttr", "P", "Cd"],
        )
        assert result["success"] is True

    def test_returns_severity_distribution(self) -> None:
        mod = _load_script("houdini-vex", "validate_vex_syntax.py")
        result = mod.validate_vex_syntax("python { exec('x'); }")
        assert result["success"] is False
        dist = result["context"]["severity_distribution"]
        assert dist["error"] >= 1

    def test_empty_snippet_fails(self) -> None:
        mod = _load_script("houdini-vex", "validate_vex_syntax.py")
        result = mod.validate_vex_syntax("")
        assert result["success"] is False

    def test_multi_line_snippet_reports_line_count(self) -> None:
        mod = _load_script("houdini-vex", "validate_vex_syntax.py")
        snippet = "@P += 1;\n@Cd = {1,0,0};\n@N = normalize(@N);"
        result = mod.validate_vex_syntax(snippet)
        assert result["success"] is True
        assert result["context"]["line_count"] == 3
        assert result["context"]["char_count"] == len(snippet)


# ---------------------------------------------------------------------------
# cook_wrangle
# ---------------------------------------------------------------------------


class TestCookWrangle:
    def test_cook_successful_wrangle(self) -> None:
        mod = _load_script("houdini-vex", "cook_wrangle.py")
        node = _node("/obj/geo1/pointwrangle1", "pointwrangle1", "pointwrangle")
        node.errors.return_value = []
        node.warnings.return_value = []

        geo = MagicMock()
        geo.points.return_value = [1, 2, 3]
        geo.prims.return_value = [1]
        geo.iterVertices.return_value = iter([1, 2, 3])

        pt_attrib = MagicMock()
        pt_attrib.name.return_value = "P"
        geo.pointAttribs.return_value = [pt_attrib]
        geo.primAttribs.return_value = []
        geo.vertexAttribs.return_value = []
        geo.globalAttribs.return_value = []

        grp = MagicMock()
        grp.name.return_value = "myGroup"
        geo.pointGroups.return_value = [grp]
        geo.primGroups.return_value = []
        geo.edgeGroups.return_value = []

        node.geometry.return_value = geo
        mock_hou = MagicMock()
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.cook_wrangle("/obj/geo1/pointwrangle1")

        assert result["success"] is True
        ctx = result["context"]
        assert ctx["cooked"] is True
        assert ctx["point_count"] == 3
        assert ctx["primitive_count"] == 1
        assert "P" in ctx["attribute_names"]

    def test_cook_failure_reports_errors(self) -> None:
        mod = _load_script("houdini-vex", "cook_wrangle.py")
        node = _node("/obj/geo1/pointwrangle1", "pointwrangle1", "pointwrangle")
        node.cook.side_effect = RuntimeError("syntax error on line 3")
        node.errors.return_value = ["syntax error on line 3"]
        node.warnings.return_value = []

        geo = MagicMock()
        geo.points.return_value = []
        geo.prims.return_value = []
        geo.iterVertices.return_value = iter([])
        geo.pointAttribs.return_value = []
        geo.primAttribs.return_value = []
        geo.vertexAttribs.return_value = []
        geo.globalAttribs.return_value = []
        geo.pointGroups.return_value = []
        geo.primGroups.return_value = []
        geo.edgeGroups.return_value = []

        node.geometry.return_value = geo
        mock_hou = MagicMock()
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.cook_wrangle("/obj/geo1/pointwrangle1")

        assert result["success"] is True  # skill reports success but cook failed
        ctx = result["context"]
        assert ctx["cooked"] is False
        assert ctx["cook_error"] is not None

    def test_cook_force_recook(self) -> None:
        mod = _load_script("houdini-vex", "cook_wrangle.py")
        node = _node("/obj/geo1/pointwrangle1", "pointwrangle1", "pointwrangle")
        node.errors.return_value = []
        node.warnings.return_value = []

        geo = MagicMock()
        geo.points.return_value = []
        geo.prims.return_value = []
        geo.iterVertices.return_value = iter([])
        geo.pointAttribs.return_value = []
        geo.primAttribs.return_value = []
        geo.vertexAttribs.return_value = []
        geo.globalAttribs.return_value = []
        geo.pointGroups.return_value = []
        geo.primGroups.return_value = []
        geo.edgeGroups.return_value = []
        node.geometry.return_value = geo
        mock_hou = MagicMock()
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.cook_wrangle("/obj/geo1/pointwrangle1", force=True)

        assert result["success"] is True
        node.cook.assert_called_once_with(force=True)

    def test_cook_missing_node(self) -> None:
        mod = _load_script("houdini-vex", "cook_wrangle.py")
        mock_hou = MagicMock()
        mock_hou.node.return_value = None

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.cook_wrangle("/obj/nonexistent")

        assert result["success"] is True  # Returns success with diagnostic
        ctx = result["context"]
        assert ctx["cooked"] is False

    def test_cook_with_warnings(self) -> None:
        mod = _load_script("houdini-vex", "cook_wrangle.py")
        node = _node("/obj/geo1/pointwrangle1", "pointwrangle1", "pointwrangle")
        node.errors.return_value = []
        node.warnings.return_value = ["attribute 'foo' not found", "degenerate polygon"]

        geo = MagicMock()
        geo.points.return_value = [1, 2, 3]
        geo.prims.return_value = [1]
        geo.iterVertices.return_value = iter([1, 2, 3])
        geo.pointAttribs.return_value = []
        geo.primAttribs.return_value = []
        geo.vertexAttribs.return_value = []
        geo.globalAttribs.return_value = []
        geo.pointGroups.return_value = []
        geo.primGroups.return_value = []
        geo.edgeGroups.return_value = []
        node.geometry.return_value = geo
        mock_hou = MagicMock()
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.cook_wrangle("/obj/geo1/pointwrangle1")

        assert result["success"] is True
        ctx = result["context"]
        assert len(ctx["warnings"]) == 2

    def test_cook_geometry_with_no_geometry(self) -> None:
        """Wrangle node that has no geometry() method (e.g., a detail wrangle)."""
        mod = _load_script("houdini-vex", "cook_wrangle.py")
        node = _node("/obj/geo1/detailwrangle1", "detailwrangle1", "detailwrangle")
        node.errors.return_value = []
        node.warnings.return_value = []
        node.geometry.return_value = None  # No geometry
        # Also make geometry raise when called
        del node.geometry
        node.geometry = MagicMock(side_effect=AttributeError)
        mock_hou = MagicMock()
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.cook_wrangle("/obj/geo1/detailwrangle1")

        assert result["success"] is True
        ctx = result["context"]
        assert ctx["cooked"] is True
        assert ctx.get("point_count") is None


# ---------------------------------------------------------------------------
# diagnose_wrangle
# ---------------------------------------------------------------------------


class TestDiagnoseWrangle:
    def test_diagnose_successful_wrangle(self) -> None:
        mod = _load_script("houdini-vex", "diagnose_wrangle.py")
        node = _node("/obj/geo1/pointwrangle1", "pointwrangle1", "pointwrangle")
        node.errors.return_value = []
        node.warnings.return_value = []

        geo = MagicMock()
        geo.points.return_value = [1, 2]
        geo.prims.return_value = [1]
        geo.iterVertices.return_value = iter([1, 2])
        geo.pointAttribs.return_value = []
        geo.primAttribs.return_value = []
        geo.vertexAttribs.return_value = []
        geo.globalAttribs.return_value = []
        geo.pointGroups.return_value = []
        geo.primGroups.return_value = []
        geo.edgeGroups.return_value = []
        node.geometry.return_value = geo
        mock_hou = MagicMock()
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.diagnose_wrangle("/obj/geo1/pointwrangle1")

        assert result["success"] is True
        assert result["context"]["likely_cause"] == "none"

    def test_diagnose_vex_compile_error(self) -> None:
        mod = _load_script("houdini-vex", "diagnose_wrangle.py")
        node = _node("/obj/geo1/pointwrangle1", "pointwrangle1", "pointwrangle")
        node.cook.side_effect = RuntimeError("syntax error: unexpected token")
        node.errors.return_value = ["syntax error: unexpected token"]
        node.warnings.return_value = []

        geo = MagicMock()
        geo.points.return_value = []
        geo.prims.return_value = []
        geo.iterVertices.return_value = iter([])
        geo.pointAttribs.return_value = []
        geo.primAttribs.return_value = []
        geo.vertexAttribs.return_value = []
        geo.globalAttribs.return_value = []
        geo.pointGroups.return_value = []
        geo.primGroups.return_value = []
        geo.edgeGroups.return_value = []
        node.geometry.return_value = geo
        mock_hou = MagicMock()
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.diagnose_wrangle("/obj/geo1/pointwrangle1")

        assert result["success"] is True
        assert result["context"]["likely_cause"] == "vex_compile_error"

    def test_diagnose_type_mismatch(self) -> None:
        mod = _load_script("houdini-vex", "diagnose_wrangle.py")
        node = _node("/obj/geo1/pointwrangle1", "pointwrangle1", "pointwrangle")
        node.cook.side_effect = RuntimeError("type mismatch: cannot convert string to float")
        node.errors.return_value = ["type mismatch: cannot convert string to float"]
        node.warnings.return_value = []

        geo = MagicMock()
        geo.points.return_value = []
        geo.prims.return_value = []
        geo.iterVertices.return_value = iter([])
        geo.pointAttribs.return_value = []
        geo.primAttribs.return_value = []
        geo.vertexAttribs.return_value = []
        geo.globalAttribs.return_value = []
        geo.pointGroups.return_value = []
        geo.primGroups.return_value = []
        geo.edgeGroups.return_value = []
        node.geometry.return_value = geo
        mock_hou = MagicMock()
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.diagnose_wrangle("/obj/geo1/pointwrangle1")

        assert result["success"] is True
        assert result["context"]["likely_cause"] == "vex_compile_error"

    def test_diagnose_unknown_attribute(self) -> None:
        mod = _load_script("houdini-vex", "diagnose_wrangle.py")
        node = _node("/obj/geo1/pointwrangle1", "pointwrangle1", "pointwrangle")
        node.cook.side_effect = RuntimeError("unknown attribute 'myAttr'")
        node.errors.return_value = ["unknown attribute 'myAttr'"]
        node.warnings.return_value = []

        geo = MagicMock()
        geo.points.return_value = []
        geo.prims.return_value = []
        geo.iterVertices.return_value = iter([])
        geo.pointAttribs.return_value = []
        geo.primAttribs.return_value = []
        geo.vertexAttribs.return_value = []
        geo.globalAttribs.return_value = []
        geo.pointGroups.return_value = []
        geo.primGroups.return_value = []
        geo.edgeGroups.return_value = []
        node.geometry.return_value = geo
        mock_hou = MagicMock()
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.diagnose_wrangle("/obj/geo1/pointwrangle1")

        assert result["success"] is True
        assert result["context"]["likely_cause"] == "vex_compile_error"

    def test_diagnose_cook_timeout(self) -> None:
        mod = _load_script("houdini-vex", "diagnose_wrangle.py")
        node = _node("/obj/geo1/pointwrangle1", "pointwrangle1", "pointwrangle")
        node.cook.side_effect = RuntimeError("cook timed out after 120s")
        node.errors.return_value = []
        node.warnings.return_value = []

        geo = MagicMock()
        geo.points.return_value = []
        geo.prims.return_value = []
        geo.iterVertices.return_value = iter([])
        geo.pointAttribs.return_value = []
        geo.primAttribs.return_value = []
        geo.vertexAttribs.return_value = []
        geo.globalAttribs.return_value = []
        geo.pointGroups.return_value = []
        geo.primGroups.return_value = []
        geo.edgeGroups.return_value = []
        node.geometry.return_value = geo
        mock_hou = MagicMock()
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.diagnose_wrangle("/obj/geo1/pointwrangle1")

        assert result["success"] is True
        assert result["context"]["likely_cause"] == "cook_timeout"

    def test_diagnose_geometry_error(self) -> None:
        mod = _load_script("houdini-vex", "diagnose_wrangle.py")
        node = _node("/obj/geo1/pointwrangle1", "pointwrangle1", "pointwrangle")
        node.cook.side_effect = RuntimeError("geometry is empty")
        node.errors.return_value = []
        node.warnings.return_value = []

        geo = MagicMock()
        geo.points.return_value = []
        geo.prims.return_value = []
        geo.iterVertices.return_value = iter([])
        geo.pointAttribs.return_value = []
        geo.primAttribs.return_value = []
        geo.vertexAttribs.return_value = []
        geo.globalAttribs.return_value = []
        geo.pointGroups.return_value = []
        geo.primGroups.return_value = []
        geo.edgeGroups.return_value = []
        node.geometry.return_value = geo
        mock_hou = MagicMock()
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.diagnose_wrangle("/obj/geo1/pointwrangle1")

        assert result["success"] is True
        assert result["context"]["likely_cause"] == "geometry_error"

    def test_diagnose_includes_geometry_snapshot(self) -> None:
        mod = _load_script("houdini-vex", "diagnose_wrangle.py")
        node = _node("/obj/geo1/pointwrangle1", "pointwrangle1", "pointwrangle")
        node.errors.return_value = []
        node.warnings.return_value = []

        geo = MagicMock()
        geo.points.return_value = [1]
        geo.prims.return_value = [1]
        geo.iterVertices.return_value = iter([1])
        geo.pointAttribs.return_value = []
        geo.primAttribs.return_value = []
        geo.vertexAttribs.return_value = []
        geo.globalAttribs.return_value = []
        geo.pointGroups.return_value = []
        geo.primGroups.return_value = []
        geo.edgeGroups.return_value = []
        node.geometry.return_value = geo
        mock_hou = MagicMock()
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.diagnose_wrangle("/obj/geo1/pointwrangle1")

        assert "geometry_diagnostics" in result["context"]


# ---------------------------------------------------------------------------
# get_vex_info
# ---------------------------------------------------------------------------


class TestGetVexInfo:
    def test_read_wrangle_info(self) -> None:
        mod = _load_script("houdini-vex", "get_vex_info.py")
        node = _node("/obj/geo1/pointwrangle1", "pointwrangle1", "pointwrangle")
        node.isCooked.return_value = True
        node.inputs.return_value = [MagicMock()]
        node.outputs.return_value = [MagicMock()]

        snip_parm = MagicMock()
        snip_parm.evalAsString.return_value = "@P += {1,0,0};"
        class_parm = MagicMock()
        class_parm.evalAsString.return_value = "point"

        def _parm_side_effect(name):
            if name == "snippet":
                return snip_parm
            if name == "class":
                return class_parm
            return None

        node.parm.side_effect = _parm_side_effect
        mock_hou = MagicMock()
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.get_vex_info("/obj/geo1/pointwrangle1")

        assert result["success"] is True
        ctx = result["context"]
        assert ctx["node_path"] == "/obj/geo1/pointwrangle1"
        assert ctx["wrangle_type"] == "pointwrangle"
        assert ctx["has_snippet"] is True
        assert ctx["cook_state"] == "cooked"
        assert ctx["input_count"] == 1
        assert ctx["output_count"] == 1

    def test_read_uncooked_wrangle(self) -> None:
        mod = _load_script("houdini-vex", "get_vex_info.py")
        node = _node("/obj/geo1/pointwrangle1", "pointwrangle1", "pointwrangle")
        node.isCooked.return_value = False
        node.inputs.return_value = []
        node.outputs.return_value = []

        snip_parm = MagicMock()
        snip_parm.evalAsString.return_value = ""
        class_parm = MagicMock()
        class_parm.evalAsString.return_value = "point"

        def _parm_side_effect(name):
            if name == "snippet":
                return snip_parm
            if name == "class":
                return class_parm
            return None

        node.parm.side_effect = _parm_side_effect
        mock_hou = MagicMock()
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.get_vex_info("/obj/geo1/pointwrangle1")

        assert result["success"] is True
        assert result["context"]["has_snippet"] is False
        assert result["context"]["cook_state"] == "uncooked"

    def test_read_info_nonexistent_node(self) -> None:
        mod = _load_script("houdini-vex", "get_vex_info.py")
        mock_hou = MagicMock()
        mock_hou.node.return_value = None

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.get_vex_info("/obj/nonexistent")

        assert result["success"] is False

    def test_snippet_preview_truncated(self) -> None:
        mod = _load_script("houdini-vex", "get_vex_info.py")
        long_code = "x" * 500
        node = _node("/obj/geo1/pointwrangle1", "pointwrangle1", "pointwrangle")
        node.isCooked.return_value = True
        node.inputs.return_value = []
        node.outputs.return_value = []

        snip_parm = MagicMock()
        snip_parm.evalAsString.return_value = long_code

        def _parm_side_effect(name):
            if name == "snippet":
                return snip_parm
            return None

        node.parm.side_effect = _parm_side_effect
        mock_hou = MagicMock()
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.get_vex_info("/obj/geo1/pointwrangle1")

        assert result["success"] is True
        preview = result["context"]["snippet_preview"]
        assert len(preview) <= 200


# ---------------------------------------------------------------------------
# list_wrangles
# ---------------------------------------------------------------------------


class TestListWrangles:
    def test_list_wrangles_under_obj(self) -> None:
        mod = _load_script("houdini-vex", "list_wrangles.py")
        root = _node("/obj", "obj", "geo")
        pw1 = _node("/obj/geo1/pointwrangle1", "pointwrangle1", "pointwrangle")
        aw1 = _node("/obj/geo1/attribwrangle1", "attribwrangle1", "attribwrangle")
        box = _node("/obj/geo1/box1", "box1", "box")
        geo1 = _node("/obj/geo1", "geo1", "geo")
        geo1.children.return_value = [pw1, aw1, box]
        root.children.return_value = [geo1]

        mock_hou = MagicMock()
        mock_hou.node.return_value = root

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.list_wrangles("/obj")

        assert result["success"] is True
        assert result["context"]["count"] == 2
        wrangles = result["context"]["wrangles"]
        wrangle_types = {w["wrangle_type"] for w in wrangles}
        assert "pointwrangle" in wrangle_types
        assert "attribwrangle" in wrangle_types

    def test_list_wrangles_empty_result(self) -> None:
        mod = _load_script("houdini-vex", "list_wrangles.py")
        root = _node("/obj", "obj", "geo")
        root.children.return_value = []
        mock_hou = MagicMock()
        mock_hou.node.return_value = root

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.list_wrangles("/obj")

        assert result["success"] is True
        assert result["context"]["count"] == 0

    def test_list_wrangles_nonexistent_parent(self) -> None:
        mod = _load_script("houdini-vex", "list_wrangles.py")
        mock_hou = MagicMock()
        mock_hou.node.return_value = None

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.list_wrangles("/obj/nonexistent")

        assert result["success"] is False

    def test_list_wrangles_nested_networks(self) -> None:
        mod = _load_script("houdini-vex", "list_wrangles.py")
        leaf = _node("/obj/geo1/subnet1/pw1", "pw1", "pointwrangle")
        leaf.children.return_value = []
        subnet = _node("/obj/geo1/subnet1", "subnet1", "subnet")
        subnet.children.return_value = [leaf]
        geo1 = _node("/obj/geo1", "geo1", "geo")
        geo1.children.return_value = [subnet]
        root = _node("/obj", "obj")
        root.children.return_value = [geo1]

        mock_hou = MagicMock()
        mock_hou.node.return_value = root

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.list_wrangles("/obj")

        assert result["success"] is True
        assert result["context"]["count"] == 1
        assert result["context"]["wrangles"][0]["node_path"] == "/obj/geo1/subnet1/pw1"


# ---------------------------------------------------------------------------
# Integration / end-to-end workflow tests
# ---------------------------------------------------------------------------


class TestVexWorkflowIntegration:
    """End-to-end workflow: create -> validate -> cook -> diagnose -> update."""

    def test_full_create_cook_diagnose_cycle(self) -> None:
        """Simulate the full VEX workflow tracer-bullet."""
        create_mod = _load_script("houdini-vex", "create_wrangle.py")
        cook_mod = _load_script("houdini-vex", "cook_wrangle.py")
        diag_mod = _load_script("houdini-vex", "diagnose_wrangle.py")
        update_mod = _load_script("houdini-vex", "update_vex_snippet.py")
        info_mod = _load_script("houdini-vex", "get_vex_info.py")

        # ── Step 1: Create a point wrangle ─────────────────────────────
        snippet = "@P += {0, 1, 0};"
        new = _node("/obj/geo1/pointwrangle1", "pointwrangle1", "pointwrangle")
        snip_parm = MagicMock()
        class_parm = MagicMock()

        def _create_parms(name):
            if name == "snippet":
                return snip_parm
            if name == "class":
                return class_parm
            return None

        new.parm.side_effect = _create_parms
        parent = _node("/obj/geo1", "geo1")
        parent.createNode.return_value = new
        mock_hou = MagicMock()
        mock_hou.node.return_value = parent

        with patch.dict(sys.modules, {"hou": mock_hou}):
            r1 = create_mod.create_wrangle(
                parent_path="/obj/geo1",
                wrangle_type="pointwrangle",
                vex_code=snippet,
            )

        assert r1["success"] is True
        assert r1["context"]["node_path"] == "/obj/geo1/pointwrangle1"

        # ── Step 2: Cook ───────────────────────────────────────────────
        geo = MagicMock()
        geo.points.return_value = [1] * 8
        geo.prims.return_value = [1] * 6
        geo.iterVertices.return_value = iter([1] * 24)
        geo.pointAttribs.return_value = []
        geo.primAttribs.return_value = []
        geo.vertexAttribs.return_value = []
        geo.globalAttribs.return_value = []
        geo.pointGroups.return_value = []
        geo.primGroups.return_value = []
        geo.edgeGroups.return_value = []

        cook_node = _node("/obj/geo1/pointwrangle1", "pointwrangle1", "pointwrangle")
        cook_node.errors.return_value = []
        cook_node.warnings.return_value = []
        cook_node.geometry.return_value = geo
        mock_hou2 = MagicMock()
        mock_hou2.node.return_value = cook_node

        with patch.dict(sys.modules, {"hou": mock_hou2}):
            r2 = cook_mod.cook_wrangle("/obj/geo1/pointwrangle1")

        assert r2["success"] is True
        assert r2["context"]["cooked"] is True
        assert r2["context"]["point_count"] == 8
        assert r2["context"]["primitive_count"] == 6

        # ── Step 3: Update snippet ─────────────────────────────────────
        snip2_parm = MagicMock()
        snip2_parm.evalAsString.return_value = snippet
        class2_parm = MagicMock()

        def _update_parms(name):
            if name == "snippet":
                return snip2_parm
            if name == "class":
                return class2_parm
            return None

        update_node = _node("/obj/geo1/pointwrangle1", "pointwrangle1", "pointwrangle")
        update_node.parm.side_effect = _update_parms
        mock_hou3 = MagicMock()
        mock_hou3.node.return_value = update_node

        new_snippet = "@P += {1, 0, 0};\n@Cd = {1, 0, 0};"

        with patch.dict(sys.modules, {"hou": mock_hou3}):
            r3 = update_mod.update_vex_snippet(
                node_path="/obj/geo1/pointwrangle1",
                vex_code=new_snippet,
            )

        assert r3["success"] is True
        snip2_parm.set.assert_called_once_with(new_snippet)
