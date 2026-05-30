"""Attach a local Python project root to sys.path for tool development."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _dev_common import ENV_DEV_ROOTS, is_root_allowed  # noqa: E402


def attach_project(project_root: str) -> dict:
    """Add *project_root* to ``sys.path`` so its modules become importable."""
    try:
        expanded = os.path.abspath(os.path.expandvars(os.path.expanduser(project_root)))
        if not os.path.isdir(expanded):
            return skill_error(
                "Project root not found",
                "Not a directory: {}".format(expanded),
                project_root=expanded,
            )
        if not is_root_allowed(expanded):
            return skill_error(
                "Project root not allowed",
                "Path is outside the trusted {} roots".format(ENV_DEV_ROOTS),
                project_root=expanded,
            )
        already = expanded in sys.path
        if not already:
            sys.path.insert(0, expanded)
        return skill_success(
            "Attached project root",
            project_root=expanded,
            already_attached=already,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to attach project root")


@skill_entry
def main(**kwargs) -> dict:
    return attach_project(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
