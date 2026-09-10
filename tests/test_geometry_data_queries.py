"""Geometry data contracts, including bounded access and metadata discovery."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from skill_loader import skill_script_import_context

_ROOT = Path(__file__).parents[1] / "src" / "dcc_mcp_houdini" / "skills"


def load(name):
    spec = importlib.util.spec_from_file_location(
        "geo_query_" + name, _ROOT / "houdini-geometry" / "scripts" / (name + ".py")
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    with skill_script_import_context(spec):
        spec.loader.exec_module(module)
    return module


def test_topology_pages_primitives_and_bounds_vertex_iteration():
    accesses, vertices = [], []

    def primitive(index):
        accesses.append(index)

        def iterate():
            for point_index in (9, 2, 7, 4):
                vertices.append(point_index)
                yield SimpleNamespace(point=lambda p=point_index: SimpleNamespace(number=lambda: p))

        return SimpleNamespace(numVertices=lambda: 4, vertices=iterate, type=lambda: "Polygon", isClosed=lambda: True)

    geo = SimpleNamespace(primCount=lambda: 10, prim=primitive)
    node = SimpleNamespace(path=lambda: "/obj/geo1/OUT", geometry=lambda: geo)
    with patch.dict(sys.modules, {"hou": SimpleNamespace(node=lambda _: node)}):
        result = load("get_primitive_topology").get_primitive_topology(
            "/obj/geo1/OUT", offset=3, limit=1, vertex_limit=2
        )
    assert result["success"]
    assert accesses == [3] and vertices == [9, 2]
    data = result["context"]
    assert data["next_offset"] == 4 and data["total_count"] == 10
    assert data["primitives"] == [
        {
            "primitive_index": 3,
            "primitive_type": "Polygon",
            "vertex_count": 4,
            "point_indices": [9, 2],
            "vertices_truncated": True,
            "closed": True,
        }
    ]


@pytest.mark.parametrize("kwargs", [{"offset": -1}, {"limit": True}, {"limit": 33}, {"vertex_limit": 129}])
def test_topology_rejects_invalid_bounds_before_hom(kwargs):
    def forbidden(_):
        raise AssertionError("Invalid request accessed HOM")

    with patch.dict(sys.modules, {"hou": SimpleNamespace(node=forbidden)}):
        result = load("get_primitive_topology").get_primitive_topology("/obj/geo1/OUT", **kwargs)
    assert not result["success"]


def make_geometry(owner, values):
    accesses = []
    attribute = SimpleNamespace(dataType=lambda: "Float", size=lambda: 3)

    def lookup(name):
        return attribute if name == "P" else None

    def element(index):
        accesses.append(index)
        return SimpleNamespace(attribValue=lambda attr: values[index]) if index < len(values) else None

    geo = SimpleNamespace()
    finder, count, accessor = {
        "point": ("findPointAttrib", "pointCount", "point"),
        "primitive": ("findPrimAttrib", "primCount", "prim"),
        "vertex": ("findVertexAttrib", "vertexCount", "vertex"),
        "detail": ("findGlobalAttrib", None, None),
    }[owner]
    setattr(geo, finder, lookup)
    if count:
        setattr(geo, count, lambda: len(values))
        setattr(geo, accessor, element)
    else:
        geo.attribValue = lambda attr: values[0]
    node = SimpleNamespace(path=lambda: "/obj/geo1/OUT", geometry=lambda: geo)
    return geo, SimpleNamespace(node=lambda path: node), accesses


@pytest.mark.parametrize("owner", ["point", "primitive", "vertex"])
def test_attribute_pagination_reads_only_requested_elements(owner):
    geo, hou, accesses = make_geometry(owner, [(i, 0, 0) for i in range(10)])
    with patch.dict(sys.modules, {"hou": hou}):
        result = load("get_attribute_values").get_attribute_values("/obj/geo1/OUT", "P", owner, offset=3, limit=2)
    assert result["success"]
    data = result["context"]
    assert accesses == [3, 4]
    assert data["next_offset"] == 5 and data["total_count"] == 10
    assert [row["value"] for row in data["values"]] == [[3, 0, 0], [4, 0, 0]]


def test_detail_array_is_bounded_and_marked():
    geo, hou, _ = make_geometry("detail", [list(range(2000))])
    with patch.dict(sys.modules, {"hou": hou}):
        result = load("get_attribute_values").get_attribute_values("/obj/geo1/OUT", "P", "detail")
    row = result["context"]["values"][0]
    assert row["truncated"] and len(row["value"]) == 64
    assert result["context"]["next_offset"] is None


@pytest.mark.parametrize("kwargs", [{"limit": True}, {"offset": -1}, {"limit": 129}, {"attribute_class": "face"}])
def test_attribute_invalid_request_does_not_touch_geometry(kwargs):
    def forbidden(path):
        raise AssertionError("invalid request touched HOM")

    with patch.dict(sys.modules, {"hou": SimpleNamespace(node=forbidden)}):
        result = load("get_attribute_values").get_attribute_values("/obj/geo1/OUT", "P", **kwargs)
    assert not result["success"]
    assert "invalid request touched HOM" not in str(result)


def test_missing_attribute_fails_instead_of_empty_success():
    geo, hou, accesses = make_geometry("point", [1])
    with patch.dict(sys.modules, {"hou": hou}):
        result = load("get_attribute_values").get_attribute_values("/obj/geo1/OUT", "missing")
    assert not result["success"] and not accesses


def test_intrinsics_read_only_selected_fields():
    values = {"bounds": (0, 1, 0, 1, 0, 1), "transform": (1, 0, 0, 0, 1, 0, 0, 0, 1)}
    reads = []

    def read(name):
        reads.append(name)
        return values[name]

    prim = SimpleNamespace(intrinsicNames=lambda: tuple(values), intrinsicValue=read, type=lambda: "PackedGeometry")
    geo = SimpleNamespace(prim=lambda index: prim if index == 7 else None)
    node = SimpleNamespace(path=lambda: "/obj/geo1/OUT", geometry=lambda: geo)
    hou = SimpleNamespace(node=lambda path: node)
    mod = load("get_primitive_intrinsics")
    with patch.dict(sys.modules, {"hou": hou}):
        result = mod.get_primitive_intrinsics(node.path(), 7, names=["transform"])
        missing = mod.get_primitive_intrinsics(node.path(), 7, names=["missing"])
    assert result["success"] and not missing["success"]
    assert reads == ["transform"]
    assert result["context"]["intrinsics"]["transform"]["value"] == list(values["transform"])


def test_geometry_queries_discover_and_load():
    import dcc_mcp_core

    catalog = dcc_mcp_core.SkillCatalog(dcc_mcp_core.ToolRegistry())
    catalog.set_in_process_executor(lambda *_args, **_kwargs: {"success": True})
    assert catalog.discover(extra_paths=[str(_ROOT)], dcc_name="houdini")
    names = catalog.load_skill("houdini-geometry")
    assert "houdini_geometry__get_attribute_values" in names
    assert "houdini_geometry__get_primitive_intrinsics" in names
