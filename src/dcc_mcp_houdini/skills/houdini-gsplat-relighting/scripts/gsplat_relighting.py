"""Typed Houdini 22 GSplat relighting setup and preflight tools."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


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
        checks = {
            "position": "P" in names,
            "color_or_albedo": bool({"Cd", "albedo"} & names),
            "normal": "N" in names,
            "orientation": "orient" in names,
            "scale": bool({"scale", "pscale"} & names),
            "opacity": bool({"GS_Alpha", "Alpha", "alpha"} & names),
            "spherical_harmonics": {"GS_SPH_R", "GS_SPH_G", "GS_SPH_B"}.issubset(names),
            "ambient_occlusion": "ao" in names,
        }
        missing = [key for key, present in checks.items() if not present and key in ("position", "color_or_albedo")]
        return skill_success(
            "Inspected GSplat relighting input",
            source=_summary(source),
            point_count=int(geometry.pointCount()),
            primitive_count=int(geometry.primCount()),
            point_attributes=attributes,
            checks=checks,
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
                "Do not label procedural point sampling as captured GSplat reconstruction.",
            ],
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to inspect GSplat input")


@skill_entry
def prepare_gsplat_sop_chain(
    node_path: str,
    create_normals: bool = True,
    create_albedo: bool = True,
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
            output_attributes=[name for name, enabled in (("N", create_normals), ("albedo", create_albedo)) if enabled],
            cooked=bool(cook),
        )
    except Exception as exc:
        for item in reversed(created):
            try:
                item.destroy()
            except Exception:  # noqa: BLE001
                pass
        return skill_exception(exc, message="Failed to prepare GSplat SOP chain; created nodes were rolled back")


@skill_entry
def create_gsplat_relight_lop(
    lop_node_path: str,
    camera_path: Optional[str] = None,
    collision_path: Optional[str] = None,
    enable_shadows: bool = True,
    shadow_bias: Optional[float] = None,
    lights: Optional[List[Dict[str, Any]]] = None,
    parameters: Optional[Dict[str, Any]] = None,
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
        return skill_success(
            "Created GSplat Solaris relighting stage",
            input=_summary(source),
            lights=light_results,
            relight=_summary(relight),
            applied_parameters=applied,
            unsupported_parameters=unsupported,
            output_attributes=["Cd", "GS_SPH_R", "GS_SPH_G", "GS_SPH_B"],
        )
    except Exception as exc:
        for item in reversed(created):
            try:
                item.destroy()
            except Exception:  # noqa: BLE001
                pass
        return skill_exception(
            exc, message="Failed to create GSplat Solaris relighting stage; created nodes were rolled back"
        )


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
    premultiply_alpha: bool = True,
) -> dict:
    """Create a camera-aware GSplat raster and optional image-refinement COPs."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")
    created = []
    try:
        copnet = _node(hou, copnet_path)
        _node(hou, sop_path)
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
            node.setInput(0, current)
            applied, unsupported = [], []
            for key, (parm_aliases, value) in controls.items():
                selected = _set_first(node, parm_aliases, value)
                (applied if selected else unsupported).append(key)
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
        if hasattr(copnet, "layoutChildren"):
            copnet.layoutChildren(items=created)
        return skill_success(
            "Created Copernicus GSplat raster chain",
            copnet=_summary(copnet),
            sop_import=_summary(sop_import),
            camera_import=_summary(camera_import) if camera_import else None,
            rasterize=_summary(raster),
            refinements=refinement_results,
            output=_summary(current),
            attribute_name=attribute_name,
            applied_parameters={
                "sop_path": import_applied,
                "use_external_sop": external_sop_applied,
                "attribute_name": attribute_applied,
                "camera_path": camera_applied,
                "resolution": resolution_applied,
            },
            next_step="Display or render the returned output COP; parameter edits update the image interactively.",
        )
    except Exception as exc:
        for item in reversed(created):
            try:
                item.destroy()
            except Exception:  # noqa: BLE001
                pass
        return skill_exception(
            exc, message="Failed to create Copernicus GSplat raster chain; created nodes were rolled back"
        )


def main(**kwargs: Any) -> dict:
    """Dispatch entrypoint used by the skill runner."""
    action = kwargs.pop("action", "inspect")
    functions = {
        "inspect": inspect_gsplat_relighting_input,
        "prepare": prepare_gsplat_sop_chain,
        "relight": create_gsplat_relight_lop,
        "rasterize": create_gsplat_copernicus_raster,
    }
    if action not in functions:
        return skill_error("Unknown GSplat action", "action must be one of: {}".format(", ".join(functions)))
    return functions[action](**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
