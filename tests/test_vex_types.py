"""Unit tests for VEX types — no Houdini dependency."""

from __future__ import annotations

import pytest

from dcc_mcp_houdini._vex_types import (
    CookDiagnostic,
    VexContext,
    VexSeverity,
    VexSnippet,
    VexSyntaxError,
    WrangleInfo,
    WrangleNodeSpec,
    WrangleType,
)


# ---------------------------------------------------------------------------
# VexContext
# ---------------------------------------------------------------------------


class TestVexContext:
    def test_all_contexts_are_valid_strings(self) -> None:
        for ctx in VexContext:
            assert isinstance(ctx.value, str)
            assert ctx.value

    def test_context_map_to_known_values(self) -> None:
        assert VexContext.POINTS.value == "points"
        assert VexContext.PRIMITIVES.value == "prims"
        assert VexContext.VERTICES.value == "verts"
        assert VexContext.DETAIL.value == "detail"


# ---------------------------------------------------------------------------
# WrangleType
# ---------------------------------------------------------------------------


class TestWrangleType:
    def test_default_for_context_returns_correct_type(self) -> None:
        assert WrangleType.default_for_context(VexContext.POINTS) == WrangleType.POINT_WRANGLE
        assert WrangleType.default_for_context(VexContext.PRIMITIVES) == WrangleType.PRIMITIVE_WRANGLE
        assert WrangleType.default_for_context(VexContext.VERTICES) == WrangleType.VERTEX_WRANGLE
        assert WrangleType.default_for_context(VexContext.DETAIL) == WrangleType.DETAIL_WRANGLE

    def test_default_for_context_falls_back_to_attribwrangle(self) -> None:
        assert WrangleType.default_for_context(VexContext.GLOBAL_VERTICES) == WrangleType.ATTRIB_WRANGLE

    def test_all_wrangle_types_have_nonempty_values(self) -> None:
        for wt in WrangleType:
            assert wt.value
            assert "wrangle" in wt.value or "vop" in wt.value


# ---------------------------------------------------------------------------
# VexSyntaxError
# ---------------------------------------------------------------------------


class TestVexSyntaxError:
    def test_basic_error_to_dict(self) -> None:
        err = VexSyntaxError(message="syntax error", severity=VexSeverity.ERROR)
        d = err.to_dict()
        assert d["message"] == "syntax error"
        assert d["severity"] == "error"
        assert "line" not in d

    def test_error_with_location_to_dict(self) -> None:
        err = VexSyntaxError(
            message="type mismatch",
            severity=VexSeverity.ERROR,
            line=5,
            column=12,
            snippet_context="float x = 'hello';",
        )
        d = err.to_dict()
        assert d["line"] == 5
        assert d["column"] == 12
        assert d["snippet_context"] == "float x = 'hello';"


# ---------------------------------------------------------------------------
# VexSnippet
# ---------------------------------------------------------------------------


class TestVexSnippet:
    def test_valid_snippet_construction(self) -> None:
        snip = VexSnippet(code="@P += {1,0,0};", context=VexContext.POINTS)
        assert snip.code == "@P += {1,0,0};"
        assert snip.context == VexContext.POINTS
        assert snip.bindings == {}
        assert snip.parameter_values == {}

    def test_empty_snippet_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            VexSnippet(code="", context=VexContext.POINTS)

    def test_whitespace_only_snippet_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            VexSnippet(code="   \n  ", context=VexContext.POINTS)

    def test_invalid_context_raises(self) -> None:
        with pytest.raises(ValueError):
            VexSnippet(code="@P += 1;", context="invalid")  # type: ignore

    def test_line_count(self) -> None:
        snip = VexSnippet(code="@P += 1;\n@Cd = {1,0,0};\n", context=VexContext.POINTS)
        assert snip.line_count == 2

    def test_line_count_excludes_empty_lines(self) -> None:
        snip = VexSnippet(code="@P += 1;\n\n\n@Cd = {1,0,0};\n", context=VexContext.POINTS)
        assert snip.line_count == 2

    def test_with_bindings(self) -> None:
        snip = VexSnippet(
            code="@pos = @P;",
            context=VexContext.POINTS,
            bindings={"pos": "vector"},
        )
        assert snip.bindings == {"pos": "vector"}

    def test_frozen_after_construction(self) -> None:
        snip = VexSnippet(code="@P += 1;", context=VexContext.POINTS)
        with pytest.raises(Exception):
            snip.code = "@Cd += 1;"  # type: ignore


# ---------------------------------------------------------------------------
# WrangleNodeSpec
# ---------------------------------------------------------------------------


