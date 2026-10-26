"""Native glTF route contracts; HOM doubles are not licensed host acceptance."""

from __future__ import annotations

import importlib.util
import json
import struct
import sys
import zlib
from pathlib import Path

import pytest
from skill_loader import skill_script_import_context

SCRIPT_DIR = Path(__file__).parents[1] / "src/dcc_mcp_houdini/skills/houdini-import-to-scene/scripts"


def png(pixel):
    def chunk(kind, payload):
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\0" + bytes(pixel)))
        + chunk(b"IEND", b"")
    )


PNG = png((126, 60, 16))
NORMAL = png((128, 128, 255))


def load_module(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPT_DIR / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    with skill_script_import_context(spec):
        spec.loader.exec_module(module)
    return module


def fixture(path, binary=False):
    """Two actual triangles, distinct UVs/material IDs, PBR colour + normal maps."""
    data = bytearray()
    views, accessors = [], []
    for fmt, values, kind, count in [
        ("18f", [0, 0, 0, 1, 0, 0, 0, 1, 0, 2, 0, 0, 3, 0, 0, 2, 1, 0], "VEC3", 6),
        ("12f", [0, 0, 1, 0, 0, 1, 0.25, 0.25, 0.75, 0.25, 0.25, 0.75], "VEC2", 6),
        ("3H", [0, 1, 2], "SCALAR", 3),
        ("3H", [3, 4, 5], "SCALAR", 3),
    ]:
        while len(data) % 4:
            data += b"\0"
        block = struct.pack("<" + fmt, *values)
        views.append({"buffer": 0, "byteOffset": len(data), "byteLength": len(block)})
        accessors.append(
            {
                "bufferView": len(views) - 1,
                "componentType": 5123 if fmt.endswith("H") else 5126,
                "count": count,
                "type": kind,
            }
        )
        data += block
    doc = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [
            {
                "primitives": [
                    {"attributes": {"POSITION": 0, "TEXCOORD_0": 1}, "indices": 2, "material": 0},
                    {"attributes": {"POSITION": 0, "TEXCOORD_0": 1}, "indices": 3, "material": 1},
                ]
            }
        ],
        "buffers": [{"byteLength": len(data)}],
        "bufferViews": views,
        "accessors": accessors,
        "images": [{"uri": "oak.png"}, {"uri": "normal.png"}],
        "textures": [{"source": 0}, {"source": 1}],
        "materials": [
            {"name": "oak", "pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}},
            {
                "name": "paint",
                "pbrMetallicRoughness": {"baseColorFactor": [0.1, 0.2, 0.8, 1]},
                "normalTexture": {"index": 1},
            },
        ],
    }
    accessors[0].update(min=[0, 0, 0], max=[3, 1, 0])
    path.parent.mkdir(parents=True, exist_ok=True)
    (path.parent / "oak.png").write_bytes(PNG)
    (path.parent / "normal.png").write_bytes(NORMAL)
    if binary:
        for image, image_data in zip(doc["images"], [PNG, NORMAL]):
            image.pop("uri")
            while len(data) % 4:
                data += b"\0"
            views.append({"buffer": 0, "byteOffset": len(data), "byteLength": len(image_data)})
            image.update(bufferView=len(views) - 1, mimeType="image/png")
            data += image_data
        doc["buffers"][0]["byteLength"] = len(data)
        raw = json.dumps(doc).encode()
        raw += b" " * ((-len(raw)) % 4)
        data += b"\0" * ((-len(data)) % 4)
        path.write_bytes(
            struct.pack("<III", 0x46546C67, 2, 28 + len(raw) + len(data))
            + struct.pack("<II", len(raw), 0x4E4F534A)
            + raw
            + struct.pack("<II", len(data), 0x004E4942)
            + data
        )
    else:
        (path.parent / "mesh.bin").write_bytes(data)
        doc["buffers"][0]["uri"] = "mesh.bin"
        path.write_text(json.dumps(doc))
    return doc


@pytest.mark.parametrize("binary", [False, True])
def test_source_plan_preserves_texture_uv_and_material_indices(tmp_path, binary):
    mod = load_module("_gltf_native_import")
    path = tmp_path / ("boat.glb" if binary else "boat.gltf")
    fixture(path, binary)
    plan = mod.inspect_gltf_source(str(path))
    assert plan["requires_native"] is True
    assert [p["material_index"] for p in plan["primitives"]] == [0, 1]
    assert [p["texcoord_accessor"] for p in plan["primitives"]] == [1, 1]
    assert plan["textures"][0]["colorspace"] == "sRGB"
    assert plan["textures"][1]["colorspace"] == "raw"
    assert plan["textures"][0]["image_index"] == 0
    assert plan["textures"][1]["image_index"] == 1
    assert plan["triangle_counts"] == {0: 1, 1: 1}


def test_missing_texture_fails_before_scene_mutation(tmp_path):
    mod = load_module("_gltf_native_import")
    path = tmp_path / "boat.gltf"
    fixture(path)
    (tmp_path / "normal.png").unlink()
    with pytest.raises(ValueError, match="missing local dependency"):
        mod.inspect_gltf_source(str(path))


@pytest.mark.parametrize(
    "change,reason",
    [
        (lambda d: d["images"][0].update(uri="https://example.invalid/oak.png"), "remote"),
        (lambda d: d["materials"][0]["pbrMetallicRoughness"]["baseColorTexture"].update(texCoord=1), "TEXCOORD_0"),
        (
            lambda d: d["materials"][0]["pbrMetallicRoughness"]["baseColorTexture"].update(
                extensions={"KHR_texture_transform": {}}
            ),
            "extension",
        ),
        (lambda d: d["meshes"][0]["primitives"][0].update(material=8), "material index"),
        (lambda d: d["materials"][0].update(doubleSided=True), "doubleSided"),
    ],
)
def test_unsupported_source_is_explicit(tmp_path, change, reason):
    mod = load_module("_gltf_native_import")
    path = tmp_path / "boat.gltf"
    doc = fixture(path)
    change(doc)
    path.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match=reason):
        mod.inspect_gltf_source(str(path))


