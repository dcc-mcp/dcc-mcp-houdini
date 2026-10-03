"""Best-effort material extraction/authoring for ``import_to_scene``.

The File-SOP import path used by :mod:`import_to_scene` carries geometry only:
Houdini does not rebuild the shading networks that live inside an interchange
carrier.  This module closes that gap for the carriers that can be decoded
without a third-party dependency (glTF/GLB, OBJ+MTL) and, when Houdini's
bundled USD bindings are importable, for USD carriers as well.

Everything here degrades gracefully: a decoder that cannot run simply reports
``supported=False`` so the caller can raise an explicit
``ImportWarningCode.MATERIAL_FALLBACK`` warning instead of silently dropping
the look of the asset.
"""

from __future__ import annotations

import json
import os
import re
import struct
from typing import Any, Dict, List, Optional, Tuple

# Material assignment parm on OBJ nodes.  ``houdini-lookdev`` reads exactly
# these two names when listing assignments, so binding through them keeps the
# import observable by ``list_assignments``.
MATERIAL_ASSIGN_PARMS = ("shop_materialpath", "shop_materialpath1")

# Shader node types to try, in priority order.
SHADER_TYPE_CANDIDATES = ("principledshader::2.0", "principledshader")

# Parm candidates per material channel.  The first name that exists on the
# created shader wins; unknown parms are reported instead of raising.
_BASE_COLOR_PARMS = ("basecolor", "baseColor", "basecolorr")
_METALLIC_PARMS = ("metallic", "metalness")
_ROUGHNESS_PARMS = ("rough", "roughness")
_EMISSIVE_PARMS = ("emitcolor", "emissivecolor", "emit")
_OPACITY_PARMS = ("opacity", "opac")

# Suffix -> decoder key, longest first so ``.usda`` beats ``.usd``.
_MATERIAL_SUFFIXES = (".gltf", ".glb", ".obj", ".usd", ".usda", ".usdc", ".usdz")

_GLB_MAGIC = 0x46546C67
_GLB_JSON_CHUNK = 0x4E4F534A


class CarrierUnreadableError(Exception):
    """Raised when a carrier declares materials that cannot be read.

    Distinct from "this carrier has no materials": the caller must warn when a
    declared look is lost, and stay quiet when there was nothing to carry.
    """


