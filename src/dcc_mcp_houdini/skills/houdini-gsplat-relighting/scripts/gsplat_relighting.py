"""Typed Houdini 22 GSplat relighting setup and preflight tools."""

from __future__ import annotations

import math
import os
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from dcc_mcp_core.skill import skill_entry, skill_error, skill_success


def _node(hou: Any, path: str) -> Any:
    if not str(path or "").startswith("/"):
        raise ValueError("node paths must be absolute")
    value = hou.node(path)
    if value is None:
        raise ValueError("Houdini node not found: {}".format(path))
    return value


def _type_name(node: Any) -> str:
    type_obj = node.type()
    return type_obj.name() if hasattr(type_obj, "name") else str(type_obj)


def _summary(node: Any) -> dict:
    return {"path": node.path(), "name": node.name(), "type": _type_name(node)}


def _safe_public_error(message: str, error: str, exc: Exception) -> dict:
    """Return a public failure without exception repr, traceback, or host paths."""
    return skill_error(message, error, error_type=type(exc).__name__)


_GSPLAT_BRIDGE_ATTRIBUTES = (
    "P",
    "Cd",
    "albedo",
    "N",
    "orient",
    "scale",
    "pscale",
    "GS_Alpha",
    "Alpha",
    "alpha",
    "GS_SPH_R",
    "GS_SPH_G",
    "GS_SPH_B",
    "ao",
)


def _attributes(geometry: Any, limit: int) -> List[dict]:
    output = []
    for attrib in list(geometry.pointAttribs())[:limit]:
        name = attrib.name()
        data_type = getattr(attrib, "dataType", lambda: None)()
        output.append(
            {
                "name": name,
                "owner": "point",
                "data_type": data_type.name() if hasattr(data_type, "name") else str(data_type or ""),
                "size": getattr(attrib, "size", lambda: None)(),
            }
        )
    return output


def _names(attributes: Iterable[dict]) -> set:
    return {item["name"] for item in attributes}


def _has_expanded_attribute(names: set, base: str, count: int) -> bool:
    """Accept the expanded PLY spellings emitted by common 3DGS exporters."""
    return any(
        all("{}{}{}".format(base, separator, index) in names for index in range(count)) for separator in ("", "_")
    )


def _gsplat_schema(names: set) -> dict:
    native_checks = {
        "position": "P" in names,
        "color_or_albedo": bool({"Cd", "albedo"} & names),
        "normal": "N" in names,
        "orientation": "orient" in names,
        "scale": bool({"scale", "pscale"} & names),
        "opacity": bool({"GS_Alpha", "Alpha", "alpha"} & names),
        "spherical_harmonics": {"GS_SPH_R", "GS_SPH_G", "GS_SPH_B"}.issubset(names),
        "ambient_occlusion": "ao" in names,
    }
    raw_checks = {
        "position": "P" in names,
        "color": "f_dc" in names or _has_expanded_attribute(names, "f_dc", 3),
        "orientation": "rot" in names or _has_expanded_attribute(names, "rot", 4),
        "scale": "scale" in names or _has_expanded_attribute(names, "scale", 3),
        "opacity": "opacity" in names,
        "spherical_harmonics": "f_rest" in names or _has_expanded_attribute(names, "f_rest", 45),
    }
    raw_core = all(raw_checks[key] for key in ("position", "color", "orientation", "scale", "opacity"))
    native_core = all(native_checks[key] for key in ("position", "color_or_albedo", "orientation", "scale", "opacity"))
    if native_core:
        source_schema = "houdini_gsplat"
    elif raw_core:
        source_schema = "standard_3dgs_ply"
    else:
        source_schema = "unknown"
    return {
        "source_schema": source_schema,
        "native_checks": native_checks,
        "raw_checks": raw_checks,
        "normalization_required": source_schema == "standard_3dgs_ply",
        "normalization_available": raw_core,
    }


def _find_node_type(parent: Any, aliases: Sequence[str]) -> str:
    category = parent.childTypeCategory()
    available = category.nodeTypes()
    for alias in aliases:
        if alias in available:
            return alias
    wanted = {_operator_base_name(alias) for alias in aliases}
    for name in available:
        if _operator_base_name(name) in wanted:
            return name
    raise ValueError(
        "Required Houdini node type is unavailable; install/enable the matching "
        "SideFX Labs or Houdini build. Tried: {}".format(", ".join(aliases))
    )


def _operator_base_name(type_name: str) -> str:
    """Return the operator name from namespace::name::version type names."""
    parts = str(type_name).split("::")
    if len(parts) > 1 and parts[-1].replace(".", "").isdigit():
        return parts[-2]
    return parts[-1]


def _normalized_name(value: str) -> str:
    return "".join(character for character in str(value).lower() if character.isalnum())


def _menu_value(parm: Any, value: Any) -> Any:
    """Translate a human-readable menu label to Houdini's menu token."""
    if not isinstance(value, str):
        return value
    template = parm.parmTemplate()
    items = list(getattr(template, "menuItems", lambda: ())())
    labels = list(getattr(template, "menuLabels", lambda: ())())
    if not items or value in items:
        return value
    wanted = _normalized_name(value)
    for item, label in zip(items, labels):
        if _normalized_name(label) == wanted:
            return item
    return value


