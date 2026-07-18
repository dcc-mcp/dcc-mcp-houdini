"""Set the Houdini project ($JOB) / workspace root with path validation."""

from __future__ import annotations

import os
from pathlib import Path

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def set_project(project_root: str, create: bool = False) -> dict:
    """Set ``$JOB`` to *project_root*; validate existence (or create it)."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        expanded = os.path.expandvars(os.path.expanduser(project_root))
        path = Path(expanded)
        if not path.exists():
            if not create:
                return skill_error(
                    "Project root does not exist",
                    "Path not found: {}".format(expanded),
                    possible_solutions=[
                        "Pass create=true to create the directory",
                        "Provide an existing absolute path",
                    ],
                    project_root=expanded,
                )
            path.mkdir(parents=True, exist_ok=True)
        elif not path.is_dir():
            return skill_error(
                "Project root is not a directory",
                "Path exists but is a file: {}".format(expanded),
                project_root=expanded,
            )
        hou.putenv("JOB", str(path))
        return skill_success(
            "Set project root",
            project_root=str(path),
            created=bool(create and not project_root),
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to set project root")


@skill_entry
def main(**kwargs) -> dict:
    return set_project(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
