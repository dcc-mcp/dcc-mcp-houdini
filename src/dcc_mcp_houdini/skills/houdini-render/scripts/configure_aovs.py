"""Configure AOVs (Arbitrary Output Variables) on a render node or Solaris product."""

from __future__ import annotations

import re
from typing import List

from _render_common import get_node, node_summary  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_KARMA_UBOX = '["ubox",{}]'
_KARMA_ZMIN = '["minmax",{"mode":"zmin"}]'

# Karma / Solaris canonical AOV presets.
#
# These drive an ``additionalrendervars`` LOP, which authors each RenderVar with
# the KarmaRenderVarAPI and HuskRenderVarAPI applied and the full
# ``driver:parameters:aov:*`` attribute set (name, format, husk:channel_prefix,
# karma:filter, multiSampled, clearValue, and the cryptomatte attributes). The
# values below were validated against husk (BRAY_HdKarma): each one produces a
# real EXR channel rather than a beauty-only image.
KARMA_AOV_PRESETS = {
    "diffuse": {
        "sourceName": "C<RD>.*L",
        "sourceType": "lpe",
        "dataType": "color3f",
        "format": "color3h",
        "multisampled": True,
        "filter": _KARMA_UBOX,
    },
    "specular": {
        "sourceName": "C<RG>.*L",
        "sourceType": "lpe",
        "dataType": "color3f",
        "format": "color3h",
        "multisampled": True,
        "filter": _KARMA_UBOX,
    },
    "transmission": {
        "sourceName": "C<TG>.*L",
        "sourceType": "lpe",
        "dataType": "color3f",
        "format": "color3h",
        "multisampled": True,
        "filter": _KARMA_UBOX,
    },
    "normal": {
        "sourceName": "ray:hitN",
        "sourceType": "raw",
        "dataType": "normal3f",
        "format": "half3",
        "multisampled": False,
        "filter": _KARMA_UBOX,
    },
    "depth": {
        "sourceName": "ray:hitPz",
        "sourceType": "raw",
        "dataType": "float",
        "format": "float",
        "multisampled": False,
        "filter": _KARMA_ZMIN,
    },
    "motionvector": {
        "sourceName": "ray:motionvector",
        "sourceType": "raw",
        "dataType": "vector3f",
        "format": "half3",
        "multisampled": False,
        "filter": _KARMA_UBOX,
    },
    "albedo": {
        "sourceName": "export_basecolor",
        "sourceType": "raw",
        "dataType": "color3f",
        "format": "color3h",
        "multisampled": False,
        "filter": _KARMA_UBOX,
    },
    "opacity": {
        "sourceName": "Of",
        "sourceType": "raw",
        "dataType": "color3f",
        "format": "color3h",
        "multisampled": False,
        "filter": _KARMA_UBOX,
    },
    "emission": {
        "sourceName": "C.*O",
        "sourceType": "lpe",
        "dataType": "color3f",
        "format": "color3h",
        "multisampled": True,
        "filter": _KARMA_UBOX,
    },
    "volume": {
        "sourceName": "CV.*L",
        "sourceType": "lpe",
        "dataType": "color3f",
        "format": "color3h",
        "multisampled": True,
        "filter": _KARMA_UBOX,
    },
    "uv": {
        "sourceName": "st",
        "sourceType": "primvar",
        "dataType": "float3",
        "format": "float3",
        "multisampled": False,
        "filter": _KARMA_UBOX,
    },
    "worldpos": {
        "sourceName": "ray:hitP",
        "sourceType": "raw",
        "dataType": "point3f",
        "format": "half3",
        "multisampled": False,
        "filter": _KARMA_UBOX,
    },
    "cryptomatte": {
        "sourceName": "material",
        "sourceType": "raw",
        "dataType": "color3f",
        "format": "color3h",
        "multisampled": False,
        "filter": _KARMA_UBOX,
        "cryptomatte": True,
        "cryptomatterank": 6,
    },
    "objectid": {
        "sourceName": "object",
        "sourceType": "raw",
        "dataType": "color3f",
        "format": "color3h",
        "multisampled": False,
        "filter": _KARMA_UBOX,
        "cryptomatte": True,
        "cryptomatterank": 6,
    },
    "materialid": {
        "sourceName": "material",
        "sourceType": "raw",
        "dataType": "color3f",
        "format": "color3h",
        "multisampled": False,
        "filter": _KARMA_UBOX,
        "cryptomatte": True,
        "cryptomatterank": 6,
    },
}

