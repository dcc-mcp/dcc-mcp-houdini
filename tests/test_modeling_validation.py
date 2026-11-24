from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from skill_loader import skill_script_import_context

_ROOT = Path(__file__).parents[1] / "src" / "dcc_mcp_houdini" / "skills"


def _load_script():
    path = _ROOT / "houdini-modeling-validation" / "scripts" / "export_model_state.py"
    spec = importlib.util.spec_from_file_location("houdini_modeling_validation_export", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    with skill_script_import_context(spec):
        spec.loader.exec_module(module)
    return module


def _node(geometry):
    parent = SimpleNamespace(path=lambda: "/obj/geo1", worldTransform=lambda: None)
    return SimpleNamespace(
        path=lambda: "/obj/geo1/OUT",
        name=lambda: "OUT",
        parent=lambda: parent,
        geometry=lambda: geometry,
    )


def test_export_model_state_reports_geometry_and_explicit_unavailable_checks():
    module = _load_script()
    uv = SimpleNamespace(name=lambda: "uv")
    material = SimpleNamespace(name=lambda: "shop_materialpath")
    primitive = SimpleNamespace(attribValue=lambda _: "/mat/toy")
    bounds = SimpleNamespace(minvec=lambda: (0, 1, 2), maxvec=lambda: (3, 4, 5))
    geometry = SimpleNamespace(
        pointCount=lambda: 8,
        primCount=lambda: 6,
        vertexCount=lambda: 24,
        boundingBox=lambda: bounds,
        vertexAttribs=lambda: [uv],
        pointAttribs=list,
        primAttribs=lambda: [material],
        globalAttribs=list,
        findPrimAttrib=lambda name: material if name == "shop_materialpath" else None,
        prim=lambda _: primitive,
    )

    with patch.dict(sys.modules, {"hou": SimpleNamespace(node=lambda _: _node(geometry))}):
        result = module.export_model_state("/obj/geo1/OUT")

    assert result["success"] is True
    state = result["context"]["state"]
    assert state["schema_name"] == "dcc-mcp/model-state"
    assert state["schema_version"] == 1
    assert state["parts"] == ["OUT"]
    assert state["hierarchy"] == ["/obj/geo1/OUT"]
    assert state["meshes"][0]["vertex_count"] == 24
    assert state["meshes"][0]["uv_sets"] == 1
    assert state["meshes"][0]["material"] == "/mat/toy"
    assert state["meshes"][0]["bounds"] == {"min": [0.0, 1.0, 2.0], "max": [3.0, 4.0, 5.0]}
    assert state["unavailable"] == ["euler", "non_manifold"]
    assert state["partial"] is True


def test_export_model_state_uses_manifold_and_euler_evidence_when_available():
    module = _load_script()
    bounds = SimpleNamespace(minvec=lambda: (0, 0, 0), maxvec=lambda: (1, 1, 1))
    matrix = SimpleNamespace(
        extractTranslates=lambda: (1, 2, 3),
        extractRotates=lambda: (0.1, 0.2, 0.3),
    )
    parent = SimpleNamespace(path=lambda: "/obj/geo1", worldTransform=lambda: matrix)
    geometry = SimpleNamespace(
        pointCount=lambda: 4,
        primCount=lambda: 2,
        vertexCount=lambda: 8,
        boundingBox=lambda: bounds,
        vertexAttribs=list,
        pointAttribs=list,
        primAttribs=list,
        globalAttribs=list,
        findPrimAttrib=lambda _: None,
        isManifold=lambda: True,
    )
    node = SimpleNamespace(
        path=lambda: "/obj/geo1/OUT",
        name=lambda: "OUT",
        parent=lambda: parent,
        geometry=lambda: geometry,
    )

    with patch.dict(sys.modules, {"hou": SimpleNamespace(node=lambda _: node)}):
        result = module.export_model_state("/obj/geo1/OUT")

    state = result["context"]["state"]
    assert result["success"] is True
    assert state["partial"] is False
    assert state["unavailable"] == []
    assert state["meshes"][0]["is_non_manifold"] is False
    assert state["objects"][0]["euler"] == [0.1, 0.2, 0.3]
    assert state["objects"][0]["transform"]["location"] == [1.0, 2.0, 3.0]


def test_export_model_state_rejects_missing_node_before_geometry_access():
    module = _load_script()
    with patch.dict(sys.modules, {"hou": SimpleNamespace(node=lambda _: None)}):
        result = module.export_model_state("/obj/missing/OUT")

    assert result["success"] is False
    assert "not found" in result["message"].lower()
