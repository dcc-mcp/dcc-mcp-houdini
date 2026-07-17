"""Validate a bounded OBJ animation loop without inspecting geometry."""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_MAX_NODES = 64
_MAX_NODE_PATH_LENGTH = 512
_MAX_ABS_FRAME = 1_000_000.0
_MAX_SAMPLE_STEP = 1_000.0
_TRANSFORM_PARMS = ("tx", "ty", "tz", "rx", "ry", "rz", "sx", "sy", "sz")
_DEFAULT_TOLERANCES = {
    "matrix_max_abs": 1.0e-4,
    "translation": 1.0e-4,
    "angular_degrees": 0.1,
    "scale": 1.0e-4,
    "linear_velocity": 1.0e-3,
    "angular_velocity_degrees": 0.5,
    "linear_acceleration": 1.0e-2,
    "angular_acceleration_degrees": 2.0,
}


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("{} must be a finite number".format(label))
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("{} must be a finite number".format(label))
    return number


def _validate_request(
    node_paths: Any,
    start_frame: Any,
    end_frame: Any,
    sample_step: Any,
    tolerances: Any,
    max_expression_chars: Any,
) -> Tuple[List[str], float, float, float, Dict[str, float], int]:
    if not isinstance(node_paths, list) or not node_paths:
        raise ValueError("node_paths must contain between 1 and 64 OBJ node paths")
    if len(node_paths) > _MAX_NODES:
        raise ValueError("node_paths accepts at most 64 paths")

    validated_paths = []
    seen = set()
    for node_path in node_paths:
        if not isinstance(node_path, str) or not node_path.startswith("/obj/"):
            raise ValueError("Every node path must be under /obj")
        if len(node_path) > _MAX_NODE_PATH_LENGTH or any(character.isspace() for character in node_path):
            raise ValueError("OBJ node paths must be at most 512 characters and contain no whitespace")
        if node_path in seen:
            raise ValueError("node_paths must be unique")
        seen.add(node_path)
        validated_paths.append(node_path)

    start = _finite_number(start_frame, "start_frame")
    end = _finite_number(end_frame, "end_frame")
    step = _finite_number(sample_step, "sample_step")
    if abs(start) > _MAX_ABS_FRAME or abs(end) > _MAX_ABS_FRAME:
        raise ValueError("start_frame and end_frame are bounded to +/-1000000")
    if step <= 0.0 or step > _MAX_SAMPLE_STEP:
        raise ValueError("sample_step must be greater than zero and at most 1000")
    if abs(end + step) > _MAX_ABS_FRAME:
        raise ValueError("The virtual end_frame + sample_step sample is bounded to +/-1000000")
    if end <= start:
        raise ValueError("end_frame must be greater than start_frame")
    if end - start < (4.0 * step) - 1.0e-9:
        raise ValueError("The loop range must span at least four sample steps")

    if isinstance(max_expression_chars, bool) or not isinstance(max_expression_chars, int):
        raise ValueError("max_expression_chars must be an integer")
    if max_expression_chars < 0 or max_expression_chars > 512:
        raise ValueError("max_expression_chars must be between 0 and 512")

    merged_tolerances = dict(_DEFAULT_TOLERANCES)
    if tolerances is not None:
        if not isinstance(tolerances, dict):
            raise ValueError("tolerances must be an object")
        unknown = sorted(set(tolerances) - set(_DEFAULT_TOLERANCES))
        if unknown:
            raise ValueError("Unknown tolerance keys: {}".format(", ".join(unknown)))
        for name, value in tolerances.items():
            number = _finite_number(value, "tolerances.{}".format(name))
            if number < 0.0:
                raise ValueError("tolerances.{} must be non-negative".format(name))
            merged_tolerances[name] = number

    return validated_paths, start, end, step, merged_tolerances, max_expression_chars


def _sample_frames(start: float, end: float, step: float) -> List[float]:
    candidates = [start, start + step, start + (2.0 * step), end - step, end, end + step]
    frames = []
    for candidate in candidates:
        if not frames or all(abs(candidate - existing) > 1.0e-9 for existing in frames):
            frames.append(float(candidate))
    return frames


