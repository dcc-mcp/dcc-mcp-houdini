"""Create an anatomy-aware honeybee KineFX skeleton."""

from __future__ import annotations

from typing import List

from create_rig import create_rig  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error

_LEG_SEGMENTS = ("coxa", "trochanter", "femur", "tibia", "tarsus", "claw")


def _append(chain: List[dict], name: str, parent: int, position: tuple[float, float, float]) -> int:
    chain.append({"name": name, "parent_index": parent, "translate": list(position)})
    return len(chain) - 1


def _honeybee_chain(scale: float, ground_z: float) -> tuple[List[dict], List[str]]:
    """Return a worker-honeybee skeleton in world-space centimetre-like units."""
    s = scale
    chain: List[dict] = []
    root = _append(chain, "body_root", -1, (0.0, 0.0, ground_z + 1.55 * s))
    thorax = _append(chain, "thorax", root, (0.0, 0.0, ground_z + 1.55 * s))
    neck = _append(chain, "neck", thorax, (0.82 * s, 0.0, ground_z + 1.57 * s))
    head = _append(chain, "head", neck, (1.25 * s, 0.0, ground_z + 1.55 * s))
    _append(chain, "compound_eye_L", head, (1.38 * s, 0.38 * s, ground_z + 1.67 * s))
    _append(chain, "compound_eye_R", head, (1.38 * s, -0.38 * s, ground_z + 1.67 * s))

    for side, sign in (("L", 1.0), ("R", -1.0)):
        antenna_base = _append(
            chain, f"antenna_{side}_scape", head, (1.58 * s, sign * 0.20 * s, ground_z + 1.82 * s)
        )
        antenna_pedicel = _append(
            chain,
            f"antenna_{side}_pedicel",
            antenna_base,
            (1.83 * s, sign * 0.32 * s, ground_z + 1.92 * s),
        )
        _append(
            chain,
            f"antenna_{side}_flagellum",
            antenna_pedicel,
            (2.16 * s, sign * 0.47 * s, ground_z + 1.82 * s),
        )

    abdomen_parent = thorax
    for index, (x, z) in enumerate(
        ((-0.65, 1.55), (-1.20, 1.50), (-1.75, 1.43), (-2.28, 1.34), (-2.72, 1.22)), start=1
    ):
        abdomen_parent = _append(chain, f"abdomen_{index:02d}", abdomen_parent, (x * s, 0.0, ground_z + z * s))

    for side, sign in (("L", 1.0), ("R", -1.0)):
        fore = _append(chain, f"forewing_{side}_root", thorax, (-0.18 * s, sign * 0.42 * s, ground_z + 1.90 * s))
        _append(chain, f"forewing_{side}_tip", fore, (-1.55 * s, sign * 2.15 * s, ground_z + 2.18 * s))
        hind = _append(chain, f"hindwing_{side}_root", thorax, (-0.52 * s, sign * 0.38 * s, ground_z + 1.84 * s))
        _append(chain, f"hindwing_{side}_tip", hind, (-1.60 * s, sign * 1.42 * s, ground_z + 1.88 * s))

    contacts: List[str] = []
    leg_specs = {
        "front": ((0.52, 0.38, 1.42), (0.86, 0.70, 1.10), (1.15, 0.86, 0.64), (1.32, 0.94, 0.25), (1.50, 0.98, 0.08), (1.58, 1.00, 0.0)),
        "middle": ((0.00, 0.44, 1.38), (0.08, 0.84, 1.02), (0.05, 1.12, 0.55), (-0.08, 1.30, 0.20), (0.06, 1.48, 0.07), (0.14, 1.55, 0.0)),
        "rear": ((-0.48, 0.40, 1.40), (-0.72, 0.78, 1.15), (-1.02, 1.10, 0.72), (-1.20, 1.36, 0.28), (-1.08, 1.60, 0.08), (-1.00, 1.72, 0.0)),
    }
    for leg_name, positions in leg_specs.items():
        for side, sign in (("L", 1.0), ("R", -1.0)):
            parent = thorax
            for segment, (x, y, z) in zip(_LEG_SEGMENTS, positions):
                joint_name = f"{leg_name}_{side}_{segment}"
                parent = _append(chain, joint_name, parent, (x * s, sign * y * s, ground_z + z * s))
            contacts.append(f"{leg_name}_{side}_claw")
    return chain, contacts


def create_insect_rig(
    geo_path: str,
    rig_name: str = "honeybee_anatomy_rig",
    scale: float = 1.0,
    ground_z: float = 0.0,
    auto_capture: bool = False,
    capture_mesh: str | None = None,
) -> dict:
    """Create a complete worker-honeybee skeleton with grounded claw joints."""
    if not 0.001 <= scale <= 1000.0:
        return skill_error(
            "Invalid insect scale", "scale must be between 0.001 and 1000", scale=scale, allowed_range=[0.001, 1000.0]
        )
    chain, contacts = _honeybee_chain(scale, ground_z)
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
        )
    return result


@skill_entry
def main(**kwargs) -> dict:
    return create_insect_rig(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
