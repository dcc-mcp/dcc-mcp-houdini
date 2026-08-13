"""Create an anatomy-aware honeybee KineFX skeleton."""

from __future__ import annotations

import math
from typing import List, Mapping

from create_rig import create_rig  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error

_LEG_SEGMENTS = ("coxa", "trochanter", "femur", "tibia", "tarsus", "claw")
_BASE_MEASUREMENTS = {
    "body_length": 4.30,
    "body_width": 0.84,
    "standing_height": 1.90,
    "wing_span": 4.30,
    "leg_span": 3.44,
}
_BASE_HALF_WIDTH = _BASE_MEASUREMENTS["body_width"] / 2.0
_BASE_FOREWING_HALF_SPAN = _BASE_MEASUREMENTS["wing_span"] / 2.0
_BASE_REAR_LEG_HALF_SPAN = _BASE_MEASUREMENTS["leg_span"] / 2.0


def _append(chain: List[dict], name: str, parent: int, position: tuple[float, float, float]) -> int:
    chain.append({"name": name, "parent_index": parent, "translate": list(position)})
    return len(chain) - 1


def _honeybee_chain(
    scale: float,
    ground_z: float,
    anatomy_measurements: Mapping[str, float] | None = None,
) -> tuple[List[dict], List[str], dict[str, float]]:
    """Return a worker-honeybee skeleton in world-space centimetre-like units."""
    s = 1.0
    base_ground = 0.0
    chain: List[dict] = []
    root = _append(chain, "body_root", -1, (0.0, 0.0, base_ground + 1.55 * s))
    thorax = _append(chain, "thorax", root, (0.0, 0.0, base_ground + 1.55 * s))
    neck = _append(chain, "neck", thorax, (0.82 * s, 0.0, base_ground + 1.57 * s))
    head = _append(chain, "head", neck, (1.25 * s, 0.0, base_ground + 1.55 * s))
    _append(chain, "compound_eye_L", head, (1.38 * s, 0.38 * s, base_ground + 1.67 * s))
    _append(chain, "compound_eye_R", head, (1.38 * s, -0.38 * s, base_ground + 1.67 * s))

    for side, sign in (("L", 1.0), ("R", -1.0)):
        antenna_base = _append(chain, f"antenna_{side}_scape", head, (1.58 * s, sign * 0.20 * s, base_ground + 1.82 * s))
        antenna_pedicel = _append(
            chain,
            f"antenna_{side}_pedicel",
            antenna_base,
            (1.83 * s, sign * 0.32 * s, base_ground + 1.92 * s),
        )
        _append(
            chain,
            f"antenna_{side}_flagellum",
            antenna_pedicel,
            (2.16 * s, sign * 0.47 * s, base_ground + 1.82 * s),
        )

    abdomen_parent = thorax
    for index, (x, z) in enumerate(
        ((-0.65, 1.55), (-1.20, 1.50), (-1.75, 1.43), (-2.28, 1.34), (-2.72, 1.22)), start=1
    ):
        abdomen_parent = _append(chain, f"abdomen_{index:02d}", abdomen_parent, (x * s, 0.0, base_ground + z * s))

    for side, sign in (("L", 1.0), ("R", -1.0)):
        fore = _append(chain, f"forewing_{side}_root", thorax, (-0.18 * s, sign * 0.42 * s, base_ground + 1.90 * s))
        _append(chain, f"forewing_{side}_tip", fore, (-1.55 * s, sign * 2.15 * s, base_ground + 2.18 * s))
        hind = _append(chain, f"hindwing_{side}_root", thorax, (-0.52 * s, sign * 0.38 * s, base_ground + 1.84 * s))
        _append(chain, f"hindwing_{side}_tip", hind, (-1.60 * s, sign * 1.42 * s, base_ground + 1.88 * s))

    contacts: List[str] = []
    leg_specs = {
        "front": (
            (0.52, 0.38, 1.42),
            (0.86, 0.70, 1.10),
            (1.15, 0.86, 0.64),
            (1.32, 0.94, 0.25),
            (1.50, 0.98, 0.08),
            (1.58, 1.00, 0.0),
        ),
        "middle": (
            (0.00, 0.44, 1.38),
            (0.08, 0.84, 1.02),
            (0.05, 1.12, 0.55),
            (-0.08, 1.30, 0.20),
            (0.06, 1.48, 0.07),
            (0.14, 1.55, 0.0),
        ),
        "rear": (
            (-0.48, 0.40, 1.40),
            (-0.72, 0.78, 1.15),
            (-1.02, 1.10, 0.72),
            (-1.20, 1.36, 0.28),
            (-1.08, 1.60, 0.08),
            (-1.00, 1.72, 0.0),
        ),
    }
    for leg_name, positions in leg_specs.items():
        for side, sign in (("L", 1.0), ("R", -1.0)):
            parent = thorax
            for segment, (x, y, z) in zip(_LEG_SEGMENTS, positions):
                joint_name = f"{leg_name}_{side}_{segment}"
                parent = _append(chain, joint_name, parent, (x * s, sign * y * s, base_ground + z * s))
            contacts.append(f"{leg_name}_{side}_claw")

    requested = dict(anatomy_measurements or {})
    effective = {name: float(requested.get(name, value * scale)) for name, value in _BASE_MEASUREMENTS.items()}
    x_factor = effective["body_length"] / _BASE_MEASUREMENTS["body_length"]
    body_y_factor = effective["body_width"] / _BASE_MEASUREMENTS["body_width"]
    z_factor = effective["standing_height"] / _BASE_MEASUREMENTS["standing_height"]
    target_half_width = effective["body_width"] / 2.0
    wing_extension_factor = (effective["wing_span"] / 2.0 - target_half_width) / (
        _BASE_FOREWING_HALF_SPAN - _BASE_HALF_WIDTH
    )
    leg_extension_factor = (effective["leg_span"] / 2.0 - target_half_width) / (
        _BASE_REAR_LEG_HALF_SPAN - _BASE_HALF_WIDTH
    )
    for joint in chain:
        name = joint["name"]
        x, y, z = joint["translate"]
        sign = -1.0 if y < 0.0 else 1.0
        if "wing_" in name:
            transformed_y = sign * (
                target_half_width + (abs(y) - _BASE_HALF_WIDTH) * wing_extension_factor
            )
        elif any(name.startswith(f"{leg}_") for leg in leg_specs):
            transformed_y = sign * (
                target_half_width + (abs(y) - _BASE_HALF_WIDTH) * leg_extension_factor
            )
        else:
            transformed_y = y * body_y_factor
        joint["translate"] = [x * x_factor, transformed_y, ground_z + z * z_factor]
    return chain, contacts, effective


