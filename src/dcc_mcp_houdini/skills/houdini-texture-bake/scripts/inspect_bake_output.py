"""Verify that baked textures landed on disk, expanding the UDIM token.

A path containing ``%(UDIM)d`` or ``$UDIM`` is a pattern, so stat-ing the
literal string would always report the bake as failed. This tool expands the
token, globs the result and reports which expected tiles are missing.
"""

from __future__ import annotations

import glob
import os
from typing import Any, List

from _texture_bake_common import UDIM_TOKEN, bake_output_paths
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

MAX_MATCHES = 256

# Houdini's own spelling of the UDIM token, in probe order.
UDIM_TOKENS = (UDIM_TOKEN, "%(UDIM)s", "$UDIM", "<UDIM>")


def _expand(hou: Any, path: str) -> str:
    expand = getattr(hou, "expandString", None)
    if not callable(expand):
        return path
    try:
        return expand(path)
    except Exception:
        return path


def _pattern_for(expanded: str) -> str:
    for token in UDIM_TOKENS:
        if token in expanded:
            return expanded.replace(token, "*"), token
    return expanded, ""


def inspect_bake_output(output_path: str, expected_tiles: List[int] = None) -> dict:
    """Report which baked files exist for ``output_path``.

    ``expected_tiles`` is the authoritative check: each tile is resolved to a
    concrete path and stat-ed, so a missing tile is reported by name instead of
    hiding behind an aggregate count.
    """
    try:
        import hou
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")
    try:
        if not isinstance(output_path, str) or not output_path:
            raise ValueError("output_path must be a non-empty string")
        tiles = []
        if expected_tiles is not None:
            if not isinstance(expected_tiles, (list, tuple)):
                raise ValueError("expected_tiles must be a list of tile indices")
            for tile in expected_tiles:
                if not isinstance(tile, int) or isinstance(tile, bool):
                    raise ValueError("expected_tiles entries must be integers")
                if tile not in tiles:
                    tiles.append(tile)
        expanded = _expand(hou, output_path)
        pattern, token = _pattern_for(expanded)
        matches = (
            sorted(glob.glob(pattern))[:MAX_MATCHES]
            if any(ch in pattern for ch in "*?[")
            else ([pattern] if pattern else [])
        )
        existing = []
        for candidate in matches:
            try:
                if os.path.isfile(candidate):
                    existing.append(candidate)
            except OSError:
                continue
        tile_report = []
        if tiles:
            for tile in tiles:
                concrete = bake_output_paths(expanded, [tile])
                concrete = concrete[0] if concrete else expanded
                try:
                    present = os.path.isfile(concrete)
                except OSError:
                    present = False
                tile_report.append({"tile": tile, "path": concrete, "exists": present})
        missing = [item["tile"] for item in tile_report if not item["exists"]]
        return skill_success(
            "Inspected bake output",
            output_path=output_path,
            expanded_output_path=expanded,
            udim_token=token,
            artifact_exists=bool(existing),
            artifact_count=len(existing),
            artifact_paths=existing,
            truncated_matches=len(matches) >= MAX_MATCHES,
            expected_tiles=tiles,
            tile_results=tile_report,
            missing_tiles=missing,
            all_tiles_present=bool(tile_report) and not missing,
            validation_scope="filesystem_stat",
            bake_verified=False,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to inspect bake output")


@skill_entry
def main(**kwargs):
    return inspect_bake_output(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
