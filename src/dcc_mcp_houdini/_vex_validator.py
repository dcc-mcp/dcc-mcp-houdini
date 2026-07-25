"""Pre-cook VEX validation: syntax, bindings, parameters.

This module validates VEX code and Wrangle parameters BEFORE they are
committed to Houdini.  All validation is read-only — it never modifies
the scene graph and never executes VEX.

Hard constraints:
- Does NOT import ``hou`` at module level (testable without Houdini).
- All ``hou``-dependent checks receive the module as an explicit parameter.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from dcc_mcp_houdini._vex_types import VexContext, VexSeverity, VexSyntaxError, WrangleType


# ---------------------------------------------------------------------------
# Client-side (no hou) validation
# ---------------------------------------------------------------------------


# Restrictive VEX allowlist: the ONLY permitted VEX constructs.
# This is the first defense against arbitrary script execution through VEX.
_ALLOWED_VEX_PATTERNS: List[re.Pattern] = [
    # — Data types —
    re.compile(r"\b(vector|vector2|vector4|matrix|matrix2|matrix3|int|float|string|int64)\b"),
    # — Attribute access (read) —
    re.compile(r"@(P|N|Cd|uv|v|id|ptnum|primnum|vtxnum|numpt|numprim|numvtx|Time|Frame|elemnum|numelem)\b"),
    # — Attribute access (generic) —
    re.compile(r"@[\w_]+"),
    # — Function calls (VEX builtins only) —
    re.compile(
        r"\b("
        r"addattribute|addvariablename|ambient|anoise|area|array|atan2|attrib|attribclass|"
        r"bbox|cbrt|ceil|ch|chv|clamp|concat|cross|curlnoise|deg|degrees|"
        r"determinant|diagonalizesymmetric|dihedral|distance|dot|"
        r"du|dv|dPdx|dPdy|dPdz|"
        r"error|exp|explodematrix|export|"
        r"filterstep|fit|fit01|fit10|fit11|flownoise|floor|frac|fresnel|fromNDC|"
        r"frontface|getattribute|getbbox|getblur|getcomp|getderiv|getmatrix|"
        r"getneighbour|getneighbourcount|getneighbourindex|getneighbourrow|"
        r"getneighbourcolumn|getneighboursurface|"
        r"getneighbourcount2|getneighbourindex2|getneighbourrow2|getneighbourcolumn2|"
        r"getneighbourcount3|getneighbourindex3|getneighbourrow3|getneighbourcolumn3|"
        r"ident|illuminance|import|importdetail|importpoint|importprim|importvertex|"
        r"invert|irradiance|isfinite|isinf|isnan|"
        r"length|length2|lerp|lighter|lookat|"
        r"match|max|min|minpos|mspace|nearpoint|nearpoints|neighbour|neighbourcount|"
        r"neighbours|noise|normalize|ntransform|"
        r"occlusion|onoise|outerproduct|ow_space|"
        r"pbrspecular|pcfilter|pgfind|pgnext|planepointdistance|planeside|"
        r"pop|pow|prim|primgrouplist|primindex|primintrinsic|primuv|"
        r"print|printf|ptlined|"
        r"radians|random|raw_noise|reflect|refract|relbbox|relpointbbox|"
        r"removeattrib|removepoint|removeprim|removevertex|"
        r"renderstate|rgbtohsv|rotate|"
        r"sample|sample_geometry|sample_discrete|"
        r"set|setattrib|setattribtypeinfo|setcomp|setdetailattrib|setpointattrib|"
        r"setpointgroup|setprimattrib|setprimgroup|setvertexattrib|setvertexgroup|"
        r"shadow|shimport|shimportfunctions|smooth|snoise|"
        r"specular|spline|split|sqrt|strip|"
        r"tan|times|toNDC|trace|transform|trunc|"
        r"vop|vop_comp|vop_flatten|vop_normalize|vop_transform|"
        r"vop_translate|vop_rotate|vop_scale|vop_add|vop_subtract|vop_multiply|vop_divide|"
        r"vop_dot|vop_cross|vop_length|vop_distance|vop_normal|vop_lerp|"
        r"vop_abs|vop_ceil|vop_floor|vop_round|vop_sin|vop_cos|vop_exp|"
        r"vop_log|vop_pow|vop_sqrt|vop_min|vop_max|vop_clamp|vop_mix|vop_select|"
        r"vop_compare|vop_switch|vop_if|vop_while|vop_for|vop_forpoints|"
        r"vop_forprims|vop_forvertices|vop_foreach|"
        r"vop_bind|vop_bindtransform|vop_float_to_int|vop_int_to_float|"
        r"vop_vector_to_float|vop_float_to_vector|vop_float_to_matrix|"
        r"vop_noise|vop_turbnoise|vop_periodicnoise|vop_worley|"
        r"wnoise|xnoise|xyzdist|rand|"
        r"acos|asin|atan|cos|cosh|sin|sinh|tanh|"
        r"abs|sign|rint|"
        # VEX flow control
        r"if|else|for|foreach|while|do|return|break|continue"
        r")\b"
    ),
    # — Comments —
    re.compile(r"//.*$|/\*.*?\*/"),
    # — Numeric literals —
    re.compile(r"\b\d+(\.\d*)?([eE][+-]?\d+)?\b"),
    # — String literals —
    re.compile(r'"[^"]*"'),
    # — Vectors/matrices —
    re.compile(r"\{[^}]*\}"),
    # — Operators —
    re.compile(r"[+\-*/%=<>!&|^~?:@.;,(){}\[\]]"),
]


# Constructs that are FORBIDDEN in any VEX snippet passed through this gateway.
# These block the "arbitrary script execution" escape hatch.
_FORBIDDEN_VEX_PATTERNS: List[re.Pattern] = [
    # Python injection via VEX
    re.compile(r"\bpython\b", re.IGNORECASE),
    re.compile(r"\bexec\b", re.IGNORECASE),
    re.compile(r"\beval\b", re.IGNORECASE),
    re.compile(r"\bimport\b", re.IGNORECASE),
    re.compile(r"\bsubprocess\b", re.IGNORECASE),
    re.compile(r"\bos\.\w+", re.IGNORECASE),
    re.compile(r"\bsys\.\w+", re.IGNORECASE),
    # System/file access — VEX has no intrinsic filesystem calls,
    # but defending against future expansions
    re.compile(r"\brun\s*\(\s*\"", re.IGNORECASE),
    re.compile(r"\bsystem\s*\(\s*\"", re.IGNORECASE),
    re.compile(r"\bpopen\b", re.IGNORECASE),
    # Houdini-specific traps
    re.compile(r"\bhou\.\w+"),
    re.compile(r"\b__\w+__\b"),  # dunder attributes
    # Unicode homoglyph / encoding attacks
    re.compile(r"[^\x00-\x7F]+", re.IGNORECASE),
    # Potential VEX escape / string injection
    re.compile(r"\\x[0-9a-fA-F]{2}"),
    re.compile(r"\\u[0-9a-fA-F]{4}"),
]


# Parameter validation rules per wrangle type.
# Maps wrangle type → {parm_name: (expected_type, allowed_values_or_Null, required)}
_WRANGLE_PARM_RULES: Dict[WrangleType, Dict[str, tuple]] = {
    WrangleType.ATTRIB_WRANGLE: {
        "snippet": (str, None, False),
        "group": (str, None, False),
        "class": (str, None, False),  # run over
        "grpfilter": (str, None, False),
        "grouptype": (str, None, False),
    },
    WrangleType.VOLUME_WRANGLE: {
        "snippet": (str, None, False),
        "group": (str, None, False),
        "bindings": (str, None, False),
    },
    WrangleType.GEOMETRY_WRANGLE: {
        "snippet": (str, None, False),
        "group": (str, None, False),
        "class": (str, None, False),
    },
    WrangleType.POINT_WRANGLE: {
        "snippet": (str, None, False),
        "group": (str, None, False),
    },
    WrangleType.PRIMITIVE_WRANGLE: {
        "snippet": (str, None, False),
        "group": (str, None, False),
    },
    WrangleType.VERTEX_WRANGLE: {
        "snippet": (str, None, False),
        "group": (str, None, False),
    },
    WrangleType.DETAIL_WRANGLE: {
        "snippet": (str, None, False),
        "group": (str, None, False),
    },
    WrangleType.TOPOLOGY_WRANGLE: {
        "snippet": (str, None, False),
        "group": (str, None, False),
    },
}




def validate_vex_snippet_client(code: str) -> List[VexSyntaxError]:
    """Client-side (no ``hou``) VEX snippet validation.

    Returns a list of :class:`VexSyntaxError`.  An empty list means the
    snippet passes all client-side checks.
    """
    errors: List[VexSyntaxError] = []

    if not code or not code.strip():
        errors.append(
            VexSyntaxError(
                message="VEX snippet is empty",
                severity=VexSeverity.ERROR,
            )
        )
        return errors

    # Check forbidden patterns first — these are hard errors.
    for pattern in _FORBIDDEN_VEX_PATTERNS:
        for match in pattern.finditer(code):
            line = code[: match.start()].count("\n") + 1
            errors.append(
                VexSyntaxError(
                    message=f"Forbidden construct in VEX snippet: '{match.group()}'",
                    severity=VexSeverity.ERROR,
                    line=line,
                    snippet_context=_extract_line(code, line),
                )
            )

    # If there are forbidden patterns, don't bother with the allowlist.
    if errors:
        return errors

    # Strip comments and strings for allowlist check.
    stripped = _strip_comments_and_strings(code)
    # Only check function-call-like tokens against the allowlist.
    # Variable names like `offset`, `x`, `y` are user-defined and not checked.
    func_calls = re.findall(r"([a-zA-Z_]\w*)\s*\(", stripped)
    for token in func_calls:
        if not _is_allowed_token(token):
            line = code[: code.find(token + "(")].count("\n") + 1
            errors.append(
                VexSyntaxError(
                    message=f"Disallowed function call in VEX snippet: '{token}()'",
                    severity=VexSeverity.ERROR,
                    line=line,
                    snippet_context=_extract_line(code, line),
                )
            )

    return errors


def validate_wrangle_parameters(
    wrangle_type: WrangleType,
    parameters: Dict[str, Any],
) -> List[str]:
    """Validate parameter names and types for a given wrangle type.

    Returns a list of error strings; empty list means all parameters are valid.
    """
    rules = _WRANGLE_PARM_RULES.get(wrangle_type, {})
    errors: List[str] = []

    for parm_name, value in parameters.items():
        rule = rules.get(parm_name)
        if rule is None:
            errors.append(
                f"Unknown parameter '{parm_name}' for wrangle type '{wrangle_type.value}'"
            )
            continue

        expected_type, allowed_values, _required = rule
        if not isinstance(value, expected_type):
            errors.append(
                f"Parameter '{parm_name}' expected type {expected_type.__name__}, "
                f"got {type(value).__name__}"
            )
        if allowed_values is not None and value not in allowed_values:
            errors.append(
                f"Parameter '{parm_name}' value '{value}' not in allowed: {allowed_values}"
            )

    return errors


def validate_attribute_bindings(
    snippet_code: str,
    known_attributes: List[str],
) -> List[VexSyntaxError]:
    """Validate that attribute bindings in VEX code reference known attributes.

    This is a best-effort static check.  Dynamic attribute names cannot be
    resolved statically.
    """
    errors: List[VexSyntaxError] = []
    known = set(known_attributes)

    # Find @attribute references that are NOT built-in globals.
    builtin_attrs = {
        "P", "N", "Cd", "uv", "v", "id", "ptnum", "primnum", "vtxnum",
        "numpt", "numprim", "numvtx", "Time", "Frame", "elemnum", "numelem",
    }

    attr_refs = re.findall(r"@(\w+)", snippet_code)
    unresolved: set[str] = set()

    for attr in attr_refs:
        if attr in builtin_attrs:
            continue
        if attr in known:
            continue
        unresolved.add(attr)

    for attr in sorted(unresolved):
        # Find where this attribute is referenced.
        first_line = None
        for match in re.finditer(rf"@{attr}\b", snippet_code):
            first_line = snippet_code[: match.start()].count("\n") + 1
            break
        msg = f"Attribute '@{attr}' is not in known geometry attributes"
        if first_line:
            errors.append(
                VexSyntaxError(
                    message=msg,
                    severity=VexSeverity.WARNING,
                    line=first_line,
                    snippet_context=_extract_line(snippet_code, first_line),
                )
            )
        else:
            errors.append(VexSyntaxError(message=msg, severity=VexSeverity.WARNING))

    return errors


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _strip_comments_and_strings(code: str) -> str:
    """Remove comments and string literals so the token allowlist is accurate."""
    # Remove block comments
    code = re.sub(r"/\*.*?\*/", " ", code, flags=re.DOTALL)
    # Remove line comments
    code = re.sub(r"//.*$", " ", code, flags=re.MULTILINE)
    # Remove string literals
    code = re.sub(r'"[^"]*"', '""', code)
    return code


def _is_allowed_token(token: str) -> bool:
    """Check if a token matches any allowlist pattern."""
    for pattern in _ALLOWED_VEX_PATTERNS:
        if pattern.fullmatch(token):
            return True
    return False


def _extract_line(code: str, line_no: int) -> Optional[str]:
    """Extract the line at *line_no* (1-indexed) from *code*."""
    lines = code.splitlines()
    idx = line_no - 1
    if 0 <= idx < len(lines):
        return lines[idx].strip()
    return None