def _measurement_error(anatomy_measurements: Mapping[str, float] | None) -> dict | None:
    if anatomy_measurements is None:
        return None
    if not isinstance(anatomy_measurements, Mapping):
        return skill_error("Invalid anatomy measurements", "anatomy_measurements must be an object")
    unknown = sorted(set(anatomy_measurements) - set(_BASE_MEASUREMENTS))
    if unknown:
        return skill_error(
            "Invalid anatomy measurements",
            "anatomy_measurements contains unsupported dimensions",
            unsupported_dimensions=unknown,
            allowed_dimensions=sorted(_BASE_MEASUREMENTS),
        )
    invalid = {
        name: value
        for name, value in anatomy_measurements.items()
        if isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or not 0.001 <= float(value) <= 100000.0
    }
    if invalid:
        return skill_error(
            "Invalid anatomy measurements",
            "each anatomy measurement must be a finite number between 0.001 and 100000",
            invalid_dimensions=invalid,
        )
    return None


def create_insect_rig(
    geo_path: str,
    rig_name: str = "honeybee_anatomy_rig",
    scale: float = 1.0,
    ground_z: float = 0.0,
    anatomy_measurements: Mapping[str, float] | None = None,
    auto_capture: bool = False,
    capture_mesh: str | None = None,
) -> dict:
    """Create a complete worker-honeybee skeleton with grounded claw joints."""
    if not 0.001 <= scale <= 1000.0:
        return skill_error(
            "Invalid insect scale", "scale must be between 0.001 and 1000", scale=scale, allowed_range=[0.001, 1000.0]
        )
    measurement_error = _measurement_error(anatomy_measurements)
    if measurement_error:
        return measurement_error
    effective_measurements = {
        name: float((anatomy_measurements or {}).get(name, value * scale))
        for name, value in _BASE_MEASUREMENTS.items()
    }
    invalid_spans = [
        name
        for name in ("wing_span", "leg_span")
        if effective_measurements[name] < effective_measurements["body_width"]
    ]
    if invalid_spans:
        return skill_error(
            "Invalid anatomy proportions",
            "wing_span and leg_span must not be smaller than body_width",
            invalid_dimensions=invalid_spans,
            effective_anatomy_measurements=effective_measurements,
        )
    chain, contacts, effective_measurements = _honeybee_chain(scale, ground_z, effective_measurements)
    names = [joint["name"] for joint in chain]
    if len(names) != len(set(names)) or len(contacts) != 6:
        return skill_error(
            "Invalid honeybee topology",
            "generated joint names must be unique and expose six claw contacts",
            joint_count=len(names),
            contact_count=len(contacts),
        )
    result = create_rig(
        geo_path=geo_path,
        rig_name=rig_name,
        joint_chain=chain,
        auto_capture=auto_capture,
        capture_mesh=capture_mesh,
    )
    if result.get("success"):
        result["context"].update(
            anatomy_preset="worker_honeybee",
            support_joint_names=contacts,
            leg_count=6,
            wing_count=4,
            abdomen_segment_count=5,
            compound_eye_count=2,
            antenna_count=2,
            ground_z=ground_z,
            scale=scale,
            effective_anatomy_measurements=effective_measurements,
        )
    return result


@skill_entry
def main(**kwargs) -> dict:
    return create_insect_rig(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
