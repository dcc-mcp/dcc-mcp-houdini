"""Set a keyframe (value or expression) on a node parameter at a frame."""

from __future__ import annotations

from typing import Optional

from _anim_common import get_node, get_parm  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_INTERPOLATION_EXPRESSIONS = {
    "bezier": "bezier()",
    "linear": "linear()",
    "constant": "constant()",
}


def set_keyframe(
    node_path: str,
    parm_name: str,
    frame: float,
    value: Optional[float] = None,
    expression: Optional[str] = None,
    language: str = "hscript",
    interpolation: Optional[str] = None,
) -> dict:
    """Set a keyframe on ``node_path/parm_name`` at *frame*.

    Provide ``value`` for a numeric key or ``expression`` for an expression
    key (``language`` is "hscript" or "python"). For numeric keys, optional
    ``interpolation`` selects the segment function starting at this key.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    if value is None and expression is None:
        return skill_error("Nothing to set", "Provide value or expression")
    if expression is not None and interpolation is not None:
        return skill_error(
            "Conflicting keyframe options",
            "interpolation applies only to numeric value keys",
        )

    normalized_interpolation = interpolation.lower() if interpolation is not None else None
    if normalized_interpolation is not None and normalized_interpolation not in _INTERPOLATION_EXPRESSIONS:
        return skill_error(
            "Unsupported interpolation",
            "interpolation must be 'bezier', 'linear', or 'constant'",
            requested=interpolation,
        )

    try:
        node = get_node(hou, node_path)
        parm = get_parm(node, parm_name)
        kf = hou.Keyframe()
        kf.setFrame(float(frame))
        if expression is not None:
            lang = hou.exprLanguage.Python if language.lower() == "python" else hou.exprLanguage.Hscript
            kf.setExpression(expression, lang)
        else:
            kf.setValue(float(value))
            if normalized_interpolation is not None:
                kf.setExpression(
                    _INTERPOLATION_EXPRESSIONS[normalized_interpolation],
                    hou.exprLanguage.Hscript,
                )
        parm.setKeyframe(kf)
        return skill_success(
            "Set keyframe",
            node_path=node.path(),
            parm=parm_name,
            frame=float(frame),
            value=value,
            expression=expression,
            interpolation=normalized_interpolation,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to set keyframe")


@skill_entry
def main(**kwargs) -> dict:
    return set_keyframe(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