def _float_tuple(values: Iterable[Any], expected: int, label: str) -> Tuple[float, ...]:
    result = tuple(float(value) for value in values)
    if len(result) != expected:
        raise ValueError("{} returned {} values; expected {}".format(label, len(result), expected))
    return result


def _vector_sub(left: Sequence[float], right: Sequence[float]) -> Tuple[float, ...]:
    return tuple(a - b for a, b in zip(left, right))


def _vector_scale(vector: Sequence[float], scale: float) -> Tuple[float, ...]:
    return tuple(value * scale for value in vector)


def _vector_norm(vector: Sequence[float]) -> float:
    return math.sqrt(sum(value * value for value in vector))


def _max_abs_delta(left: Sequence[float], right: Sequence[float]) -> float:
    return max(abs(a - b) for a, b in zip(left, right))


def _normalize_quaternion(quaternion: Sequence[float]) -> Tuple[float, float, float, float]:
    length = _vector_norm(quaternion)
    if not math.isfinite(length) or length <= 1.0e-12:
        raise ValueError("Rotation matrix produced an invalid orientation")
    return tuple(value / length for value in quaternion)  # type: ignore[return-value]


def _matrix3_quaternion(values: Sequence[float]) -> Tuple[float, float, float, float]:
    """Convert Houdini's row-vector 3x3 matrix to a normalized quaternion."""
    matrix = _float_tuple(values, 9, "extractRotationMatrix3")
    # Quaternion conversion formulas conventionally use column vectors, so
    # transpose Houdini's row-vector matrix while unpacking it.
    m00, m10, m20, m01, m11, m21, m02, m12, m22 = matrix
    trace = m00 + m11 + m22
    if trace > 0.0:
        scale = math.sqrt(trace + 1.0) * 2.0
        quaternion = (0.25 * scale, (m21 - m12) / scale, (m02 - m20) / scale, (m10 - m01) / scale)
    elif m00 > m11 and m00 > m22:
        scale = math.sqrt(max(0.0, 1.0 + m00 - m11 - m22)) * 2.0
        quaternion = ((m21 - m12) / scale, 0.25 * scale, (m01 + m10) / scale, (m02 + m20) / scale)
    elif m11 > m22:
        scale = math.sqrt(max(0.0, 1.0 + m11 - m00 - m22)) * 2.0
        quaternion = ((m02 - m20) / scale, (m01 + m10) / scale, 0.25 * scale, (m12 + m21) / scale)
    else:
        scale = math.sqrt(max(0.0, 1.0 + m22 - m00 - m11)) * 2.0
        quaternion = ((m10 - m01) / scale, (m02 + m20) / scale, (m12 + m21) / scale, 0.25 * scale)
    return _normalize_quaternion(quaternion)


def _quaternion_multiply(left: Sequence[float], right: Sequence[float]) -> Tuple[float, float, float, float]:
    lw, lx, ly, lz = left
    rw, rx, ry, rz = right
    return (
        (lw * rw) - (lx * rx) - (ly * ry) - (lz * rz),
        (lw * rx) + (lx * rw) + (ly * rz) - (lz * ry),
        (lw * ry) - (lx * rz) + (ly * rw) + (lz * rx),
        (lw * rz) + (lx * ry) - (ly * rx) + (lz * rw),
    )


def _angular_delta_vector_degrees(start: Sequence[float], end: Sequence[float]) -> Tuple[float, float, float]:
    start_q = _normalize_quaternion(start)
    end_q = _normalize_quaternion(end)
    if sum(a * b for a, b in zip(start_q, end_q)) < 0.0:
        end_q = tuple(-value for value in end_q)
    relative = _normalize_quaternion(_quaternion_multiply(end_q, (start_q[0], -start_q[1], -start_q[2], -start_q[3])))
    if relative[0] < 0.0:
        relative = tuple(-value for value in relative)
    sine_half = _vector_norm(relative[1:])
    if sine_half <= 1.0e-12:
        return (0.0, 0.0, 0.0)
    angle_degrees = math.degrees(2.0 * math.atan2(sine_half, max(0.0, relative[0])))
    return tuple((component / sine_half) * angle_degrees for component in relative[1:])  # type: ignore[return-value]


def _json_number(value: float) -> Optional[float]:
    return float(value) if math.isfinite(value) else None