# Solaris Render Product LOP types this tool can configure.
KARMA_PRODUCT_TYPES = ("renderproduct",)

# USD property authored on the product so husk combines every AOV into one EXR.
_IMAGE_FORMAT_PROP = "driver:parameters:husk:image_format"
_IMAGE_FORMAT_VALUE = "OpenEXR"
# Control-parm states for ``driver:parameters:husk:image_format`` that mean the
# attribute is NOT authored as a readable value on the USD stage (so husk will
# not see it and would collapse the render to beauty-only). A non-empty value
# parm with a control in this set must still be (re)authored as OpenEXR.
_IMAGE_FORMAT_NON_AUTHORING_CONTROLS = frozenset({"none", "block", ""})
_ADDITIONAL_RENDERVARS_TYPE = "additionalrendervars"
_ARV_PARENT_PATH = "parentprimpath"
_ARV_COUNT_PARM = "rendervars"
_DEFAULT_VAR_PARENT = "/Render/Products/Vars"

# additionalrendervars multiparm instance fields we author.
_ARV_VALUE_KEYS = (
    "enable",
    "name",
    "sourceName",
    "sourceType",
    "dataType",
    "format",
    "multisampled",
    "clearvalue",
    "filter",
    "cryptomatte",
    "cryptomatterank",
)

MANTRA_AOV_PRESETS = {
    "diffuse": {"source": "lpe:C<RD>.*L", "type": "vector", "channel": "diffuse"},
    "specular": {"source": "lpe:C<RG>.*[LO]", "type": "vector", "channel": "specular"},
    "transmission": {"source": "lpe:C<TG>.*[LO]", "type": "vector", "channel": "transmission"},
    "normal": {
        "source": "N",
        "type": "unitvector",
        "channel": "normal",
        "quantize": "float",
        "pixel_filter": "minmax omedian",
    },
    "depth": {
        "source": "Pz",
        "type": "float",
        "channel": "depth",
        "quantize": "float",
        "pixel_filter": "minmax omedian",
    },
    "motionvector": {
        "source": "motion_vector",
        "type": "vector",
        "channel": "motionvector",
        "quantize": "float",
        "pixel_filter": "minmax omedian",
    },
    "albedo": {"source": "export_basecolor", "type": "vector", "channel": "albedo"},
    "opacity": {"source": "Of", "type": "vector", "channel": "opacity"},
    "emission": {
        "source": "all_emission",
        "type": "vector",
        "channel": "emission",
        "sample_filter": "fullopacity",
    },
    "volume": {
        "source": "lpe:CV.*L",
        "type": "vector",
        "channel": "volume",
        "sample_filter": "fullopacity",
    },
    "objectid": {
        "source": "Op_Id",
        "type": "float",
        "channel": "objectid",
        "quantize": "float",
    },
    "materialid": {
        "source": "Material_Id",
        "type": "float",
        "channel": "materialid",
        "quantize": "float",
    },
    "uv": {"source": "uv", "type": "vector", "channel": "uv", "quantize": "float"},
    "worldpos": {
        "source": "P",
        "type": "vector",
        "channel": "worldpos",
        "quantize": "float",
        "pixel_filter": "minmax omedian",
    },
}


