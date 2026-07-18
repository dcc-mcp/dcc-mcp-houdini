"""Probe a file path for interchange (no Houdini required)."""

from __future__ import annotations

from _io_common import probe  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success


def probe_file(file_path: str) -> dict:
    """Report existence, size, format category, and import support for a path."""
    try:
        info = probe(file_path)
        return skill_success("Probed file", **info)
    except Exception as exc:
        return skill_exception(exc, message="Failed to probe file")


@skill_entry
def main(**kwargs) -> dict:
    return probe_file(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