def _set_first(node: Any, names: Sequence[str], value: Any) -> Optional[str]:
    for name in names:
        parm = node.parm(name)
        tuple_parm = node.parmTuple(name) if isinstance(value, (list, tuple)) else None
        if tuple_parm is not None:
            tuple_parm.set(tuple(value))
            return name
        if parm is not None:
            parm.set(_menu_value(parm, value))
            return name
    wanted = {_normalized_name(name) for name in names}
    candidates = []
    for parm_tuple in getattr(node, "parmTuples", lambda: ())():
        template = parm_tuple.parmTemplate()
        keys = {_normalized_name(parm_tuple.name()), _normalized_name(template.label())}
        if wanted & keys:
            candidates.append(parm_tuple)
    candidates.sort(key=lambda item: "_control_" in item.name())
    for parm_tuple in candidates:
        if isinstance(value, (list, tuple)):
            if len(parm_tuple) != len(value):
                continue
            parm_tuple.set(tuple(value))
            return parm_tuple.name()
        if len(parm_tuple) != 1:
            continue
        parm = parm_tuple[0]
        try:
            parm.set(_menu_value(parm, value))
            return parm.name()
        except Exception:  # noqa: BLE001 - try the next semantic H22 parameter match.
            continue
    return None


def _apply_parameters(node: Any, parameters: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    applied, unsupported = [], []
    for name, value in (parameters or {}).items():
        selected = _set_first(node, [str(name)], value)
        (applied if selected else unsupported).append(str(name))
    return applied, unsupported


def _create(parent: Any, aliases: Sequence[str], name: str) -> Any:
    return parent.createNode(
        _find_node_type(parent, aliases),
        node_name=name,
        exact_type_name=True,
    )


def _resolve_parm(node: Any, keys: Sequence[str], value: Any) -> Optional[str]:
    return _set_first(node, keys, value)


@skill_entry
def inspect_gsplat_relighting_input(
    node_path: str,
    max_attributes: int = 128,
    provenance_type: str = "unknown",
    source_view_count: int = 0,
    camera_poses_solved: bool = False,
    public_showcase: bool = False,
) -> dict:
    """Report the point attributes used by the Labs GSplat workflow."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")
    try:
        if isinstance(max_attributes, bool) or not 1 <= int(max_attributes) <= 256:
            raise ValueError("max_attributes must be between 1 and 256")
        source = _node(hou, node_path)
        geometry = source.geometry()
        attributes = _attributes(geometry, int(max_attributes))
        names = _names(attributes)
        provenance_type = str(provenance_type or "unknown").lower()
        allowed_provenance = {"captured", "synthetic", "unknown"}
        if provenance_type not in allowed_provenance:
            raise ValueError("provenance_type must be captured, synthetic, or unknown")
        if isinstance(source_view_count, bool) or int(source_view_count) < 0:
            raise ValueError("source_view_count must be a non-negative integer")
        has_capture_type = provenance_type == "captured"
        has_enough_views = int(source_view_count) >= 3
        captured_provenance = has_capture_type and has_enough_views and bool(camera_poses_solved)
        showcase_provenance_pass = captured_provenance or not bool(public_showcase)
        schema = _gsplat_schema(names)
        checks = schema["native_checks"]
        missing = [key for key, present in checks.items() if not present and key in ("position", "color_or_albedo")]
        ready_for_preparation = schema["source_schema"] in ("houdini_gsplat", "standard_3dgs_ply")
        return skill_success(
            "Inspected GSplat relighting input",
            source=_summary(source),
            point_count=int(geometry.pointCount()),
            primitive_count=int(geometry.primCount()),
            point_attributes=attributes,
            checks=checks,
            raw_checks=schema["raw_checks"],
            source_schema=schema["source_schema"],
            normalization_required=schema["normalization_required"],
            normalization_available=schema["normalization_available"],
            recommended_normalizer="bakegsplat" if schema["normalization_required"] else None,
            ready_for_preparation=ready_for_preparation,
            ready_for_relighting=not missing and showcase_provenance_pass,
            blocking_missing=missing + ([] if showcase_provenance_pass else ["captured_gsplat_provenance"]),
            provenance={
                "type": provenance_type,
                "source_view_count": int(source_view_count),
                "camera_poses_solved": bool(camera_poses_solved),
                "captured_gsplat": captured_provenance,
                "public_showcase_pass": showcase_provenance_pass,
            },
            recommendations=[
                "Run Labs Normals from GSplats when N is absent.",
                "Run Labs Delight GSplats when albedo is absent or captured lighting must be removed.",
                "Preserve GS_SPH_R/G/B when view-dependent captured appearance matters.",
                "Run Houdini Bake GSplats before Labs when source_schema is standard_3dgs_ply.",
                "Do not label procedural point sampling as captured GSplat reconstruction.",
            ],
        )
    except Exception as exc:
        return _safe_public_error("Failed to inspect GSplat input", "Houdini GSplat inspection failed", exc)


@skill_entry
def prepare_gsplat_sop_chain(
    node_path: str,
    create_normals: bool = True,
    create_albedo: bool = True,
    normalize_input: bool = True,
    preserve_spherical_harmonics: bool = True,
    name_prefix: str = "gsplat_relight",
    cook: bool = True,
) -> dict:
    """Append Labs GSplat preparation SOPs with rollback on failure."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")
    created = []
    try:
        source = _node(hou, node_path)
        parent = source.parent()
        if parent is None or not hasattr(parent, "createNode"):
            raise ValueError("node_path must identify a SOP inside an editable network")
        stages = []
        if create_normals:
            stages.append(("normals", ("labs::normals_from_gsplats", "labs::normals_from_gsplats::1.0")))
        if create_albedo:
            stages.append(("delight", ("labs::delight_gsplats", "labs::delight_gsplats::1.0")))
        if not stages:
            raise ValueError("At least one of create_normals/create_albedo must be true")
        current = source
        names = {attrib.name() for attrib in source.geometry().pointAttribs()}
        schema = _gsplat_schema(names)
        normalizer = None
        convert_spherical_harmonics = False
        if schema["normalization_required"]:
            if not normalize_input:
                raise ValueError("Standard 3DGS PLY attributes require Houdini Bake GSplats before Labs processing")
            bake = _create(parent, ("bakegsplat",), "{}_bake".format(name_prefix))
            created.append(bake)
            bake.setInput(0, current)
            convert_spherical_harmonics = bool(
                preserve_spherical_harmonics and schema["raw_checks"]["spherical_harmonics"]
            )
            _set_first(bake, ("sphcoeff",), convert_spherical_harmonics)
            current = bake
            normalizer = _summary(bake)
        for suffix, aliases in stages:
            child = _create(parent, aliases, "{}_{}".format(name_prefix, suffix))
            created.append(child)
            child.setInput(0, current)
            current = child
        if hasattr(parent, "layoutChildren"):
            parent.layoutChildren(items=created)
        if cook:
            current.cook(force=False)
        return skill_success(
            "Prepared GSplat SOP chain",
            source=_summary(source),
            nodes=[_summary(item) for item in created],
            output=_summary(current),
            source_schema=schema["source_schema"],
            normalized_input=normalizer is not None,
            normalizer=normalizer,
            output_attributes=(
                (["Cd", "orient", "scale", "GS_Alpha"] if normalizer else [])
                + (["GS_SPH_R", "GS_SPH_G", "GS_SPH_B"] if normalizer and convert_spherical_harmonics else [])
                + [name for name, enabled in (("N", create_normals), ("albedo", create_albedo)) if enabled]
            ),
            cooked=bool(cook),
        )
    except Exception as exc:
        for item in reversed(created):
            try:
                item.destroy()
            except Exception:  # noqa: BLE001
                pass
        return _safe_public_error(
            "Failed to prepare GSplat SOP chain; created nodes were rolled back",
            "Houdini GSplat SOP preparation failed",
            exc,
        )


