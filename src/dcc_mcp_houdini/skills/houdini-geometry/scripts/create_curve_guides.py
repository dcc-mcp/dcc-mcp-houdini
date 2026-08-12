"""Create bounded, typed polyline or NURBS guide geometry in a Stash SOP."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, List, Optional, Tuple

from _geo_common import get_node
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

MAX_GUIDES = 10_000
MAX_CVS = 1_000_000
MAX_CVS_PER_GUIDE = 4_096
MAX_INPUT_BYTES = 32 * 1024 * 1024
MAX_CLUSTER_NAME_BYTES = 256


def _error(message: str, error: str, **context: Any) -> dict:
    return skill_error(message, error, **context)


def _read_payload(guides: Optional[List[dict]], input_file: Optional[str]) -> Tuple[Any, dict]:
    if (guides is None) == (input_file is None):
        raise ValueError("Provide exactly one of guides or input_file")
    if input_file is None:
        return guides, {"kind": "inline_json"}

    path = Path(input_file).expanduser().resolve()
    if path.suffix.lower() != ".json":
        raise ValueError("input_file must have a .json suffix")
    if not path.is_file():
        raise ValueError("input_file does not exist: {}".format(path))
    size = path.stat().st_size
    if size > MAX_INPUT_BYTES:
        raise ValueError("input_file exceeds {} byte limit".format(MAX_INPUT_BYTES))
    raw = path.read_bytes()
    if len(raw) > MAX_INPUT_BYTES:
        raise ValueError("input_file exceeds {} byte limit".format(MAX_INPUT_BYTES))
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("input_file is not valid UTF-8 JSON: {}".format(exc)) from exc
    source = {
        "kind": "json_file",
        "file_path": str(path),
        "size_bytes": size,
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    if isinstance(payload, dict):
        unknown = sorted(set(payload) - {"guides"})
        if unknown:
            raise ValueError("input_file object has unsupported keys: {}".format(", ".join(unknown)))
        payload = payload.get("guides")
    return payload, source


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("{} must be a number".format(label))
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("{} must be finite".format(label))
    return number


def _vector(value: Any, size: int, label: str) -> Tuple[float, ...]:
    if not isinstance(value, (list, tuple)) or len(value) != size:
        raise ValueError("{} must contain {} numbers".format(label, size))
    return tuple(_finite_number(component, "{}[{}]".format(label, index)) for index, component in enumerate(value))


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("{} must be an integer".format(label))
    return value


def _normalize_guides(payload: Any) -> Tuple[List[dict], List[dict]]:
    if not isinstance(payload, list):
        raise ValueError("guides must be an array")
    if not payload:
        raise ValueError("guides must not be empty")
    if len(payload) > MAX_GUIDES:
        raise ValueError("guide count {} exceeds {} limit".format(len(payload), MAX_GUIDES))

    normalized = []
    rejected = []
    total_cvs = 0
    allowed = {"guide_id", "cluster_id", "cluster_name", "curve_type", "order", "cvs", "widths", "colors"}
    guide_ids = set()
    for index, raw in enumerate(payload):
        guide_id = raw.get("guide_id") if isinstance(raw, dict) else None
        try:
            if not isinstance(raw, dict):
                raise ValueError("guide must be an object")
            unknown = sorted(set(raw) - allowed)
            if unknown:
                raise ValueError("unsupported keys: {}".format(", ".join(unknown)))
            guide_id = _integer(raw.get("guide_id"), "guide_id")
            if guide_id in guide_ids:
                raise ValueError("guide_id must be unique")
            guide_ids.add(guide_id)
            cluster_id = _integer(raw.get("cluster_id"), "cluster_id")
            cluster_name = raw.get("cluster_name", "")
            if not isinstance(cluster_name, str):
                raise ValueError("cluster_name must be a string")
            if len(cluster_name.encode("utf-8")) > MAX_CLUSTER_NAME_BYTES:
                raise ValueError("cluster_name exceeds {} UTF-8 bytes".format(MAX_CLUSTER_NAME_BYTES))
            curve_type = raw.get("curve_type", "polyline")
            if curve_type not in {"polyline", "nurbs"}:
                raise ValueError("curve_type must be polyline or nurbs")
            order = _integer(raw.get("order", 4), "order")
            if order < 2 or order > 10:
                raise ValueError("order must be between 2 and 10")
            cvs_raw = raw.get("cvs")
            if not isinstance(cvs_raw, list) or len(cvs_raw) < 2:
                raise ValueError("cvs must contain at least two root-to-tip positions")
            if len(cvs_raw) > MAX_CVS_PER_GUIDE:
                raise ValueError("guide CV count exceeds {} limit".format(MAX_CVS_PER_GUIDE))
            if curve_type == "nurbs" and len(cvs_raw) < order:
                raise ValueError("nurbs guide CV count must be at least its order")
            cvs = [_vector(value, 3, "cvs[{}]".format(cv_index)) for cv_index, value in enumerate(cvs_raw)]
            widths_raw = raw.get("widths")
            if widths_raw is None:
                widths = [0.01] * len(cvs)
            else:
                if not isinstance(widths_raw, list) or len(widths_raw) != len(cvs):
                    raise ValueError("widths must match cvs length")
                widths = [_finite_number(value, "widths[{}]".format(i)) for i, value in enumerate(widths_raw)]
                if any(value < 0 for value in widths):
                    raise ValueError("widths must be non-negative")
            colors_raw = raw.get("colors")
            if colors_raw is None:
                colors = [(1.0, 1.0, 1.0)] * len(cvs)
            else:
                if not isinstance(colors_raw, list) or len(colors_raw) != len(cvs):
                    raise ValueError("colors must match cvs length")
                colors = [_vector(value, 3, "colors[{}]".format(i)) for i, value in enumerate(colors_raw)]
            total_cvs += len(cvs)
            if total_cvs > MAX_CVS:
                raise ValueError("total CV count exceeds {} limit".format(MAX_CVS))
            normalized.append(
                {
                    "guide_id": guide_id,
                    "cluster_id": cluster_id,
                    "cluster_name": cluster_name,
                    "curve_type": curve_type,
                    "order": order,
                    "cvs": cvs,
                    "widths": widths,
                    "colors": colors,
                }
            )
        except ValueError as exc:
            rejected.append({"index": index, "guide_id": guide_id, "error": str(exc)})
    return normalized, rejected


def _build_geometry(hou: Any, normalized: List[dict]) -> Any:
    geometry = hou.Geometry()
    point_attributes = {
        "u": geometry.addAttrib(hou.attribType.Point, "u", 0.0),
        "root_flag": geometry.addAttrib(hou.attribType.Point, "root_flag", 0),
        "Cd": geometry.addAttrib(hou.attribType.Point, "Cd", (1.0, 1.0, 1.0)),
        "width": geometry.addAttrib(hou.attribType.Point, "width", 0.01),
    }
    primitive_attributes = {
        "guide_id": geometry.addAttrib(hou.attribType.Prim, "guide_id", 0),
        "cluster_id": geometry.addAttrib(hou.attribType.Prim, "cluster_id", 0),
        "cluster_name": geometry.addAttrib(hou.attribType.Prim, "cluster_name", ""),
    }
    for guide in normalized:
        if guide["curve_type"] == "nurbs":
            # Positional arguments are required for compatibility with the
            # Houdini 22.0 HOM binding, whose exposed keyword name differs
            # from the current documentation.
            primitive = geometry.createNURBSCurve(len(guide["cvs"]), False, guide["order"])
            points = [vertex.point() for vertex in primitive.vertices()]
        else:
            primitive = geometry.createPolygon(False)
            points = [geometry.createPoint() for _ in guide["cvs"]]
        denominator = float(len(guide["cvs"]) - 1)
        for index, (position, point) in enumerate(zip(guide["cvs"], points)):
            point.setPosition(position)
            point.setAttribValue(point_attributes["u"], index / denominator)
            point.setAttribValue(point_attributes["root_flag"], 1 if index == 0 else 0)
            point.setAttribValue(point_attributes["Cd"], guide["colors"][index])
            point.setAttribValue(point_attributes["width"], guide["widths"][index])
            if guide["curve_type"] == "polyline":
                primitive.addVertex(point)
        primitive.setAttribValue(primitive_attributes["guide_id"], guide["guide_id"])
        primitive.setAttribValue(primitive_attributes["cluster_id"], guide["cluster_id"])
        primitive.setAttribValue(primitive_attributes["cluster_name"], guide["cluster_name"])
    return geometry


def _bounds(geometry: Any) -> dict:
    bbox = geometry.boundingBox()
    return {
        "min": [float(value) for value in bbox.minvec()],
        "max": [float(value) for value in bbox.maxvec()],
        "size": [float(value) for value in bbox.sizevec()],
    }


def create_curve_guides(
    parent_path: str,
    guides: Optional[List[dict]] = None,
    input_file: Optional[str] = None,
    node_name: Optional[str] = None,
    set_display: bool = True,
) -> dict:
    """Validate all input, then atomically create editable guide geometry."""
    try:
        payload, source = _read_payload(guides, input_file)
        normalized, rejected = _normalize_guides(payload)
    except (OSError, ValueError) as exc:
        return _error("Curve guide input failed validation: {}".format(exc), str(exc), rejected_guides=[])
    if rejected:
        return _error(
            "Curve guide input failed validation",
            "{} guide(s) were rejected; no scene changes were made".format(len(rejected)),
            rejected_guides=rejected,
        )

    node = None
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return _error("Houdini not available", "hou could not be imported")

    try:
        parent = get_node(hou, parent_path)
        geometry = _build_geometry(hou, normalized)
        increment_data_ids = getattr(geometry, "incrementAllDataIds", None)
        if callable(increment_data_ids):
            increment_data_ids()
        node = parent.createNode("stash", node_name=node_name)
        stash_parm = node.parm("stash")
        if stash_parm is None:
            raise ValueError("Created Stash SOP has no stash data parameter")
        stash_parm.set(geometry)
        if set_display and hasattr(node, "setDisplayFlag"):
            node.setDisplayFlag(True)
        cv_count = sum(len(guide["cvs"]) for guide in normalized)
        cluster_count = len({guide["cluster_id"] for guide in normalized})
        return skill_success(
            "Created bounded Houdini curve guides",
            parent_path=parent.path(),
            node_path=node.path(),
            source=source,
            topology=sorted({guide["curve_type"] for guide in normalized}),
            cv_order="root_to_tip",
            metrics={
                "curve_count": len(normalized),
                "cv_count": cv_count,
                "cluster_count": cluster_count,
                "root_count": len(normalized),
                "root_to_tip_valid": True,
                "bounds": _bounds(geometry),
            },
            attribute_schema={
                "point": ["u", "root_flag", "Cd", "width"],
                "primitive": ["guide_id", "cluster_id", "cluster_name"],
            },
            rejected_guides=[],
            limits={
                "max_guides": MAX_GUIDES,
                "max_total_cvs": MAX_CVS,
                "max_cvs_per_guide": MAX_CVS_PER_GUIDE,
                "max_input_bytes": MAX_INPUT_BYTES,
            },
        )
    except Exception as exc:
        if node is not None:
            try:
                node.destroy()
            except Exception:  # noqa: BLE001 - preserve the authoring failure
                pass
        return skill_exception(exc, message="Failed to create Houdini curve guides")


@skill_entry
def main(**kwargs: Any) -> dict:
    return create_curve_guides(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