def _json_vector(values: Sequence[float]) -> List[Optional[float]]:
    return [_json_number(value) for value in values]


def _snapshot(node: Any) -> Dict[str, Any]:
    matrix = node.worldTransform()
    matrix_values = _float_tuple(matrix.asTuple(), 16, "worldTransform")
    translation = _float_tuple(matrix.extractTranslates(), 3, "extractTranslates")
    rotation_euler = _float_tuple(matrix.extractRotates(), 3, "extractRotates")
    scale = _float_tuple(matrix.extractScales(), 3, "extractScales")
    rotation_matrix = matrix.extractRotationMatrix3()
    orientation = _matrix3_quaternion(rotation_matrix.asTuple())
    finite = all(
        math.isfinite(value)
        for values in (matrix_values, translation, rotation_euler, scale, orientation)
        for value in values
    )
    return {
        "matrix": matrix_values,
        "translation": translation,
        "rotation_euler_degrees": rotation_euler,
        "scale": scale,
        "orientation": orientation,
        "finite": finite,
    }


def _expression_summary(parm: Any, max_chars: int) -> Tuple[Optional[str], Optional[str], bool]:
    try:
        expression = str(parm.expression())
    except Exception:  # noqa: BLE001 - HOM raises when no expression exists
        return None, None, False
    language = None
    try:
        expression_language = parm.expressionLanguage()
        language = expression_language.name() if hasattr(expression_language, "name") else str(expression_language)
    except Exception:  # noqa: BLE001
        language = None
    truncated = len(expression) > max_chars
    return expression[:max_chars], language, truncated


def _keyframe_summary(parm: Any) -> Tuple[int, Optional[float], Optional[float]]:
    try:
        keyframes = list(parm.keyframes())
    except Exception:  # noqa: BLE001
        return 0, None, None
    frames = []
    for keyframe in keyframes:
        try:
            frames.append(float(keyframe.frame()))
        except Exception:  # noqa: BLE001
            continue
    return len(keyframes), min(frames) if frames else None, max(frames) if frames else None


def _driver_summary(node: Any, max_expression_chars: int) -> Dict[str, Any]:
    counts = {"expression": 0, "keyframes": 0, "static": 0, "time_dependent": 0}
    parameters = []
    for parm_name in _TRANSFORM_PARMS:
        parm = node.parm(parm_name)
        if parm is None:
            continue
        expression, language, truncated = _expression_summary(parm, max_expression_chars)
        keyframe_count, first_keyframe, last_keyframe = _keyframe_summary(parm)
        try:
            time_dependent = bool(parm.isTimeDependent())
        except Exception:  # noqa: BLE001
            time_dependent = False
        if expression is not None:
            driver = "expression"
        elif keyframe_count:
            driver = "keyframes"
        elif time_dependent:
            driver = "time_dependent"
        else:
            driver = "static"
        counts[driver] += 1
        parameters.append(
            {
                "name": parm_name,
                "driver": driver,
                "expression_preview": expression,
                "expression_language": language,
                "expression_truncated": truncated,
                "keyframe_count": keyframe_count,
                "first_keyframe": first_keyframe,
                "last_keyframe": last_keyframe,
                "time_dependent": time_dependent,
            }
        )
    return {"counts": counts, "parameters": parameters}


def _public_endpoint(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "translation": _json_vector(snapshot["translation"]),
        "rotation_euler_degrees": _json_vector(snapshot["rotation_euler_degrees"]),
        "scale": _json_vector(snapshot["scale"]),
    }


def _empty_transform_delta() -> Dict[str, None]:
    return {
        "matrix_max_abs": None,
        "translation_distance": None,
        "angular_degrees": None,
        "scale_max_abs": None,
    }


def _failed_metrics() -> Tuple[Dict[str, None], Dict[str, None], Dict[str, Any], Dict[str, Any]]:
    endpoint_duplicate = _empty_transform_delta()
    periodic = _empty_transform_delta()
    velocity = {
        "linear_vector_per_second": None,
        "linear_magnitude_per_second": None,
        "angular_vector_degrees_per_second": None,
        "angular_magnitude_degrees_per_second": None,
    }
    acceleration = {
        "linear_vector_per_second2": None,
        "linear_magnitude_per_second2": None,
        "angular_vector_degrees_per_second2": None,
        "angular_magnitude_degrees_per_second2": None,
    }
    return endpoint_duplicate, periodic, velocity, acceleration