def _configure_mantra_aovs(node, aovs: List[str], action: str) -> tuple:
    count_parm = node.parm("vm_numaux")
    if count_parm is None:
        return [], list(dict.fromkeys(aovs))

    count = int(count_parm.eval())
    planes = []
    existing = set()
    for index in range(1, count + 1):
        source_parm = node.parm("vm_variable_plane{}".format(index))
        channel_parm = node.parm("vm_channel_plane{}".format(index))
        source = str(source_parm.eval()) if source_parm is not None else ""
        channel = str(channel_parm.eval()) if channel_parm is not None else ""
        planes.append({"index": index, "source": source, "channel": channel})
        existing.update(value.lower() for value in (source, channel) if value)

    if action == "remove":
        configured = []
        unsupported = []
        removed_indices = set()
        seen = set()
        for requested_name in aovs:
            name = str(requested_name).strip().lower()
            if not name or name in seen:
                continue
            seen.add(name)
            preset = MANTRA_AOV_PRESETS.get(name, {})
            matches = {
                value
                for value in (
                    name,
                    str(preset.get("source", "")).lower(),
                    str(preset.get("channel", "")).lower(),
                )
                if value
            }
            matching_planes = [
                item
                for item in planes
                if {value for value in (item["source"].lower(), item["channel"].lower()) if value} & matches
            ]
            if not matching_planes:
                unsupported.append(requested_name)
                continue
            new_matches = [item for item in matching_planes if item["index"] not in removed_indices]
            if not new_matches:
                continue
            removed_indices.update(item["index"] for item in new_matches)
            plane = new_matches[0]
            configured.append(
                {
                    "name": name,
                    "action": "removed",
                    "source": plane["source"],
                    "channel": plane["channel"],
                }
            )
        for index in sorted(removed_indices, reverse=True):
            count_parm.removeMultiParmInstance(index - 1)
        return configured, unsupported

    if action != "add":
        return [], list(dict.fromkeys(aovs))

    initial_count = count
    configured = []
    unsupported = []
    seen = set()
    for requested_name in aovs:
        name = str(requested_name).strip().lower()
        if not name or name in seen:
            continue
        seen.add(name)
        preset = MANTRA_AOV_PRESETS.get(name)
        if preset is None:
            unsupported.append(requested_name)
            continue
        if preset["source"].lower() in existing or preset["channel"].lower() in existing:
            continue

        index = count + 1
        count_parm.set(index)
        plane_values = {
            "source": preset["source"],
            "type": preset["type"],
            "channel": preset["channel"],
            "quantize": preset.get("quantize", "half"),
            "pixel_filter": preset.get("pixel_filter", ""),
            "sample_filter": preset.get("sample_filter", "alpha"),
        }
        plane_parms = {
            key: node.parm(pattern.format(index))
            for key, pattern in (
                ("source", "vm_variable_plane{}"),
                ("type", "vm_vextype_plane{}"),
                ("channel", "vm_channel_plane{}"),
                ("quantize", "vm_quantize_plane{}"),
                ("pixel_filter", "vm_pfilter_plane{}"),
                ("sample_filter", "vm_sfilter_plane{}"),
            )
        }
        if any(parm is None for parm in plane_parms.values()):
            count_parm.set(count)
            unsupported.append(requested_name)
            continue
        try:
            for key, parm in plane_parms.items():
                parm.set(plane_values[key])
        except Exception:
            count_parm.set(initial_count)
            raise
        count = index
        existing.update((preset["source"].lower(), preset["channel"].lower()))
        configured.append({"name": name, "action": "added", "index": index, **plane_values})
    return configured, unsupported


class UnsupportedSolarisTarget(ValueError):
    """Raised when a /stage path does not point at a Solaris Render Product LOP."""


def _node_type_name(node) -> str:
    try:
        return node.type().name().split("::", 1)[0]
    except Exception:  # noqa: BLE001
        return ""


def _owned_arv_name(product) -> str:
    return "{}_aovs".format(product.name())


