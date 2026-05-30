"""Run a project-local .py script with captured stdout/stderr/traceback."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _dev_common import capture_call, is_root_allowed  # noqa: E402


def run_script(script_path: str) -> dict:
    """Execute *script_path* in a fresh namespace and capture its output."""
    try:
        expanded = os.path.abspath(os.path.expandvars(os.path.expanduser(script_path)))
        if not os.path.isfile(expanded):
            return skill_error(
                "Script not found",
                "Not a file: {}".format(expanded),
                script_path=expanded,
            )
        if not is_root_allowed(expanded):
            return skill_error(
                "Script not allowed",
                "Path is outside the trusted dev roots",
                script_path=expanded,
            )
        with open(expanded, "r", encoding="utf-8") as handle:
            source = handle.read()

        namespace = {"__name__": "__main__", "__file__": expanded}
        code = compile(source, expanded, "exec")
        _, out, err, tb = capture_call(lambda: exec(code, namespace))  # noqa: S102
        if tb is not None:
            return skill_error(
                "Script raised",
                "Exception while running {}".format(expanded),
                script_path=expanded,
                stdout=out,
                stderr=err,
                traceback=tb,
            )
        return skill_success(
            "Ran script",
            script_path=expanded,
            stdout=out,
            stderr=err,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to run script")


@skill_entry
def main(**kwargs) -> dict:
    return run_script(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
