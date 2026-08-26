"""Public-contract tests for Houdini's typed modeling vocabulary."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import pytest
import yaml
from skill_loader import skill_script_import_context

_SKILL_ROOT = Path(__file__).parents[1] / "src" / "dcc_mcp_houdini" / "skills" / "houdini-mesh-ops"


def _load_skill_script(skill: str, name: str) -> ModuleType:
    path = _SKILL_ROOT.parent / skill / "scripts" / name
    spec = importlib.util.spec_from_file_location("typed_modeling_{}".format(path.stem), path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    with skill_script_import_context(spec):
        spec.loader.exec_module(module)
    return module


def _load_script(name: str) -> ModuleType:
    return _load_skill_script("houdini-mesh-ops", name)


class _Type:
    def __init__(self, name: str) -> None:
        self._name = name

    def name(self) -> str:
        return self._name


class _Parm:
    def __init__(self, menu_items=None, menu_labels=None) -> None:
        self.value = None
        self._menu_items = tuple(menu_items or ())
        self._menu_labels = tuple(menu_labels or ())

    def set(self, value) -> None:
        self.value = value

    def eval(self):
        return self.value

    def evalAsString(self) -> str:
        return str(self.value)

    def menuItems(self):
        return self._menu_items

    def menuLabels(self):
        return self._menu_labels


class _ParmTuple:
    def __init__(self, value=(0.0, 0.0, 0.0)) -> None:
        self.value = tuple(value)

    def set(self, value) -> None:
        self.value = tuple(value)

    def eval(self):
        return self.value


class _Bounds:
    def __init__(self, minimum, maximum) -> None:
        self._minimum = minimum
        self._maximum = maximum

    def minvec(self):
        return self._minimum

    def maxvec(self):
        return self._maximum

    def sizevec(self):
        return tuple(self._maximum[index] - self._minimum[index] for index in range(3))


class _Attrib:
    def __init__(self, size: int) -> None:
        self._size = size

    def size(self) -> int:
        return self._size


class _Geometry:
    def __init__(
        self,
        points: int,
        primitives: int,
        vertices: int,
        minimum,
        maximum,
        attributes=(),
        point_float_attributes=None,
        point_int_attributes=None,
    ) -> None:
        self._points = points
        self._primitives = primitives
        self._vertices = vertices
        self._bounds = _Bounds(minimum, maximum)
        self._attributes = set(attributes)
        self._point_float_attributes = dict(point_float_attributes or {})
        self._point_int_attributes = dict(point_int_attributes or {})

    def pointCount(self) -> int:
        return self._points

    def primCount(self) -> int:
        return self._primitives

    def vertexCount(self) -> int:
        return self._vertices

    def boundingBox(self) -> _Bounds:
        return self._bounds

    def findVertexAttrib(self, name: str):
        return object() if name in self._attributes else None

    def findPointAttrib(self, name: str):
        values = self._point_float_attributes.get(name)
        if values:
            return _Attrib(len(values[0]))
        if name in self._point_int_attributes:
            return _Attrib(1)
        return None

    def pointFloatAttribValues(self, name: str):
        return tuple(component for value in self._point_float_attributes[name] for component in value)

    def pointIntAttribValues(self, name: str):
        return tuple(self._point_int_attributes[name])


class _Node:
    def __init__(self, path: str, type_name: str, geometry: _Geometry, max_inputs=None) -> None:
        self._path = path
        self._type = _Type(type_name)
        self._geometry = geometry
        self._parent = None
        self._inputs = {}
        self._parms = {}
        self._parm_tuples = {}
        self.created = []
        self.destroyed = False
        self.destroy_calls = 0
        self._max_inputs = max_inputs
        self._fail_input_index = None

    def path(self) -> str:
        return self._path

    def name(self) -> str:
        return self._path.rsplit("/", 1)[-1]

    def type(self) -> _Type:
        return self._type

    def geometry(self) -> _Geometry:
        return self._geometry

    def parent(self):
        return self._parent

    def createNode(self, type_name: str, node_name=None):
        path = "{}/{}".format(self._path, node_name or "{}1".format(type_name))
        node = _Node(
            path,
            type_name,
            _Geometry(16, 10, 40, (-1.0, -1.0, -1.0), (1.0, 1.25, 1.0)),
        )
        node._parent = self
        self.created.append(node)
        return node

    def setInput(self, index: int, node) -> None:
        if self._max_inputs is not None and index >= self._max_inputs:
            raise RuntimeError("Input {} is not available on {}".format(index, self._type.name()))
        if index == self._fail_input_index:
            raise RuntimeError("PRIVATE_CONNECTION_DETAIL")
        self._inputs[index] = node

    def inputs(self):
        return tuple(self._inputs[index] for index in sorted(self._inputs))

    def parm(self, name: str):
        return self._parms.setdefault(name, _Parm())

    def parmTuple(self, _name: str):
        return self._parm_tuples.setdefault(_name, _ParmTuple())

    def cook(self, force: bool = False) -> None:
        assert force is True

    def errors(self):
        return []

    def warnings(self):
        return []

    def setDisplayFlag(self, _value: bool) -> None:
        return None

    def moveToGoodPosition(self) -> None:
        return None

    def destroy(self) -> None:
        self.destroy_calls += 1
        self.destroyed = True


def test_extrude_faces_is_typed_and_reads_back_the_created_sop() -> None:
    tools = yaml.safe_load((_SKILL_ROOT / "tools.yaml").read_text(encoding="utf-8"))["tools"]
    groups = yaml.safe_load((_SKILL_ROOT / "groups.yaml").read_text(encoding="utf-8"))["groups"]
    by_group = {group["name"]: group for group in groups}
    assert by_group["mesh-edit"]["default_active"] is True
    assert by_group["modeling"]["default_active"] is False
    assert set(by_group["modeling"]["tools"]) == {item["name"] for item in tools if item["group"] == "modeling"}
    contract = next(item for item in tools if item["name"] == "extrude_faces")
    assert contract["execution"] == "sync"
    assert contract["affinity"] == "main"
    assert contract["group"] == "modeling"
    assert contract["input_schema"]["additionalProperties"] is False

    module = _load_script("extrude_faces.py")
    parent = _Node("/obj/geo1", "geo", _Geometry(0, 0, 0, (0, 0, 0), (0, 0, 0)))
    source = _Node(
        "/obj/geo1/box1",
        "box",
        _Geometry(8, 6, 24, (-1.0, -1.0, -1.0), (1.0, 1.0, 1.0)),
    )
    source._parent = parent

    class _Hou:
        @staticmethod
        def node(path: str):
            return source if path == source.path() else None

    with patch.dict(sys.modules, {"hou": _Hou()}):
        result = module.main(
            input_path=source.path(),
            group="0",
            distance=0.25,
            node_name="rim_extrude",
        )

    assert result["success"] is True, result
    assert result["context"]["node"] == {
        "path": "/obj/geo1/rim_extrude",
        "name": "rim_extrude",
        "type": "polyextrude",
    }
    assert result["context"]["parameters"] == {
        "distance": 0.25,
        "group": "0",
        "inset": 0.0,
    }
    assert result["context"]["readback"]["primitive_count"] == 10
    assert result["context"]["readback"]["verified"] is True
    assert parent.created[0].inputs() == (source,)


def test_bevel_edges_is_bounded_and_reads_back_the_created_sop() -> None:
    tools = yaml.safe_load((_SKILL_ROOT / "tools.yaml").read_text(encoding="utf-8"))["tools"]
    contract = next(item for item in tools if item["name"] == "bevel_edges")
    assert contract["input_schema"]["properties"]["divisions"]["maximum"] == 64

    module = _load_script("bevel_edges.py")
    parent = _Node("/obj/geo1", "geo", _Geometry(0, 0, 0, (0, 0, 0), (0, 0, 0)))
    source = _Node(
        "/obj/geo1/box1",
        "box",
        _Geometry(8, 6, 24, (-1.0, -1.0, -1.0), (1.0, 1.0, 1.0)),
    )
    source._parent = parent

    class _Hou:
        @staticmethod
        def node(path: str):
            return source if path == source.path() else None

    with patch.dict(sys.modules, {"hou": _Hou()}):
        result = module.main(
            input_path=source.path(),
            group="0-3",
            distance=0.05,
            divisions=3,
            node_name="rim_bevel",
        )

    assert result["success"] is True, result
    assert result["context"]["node"]["type"] == "polybevel"
    assert result["context"]["parameters"] == {
        "distance": 0.05,
        "divisions": 3,
        "group": "0-3",
    }
    assert result["context"]["readback"]["verified"] is True


def test_inset_reuses_verified_polyextrude_without_raw_execution() -> None:
    tools = yaml.safe_load((_SKILL_ROOT / "tools.yaml").read_text(encoding="utf-8"))["tools"]
    contract = next(item for item in tools if item["name"] == "inset")
    assert contract["source_file"] == "scripts/inset.py"
    assert contract["input_schema"]["additionalProperties"] is False

    module = _load_script("inset.py")
    parent = _Node("/obj/geo1", "geo", _Geometry(0, 0, 0, (0, 0, 0), (0, 0, 0)))
    source = _Node(
        "/obj/geo1/box1",
        "box",
        _Geometry(8, 6, 24, (-1.0, -1.0, -1.0), (1.0, 1.0, 1.0)),
    )
    source._parent = parent

    class _Hou:
        @staticmethod
        def node(path: str):
            return source if path == source.path() else None

    with patch.dict(sys.modules, {"hou": _Hou()}):
        result = module.main(input_path=source.path(), group="0", amount=0.1)

    assert result["success"] is True, result
    assert result["context"]["node"]["type"] == "polyextrude"
    assert result["context"]["parameters"] == {
        "distance": 0.0,
        "group": "0",
        "inset": 0.1,
    }
    assert result["context"]["readback"]["verified"] is True


def test_loft_sections_wires_bounded_same_network_inputs_and_reads_back() -> None:
    tools = yaml.safe_load((_SKILL_ROOT / "tools.yaml").read_text(encoding="utf-8"))["tools"]
    contract = next(item for item in tools if item["name"] == "loft_sections")
    sections_schema = contract["input_schema"]["properties"]["sections"]
    assert sections_schema["minItems"] == 2
    assert sections_schema["maxItems"] == 64

    module = _load_script("loft_sections.py")
    parent = _Node("/obj/geo1", "geo", _Geometry(0, 0, 0, (0, 0, 0), (0, 0, 0)))
    sections = [
        _Node(
            "/obj/geo1/section{}".format(index),
            "circle",
            _Geometry(8, 1, 8, (-1.0, float(index), -1.0), (1.0, float(index), 1.0)),
        )
        for index in range(3)
    ]
    for section in sections:
        section._parent = parent
    by_path = {section.path(): section for section in sections}
    original_create = parent.createNode

    def create_node(type_name: str, node_name=None):
        node = original_create(type_name, node_name)
        if type_name == "skin":
            node._max_inputs = 2
        return node

    parent.createNode = create_node

    class _Hou:
        @staticmethod
        def node(path: str):
            return by_path.get(path)

    with patch.dict(sys.modules, {"hou": _Hou()}):
        result = module.main(
            sections=[section.path() for section in sections],
            node_name="fuselage_loft",
        )

    assert result["success"] is True, result
    assert result["context"]["node"]["type"] == "skin"
    assert result["context"]["node"]["path"] == "/obj/geo1/fuselage_loft"
    merge, skin = parent.created
    assert merge.type().name() == "merge"
    assert merge.inputs() == tuple(sections)
    assert skin.inputs() == (merge,)
    assert result["context"]["merge_node"]["path"] == merge.path()
    assert result["context"]["readback"]["verified"] is True


@pytest.mark.parametrize(
    ("failure_stage", "expected_created"),
    (
        ("merge_create", 0),
        ("merge_connect", 1),
        ("skin_create", 1),
        ("skin_connect", 2),
    ),
)
def test_loft_sections_rolls_back_the_whole_linear_loft_on_failure(
    failure_stage: str,
    expected_created: int,
) -> None:
    module = _load_script("loft_sections.py")
    parent = _Node("/obj/geo1", "geo", _Geometry(0, 0, 0, (0, 0, 0), (0, 0, 0)))
    sections = [
        _Node(
            "/obj/geo1/section{}".format(index),
            "circle",
            _Geometry(8, 1, 8, (-1.0, float(index), -1.0), (1.0, float(index), 1.0)),
        )
        for index in range(3)
    ]
    for section in sections:
        section._parent = parent
    by_path = {section.path(): section for section in sections}
    original_create = parent.createNode

    def create_node(type_name: str, node_name=None):
        if failure_stage == "merge_create" and type_name == "merge":
            raise RuntimeError("PRIVATE_CREATE_DETAIL")
        if failure_stage == "skin_create" and type_name == "skin":
            raise RuntimeError("PRIVATE_CREATE_DETAIL")
        node = original_create(type_name, node_name)
        if type_name == "merge" and failure_stage == "merge_connect":
            node._fail_input_index = 1
        if type_name == "skin":
            node._max_inputs = 2
            if failure_stage == "skin_connect":
                node._fail_input_index = 0
        return node

    parent.createNode = create_node

    class _Hou:
        @staticmethod
        def node(path: str):
            return by_path.get(path)

    with patch.dict(sys.modules, {"hou": _Hou()}):
        result = module.main(sections=[section.path() for section in sections])

    assert result["success"] is False
    assert result["message"] == "Failed to create verified Skin SOP loft"
    assert "PRIVATE_" not in str(result)
    assert len(parent.created) == expected_created
    assert all(node.destroyed for node in parent.created)


def test_boolean_op_resolves_native_menu_and_verifies_two_input_result() -> None:
    tools = yaml.safe_load((_SKILL_ROOT / "tools.yaml").read_text(encoding="utf-8"))["tools"]
    contract = next(item for item in tools if item["name"] == "boolean_op")
    assert contract["input_schema"]["properties"]["operation"]["enum"] == [
        "union",
        "intersect",
        "subtract",
    ]

    module = _load_script("boolean_op.py")
    parent = _Node("/obj/geo1", "geo", _Geometry(0, 0, 0, (0, 0, 0), (0, 0, 0)))
    left = _Node(
        "/obj/geo1/body",
        "box",
        _Geometry(8, 6, 24, (-1.0, -1.0, -1.0), (1.0, 1.0, 1.0)),
    )
    right = _Node(
        "/obj/geo1/cutter",
        "tube",
        _Geometry(16, 18, 64, (-0.25, -2.0, -0.25), (0.25, 2.0, 0.25)),
    )
    left._parent = parent
    right._parent = parent
    by_path = {left.path(): left, right.path(): right}

    class _Hou:
        @staticmethod
        def node(path: str):
            return by_path.get(path)

    original_create = parent.createNode

    def create_node(type_name: str, node_name=None):
        node = original_create(type_name, node_name)
        node._parms["booleanop"] = _Parm(
            menu_items=("0", "1", "2"),
            menu_labels=("Union", "Intersect", "A Minus B"),
        )
        return node

    parent.createNode = create_node
    with patch.dict(sys.modules, {"hou": _Hou()}):
        result = module.main(
            input_a=left.path(),
            input_b=right.path(),
            operation="subtract",
            node_name="launcher_cutout",
        )

    assert result["success"] is True, result
    assert result["context"]["node"]["type"] == "boolean"
    assert result["context"]["parameters"] == {
        "operation": "subtract",
        "operation_token": "2",
    }
    assert parent.created[0].inputs() == (left, right)
    assert result["context"]["readback"]["verified"] is True


def test_lathe_profile_sets_axis_and_divisions_with_readback() -> None:
    tools = yaml.safe_load((_SKILL_ROOT / "tools.yaml").read_text(encoding="utf-8"))["tools"]
    contract = next(item for item in tools if item["name"] == "lathe_profile")
    assert contract["input_schema"]["properties"]["segments"]["maximum"] == 256

    module = _load_script("lathe_profile.py")
    parent = _Node("/obj/geo1", "geo", _Geometry(0, 0, 0, (0, 0, 0), (0, 0, 0)))
    profile = _Node(
        "/obj/geo1/profile",
        "curve",
        _Geometry(5, 1, 5, (0.5, -1.0, 0.0), (1.0, 1.0, 0.0)),
    )
    profile._parent = parent

    class _Hou:
        @staticmethod
        def node(path: str):
            return profile if path == profile.path() else None

    with patch.dict(sys.modules, {"hou": _Hou()}):
        result = module.main(
            profile=profile.path(),
            axis="y",
            origin=[0.0, 0.0, 0.0],
            segments=48,
            node_name="rotor_hub",
        )

    assert result["success"] is True, result
    assert result["context"]["node"]["type"] == "revolve"
    assert result["context"]["parameters"] == {
        "axis": "y",
        "axis_direction": [0.0, 1.0, 0.0],
        "origin": [0.0, 0.0, 0.0],
        "segments": 48,
    }
    assert result["context"]["readback"]["verified"] is True


def test_edge_loop_and_bridge_are_bounded_verified_sop_operations() -> None:
    tools = yaml.safe_load((_SKILL_ROOT / "tools.yaml").read_text(encoding="utf-8"))["tools"]
    edge_contract = next(item for item in tools if item["name"] == "add_edge_loop")
    bridge_contract = next(item for item in tools if item["name"] == "bridge_edges")
    assert edge_contract["input_schema"]["properties"]["split_locations"]["maxLength"] == 4096
    assert bridge_contract["input_schema"]["properties"]["divisions"]["maximum"] == 64

    edge_module = _load_script("add_edge_loop.py")
    bridge_module = _load_script("bridge_edges.py")
    parent = _Node("/obj/geo1", "geo", _Geometry(0, 0, 0, (0, 0, 0), (0, 0, 0)))
    source = _Node(
        "/obj/geo1/body",
        "box",
        _Geometry(8, 6, 24, (-1.0, -1.0, -1.0), (1.0, 1.0, 1.0)),
    )
    source._parent = parent

    class _Hou:
        @staticmethod
        def node(path: str):
            return source if path == source.path() else None

    with patch.dict(sys.modules, {"hou": _Hou()}):
        edge_result = edge_module.main(
            input_path=source.path(),
            split_locations="0e0:0.5",
            node_name="support_loop",
        )
        bridge_result = bridge_module.main(
            input_path=source.path(),
            source_group="left_rim",
            destination_group="right_rim",
            divisions=4,
            node_name="rim_bridge",
        )

    assert edge_result["success"] is True, edge_result
    assert edge_result["context"]["node"]["type"] == "polysplit"
    assert edge_result["context"]["parameters"]["split_locations"] == "0e0:0.5"
    assert bridge_result["success"] is True, bridge_result
    assert bridge_result["context"]["node"]["type"] == "polybridge"
    assert bridge_result["context"]["parameters"] == {
        "destination_group": "right_rim",
        "divisions": 4,
        "source_group": "left_rim",
    }


def test_mirror_and_uv_tools_return_native_postcondition_readback() -> None:
    tools = yaml.safe_load((_SKILL_ROOT / "tools.yaml").read_text(encoding="utf-8"))["tools"]
    names = {item["name"] for item in tools}
    assert {"mirror", "auto_uv", "uv_project"} <= names

    mirror_module = _load_script("mirror.py")
    auto_uv_module = _load_script("auto_uv.py")
    project_module = _load_script("uv_project.py")
    parent = _Node("/obj/geo1", "geo", _Geometry(0, 0, 0, (0, 0, 0), (0, 0, 0)))
    source = _Node(
        "/obj/geo1/pylon",
        "box",
        _Geometry(8, 6, 24, (-1.0, -1.0, -1.0), (1.0, 1.0, 1.0)),
    )
    source._parent = parent
    original_create = parent.createNode

    def create_node(type_name: str, node_name=None):
        node = original_create(type_name, node_name)
        if type_name in {"uvunwrap", "uvproject"}:
            node._geometry = _Geometry(
                16,
                10,
                40,
                (-1.0, -1.0, -1.0),
                (1.0, 1.25, 1.0),
                attributes=("uv",),
            )
        if type_name == "uvproject":
            node._parms["projection"] = _Parm(
                menu_items=("0", "1", "2"),
                menu_labels=("Orthographic", "Cylindrical", "Spherical"),
            )
        return node

    parent.createNode = create_node

    class _Hou:
        @staticmethod
        def node(path: str):
            return source if path == source.path() else None

    with patch.dict(sys.modules, {"hou": _Hou()}):
        mirror_result = mirror_module.main(
            input_path=source.path(),
            origin=[0.0, 0.0, 0.0],
            direction=[1.0, 0.0, 0.0],
        )
        auto_result = auto_uv_module.main(input_path=source.path(), uv_attribute="uv")
        project_result = project_module.main(
            input_path=source.path(),
            projection="cylindrical",
            uv_attribute="uv",
        )

    assert mirror_result["success"] is True, mirror_result
    assert mirror_result["context"]["node"]["type"] == "mirror"
    assert mirror_result["context"]["parameters"]["direction"] == [1.0, 0.0, 0.0]
    assert auto_result["success"] is True, auto_result
    assert auto_result["context"]["readback"]["uv_attribute"] == "uv"
    assert project_result["success"] is True, project_result
    assert project_result["context"]["parameters"]["projection"] == "cylindrical"
    assert project_result["context"]["readback"]["uv_attribute"] == "uv"


def test_array_instances_builds_verified_radial_copy_to_points() -> None:
    tools = yaml.safe_load((_SKILL_ROOT / "tools.yaml").read_text(encoding="utf-8"))["tools"]
    contract = next(item for item in tools if item["name"] == "array_instances")
    assert contract["input_schema"]["properties"]["count"] == {
        "type": "integer",
        "minimum": 2,
        "maximum": 128,
    }
    assert contract["input_schema"]["properties"]["direction_mode"]["enum"] == [
        "radial",
        "tangent",
    ]
    assert contract["input_schema"]["properties"]["source_forward"]["enum"] == [
        "+x",
        "-x",
        "+y",
        "-y",
        "+z",
        "-z",
    ]

    module = _load_script("array_instances.py")
    parent = _Node("/obj/geo1", "geo", _Geometry(0, 0, 0, (0, 0, 0), (0, 0, 0)))
    source = _Node(
        "/obj/geo1/rotor_blade",
        "box",
        _Geometry(8, 6, 24, (0.0, -0.1, -0.5), (4.0, 0.1, 0.5)),
    )
    source._parent = parent
    original_create = parent.createNode

    def create_node(type_name: str, node_name=None):
        node = original_create(type_name, node_name)
        if type_name == "circle":
            node._geometry = _Geometry(4, 1, 4, (-3.5, 0.0, -3.5), (3.5, 0.0, 3.5))
            node._parms["type"] = _Parm(
                menu_items=("0", "1"),
                menu_labels=("Polygon", "NURBS Curve"),
            )
            node._parms["orient"] = _Parm(
                menu_items=("0", "1", "2"),
                menu_labels=("XY Plane", "YZ Plane", "ZX Plane"),
            )
        if type_name == "attribwrangle":
            orientation_geometry = _Geometry(
                4,
                1,
                4,
                (-3.5, 0.0, -3.5),
                (3.5, 0.0, 3.5),
                point_float_attributes={
                    "P": (
                        (0.0, 0.0, 3.5),
                        (3.5, 0.0, 0.0),
                        (0.0, 0.0, -3.5),
                        (-3.5, 0.0, 0.0),
                    ),
                    "orient": (
                        (0.0, 0.0, 0.0, 1.0),
                        (0.0, 0.70710678, 0.0, 0.70710678),
                        (0.0, 1.0, 0.0, 0.0),
                        (0.0, -0.70710678, 0.0, 0.70710678),
                    ),
                },
                point_int_attributes={"dcc_mcp_orientation_valid": (1, 1, 1, 1)},
            )
            node._parms["class"] = _Parm(
                menu_items=("0", "1", "2"),
                menu_labels=("Points", "Primitives", "Detail"),
            )

            def verified_geometry():
                snippet = node.parm("snippet").eval()
                assert "vector ring_axis = set(0.0, 1.0, 0.0);" in snippet
                assert "vector source_forward = set(1.0, 0.0, 0.0);" in snippet
                assert "normalize(cross(ring_axis, radial))" in snippet
                assert "p@orient = quaternion(dihedral" in snippet
                assert "i@dcc_mcp_orientation_valid = 1" in snippet
                return orientation_geometry

            node.geometry = verified_geometry
        return node

    parent.createNode = create_node

    class _Hou:
        @staticmethod
        def node(path: str):
            return source if path == source.path() else None

    with patch.dict(sys.modules, {"hou": _Hou()}):
        result = module.main(
            input_path=source.path(),
            count=4,
            radius=3.5,
            axis="y",
            start_angle_degrees=30.0,
            direction_mode="tangent",
            source_forward="+x",
            node_name="main_rotor_array",
        )

    assert result["success"] is True, result
    assert result["context"]["node"]["type"] == "copytopoints"
    assert result["context"]["points_node"]["type"] == "circle"
    assert result["context"]["orientation_node"]["type"] == "attribwrangle"
    assert result["context"]["parameters"] == {
        "axis": "y",
        "count": 4,
        "direction_mode": "tangent",
        "radius": 3.5,
        "source_forward": "+x",
        "start_angle_degrees": 30.0,
    }
    circle, orientation, copy = parent.created
    assert circle.parmTuple("r").eval() == (0.0, 30.0, 0.0)
    assert orientation.inputs() == (circle,)
    assert copy.inputs() == (source, orientation)
    assert result["context"]["readback"]["orientation"] == {
        "attribute": "orient",
        "distinct_count": 4,
        "point_count": 4,
        "tuple_size": 4,
        "valid_count": 4,
        "verified": True,
    }
    assert result["context"]["readback"]["verified"] is True


@pytest.mark.parametrize(
    (
        "axis",
        "direction_mode",
        "source_forward",
        "axis_literal",
        "forward_literal",
        "target_literal",
    ),
    (
        (
            "x",
            "radial",
            "-z",
            "set(1.0, 0.0, 0.0)",
            "set(0.0, 0.0, -1.0)",
            "vector target = radial;",
        ),
        (
            "z",
            "tangent",
            "+y",
            "set(0.0, 0.0, 1.0)",
            "set(0.0, 1.0, 0.0)",
            "vector target = normalize(cross(ring_axis, radial));",
        ),
    ),
)
def test_array_instances_emits_axis_and_source_forward_orientation_contract(
    axis: str,
    direction_mode: str,
    source_forward: str,
    axis_literal: str,
    forward_literal: str,
    target_literal: str,
) -> None:
    module = _load_script("array_instances.py")

    snippet = module._orientation_vex(axis, direction_mode, source_forward)

    assert "vector ring_axis = {};".format(axis_literal) in snippet
    assert "vector source_forward = {};".format(forward_literal) in snippet
    assert target_literal in snippet
    assert "length2(radial) > 1e-12" in snippet
    assert "i@dcc_mcp_orientation_valid = 0" in snippet


def test_array_instances_rejects_missing_orientation_readback_and_rolls_back() -> None:
    module = _load_script("array_instances.py")
    parent = _Node("/obj/geo1", "geo", _Geometry(0, 0, 0, (0, 0, 0), (0, 0, 0)))
    source = _Node(
        "/obj/geo1/rotor_blade",
        "box",
        _Geometry(8, 6, 24, (0.0, -0.1, -0.5), (4.0, 0.1, 0.5)),
    )
    source._parent = parent
    original_create = parent.createNode

    def create_node(type_name: str, node_name=None):
        node = original_create(type_name, node_name)
        if type_name == "circle":
            node._geometry = _Geometry(4, 1, 4, (-2.0, 0.0, -2.0), (2.0, 0.0, 2.0))
            node._parms["type"] = _Parm(
                menu_items=("0", "1"),
                menu_labels=("Polygon", "NURBS Curve"),
            )
            node._parms["orient"] = _Parm(
                menu_items=("0", "1", "2"),
                menu_labels=("XY Plane", "YZ Plane", "ZX Plane"),
            )
        if type_name == "attribwrangle":
            node._geometry = _Geometry(4, 1, 4, (-2.0, 0.0, -2.0), (2.0, 0.0, 2.0))
            node._parms["class"] = _Parm(
                menu_items=("0", "1", "2"),
                menu_labels=("Points", "Primitives", "Detail"),
            )
        return node

    parent.createNode = create_node

    class _Hou:
        @staticmethod
        def node(path: str):
            return source if path == source.path() else None

    with patch.dict(sys.modules, {"hou": _Hou()}):
        result = module.main(input_path=source.path(), count=4, radius=2.0, axis="y")

    assert result["success"] is False
    assert result["message"] == "Failed to create verified radial instance array"
    assert len(parent.created) == 2
    assert all(node.destroyed for node in parent.created)


@pytest.mark.parametrize("failure_stage", ("input_zero", "display_flag"))
def test_array_instances_rolls_back_unreturned_wrangle_on_pre_return_failure(
    failure_stage: str,
) -> None:
    module = _load_script("array_instances.py")
    parent = _Node("/obj/geo1", "geo", _Geometry(0, 0, 0, (0, 0, 0), (0, 0, 0)))
    source = _Node(
        "/obj/geo1/rotor_blade",
        "box",
        _Geometry(8, 6, 24, (0.0, -0.1, -0.5), (4.0, 0.1, 0.5)),
    )
    source._parent = parent
    original_create = parent.createNode

    def create_node(type_name: str, node_name=None):
        node = original_create(type_name, node_name)
        if type_name == "circle":
            node._geometry = _Geometry(4, 1, 4, (-2.0, 0.0, -2.0), (2.0, 0.0, 2.0))
            node._parms["type"] = _Parm(
                menu_items=("0", "1"),
                menu_labels=("Polygon", "NURBS Curve"),
            )
            node._parms["orient"] = _Parm(
                menu_items=("0", "1", "2"),
                menu_labels=("XY Plane", "YZ Plane", "ZX Plane"),
            )
        if type_name == "attribwrangle":
            if failure_stage == "input_zero":
                node._fail_input_index = 0
            else:

                def fail_display(_value: bool) -> None:
                    raise RuntimeError("PRIVATE_DISPLAY_DETAIL")

                node.setDisplayFlag = fail_display
        return node

    parent.createNode = create_node

    class _Hou:
        @staticmethod
        def node(path: str):
            return source if path == source.path() else None

    with patch.dict(sys.modules, {"hou": _Hou()}):
        result = module.main(input_path=source.path(), count=4, radius=2.0, axis="y")

    assert result["success"] is False
    assert result["message"] == "Failed to create verified radial instance array"
    assert "PRIVATE_" not in str(result)
    assert len(parent.created) == 2
    assert all(node.destroyed for node in parent.created)
    assert [node.destroy_calls for node in parent.created] == [1, 1]


@pytest.mark.parametrize("copy_input_index", (0, 1))
def test_array_instances_rolls_back_ring_orientation_and_copy_on_connection_failure(
    copy_input_index: int,
) -> None:
    module = _load_script("array_instances.py")
    parent = _Node("/obj/geo1", "geo", _Geometry(0, 0, 0, (0, 0, 0), (0, 0, 0)))
    source = _Node(
        "/obj/geo1/rotor_blade",
        "box",
        _Geometry(8, 6, 24, (0.0, -0.1, -0.5), (4.0, 0.1, 0.5)),
    )
    source._parent = parent
    original_create = parent.createNode

    def create_node(type_name: str, node_name=None):
        node = original_create(type_name, node_name)
        if type_name == "circle":
            node._geometry = _Geometry(4, 1, 4, (-2.0, 0.0, -2.0), (2.0, 0.0, 2.0))
            node._parms["type"] = _Parm(
                menu_items=("0", "1"),
                menu_labels=("Polygon", "NURBS Curve"),
            )
            node._parms["orient"] = _Parm(
                menu_items=("0", "1", "2"),
                menu_labels=("XY Plane", "YZ Plane", "ZX Plane"),
            )
        if type_name == "attribwrangle":
            node._geometry = _Geometry(
                4,
                1,
                4,
                (-2.0, 0.0, -2.0),
                (2.0, 0.0, 2.0),
                point_float_attributes={
                    "P": (
                        (2.0, 0.0, 0.0),
                        (0.0, 0.0, -2.0),
                        (-2.0, 0.0, 0.0),
                        (0.0, 0.0, 2.0),
                    ),
                    "orient": (
                        (0.0, 0.0, 0.0, 1.0),
                        (0.0, 0.70710678, 0.0, 0.70710678),
                        (0.0, 1.0, 0.0, 0.0),
                        (0.0, -0.70710678, 0.0, 0.70710678),
                    ),
                },
                point_int_attributes={"dcc_mcp_orientation_valid": (1, 1, 1, 1)},
            )
            node._parms["class"] = _Parm(
                menu_items=("0", "1", "2"),
                menu_labels=("Points", "Primitives", "Detail"),
            )
        if type_name == "copytopoints":
            node._fail_input_index = copy_input_index
        return node

    parent.createNode = create_node

    class _Hou:
        @staticmethod
        def node(path: str):
            return source if path == source.path() else None

    with patch.dict(sys.modules, {"hou": _Hou()}):
        result = module.main(input_path=source.path(), count=4, radius=2.0, axis="y")

    assert result["success"] is False
    assert result["message"] == "Failed to create verified radial instance array"
    assert len(parent.created) == 3
    assert all(node.destroyed for node in parent.created)
    assert [node.destroy_calls for node in parent.created] == [1, 1, 1]


def test_make_downstream_sop_preserves_display_failure_when_cleanup_raises_base_exception() -> None:
    module = _load_script("_mesh_common.py")
    parent = _Node("/obj/geo1", "geo", _Geometry(0, 0, 0, (0, 0, 0), (0, 0, 0)))
    source = _Node(
        "/obj/geo1/source",
        "box",
        _Geometry(8, 6, 24, (-1.0, -1.0, -1.0), (1.0, 1.0, 1.0)),
    )
    source._parent = parent
    original_failure = KeyboardInterrupt("PRIVATE_DISPLAY_DETAIL")
    cleanup_failure = SystemExit("PRIVATE_CLEANUP_DETAIL")
    original_create = parent.createNode

    def create_node(type_name: str, node_name=None):
        node = original_create(type_name, node_name)

        def fail_display(_value: bool) -> None:
            raise original_failure

        def fail_cleanup() -> None:
            node.destroy_calls += 1
            raise cleanup_failure

        node.setDisplayFlag = fail_display
        node.destroy = fail_cleanup
        return node

    parent.createNode = create_node

    with pytest.raises(KeyboardInterrupt) as captured:
        module.make_downstream_sop(source, "attribwrangle")

    assert captured.value is original_failure
    assert len(parent.created) == 1
    assert parent.created[0].inputs() == (source,)
    assert parent.created[0].destroy_calls == 1


def test_boolean_op_fails_closed_and_removes_partial_node_without_native_menu() -> None:
    module = _load_script("boolean_op.py")
    parent = _Node("/obj/geo1", "geo", _Geometry(0, 0, 0, (0, 0, 0), (0, 0, 0)))
    left = _Node(
        "/obj/geo1/body",
        "box",
        _Geometry(8, 6, 24, (-1.0, -1.0, -1.0), (1.0, 1.0, 1.0)),
    )
    right = _Node(
        "/obj/geo1/cutter",
        "tube",
        _Geometry(16, 18, 64, (-0.25, -2.0, -0.25), (0.25, 2.0, 0.25)),
    )
    left._parent = parent
    right._parent = parent
    by_path = {left.path(): left, right.path(): right}

    class _Hou:
        @staticmethod
        def node(path: str):
            return by_path.get(path)

    with patch.dict(sys.modules, {"hou": _Hou()}):
        result = module.main(input_a=left.path(), input_b=right.path(), operation="subtract")

    assert result["success"] is False
    assert result["context"] == {
        "error_code": "houdini_sop_transaction_failed",
        "error_type": "RuntimeError",
    }
    assert "traceback" not in str(result).lower()
    assert parent.created[0].destroyed is True


def test_set_pivot_is_owned_by_object_ops_and_returns_exact_readback() -> None:
    object_skill = _SKILL_ROOT.parent / "houdini-object-ops"
    tools = yaml.safe_load((object_skill / "tools.yaml").read_text(encoding="utf-8"))["tools"]
    contract = next(item for item in tools if item["name"] == "set_pivot")
    assert contract["input_schema"]["additionalProperties"] is False
    assert contract["input_schema"]["properties"]["position"]["maxItems"] == 3

    module = _load_skill_script("houdini-object-ops", "set_pivot.py")
    node = _Node("/obj/main_rotor", "geo", _Geometry(0, 0, 0, (0, 0, 0), (0, 0, 0)))

    class _Hou:
        @staticmethod
        def node(path: str):
            return node if path == node.path() else None

    with patch.dict(sys.modules, {"hou": _Hou()}):
        result = module.main(node_path=node.path(), position=[0.0, 2.5, 0.0])

    assert result["success"] is True, result
    assert result["context"]["node_path"] == node.path()
    assert result["context"]["position"] == [0.0, 2.5, 0.0]
    assert result["context"]["readback"] == {"pivot": [0.0, 2.5, 0.0], "verified": True}
