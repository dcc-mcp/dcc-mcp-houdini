"""Configure AOVs (Arbitrary Output Variables) on a render node or Solaris product."""

from __future__ import annotations

from typing import List

from _render_common import get_node, node_summary, set_first_parm  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

# Common AOV presets with their source names
AOV_PRESETS = {
    "diffuse": {"source": "diffuse", "type": "color"},
    "specular": {"source": "specular", "type": "color"},
    "transmission": {"source": "transmission", "type": "color"},
    "normal": {"source": "normal", "type": "vector"},
    "depth": {"source": "depth", "type": "float"},
    "motionvector": {"source": "motionvector", "type": "vector"},
    "albedo": {"source": "albedo", "type": "color"},
    "opacity": {"source": "opacity", "type": "color"},
    "emission": {"source": "emission", "type": "color"},
    "volume": {"source": "volume", "type": "color"},
    "cryptomatte": {"source": "cryptomatte", "type": "color"},
    "objectid": {"source": "objectid", "type": "int"},
    "materialid": {"source": "materialid", "type": "int"},
    "uv": {"source": "uv", "type": "vector"},
    "worldpos": {"source": "worldpos", "type": "vector"},
}

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
            # Solaris: iterate render vars under a render product
            for aov_name in aovs:
                if action == "remove":
                    rv_node = node.node(aov_name)
                    if rv_node:
                        rv_node.destroy()
                        configured.append({"name": aov_name, "action": "removed"})
                    else:
                        unsupported.append(aov_name)
                else:
                    preset = AOV_PRESETS.get(aov_name.lower(), {"source": aov_name, "type": "raw"})
                    rv_node = node.createNode("rendervar", node_name=aov_name)
                    set_first_parm(rv_node, ("sourceName", "sourcename"), preset["source"])
                    set_first_parm(rv_node, ("sourceType", "sourcetype"), preset["type"])
                    configured.append(
                        {
                            "name": aov_name,
                            "source": preset["source"],
                            "type": preset["type"],
                            "path": rv_node.path(),
                        }
                    )
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
    except Exception as exc:
        return skill_exception(exc, message="Failed to configure AOVs")


@skill_entry
def main(**kwargs) -> dict:
    return configure_aovs(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
