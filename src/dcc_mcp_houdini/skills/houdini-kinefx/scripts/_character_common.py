"""Pure helpers for the Houdini character-animation workflow.

This module deliberately contains **no** ``hou`` import.  Everything here is
deterministic data or math so the workflow plan, character design contract,
biped naming maps and rig-inversion linear algebra can be unit-tested without
a licensed Houdini.  Scene tools import these helpers and keep ``hou`` access
inside their tool functions (see the skill authoring checklist).
"""

from __future__ import annotations

# Canonical humanoid biped skeleton (Y-up, ~1.7 units tall, T-pose).
# Each entry: (canonical key, parent key or None, rest translation).
BIPED_SPEC = (
    ("hips", None, (0.0, 0.95, 0.0)),
    ("spine", "hips", (0.0, 1.10, 0.0)),
    ("spine1", "spine", (0.0, 1.28, 0.0)),
    ("spine2", "spine1", (0.0, 1.45, 0.0)),
    ("neck", "spine2", (0.0, 1.58, 0.0)),
    ("head", "neck", (0.0, 1.70, 0.0)),
    ("clavicle_l", "spine2", (0.06, 1.52, 0.0)),
    ("upperarm_l", "clavicle_l", (0.18, 1.52, 0.0)),
    ("lowerarm_l", "upperarm_l", (0.42, 1.52, 0.0)),
    ("hand_l", "lowerarm_l", (0.66, 1.52, 0.0)),
    ("clavicle_r", "spine2", (-0.06, 1.52, 0.0)),
    ("upperarm_r", "clavicle_r", (-0.18, 1.52, 0.0)),
    ("lowerarm_r", "upperarm_r", (-0.42, 1.52, 0.0)),
    ("hand_r", "lowerarm_r", (-0.66, 1.52, 0.0)),
    ("thigh_l", "hips", (0.10, 0.92, 0.0)),
    ("calf_l", "thigh_l", (0.10, 0.52, 0.0)),
    ("foot_l", "calf_l", (0.10, 0.10, 0.0)),
    ("toe_l", "foot_l", (0.10, 0.05, 0.16)),
    ("thigh_r", "hips", (-0.10, 0.92, 0.0)),
    ("calf_r", "thigh_r", (-0.10, 0.52, 0.0)),
    ("foot_r", "calf_r", (-0.10, 0.10, 0.0)),
    ("toe_r", "foot_r", (-0.10, 0.05, 0.16)),
)

CENTER_KEYS = ("hips", "spine", "spine1", "spine2", "neck", "head")
LEFT_KEYS = (
    "clavicle_l",
    "upperarm_l",
    "lowerarm_l",
    "hand_l",
    "thigh_l",
    "calf_l",
    "foot_l",
    "toe_l",
)
RIGHT_KEYS = tuple(key.replace("_l", "_r") for key in LEFT_KEYS)

SUPPORT_KEYS = ("toe_l", "foot_l", "toe_r", "foot_r")

# Supported naming conventions. Each maps a canonical key to a joint name.
CONVENTIONS = ("kinefx", "biped", "mixamo", "unreal", "fbx")


def _kinefx_names() -> dict:
    center = {
        "hips": "Hips",
        "spine": "Spine",
        "spine1": "Spine1",
        "spine2": "Spine2",
        "neck": "Neck",
        "head": "Head",
    }
    left = {
        "clavicle_l": "LeftShoulder",
        "upperarm_l": "LeftArm",
        "lowerarm_l": "LeftForeArm",
        "hand_l": "LeftHand",
        "thigh_l": "LeftUpLeg",
        "calf_l": "LeftLeg",
        "foot_l": "LeftFoot",
        "toe_l": "LeftToeBase",
    }
    names = dict(center)
    for key, name in left.items():
        names[key] = name
        names[key.replace("_l", "_r")] = name.replace("Left", "Right")
    return names


