"""Public-contract tests for Houdini's typed modeling vocabulary."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

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


class _Geometry:
    def __init__(
        self,
        points: int,
        primitives: int,
        vertices: int,
        minimum,
        maximum,
        attributes=(),
    ) -> None:
        self._points = points
        self._primitives = primitives
        self._vertices = vertices
        self._bounds = _Bounds(minimum, maximum)
        self._attributes = set(attributes)

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


class _Node:
    def __init__(self, path: str, type_name: str, geometry: _Geometry) -> None:
        self._path = path
        self._type = _Type(type_name)
        self._geometry = geometry
        self._parent = None
        self._inputs = {}
        self._parms = {}
        self._parm_tuples = {}
        self.created = []
        self.destroyed = False

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
    assert parent.created[0].inputs() == tuple(sections)
    assert result["context"]["readback"]["verified"] is True


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
            node._parms["type"] = _Parm(
                menu_items=("0", "1"),
                menu_labels=("Polygon", "NURBS Curve"),
            )
            node._parms["orient"] = _Parm(
                menu_items=("0", "1", "2"),
                menu_labels=("XY Plane", "YZ Plane", "ZX Plane"),
            )
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
            node_name="main_rotor_array",
        )

    assert result["success"] is True, result
    assert result["context"]["node"]["type"] == "copytopoints"
    assert result["context"]["points_node"]["type"] == "circle"
    assert result["context"]["parameters"] == {
        "axis": "y",
        "count": 4,
        "radius": 3.5,
    }
    circle, copy = parent.created
    assert copy.inputs() == (source, circle)
    assert result["context"]["readback"]["verified"] is True


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
    assert "menu" in result["message"].lower() or "menu" in str(result).lower()
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