@skill_entry
def create_gsplat_relight_lop(
    lop_node_path: str,
    camera_path: Optional[str] = None,
    collision_path: Optional[str] = None,
    enable_shadows: bool = True,
    shadow_bias: Optional[float] = None,
    lights: Optional[List[Dict[str, Any]]] = None,
    parameters: Optional[Dict[str, Any]] = None,
    create_sop_bridge: bool = True,
) -> dict:
    """Create USD lights and a Labs Relight GSplats LOP."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")
    created = []
    try:
        source = _node(hou, lop_node_path)
        parent = source.parent()
        if parent is None or not hasattr(parent, "createNode"):
            raise ValueError("lop_node_path must identify an editable Solaris network")
        current = source
        light_results = []
        for index, spec in enumerate(lights or []):
            name = str(spec.get("name") or "gsplat_light_{}".format(index + 1))
            light_type = str(spec.get("type", "Distant"))
            node_aliases = ("domelight::3.0", "domelight") if light_type == "Dome" else ("light",)
            light = _create(parent, node_aliases, name)
            created.append(light)
            light.setInput(0, current)
            applied, unsupported = [], []
            values = {
                "prim_path": spec.get("prim_path", "/World/GSplatRelight/{}".format(name)),
                "light_type": None if light_type == "Dome" else light_type,
                "intensity": spec.get("intensity"),
                "exposure": spec.get("exposure"),
                "color": spec.get("color"),
                "environment_texture": spec.get("environment_texture"),
            }
            candidates = {
                "prim_path": ("primpath", "prim_path"),
                "light_type": ("lighttype", "light_type"),
                "intensity": ("intensity",),
                "exposure": ("exposure",),
                "color": ("color",),
                "environment_texture": ("env_map", "environment_texture", "texture"),
            }
            for key, value in values.items():
                if value is None:
                    continue
                selected = _resolve_parm(light, candidates[key], value)
                (applied if selected else unsupported).append(key)
            light_results.append({"node": _summary(light), "applied": applied, "unsupported": unsupported})
            current = light
        relight = _create(parent, ("labs::relight_gsplats", "labs::relight_gsplats::1.0"), "gsplat_relight")
        created.append(relight)
        relight.setInput(0, current)
        if collision_path:
            relight.setInput(1, _node(hou, collision_path))
        applied, unsupported = [], []
        controls = dict(parameters or {})
        controls.setdefault("enable_shadows", enable_shadows)
        if shadow_bias is not None:
            controls.setdefault("shadow_bias", shadow_bias)
            controls.setdefault("overwrite_shadow_bias", True)
        if camera_path:
            controls.setdefault("camera", camera_path)
        aliases = {
            "enable_shadows": ("enableshadows", "enable_shadows"),
            "shadow_bias": ("shadowbias", "shadow_bias"),
            "overwrite_shadow_bias": ("overwriteshadowbias", "overwrite_shadow_bias"),
            "camera": ("camera", "rendercamera", "render_camera"),
        }
        for key, value in controls.items():
            selected = _resolve_parm(relight, aliases.get(key, (str(key),)), value)
            (applied if selected else unsupported).append(key)
        if hasattr(parent, "layoutChildren"):
            parent.layoutChildren(items=created)
        bridge_contract = {
            "sop_bridge_available": False,
            "sop_output_path": None,
            "point_count": 0,
            "gsplat_attributes": [],
            "bridge_refreshed": False,
            "sop_bridge_status": "disabled",
            "sop_bridge_error_type": None,
        }
        if create_sop_bridge:
            try:
                bridge_contract = _build_or_refresh_relight_sop_bridge(hou, relight, force=True)
            except ValueError as exc:
                bridge_contract["sop_bridge_status"] = "compatible_sop_output_not_available"
                bridge_contract["sop_bridge_error_type"] = type(exc).__name__
            except Exception as exc:  # noqa: BLE001
                bridge_contract["sop_bridge_status"] = "bridge_refresh_failed"
                bridge_contract["sop_bridge_error_type"] = type(exc).__name__
        return skill_success(
            "Created GSplat Solaris relighting stage",
            input=_summary(source),
            lights=light_results,
            relight=_summary(relight),
            applied_parameters=applied,
            unsupported_parameters=unsupported,
            output_attributes=["Cd", "GS_SPH_R", "GS_SPH_G", "GS_SPH_B"],
            **bridge_contract,
        )
    except Exception as exc:
        for item in reversed(created):
            try:
                item.destroy()
            except Exception:  # noqa: BLE001
                pass
        return _safe_public_error(
            "Failed to create GSplat Solaris relighting stage; created nodes were rolled back",
            "Houdini Solaris relighting setup failed",
            exc,
        )


def _node_point_contract(node: Any) -> Optional[dict]:
    geometry_method = getattr(node, "geometry", None)
    if not callable(geometry_method):
        return None
    try:
        geometry = geometry_method()
        point_count = int(geometry.pointCount())
        names = {attrib.name() for attrib in geometry.pointAttribs()}
    except Exception:  # noqa: BLE001
        return None
    if point_count <= 0 or "P" not in names:
        return None
    checks = (
        bool({"Cd", "albedo"} & names),
        "orient" in names,
        bool({"scale", "pscale"} & names),
        bool({"GS_Alpha", "Alpha", "alpha"} & names),
    )
    if sum(checks) < 3:
        return None
    attributes = sorted(names & set(_GSPLAT_BRIDGE_ATTRIBUTES))
    score = len(attributes)
    if {"GS_SPH_R", "GS_SPH_G", "GS_SPH_B"}.issubset(names):
        score += 20
    try:
        if str(node.name()).upper() == "OUT":
            score += 8
    except Exception:  # noqa: BLE001
        pass
    for method_name in ("isDisplayFlagSet", "isRenderFlagSet"):
        try:
            if bool(getattr(node, method_name)()):
                score += 4
        except Exception:  # noqa: BLE001
            pass
    return {"node": node, "point_count": point_count, "gsplat_attributes": attributes, "score": score}


def _discover_relight_sop_output(relight: Any, max_nodes: int = 256) -> dict:
    try:
        descendants = list(
            relight.allSubChildren(
                recurse_in_locked_nodes=True,
                sync_delayed_definition=True,
            )
        )[:max_nodes]
    except Exception:  # noqa: BLE001
        descendants = []
        pending = list(getattr(relight, "children", lambda: ())())
        while pending and len(descendants) < max_nodes:
            child = pending.pop(0)
            descendants.append(child)
            try:
                pending.extend(child.children())
            except Exception:  # noqa: BLE001
                pass
    contracts = []
    for node in descendants:
        contract = _node_point_contract(node)
        if contract is not None:
            contracts.append(contract)
    if not contracts:
        raise ValueError("No compatible GSplat SOP output was discovered inside the relight asset")
    return max(contracts, key=lambda item: item["score"])


def _bridge_child(parent: Any, name: str, type_name: str) -> Any:
    node = parent.node(name)
    if node is None:
        return parent.createNode(type_name, name)
    if _type_name(node).split("::", 1)[0] != type_name:
        raise ValueError("Stable GSplat SOP bridge contains an incompatible node")
    return node


def _build_or_refresh_relight_sop_bridge(hou: Any, relight: Any, force: bool = True) -> dict:
    relight.cook(force=bool(force))
    discovered = _discover_relight_sop_output(relight)
    internal_output = discovered["node"]
    internal_output.cook(force=bool(force))

    obj = _node(hou, "/obj")
    safe_relight_name = re.sub(r"[^A-Za-z0-9_]+", "_", str(relight.name())).strip("_") or "gsplat_relight"
    bridge_name = "dcc_mcp_{}_sop_bridge".format(safe_relight_name)[:64]
    bridge_geo = obj.node(bridge_name)
    if bridge_geo is None:
        bridge_geo = obj.createNode("geo", bridge_name)
    elif _type_name(bridge_geo).split("::", 1)[0] != "geo":
        raise ValueError("Stable GSplat SOP bridge name is occupied by an incompatible node")

    object_merge = _bridge_child(bridge_geo, "GSPLAT_RELIT_SOURCE", "object_merge")
    output = _bridge_child(bridge_geo, "OUT", "null")
    source_parm = object_merge.parm("objpath1")
    if source_parm is None:
        raise ValueError("Stable GSplat SOP bridge has no source-path parameter")
    source_parm.deleteAllKeyframes()
    source_parm.set(internal_output.path())
    output.setInput(0, object_merge)
    if hasattr(output, "setDisplayFlag"):
        output.setDisplayFlag(True)
    if hasattr(output, "setRenderFlag"):
        output.setRenderFlag(True)
    if hasattr(bridge_geo, "layoutChildren"):
        bridge_geo.layoutChildren(items=[object_merge, output])
    object_merge.cook(force=bool(force))
    output.cook(force=bool(force))

    output_contract = _node_point_contract(output)
    if output_contract is None:
        raise ValueError("Stable GSplat SOP bridge did not produce compatible point geometry")
    if hasattr(relight, "setUserData"):
        relight.setUserData("dcc_mcp.gsplat_relight.sop_output", output.path())
    return {
        "sop_bridge_available": True,
        "sop_output_path": output.path(),
        "point_count": output_contract["point_count"],
        "gsplat_attributes": output_contract["gsplat_attributes"],
        "bridge_refreshed": True,
        "sop_bridge_status": "ready",
    }


@skill_entry
def refresh_gsplat_relight_sop_bridge(relight_lop_path: str, force: bool = True) -> dict:
    """Rediscover and force-cook the stable SOP bridge for a Labs relight LOP."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")
    try:
        relight = _node(hou, relight_lop_path)
        contract = _build_or_refresh_relight_sop_bridge(hou, relight, force=force)
        return skill_success("Refreshed GSplat Solaris-to-SOP bridge", relight=_summary(relight), **contract)
    except ValueError as exc:
        return _safe_public_error(
            "GSplat Solaris-to-SOP bridge is unavailable",
            "Compatible relit GSplat SOP output was not available",
            exc,
        )
    except Exception as exc:
        return _safe_public_error(
            "Failed to refresh GSplat Solaris-to-SOP bridge",
            "Houdini bridge refresh failed",
            exc,
        )