def _biped_names() -> dict:
    center = {
        "hips": "Bip01",
        "spine": "Bip01 Spine",
        "spine1": "Bip01 Spine1",
        "spine2": "Bip01 Spine2",
        "neck": "Bip01 Neck",
        "head": "Bip01 Head",
    }
    left = {
        "clavicle_l": "Bip01 L Clavicle",
        "upperarm_l": "Bip01 L UpperArm",
        "lowerarm_l": "Bip01 L Forearm",
        "hand_l": "Bip01 L Hand",
        "thigh_l": "Bip01 L Thigh",
        "calf_l": "Bip01 L Calf",
        "foot_l": "Bip01 L Foot",
        "toe_l": "Bip01 L Toe0",
    }
    names = dict(center)
    for key, name in left.items():
        names[key] = name
        names[key.replace("_l", "_r")] = name.replace(" L ", " R ")
    return names


def _unreal_names() -> dict:
    center = {
        "hips": "pelvis",
        "spine": "spine_01",
        "spine1": "spine_02",
        "spine2": "spine_03",
        "neck": "neck_01",
        "head": "head",
    }
    left = {
        "clavicle_l": "clavicle_l",
        "upperarm_l": "upperarm_l",
        "lowerarm_l": "lowerarm_l",
        "hand_l": "hand_l",
        "thigh_l": "thigh_l",
        "calf_l": "calf_l",
        "foot_l": "foot_l",
        "toe_l": "ball_l",
    }
    names = dict(center)
    for key, name in left.items():
        names[key] = name
        names[key.replace("_l", "_r")] = name.replace("_l", "_r")
    return names


def convention_names(convention: str) -> dict:
    """Return the ``{canonical_key: joint_name}`` map for *convention*.

    ``kinefx``/``fbx`` use a generic Mixamo-like biped; ``biped`` uses 3ds Max
    Biped names; ``mixamo`` prefixes with ``mixamorig:``; ``unreal`` uses the
    UE Mannequin skeleton. Unknown conventions raise ``ValueError``.
    """
    if convention not in CONVENTIONS:
        raise ValueError("Unknown convention {!r}; expected one of {}".format(convention, ", ".join(CONVENTIONS)))
    if convention == "biped":
        return _biped_names()
    if convention == "unreal":
        return _unreal_names()
    base = _kinefx_names()
    if convention == "mixamo":
        return {key: "mixamorig:" + name for key, name in base.items()}
    return base  # kinefx / fbx


def biped_joint_map(source_convention: str, target_convention: str) -> dict:
    """Return an explicit retarget map between two biped naming conventions.

    The result has ``source_name -> target_name`` pairs (plus metadata) suitable
    for authoring a ``retarget_joint`` point attribute used by KineFX Map Points
    / Full Body IK when source and target skeletons use different joint names.
    """
    source = convention_names(source_convention)
    target = convention_names(target_convention)
    pairs = {source[key]: target[key] for key, _, _ in BIPED_SPEC}
    return {
        "source_convention": source_convention,
        "target_convention": target_convention,
        "joint_count": len(pairs),
        "pairs": pairs,
        "reverse_pairs": {value: key for key, value in pairs.items()},
    }


