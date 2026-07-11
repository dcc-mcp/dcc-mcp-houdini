"""Get Houdini version and Python environment information."""

from __future__ import annotations

import sys

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def get_session_info() -> dict:
    """Return Houdini version and Python environment details."""
    try:
        import hou  # noqa: PLC0415

        info = {
            "houdini_version": ".".join(str(v) for v in hou.applicationVersion()),
            "houdini_version_string": hou.applicationVersionString(),
            "python_version": sys.version,
            "python_executable": sys.executable,
            "platform": sys.platform,
            "ui_available": bool(hou.isUIAvailable()),
            "hip_file": hou.hipFile.name() if not hou.hipFile.isNewFile() else None,
        }
        return skill_success(
            "Houdini session info retrieved",
            **info,
            prompt="Use execute_python to run custom Houdini Python code.",
        )
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to get Houdini session info")


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`get_session_info`."""
    return get_session_info(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
