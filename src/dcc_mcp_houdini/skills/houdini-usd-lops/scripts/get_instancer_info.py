"""Inspect a USD PointInstancer (scattered assets) on a composed Solaris Stage."""

from __future__ import annotations

from typing import Any, Optional

from _usd_common import (  # noqa: E402
    bounded_value,
    make_time_code,
    require_range,
    resolve_prim,
    resolve_stage,
)
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

# Canonical UsdGeomPointInstancer arrays. ``protoIndices`` defines the instance
# count; positions/orientations/scales are per-instance transforms (one entry per
# instance when authored); invisibleIds is a sparse id list, so its length is not
# expected to match the instance count.
_INSTANCE_ARRAYS = ("protoIndices", "positions", "orientations", "scales", "invisibleIds")
_PER_INSTANCE_ARRAYS = ("positions", "orientations", "scales")


def _is_point_instancer(UsdGeom: Any, prim: Any) -> bool:
    """Return True when *prim* is a UsdGeomPointInstancer (scattered assets)."""
    schema = UsdGeom.PointInstancer(prim)
    return bool(schema)


def _authored_array(prim: Any, name: str, time: Any) -> Any:
    """Return the authored value of array attribute *name*, else ``None``."""
    attribute = prim.GetAttribute(name)
    if not attribute:
        return None
    return attribute.Get(time)


def _array_count(value: Any) -> int:
    if value is None:
        return 0
    try:
        return len(value)
    except TypeError:
        return 0


def _bounded_sample(value: Any, max_values: int) -> Optional[dict]:
    """Return a size-bounded, JSON-safe sample of an authored array."""
    if value is None:
        return None
    return bounded_value(list(value), max_values, 1024)


def get_instancer_info(
    lop_node_path: str,
    prim_path: str,
    time_code: Optional[float] = None,
    max_values: int = 64,
    max_prototypes: int = 64,
) -> dict:
    """Inspect and validate a USD PointInstancer on a LOP node's composed Stage.

    Reports the prototype prims, the bounded ``protoIndices`` and per-instance
    transform arrays, and a decidable ``validation`` verdict so a caller can
    assert whether a scattered-asset setup is well formed without authoring any
    change to the stage.
    """
    try:
        import hou  # noqa: PLC0415
        from pxr import Usd, UsdGeom  # noqa: PLC0415
    except ImportError as exc:
        return skill_error("Houdini USD APIs not available", str(exc))

    try:
        require_range(max_values, "max_values", 1, 256)
        require_range(max_prototypes, "max_prototypes", 1, 256)
        node, stage = resolve_stage(hou, lop_node_path)
        prim = resolve_prim(stage, prim_path)
        if not _is_point_instancer(UsdGeom, prim):
            raise ValueError("USD prim is not a PointInstancer: {} (type {})".format(prim_path, prim.GetTypeName()))
        usd_time = make_time_code(Usd, time_code)

        # Prototype relationship: which asset prims the scatter references.
        relationship = prim.GetRelationship("prototypes")
        targets = list(relationship.GetTargets()) if relationship else []
        prototype_count = len(targets)
        prototypes_truncated = prototype_count > max_prototypes
        prototypes = [str(target) for target in targets[:max_prototypes]]

        # One read per array: full count, plus a bounded JSON-safe sample.
        arrays = {}
        counts = {}
        raw = {}
        for name in _INSTANCE_ARRAYS:
            value = _authored_array(prim, name, usd_time)
            raw[name] = value
            arrays[name] = _bounded_sample(value, max_values)
            counts[name] = _array_count(value)

        instance_count = counts["protoIndices"]
        indices = raw["protoIndices"]

        # protoIndices map each instance to a prototype; validate the range.
        out_of_range = 0
        if indices is not None:
            for index in indices:
                if not isinstance(index, int) or isinstance(index, bool):
                    out_of_range += 1
                elif index < 0 or index >= prototype_count:
                    out_of_range += 1

        mismatched = []
        for name in _PER_INSTANCE_ARRAYS:
            if counts[name] and counts[name] != instance_count:
                mismatched.append(name)

        issue_codes = []
        if out_of_range:
            issue_codes.append("proto_indices_out_of_range")
        if instance_count and not prototype_count:
            issue_codes.append("missing_prototypes")
        for name in mismatched:
            issue_codes.append("{}_length_mismatch".format(name))

        validation = {
            "instance_count": instance_count,
            "prototype_count": prototype_count,
            "proto_indices_in_range": out_of_range == 0,
            "out_of_range_count": out_of_range,
            "per_instance_arrays_match": not mismatched,
            "consistent": not issue_codes,
            "issue_codes": issue_codes,
        }

        return skill_success(
            "Inspected USD PointInstancer",
            lop_node_path=str(node.path()),
            prim_path=str(prim.GetPath()),
            time_code="default" if time_code is None else float(time_code),
            type_name=str(prim.GetTypeName()),
            instance_count=instance_count,
            prototype_count=prototype_count,
            prototypes=prototypes,
            prototypes_truncated=prototypes_truncated,
            proto_indices=arrays["protoIndices"],
            instance_arrays=arrays,
            array_counts=counts,
            validation=validation,
            bounds={"max_values": max_values, "max_prototypes": max_prototypes},
        )
    except ValueError as exc:
        return skill_error("Invalid USD PointInstancer query", str(exc))
    except Exception as exc:
        return skill_exception(exc, message="Failed to inspect USD PointInstancer")


@skill_entry
def main(**kwargs) -> dict:
    return get_instancer_info(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
