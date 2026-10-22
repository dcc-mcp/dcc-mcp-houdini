"""Guard the Husk acceptance fixture's RenderVar AOV token contract.

``.github/scripts/run_houdini_husk_acceptance.py`` authors a RenderVar directly
in USD. On Houdini 20.5.x husk rejects the deprecated ``driver:parameters:aov:husk:*``
namespace with ``Missing driver:parameters:aov:name token`` and exits before any
EXR is written, so the fixture's zero-exit precondition silently fails. These
tests parse the fixture (no Houdini host required) and assert it authors the
generic Karma-canonical ``driver:parameters:aov:*`` tokens instead.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / ".github" / "scripts" / "run_houdini_husk_acceptance.py"
DEPRECATED_PREFIX = "driver:parameters:aov:husk:"


def _first_string_arg(call: ast.Call):
    if call.args and isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str):
        return call.args[0].value
    return None


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


@pytest.fixture(scope="module")
def fixture_tree() -> ast.AST:
    assert FIXTURE.is_file(), "husk acceptance fixture is missing: {}".format(FIXTURE)
    return ast.parse(FIXTURE.read_text(encoding="utf-8"), filename=str(FIXTURE))


def test_fixture_does_not_author_deprecated_husk_aov_tokens(fixture_tree: ast.AST) -> None:
    deprecated = {name for name in _authored_attribute_names(fixture_tree) if name.startswith(DEPRECATED_PREFIX)}
    assert deprecated == set(), "fixture still authors deprecated tokens: {}".format(sorted(deprecated))


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