class TestWrangleNodeSpec:
    def test_minimal_spec(self) -> None:
        spec = WrangleNodeSpec(parent_path="/obj/geo1")
        assert spec.parent_path == "/obj/geo1"
        assert spec.node_name is None
        assert spec.wrangle_type == WrangleType.ATTRIB_WRANGLE
        assert spec.run_over == VexContext.POINTS
        assert spec.snippet is None

    def test_full_spec(self) -> None:
        snip = VexSnippet(code="@P += 1;", context=VexContext.POINTS)
        spec = WrangleNodeSpec(
            parent_path="/obj/geo1",
            node_name="myWrangle",
            wrangle_type=WrangleType.POINT_WRANGLE,
            run_over=VexContext.POINTS,
            snippet=snip,
            set_display=True,
            set_render=False,
        )
        assert spec.node_name == "myWrangle"
        assert spec.wrangle_type == WrangleType.POINT_WRANGLE
        assert spec.snippet is snip
        assert spec.set_display is True
        assert spec.set_render is False

    def test_empty_parent_path_raises(self) -> None:
        with pytest.raises(ValueError, match="parent_path"):
            WrangleNodeSpec(parent_path="")

    def test_invalid_wrangle_type_raises(self) -> None:
        with pytest.raises(ValueError):
            WrangleNodeSpec(parent_path="/obj/geo1", wrangle_type="bogus")  # type: ignore

    def test_invalid_snippet_type_raises(self) -> None:
        with pytest.raises(ValueError):
            WrangleNodeSpec(parent_path="/obj/geo1", snippet="not a VexSnippet")  # type: ignore


# ---------------------------------------------------------------------------
# CookDiagnostic
# ---------------------------------------------------------------------------


class TestCookDiagnostic:
    def test_successful_cook_to_dict(self) -> None:
        diag = CookDiagnostic(
            node_path="/obj/geo1/pointwrangle1",
            cooked=True,
            point_count=42,
            primitive_count=10,
            vertex_count=84,
            attribute_names=["P", "Cd", "N"],
            group_names=["group1"],
            elapsed_secs=0.123,
        )
        d = diag.to_dict()
        assert d["cooked"] is True
        assert d["point_count"] == 42
        assert d["vertex_count"] == 84
        assert "Cd" in d["attribute_names"]

    def test_failed_cook_to_dict(self) -> None:
        diag = CookDiagnostic(
            node_path="/obj/geo1/pointwrangle1",
            cooked=False,
            cook_error="syntax error on line 3",
            errors=["syntax error on line 3"],
            warnings=[],
            elapsed_secs=0.001,
        )
        d = diag.to_dict()
        assert d["cooked"] is False
        assert d["cook_error"] == "syntax error on line 3"
        assert d["errors"] == ["syntax error on line 3"]


# ---------------------------------------------------------------------------
# WrangleInfo
# ---------------------------------------------------------------------------


class TestWrangleInfo:
    def test_info_to_dict(self) -> None:
        info = WrangleInfo(
            node_path="/obj/geo1/pointwrangle1",
            node_name="pointwrangle1",
            wrangle_type="pointwrangle",
            run_over="points",
            snippet_preview="@P += {1,0,0};",
            has_snippet=True,
            cook_state="cooked",
            input_count=1,
            output_count=1,
        )
        d = info.to_dict()
        assert d["node_path"] == "/obj/geo1/pointwrangle1"
        assert d["wrangle_type"] == "pointwrangle"
        assert d["has_snippet"] is True
        assert d["cook_state"] == "cooked"


# ---------------------------------------------------------------------------
# vex_context_to_attrib_class
# ---------------------------------------------------------------------------


class TestVexContextToAttribClass:
    def test_points_maps_to_0(self) -> None:
        from dcc_mcp_houdini._vex_types import vex_context_to_attrib_class

        assert vex_context_to_attrib_class(VexContext.POINTS) == 0

    def test_primitives_maps_to_1(self) -> None:
        from dcc_mcp_houdini._vex_types import vex_context_to_attrib_class

        assert vex_context_to_attrib_class(VexContext.PRIMITIVES) == 1

    def test_vertices_maps_to_2(self) -> None:
        from dcc_mcp_houdini._vex_types import vex_context_to_attrib_class

        assert vex_context_to_attrib_class(VexContext.VERTICES) == 2

    def test_detail_maps_to_3(self) -> None:
        from dcc_mcp_houdini._vex_types import vex_context_to_attrib_class

        assert vex_context_to_attrib_class(VexContext.DETAIL) == 3
