"""Run a project-local .py script with captured stdout/stderr/traceback."""

from __future__ import annotations

import os

from _dev_common import capture_call, is_root_allowed  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


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