class Parm:
    def __init__(self, value=None, button=None):
        self.value, self.button = value, button
        self.set_count = 0

    def set(self, value):
        self.set_count += 1
        self.value = value

    def eval(self):
        return self.value

    def evalAsString(self):
        return str(self.value)

    def menuItems(self):
        return ("sRGB", "raw")

    def pressButton(self):
        self.button()


class NativeNode:
    def __init__(self, hou, path, kind):
        self.hou, self._path, self.kind = hou, path, kind
        self.params = {}
        hou.nodes[path] = self

    def path(self):
        return self._path

    def name(self):
        return self._path.rsplit("/", 1)[-1]

    def type(self):
        return type("NodeType", (), {"name": lambda _: self.kind})()

    def parm(self, name):
        return self.params.get(name)

    def parmTuple(self, name):
        return self.params.get(name)

    def setComment(self, value):
        self.comment = value

    def setUserData(self, name, value):
        pass

    def createNode(self, kind, node_name=None):
        if self.hou.unsupported:
            raise RuntimeError("native gltf_hierarchy unavailable")
        child = NativeNode(self.hou, self._path + "/" + (node_name or kind), kind)
        for name in [
            "filename",
            "assetfolder",
            "scene",
            "flattenhierarchy",
            "importmaterials",
            "promotepointattrs",
            "lockgeo",
        ]:
            child.params[name] = Parm()
        child.params["buildscene"] = Parm(button=lambda: self.hou.build(child))
        return child

    def allSubChildren(self):
        return [n for path, n in self.hou.nodes.items() if path.startswith(self._path + "/")]

    def displayNode(self):
        return self.hou.nodes[self._path + "/OUT"]

    def cook(self, force=False):
        pass

    def errors(self):
        return []

    def geometry(self):
        return self.hou.geometry

    def destroy(self):
        for path in list(self.hou.nodes):
            if path == self._path or path.startswith(self._path + "/"):
                del self.hou.nodes[path]


class Geometry:
    def __init__(self, paths):
        self.paths = paths

    def findVertexAttrib(self, name):
        return object()

    def findPrimAttrib(self, name):
        return object()

    def prims(self):
        return [type("Primitive", (), {"attribValue": lambda _, name, p=path: p})() for path in self.paths]


