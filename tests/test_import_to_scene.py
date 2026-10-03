"""Behaviour tests for the Houdini ``import_to_scene`` material contract.

Regression cover for the silent material drop: ``material_mode`` used to be
accepted, schema-validated and then ignored, so ``as_authored`` reported
``success: true`` with zero materials and no warning.
"""

from __future__ import annotations

import importlib.util
import json
import struct
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, List, Optional

import pytest
from skill_loader import skill_script_import_context

_SKILLS_ROOT = Path(__file__).parent.parent / "src" / "dcc_mcp_houdini" / "skills"
_SCRIPT_DIR = _SKILLS_ROOT / "houdini-import-to-scene" / "scripts"
_SCRIPT = _SCRIPT_DIR / "import_to_scene.py"


# ---------------------------------------------------------------------------
# HOM doubles
# ---------------------------------------------------------------------------


class FakeParmTuple:
    def __init__(self, name: str, size: int = 3) -> None:
        self._name = name
        self.values = [0.0] * size

    def name(self) -> str:
        return self._name

    def set(self, values: Any) -> None:
        self.values = list(values)

    def eval(self) -> List[float]:
        return list(self.values)


class FakeParm:
    def __init__(self, name: str, value: Any = 0.0) -> None:
        self._name = name
        self.value = value

    def name(self) -> str:
        return self._name

    def set(self, value: Any) -> None:
        self.value = value

    def eval(self) -> Any:
        return self.value


# parm tuples / scalar parms exposed per node type, mirroring real Houdini.
_NODE_PARM_TUPLES = {"principledshader::2.0": {"basecolor": 3}, "principledshader": {"basecolor": 3}}
_NODE_PARMS = {
    "geo": {"scale": 1.0, "shop_materialpath": ""},
    "file": {"file": ""},
    "principledshader::2.0": {"metallic": 0.0, "rough": 1.0, "opacity": 1.0, "emitcolor": 0.0},
    "principledshader": {"metallic": 0.0, "rough": 1.0, "opacity": 1.0, "emitcolor": 0.0},
    "matnet": {},
}


class FakeNode:
    def __init__(self, path: str, type_name: str, parent: Optional["FakeNode"], registry: Dict[str, Any]) -> None:
        self._path = path
        self._type = type_name
        self._parent = parent
        self.registry = registry
        self._children: Dict[str, "FakeNode"] = {}
        self.parms = {name: FakeParm(name, value) for name, value in _NODE_PARMS.get(type_name, {}).items()}
        self.parm_tuples = {
            name: FakeParmTuple(name, size) for name, size in _NODE_PARM_TUPLES.get(type_name, {}).items()
        }
        self.comment = ""
        self.user_data: Dict[str, Any] = {}
        self.cooked = 0
        registry[path] = self

    # -- identity ---------------------------------------------------------
    def path(self) -> str:
        return self._path

    def name(self) -> str:
        return self._path.rsplit("/", 1)[-1]

    def type(self) -> Any:
        return type("Type", (), {"name": lambda _self=None, t=self._type: t})()

    def parent(self) -> Optional["FakeNode"]:
        return self._parent

    def children(self) -> List["FakeNode"]:
        return list(self._children.values())

    def node(self, name: str) -> Any:
        return self._children.get(name)

    # -- graph ------------------------------------------------------------
    def createNode(self, node_type: str, node_name: Optional[str] = None) -> "FakeNode":
        name = node_name or node_type.replace(":", "_") + "1"
        if name in self._children:
            suffix = 2
            while "{0}{1}".format(name, suffix) in self._children:
                suffix += 1
            name = "{0}{1}".format(name, suffix)
        prefix = "" if self._path == "/" else self._path
        child = FakeNode("{0}/{1}".format(prefix, name), node_type, self, self.registry)
        self._children[name] = child
        return child

    # -- parameters -------------------------------------------------------
    def parm(self, name: str) -> Optional[FakeParm]:
        return self.parms.get(name)

    def parmTuple(self, name: str) -> Optional[FakeParmTuple]:
        return self.parm_tuples.get(name)

    def setParms(self, values: Dict[str, Any]) -> None:
        for key, value in values.items():
            parm = self.parms.setdefault(key, FakeParm(key))
            parm.set(value)

    def setComment(self, comment: str) -> None:
        self.comment = comment

    def setUserData(self, key: str, value: Any) -> None:
        self.user_data[key] = value

    def cook(self, force: bool = False) -> None:
        self.cooked += 1

    def destroy(self) -> None:
        self.registry.pop(self._path, None)


class FakeHou:
    """Minimal HOM stand-in with a path registry rooted at ``/``."""

    def __init__(self) -> None:
        self.registry: Dict[str, Any] = {}
        self.root = FakeNode("/", "root", None, self.registry)
        self.obj = self.root.createNode("obj", "obj")

    def node(self, path: str) -> Any:
        return self.registry.get(path)