def _clamp01(value: Any, default: float = 0.0) -> float:
    """Coerce *value* to a float in [0, 1], falling back to *default*."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number:  # NaN
        return default
    return min(1.0, max(0.0, number))


def _rgb(value: Any, default: Optional[List[float]] = None) -> List[float]:
    """Coerce a 3- or 4-component colour to a clamped RGB triple.

    Accepts anything sequence-like: USD hands back ``Gf.Vec3f`` (iterable but
    not a ``list``/``tuple``), glTF hands back a plain JSON list.
    """
    components = _colour_components(value)
    if components is None or len(components) < 3:
        return list(default) if default else [1.0, 1.0, 1.0]
    # Round away float32 noise (USD stores colours as ``float`` triples).
    return [round(_clamp01(channel), 6) for channel in components[:3]]


def _colour_components(value: Any) -> Optional[List[float]]:
    """Return *value* as a list of floats, or ``None`` when it is not a colour."""
    if value is None or isinstance(value, (str, bytes)):
        return None
    if isinstance(value, (list, tuple)):
        return list(value)
    try:
        return list(value)  # Gf.Vec3f / VtArray / other iterable colour types
    except TypeError:
        return None


def detect_material_format(file_path: str, declared_format: Optional[str] = None) -> str:
    """Return the material carrier format for *file_path*.

    Prefers the file suffix (that is what the decoder has to read anyway) and
    falls back to the format declared on the ``AssetFileVariant``.
    """
    lowered = (file_path or "").lower()
    for suffix in sorted(_MATERIAL_SUFFIXES, key=len, reverse=True):
        if lowered.endswith(suffix):
            return suffix.lstrip(".")
    declared = (declared_format or "").lower()
    if declared in {suffix.lstrip(".") for suffix in _MATERIAL_SUFFIXES}:
        return declared
    return ""


# ---------------------------------------------------------------------------
# Decoders: each returns a list of material specs (plain dicts).
# ---------------------------------------------------------------------------


def _material_spec(
    name: str,
    base_color: Optional[List[float]] = None,
    metallic: float = 0.0,
    roughness: float = 0.5,
    emissive: Optional[List[float]] = None,
    opacity: float = 1.0,
) -> Dict[str, Any]:
    return {
        "name": name,
        "base_color": list(base_color) if base_color else [0.8, 0.8, 0.8],
        "metallic": _clamp01(metallic),
        "roughness": _clamp01(roughness, 0.5),
        "emissive": list(emissive) if emissive else None,
        "opacity": _clamp01(opacity, 1.0),
    }


def _read_gltf_json(file_path: str) -> Optional[Dict[str, Any]]:
    """Return the glTF JSON document for a ``.gltf`` or ``.glb`` file."""
    with open(file_path, "rb") as handle:
        head = handle.read(4)
        if len(head) < 4:
            return None
        if struct.unpack("<I", head)[0] != _GLB_MAGIC:
            handle.seek(0)
            return json.loads(handle.read().decode("utf-8", "replace"))

        # Binary container: header (magic, version, length) then chunks.
        handle.seek(0)
        blob = handle.read()
    if len(blob) < 20:
        return None
    offset = 12
    while offset + 8 <= len(blob):
        chunk_length, chunk_type = struct.unpack_from("<II", blob, offset)
        if chunk_length < 0 or offset + 8 + chunk_length > len(blob):
            return None
        if chunk_type == _GLB_JSON_CHUNK:
            payload = blob[offset + 8 : offset + 8 + chunk_length]
            return json.loads(payload.decode("utf-8", "replace"))
        offset += 8 + chunk_length
    return None


def _decode_gltf(file_path: str) -> Optional[List[Dict[str, Any]]]:
    """Extract PBR material specs from a glTF/GLB carrier.

    Returns ``None`` when the carrier simply declares no materials, and raises
    :class:`CarrierUnreadableError` when it references materials that are not
    there (a mesh pointing at an out-of-range material index).
    """
    document = _read_gltf_json(file_path)
    if not isinstance(document, dict):
        return None

    # Only keep materials that are actually referenced by a mesh primitive:
    # unreferenced definitions are not part of the imported look.
    used_indexes = set()
    for mesh in document.get("meshes") or []:
        for primitive in mesh.get("primitives") or []:
            material_index = primitive.get("material")
            if isinstance(material_index, int) and material_index >= 0:
                used_indexes.add(material_index)

    raw_materials = document.get("materials") or []
    if not raw_materials:
        return None

    dangling = sorted(index for index in used_indexes if index >= len(raw_materials))
    if dangling:
        raise CarrierUnreadableError(
            "glTF mesh references material index(es) {0} but the carrier defines only {1} material(s)".format(
                ", ".join(str(i) for i in dangling), len(raw_materials)
            )
        )

    specs: List[Dict[str, Any]] = []
    for index, raw in enumerate(raw_materials):
        if used_indexes and index not in used_indexes:
            continue
        pbr = raw.get("pbrMetallicRoughness") or {}
        name = str(raw.get("name") or "material_{0}".format(index))
        base_color_factor = pbr.get("baseColorFactor")
        alpha = None
        if isinstance(base_color_factor, (list, tuple)) and len(base_color_factor) > 3:
            alpha = _clamp01(base_color_factor[3], 1.0)
        opacity = alpha if alpha is not None else (1.0 if raw.get("alphaMode", "OPAQUE") == "OPAQUE" else 0.5)
        specs.append(
            _material_spec(
                name=name,
                base_color=_rgb(base_color_factor, [1.0, 1.0, 1.0]),
                metallic=pbr.get("metallicFactor", 0.0),
                roughness=pbr.get("roughnessFactor", 1.0),
                emissive=_rgb(raw.get("emissiveFactor"), [0.0, 0.0, 0.0]) if raw.get("emissiveFactor") else None,
                opacity=opacity,
            )
        )
    return specs


def _parse_mtl(mtl_path: str) -> Dict[str, Dict[str, Any]]:
    """Parse a Wavefront ``.mtl`` file into raw material records."""
    materials: Dict[str, Dict[str, Any]] = {}
    current: Optional[Dict[str, Any]] = None
    try:
        with open(mtl_path, "r", errors="replace") as handle:
            lines = handle.read().splitlines()
    except OSError:
        return materials

    for line in lines:
        tokens = line.strip().split()
        if not tokens or tokens[0].startswith("#"):
            continue
        # Exact keyword match: ``mtllibX`` / an indented ``usemtl`` must not be
        # mistaken for the real thing.
        keyword, values = tokens[0].lower(), tokens[1:]
        if keyword == "newmtl" and values:
            current = {"name": values[0], "Kd": [0.8, 0.8, 0.8], "Ks": [0.0, 0.0, 0.0], "Ns": 10.0, "d": 1.0}
            materials[values[0]] = current
        elif current is None:
            continue
        elif keyword in ("kd", "ks") and len(values) >= 3:
            current["Kd" if keyword == "kd" else "Ks"] = [_clamp01(v, 0.0) for v in values[:3]]
        elif keyword == "ns" and values:
            try:
                current["Ns"] = min(1000.0, max(0.0, float(values[0])))
            except ValueError:
                current["Ns"] = 10.0
        elif keyword in ("d", "tr") and values:
            try:
                alpha = float(values[0])
            except ValueError:
                alpha = 1.0
            current["d"] = alpha if keyword == "d" else 1.0 - alpha
    return materials


def _phong_to_roughness(shininess: float) -> float:
    """Convert a Phong ``Ns`` exponent into a perceptual roughness."""
    exponent = max(2.0, float(shininess))
    return _clamp01((2.0 / (exponent + 2.0)) ** 0.5, 1.0)


def _decode_obj(obj_path: str) -> Optional[List[Dict[str, Any]]]:
    """Extract material specs from an OBJ + MTL pair.

    Returns ``None`` when the OBJ declares no ``mtllib`` (nothing to carry).
    Raises :class:`CarrierUnreadableError` when it declares materials that
    cannot be read: an unreadable OBJ, a missing/unparsable ``.mtl`` sidecar,
    or a ``usemtl`` name with no matching definition.
    """
    try:
        with open(obj_path, "r", errors="replace") as handle:
            lines = handle.read().splitlines()
    except OSError as exc:
        raise CarrierUnreadableError("OBJ carrier could not be read: {0}".format(exc)) from exc

    mtl_names: List[str] = []
    used: List[str] = []
    for line in lines:
        tokens = line.strip().split()
        if not tokens:
            continue
        keyword = tokens[0].lower()
        if keyword == "mtllib":
            mtl_names.extend(tokens[1:])
        elif keyword == "usemtl" and len(tokens) > 1:
            name = tokens[1]
            if name not in used:
                used.append(name)
    if not mtl_names:
        return None

    base_dir = os.path.dirname(os.path.abspath(obj_path))
    records: Dict[str, Dict[str, Any]] = {}
    missing: List[str] = []
    for mtl_name in mtl_names:
        mtl_path = os.path.join(base_dir, os.path.basename(mtl_name))
        if not os.path.isfile(mtl_path):
            missing.append(mtl_name)
            continue
        parsed = _parse_mtl(mtl_path)
        if not parsed:
            missing.append(mtl_name)
            continue
        records.update(parsed)

    if not records:
        detail = (
            "mtllib sidecar(s) not found: {0}".format(", ".join(missing))
            if missing
            else "the sidecar defines no material"
        )
        raise CarrierUnreadableError("OBJ declares mtllib {0} but {1}".format(", ".join(mtl_names), detail))

    unknown = [name for name in used if name not in records]
    if unknown:
        raise CarrierUnreadableError(
            "usemtl {0} has no matching definition in {1}".format(", ".join(unknown), ", ".join(mtl_names))
        )

    ordered = used or sorted(records)
    specs: List[Dict[str, Any]] = []
    for name in ordered:
        record = records.get(name)
        if not record:
            continue
        specular = record.get("Ks") or [0.0, 0.0, 0.0]
        metallic = _clamp01(max(specular) * 0.9)
        specs.append(
            _material_spec(
                name=str(record.get("name") or name),
                base_color=_rgb(record.get("Kd"), [0.8, 0.8, 0.8]),
                metallic=metallic,
                roughness=_phong_to_roughness(record.get("Ns", 10.0)),
                opacity=record.get("d", 1.0),
            )
        )
    return specs


def _surface_shader(material: Any, UsdShade: Any) -> Optional[Any]:
    """Return the surface :class:`UsdShade.Shader` bound to *material*.

    ``ComputeSurfaceSource()`` is version-fragile: modern USD returns the
    3-tuple ``(shader, sourceName, attributeType)`` while older builds return
    the shader (or its prim) directly.  Handle every shape instead of letting
    the difference swallow every material in the stage.
    """
    try:
        source = material.ComputeSurfaceSource()
    except TypeError:
        try:
            source = material.ComputeSurfaceSource("universal")
        except Exception:  # noqa: BLE001
            return None
    except Exception:  # noqa: BLE001
        return None

    if isinstance(source, (tuple, list)):
        source = source[0] if source else None
    if source is None:
        return None
    if hasattr(source, "GetInput"):
        return source
    try:
        return UsdShade.Shader(source.GetPrim() if hasattr(source, "GetPrim") else source)
    except Exception:  # noqa: BLE001
        return None


def _shader_spec(shader: Any, name: str) -> Dict[str, Any]:
    """Translate a UsdPreviewSurface-style *shader* into a material spec.

    Kept free of ``pxr`` imports so it can be exercised with plain doubles:
    USD hands back ``Gf.Vec3f`` colours and ``UsdShade.Input`` objects whose
    ``Get()`` returns ``None`` for inputs that are not authored.
    """

    def _input(input_name: str, default: Any = None) -> Any:
        try:
            shader_input = shader.GetInput(input_name)
            if shader_input is None:
                return default
            value = shader_input.Get()
            return default if value is None else value
        except Exception:  # noqa: BLE001
            return default

    emissive = _input("emissiveColor")
    return _material_spec(
        name=name,
        base_color=_rgb(_input("diffuseColor", [0.8, 0.8, 0.8]), [0.8, 0.8, 0.8]),
        metallic=_input("metallic", 0.0),
        roughness=_input("roughness", 0.5),
        emissive=_rgb(emissive, [0.0, 0.0, 0.0]) if emissive else None,
        opacity=_input("opacity", 1.0),
    )


def _decode_usd(file_path: str) -> Optional[List[Dict[str, Any]]]:
    """Extract UsdPreviewSurface material specs from a USD carrier.

    Uses Houdini's bundled ``pxr`` bindings when available.  Returns ``None``
    when USD cannot be inspected at all.
    """
    try:
        from pxr import Usd, UsdShade  # type: ignore[import-not-found]  # noqa: PLC0415
    except Exception:  # noqa: BLE001 - pxr is optional and version-fragile
        return None

    try:
        stage = Usd.Stage.Open(file_path)
        if stage is None:
            return None
    except Exception:  # noqa: BLE001
        return None

    specs: List[Dict[str, Any]] = []
    unresolved: List[str] = []
    for prim in stage.Traverse():
        try:
            if not prim.IsA(UsdShade.Material):
                continue
            name = str(prim.GetName() or "material")
            shader = _surface_shader(UsdShade.Material(prim), UsdShade)
            if shader is None:
                unresolved.append(name)
                continue
            specs.append(_shader_spec(shader, name))
        except Exception:  # noqa: BLE001 - skip prims we cannot interpret
            try:
                unresolved.append(str(prim.GetName() or "material"))
            except Exception:  # noqa: BLE001
                unresolved.append("<unnamed>")

    if not specs and unresolved:
        # The stage declares materials whose shading we could not resolve —
        # that is a lost look, not an asset without materials.
        raise CarrierUnreadableError(
            "USD declares material(s) {0} but no surface shader could be resolved".format(", ".join(unresolved))
        )
    return specs


_DECODERS = {
    "gltf": _decode_gltf,
    "glb": _decode_gltf,
    "obj": _decode_obj,
    "usd": _decode_usd,
    "usda": _decode_usd,
    "usdc": _decode_usd,
    "usdz": _decode_usd,
}


def decode_materials_report(file_path: str, material_format: str) -> Tuple[Optional[List[Dict[str, Any]]], str, str]:
    """Decode the materials carried by *file_path*.

    Returns ``(specs, status, detail)`` where ``status`` is one of:

    ``"decoded"``
        Materials were found and decoded.
    ``"no_materials"``
        The carrier was read and simply carries no materials (no warning).
    ``"carrier_unreadable"``
        The carrier declares materials that could not be read — the caller
        must warn, this is a lost look.
    ``"decode_failed"``
        The carrier could not be decoded at all.
    ``"unsupported_format"``
        This adapter has no material path for the format.

    ``detail`` carries the decoder's own explanation (empty when there is
    nothing more to say) so warnings can name the actual cause.
    """
    decoder = _DECODERS.get(material_format)
    if decoder is None:
        return None, "unsupported_format", ""
    try:
        specs = decoder(file_path)
    except CarrierUnreadableError as exc:
        return None, "carrier_unreadable", str(exc)
    except Exception as exc:  # noqa: BLE001 - a broken carrier must not fail the import
        return None, "decode_failed", "{0}: {1}".format(type(exc).__name__, exc)
    if not specs:
        return None, "no_materials", ""
    return specs, "decoded", ""


def decode_materials(file_path: str, material_format: str) -> Tuple[Optional[List[Dict[str, Any]]], str]:
    """Decode the materials carried by *file_path*.

    Returns ``(specs, status)``; see :func:`decode_materials_report` for the
    status vocabulary.
    """
    specs, status, _detail = decode_materials_report(file_path, material_format)
    return specs, status


# ---------------------------------------------------------------------------
# Houdini authoring
# ---------------------------------------------------------------------------


def _set_first_parm(node: Any, names: Any, value: Any) -> Optional[str]:
    """Set the first existing parm (scalar or tuple) in *names*."""
    for name in names:
        parm_tuple = node.parmTuple(name) if hasattr(node, "parmTuple") else None
        if parm_tuple is not None:
            try:
                parm_tuple.set(tuple(value))
                return name
            except Exception:  # noqa: BLE001
                continue
        parm = node.parm(name) if hasattr(node, "parm") else None
        if parm is None:
            continue
        try:
            parm.set(value[0] if isinstance(value, (list, tuple)) and len(value) == 1 else value)
            return name
        except Exception:  # noqa: BLE001
            continue
    return None


def _safe_name(name: str, fallback: str) -> str:
    """Return a Houdini-safe node name."""
    cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", str(name or "").strip()) or fallback
    if cleaned[0].isdigit():
        cleaned = "m_" + cleaned
    return cleaned


def _ensure_material_network(hou: Any, parent_path: str) -> Optional[Any]:
    """Return the material network at *parent_path*, creating it when needed."""
    network = hou.node(parent_path)
    if network is not None:
        return network
    try:
        root = hou.node("/") if hou.node("/") is not None else None
        if root is None:
            return None
        network = root.createNode("matnet", parent_path.strip("/") or "mat")
    except Exception:  # noqa: BLE001
        return None
    return network


def _create_shader(network: Any, spec: Dict[str, Any], node_name: str) -> Tuple[Optional[Any], List[str], List[str]]:
    """Create one shader node for *spec*.

    Returns ``(node, unapplied_required, unapplied_optional)``.  Required
    channels are the ones that define the base look; when one of them cannot be
    applied the material is materially wrong and the caller must warn.
    """
    material = None
    for shader_type in SHADER_TYPE_CANDIDATES:
        try:
            material = network.createNode(shader_type, node_name=node_name)
        except Exception:  # noqa: BLE001
            material = None
        if material is not None:
            break
    if material is None:
        return None, [], []

    unapplied_required: List[str] = []
    unapplied_optional: List[str] = []
    channels = (
        ("base_color", _BASE_COLOR_PARMS, spec.get("base_color"), True),
        ("metallic", _METALLIC_PARMS, spec.get("metallic"), True),
        ("roughness", _ROUGHNESS_PARMS, spec.get("roughness"), True),
        ("opacity", _OPACITY_PARMS, spec.get("opacity"), False),
    )
    for channel, parm_names, value, required in channels:
        if value is None:
            continue
        if _set_first_parm(material, parm_names, value) is None:
            (unapplied_required if required else unapplied_optional).append(channel)

    emissive = spec.get("emissive")
    if emissive and any(emissive):
        if _set_first_parm(material, _EMISSIVE_PARMS, emissive) is None:
            unapplied_optional.append("emissive")

    try:
        material.setComment("dcc_mcp_source_material: {0}".format(spec.get("name", "")))
    except Exception:  # noqa: BLE001
        pass
    return material, unapplied_required, unapplied_optional


def _assign_material(container: Any, material_path: str) -> Optional[str]:
    """Bind *material_path* to the geometry container; return the parm used."""
    for parm_name in MATERIAL_ASSIGN_PARMS:
        parm = container.parm(parm_name) if hasattr(container, "parm") else None
        if parm is None:
            continue
        try:
            parm.set(material_path)
            return parm_name
        except Exception:  # noqa: BLE001
            continue
    return None


def build_materials(
    hou: Any,
    specs: List[Dict[str, Any]],
    container: Any,
    parent_path: str = "/mat",
    name_prefix: str = "",
) -> Dict[str, Any]:  # noqa: PLR0913 - explicit report/knobs beat a kwargs blob
    """Create Houdini material nodes for *specs* and bind them to *container*.

    Returns a report dict with ``created`` (list of node paths), ``assigned``
    (list of ``{object, material}`` pairs), ``unapplied`` (every channel the
    shader did not expose, as ``"<material path>:<channel>"``) and
    ``unapplied_required`` (the subset that changes the base look).
    """
    report: Dict[str, Any] = {"created": [], "assigned": [], "unapplied": [], "unapplied_required": []}
    if not specs or container is None:
        return report

    network = _ensure_material_network(hou, parent_path)
    if network is None:
        return report

    used_names = set()
    for index, spec in enumerate(specs):
        node_name = _safe_name("{0}{1}".format(name_prefix, spec.get("name") or ""), "material_{0}".format(index))
        while node_name in used_names:
            node_name = node_name + "_1"
        used_names.add(node_name)

        material, unapplied_required, unapplied_optional = _create_shader(network, spec, node_name)
        if material is None:
            continue
        material_path = material.path()
        report["created"].append(material_path)
        for channel in list(unapplied_required) + list(unapplied_optional):
            report["unapplied"].append("{0}:{1}".format(material_path, channel))
        for channel in unapplied_required:
            report["unapplied_required"].append("{0}:{1}".format(material_path, channel))

    if report["created"] and container is not None:
        parm_name = _assign_material(container, report["created"][0])
        if parm_name:
            report["assigned"].append({"object": container.path(), "material": report["created"][0], "parm": parm_name})
    return report
