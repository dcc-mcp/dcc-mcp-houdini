"""Start a debugpy listener inside the Houdini process (safe defaults)."""

from __future__ import annotations

import sys
from pathlib import Path

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

# Process-wide flag so repeated calls report "already running" rather than
# raising from a second listen() on the same port.
_STATE: dict = {"listening": False, "host": None, "port": None}


def start_debugpy(host: str = "127.0.0.1", port: int = 5678) -> dict:
    """Start (or report) a debugpy listener on *host*:*port*."""
    try:
        if _STATE["listening"]:
            return skill_success(
                "debugpy already listening",
                already_running=True,
                host=_STATE["host"],
                port=_STATE["port"],
            )
        try:
            import debugpy  # noqa: PLC0415
        except ImportError:
            return skill_error(
                "debugpy not installed",
                "Install debugpy in the Houdini Python environment first",
                possible_solutions=["hython -m pip install debugpy"],
            )
        debugpy.listen((host, int(port)))
        _STATE.update({"listening": True, "host": host, "port": int(port)})
        return skill_success(
            "Started debugpy listener",
            already_running=False,
            host=host,
            port=int(port),
            attach_hint="Attach your debugger to {}:{}".format(host, int(port)),
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to start debugpy listener")


@skill_entry
def main(**kwargs) -> dict:
    return start_debugpy(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
