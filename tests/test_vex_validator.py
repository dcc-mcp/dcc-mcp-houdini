"""Unit tests for VEX validator — no Houdini dependency."""

from __future__ import annotations

from dcc_mcp_houdini._vex_types import VexSeverity, WrangleType
from dcc_mcp_houdini._vex_validator import (
    validate_attribute_bindings,
    validate_vex_snippet_client,
    validate_wrangle_parameters,
)

# ---------------------------------------------------------------------------
# validate_vex_snippet_client — allowlist
# ---------------------------------------------------------------------------


class TestValidateVexSnippetClient:
    def test_empty_snippet_rejected(self) -> None:
        errors = validate_vex_snippet_client("")
        assert len(errors) == 1
        assert "empty" in errors[0].message.lower()

    def test_whitespace_only_rejected(self) -> None:
        errors = validate_vex_snippet_client("   \n  \t  ")
        assert len(errors) == 1

    def test_valid_simple_snippet(self) -> None:
        errors = validate_vex_snippet_client("@P += {1, 0, 0};")
        assert len(errors) == 0

    def test_valid_multi_line_snippet(self) -> None:
        snippet = """// Move points up
vector offset = {0, 1, 0};
@P += offset;
@Cd = {1, 0, 0};
"""
        errors = validate_vex_snippet_client(snippet)
        assert len(errors) == 0

    def test_valid_with_if_statement(self) -> None:
        snippet = """if (@P.y > 0) {
    @Cd = {1, 0, 0};
} else {
    @Cd = {0, 0, 1};
}"""
        errors = validate_vex_snippet_client(snippet)
        assert len(errors) == 0

    def test_valid_with_for_loop(self) -> None:
        snippet = """int i;
for (i = 0; i < @numpt; i++) {
    setpointattrib(0, "Cd", i, {1, 0, 0});
}"""
        errors = validate_vex_snippet_client(snippet)
        assert len(errors) == 0

    def test_valid_with_functions(self) -> None:
        snippet = """vector n = normalize(@N);
float d = dot(n, {0, 1, 0});
@P.y += d * 0.5;"""
        errors = validate_vex_snippet_client(snippet)
        assert len(errors) == 0

    def test_valid_with_noise(self) -> None:
        snippet = """float n = noise(@P * 0.1);
@P.y += n;
@Cd = snoise(@P);"""
        errors = validate_vex_snippet_client(snippet)
        assert len(errors) == 0

    def test_valid_volume_wrangle(self) -> None:
        snippet = """@density = rand(@P);
@temperature = fit(@density, 0, 1, 0, 100);"""
        errors = validate_vex_snippet_client(snippet)
        assert len(errors) == 0

    def test_valid_with_comments(self) -> None:
        snippet = """/* Block comment */
// Line comment
@P += 1;  // Inline comment
"""
        errors = validate_vex_snippet_client(snippet)
        assert len(errors) == 0

    def test_topology_functions_require_topology_wrangle(self) -> None:
        snippet = 'int point = addpoint(0, {0, 0, 0}); int prim = addprim(0, "poly"); addvertex(0, prim, point);'
        assert validate_vex_snippet_client(snippet)
        assert validate_vex_snippet_client(snippet, WrangleType.TOPOLOGY_WRANGLE) == []


# ---------------------------------------------------------------------------
# validate_vex_snippet_client — deny list
# ---------------------------------------------------------------------------