def _evaluate_node(
    node_path: str,
    snapshots: Dict[float, Dict[str, Any]],
    frames: Sequence[float],
    fps: float,
    step: float,
    tolerances: Dict[str, float],
    drivers: Dict[str, Any],
    errors: List[str],
) -> Dict[str, Any]:
    finite = not errors and len(snapshots) == len(frames) and all(snapshot["finite"] for snapshot in snapshots.values())
    checks = {"finite": finite}
    if not finite:
        endpoint_duplicate, periodic, velocity, acceleration = _failed_metrics()
        checks.update(
            {
                "periodic_matrix": False,
                "periodic_translation": False,
                "periodic_angular": False,
                "periodic_scale": False,
                "linear_velocity": False,
                "angular_velocity": False,
                "linear_acceleration": False,
                "angular_acceleration": False,
            }
        )
        return {
            "node_path": node_path,
            "resolved": True,
            "finite": False,
            "passed": False,
            "duplicate_endpoint_hold_risk": False,
            "endpoints": None,
            "endpoint_duplicate_delta": endpoint_duplicate,
            "periodic_delta": periodic,
            "velocity_residuals": velocity,
            "acceleration_residuals": acceleration,
            "drivers": drivers,
            "checks": checks,
            "errors": errors or ["One or more transform samples were non-finite"],
        }

    start, start_one, start_two = (snapshots[frames[index]] for index in (0, 1, 2))
    end_one, end, periodic_next = (snapshots[frames[index]] for index in (-3, -2, -1))
    seconds_per_step = step / fps

    endpoint_translation_delta = _vector_sub(end["translation"], start["translation"])
    endpoint_angular_delta = _angular_delta_vector_degrees(start["orientation"], end["orientation"])
    endpoint_duplicate = {
        "matrix_max_abs": _max_abs_delta(start["matrix"], end["matrix"]),
        "translation_distance": _vector_norm(endpoint_translation_delta),
        "angular_degrees": _vector_norm(endpoint_angular_delta),
        "scale_max_abs": _max_abs_delta(start["scale"], end["scale"]),
    }
    periodic_translation_delta = _vector_sub(periodic_next["translation"], start["translation"])
    periodic_angular_delta = _angular_delta_vector_degrees(start["orientation"], periodic_next["orientation"])
    periodic = {
        "matrix_max_abs": _max_abs_delta(start["matrix"], periodic_next["matrix"]),
        "translation_distance": _vector_norm(periodic_translation_delta),
        "angular_degrees": _vector_norm(periodic_angular_delta),
        "scale_max_abs": _max_abs_delta(start["scale"], periodic_next["scale"]),
    }
    first_step_translation = _vector_norm(_vector_sub(start_one["translation"], start["translation"]))
    first_step_angular = _vector_norm(_angular_delta_vector_degrees(start["orientation"], start_one["orientation"]))
    endpoint_is_duplicate = (
        endpoint_duplicate["matrix_max_abs"] <= tolerances["matrix_max_abs"]
        and endpoint_duplicate["translation_distance"] <= tolerances["translation"]
        and endpoint_duplicate["angular_degrees"] <= tolerances["angular_degrees"]
        and endpoint_duplicate["scale_max_abs"] <= tolerances["scale"]
    )
    duplicate_endpoint_hold_risk = endpoint_is_duplicate and (
        first_step_translation > tolerances["translation"] or first_step_angular > tolerances["angular_degrees"]
    )

    start_linear_velocity = _vector_scale(
        _vector_sub(start_one["translation"], start["translation"]), 1.0 / seconds_per_step
    )
    end_linear_velocity = _vector_scale(
        _vector_sub(periodic_next["translation"], end["translation"]), 1.0 / seconds_per_step
    )
    linear_velocity_residual = _vector_sub(end_linear_velocity, start_linear_velocity)
    start_angular_velocity = _vector_scale(
        _angular_delta_vector_degrees(start["orientation"], start_one["orientation"]), 1.0 / seconds_per_step
    )
    end_angular_velocity = _vector_scale(
        _angular_delta_vector_degrees(end["orientation"], periodic_next["orientation"]), 1.0 / seconds_per_step
    )
    angular_velocity_residual = _vector_sub(end_angular_velocity, start_angular_velocity)

    next_linear_velocity = _vector_scale(
        _vector_sub(start_two["translation"], start_one["translation"]), 1.0 / seconds_per_step
    )
    previous_linear_velocity = _vector_scale(
        _vector_sub(end["translation"], end_one["translation"]), 1.0 / seconds_per_step
    )
    start_linear_acceleration = _vector_scale(
        _vector_sub(next_linear_velocity, start_linear_velocity), 1.0 / seconds_per_step
    )
    end_linear_acceleration = _vector_scale(
        _vector_sub(end_linear_velocity, previous_linear_velocity), 1.0 / seconds_per_step
    )
    linear_acceleration_residual = _vector_sub(end_linear_acceleration, start_linear_acceleration)

    next_angular_velocity = _vector_scale(
        _angular_delta_vector_degrees(start_one["orientation"], start_two["orientation"]), 1.0 / seconds_per_step
    )
    previous_angular_velocity = _vector_scale(
        _angular_delta_vector_degrees(end_one["orientation"], end["orientation"]), 1.0 / seconds_per_step
    )
    start_angular_acceleration = _vector_scale(
        _vector_sub(next_angular_velocity, start_angular_velocity), 1.0 / seconds_per_step
    )
    end_angular_acceleration = _vector_scale(
        _vector_sub(end_angular_velocity, previous_angular_velocity), 1.0 / seconds_per_step
    )
    angular_acceleration_residual = _vector_sub(end_angular_acceleration, start_angular_acceleration)

    velocity = {
        "linear_vector_per_second": list(linear_velocity_residual),
        "linear_magnitude_per_second": _vector_norm(linear_velocity_residual),
        "angular_vector_degrees_per_second": list(angular_velocity_residual),
        "angular_magnitude_degrees_per_second": _vector_norm(angular_velocity_residual),
    }
    acceleration = {
        "linear_vector_per_second2": list(linear_acceleration_residual),
        "linear_magnitude_per_second2": _vector_norm(linear_acceleration_residual),
        "angular_vector_degrees_per_second2": list(angular_acceleration_residual),
        "angular_magnitude_degrees_per_second2": _vector_norm(angular_acceleration_residual),
    }
    checks.update(
        {
            "periodic_matrix": periodic["matrix_max_abs"] <= tolerances["matrix_max_abs"],
            "periodic_translation": periodic["translation_distance"] <= tolerances["translation"],
            "periodic_angular": periodic["angular_degrees"] <= tolerances["angular_degrees"],
            "periodic_scale": periodic["scale_max_abs"] <= tolerances["scale"],
            "linear_velocity": velocity["linear_magnitude_per_second"] <= tolerances["linear_velocity"],
            "angular_velocity": velocity["angular_magnitude_degrees_per_second"]
            <= tolerances["angular_velocity_degrees"],
            "linear_acceleration": acceleration["linear_magnitude_per_second2"] <= tolerances["linear_acceleration"],
            "angular_acceleration": acceleration["angular_magnitude_degrees_per_second2"]
            <= tolerances["angular_acceleration_degrees"],
        }
    )
    return {
        "node_path": node_path,
        "resolved": True,
        "finite": True,
        "passed": all(checks.values()),
        "duplicate_endpoint_hold_risk": duplicate_endpoint_hold_risk,
        "first_step_motion": {
            "translation_distance": first_step_translation,
            "angular_degrees": first_step_angular,
        },
        "endpoints": {
            "start": _public_endpoint(start),
            "end": _public_endpoint(end),
            "virtual_next": _public_endpoint(periodic_next),
        },
        "endpoint_duplicate_delta": endpoint_duplicate,
        "periodic_delta": periodic,
        "velocity_residuals": velocity,
        "acceleration_residuals": acceleration,
        "drivers": drivers,
        "checks": checks,
        "errors": errors,
    }