def _find_owned_arv(product):
    """Return the additionalrendervars LOP owned by *product*, or None."""
    name = _owned_arv_name(product)
    parent = product.parent()
    candidate = parent.node(name) if parent is not None else None
    if candidate is not None and _node_type_name(candidate) == _ADDITIONAL_RENDERVARS_TYPE:
        return candidate
    incoming = product.input(0)
    if (
        incoming is not None
        and _node_type_name(incoming) == _ADDITIONAL_RENDERVARS_TYPE
        and incoming.name().startswith(name)
    ):
        return incoming
    return None


def _get_or_create_additional_rendervars(product):
    """Return the product-owned additionalrendervars LOP, wired as its input."""
    arv = _find_owned_arv(product)
    if arv is not None:
        if product.input(0) is not arv:
            upstream = product.input(0)
            arv.setInput(0, upstream)
            product.setInput(0, arv)
        return arv
    parent = product.parent()
    try:
        arv = parent.createNode(_ADDITIONAL_RENDERVARS_TYPE, node_name=_owned_arv_name(product))
    except Exception as exc:  # noqa: BLE001
        raise UnsupportedSolarisTarget(
            "Could not create an additionalrendervars LOP under '{}': {}".format(parent.path(), exc)
        ) from exc
    upstream = product.input(0)
    arv.setInput(0, upstream)
    product.setInput(0, arv)
    return arv


def _arv_var_parent(arv) -> str:
    parm = arv.parm(_ARV_PARENT_PATH)
    value = str(parm.eval()).strip().rstrip("/") if parm is not None else ""
    return value or _DEFAULT_VAR_PARENT


def _var_prim_path(var_parent: str, name: str) -> str:
    return "{}/{}".format(var_parent, name)


def _arv_existing_names(arv) -> list:
    """Ordered, de-duplicated list of preset names currently authored on *arv*.

    Only preset (tool-managed) names are returned; hand-authored instances are
    intentionally excluded here so they are never mistaken for managed state
    (they are preserved separately by ``_arv_foreign_instances``).
    """
    count_parm = arv.parm(_ARV_COUNT_PARM)
    count = int(count_parm.eval()) if count_parm is not None else 0
    names = []
    for index in range(1, count + 1):
        parm = arv.parm("name{}".format(index))
        name = str(parm.eval()).strip().lower() if parm is not None else ""
        if name and name in KARMA_AOV_PRESETS and name not in names:
            names.append(name)
    return names


def _arv_foreign_instances(arv) -> list:
    """Snapshots of non-preset multiparm instances currently authored on *arv*.

    The additionalrendervars LOP is tool-owned, but a user may hand-author extra
    instances on it. Those are not managed presets, so they must survive a
    rebuild of the managed set rather than being overwritten. Blank default
    instances (empty name) are dropped.
    """
    count_parm = arv.parm(_ARV_COUNT_PARM)
    count = int(count_parm.eval()) if count_parm is not None else 0
    foreign = []
    for index in range(1, count + 1):
        parm = arv.parm("name{}".format(index))
        name = str(parm.eval()).strip().lower() if parm is not None else ""
        if not name or name in KARMA_AOV_PRESETS:
            continue
        fields = {}
        for key in _ARV_VALUE_KEYS:
            key_parm = arv.parm("{}{}".format(key, index))
            if key_parm is not None:
                fields[key] = key_parm.eval()
        if fields:
            foreign.append(fields)
    return foreign


def _arv_instance_values(name: str, preset: dict) -> dict:
    return {
        "enable": True,
        "name": name,
        "sourceName": preset["sourceName"],
        "sourceType": preset["sourceType"],
        "dataType": preset["dataType"],
        "format": preset["format"],
        "multisampled": bool(preset.get("multisampled", False)),
        "clearvalue": 0,
        "filter": preset.get("filter", _KARMA_UBOX),
        "cryptomatte": bool(preset.get("cryptomatte", False)),
        "cryptomatterank": int(preset.get("cryptomatterank", 6)),
    }


def _write_arv_instance(arv, index: int, values: dict) -> None:
    missing = [key for key in values if arv.parm("{}{}".format(key, index)) is None]
    if missing:
        raise ValueError("additionalrendervars node is missing parameters: {}".format(", ".join(sorted(missing))))
    for key, value in values.items():
        arv.parm("{}{}".format(key, index)).set(value)


