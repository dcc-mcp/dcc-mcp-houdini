"""Cook a Wrangle node and return geometry diagnostics — the sole VEX evaluation path."""

from __future__ import annotations

from _vex_common import _get_node  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def cook_wrangle(node_path: str, force: bool = False) -> dict:
    """Cook *node_path* and return cook status plus geometry diagnostics.

    The cook triggers VEX compilation and evaluation inside Houdini.
    Diagnostics include point/prim/vertex counts, attribute names, group
    names, and any cook errors or warnings.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        from dcc_mcp_houdini._vex_executor import cook_and_diagnose
    except ImportError as exc:
        return skill_error("VEX module not available", str(exc))

    try:
        diag = cook_and_diagnose(hou, node_path, force=force)
        return skill_success("Cooked Wrangle", **diag.to_dict())
    except Exception as exc:
        return skill_exception(exc, message="Failed to cook Wrangle")


@skill_entry
def main(**kwargs) -> dict:
    return cook_wrangle(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
