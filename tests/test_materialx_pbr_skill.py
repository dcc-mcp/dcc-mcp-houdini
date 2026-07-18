"""Behavior tests for typed MaterialX PBR authoring."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

_SCRIPTS = Path(__file__).parent.parent / "src" / "dcc_mcp_houdini" / "skills" / "houdini-materials" / "scripts"


def _load_script(name: str) -> ModuleType:
    path = _SCRIPTS / name
    spec = importlib.util.spec_from_file_location("materialx_{}".format(path.stem), path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _Type:
    def __init__(self, name: str) -> None:
        self._name = name

    def name(self) -> str:
        return self._name


class _Parm:
    def __init__(self) -> None:
        self.value = None

    def set(self, value) -> None:
        self.value = value

    def evalAsString(self) -> str:
        return str(self.value or "")


_INPUTS = {
    "mtlxstandard_surface": ["base_color", "metalness", "specular_roughness", "normal"],
    "mtlxnormalmap": ["in", "scale"],
    "mtlxdisplacement": ["displacement", "scale"],
    "subnetconnector": ["suboutput"],
}


class _Node:
    def __init__(self, path: str, node_type: str) -> None:
        self._path = path
        self._type = node_type
        self._children = {}
        self._inputs = []
        self._parms = {}
        self._user_data = {}
        self.destroyed = False

    def path(self) -> str:
        return self._path

    def name(self) -> str:
        return self._path.rsplit("/", 1)[-1]

    def type(self) -> _Type:
        return _Type(self._type)

    def inputNames(self):
        return _INPUTS.get(self._type, [])

    def inputs(self):
        return list(self._inputs)

    def setInput(self, index: int, source, _output_index: int = 0) -> None:
        while len(self._inputs) <= index:
            self._inputs.append(None)
        self._inputs[index] = source

    def parm(self, name: str) -> _Parm:
        return self._parms.setdefault(name, _Parm())

    def parmTuple(self, name: str) -> _Parm:
        return self._parms.setdefault(name, _Parm())

    def setUserData(self, name: str, value: str) -> None:
        self._user_data[name] = value

    def userData(self, name: str):
        return self._user_data.get(name)

    def createNode(self, node_type: str, node_name: str, **_kwargs):
        child = _Node(self._path + "/" + node_name, node_type)
        self._children[node_name] = child
        return child

    def node(self, name: str):
        return self._children.get(name)

    def children(self):
        return list(self._children.values())

    def layoutChildren(self) -> None:
        pass

    def destroy(self) -> None:
        self.destroyed = True


def _materialx_setup(builder: _Node, _prefix: str) -> None:
    builder._children["surface_output"] = _Node(builder.path() + "/surface_output", "subnetconnector")
    builder._children["displacement_output"] = _Node(builder.path() + "/displacement_output", "subnetconnector")


def test_build_materialx_pbr_connects_requested_channels() -> None:
    mod = _load_script("build_materialx_pbr.py")
    parent = _Node("/mat", "matnet")
    hou = SimpleNamespace(node=lambda path: parent if path == "/mat" else None)
    voptoolutils = SimpleNamespace(_setupMtlXBuilderSubnet=_materialx_setup)

    with patch.dict(sys.modules, {"hou": hou, "voptoolutils": voptoolutils}):
        result = mod.build_materialx_pbr(
            material_name="planet",
            base_color_texture="planet_basecolor.exr",
            roughness_texture="planet_roughness.exr",
            metallic_texture="planet_metallic.exr",
            normal_texture="planet_normal.exr",
            displacement_texture="planet_height.exr",
        )

    assert result["success"] is True
    assert result["context"]["valid"] is True
    assert set(result["context"]["channels"]) == {
        "base_color",
        "roughness",
        "metallic",
        "normal",
        "displacement",
    }
    material = parent.node("planet")
    surface = material.node("standard_surface")
    assert material.node("surface_output").inputs()[0] is surface
    assert material.node("displacement_output").inputs()[0] is material.node("displacement")
    assert surface.inputs()[0] is material.node("base_color_texture")
    assert surface.inputs()[1] is material.node("metallic_texture")
    assert surface.inputs()[2] is material.node("roughness_texture")
    assert surface.inputs()[3] is material.node("normal_map")


def test_validate_materialx_pbr_reads_back_required_channels() -> None:
    build_mod = _load_script("build_materialx_pbr.py")
    validate_mod = _load_script("validate_materialx_pbr.py")
    parent = _Node("/mat", "matnet")

    def node(path: str):
        if path == "/mat":
            return parent
        if path.startswith("/mat/"):
            return parent.node(path.rsplit("/", 1)[-1])
        return None

    hou = SimpleNamespace(node=node)
    voptoolutils = SimpleNamespace(_setupMtlXBuilderSubnet=_materialx_setup)
    with patch.dict(sys.modules, {"hou": hou, "voptoolutils": voptoolutils}):
        built = build_mod.build_materialx_pbr(
            material_name="planet",
            base_color_texture="planet_basecolor.exr",
            normal_texture="planet_normal.exr",
            displacement_texture="planet_height.exr",
        )
        material = parent.node("planet")
        surface = material.node("standard_surface")
        material.node("surface_output")._inputs[0] = _Node(surface.path(), surface.type().name())
        result = validate_mod.validate_materialx_pbr(
            built["context"]["material"]["path"],
            required_channels=["base_color", "normal", "displacement"],
        )

    assert result["success"] is True
    assert result["context"]["valid"] is True
    assert result["context"]["issues"] == []
    assert set(result["context"]["channels"]) == {"base_color", "normal", "displacement"}


def test_build_materialx_pbr_removes_partial_material_on_failure() -> None:
    mod = _load_script("build_materialx_pbr.py")
    parent = _Node("/mat", "matnet")
    hou = SimpleNamespace(node=lambda path: parent if path == "/mat" else None)

    def fail_setup(_builder, _prefix: str) -> None:
        raise RuntimeError("builder setup failed")

    voptoolutils = SimpleNamespace(_setupMtlXBuilderSubnet=fail_setup)
    with patch.dict(sys.modules, {"hou": hou, "voptoolutils": voptoolutils}):
        result = mod.build_materialx_pbr(material_name="broken")

    assert result["success"] is False
    assert parent.node("broken").destroyed is True


def test_validate_materialx_pbr_reports_disconnected_surface() -> None:
    build_mod = _load_script("build_materialx_pbr.py")
    validate_mod = _load_script("validate_materialx_pbr.py")
    parent = _Node("/mat", "matnet")

    def node(path: str):
        return parent if path == "/mat" else parent.node(path.rsplit("/", 1)[-1])

    hou = SimpleNamespace(node=node)
    voptoolutils = SimpleNamespace(_setupMtlXBuilderSubnet=_materialx_setup)
    with patch.dict(sys.modules, {"hou": hou, "voptoolutils": voptoolutils}):
        build_mod.build_materialx_pbr(material_name="broken_output")
        parent.node("broken_output").node("surface_output")._inputs[0] = None
        result = validate_mod.validate_materialx_pbr("/mat/broken_output")

    assert result["success"] is True
    assert result["context"]["valid"] is False
    assert result["context"]["issues"] == ["Standard surface is not connected to the surface output"]
