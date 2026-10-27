"""Read the channel expression on a Houdini parameter, if any."""

from __future__ import annotations

from _parm_common import get_node  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


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
        keyframes = parm.keyframes()
        if len(keyframes) > 1:
            return skill_error(
                "Parameter has multiple keyframes",
                "multiple_keyframes",
                prompt="Use houdini_animation__get_keyframes to inspect each keyframe's expression.",
                node_path=node.path(),
                parm=parm_name,
                keyframe_count=len(keyframes),
            )
        if not keyframes or not keyframes[0].isExpressionSet():
            return skill_success(
                "No expression set",
                node_path=node.path(),
                parm=parm_name,
                has_expression=False,
                value=parm.eval(),
            )
        expression = parm.expression()
        language = str(parm.expressionLanguage())
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