def _cop_output_reference(source: Any) -> Any:
    """Return a named Copernicus output when exposed, otherwise output zero."""
    output_names_method = getattr(source, "outputNames", None)
    if not callable(output_names_method):
        raise ValueError("Copernicus source does not expose outputNames")
    output_names = output_names_method()
    if not isinstance(output_names, (list, tuple)):
        raise ValueError("Copernicus source returned an invalid outputNames contract")
    names = tuple(str(name) for name in output_names if str(name))
    return names[0] if names else 0


def _set_named_cop_input(target: Any, input_name: str, source: Any) -> Any:
    """Connect a Houdini 22 Copernicus input by name after contract inspection."""
    input_names_method = getattr(target, "inputNames", None)
    set_named_input = getattr(target, "setNamedInput", None)
    if not callable(input_names_method) or not callable(set_named_input):
        raise ValueError("Copernicus target does not support named inputs")
    input_names = input_names_method()
    if not isinstance(input_names, (list, tuple)):
        raise ValueError("Copernicus target returned an invalid inputNames contract")
    if input_name not in tuple(str(name) for name in input_names):
        raise ValueError("Copernicus target is missing a required named input")
    output_reference = _cop_output_reference(source)
    set_named_input(input_name, source, output_reference)
    return output_reference


def _configure_file_cop_color_output(file_cop: Any) -> str:
    """Expose one RGBA ``C`` AOV from a Houdini 22 File COP.

    File COP outputs are dynamic.  A filename alone leaves ``aovs`` at zero,
    which can draw a cable in the network while the downstream Blend COP still
    cooks with ``bg is missing``.  Author the same bounded AOV contract that
    the File COP UI's *Add AOVs from File* callback would create.
    """
    aovs_applied = _set_first(file_cop, ("aovs",), 1)
    if not aovs_applied:
        raise ValueError("File COP does not expose its Houdini 22 AOV multiparm")
    applied = {
        "name": _set_first(file_cop, ("aov1",), "C"),
        # Houdini 22's File COP menu uses 3 for an RGBA raster.
        "type": _set_first(file_cop, ("type1",), 3),
        "raw": _set_first(file_cop, ("raw1",), False),
    }
    if not all(applied.values()):
        raise ValueError("File COP does not expose a complete color AOV contract")
    cook = getattr(file_cop, "cook", None)
    if callable(cook):
        cook(force=True)
    output_reference = _cop_output_reference(file_cop)
    if output_reference != "C":
        raise ValueError("File COP did not expose the configured color AOV")
    return output_reference


