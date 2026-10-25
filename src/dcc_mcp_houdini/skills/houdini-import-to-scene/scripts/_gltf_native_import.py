"""Use SideFX's glTF hierarchy importer for textured/multi-material assets.

Pure preflight retains source indices and texture semantics. Geometry, UVs,
image extraction and shaders remain the native importer's responsibility.
"""

from __future__ import annotations

import base64
import hashlib
import os
import re
import struct
from collections import Counter
from urllib.parse import unquote, urlsplit

from _asset_material_import import _read_gltf_json

_TEXTURES = (
    ("baseColorTexture", "basecolor", "sRGB", None),
    ("metallicRoughnessTexture", "metallic", "raw", 3),
    ("metallicRoughnessTexture", "rough", "raw", 2),
    ("normalTexture", "baseNormal", "raw", None),
    ("emissiveTexture", "emitcolor", "sRGB", None),
)


def requires_native_gltf(filepath):
    """Complex carriers use the native path; legacy errors keep their reports."""
    try:
        document = _read_gltf_json(filepath)
    except Exception:
        return False
    materials = document.get("materials", [])
    authored_textures = any(
        any(field in material or field in material.get("pbrMetallicRoughness", {}) for field, *_ in _TEXTURES)
        for material in materials
    )
    return bool(document.get("textures")) or authored_textures or len(materials) > 1


def _local_uri(uri, root):
    if not isinstance(uri, str):
        raise ValueError("invalid local dependency URI")
    if uri.startswith("data:"):
        return None
    parsed = urlsplit(uri)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError("remote or nonlocal glTF dependency is unsupported")
    path = os.path.realpath(os.path.join(root, unquote(uri)))
    if os.path.commonpath([root, path]) != root:
        raise ValueError("glTF dependency escapes the carrier directory")
    if not os.path.isfile(path):
        raise ValueError("missing local dependency: {0}".format(uri))
    return path


def _uri_bytes(uri, root):
    path = _local_uri(uri, root)
    if path is not None:
        with open(path, "rb") as handle:
            return handle.read()
    header, payload = uri.split(",", 1)
    if not header.endswith(";base64"):
        raise ValueError("only base64 data URIs are supported")
    return base64.b64decode(payload, validate=True)


def _buffers(document, filepath, root):
    binary = None
    if filepath.lower().endswith(".glb"):
        with open(filepath, "rb") as handle:
            blob = handle.read()
        offset = 12
        while offset + 8 <= len(blob):
            length, kind = struct.unpack_from("<II", blob, offset)
            if offset + 8 + length > len(blob):
                raise ValueError("truncated GLB buffer")
            if kind == 0x004E4942:
                binary = blob[offset + 8 : offset + 8 + length]
                break
            offset += 8 + length
    result = []
    for item in document.get("buffers", []):
        data = _uri_bytes(item["uri"], root) if "uri" in item else binary
        if data is None or len(data) < item.get("byteLength", 0):
            raise ValueError("missing or truncated glTF buffer")
        result.append(data)
    return result


def _image_digest(document, index, buffers, root):
    image = document["images"][index]
    if "uri" in image:
        data = _uri_bytes(image["uri"], root)
    else:
        view = document["bufferViews"][image["bufferView"]]
        data_buffer = buffers[view["buffer"]]
        offset, length = view.get("byteOffset", 0), view["byteLength"]
        if offset < 0 or length <= 0 or offset + length > len(data_buffer):
            raise ValueError("invalid embedded image buffer range")
        data = data_buffer[offset : offset + length]
    return hashlib.sha256(data).hexdigest()


def _index(values, index, label):
    if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(values):
        raise ValueError("invalid " + label + " index")
    return values[index]