def _unresolved_diagnostic(node_path: str, error: str) -> Dict[str, Any]:
    endpoint_duplicate, periodic, velocity, acceleration = _failed_metrics()
    checks = {
        "finite": False,
        "periodic_matrix": False,
        "periodic_translation": False,
        "periodic_angular": False,
        "periodic_scale": False,
        "linear_velocity": False,
        "angular_velocity": False,
        "linear_acceleration": False,
        "angular_acceleration": False,
    }
    return {
        "node_path": node_path,
        "resolved": False,
        "finite": False,
        "passed": False,
        "duplicate_endpoint_hold_risk": False,
        "endpoints": None,
        "endpoint_duplicate_delta": endpoint_duplicate,
        "periodic_delta": periodic,
        "velocity_residuals": velocity,
        "acceleration_residuals": acceleration,
        "drivers": {"counts": {"expression": 0, "keyframes": 0, "static": 0, "time_dependent": 0}, "parameters": []},
        "checks": checks,
        "errors": [error],
    }


def validate_loop_contract(
    node_paths: List[str],
    start_frame: float,
    end_frame: float,
    sample_step: float = 1.0,
    tolerances: Optional[Dict[str, float]] = None,
    max_expression_chars: int = 160,
) -> dict:
    """Validate transform continuity around the seam of a bounded OBJ loop."""
    try:
        paths, start, end, step, merged_tolerances, expression_limit = _validate_request(
            node_paths, start_frame, end_frame, sample_step, tolerances, max_expression_chars
        )
    except ValueError as exc:
        return skill_error("Invalid loop validation request", str(exc))

    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    original_frame = None
    restore_error = None
    execution_error = None
    diagnostics_by_path = {}
    frames = _sample_frames(start, end, step)
    try:
        original_frame = float(hou.frame())
        fps = float(hou.fps())
        if not math.isfinite(fps) or fps <= 0.0:
            raise ValueError("Houdini FPS must be a positive finite number")

        resolved = []
        for node_path in paths:
            node = hou.node(node_path)
            if node is None:
                diagnostics_by_path[node_path] = _unresolved_diagnostic(node_path, "Houdini node not found")
                continue
            try:
                if node.type().category() != hou.objNodeTypeCategory():
                    diagnostics_by_path[node_path] = _unresolved_diagnostic(node_path, "Node is not an OBJ node")
                    continue
            except Exception as exc:  # noqa: BLE001
                diagnostics_by_path[node_path] = _unresolved_diagnostic(
                    node_path, "Could not verify OBJ category: {}".format(exc)
                )
                continue
            resolved.append(
                {
                    "path": node_path,
                    "node": node,
                    "snapshots": {},
                    "errors": [],
                    "drivers": _driver_summary(node, expression_limit),
                }
            )

        for frame in frames:
            hou.setFrame(frame)
            for entry in resolved:
                try:
                    entry["snapshots"][frame] = _snapshot(entry["node"])
                except Exception as exc:  # noqa: BLE001
                    entry["errors"].append("Frame {}: {}".format(frame, exc))

        for entry in resolved:
            diagnostics_by_path[entry["path"]] = _evaluate_node(
                entry["path"],
                entry["snapshots"],
                frames,
                fps,
                step,
                merged_tolerances,
                entry["drivers"],
                entry["errors"],
            )
    except Exception as exc:  # noqa: BLE001
        execution_error = exc
    finally:
        if original_frame is not None:
            try:
                hou.setFrame(original_frame)
            except Exception as exc:  # noqa: BLE001
                restore_error = exc

    if restore_error is not None:
        return skill_error("Failed to restore the original Houdini frame", str(restore_error))
    if execution_error is not None:
        return skill_exception(execution_error, message="Failed to validate animation loop")

    diagnostics = [diagnostics_by_path[node_path] for node_path in paths]
    passed = all(diagnostic["passed"] for diagnostic in diagnostics)
    return skill_success(
        "Animation loop contract passed" if passed else "Animation loop contract failed",
        passed=passed,
        node_count=len(paths),
        sample_frames=frames,
        sample_step=step,
        range_semantics="[start_frame, end_frame] contains unique playback samples; end_frame + sample_step is the virtual periodic sample",
        virtual_periodic_frame=end + step,
        fps=fps,
        original_frame=original_frame,
        restored_frame=True,
        tolerances=merged_tolerances,
        nodes=diagnostics,
    )


@skill_entry
def main(**kwargs: Any) -> dict:
    return validate_loop_contract(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
