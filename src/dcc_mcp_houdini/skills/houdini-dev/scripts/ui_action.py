"""Trigger supported Houdini UI actions (switch desktop, display message)."""

from __future__ import annotations

from typing import Optional

from _dev_common import has_ui  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SUPPORTED = ("set_desktop", "display_message", "cook_meta")


def ui_action(action: str, value: Optional[str] = None) -> dict:
    """Perform a small, safe UI action.

    Supported actions: ``set_desktop`` (value=desktop name),
    ``display_message`` (value=text), ``cook_meta`` (force a UI status update).
    Returns ``supported=false`` in headless hython.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        if action not in _SUPPORTED:
            return skill_error(
                "Unsupported action",
                "Unknown action {!r}".format(action),
                supported_actions=list(_SUPPORTED),
            )
        if not has_ui(hou):
            return skill_success(
                "UI not available (headless)",
                supported=False,
                action=action,
            )

        if action == "set_desktop":
            if not value:
                return skill_error("Missing value", "set_desktop requires a desktop name")
            target = next((d for d in hou.ui.desktops() if d.name() == value), None)
            if target is None:
                return skill_error("Desktop not found", "No desktop named {!r}".format(value))
            target.setAsCurrent()
            return skill_success("Switched desktop", supported=True, action=action, desktop=value)

        if action == "display_message":
            hou.ui.displayMessage(value or "")
            return skill_success("Displayed message", supported=True, action=action)

        # cook_meta — nudge the UI to refresh; harmless no-op signal.
        trigger = getattr(hou.ui, "triggerUpdate", None)
        if callable(trigger):
            trigger()
        return skill_success("Triggered UI update", supported=True, action=action)
    except Exception as exc:
        return skill_exception(exc, message="Failed to perform UI action")


@skill_entry
def main(**kwargs) -> dict:
    return ui_action(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