def inspect_gltf_source(filepath):
    """Return a source plan without importing hou or mutating files/scene."""
    document = _read_gltf_json(filepath)
    if document.get("extensionsRequired"):
        raise ValueError("required glTF extension is unsupported by this import contract")
    root = os.path.realpath(os.path.dirname(filepath))
    materials = document.get("materials", [])
    primitives, used = [], set()
    meshes = document.get("meshes", [])
    # Count only instances in the selected scene, as the native importer does.
    instances = Counter()
    nodes = document.get("nodes", [])
    scenes = document.get("scenes", [])
    if scenes:

        def visit(index, ancestors):
            if index in ancestors:
                raise ValueError("cyclic glTF scene")
            node = nodes[index]
            if "mesh" in node:
                instances[node["mesh"]] += 1
            for child in node.get("children", []):
                visit(child, ancestors | {index})

        for index in scenes[document.get("scene", 0)].get("nodes", []):
            visit(index, set())
    else:
        instances.update(range(len(meshes)))
    counts = Counter()
    for mesh_index, mesh in enumerate(meshes):
        if mesh_index not in instances:
            continue
        for primitive_index, primitive in enumerate(mesh.get("primitives", [])):
            index = primitive.get("material")
            if index is not None and (
                isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(materials)
            ):
                raise ValueError("invalid primitive material index")
            if index is not None:
                used.add(index)
            attrs = primitive.get("attributes", {})
            accessor = primitive.get("indices", attrs.get("POSITION"))
            count = document.get("accessors", [])[accessor]["count"] if accessor is not None else 0
            if primitive.get("mode", 4) != 4:
                raise ValueError("only native glTF triangle primitives are supported")
            counts[index] += count // 3 * instances[mesh_index]
            primitives.append(
                {
                    "mesh_index": mesh_index,
                    "primitive_index": primitive_index,
                    "material_index": index,
                    "texcoord_accessor": attrs.get("TEXCOORD_0"),
                }
            )
    textures = []
    payloads = _buffers(document, filepath, root)
    names = Counter(str(m.get("name", "")) for m in materials)
    source_materials = []
    for index in sorted(used):
        material = materials[index]
        if (
            material.get("extensions")
            or material.get("occlusionTexture")
            or material.get("alphaMode", "OPAQUE") != "OPAQUE"
            or material.get("doubleSided", False)
        ):
            raise ValueError(
                "material extension, occlusion, doubleSided or nonopaque mode requires unsupported shader handling"
            )
        source_name = str(material.get("name", ""))
        native_name = source_name + ("_" + str(index) if names[source_name] > 1 else "")
        native_name = re.sub(r"[^a-zA-Z0-9_]", "_", native_name)
        if native_name[:1].isdigit():
            native_name = "_" + native_name
        pbr = material.get("pbrMetallicRoughness", {})
        source_materials.append(
            {
                "material_index": index,
                "name": source_name,
                "native_name": native_name,
                "factors": {
                    "basecolor": pbr.get("baseColorFactor", [1, 1, 1, 1])[:3],
                    "metallic": pbr.get("metallicFactor", 1.0),
                    "rough": pbr.get("roughnessFactor", 1.0),
                },
            }
        )
        for field, slot, colorspace, channel in _TEXTURES:
            info = (
                material.get("pbrMetallicRoughness", {})
                if field in ("baseColorTexture", "metallicRoughnessTexture")
                else material
            ).get(field)
            if info is None:
                continue
            if info.get("texCoord", 0) != 0:
                raise ValueError("only TEXCOORD_0 texture coordinates are supported")
            if info.get("extensions"):
                raise ValueError("texture extension is unsupported by this import contract")
            for prim in primitives:
                if prim["material_index"] == index and prim["texcoord_accessor"] is None:
                    raise ValueError("textured primitive has no TEXCOORD_0")
            texture = _index(document.get("textures", []), info["index"], "texture")
            image_index = texture["source"]
            _index(document.get("images", []), image_index, "image")
            digest = _image_digest(document, image_index, payloads, root)
            textures.append(
                {
                    "material_index": index,
                    "slot": slot,
                    "colorspace": colorspace,
                    "image_index": image_index,
                    "texture_index": info["index"],
                    "texcoord": 0,
                    "source_uri": (
                        "data:<embedded>"
                        if str(document["images"][image_index].get("uri", "")).startswith("data:")
                        else document["images"][image_index].get("uri")
                    ),
                    "sha256": digest,
                    "mono_channel": channel,
                }
            )
    return {
        "requires_native": bool(textures) or len(used) > 1,
        "primitives": primitives,
        "materials": source_materials,
        "textures": textures,
        "triangle_counts": dict(counts),
        "scene_index": document.get("scene", 0),
    }


def _required_parm(node, name, value):
    parm = node.parm(name)
    if parm is None:
        raise RuntimeError("native glTF importer does not expose " + name)
    parm.set(value)
    if parm.eval() != value:
        raise RuntimeError("native glTF parameter readback mismatch: " + name)


