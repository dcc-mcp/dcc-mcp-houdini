"""Guard the Husk acceptance fixture's RenderVar AOV token contract.

``.github/scripts/run_houdini_husk_acceptance.py`` authors a RenderVar directly
in USD. On Houdini 20.5.x husk rejects the deprecated ``driver:parameters:aov:husk:*``
namespace with ``Missing driver:parameters:aov:name token`` and exits before any
EXR is written, so the fixture's zero-exit precondition silently fails. These
tests parse the fixture (no Houdini host required) and assert it authors the
generic Karma-canonical ``driver:parameters:aov:*`` tokens instead.

``ast.parse`` builds string literals as ``ast.Constant`` (``.value``) on Python
3.8+ but as the dedicated ``ast.Str`` node (``.s``) on Python 3.7, which this
project still supports. Every guard below therefore runs against both node
shapes: an ``ast.Constant``-only helper would silently return ``None`` on 3.7
and turn the guards into a no-op there.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / ".github" / "scripts" / "run_houdini_husk_acceptance.py"
DEPRECATED_PREFIX = "driver:parameters:aov:husk:"

# ``ast.Constant`` is the unified literal node on 3.8+. Resolve it lazily: a
# missing name (very old builds) yields an empty tuple, for which isinstance()
# is always False, so those builds fall through to the ast.Str branch below.
_AST_CONSTANT = getattr(ast, "Constant", ())


class _LegacyStr(ast.AST):
    """Faithful stand-in for Python 3.7's ``ast.Str`` literal node.

    On 3.7 ``ast.parse`` emits dedicated string nodes that expose the text in
    ``.s``, are *not* ``ast.Constant``, and have no ``.value``. ``ast.Str``
    itself is deprecated on 3.12+ and removed on 3.14, so this node reproduces
    exactly the discriminating attributes the guards depend on, letting the
    3.7 code path be exercised on any modern interpreter.
    """

    _fields = ("s",)


def _parse_like_py37(source: str, filename: str = "<string>") -> ast.AST:
    """Parse *source*, rewriting string ``ast.Constant`` nodes as 3.7 ``Str``-shaped nodes."""
    tree = ast.parse(source, filename=filename)

    class _ToLegacyStr(ast.NodeTransformer):
        def visit_Constant(self, node):
            if isinstance(node.value, str):
                legacy = _LegacyStr()
                legacy.s = node.value
                return legacy
            return node

    return ast.fix_missing_locations(_ToLegacyStr().visit(tree))


def _parse_modern(source: str, filename: str = "<string>") -> ast.AST:
    return ast.parse(source, filename=filename)


def _first_string_arg(call: ast.Call):
    """Return the first argument of *call* when it is a string literal, else None.

    Covers both ``ast.Constant`` (Python 3.8+) and the dedicated ``ast.Str``
    node (Python 3.7, still supported). Handle ``ast.Constant`` first and
    return before reading ``.s`` so the deprecated compatibility property is
    never touched on 3.12+/3.14.
    """
    if not call.args:
        return None
    node = call.args[0]
    if isinstance(node, _AST_CONSTANT):
        return node.value if isinstance(node.value, str) else None
    legacy = getattr(node, "s", None)
    return legacy if isinstance(legacy, str) else None


def _calls_named(tree: ast.AST, attr_name: str):
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == attr_name:
            yield node


def _authored_attribute_names(tree: ast.AST):
    names = set()
    for call in _calls_named(tree, "CreateAttribute"):
        name = _first_string_arg(call)
        if name is not None:
            names.add(name)
    return names


def _applied_schemas(tree: ast.AST):
    schemas = set()
    for call in _calls_named(tree, "AddAppliedSchema"):
        schema = _first_string_arg(call)
        if schema is not None:
            schemas.add(schema)
    return schemas


def _set_value_for_attribute(tree: ast.AST, attribute_name: str):
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "Set"):
            continue
        target = node.func.value
        if not (
            isinstance(target, ast.Call)
            and isinstance(target.func, ast.Attribute)
            and target.func.attr == "CreateAttribute"
        ):
            continue
        if _first_string_arg(target) == attribute_name:
            return _first_string_arg(node)
    return None


def _assert_no_deprecated(tree: ast.AST) -> None:
    deprecated = {name for name in _authored_attribute_names(tree) if name.startswith(DEPRECATED_PREFIX)}
    assert deprecated == set(), "fixture still authors deprecated tokens: {}".format(sorted(deprecated))


@pytest.fixture(params=[_parse_modern, _parse_like_py37], ids=["py38-Constant", "py37-ast.Str"])
def ast_parser(request):
    """Parse the fixture with both modern and Python 3.7 literal node shapes."""
    return request.param


@pytest.fixture
def fixture_tree(ast_parser) -> ast.AST:
    assert FIXTURE.is_file(), "husk acceptance fixture is missing: {}".format(FIXTURE)
    return ast_parser(FIXTURE.read_text(encoding="utf-8"), str(FIXTURE))


# A deliberately regressed RenderVar that authors the deprecated husk
# namespace instead of the generic Karma-canonical tokens.
_REGRESSED_SOURCE = """
var.GetPrim().AddAppliedSchema("HuskRenderVarAPI")
var.GetPrim().CreateAttribute("driver:parameters:aov:husk:format", Sdf.ValueTypeNames.String).Set("color4f")
var.GetPrim().CreateAttribute("driver:parameters:aov:husk:name", Sdf.ValueTypeNames.String).Set("C")
"""


def test_first_string_arg_accepts_constant_and_legacy_str() -> None:
    modern = _parse_modern('f("value")').body[0].value
    legacy = _parse_like_py37('f("value")').body[0].value
    assert _first_string_arg(modern) == "value"  # ast.Constant (3.8+)
    assert _first_string_arg(legacy) == "value"  # ast.Str-shaped (3.7)
    assert _first_string_arg(_parse_modern("f(42)").body[0].value) is None
    assert _first_string_arg(_parse_modern("f()").body[0].value) is None


def test_fixture_does_not_author_deprecated_husk_aov_tokens(fixture_tree: ast.AST) -> None:
    _assert_no_deprecated(fixture_tree)


def test_fixture_authors_generic_aov_name_and_format(fixture_tree: ast.AST) -> None:
    names = _authored_attribute_names(fixture_tree)
    assert "driver:parameters:aov:name" in names
    assert "driver:parameters:aov:format" in names


def test_fixture_applies_karma_and_husk_render_var_api(fixture_tree: ast.AST) -> None:
    schemas = _applied_schemas(fixture_tree)
    assert "KarmaRenderVarAPI" in schemas
    assert "HuskRenderVarAPI" in schemas


def test_fixture_uses_karma_canonical_aov_values(fixture_tree: ast.AST) -> None:
    assert _set_value_for_attribute(fixture_tree, "driver:parameters:aov:name") == "C"
    # Karma writes color AOVs as half-float in EXR; color4h is the canonical value.
    assert _set_value_for_attribute(fixture_tree, "driver:parameters:aov:format") == "color4h"


def test_deprecated_token_regression_is_detected(ast_parser) -> None:
    """The guard must FAIL, not pass vacuously, when the fixture reverts to old tokens.

    With a Python 3.7 ``ast.Str``-shaped tree, an ``ast.Constant``-only helper
    collects no attribute names at all, so ``_assert_no_deprecated`` would pass
    even though deprecated tokens are present. This counter-example proves the
    guard still rejects a regressed fixture in both node regimes.
    """
    tree = ast_parser(_REGRESSED_SOURCE, "<regressed>")
    deprecated = {name for name in _authored_attribute_names(tree) if name.startswith(DEPRECATED_PREFIX)}
    assert deprecated, "regressed fixture authored deprecated tokens but none were detected"
    with pytest.raises(AssertionError):
        _assert_no_deprecated(tree)
