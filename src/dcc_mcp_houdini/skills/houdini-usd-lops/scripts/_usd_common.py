"""Shared, dependency-free helpers for USD inspection and stage authoring."""

from __future__ import annotations

import math
from contextlib import contextmanager
from typing import Any, Iterator, Tuple

from dcc_mcp_houdini._bounded_values import bounded_value as bounded_value
from dcc_mcp_houdini._bounded_values import require_range as require_range


def require_absolute_path(value: str, label: str) -> str:
    """Validate and return an absolute Houdini or USD path."""
    path = str(value or "").strip()
    if not path.startswith("/"):
        raise ValueError("{} must be an absolute path".format(label))
    return path


def resolve_stage(hou: Any, lop_node_path: str) -> Tuple[Any, Any]:
    """Resolve a Houdini LOP node and its composed USD Stage."""
    node_path = require_absolute_path(lop_node_path, "lop_node_path")
    node = hou.node(node_path)
    if node is None:
        raise ValueError("Houdini node not found: {}".format(node_path))
    stage_method = getattr(node, "stage", None)
    if not callable(stage_method):
        raise ValueError("Houdini node is not a LOP node: {}".format(node_path))
    stage = stage_method()
    if stage is None:
        raise RuntimeError("LOP node returned no composed USD Stage: {}".format(node_path))
    return node, stage


def resolve_prim(stage: Any, prim_path: str) -> Any:
    """Resolve a valid prim from *stage*."""
    path = require_absolute_path(prim_path, "prim_path")
    prim = stage.GetPrimAtPath(path)
    if not prim:
        raise ValueError("USD prim not found: {}".format(path))
    return prim


def make_time_code(Usd: Any, value: Any) -> Any:
    """Create default or numeric ``Usd.TimeCode`` with finite-number validation."""
    if value is None:
        return Usd.TimeCode.Default()
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("time_code must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("time_code must be a finite number")
    return Usd.TimeCode(number)


def _edit_target_layer(target: Any) -> Any:
    """Return the layer *target* points at, or ``None`` when it has none."""
    if target is None:
        return None
    try:
        if not target.IsValid():
            return None
        return target.GetLayer()
    except Exception:  # noqa: BLE001 - a target we cannot inspect is not usable
        return None


def _layer_is_editable(layer: Any) -> bool:
    """Return True when *layer* allows authoring.

    OpenUSD wraps ``SdfLayer.PermissionToEdit()`` as the ``permissionToEdit``
    Python property (see ``sdf/wrapLayer.cpp``: ``add_property("permissionToEdit",
    ...)``), so a read-only LOP layer is detected through that attribute rather
    than a callable. A callable variant is tolerated for host builds that expose
    it as a method instead.
    """
    permission = getattr(layer, "permissionToEdit", None)
    if permission is None:
        permission = getattr(layer, "PermissionToEdit", None)
    if callable(permission):
        permission = permission()
    return bool(permission)


def _edit_target_is_writable(target: Any) -> bool:
    """Return True only when *target* maps to a layer we are allowed to author."""
    layer = _edit_target_layer(target)
    if layer is None:
        return False
    try:
        return _layer_is_editable(layer)
    except Exception:  # noqa: BLE001 - treat an uninspectable layer as read-only
        return False


@contextmanager
def writable_edit_target(stage: Any, Usd: Any) -> Iterator[None]:
    """Author into *stage* against a layer that can actually be edited.

    A LOP's composed stage (``node.stage()``) frequently carries a read-only edit
    target — for sublayer/reference content it is the anonymous
    ``@anon:...:LOP@`` layer — so ``prim.CreateAttribute`` raises
    ``Tf.ErrorException: Layer ... is not editable``. When the current target is
    already editable we leave it in place, so authoring on an editable LOP keeps
    writing to the node's own layer. Only when it is read-only do we retarget to
    the session layer, which is always editable and composes above every file
    layer. The previous target is restored on exit so a write leaves no lasting
    edit-target side effect on the shared stage object.
    """
    try:
        current = stage.GetEditTarget()
    except Exception:  # noqa: BLE001 - a stage we cannot query falls back to session below
        current = None

    if _edit_target_is_writable(current):
        yield
        return

    session_layer = stage.GetSessionLayer()
    if session_layer is None:
        raise RuntimeError("USD stage has no session layer to author into")

    restore = current if _edit_target_layer(current) is not None else None
    stage.SetEditTarget(Usd.EditTarget(session_layer))
    try:
        yield
    finally:
        if restore is not None:
            stage.SetEditTarget(restore)
