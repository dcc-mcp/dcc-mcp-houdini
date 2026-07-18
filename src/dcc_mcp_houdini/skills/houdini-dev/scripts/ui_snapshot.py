"""Snapshot Houdini UI desktops, pane tabs, and the floating-panel layout."""

from __future__ import annotations

from _dev_common import has_ui  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def ui_snapshot() -> dict:
    """Return the current desktop, available desktops, and pane-tab types.

    Returns a clean ``supported=false`` result in headless hython.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        if not has_ui(hou):
            return skill_success(
                "UI not available (headless)",
                supported=False,
                desktops=[],
                pane_tabs=[],
            )

        desktops = []
        current = None
        try:
            desktops = [d.name() for d in hou.ui.desktops()]
            current = hou.ui.curDesktop().name()
        except Exception:  # noqa: BLE001
            pass

        pane_tabs = []
        try:
            for tab in hou.ui.paneTabs():
                pane_tabs.append(
                    {
                        "name": tab.name() if hasattr(tab, "name") else None,
                        "type": str(tab.type()) if hasattr(tab, "type") else None,
                    }
                )
        except Exception:  # noqa: BLE001
            pass

        return skill_success(
            "Captured UI snapshot",
            supported=True,
            current_desktop=current,
            desktops=desktops,
            pane_tab_count=len(pane_tabs),
            pane_tabs=pane_tabs,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to snapshot UI")


@skill_entry
def main(**kwargs) -> dict:
    return ui_snapshot(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
