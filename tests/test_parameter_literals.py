"""Literal skill values must not modify another parameter through a reference."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from skill_loader import skill_script_import_context

from dcc_mcp_houdini.api import set_parm_value


class ReferencingParm:
    def __init__(self, value, reference=None):
        self.value = value
        self.reference = reference

    def set(self, value, *, follow_parm_reference=True):
        if follow_parm_reference and self.reference is not None:
            self.reference.set(value)
        else:
            self.value = value
            self.reference = None

    def eval(self):
        return self.reference.eval() if self.reference is not None else self.value


class ReferencingTuple:
    def __init__(self, parms):
        self.parms = parms

    def __len__(self):
        return len(self.parms)

    def __iter__(self):
        return iter(self.parms)

    def set(self, values, *, follow_parm_references=True):
        # Native H22 ignores this flag for numeric tuple literals.
        for parm, value in zip(self.parms, values):
            parm.set(value)


class Node:
    def __init__(self, scalar=None, tuple_parm=None):
        self.scalar = scalar
        self.tuple_parm = tuple_parm

    def parm(self, name):
        return self.scalar if name == "shrink" else None

    def parmTuple(self, name):
        return self.tuple_parm if name == "t" else None

    def path(self):
        return "/obj/test"


@pytest.mark.parametrize(
    "skill,filename",
    [
        ("automation", "_automation_common.py"),
        ("nodes", "_node_common.py"),
        ("hda", "_hda_common.py"),
        ("materials", "_material_common.py"),
    ],
)
def test_skill_helpers_preserve_reference_drivers(skill, filename):
    path = Path(__file__).parents[1] / "src/dcc_mcp_houdini/skills" / ("houdini-" + skill) / "scripts" / filename
    spec = importlib.util.spec_from_file_location("literal_helper_" + skill, path)
    module = importlib.util.module_from_spec(spec)
    with skill_script_import_context(spec):
        spec.loader.exec_module(module)
    driver = ReferencingParm(4.0)
    scalar = ReferencingParm(None, driver)
    parms = [ReferencingParm(None, driver) for _ in range(3)]
    node = Node(scalar, ReferencingTuple(parms))
    module.set_parm_value(node, "shrink", 2.5)
    module.set_parm_value(node, "t", [1, 2, 3])
    assert driver.eval() == 4.0
    assert scalar.eval() == 2.5
    assert [parm.eval() for parm in parms] == [1, 2, 3]


def test_scalar_literal_leaves_referenced_driver_unchanged():
    margin = ReferencingParm(0.001)
    shrink = ReferencingParm(None, margin)
    set_parm_value(Node(scalar=shrink), "shrink", 0.0015)
    assert margin.value == 0.001
    assert shrink.value == 0.0015
    assert shrink.reference is None


def test_tuple_literal_leaves_all_referenced_drivers_unchanged():
    drivers = [ReferencingParm(value) for value in (4, 5, 6)]
    parms = [ReferencingParm(None, driver) for driver in drivers]
    set_parm_value(Node(tuple_parm=ReferencingTuple(parms)), "t", [1, 2, 3])
    assert [parm.value for parm in parms] == [1, 2, 3]
    assert [driver.value for driver in drivers] == [4, 5, 6]


def test_missing_parameter_remains_an_error():
    with pytest.raises(ValueError, match="Parameter 'missing' not found on /obj/test"):
        set_parm_value(Node(), "missing", 1)


def test_tuple_length_is_checked_before_any_write():
    parms = [ReferencingParm(value) for value in (4, 5, 6)]
    with pytest.raises(ValueError, match="requires 3 values"):
        set_parm_value(Node(tuple_parm=ReferencingTuple(parms)), "t", [1, 2])
    assert [parm.value for parm in parms] == [4, 5, 6]


@pytest.mark.parametrize(
    "skill,filename",
    [("lookdev", "_lookdev_common.py"), ("material-library", "_library_common.py")],
)
def test_coercing_helpers_preserve_reference_drivers(skill, filename):
    path = Path(__file__).parents[1] / "src/dcc_mcp_houdini/skills" / ("houdini-" + skill) / "scripts" / filename
    spec = importlib.util.spec_from_file_location("literal_coercion_" + skill, path)
    module = importlib.util.module_from_spec(spec)
    with skill_script_import_context(spec):
        spec.loader.exec_module(module)
    driver = ReferencingParm(4.0)
    scalar = ReferencingParm(None, driver)
    parms = [ReferencingParm(None, driver) for _ in range(3)]
    node = Node(scalar, ReferencingTuple(parms))
    if skill == "lookdev":
        applied, errors = module.set_parameters(node, {"shrink": "2.5", "t": [1, 2, 3]})
        assert applied == {"shrink": 2.5, "t": [1, 2, 3]}
        assert not errors
    else:
        assert module.set_node_parameter(node, "shrink", "2.5") == 2.5
        assert module.set_node_parameter(node, "t", [1, 2, 3]) == [1, 2, 3]
    assert driver.eval() == 4.0
    assert scalar.eval() == 2.5
    assert [parm.eval() for parm in parms] == [1, 2, 3]
