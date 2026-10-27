"""Read bounded field metadata from a clean, already-cooked DOP network."""

from __future__ import annotations

import math
from itertools import islice

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

from dcc_mcp_houdini._bounded_values import require_range
from dcc_mcp_houdini._domain_graph import get_node, hou_missing_error, require_category


def _exact_path(value, label, absolute=False, allow_path=True):
    if not isinstance(value, str) or not value or len(value) > 1024:
        raise ValueError("{} must be a nonempty string of at most 1024 characters".format(label))
    if value.startswith("/") != absolute:
        raise ValueError("{} must be {}".format(label, "absolute" if absolute else "relative"))
    parts = value[1:].split("/") if absolute else value.split("/")
    if (
        any(part in ("", ".", "..") for part in parts)
        or not allow_path
        and len(parts) != 1
        or any(char.isspace() or ord(char) < 32 or ord(char) == 127 or char in "*?[]\\" for char in value)
    ):
        raise ValueError("{} must be an exact name or path without patterns or traversal".format(label))


def _network_state(hou, network):
    count = network.cookCount()
    if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
        raise ValueError("DOP network must already have cooked before inspection")
    if network.needsToCook() is not False:
        raise ValueError("DOP network must be clean; inspection will not cook it")
    return {"frame": hou.frame(), "cook_count": count}


def _field_metadata(obj, name):
    item = {"name": name}
    try:
        parent_path, _, leaf = name.rpartition("/")
        parent = obj.findSubData(parent_path) if parent_path else obj
        data = parent.subData().get(leaf) if parent is not None else None
        if data is None:
            return dict(item, status="missing")
        item["data_type"] = data.dataType()
        geometry = parent.fieldGeometry(leaf)
        if geometry is None:
            return dict(item, status="not_field")
        primitives = list(islice(geometry.iterPrims(), 17))
        if len(primitives) > 16:
            raise ValueError("Field exceeds the 16-component inspection limit")
        name_attrib = geometry.findPrimAttrib("name")
        components = []
        for prim in primitives:
            resolution, voxel_size = list(prim.resolution()), list(prim.voxelSize())
            if len(resolution) != 3 or len(voxel_size) != 3 or not all(math.isfinite(v) for v in voxel_size):
                raise ValueError("Field component has invalid resolution or voxel size metadata")
            components.append(
                {
                    "name": prim.attribValue(name_attrib) if name_attrib is not None else None,
                    "primitive_type": prim.type().name(),
                    "resolution": resolution,
                    "voxel_size": voxel_size,
                }
            )
        return dict(item, status="ok", components=components)
    except Exception as exc:
        return dict(item, status="read_error", error_type=type(exc).__name__, error=str(exc))


def inspect_simulation_fields(network_path: str, object_name: str, field_names=None, max_fields: int = 16) -> dict:
    try:
        _exact_path(network_path, "network_path", absolute=True)
        _exact_path(object_name, "object_name", allow_path=False)
        require_range(max_fields, "max_fields", 1, 32)
        if field_names is not None:
            if not isinstance(field_names, (list, tuple)) or not 1 <= len(field_names) <= 32:
                raise ValueError("field_names must contain 1 to 32 exact relative names or paths")
            for name in field_names:
                _exact_path(name, "field name")
            if len(set(field_names)) != len(field_names):
                raise ValueError("field_names must not contain duplicates")
    except Exception as exc:
        return skill_exception(exc, message="Invalid simulation field inspection arguments")
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return hou_missing_error()
    try:
        network = require_category(get_node(hou, network_path), "Dop", children=True)
        before = _network_state(hou, network)
        simulation = network.simulation()
        before["simulation_time"] = simulation.time()
        after_time = simulation.time()
        after = dict(_network_state(hou, network), simulation_time=after_time)
        if before != after:
            return skill_error(
                "Simulation state changed during access",
                "Frame, cook count or simulation time changed",
                before=before,
                after=after,
            )
        obj = simulation.findObject(object_name)
        if obj is None:
            return skill_error("Simulation object not found", object_name)
        if obj.name() != object_name:
            raise ValueError("Simulation object lookup did not return the exact requested name")
        names = list(field_names) if field_names is not None else sorted(obj.subData())
        object_id = obj.objid()
        fields = [_field_metadata(obj, name) for name in names[:max_fields]]
        after_time = simulation.time()
        after = dict(_network_state(hou, network), simulation_time=after_time)
        if before != after:
            return skill_error(
                "Simulation state changed during inspection",
                "Frame, cook count or simulation time changed; metadata discarded",
                before=before,
                after=after,
            )
        return skill_success(
            "Inspected simulation field metadata",
            network_path=network_path,
            object_name=object_name,
            object_id=object_id,
            frame=before["frame"],
            simulation_time=before["simulation_time"],
            before=before,
            after=after,
            fields=fields,
            total_entries=len(names),
            truncated=len(names) > max_fields,
            scope="field_metadata_only",
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to inspect simulation fields")


@skill_entry
def main(**kwargs) -> dict:
    return inspect_simulation_fields(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
