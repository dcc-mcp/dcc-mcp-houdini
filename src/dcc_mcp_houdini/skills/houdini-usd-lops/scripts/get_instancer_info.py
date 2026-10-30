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
    """Return the value of array attribute *name* at *time*, else ``None``."""
    attribute = prim.GetAttribute(name)
    if not attribute:
        return None
    return attribute.Get(time)


def _num_time_samples(attribute: Any) -> int:
    """Return the authored time-sample count, or 0 when the API is absent."""
    get_count = getattr(attribute, "GetNumTimeSamples", None)
    if not callable(get_count):
        return 0
    try:
        return int(get_count())
    except (TypeError, ValueError):
        return 0


def _earliest_numeric_time(prim: Any, names: Any) -> Any:
    """Return the smallest numeric time sample across *names*, else ``"earliest"``."""
    earliest = None
    for name in names:
        attribute = prim.GetAttribute(name)
        get_samples = getattr(attribute, "GetTimeSamples", None)
        if not callable(get_samples):
            continue
        try:
            samples = list(get_samples())
        except (TypeError, ValueError):
            continue
        for sample in samples:
            try:
                value = float(sample)
            except (TypeError, ValueError):
                continue
            if earliest is None or value < earliest:
                earliest = value
    return earliest if earliest is not None else "earliest"


def _array_count(value: Any) -> int:
    if value is None:
        return 0
    try:
        return len(value)
    except TypeError:
        return 0


def _normalize_element(element: Any) -> Any:
    """Turn a non-iterable Gf quaternion into a numeric ``[real, i, j, k]`` list.

    ``bounded_value`` falls back to ``str(value)`` for objects it cannot iterate,
    which would turn an orientation into ``"(1, 0, 0, 0)"``. USD quats expose a
    real part and a 3-vector imaginary part; decompose either API shape so the
    sample stays a parseable numeric array.
    """
    get_real = getattr(element, "GetReal", None)
    get_imag = getattr(element, "GetImaginary", None)
    if callable(get_real) and callable(get_imag):
        try:
            imaginary = get_imag()
            return [float(get_real()), float(imaginary[0]), float(imaginary[1]), float(imaginary[2])]
        except (TypeError, ValueError, IndexError, KeyError):
            return element
    real = getattr(element, "real", None)
    imaginary = getattr(element, "imaginary", None)
    if real is not None and imaginary is not None and not isinstance(element, (int, float)):
        try:
            return [float(real), float(imaginary[0]), float(imaginary[1]), float(imaginary[2])]
        except (TypeError, ValueError, IndexError, KeyError):
            return element
    return element


def _bounded_sample(value: Any, max_values: int) -> Optional[dict]:
    """Return a size-bounded, JSON-safe sample without materialising the array.

    A lazy generator keeps a multi-million-instance scatter bounded on the main
    thread; quaternion elements are normalised before ``bounded_value`` sees them.
    """
    if value is None:
        return None
    return bounded_value((_normalize_element(item) for item in value), max_values, 1024)


def _read_arrays(prim: Any, time: Any, max_values: int) -> tuple:
    """Read every instance array once: full count plus a bounded, safe sample."""
    raw, arrays, counts = {}, {}, {}
    for name in _INSTANCE_ARRAYS:
        value = _authored_array(prim, name, time)
        raw[name] = value
        arrays[name] = _bounded_sample(value, max_values)
        counts[name] = _array_count(value)
    return raw, arrays, counts


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

    A LOP scatter often writes its arrays only as per-frame time samples (no
    default value). At ``Usd.TimeCode.Default()`` those arrays read empty, which
    would otherwise look like "0 instances, all consistent" — a false pass for a
    validation tool. When no explicit ``time_code`` is given and such arrays are
    detected, the arrays are re-read at the earliest time sample (so the data is
    real), the effective time is reported, and ``time_samples_require_time_code``
    is flagged so ``consistent`` is never a silent green on frame-varying data.
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

        # Prototype relationship: which asset prims the scatter references.
        relationship = prim.GetRelationship("prototypes")
        targets = list(relationship.GetTargets()) if relationship else []
        prototype_count = len(targets)
        prototypes_truncated = prototype_count > max_prototypes
        prototypes = [str(target) for target in targets[:max_prototypes]]

        requested_time = make_time_code(Usd, time_code)
        raw, arrays, counts = _read_arrays(prim, requested_time, max_values)

        # Detect arrays authored only as time samples (empty at Default()). Re-read
        # everything at the earliest sample so validation uses real, frame-varying
        # data, and flag that a definitive verdict needs an explicit time_code.
        time_sampled_arrays = []
        time_code_source = "default" if time_code is None else "explicit"
        effective_time_code = "default" if time_code is None else float(time_code)
        if time_code is None:
            for name in _INSTANCE_ARRAYS:
                attribute = prim.GetAttribute(name)
                if attribute and _num_time_samples(attribute) > 0 and counts[name] == 0:
                    time_sampled_arrays.append(name)
            if time_sampled_arrays:
                earliest = Usd.TimeCode.EarliestTime()
                raw, arrays, counts = _read_arrays(prim, earliest, max_values)
                time_code_source = "earliest_sample"
                effective_time_code = _earliest_numeric_time(prim, time_sampled_arrays)

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
        if time_sampled_arrays:
            issue_codes.append("time_samples_require_time_code")
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
            time_code_source=time_code_source,
            effective_time_code=effective_time_code,
            time_sampled_arrays=time_sampled_arrays,
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