def _snapshot_arv(arv) -> list:
    count_parm = arv.parm(_ARV_COUNT_PARM)
    count = int(count_parm.eval()) if count_parm is not None else 0
    snapshot = []
    for index in range(1, count + 1):
        fields = {}
        for key in _ARV_VALUE_KEYS:
            parm = arv.parm("{}{}".format(key, index))
            if parm is not None:
                fields[key] = parm.eval()
        snapshot.append(fields)
    return snapshot


def _restore_arv(arv, snapshot: list) -> None:
    count_parm = arv.parm(_ARV_COUNT_PARM)
    if count_parm is None:
        return
    count_parm.set(len(snapshot))
    for index, fields in enumerate(snapshot, start=1):
        for key, value in fields.items():
            parm = arv.parm("{}{}".format(key, index))
            if parm is not None:
                parm.set(value)


def _rewrite_arv(arv, names: list) -> None:
    count_parm = arv.parm(_ARV_COUNT_PARM)
    if count_parm is None:
        raise ValueError("additionalrendervars node has no '{}' parameter".format(_ARV_COUNT_PARM))
    foreign = _arv_foreign_instances(arv)
    count_parm.set(len(names) + len(foreign))
    for index, name in enumerate(names, start=1):
        _write_arv_instance(arv, index, _arv_instance_values(name, KARMA_AOV_PRESETS[name]))
    for offset, fields in enumerate(foreign, start=1):
        _write_arv_instance(arv, len(names) + offset, fields)


def _read_ordered_vars(product) -> list:
    parm = product.parm("orderedVars")
    if parm is None:
        return []
    raw = str(parm.eval() or "").strip()
    if not raw:
        return []
    return [token for token in re.split(r"[\s,]+", raw) if token]


def _write_ordered_vars(product, paths: list) -> None:
    parm = product.parm("orderedVars")
    if parm is None:
        raise ValueError("Render Product '{}' has no 'orderedVars' parameter".format(product.path()))
    parm.set(" ".join(paths))


def _ordered_vars_path(var_parent: str, names: list) -> list:
    return [_var_prim_path(var_parent, name) for name in names]


def _merge_ordered_vars(original: list, var_parent: str, managed_before: list, managed_after: list) -> list:
    """Keep unrelated RenderVar references and replace only managed preset paths.

    ``orderedVars`` may reference RenderVars authored by other LOPs or by hand;
    those must survive an add/remove. Only the paths for preset names the tool
    currently manages (``managed_before``) are swapped out, and the paths for
    ``managed_after`` are appended without duplicating anything already kept.
    """
    managed_paths = set(_ordered_vars_path(var_parent, managed_before))
    kept = [path for path in original if path not in managed_paths]
    kept_set = set(kept)
    return kept + [path for path in _ordered_vars_path(var_parent, managed_after) if path not in kept_set]


def _find_driver_parms(node, usd_prop: str):
    """Map a USD property to its Houdini value/control parms via stem matching."""
    stem = "".join(char for char in usd_prop if char.isalnum() or char == "_")
    prefix = "xn__{}_".format(stem)
    value_names = []
    control_names = []
    for parm in node.parms():
        name = parm.name()
        if not name.startswith(prefix):
            continue
        (control_names if "_control_" in name else value_names).append(name)
    value_names.sort(key=len)
    control_names.sort(key=len)
    return value_names, control_names


def _capture_image_format(product) -> dict:
    value_names, control_names = _find_driver_parms(product, _IMAGE_FORMAT_PROP)
    state = {"value_names": value_names, "control_names": control_names, "value": None, "controls": {}}
    if value_names:
        parm = product.parm(value_names[0])
        state["value"] = parm.eval() if parm is not None else None
    for name in control_names:
        parm = product.parm(name)
        state["controls"][name] = parm.eval() if parm is not None else None
    return state


