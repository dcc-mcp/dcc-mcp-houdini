"""Get Houdini version and Python environment information."""

from __future__ import annotations

import os
import sys

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

from dcc_mcp_houdini._installer import _host_root, _process_executable_path, _process_start_identity


def get_session_info() -> dict:
    """Return Houdini version and Python environment details."""
    try:
        import dcc_mcp_core  # noqa: PLC0415
        import hou  # noqa: PLC0415

        import dcc_mcp_houdini  # noqa: PLC0415

        host_pid = os.getpid()
        host_executable = _process_executable_path(host_pid)

        info = {
            "adapter_version": dcc_mcp_houdini.__version__,
            "adapter_module_path": dcc_mcp_houdini.__file__,
            "core_module_path": dcc_mcp_core.__file__,
            "hou_module_path": getattr(hou, "__file__", None),
            "houdini_version": ".".join(str(v) for v in hou.applicationVersion()),
            "houdini_version_string": hou.applicationVersionString(),
            "host_pid": host_pid,
            "host_executable": str(host_executable) if host_executable else None,
            "houdini_root": str(_host_root(host_executable)) if host_executable else None,
            "process_start_identity": _process_start_identity(host_pid),
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
