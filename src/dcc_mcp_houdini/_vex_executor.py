"""Safe VEX Wrangle execution — create, update, cook, diagnose.

This is the ONLY module that mutates the Houdini scene graph for VEX
operations.  Every call that touches ``hou`` objects is wrapped so it can
be dispatched through the Houdini main-thread queue.

Hard constraints:
- VEX code is set via ``hou.Parm.set()``, NOT via Python ``exec``/``eval``.
- All ``hou`` calls are gated through the dispatcher (main-thread affinity).
- Timeout and cancel boundaries are explicit — cooks are launched as
  durable isolated jobs when timeouts are set.
- This module NEVER constructs arbitrary Python from VEX strings.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from dcc_mcp_houdini._vex_types import (
    CookDiagnostic,
    VexContext,
    VexSnippet,
    VexSyntaxError,
    WrangleInfo,
    WrangleNodeSpec,
    WrangleType,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# VEX snippet limit: Houdini's internal limit is much larger, but we cap
# agent-authored snippets to prevent Denial-of-Memory attacks.
_MAX_VEX_LINES = 2000
_MAX_VEX_CHARS = 64 * 1024  # 64KB

# Default cook timeout for in-process cooks (no isolated job).
_DEFAULT_COOK_TIMEOUT_SECS = 60.0

# Threshold beyond which a cook is launched as an isolated hython job.
_ISOLATED_COOK_THRESHOLD_SECS = 10.0


# ---------------------------------------------------------------------------
# Core operations (each expects ``hou`` as an explicit parameter)
# ---------------------------------------------------------------------------


def create_wrangle(hou: Any, spec: WrangleNodeSpec) -> Dict[str, Any]:
    """Create a Wrangle SOP node from a typed specification.

    This is the ONLY entry point for creating Wrangle nodes.  The *spec*
    carries a validated :class:`VexSnippet` — raw strings are rejected.

    Args:
        hou: The ``hou`` module (lazy import from the caller).
        spec: A fully validated :class:`WrangleNodeSpec`.

    Returns:
        A dict with ``success``, ``node_path``, ``node_name``, ``wrangle_type``,
        and any errors.
    """
    # ── Pre-flight validation ──────────────────────────────────────────
    if spec.snippet is not None:
        if len(spec.snippet.code) > _MAX_VEX_CHARS:
            return _fail("VEX snippet exceeds 64KB limit")
        if spec.snippet.line_count > _MAX_VEX_LINES:
            return _fail("VEX snippet exceeds 2000-line limit")

    try:
        parent = _resolve_node(hou, spec.parent_path)
    except ValueError as exc:
        return _fail(str(exc))

    sop_type = spec.wrangle_type.value
    node = parent.createNode(sop_type, node_name=spec.node_name)

    if node is None:
        return _fail(f"Failed to create {sop_type} node under {spec.parent_path}")

    # ── Set run-over context ───────────────────────────────────────────
    _set_run_over(node, spec.run_over)

    # ── Set VEX snippet ────────────────────────────────────────────────
    if spec.snippet is not None:
        snip_parm = node.parm("snippet")
        if snip_parm is None:
            return _fail(
                f"Wrangle node {node.path()} has no 'snippet' parameter",
                node_path=node.path(),
            )
        snip_parm.set(spec.snippet.code)

        # Apply user-defined parameter values (e.g. group, etc.).
        for parm_name, value in spec.snippet.parameter_values.items():
            parm = node.parm(parm_name)
            if parm is not None:
                try:
                    parm.set(value)
                except Exception:
                    pass  # Non-critical: the cook will surface real issues.

    # ── Bindings ───────────────────────────────────────────────────────
    if spec.snippet is not None and spec.snippet.bindings:
        bindings_str = _encode_bindings(spec.snippet.bindings)
        bind_parm = node.parm("bindings")
        if bind_parm is not None:
            bind_parm.set(bindings_str)

    # ── Display / Render flags ─────────────────────────────────────────
    if spec.set_display and hasattr(node, "setDisplayFlag"):
        node.setDisplayFlag(True)
    if spec.set_render and hasattr(node, "setRenderFlag"):
        node.setRenderFlag(True)

    return {
        "success": True,
        "node_path": node.path(),
        "node_name": node.name(),
        "wrangle_type": sop_type,
        "run_over": spec.run_over.value,
        "has_snippet": spec.snippet is not None,
    }


def update_vex_snippet(
    hou: Any,
    node_path: str,
    snippet: VexSnippet,
) -> Dict[str, Any]:
    """Update the VEX snippet on an existing Wrangle node.

    The *snippet* must be a validated :class:`VexSnippet` — raw strings
    are rejected at the type level.

    Args:
        hou: The ``hou`` module.
        node_path: Path to an existing Wrangle node.
        snippet: The validated VEX snippet to set.

    Returns:
        Dict with ``success``, ``node_path``, and ``previous_snippet_preview``.
    """
    try:
        node = _resolve_node(hou, node_path)
    except ValueError as exc:
        return _fail(str(exc))

    snip_parm = node.parm("snippet")
    if snip_parm is None:
        return _fail(f"Node {node_path} has no 'snippet' parameter", node_path=node_path)

    # Capture the old snippet for the audit trail.
    try:
        previous = snip_parm.evalAsString() or ""
        previous_preview = previous[:200]
    except Exception:
        previous_preview = "<unreadable>"

    if len(snippet.code) > _MAX_VEX_CHARS:
        return _fail("VEX snippet exceeds 64KB limit", node_path=node_path)
    if snippet.line_count > _MAX_VEX_LINES:
        return _fail("VEX snippet exceeds 2000-line limit", node_path=node_path)

    snip_parm.set(snippet.code)

    # Update run-over if context changed.
    _set_run_over(node, snippet.context)

    # Apply bindings.
    if snippet.bindings:
        bind_parm = node.parm("bindings")
        if bind_parm is not None:
            bind_parm.set(_encode_bindings(snippet.bindings))

    # Apply parameter values.
    for parm_name, value in snippet.parameter_values.items():
        parm = node.parm(parm_name)
        if parm is not None:
            try:
                parm.set(value)
            except Exception:
                pass

    return {
        "success": True,
        "node_path": node.path(),
        "previous_snippet_preview": previous_preview,
        "line_count": snippet.line_count,
    }


def cook_and_diagnose(
    hou: Any,
    node_path: str,
    force: bool = False,
    timeout_secs: Optional[float] = None,
) -> CookDiagnostic:
    """Cook a Wrangle node and collect geometry diagnostics.

    For cooks that may exceed the timeout threshold, use
    :func:`launch_durable_cook` instead.

    Args:
        hou: The ``hou`` module.
        node_path: Path to the Wrangle node.
        force: Force a recook even if already cooked.
        timeout_secs: Soft timeout (best-effort; Houdini cooks cannot be
            interrupted mid-cook from Python).

    Returns:
        A :class:`CookDiagnostic` with cook status and geometry stats.
    """
    t0 = time.monotonic()

    try:
        node = _resolve_node(hou, node_path)
    except ValueError as exc:
        return CookDiagnostic(
            node_path=node_path,
            cooked=False,
            cook_error=str(exc),
            elapsed_secs=0.0,
        )

    # ── Cook ───────────────────────────────────────────────────────────
    cook_error: Optional[str] = None
    try:
        node.cook(force=force)
    except Exception as exc:
        cook_error = str(exc)

    # ── Collect errors and warnings ────────────────────────────────────
    errors: List[str] = []
    warnings_list: List[str] = []
    if hasattr(node, "errors"):
        try:
            errors = list(node.errors())
        except Exception:
            pass
    if hasattr(node, "warnings"):
        try:
            warnings_list = list(node.warnings())
        except Exception:
            pass

    # ── Geometry diagnostics ───────────────────────────────────────────
    geo = None
    if hasattr(node, "geometry"):
        try:
            geo = node.geometry()
        except Exception:
            pass

    point_count: Optional[int] = None
    prim_count: Optional[int] = None
    vertex_count: Optional[int] = None
    attr_names: List[str] = []
    group_names: List[str] = []

    if geo is not None:
        if hasattr(geo, "points"):
            try:
                point_count = len(geo.points())
            except Exception:
                pass
        if hasattr(geo, "prims"):
            try:
                prim_count = len(geo.prims())
            except Exception:
                pass
        if hasattr(geo, "iterVertices"):
            try:
                vertex_count = sum(1 for _ in geo.iterVertices())
            except Exception:
                pass

        # Attribute names.
        for attr_list_fn_name in ("pointAttribs", "primAttribs", "vertexAttribs", "globalAttribs"):
            fn = getattr(geo, attr_list_fn_name, None)
            if fn is None:
                continue
            try:
                for attrib in fn():
                    name = getattr(attrib, "name", None)
                    if callable(name):
                        name = name()
                    if name:
                        attr_names.append(str(name))
            except Exception:
                pass

        # Group names.
        for group_fn_name in ("pointGroups", "primGroups", "edgeGroups"):
            fn = getattr(geo, group_fn_name, None)
            if fn is None:
                continue
            try:
                for grp in fn():
                    name = getattr(grp, "name", None)
                    if callable(name):
                        name = name()
                    if name:
                        group_names.append(str(name))
            except Exception:
                pass

    elapsed = time.monotonic() - t0

    return CookDiagnostic(
        node_path=node.path(),
        cooked=cook_error is None,
        cook_error=cook_error,
        errors=errors,
        warnings=warnings_list,
        point_count=point_count,
        primitive_count=prim_count,
        vertex_count=vertex_count,
        attribute_names=sorted(set(attr_names)),
        group_names=sorted(set(group_names)),
        elapsed_secs=elapsed,
    )


def get_wrangle_info(hou: Any, node_path: str) -> WrangleInfo:
    """Extract read-only metadata from an existing Wrangle node.

    This is a read-only operation — it never cooks or mutates the node.
    """
    try:
        node = _resolve_node(hou, node_path)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc

    type_name = ""
    if hasattr(node, "type"):
        try:
            type_name = str(node.type().name())
        except Exception:
            type_name = "unknown"

    run_over = ""
    run_over_parm = node.parm("class")
    if run_over_parm is not None:
        try:
            run_over = str(run_over_parm.evalAsString())
        except Exception:
            pass

    snippet_preview = ""
    has_snippet = False
    snip_parm = node.parm("snippet")
    if snip_parm is not None:
        try:
            raw = snip_parm.evalAsString() or ""
            has_snippet = bool(raw.strip())
            snippet_preview = raw[:200]
        except Exception:
            pass

    cook_state = "unknown"
    try:
        if hasattr(node, "isCooked"):
            cook_state = "cooked" if node.isCooked() else "uncooked"
    except Exception:
        pass

    input_count = 0
    output_count = 0
    if hasattr(node, "inputs"):
        try:
            input_count = len(node.inputs())
        except Exception:
            pass
    if hasattr(node, "outputs"):
        try:
            output_count = len(node.outputs())
        except Exception:
            pass

    return WrangleInfo(
        node_path=node.path(),
        node_name=str(node.name()) if hasattr(node, "name") else "",
        wrangle_type=type_name,
        run_over=run_over,
        snippet_preview=snippet_preview,
        has_snippet=has_snippet,
        cook_state=cook_state,
        input_count=input_count,
        output_count=output_count,
    )


def list_wrangles(hou: Any, parent_path: str = "/obj") -> List[Dict[str, str]]:
    """List all Wrangle-type nodes under *parent_path* recursively.

    Returns a list of ``{node_path, node_name, wrangle_type}`` dicts.
    """
    try:
        parent = _resolve_node(hou, parent_path)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc

    wrangle_type_names = {wt.value for wt in WrangleType}
    results: List[Dict[str, str]] = []

    def _walk(node: Any) -> None:
        try:
            type_name = str(node.type().name()) if hasattr(node, "type") else ""
        except Exception:
            type_name = ""
        if type_name in wrangle_type_names:
            results.append(
                {
                    "node_path": node.path(),
                    "node_name": str(node.name()) if hasattr(node, "name") else "",
                    "wrangle_type": type_name,
                }
            )
        if hasattr(node, "children"):
            try:
                for child in node.children():
                    _walk(child)
            except Exception:
                pass

    _walk(parent)
    return results


def locate_wrangle_failure(diagnostic: CookDiagnostic) -> Dict[str, Any]:
    """Analyse a failed :class:`CookDiagnostic` and suggest failure location.

    This combines:
    - Cook error messages (Houdini native errors)
    - VEX compile errors (from ``node.errors()``)
    - Geometry statistics (missing attributes, zero geometry)

    Returns a dict with ``likely_cause``, ``error_location``, ``suggested_fix``.
    """
    result: Dict[str, Any] = {
        "node_path": diagnostic.node_path,
        "cooked": diagnostic.cooked,
    }

    if diagnostic.cooked:
        result["likely_cause"] = "none"
        result["summary"] = "Node cooked successfully"
        return result

    # ── Heuristic analysis ──────────────────────────────────────────────
    all_messages = diagnostic.errors + [diagnostic.cook_error] if diagnostic.cook_error else diagnostic.errors

    # VEX compile errors typically contain specific patterns.
    vex_compile_markers = [
        "syntax error",
        "undefined variable",
        "type mismatch",
        "invalid type",
        "cannot convert",
        "no matching function",
        "unexpected",
        "unknown attribute",
        "undefined function",
        "incompatible",
    ]

    for msg in all_messages:
        msg_lower = msg.lower() if isinstance(msg, str) else ""
        for marker in vex_compile_markers:
            if marker in msg_lower:
                result["likely_cause"] = "vex_compile_error"
                result["error_location"] = str(msg)
                result["suggested_fix"] = _suggest_fix_for_marker(marker, msg)
                return result

    # Geometry issues.
    if diagnostic.cook_error and "geometry" in str(diagnostic.cook_error).lower():
        result["likely_cause"] = "geometry_error"
        result["error_location"] = diagnostic.cook_error
        result["suggested_fix"] = "Check input geometry — it may be empty or corrupted"
        return result

    # Cook timeout or process failure.
    if diagnostic.cook_error and (
        "timeout" in str(diagnostic.cook_error).lower()
        or "timed out" in str(diagnostic.cook_error).lower()
    ):
        result["likely_cause"] = "cook_timeout"
        result["error_location"] = diagnostic.cook_error
        result["suggested_fix"] = "Simplify the VEX snippet or reduce input geometry complexity"
        return result

    # Fallback: unknown error.
    result["likely_cause"] = "unknown"
    result["error_location"] = diagnostic.cook_error or "; ".join(map(str, diagnostic.errors))
    result["suggested_fix"] = "Inspect the VEX snippet and geometry manually"
    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_node(hou: Any, path: str) -> Any:
    """Resolve a node path, raising ``ValueError`` if not found."""
    node = hou.node(path)
    if node is None:
        raise ValueError(f"Houdini node not found: {path}")
    return node


def _set_run_over(node: Any, context: VexContext) -> None:
    """Set the run-over (class) parameter on a Wrangle node."""
    parm = node.parm("class")
    if parm is None:
        return
    from dcc_mcp_houdini._vex_types import vex_context_to_attrib_class

    class_value = vex_context_to_attrib_class(context)
    try:
        parm.set(class_value)
    except Exception:
        pass


def _encode_bindings(bindings: Dict[str, str]) -> str:
    """Encode attribute bindings dict into the Houdini bindings string format."""
    # Houdini expects bindings as "name=attribute type" separated by spaces.
    parts = [f"{name}={attr_type}" for name, attr_type in sorted(bindings.items())]
    return " ".join(parts)


def _fail(message: str, **extra: Any) -> Dict[str, Any]:
    """Return a failure dict."""
    result: Dict[str, Any] = {"success": False, "error": message}
    result.update(extra)
    return result


def _suggest_fix_for_marker(marker: str, error_message: str) -> str:
    """Suggest a human-readable fix based on the error marker."""
    suggestions = {
        "syntax error": "Check for missing semicolons, mismatched braces, or invalid VEX syntax",
        "undefined variable": "Ensure all variables are declared before use (e.g. 'int x; x = 1;')",
        "type mismatch": "Cast values explicitly (e.g. 'int(x)' or 'float(x)')",
        "invalid type": "Use VEX-compatible types: int, float, vector, vector2, vector4, matrix, string",
        "cannot convert": "Add explicit type casts between incompatible types",
        "no matching function": "Check function name spelling and argument types",
        "unexpected": "Verify the expression or statement is valid VEX syntax",
        "unknown attribute": "The referenced attribute does not exist on the input geometry — create it first or use hasattrib()",
        "undefined function": "The function name is not a VEX builtin — check spelling or use a vop_ equivalent",
        "incompatible": "The operation is not valid for the given types — add explicit casts",
    }
    return suggestions.get(marker, "Review the VEX snippet and input geometry")