def biped_chain(height: float, convention: str, ground_z: float = 0.0) -> dict:
    """Build the KineFX joint-chain definition for a scaled biped template.

    Positions are scaled uniformly from the ~1.7-unit canonical rest pose and
    shifted so the feet rest on ``ground_z``. Returns a dict with the
    ``joint_chain`` (consumable by ``get_or_create_rig``), the ``name`` list,
    ``support_joint_names`` and the effective ``height``.
    """
    if height <= 0:
        raise ValueError("height must be positive")
    names = convention_names(convention)
    scale = height / 1.7
    min_y = min(pos[1] for _, _, pos in BIPED_SPEC)
    key_to_index = {key: idx for idx, (key, _, _) in enumerate(BIPED_SPEC)}
    chain = []
    for key, parent_key, pos in BIPED_SPEC:
        parent_index = -1 if parent_key is None else key_to_index[parent_key]
        chain.append(
            {
                "name": names[key],
                "parent_index": parent_index,
                "translate": [
                    round(pos[0] * scale, 5),
                    round((pos[1] - min_y) * scale + ground_z, 5),
                    round(pos[2] * scale, 5),
                ],
            }
        )
    support = [names[key] for key in SUPPORT_KEYS]
    return {
        "joint_chain": chain,
        "joint_names": [names[key] for key, _, _ in BIPED_SPEC],
        "support_joint_names": support,
        "height": height,
        "ground_z": ground_z,
        "convention": convention,
        "canonical_keys": [key for key, _, _ in BIPED_SPEC],
        "parent_indices": [joint["parent_index"] for joint in chain],
    }


# ---------------------------------------------------------------------------
# Rig-inversion linear algebra (pure).
#
# Matrices are 16-value 4x4 tuples in Houdini's row-major, row-vector
# convention: vectors are rows (``v' = v * M``), the 3x3 rotation/scale block
# is the upper-left (indices 0,1,2,4,5,6,8,9,10) and the translation lives in
# the bottom row (indices 12,13,14). Forward kinematics composes as
# ``world[i] = local[i] * world[parent]``, so rig inversion is
# ``local[i] = world[i] * inverse(world[parent])``. Keeping one explicit
# convention here (and in the scene/headless tools) avoids mirrored rotations.
# ---------------------------------------------------------------------------


def _mat4_mul(a, b):
    out = []
    for i in range(4):
        for j in range(4):
            out.append(sum(a[i * 4 + k] * b[k * 4 + j] for k in range(4)))
    return tuple(out)


def _mat4_inverse(m):
    aug = [list(m[i * 4 : (i + 1) * 4]) + [1.0 if i == j else 0.0 for j in range(4)] for i in range(4)]
    for col in range(4):
        pivot = max(range(col, 4), key=lambda r: abs(aug[r][col]))
        if abs(aug[pivot][col]) < 1e-12:
            raise ValueError("Singular world transform; cannot invert rig")
        aug[col], aug[pivot] = aug[pivot], aug[col]
        factor = aug[col][col]
        aug[col] = [value / factor for value in aug[col]]
        for row in range(4):
            if row != col and aug[row][col] != 0.0:
                f = aug[row][col]
                aug[row] = [aug[row][k] - f * aug[col][k] for k in range(8)]
    inverse = []
    for row in aug:
        inverse.extend(row[4:8])
    return tuple(inverse)


def compute_local_transforms(world_matrices, parent_indices):
    """Return parent-relative (local) transforms from world transforms.

    Matrices follow Houdini's row-vector convention (see the module header):
    ``world[i] = local[i] * world[parent]``. Rig inversion is therefore
    ``local[i] = world[i] * inverse(world[parent])`` (world for roots). Using
    the inverse on the *right* keeps the rotation direction correct; applying
    it on the left mirrors rotations. Raises ``ValueError`` on bad input or a
    singular parent transform.
    """
    if len(world_matrices) != len(parent_indices):
        raise ValueError("world_matrices and parent_indices length mismatch")
    locals_out = []
    for index, world in enumerate(world_matrices):
        world = tuple(float(value) for value in world)
        if len(world) != 16:
            raise ValueError("Each world transform must contain 16 values")
        parent = parent_indices[index]
        if parent is None or parent < 0:
            locals_out.append(world)
            continue
        if parent >= len(world_matrices) or parent == index:
            raise ValueError("parent_index must reference another valid joint")
        parent_world = tuple(float(v) for v in world_matrices[parent])
        parent_inverse = _mat4_inverse(parent_world)
        locals_out.append(_mat4_mul(world, parent_inverse))
    return [tuple(round(value, 6) for value in matrix) for matrix in locals_out]