class NativeHou:
    """Emulates only the native button/readback boundary, never a glTF decoder."""

    def __init__(self, root, corrupt=None, packed=False):
        self.nodes = {}
        self.root = root
        self.corrupt = corrupt
        self.unsupported = False
        self.packed = packed
        self.geometry = None
        NativeNode(self, "/obj", "obj")

    def node(self, path):
        return self.nodes.get(path)

    def build(self, importer):
        paths = []
        for name, slot, file in [("oak", "basecolor", "oak.png"), ("paint", "baseNormal", "normal.png")]:
            shader = NativeNode(self, importer.path() + "/materials/" + name, "principledshader::2.0")
            shader.params[slot + "_texture"] = Parm(str(self.root / file))
            shader.params.update({"basecolor": Parm([0, 0, 0]), "metallic": Parm(0), "rough": Parm(0)})
            if self.corrupt == "texture_path" and slot == "baseNormal":
                shader.params[slot + "_texture"].value = str(self.root / "oak.png")
            shader.params[slot + "_textureColorSpace"] = Parm("automatic")
            enable = "baseBumpAndNormal_enable" if slot == "baseNormal" else slot + "_useTexture"
            shader.params[enable] = Parm(1)
            if self.packed and name == "oak":
                for channel, component in [("metallic", 3), ("rough", 2)]:
                    shader.params[channel + "_texture"] = Parm(str(self.root / "mr.png"))
                    shader.params[channel + "_textureColorSpace"] = Parm("raw")
                    shader.params[channel + "_useTexture"] = Parm(1)
                    shader.params[channel + "_monoChannel"] = Parm(component)
            if self.corrupt == "color_space":
                shader.params.pop(slot + "_textureColorSpace")
            if self.corrupt == "disabled":
                shader.params[enable].value = 0
            paths.append(shader.path())
        if self.corrupt == "assignment":
            paths[1] = paths[0]
        if self.corrupt == "assignment_swap":
            paths.reverse()
        geo = NativeNode(self, importer.path() + "/mesh", "geo")
        NativeNode(self, geo.path() + "/OUT", "gltf")
        self.geometry = Geometry(paths)


def test_native_route_reports_two_material_counts_without_claiming_face_identity(tmp_path):
    mod = load_module("_gltf_native_import")
    carrier = tmp_path / "boat.gltf"
    fixture(carrier)
    hou = NativeHou(tmp_path)
    nodes, report = mod.import_native_gltf(
        hou, str(carrier), "boat", "/obj", mod.inspect_gltf_source(str(carrier)), str(tmp_path / "extract")
    )
    assert nodes[0] == "/obj/boat"
    assert report["status"] == "partial_native_materials"
    assert report["primitive_identity_verified"] is False
    assert [a["source_material_index"] for a in report["material_assignments"]] == [0, 1]
    assert [a["primitive_count"] for a in report["material_assignments"]] == [1, 1]
    assert all(
        t["verified"] and t["enabled"] and t["color_space_readback"]["verified"] for t in report["texture_bindings"]
    )
    assert all(u["uv_present"] for u in report["uv_readback"])
    assert all(p["verified"] for p in report["pbr_factor_readback"])
    corrected = [p for p in report["pbr_factor_readback"] if p["correction_applied"]]
    assert corrected and all(not p["native_verified"] for p in corrected)
    assert all(p["initial_value"] != p["actual"] for p in corrected)
    assert all(t["color_space_readback"]["initial_value"] == "automatic" for t in report["texture_bindings"])
    assert all(t["color_space_readback"]["correction_applied"] for t in report["texture_bindings"])
    assert report["texture_bindings"][0]["path"] == str(tmp_path / "oak.png")


def test_equal_counts_cannot_verify_primitive_material_identity(tmp_path):
    mod = load_module("_gltf_native_import")
    carrier = tmp_path / "boat.gltf"
    fixture(carrier)
    hou = NativeHou(tmp_path, corrupt="assignment_swap")
    _, report = mod.import_native_gltf(
        hou, str(carrier), "boat", "/obj", mod.inspect_gltf_source(str(carrier)), str(tmp_path / "extract")
    )
    assert [a["primitive_count"] for a in report["material_assignments"]] == [1, 1]
    assert report["status"] == "partial_native_materials"
    assert report["primitive_identity_verified"] is False
    assert "counts alone are insufficient" in "; ".join(report["unapplied_required"])


@pytest.mark.parametrize("corrupt", ["color_space", "disabled", "assignment", "texture_path"])
def test_unverified_native_readback_cannot_claim_as_authored(tmp_path, corrupt):
    mod = load_module("_gltf_native_import")
    carrier = tmp_path / "boat.gltf"
    fixture(carrier)
    _, report = mod.import_native_gltf(
        NativeHou(tmp_path, corrupt),
        str(carrier),
        "boat",
        "/obj",
        mod.inspect_gltf_source(str(carrier)),
        str(tmp_path / "extract"),
    )
    assert report["status"] == "partial_native_materials"
    assert report["unapplied_required"]


def test_native_unavailable_does_not_fall_back_to_first_material(tmp_path):
    mod = load_module("_gltf_native_import")
    carrier = tmp_path / "boat.gltf"
    fixture(carrier)
    hou = NativeHou(tmp_path)
    hou.unsupported = True
    with pytest.raises(RuntimeError, match="unavailable"):
        mod.import_native_gltf(
            hou, str(carrier), "boat", "/obj", mod.inspect_gltf_source(str(carrier)), str(tmp_path / "extract")
        )
    assert list(hou.nodes) == ["/obj"]
    assert not (tmp_path / "extract").exists()


