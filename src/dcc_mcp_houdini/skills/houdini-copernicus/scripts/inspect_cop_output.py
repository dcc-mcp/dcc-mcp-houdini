"""Resolve a Copernicus output path and verify the artifact on disk.

Rendering is owned by ``houdini_render__render_rop``; this tool only answers
"where would this write, and is that file actually there".
"""

import os

from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success

from dcc_mcp_houdini._domain_graph import get_node, hou_missing_error, node_summary

# Candidate output parameters, in probe order. Node types differ in which one
# they expose, so a miss is reported rather than treated as an error.
OUTPUT_PARMS = ("copoutput", "copfile", "filename", "output", "picture", "vm_picture")


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
        exists = False
        size_bytes = None
        if resolved is not None:
            try:
                exists = os.path.isfile(resolved)
                size_bytes = os.path.getsize(resolved) if exists else None
            except OSError:
                exists = False
        return skill_success(
            "Inspected Cop output",
            node=node_summary(node),
            node_path=node.path(),
            output_path=resolved,
            output_path_source=resolved_from,
            output_parms_probed=list(OUTPUT_PARMS),
            artifact_exists=exists,
            artifact_size_bytes=size_bytes,
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