def _restore_image_format(product, state: dict) -> None:
    for name, value in state["controls"].items():
        parm = product.parm(name)
        if parm is not None and value is not None:
            parm.set(value)
    if state["value_names"]:
        parm = product.parm(state["value_names"][0])
        if parm is not None and state["value"] is not None:
            parm.set(state["value"])


def _ensure_product_image_format(product) -> bool:
    """Author image_format=OpenEXR unless the product already authors one.

    husk only merges every ordered RenderVar into a single EXR when the product
    carries an authored ``driver:parameters:husk:image_format``; without it the
    render collapses to the beauty/first channel. A non-empty value parm is not
    enough on its own: the attribute must also be authored on the USD stage,
    which the control parm reports ("none"/"block"/empty mean husk would not see
    a readable value). Only a non-empty value paired with an authored control
    counts as already configured.
    """
    value_names, control_names = _find_driver_parms(product, _IMAGE_FORMAT_PROP)
    if not value_names:
        return False
    value_parm = product.parm(value_names[0])
    value_is_set = value_parm is not None and bool(str(value_parm.eval()).strip())
    if value_is_set:
        for name in control_names:
            control_parm = product.parm(name)
            if control_parm is None:
                continue
            if str(control_parm.eval()).strip().lower() not in _IMAGE_FORMAT_NON_AUTHORING_CONTROLS:
                return False
    for name in control_names:
        control_parm = product.parm(name)
        if control_parm is not None:
            control_parm.set("set")
    if value_parm is not None:
        value_parm.set(_IMAGE_FORMAT_VALUE)
    return True


def _unwire_and_destroy_arv(product, arv) -> None:
    # Only bypass the node when it is actually the product's current input. A
    # findable-but-unwired sibling additionalrendervars LOP must be destroyed
    # without touching the product's existing upstream connection.
    if product.input(0) is arv:
        product.setInput(0, arv.input(0))
    try:
        arv.destroy()
    except Exception:  # noqa: BLE001
        pass


def _configured_record(name: str, preset: dict, var_parent: str, action: str) -> dict:
    return {
        "name": name,
        "action": action,
        "prim_path": _var_prim_path(var_parent, name),
        "source_name": preset["sourceName"],
        "source_type": preset["sourceType"],
        "data_type": preset["dataType"],
        "format": preset["format"],
        "multi_sampled": bool(preset.get("multisampled", False)),
        "cryptomatte": bool(preset.get("cryptomatte", False)),
    }


def _normalize_solaris_requests(aovs):
    """Return (requests, unsupported); requests is [(raw, name, preset), ...]."""
    seen = set()
    requests = []
    unsupported = []
    for raw in aovs:
        name = str(raw).strip().lower()
        if not name or name in seen:
            continue
        seen.add(name)
        preset = KARMA_AOV_PRESETS.get(name)
        if preset is None:
            unsupported.append(raw)
        else:
            requests.append((raw, name, preset))
    return requests, unsupported