def test_missing_parent_does_not_create_texture_directory(tmp_path):
    mod = load_module("_gltf_native_import")
    carrier = tmp_path / "boat.gltf"
    fixture(carrier)
    with pytest.raises(ValueError, match="parent does not exist"):
        mod.import_native_gltf(
            NativeHou(tmp_path),
            str(carrier),
            "boat",
            "/missing",
            mod.inspect_gltf_source(str(carrier)),
            str(tmp_path / "extract"),
        )
    assert not (tmp_path / "extract").exists()


def test_failed_build_keeps_newly_extracted_files(tmp_path):
    mod = load_module("_gltf_native_import")
    carrier = tmp_path / "boat.gltf"
    fixture(carrier)
    hou = NativeHou(tmp_path)

    def failing_build(importer):
        output = Path(importer.parm("assetfolder").evalAsString())
        (output / "diagnostic.txt").write_text("preserve")
        raise RuntimeError("build failed after extraction")

    hou.build = failing_build
    with pytest.raises(RuntimeError, match="after extraction"):
        mod.import_native_gltf(
            hou, str(carrier), "boat", "/obj", mod.inspect_gltf_source(str(carrier)), str(tmp_path / "extract")
        )
    assert (tmp_path / "extract" / "diagnostic.txt").read_text() == "preserve"
    assert list(hou.nodes) == ["/obj"]


def test_material_paths_only_reports_mapped_source_materials(tmp_path):
    mod = load_module("_gltf_native_import")
    carrier = tmp_path / "boat.gltf"
    doc = fixture(carrier)
    doc["materials"][1]["name"] = "unmapped"
    carrier.write_text(json.dumps(doc))
    _, report = mod.import_native_gltf(
        NativeHou(tmp_path),
        str(carrier),
        "boat",
        "/obj",
        mod.inspect_gltf_source(str(carrier)),
        str(tmp_path / "extract"),
    )
    assert report["materials_imported"] == 1
    assert report["material_paths"] == ["/obj/boat/materials/oak"]


def test_already_correct_color_space_is_read_without_writing(tmp_path):
    mod = load_module("_gltf_native_import")
    hou = NativeHou(tmp_path)
    shader = NativeNode(hou, "/mat/oak", "principledshader::2.0")
    parm = Parm("sRGB")
    shader.params["basecolor_textureColorSpace"] = parm
    record = mod._colorspace(shader, "basecolor", "sRGB")
    assert record["verified"] and record["native_verified"]
    assert not record["correction_applied"]
    assert parm.set_count == 0


def test_failed_factor_correction_is_not_reported_as_applied(tmp_path):
    mod = load_module("_gltf_native_import")
    carrier = tmp_path / "boat.gltf"
    fixture(carrier)
    hou = NativeHou(tmp_path)
    original_build = hou.build

    class StuckParm(Parm):
        def set(self, value):
            self.set_count += 1

    def build(importer):
        original_build(importer)
        hou.node(importer.path() + "/materials/oak").params["rough"] = StuckParm(0)

    hou.build = build
    _, report = mod.import_native_gltf(
        hou, str(carrier), "boat", "/obj", mod.inspect_gltf_source(str(carrier)), str(tmp_path / "extract")
    )
    record = next(p for p in report["pbr_factor_readback"] if p["material_index"] == 0 and p["parameter"] == "rough")
    assert not record["verified"] and not record["native_verified"]
    assert record["correction_attempted"] and not record["correction_applied"]


def test_existing_texture_folder_is_never_overwritten(tmp_path):
    mod = load_module("_gltf_native_import")
    carrier = tmp_path / "boat.gltf"
    fixture(carrier)
    folder = tmp_path / "extract"
    folder.mkdir()
    marker = folder / "existing.txt"
    marker.write_text("preserve")
    hou = NativeHou(tmp_path)
    with pytest.raises(FileExistsError):
        mod.import_native_gltf(hou, str(carrier), "boat", "/obj", mod.inspect_gltf_source(str(carrier)), str(folder))
    assert marker.read_text() == "preserve"
    assert list(hou.nodes) == ["/obj"]