@pytest.fixture()
def hou(monkeypatch: pytest.MonkeyPatch) -> FakeHou:
    fake = FakeHou()
    monkeypatch.setitem(sys.modules, "hou", fake)
    return fake


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("test_import_to_scene_script", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    with skill_script_import_context(spec):
        spec.loader.exec_module(module)
    return module


@pytest.fixture()
def script() -> ModuleType:
    return _load_script()


# ---------------------------------------------------------------------------
# Carrier fixtures
# ---------------------------------------------------------------------------


def _pad(data: bytes, fill: bytes = b" ") -> bytes:
    remainder = len(data) % 4
    return data + fill * (4 - remainder if remainder else 0)


def write_glb(path: Path, materials: List[Dict[str, Any]], referenced: Optional[List[int]] = None) -> Path:
    """Write a minimal GLB carrying *materials* (default: all referenced)."""
    document = {
        "asset": {"version": "2.0"},
        "meshes": [
            {
                "primitives": [
                    {"attributes": {"POSITION": 0}, "material": index}
                    for index in (referenced if referenced is not None else range(len(materials)))
                ]
            }
        ],
        "materials": materials,
    }
    payload = _pad(json.dumps(document).encode("utf-8"), b" ")
    total = 12 + 8 + len(payload)
    header = struct.pack("<III", 0x46546C67, 2, total)
    chunk = struct.pack("<II", len(payload), 0x4E4F534A)
    path.write_bytes(header + chunk + payload)
    return path


def write_obj_with_mtl(path: Path) -> Path:
    mtl = "\n".join(
        [
            "newmtl brushed_metal",
            "Kd 0.72 0.45 0.20",
            "Ks 0.90 0.90 0.90",
            "Ns 120.0",
            "d 1.0",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    (path.parent / "asset.mtl").write_text(mtl, encoding="utf-8")
    path.write_text(
        "\n".join(["mtllib asset.mtl", "v 0 0 0", "v 1 0 0", "v 0 1 0", "usemtl brushed_metal", "f 1 2 3", ""]),
        encoding="utf-8",
    )
    return path


def _descriptor(path: Path, fmt: str, asset_id: str = "showcase_gltf") -> Dict[str, Any]:
    return {
        "asset_id": asset_id,
        "variants": [{"local_path": str(path), "format": fmt, "preferred": True}],
        "unit_hint": "meter",
        "meters_per_unit": 1.0,
        "up_axis": "y",
    }


def _warnings(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    return list(result.get("context", {}).get("warnings") or [])


def _extra(result: Dict[str, Any]) -> Dict[str, Any]:
    return dict(result.get("context", {}).get("extra") or {})


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestMaterialModeAsAuthored:
    def test_gltf_materials_are_imported_and_bound(self, script: ModuleType, hou: FakeHou, tmp_path: Path) -> None:
        carrier = write_glb(
            tmp_path / "showcase.glb",
            [
                {
                    "name": "brushed_metal",
                    "pbrMetallicRoughness": {
                        "baseColorFactor": [0.72, 0.45, 0.20, 1.0],
                        "metallicFactor": 1.0,
                        "roughnessFactor": 0.28,
                    },
                }
            ],
        )

        result = script.import_to_scene(_descriptor(carrier, "glb"), material_mode="as_authored")

        assert result["success"] is True
        material_path = "/mat/showcase_gltf_brushed_metal"
        assert _extra(result)["materials_imported"] == 1
        assert _extra(result)["material_paths"] == [material_path]
        assert _extra(result)["material_assignments"] == [
            {"object": "/obj/showcase_gltf", "material": material_path, "parm": "shop_materialpath"}
        ]
        assert _warnings(result) == []

        shader = hou.registry[material_path]
        assert shader.parm_tuples["basecolor"].values == [0.72, 0.45, 0.20]
        assert shader.parms["metallic"].value == 1.0
        assert shader.parms["rough"].value == 0.28
        assert hou.registry["/obj/showcase_gltf"].parms["shop_materialpath"].value == material_path
        # Material nodes are reported alongside the geometry nodes.
        assert material_path in result["context"]["imported_nodes"]

    def test_obj_mtl_materials_are_imported(self, script: ModuleType, hou: FakeHou, tmp_path: Path) -> None:
        carrier = write_obj_with_mtl(tmp_path / "asset.obj")

        result = script.import_to_scene(_descriptor(carrier, "obj"), material_mode="as_authored")

        assert result["success"] is True
        assert _extra(result)["materials_imported"] == 1
        shader = hou.registry["/mat/showcase_gltf_brushed_metal"]
        assert shader.parm_tuples["basecolor"].values == [0.72, 0.45, 0.20]
        assert 0.0 < shader.parms["rough"].value < 0.3  # Ns 120 -> glossy
        assert shader.parms["metallic"].value > 0.5  # bright Ks -> metallic
        assert _warnings(result) == []


class TestMaterialModeIsNotSilent:
    def test_unsupported_carrier_warns_instead_of_lying(self, script: ModuleType, hou: FakeHou, tmp_path: Path) -> None:
        carrier = tmp_path / "showcase.fbx"
        carrier.write_bytes(b"not a real fbx")

        result = script.import_to_scene(_descriptor(carrier, "fbx"), material_mode="as_authored")

        assert result["success"] is True  # geometry import still succeeded
        warnings = _warnings(result)
        assert [w["code"] for w in warnings] == ["material_fallback"]
        assert "as_authored" in warnings[0]["message"]
        assert _extra(result)["materials_imported"] == 0
        assert _extra(result)["status"] == "unsupported_format"
        assert "material_fallback" in result["prompt"]
        assert "not honoured" in result["message"]

    def test_broken_carrier_warns(self, script: ModuleType, hou: FakeHou, tmp_path: Path) -> None:
        carrier = tmp_path / "broken.glb"
        carrier.write_bytes(b"\x00\x01\x02not-a-glb")

        result = script.import_to_scene(_descriptor(carrier, "glb"), material_mode="as_authored")

        assert result["success"] is True
        assert [w["code"] for w in _warnings(result)] == ["material_fallback"]
        assert _extra(result)["materials_imported"] == 0

    def test_carrier_without_materials_does_not_warn(self, script: ModuleType, hou: FakeHou, tmp_path: Path) -> None:
        carrier = write_glb(tmp_path / "untextured.glb", [], referenced=[])

        result = script.import_to_scene(_descriptor(carrier, "glb"), material_mode="as_authored")

        assert result["success"] is True
        assert _warnings(result) == []
        assert _extra(result)["materials_imported"] == 0
        assert _extra(result)["status"] == "no_materials"

    def test_default_result_is_never_silent_about_materials(
        self, script: ModuleType, hou: FakeHou, tmp_path: Path
    ) -> None:
        """Regression: the default call used to ignore material_mode entirely."""
        carrier = tmp_path / "showcase.fbx"
        carrier.write_bytes(b"x")

        result = script.import_to_scene(_descriptor(carrier, "fbx"))

        assert _extra(result)["material_mode"] == "as_authored"
        assert _warnings(result), "default material_mode must not drop materials silently"


class TestMaterialModeVariants:
    def test_skip_creates_nothing_and_stays_quiet(self, script: ModuleType, hou: FakeHou, tmp_path: Path) -> None:
        carrier = write_glb(
            tmp_path / "showcase.glb",
            [{"name": "brushed_metal", "pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1]}}],
        )

        result = script.import_to_scene(_descriptor(carrier, "glb"), material_mode="skip")

        assert result["success"] is True
        assert _extra(result)["materials_imported"] == 0
        assert _warnings(result) == []
        assert hou.node("/mat") is None

    def test_default_gray_creates_a_neutral_material(self, script: ModuleType, hou: FakeHou, tmp_path: Path) -> None:
        carrier = tmp_path / "showcase.fbx"
        carrier.write_bytes(b"x")

        result = script.import_to_scene(_descriptor(carrier, "fbx"), material_mode="default_gray")

        assert result["success"] is True
        material_path = "/mat/showcase_gltf_default_gray"
        assert _extra(result)["material_paths"] == [material_path]
        assert hou.registry[material_path].parm_tuples["basecolor"].values == [0.5, 0.5, 0.5]
        assert hou.registry["/obj/showcase_gltf"].parms["shop_materialpath"].value == material_path
        assert _warnings(result) == []

    def test_unknown_mode_is_rejected(self, script: ModuleType, hou: FakeHou, tmp_path: Path) -> None:
        carrier = tmp_path / "showcase.fbx"
        carrier.write_bytes(b"x")

        result = script.import_to_scene(_descriptor(carrier, "fbx"), material_mode="as_dauthored")

        assert result["success"] is False
        assert "material_mode" in result["message"]
        assert result["context"]["supported_modes"] == ["as_authored", "default_gray", "skip"]


class TestGeometryImportUnchanged:
    def test_geometry_nodes_and_asset_id_are_still_reported(
        self, script: ModuleType, hou: FakeHou, tmp_path: Path
    ) -> None:
        carrier = tmp_path / "showcase.fbx"
        carrier.write_bytes(b"x")

        result = script.import_to_scene(_descriptor(carrier, "fbx"), material_mode="skip")

        assert result["context"]["imported_nodes"] == ["/obj/showcase_gltf", "/obj/showcase_gltf/file1"]
        assert hou.registry["/obj/showcase_gltf"].user_data["dcc_mcp_asset_id"] == "showcase_gltf"

    def test_missing_file_still_fails(self, script: ModuleType, hou: FakeHou, tmp_path: Path) -> None:
        carrier = tmp_path / "missing.bgeo"

        result = script.import_to_scene(_descriptor(carrier, "bgeo"))

        assert result["success"] is False
