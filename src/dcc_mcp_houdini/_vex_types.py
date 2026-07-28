"""Typed contracts for the Houdini VEX workflow.

This module defines the typed enums, dataclasses, and validation contracts
that form the safe boundary between user-facing MCP tools and the Houdini
Wrangle node manipulation.  No raw dicts or untyped strings cross this
boundary — every VEX operation is validated against these types.

Hard constraint: this module is Python-only.  It does NOT import ``hou``
and runs in any environment (tests, CI, linting).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class VexContext(str, Enum):
    """VEX geometry context — maps to the Wrangle node's run-over mode."""

    POINTS = "points"
    PRIMITIVES = "prims"
    VERTICES = "verts"
    DETAIL = "detail"
    GLOBAL_VERTICES = "global"
    ATTRIBUTES = "attribs"
    NUMBERS = "numbers"


class WrangleType(str, Enum):
    """Houdini Wrangle SOP types that carry VEX snippets."""

    ATTRIB_WRANGLE = "attribwrangle"
    VOLUME_WRANGLE = "volumewrangle"
    ATTRIB_VOP = "attribvop"
    GEOMETRY_WRANGLE = "geometrywrangle"
    POINT_WRANGLE = "pointwrangle"
    PRIMITIVE_WRANGLE = "primitivewrangle"
    VERTEX_WRANGLE = "vertexwrangle"
    DETAIL_WRANGLE = "detailwrangle"
    TOPOLOGY_WRANGLE = "topologywrangle"

    @classmethod
    def default_for_context(cls, context: VexContext) -> "WrangleType":
        """Return the most appropriate wrangle type for a give context."""
        _context_map: dict[VexContext, WrangleType] = {
            VexContext.POINTS: cls.POINT_WRANGLE,
            VexContext.PRIMITIVES: cls.PRIMITIVE_WRANGLE,
            VexContext.VERTICES: cls.VERTEX_WRANGLE,
            VexContext.DETAIL: cls.DETAIL_WRANGLE,
            VexContext.GLOBAL_VERTICES: cls.ATTRIB_WRANGLE,
            VexContext.ATTRIBUTES: cls.ATTRIB_WRANGLE,
            VexContext.NUMBERS: cls.ATTRIB_WRANGLE,
        }
        return _context_map.get(context, cls.ATTRIB_WRANGLE)


class VexSeverity(str, Enum):
    """Severity levels for VEX diagnostics."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


# ---------------------------------------------------------------------------
# Dataclasses — immutable typed contracts
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VexSyntaxError:
    """A single VEX compile diagnostic with file-like location."""

    message: str
    severity: VexSeverity = VexSeverity.ERROR
    line: Optional[int] = None
    column: Optional[int] = None
    snippet_context: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "message": self.message,
            "severity": self.severity.value,
        }
        if self.line is not None:
            result["line"] = self.line
        if self.column is not None:
            result["column"] = self.column
        if self.snippet_context is not None:
            result["snippet_context"] = self.snippet_context
        return result


@dataclass(frozen=True)
class VexSnippet:
    """A validated VEX code fragment with its bindings and metadata.

    This is the ONLY type that carries VEX code across module boundaries.
    Code that is not wrapped in a :class:`VexSnippet` must never be set on
    a Wrangle node.
    """

    code: str
    context: VexContext
    bindings: Dict[str, str] = field(default_factory=dict)
    parameter_values: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.code, str) or not self.code.strip():
            raise ValueError("VEX snippet code must be a non-empty string")
        if not isinstance(self.context, VexContext):
            raise ValueError(f"context must be a VexContext, got {type(self.context)}")

    @property
    def line_count(self) -> int:
        """Number of non-empty lines in the snippet."""
        return len([ln for ln in self.code.splitlines() if ln.strip()])


@dataclass(frozen=True)
class WrangleNodeSpec:
    """Specification for creating or updating a Wrangle node."""

    parent_path: str
    node_name: Optional[str] = None
    wrangle_type: WrangleType = WrangleType.ATTRIB_WRANGLE
    run_over: VexContext = VexContext.POINTS
    snippet: Optional[VexSnippet] = None
    set_display: bool = True
    set_render: bool = False

    def __post_init__(self) -> None:
        if not self.parent_path or not isinstance(self.parent_path, str):
            raise ValueError("parent_path must be a non-empty string")
        if not isinstance(self.wrangle_type, WrangleType):
            raise ValueError(f"wrangle_type must be a WrangleType, got {type(self.wrangle_type)}")
        if self.snippet is not None and not isinstance(self.snippet, VexSnippet):
            raise ValueError(f"snippet must be a VexSnippet, got {type(self.snippet)}")


# Mapping from VexContext to stable Attrib Wrangle menu tokens.
_VEX_CONTEXT_TO_ATTRIB_CLASS: Dict[VexContext, str] = {
    VexContext.POINTS: "point",
    VexContext.PRIMITIVES: "prim",
    VexContext.VERTICES: "vertex",
    VexContext.DETAIL: "detail",
    VexContext.GLOBAL_VERTICES: "point",
    VexContext.ATTRIBUTES: "point",
    VexContext.NUMBERS: "point",
}


def vex_context_to_attrib_class(context: VexContext) -> str:
    """Map a :class:`VexContext` to the Attrib Wrangle menu token."""
    return _VEX_CONTEXT_TO_ATTRIB_CLASS.get(context, "point")


@dataclass(frozen=True)
class CookDiagnostic:
    """The result of cooking a Wrangle node, including geometry diagnostics."""

    node_path: str
    cooked: bool
    cook_error: Optional[str] = None
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    point_count: Optional[int] = None
    primitive_count: Optional[int] = None
    vertex_count: Optional[int] = None
    attribute_names: List[str] = field(default_factory=list)
    group_names: List[str] = field(default_factory=list)
    elapsed_secs: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-compatible dict for MCP tool responses."""
        result: Dict[str, Any] = {
            "node_path": self.node_path,
            "cooked": self.cooked,
            "errors": self.errors,
            "warnings": self.warnings,
        }
        if self.cook_error:
            result["cook_error"] = self.cook_error
        if self.point_count is not None:
            result["point_count"] = self.point_count
        if self.primitive_count is not None:
            result["primitive_count"] = self.primitive_count
        if self.vertex_count is not None:
            result["vertex_count"] = self.vertex_count
        if self.attribute_names:
            result["attribute_names"] = self.attribute_names
        if self.group_names:
            result["group_names"] = self.group_names
        if self.elapsed_secs is not None:
            result["elapsed_secs"] = round(self.elapsed_secs, 3)
        return result


@dataclass(frozen=True)
class WrangleInfo:
    """Read-only info extracted from an existing Wrangle node."""

    node_path: str
    node_name: str
    wrangle_type: str
    run_over: str
    snippet_preview: str
    has_snippet: bool
    cook_state: str
    input_count: int
    output_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_path": self.node_path,
            "node_name": self.node_name,
            "wrangle_type": self.wrangle_type,
            "run_over": self.run_over,
            "snippet_preview": self.snippet_preview,
            "has_snippet": self.has_snippet,
            "cook_state": self.cook_state,
            "input_count": self.input_count,
            "output_count": self.output_count,
        }