@pytest.mark.parametrize("corrupt", [None, "color_space", "assignment", "disabled", "texture_path"])
def test_existing_import_entrypoint_uses_native_and_reports_partial(tmp_path, monkeypatch, corrupt):
    carrier = tmp_path / "boat.gltf"
    fixture(carrier)
    hou = NativeHou(tmp_path, corrupt)
    monkeypatch.setitem(sys.modules, "hou", hou)
    script = load_module("import_to_scene")
    descriptor = {
        "asset_id": "boat",
        "variants": [{"local_path": str(carrier), "format": "gltf", "preferred": True}],
        "meters_per_unit": 1.0,
        "up_axis": "y",
    }
    result = script.import_to_scene(descriptor, texture_output_dir=str(tmp_path / "extract"))
    assert result["success"] is True
    report = result["context"]["extra"]
    assert report["native_importer"] == "gltf_hierarchy"
    assert report["status"] == "partial_native_materials"
    assert result["context"]["warnings"]
    assert "native materials were created but could not be fully verified" in result["prompt"]
    assert "materials were dropped" not in result["prompt"]
    assert "context.warnings (code=material_fallback)" in result["prompt"]
    assert len(result["context"]["imported_nodes"]) == len(set(result["context"]["imported_nodes"]))
    assert not any(n.kind == "file" for n in hou.nodes.values())


def test_existing_import_entrypoint_rejects_missing_texture_without_mutation(tmp_path, monkeypatch):
    carrier = tmp_path / "boat.gltf"
    fixture(carrier)
    (tmp_path / "oak.png").unlink()
    hou = NativeHou(tmp_path)
    monkeypatch.setitem(sys.modules, "hou", hou)
    script = load_module("import_to_scene")
    result = script.import_to_scene(
        {"asset_id": "boat", "variants": [{"local_path": str(carrier), "format": "gltf"}]},
        texture_output_dir=str(tmp_path / "extract"),
    )
    assert result["success"] is False
    assert list(hou.nodes) == ["/obj"]
    assert not (tmp_path / "extract").exists()


def test_partial_prompt_does_not_claim_creation_without_verified_materials(tmp_path, monkeypatch):
    carrier = tmp_path / "boat.gltf"
    doc = fixture(carrier)
    for index, material in enumerate(doc["materials"]):
        material["name"] = "unmapped_" + str(index)
    carrier.write_text(json.dumps(doc))
    monkeypatch.setitem(sys.modules, "hou", NativeHou(tmp_path))
    script = load_module("import_to_scene")
    result = script.import_to_scene(
        {"asset_id": "boat", "variants": [{"local_path": str(carrier), "format": "gltf"}]},
        texture_output_dir=str(tmp_path / "extract"),
    )
    assert result["context"]["extra"]["materials_imported"] == 0
    assert "native materials could not be fully verified" in result["prompt"]
    assert "were created" not in result["prompt"]
    assert "materials were dropped" not in result["prompt"]


def test_packed_metallic_roughness_is_raw_and_keeps_blue_green_channels(tmp_path):
    mod = load_module("_gltf_native_import")
    carrier = tmp_path / "boat.gltf"
    doc = fixture(carrier)
    (tmp_path / "mr.png").write_bytes(png((0, 180, 70)))
    doc["images"].append({"uri": "mr.png"})
    doc["textures"].append({"source": 2})
    doc["materials"][0]["pbrMetallicRoughness"]["metallicRoughnessTexture"] = {"index": 2}
    carrier.write_text(json.dumps(doc))
    _, report = mod.import_native_gltf(
        NativeHou(tmp_path, packed=True),
        str(carrier),
        "boat",
        "/obj",
        mod.inspect_gltf_source(str(carrier)),
        str(tmp_path / "extract"),
    )
    assert report["status"] == "partial_native_materials"
    packed = [t for t in report["texture_bindings"] if t["slot"] in ("metallic", "rough")]
    assert [t["mono_channel"] for t in packed] == [3, 2]
    assert all(t["colorspace"] == "raw" and t["channel_verified"] for t in packed)


def test_malformed_texture_table_is_not_silently_ignored(tmp_path, monkeypatch):
    carrier = tmp_path / "boat.gltf"
    doc = fixture(carrier)
    doc["materials"] = doc["materials"][:1]
    doc["meshes"][0]["primitives"] = doc["meshes"][0]["primitives"][:1]
    doc.pop("textures")
    carrier.write_text(json.dumps(doc))
    hou = NativeHou(tmp_path)
    monkeypatch.setitem(sys.modules, "hou", hou)
    script = load_module("import_to_scene")
    result = script.import_to_scene(
        {"asset_id": "boat", "variants": [{"local_path": str(carrier), "format": "gltf"}]},
        texture_output_dir=str(tmp_path / "extract"),
    )
    assert result["success"] is False
    assert list(hou.nodes) == ["/obj"]
