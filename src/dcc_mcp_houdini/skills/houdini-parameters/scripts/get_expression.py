"""Read the channel expression on a Houdini parameter, if any."""

from __future__ import annotations

from _parm_common import get_node  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

from dcc_mcp_houdini.api import safe_parm_eval


def get_expression(node_path: str, parm_name: str) -> dict:
    """Return the parm's expression and language, or the plain value when none."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        node = get_node(hou, node_path)
        parm = node.parm(parm_name)
        if parm is None:
            return skill_error(
                "Parameter not found",
                "No parameter named {!r}".format(parm_name),
                node_path=node.path(),
            )
        try:
            expression = parm.expression()
        except Exception:  # noqa: BLE001 - HOM raises when there is no expression
            return skill_success(
                "No expression set",
                node_path=node.path(),
                parm=parm_name,
                has_expression=False,
                value=safe_parm_eval(parm),
            )
        language = None
        try:
            language = str(parm.expressionLanguage())
        except Exception:  # noqa: BLE001
            pass
        return skill_success(
            "Read expression",
            node_path=node.path(),
            parm=parm_name,
            has_expression=True,
            expression=expression,
            language=language,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to read expression")


@skill_entry
def main(**kwargs) -> dict:
    return get_expression(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
