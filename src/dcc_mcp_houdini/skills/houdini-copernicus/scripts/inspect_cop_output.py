"""Resolve a Copernicus output path and verify the artifact on disk.

Rendering is owned by ``houdini_render__render_rop``; this tool only answers
"where would this write, and is that file actually there".
"""

import glob
import os

from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success

from dcc_mcp_houdini._domain_graph import get_node, hou_missing_error, node_summary

# Candidate output parameters, in probe order. Node types differ in which one
# they expose, so a miss is reported rather than treated as an error.
OUTPUT_PARMS = ("copoutput", "copfile", "filename", "output", "picture", "vm_picture")

MAX_MATCHES = 64


def _resolve_output_path(node, output_path):
    if output_path is not None:
        return output_path, "argument"
    for name in OUTPUT_PARMS:
        parm = node.parm(name)
        if parm is None:
            continue
        try:
            value = parm.eval()
        except Exception:
            continue
        if isinstance(value, str) and value:
            return value, name
    return None, None


def _expand_path(hou, path):
    """Expand Houdini variables and frame tokens (``$F4``, ``$F``).

    A path containing frame tokens is a pattern, not a literal file name, so a
    plain ``os.path.isfile`` on it would always report the render as failed.
    """
    expand = getattr(hou, "expandString", None)
    if not callable(expand):
        return path
    try:
        return expand(path)
    except Exception:
        return path


def _match_paths(expanded):
    """Return concrete paths for ``expanded``, globbing when it is a pattern."""
    if any(token in expanded for token in ("*", "?", "[")):
        return sorted(glob.glob(expanded))[:MAX_MATCHES]
    return [expanded] if expanded else []


def inspect_cop_output(node_path: str, output_path: str = None) -> dict:
    try:
        import hou
    except ImportError:
        return hou_missing_error()
    try:
        if output_path is not None and not isinstance(output_path, str):
            raise ValueError("output_path must be a string")
        node = get_node(hou, node_path)
        resolved, resolved_from = _resolve_output_path(node, output_path)
        expanded = _expand_path(hou, resolved) if resolved is not None else None
        matches = _match_paths(expanded) if expanded else []
        existing = []
        for candidate in matches:
            try:
                if os.path.isfile(candidate):
                    existing.append(candidate)
            except OSError:
                continue
        size_bytes = None
        if existing:
            try:
                size_bytes = os.path.getsize(existing[0])
            except OSError:
                size_bytes = None
        return skill_success(
            "Inspected Cop output",
            node=node_summary(node),
            node_path=node.path(),
            output_path=resolved,
            expanded_output_path=expanded,
            output_path_source=resolved_from,
            output_parms_probed=list(OUTPUT_PARMS),
            artifact_exists=bool(existing),
            artifact_count=len(existing),
            artifact_paths=existing,
            artifact_size_bytes=size_bytes,
            truncated_matches=len(matches) > MAX_MATCHES,
            validation_scope="filesystem_stat",
            render_verified=False,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to inspect Cop output")


@skill_entry
def main(**kwargs):
    return inspect_cop_output(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