@skill_entry
def create_gsplat_copernicus_raster(
    copnet_path: str,
    sop_path: str,
    camera_path: Optional[str] = None,
    attribute_name: str = "Cd",
    resolution: Optional[List[int]] = None,
    sharpen_amount: Optional[float] = None,
    saturation_scale: Optional[float] = None,
    value_scale: Optional[float] = None,
    gamma: Optional[float] = None,
    premultiply_alpha: bool = False,
    background_image_path: Optional[str] = None,
    background_mode: str = "over",
    background_brightness: float = 1.0,
    background_rotation: Sequence[float] = (0.0, 0.0, 0.0),
) -> dict:
    """Create a camera-aware GSplat raster, refinements, and optional background."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")
    created = []
    try:
        if background_mode != "over":
            raise ValueError("background_mode must be over")
        if (
            isinstance(background_brightness, bool)
            or not math.isfinite(float(background_brightness))
            or not 0.01 <= float(background_brightness) <= 16.0
        ):
            raise ValueError("background_brightness must be between 0.01 and 16")
        if not isinstance(background_rotation, (list, tuple)) or len(background_rotation) != 3:
            raise ValueError("background_rotation must contain exactly [rx, ry, rz]")
        if any(isinstance(value, bool) or not math.isfinite(float(value)) for value in background_rotation):
            raise ValueError("background_rotation values must be finite numbers")
        background_rotation = tuple(float(value) for value in background_rotation)
        if background_image_path is not None:
            if not isinstance(background_image_path, str) or not background_image_path.strip():
                raise ValueError("background_image_path must be a non-empty absolute image path")
            if not os.path.isabs(background_image_path):
                raise ValueError("background_image_path must be an absolute image path")

        copnet = _node(hou, copnet_path)
        _node(hou, sop_path)
        camera = None
        if camera_path:
            camera = _node(hou, camera_path)
            if _type_name(camera).split("::", 1)[0] != "cam":
                raise ValueError("camera_path must reference a Houdini camera node")
        sop_import = _create(copnet, ("sopimport", "sop_import"), "gsplat_sop_import")
        created.append(sop_import)
        import_applied = _set_first(sop_import, ("soppath", "sop_path", "nodepath"), sop_path)
        if not import_applied:
            raise ValueError("SOP Import COP does not expose an external SOP path parameter")
        external_sop_applied = _set_first(
            sop_import,
            ("usesoppath", "use_external_sop", "useexternalsop"),
            True,
        )
        raster = _create(copnet, ("rasterizegsplats", "rasterize_gsplats"), "gsplat_rasterize")
        created.append(raster)
        raster.setInput(1, sop_import)
        attribute_applied = _set_first(raster, ("name1", "attribute1", "attribute_name"), attribute_name)
        camera_import = None
        camera_applied = None
        if camera_path:
            camera_import = _create(copnet, ("cameraimport", "camera_import"), "gsplat_camera_import")
            created.append(camera_import)
            camera_applied = _set_first(camera_import, ("camera", "camerapath", "camera_path"), camera_path)
            raster.setInput(0, camera_import)
        resolution_applied = []
        if resolution is not None:
            if len(resolution) != 2 or any(isinstance(value, bool) or int(value) < 1 for value in resolution):
                raise ValueError("resolution must contain two positive integers")
            enabled = _set_first(copnet, ("setres", "set_resolution"), True)
            if enabled:
                resolution_applied.append(enabled)
            resolution_x = _set_first(
                copnet,
                ("res1", "resolutionx", "resx"),
                int(resolution[0]),
            )
            resolution_y = _set_first(
                copnet,
                ("res2", "resolutiony", "resy"),
                int(resolution[1]),
            )
            resolution_applied.extend(name for name in (resolution_x, resolution_y) if name)
            if not resolution_x or not resolution_y:
                raise ValueError("COP network does not expose writable resolution parameters")

        current = raster
        refinement_results = []

        def append_refinement(
            aliases: Sequence[str],
            name: str,
            controls: Dict[str, Tuple[Sequence[str], Any]],
        ) -> Any:
            nonlocal current
            node = _create(copnet, aliases, name)
            created.append(node)
            applied, unsupported = [], []
            for key, (parm_aliases, value) in controls.items():
                selected = _set_first(node, parm_aliases, value)
                (applied if selected else unsupported).append(key)
            # Some Copernicus controls (notably Premultiply's operation) rebuild
            # the node's input signature.  Connect only after applying controls
            # so Houdini cannot silently discard the source connection.
            node.setInput(0, current)
            inputs = node.inputs() if hasattr(node, "inputs") else None
            if isinstance(inputs, (list, tuple)) and (not inputs or inputs[0] != current):
                raise RuntimeError("{} did not retain its source connection".format(name))
            refinement_results.append(
                {
                    "node": _summary(node),
                    "applied": applied,
                    "unsupported": unsupported,
                }
            )
            current = node
            return node

        if sharpen_amount is not None:
            if isinstance(sharpen_amount, bool) or float(sharpen_amount) < 0:
                raise ValueError("sharpen_amount must be non-negative")
            append_refinement(
                ("sharpen",),
                "gsplat_sharpen",
                {"sharpen_amount": (("amplitude", "amount"), float(sharpen_amount))},
            )
        if saturation_scale is not None or value_scale is not None:
            controls = {}
            if saturation_scale is not None:
                if isinstance(saturation_scale, bool) or float(saturation_scale) < 0:
                    raise ValueError("saturation_scale must be non-negative")
                controls["saturation_scale"] = (("satscale", "saturation_scale"), float(saturation_scale))
            if value_scale is not None:
                if isinstance(value_scale, bool) or float(value_scale) < 0:
                    raise ValueError("value_scale must be non-negative")
                controls["value_scale"] = (("valscale", "value_scale"), float(value_scale))
            append_refinement(("hsv",), "gsplat_hsv", controls)
        if gamma is not None:
            if isinstance(gamma, bool) or float(gamma) <= 0:
                raise ValueError("gamma must be greater than zero")
            append_refinement(
                ("gamma",),
                "gsplat_gamma",
                {"gamma": (("gamma",), float(gamma))},
            )
        if premultiply_alpha:
            append_refinement(
                ("premult",),
                "gsplat_premult",
                {"operation": (("op", "operation"), "mult")},
            )

        background_composite = {"enabled": False}
        if background_image_path is not None:
            # Blend/Over consumes alpha-associated foreground color. Keep the
            # standalone raster straight by default, but establish association
            # automatically at the composite boundary.
            if not premultiply_alpha:
                append_refinement(
                    ("premult",),
                    "gsplat_composite_premult",
                    {"operation": (("op", "operation"), "mult")},
                )
            background_file = _create(copnet, ("file",), "gsplat_background_file")
            created.append(background_file)
            filename_applied = _set_first(background_file, ("filename",), background_image_path)
            if not filename_applied:
                raise ValueError("File COP does not expose its Houdini 22 filename parameter")
            _configure_file_cop_color_output(background_file)

            # The HDRI is latitude-longitude data, not a camera plate.  Sample
            # it as a celestial sphere into the same camera/view metadata as
            # the rasterized GSplat before compositing.
            background_sphere = _create(
                copnet,
                ("spheresample", "sphere_sample"),
                "gsplat_background_sphere",
            )
            created.append(background_sphere)
            celestial_applied = _set_first(
                background_sphere,
                ("celestial", "celestialsphere", "celestial_sphere"),
                True,
            )
            if not celestial_applied:
                raise ValueError("Sphere Sample COP does not expose its celestial-sphere parameter")
            # background_rotation is validated as exactly three values above;
            # avoid zip(strict=...) to preserve the adapter's Python 3.8 floor.
            for parm_name, value in zip(("rx", "ry", "rz"), background_rotation):
                if not _set_first(background_sphere, (parm_name,), value):
                    raise ValueError("Sphere Sample COP does not expose its rotation parameters")
            # Prefer the imported camera metadata itself.  The refined GSplat
            # layer can carry a data window but is not guaranteed to remain a
            # valid camera reference after color operations.
            _set_named_cop_input(background_sphere, "size_ref", camera_import or current)
            _set_named_cop_input(background_sphere, "source", background_file)

            background_bright = _create(copnet, ("bright",), "gsplat_background_brightness")
            created.append(background_bright)
            brightness_applied = _set_first(background_bright, ("bright",), float(background_brightness))
            if not brightness_applied:
                raise ValueError("Bright COP does not expose its Houdini 22 brightness parameter")
            background_bright.setInput(0, background_sphere)

            blend = _create(copnet, ("blend",), "gsplat_background_over")
            created.append(blend)
            mode_applied = _set_first(blend, ("mode",), background_mode)
            if not mode_applied:
                raise ValueError("Blend COP does not expose its Houdini 22 mode parameter")
            alpha_applied = _set_first(blend, ("alpha",), True)
            clip_applied = _set_first(blend, ("clipbydata",), True)
            if not alpha_applied or not clip_applied:
                raise ValueError("Blend COP does not expose its alpha-compositing contract")
            background_output = _set_named_cop_input(blend, "bg", background_bright)
            foreground_output = _set_named_cop_input(blend, "fg", current)
            background_composite = {
                "enabled": True,
                "mode": background_mode,
                "file": _summary(background_file),
                "sphere": _summary(background_sphere),
                "brightness": _summary(background_bright),
                "brightness_scale": float(background_brightness),
                "rotation": list(background_rotation),
                "blend": _summary(blend),
                "named_inputs": {"bg": background_output, "fg": foreground_output},
            }
            current = blend

        if hasattr(copnet, "layoutChildren"):
            copnet.layoutChildren(items=created)
        return skill_success(
            "Created Copernicus GSplat raster chain",
            copnet=_summary(copnet),
            sop_import=_summary(sop_import),
            camera_import=_summary(camera_import) if camera_import else None,
            rasterize=_summary(raster),
            refinements=refinement_results,
            background_composite=background_composite,
            output=_summary(current),
            attribute_name=attribute_name,
            applied_parameters={
                "sop_path": import_applied,
                "use_external_sop": external_sop_applied,
                "attribute_name": attribute_applied,
                "camera_path": camera_applied,
                "resolution": resolution_applied,
            },
            next_step=(
                "Render the returned output COP through an Image ROP for pixel-level acceptance. "
                "Rasterize GSplats already produces alpha-associated color; append Premult only "
                "when a downstream straight-alpha contract explicitly requires it."
            ),
        )
    except Exception as exc:
        for item in reversed(created):
            try:
                item.destroy()
            except Exception:  # noqa: BLE001
                pass
        return _safe_public_error(
            "Failed to create Copernicus GSplat raster chain; created nodes were rolled back",
            "Houdini Copernicus GSplat setup failed",
            exc,
        )


def _required_parm(node: Any, name: str) -> Any:
    parm = node.parm(name)
    if parm is None:
        raise ValueError("Houdini 22 Image ROP is missing required parameter: {}".format(name))
    return parm


def _file_signature(path: str) -> Optional[dict]:
    try:
        stat = os.stat(path)
    except OSError:
        return None
    if not os.path.isfile(path):
        return None
    return {"mtime_ns": int(stat.st_mtime_ns), "size_bytes": int(stat.st_size)}


def write_gsplat_copernicus_image(
    cop_output_path: str,
    output_file: str,
    frame: float,
    resolution: Sequence[int],
    color_conversion: str,
    rop_name: str = "dcc_mcp_gsplat_image_proof",
) -> dict:
    """Render one Copernicus frame through a named Houdini 22 Image ROP."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        if not isinstance(cop_output_path, str) or not cop_output_path.startswith("/") or ".." in cop_output_path:
            raise ValueError("cop_output_path must be an absolute Houdini COP node path without '..'")
        if not isinstance(output_file, str) or not os.path.isabs(output_file):
            raise ValueError("output_file must be an absolute output file path")
        if not output_file.strip() or os.path.basename(output_file) in ("", ".", ".."):
            raise ValueError("output_file must name a file, not a directory")
        if not isinstance(rop_name, str) or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", rop_name) is None:
            raise ValueError("rop_name must be a Houdini-safe name with at most 64 characters")
        if isinstance(frame, bool) or not math.isfinite(float(frame)):
            raise ValueError("frame must be a finite number")
        if not isinstance(resolution, (list, tuple)) or len(resolution) != 2:
            raise ValueError("resolution must contain exactly [width, height]")
        if any(isinstance(value, bool) or not isinstance(value, int) for value in resolution):
            raise ValueError("resolution values must be integers")
        width, height = int(resolution[0]), int(resolution[1])
        if not 1 <= width <= 16384 or not 1 <= height <= 16384:
            raise ValueError("resolution values must be between 1 and 16384")
        if color_conversion not in ("raw", "ocio", "bakeocio"):
            raise ValueError("color_conversion must be one of: raw, ocio, bakeocio")

        cop_output = _node(hou, cop_output_path)
        out = _node(hou, "/out")
        rop = out.node(rop_name)
        created = rop is None
        if created:
            rop = out.createNode("image", rop_name)
        elif _type_name(rop).split("::", 1)[0] != "image":
            raise ValueError("/out/{} exists but is not a Houdini Image ROP".format(rop_name))

        _required_parm(rop, "coppath").set(cop_output.path())
        output_parm = _required_parm(rop, "copoutput")
        # Image ROPs may ship with an expression/default tokenized path. Remove
        # animation or expressions before assigning the caller-bounded path.
        output_parm.deleteAllKeyframes()
        output_parm.set(output_file)

        _required_parm(rop, "trange").set(0)
        render_frame = float(frame)
        _required_parm(rop, "f1").set(render_frame)
        _required_parm(rop, "f2").set(render_frame)
        _required_parm(rop, "f3").set(1.0)
        _required_parm(rop, "setres").set(True)
        _required_parm(rop, "res1").set(width)
        _required_parm(rop, "res2").set(height)
        _required_parm(rop, "colorconversion").set(color_conversion)
        mkpath = rop.parm("mkpath")
        if mkpath is not None:
            mkpath.set(True)

        before = _file_signature(output_file)
        rop.render(frame_range=(render_frame, render_frame, 1.0), verbose=False)
        after = _file_signature(output_file)
        exists = after is not None
        size_bytes = after["size_bytes"] if after else 0
        updated_by_render = bool(after and after != before)
        evidence = {
            "exists": exists,
            "size_bytes": size_bytes,
            "updated_by_render": updated_by_render,
        }
        if not exists or size_bytes <= 0 or not updated_by_render:
            return skill_error(
                "Image ROP did not produce fresh pixel evidence",
                "The foreground render returned without creating or updating a non-empty output file",
                written_files=[],
                output_evidence=evidence,
                image_rop=_summary(rop),
            )

        return skill_success(
            "Rendered Copernicus output to a verified image file",
            written_files=[output_file],
            output_evidence=evidence,
            image_rop=_summary(rop),
            created=created,
            cop_output_path=cop_output.path(),
            frame=render_frame,
            resolution=[width, height],
            color_conversion=color_conversion,
        )
    except ValueError as exc:
        return _safe_public_error(
            "Invalid Copernicus Image ROP request",
            "Image ROP request validation failed",
            exc,
        )
    except Exception as exc:
        return _safe_public_error(
            "Failed to render Copernicus output through Houdini Image ROP",
            "Houdini Image ROP operation failed",
            exc,
        )


def main(**kwargs: Any) -> dict:
    """Dispatch entrypoint used by the skill runner."""
    action = kwargs.pop("action", "inspect")
    functions = {
        "inspect": inspect_gsplat_relighting_input,
        "prepare": prepare_gsplat_sop_chain,
        "relight": create_gsplat_relight_lop,
        "refresh_relight_sop": refresh_gsplat_relight_sop_bridge,
        "rasterize": create_gsplat_copernicus_raster,
        "write_image": write_gsplat_copernicus_image,
    }
    if action not in functions:
        return skill_error("Unknown GSplat action", "action must be one of: {}".format(", ".join(functions)))
    return functions[action](**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