def _configure_solaris_aovs(product, aovs: List[str], action: str) -> tuple:
    requests, unsupported = _normalize_solaris_requests(aovs)
    configured: list = []
    if not requests:
        return configured, unsupported

    if action == "remove":
        arv = _find_owned_arv(product)
        if arv is None:
            return configured, [raw for raw, _name, _preset in requests] + unsupported
        var_parent = _arv_var_parent(arv)
        current_names = _arv_existing_names(arv)
        remove_set = {name for _raw, name, _preset in requests}
        present = [name for name in current_names if name in remove_set]
        present_set = set(present)
        for raw, name, preset in requests:
            if name in present_set:
                configured.append(_configured_record(name, preset, var_parent, "removed"))
            else:
                unsupported.append(raw)
        if not present:
            return configured, unsupported
        remaining = [name for name in current_names if name not in remove_set]
        original_ordered = _read_ordered_vars(product)
        snapshot = _snapshot_arv(arv)
        try:
            _rewrite_arv(arv, remaining)
            _write_ordered_vars(
                product,
                _merge_ordered_vars(original_ordered, var_parent, current_names, remaining),
            )
        except Exception:  # noqa: BLE001
            _restore_arv(arv, snapshot)
            _write_ordered_vars(product, original_ordered)
            raise
        count_parm = arv.parm(_ARV_COUNT_PARM)
        if count_parm is None or int(count_parm.eval()) == 0:
            _unwire_and_destroy_arv(product, arv)
        return configured, unsupported

    # action == "add"
    pre_existing = _find_owned_arv(product)
    original_input = product.input(0)
    # Capture the node's own upstream before _get_or_create may rewire it, so a
    # failed add can restore both the product's input and the node's input.
    original_arv_input = pre_existing.input(0) if pre_existing is not None else None
    arv = _get_or_create_additional_rendervars(product)
    arv_created = pre_existing is None
    var_parent = _arv_var_parent(arv)
    current_names = _arv_existing_names(arv)
    target_names = list(current_names)
    existing_set = set(current_names)
    added = []
    for _raw, name, _preset in requests:
        if name in existing_set:
            continue
        target_names.append(name)
        existing_set.add(name)
        added.append(name)
    if not added:
        return configured, unsupported

    original_ordered = _read_ordered_vars(product)
    snapshot = _snapshot_arv(arv)
    image_state = _capture_image_format(product)
    try:
        _rewrite_arv(arv, target_names)
        _write_ordered_vars(
            product,
            _merge_ordered_vars(original_ordered, var_parent, current_names, target_names),
        )
        _ensure_product_image_format(product)
    except Exception:  # noqa: BLE001
        if arv_created:
            _unwire_and_destroy_arv(product, arv)
        else:
            _restore_arv(arv, snapshot)
            # Undo the input rewire _get_or_create performed for a pre-existing
            # node, so a failed add leaves the scene graph untouched.
            arv.setInput(0, original_arv_input)
        # Restore the product's original input unconditionally: _get_or_create
        # may have rewired it even for a pre-existing node.
        product.setInput(0, original_input)
        _write_ordered_vars(product, original_ordered)
        _restore_image_format(product, image_state)
        raise
    for name in added:
        configured.append(_configured_record(name, KARMA_AOV_PRESETS[name], var_parent, "added"))
    return configured, unsupported


def configure_aovs(
    rop_path: str,
    aovs: List[str],
    action: str = "add",
) -> dict:
    """Add or remove AOVs on the ROP/Solaris node at *rop_path*."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        if action not in ("add", "remove"):
            return skill_error(
                "Invalid action",
                "action must be 'add' or 'remove'",
                action=action,
            )
        node = get_node(hou, rop_path)
        is_solaris = rop_path.startswith("/stage")
        configured: list = []
        unsupported: list = []

        if is_solaris:
            product_type = _node_type_name(node)
            if product_type not in KARMA_PRODUCT_TYPES:
                return skill_error(
                    "Unsupported Solaris target",
                    "configure_aovs on Solaris requires a Render Product LOP ({}); node at '{}' is a '{}'. "
                    "Pass the path of the renderproduct LOP that should carry the AOVs.".format(
                        ", ".join(KARMA_PRODUCT_TYPES), rop_path, product_type or "unknown"
                    ),
                    node=node_summary(node),
                    node_type=product_type,
                    is_solaris=is_solaris,
                )
            configured, unsupported = _configure_solaris_aovs(node, aovs, action)
        else:
            configured, unsupported = _configure_mantra_aovs(node, aovs, action)

        return skill_success(
            "Configured AOVs",
            node=node_summary(node),
            configured=configured,
            unsupported=unsupported,
            action=action,
            is_solaris=is_solaris,
        )
    except UnsupportedSolarisTarget as exc:
        return skill_error("Unsupported Solaris target", str(exc))
    except Exception as exc:
        return skill_exception(exc, message="Failed to configure AOVs")


@skill_entry
def main(**kwargs) -> dict:
    return configure_aovs(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