def _colorspace(shader, slot, expected):
    for name in (slot + "_textureColorSpace", slot + "_texturecolorspace"):
        parm = shader.parm(name)
        if parm is None:
            continue
        accepted = {"srgb", "utility - srgb - texture"} if expected == "sRGB" else {"raw", "utility - raw"}
        initial = parm.evalAsString()
        if initial in parm.menuItems() and initial.lower() in accepted:
            return {
                "parameter": name,
                "value": initial,
                "initial_value": initial,
                "verified": True,
                "native_verified": True,
                "correction_applied": False,
            }
        for token in parm.menuItems():
            if token.lower() in accepted:
                parm.set(token)
                if parm.evalAsString() == token:
                    return {
                        "parameter": name,
                        "value": token,
                        "initial_value": initial,
                        "verified": True,
                        "native_verified": False,
                        "correction_applied": True,
                    }
    return {
        "verified": False,
        "reason": "native shader has no verified explicit " + expected + " texture color-space menu",
    }


def import_native_gltf(hou, filepath, node_name, parent_path, plan, texture_output_dir):
    """Build once with the native HDA; inspect the scene instead of trusting button delivery."""
    if not texture_output_dir or not os.path.isabs(texture_output_dir):
        raise ValueError("textured/multi-material glTF requires an absolute texture_output_dir")
    # Native extraction can overwrite files. Require a new directory, not a shared cache.
    parent = hou.node(parent_path)
    if parent is None:
        raise ValueError("native glTF parent does not exist")
    os.mkdir(texture_output_dir)
    importer = None
    try:
        importer = parent.createNode("gltf_hierarchy", node_name=node_name)
        for name, value in (
            ("filename", filepath),
            ("assetfolder", texture_output_dir),
            ("scene", str(plan["scene_index"])),
            ("flattenhierarchy", 1),
            ("importmaterials", 1),
            ("promotepointattrs", 1),
            ("lockgeo", 0),
        ):
            _required_parm(importer, name, value)
        button = importer.parm("buildscene")
        if button is None:
            raise RuntimeError("native glTF buildscene button unavailable")
        button.pressButton()
        descendants = list(importer.allSubChildren())
        shaders = [n for n in descendants if n.type().name() in ("principledshader", "principledshader::2.0")]
        by_index = {}
        problems = []
        factor_readback = []
        for source in plan["materials"]:
            matching = [n for n in shaders if source["native_name"] and n.name() == source["native_name"]]
            if len(matching) != 1:
                problems.append("cannot uniquely map source material index " + str(source["material_index"]))
                continue
            by_index[source["material_index"]] = matching[0]
            shader = matching[0]
            for name, expected in source["factors"].items():
                parm = shader.parmTuple(name) if isinstance(expected, list) else shader.parm(name)
                if parm is None:
                    problems.append("missing native PBR factor parameter " + name)
                    continue
                actual = parm.eval()
                wanted = expected if isinstance(expected, list) else [expected]
                observed = list(actual) if isinstance(actual, (tuple, list)) else [actual]
                verified = len(observed) == len(wanted) and all(abs(a - b) < 1e-6 for a, b in zip(observed, wanted))
                initial, native_verified = actual, verified
                if not verified:
                    parm.set(tuple(expected) if isinstance(expected, list) else expected)
                    actual = parm.eval()
                    observed = list(actual) if isinstance(actual, (tuple, list)) else [actual]
                    verified = len(observed) == len(wanted) and all(abs(a - b) < 1e-6 for a, b in zip(observed, wanted))
                factor_readback.append(
                    {
                        "material_index": source["material_index"],
                        "parameter": name,
                        "expected": expected,
                        "actual": actual,
                        "initial_value": initial,
                        "native_verified": native_verified,
                        "correction_attempted": not native_verified,
                        "correction_applied": not native_verified and verified,
                        "verified": verified,
                    }
                )
                if not verified:
                    problems.append("native PBR factor readback differs at " + name)
        assignments, observed_counts, uv_records = [], Counter(), []
        for node in descendants:
            if node.type().name() != "geo":
                continue
            display = node.displayNode()
            if display is None:
                continue
            display.cook(force=True)
            if display.errors():
                raise RuntimeError("native glTF geometry cook failed: " + str(display.errors()))
            geometry = display.geometry()
            uv = geometry.findVertexAttrib("uv") or geometry.findPointAttrib("uv")
            if plan["textures"] and uv is None:
                problems.append("native geometry lost UVs: " + display.path())
            uv_records.append({"node": display.path(), "uv_present": uv is not None})
            if geometry.findPrimAttrib("shop_materialpath") is None:
                problems.append("native geometry has no primitive material assignments")
                continue
            for primitive in geometry.prims():
                raw = primitive.attribValue("shop_materialpath")
                shader = display.node(raw) if raw and not raw.startswith("/") else hou.node(raw)
                path = shader.path() if shader is not None else raw
                observed_counts[path] += 1
        for index, shader in by_index.items():
            observed = observed_counts[shader.path()]
            expected = plan["triangle_counts"].get(index, 0)
            if observed != expected or not observed:
                problems.append("source/native primitive material count differs at index " + str(index))
            assignments.append(
                {
                    "material": shader.path(),
                    "source_material_index": index,
                    "primitive_count": observed,
                    "expected_primitive_count": expected,
                }
            )
        # Equal material totals cannot distinguish a swap between source faces.
        # The native HDA does not expose a verified source-face identity here.
        identity_verified = (
            len([n for n in plan["triangle_counts"].values() if n]) == 1
            and bool(by_index)
            and len(by_index) == len(plan["materials"])
            and all(
                observed_counts[shader.path()] == plan["triangle_counts"].get(index, 0)
                for index, shader in by_index.items()
            )
        )
        if not identity_verified:
            problems.append("source/native primitive material identity is unverified; counts alone are insufficient")
        if sum(observed_counts.values()) != sum(plan["triangle_counts"].values()):
            problems.append("source/native total primitive count differs")
            identity_verified = False
        known_materials = {shader.path() for shader in by_index.values()}
        if any(path not in known_materials for path in observed_counts):
            problems.append("native geometry has unexpected primitive material assignments")
            identity_verified = False
        textures = []
        for source in plan["textures"]:
            shader = by_index.get(source["material_index"])
            record = dict(source)
            record["verified"] = False
            if shader is not None:
                parm = shader.parm(source["slot"] + "_texture")
                path = parm.evalAsString() if parm is not None else ""
                record["path"] = path
                if path and os.path.isfile(path):
                    with open(path, "rb") as handle:
                        record["actual_sha256"] = hashlib.sha256(handle.read()).hexdigest()
                    record["verified"] = record["actual_sha256"] == source["sha256"]
                record["color_space_readback"] = _colorspace(shader, source["slot"], source["colorspace"])
                enable_name = (
                    "baseBumpAndNormal_enable" if source["slot"] == "baseNormal" else source["slot"] + "_useTexture"
                )
                enable = shader.parm(enable_name)
                record["enabled"] = enable is not None and bool(enable.eval())
                if source["mono_channel"] is not None:
                    channel = shader.parm(source["slot"] + "_monoChannel")
                    record["channel_verified"] = channel is not None and channel.eval() == source["mono_channel"]
                else:
                    record["channel_verified"] = True
            if not record["verified"] or not record.get("channel_verified") or not record.get("enabled"):
                problems.append(
                    "native texture/channel readback differs at material {0} slot {1}".format(
                        source["material_index"], source["slot"]
                    )
                )
            if not record.get("color_space_readback", {}).get("verified"):
                problems.append(
                    "unverified texture color space at material {0} slot {1}".format(
                        source["material_index"], source["slot"]
                    )
                )
            textures.append(record)
        if not observed_counts or len(by_index) != len(plan["materials"]):
            problems.append("native material/geometry readback incomplete")
        report = {
            "pbr_factor_readback": factor_readback,
            "material_mode": "as_authored",
            "status": "partial_native_materials" if problems else "as_authored",
            "native_importer": "gltf_hierarchy",
            "materials_detected": len(plan["materials"]),
            "materials_imported": len(by_index),
            "materials_lost": len(plan["materials"]) - len(by_index),
            "material_paths": [shader.path() for shader in by_index.values()],
            "material_assignments": assignments,
            "primitive_identity_verified": identity_verified,
            "primitive_assignment_verification": "aggregate_counts_only",
            "source_primitive_materials": plan["primitives"],
            "texture_bindings": textures,
            "uv_readback": uv_records,
            "unapplied_parameters": problems,
            "unapplied_required": problems,
            "texture_output_dir": texture_output_dir,
        }
        return [importer.path()] + [n.path() for n in descendants], report
    except Exception:
        if importer is not None:
            importer.destroy()
        # mkdir above proves ownership; rmdir removes only this attempt's empty directory.
        # Keep extracted files for inspection, and never delete another import's data.
        try:
            os.rmdir(texture_output_dir)
        except OSError:
            pass
        raise