class TestValidateVexSnippetDenyList:
    def test_python_blocked(self) -> None:
        errors = validate_vex_snippet_client("python { @P += 1; }")
        assert len(errors) >= 1
        assert any("python" in e.message.lower() for e in errors)

    def test_exec_blocked(self) -> None:
        errors = validate_vex_snippet_client("exec('something')")
        assert len(errors) >= 1
        assert any("exec" in e.message.lower() for e in errors)

    def test_eval_blocked(self) -> None:
        errors = validate_vex_snippet_client("eval(@P)")
        assert len(errors) >= 1
        assert any("eval" in e.message.lower() for e in errors)

    def test_import_blocked(self) -> None:
        errors = validate_vex_snippet_client("import something")
        assert len(errors) >= 1
        assert any("import" in e.message.lower() for e in errors)

    def test_subprocess_blocked(self) -> None:
        errors = validate_vex_snippet_client("subprocess.call('ls')")
        assert len(errors) >= 1

    def test_os_access_blocked(self) -> None:
        errors = validate_vex_snippet_client("os.system('ls')")
        assert len(errors) >= 1

    def test_sys_access_blocked(self) -> None:
        errors = validate_vex_snippet_client("sys.exit(1)")
        assert len(errors) >= 1

    def test_hou_access_blocked(self) -> None:
        errors = validate_vex_snippet_client("hou.node('/obj')")
        assert len(errors) >= 1

    def test_dunder_blocked(self) -> None:
        errors = validate_vex_snippet_client("__import__('os')")
        assert len(errors) >= 1

    def test_unicode_escape_blocked(self) -> None:
        errors = validate_vex_snippet_client("@P += \\x41;")
        assert len(errors) >= 1

    def test_system_call_blocked(self) -> None:
        errors = validate_vex_snippet_client('run("calc.exe")')
        assert len(errors) >= 1

    def test_popen_blocked(self) -> None:
        errors = validate_vex_snippet_client("popen('cmd')")
        assert len(errors) >= 1

    def test_non_ascii_blocked(self) -> None:
        # Unicode homoglyph attack
        errors = validate_vex_snippet_client("@P += 1; // 你好")
        assert len(errors) >= 1


# ---------------------------------------------------------------------------
# validate_wrangle_parameters
# ---------------------------------------------------------------------------


class TestValidateWrangleParameters:
    def test_valid_known_parameters(self) -> None:
        errors = validate_wrangle_parameters(
            WrangleType.ATTRIB_WRANGLE,
            {"snippet": "// code", "group": "group1"},
        )
        assert len(errors) == 0

    def test_unknown_parameter_is_reported(self) -> None:
        errors = validate_wrangle_parameters(
            WrangleType.ATTRIB_WRANGLE,
            {"bogus_parm": 42},
        )
        assert len(errors) >= 1
        assert any("bogus_parm" in e for e in errors)

    def test_wrong_type_is_reported(self) -> None:
        errors = validate_wrangle_parameters(
            WrangleType.ATTRIB_WRANGLE,
            {"snippet": 123},  # Should be str
        )
        assert len(errors) >= 1

    def test_empty_parameters_is_valid(self) -> None:
        errors = validate_wrangle_parameters(WrangleType.ATTRIB_WRANGLE, {})
        assert len(errors) == 0

    def test_point_wrangle_accepts_snippet(self) -> None:
        errors = validate_wrangle_parameters(
            WrangleType.POINT_WRANGLE,
            {"snippet": "@P += 1;"},
        )
        assert len(errors) == 0


# ---------------------------------------------------------------------------
# validate_attribute_bindings
# ---------------------------------------------------------------------------


class TestValidateAttributeBindings:
    def test_builtin_attributes_not_flagged(self) -> None:
        errors = validate_attribute_bindings("@P += 1; @Cd = {1,0,0}; @N = {0,1,0};", [])
        assert len(errors) == 0

    def test_unknown_attribute_flagged_as_warning(self) -> None:
        errors = validate_attribute_bindings("@myCustomAttr = 1.0;", [])
        assert len(errors) >= 1
        assert errors[0].severity == VexSeverity.WARNING
        assert "myCustomAttr" in errors[0].message

    def test_known_user_attribute_not_flagged(self) -> None:
        errors = validate_attribute_bindings("@myAttr = 1.0;", ["myAttr"])
        assert len(errors) == 0

    def test_multiple_unknown_attributes(self) -> None:
        errors = validate_attribute_bindings("@foo = 1; @bar = 2;", [])
        assert len(errors) == 2

    def test_ptnum_not_flagged(self) -> None:
        errors = validate_attribute_bindings("@ptnum", [])
        assert len(errors) == 0

    def test_Time_not_flagged(self) -> None:
        errors = validate_attribute_bindings("@Time", [])
        assert len(errors) == 0

    def test_line_extraction_in_errors(self) -> None:
        snippet = "// header\n@unknownAttr = 1.0;\n@P += 1;"
        errors = validate_attribute_bindings(snippet, [])
        assert len(errors) >= 1
        # Should have line context
        assert errors[0].line is not None
        assert "unknownAttr" in errors[0].message
