"""Bind an IES photometric profile to a light, reporting whether the file resolves.

An IES path that does not resolve is reported as such. Silently "binding" a path
that is not there would leave a light configured in a way that looks correct and
renders as if no profile were set.
"""

import os
from typing import Any, Optional, Tuple

from _light_rig_common import IES_ALIASES
from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success

from dcc_mcp_houdini._domain_graph import get_node, hou_missing_error, node_summary, set_parameters

IES_SETTINGS = tuple(IES_ALIASES)


def _resolve(node: Any, key: str, value: Any) -> Tuple[Optional[str], Any, Optional[str]]:
    """Return (parm_name, value, miss) for the first alias the node exposes."""
    for name in IES_ALIASES[key]:
        if node.parm(name) is not None:
            return name, value, None
    return None, None, key


def _expand(hou: Any, path: str) -> str:
    """Expand Houdini variables, so `$HIP/...` can be checked on disk."""
    expand = getattr(hou, "expandString", None)
    if not callable(expand):
        return path
    try:
        return expand(path)
    except Exception:
        return path


def set_light_ies(light_path: str, ies_file: str, settings: dict = None) -> dict:
    try:
        import hou
    except ImportError:
        return hou_missing_error()
    try:
        if not isinstance(ies_file, str) or not ies_file:
            raise ValueError("ies_file must be a non-empty string")
        if settings is not None and not isinstance(settings, dict):
            raise ValueError("settings must be an object")
        extras = dict(settings or {})
        unknown = sorted(set(extras) - set(IES_SETTINGS))
        if unknown:
            raise ValueError(
                "Unsupported IES settings: {}. Supported: {}".format(
                    ", ".join(unknown), ", ".join(sorted(IES_SETTINGS))
                )
            )
        light = get_node(hou, light_path)

        requested = {"ies_file": ies_file}
        requested.update(extras)
        overrides, skipped, resolved = {}, [], {}
        for key, value in requested.items():
            name, resolved_value, miss = _resolve(light, key, value)
            resolved[key] = name
            if miss is not None:
                skipped.append(miss)
            else:
                overrides[name] = resolved_value

        # Stat the file separately from binding it: a path that does not resolve
        # must never be reported as bound.
        expanded = _expand(hou, ies_file) if ies_file else ies_file
        try:
            ies_exists = bool(expanded) and os.path.isfile(expanded)
        except OSError:
            ies_exists = False
        # Nothing can be bound if the light exposes no IES parameter, whatever
        # the file system says.
        if not resolved.get("ies_file"):
            ies_state = "unresolved"
        else:
            ies_state = "resolved" if ies_exists else "missing"

        if not overrides:
            return skill_success(
                "No IES parameters to apply",
                light=node_summary(light),
                light_path=light.path(),
                ies_file=ies_file,
                expanded_ies_file=expanded,
                ies_file_exists=ies_exists,
                ies_state=ies_state,
                ies_bound=False,
                applied_parameters={},
                skipped_parameters=skipped,
                resolved_names=resolved,
                valid=False,
                setup_state="unchanged",
                required_setup=[
                    "this light exposes none of the known IES parameters",
                    "verify the profile renders as expected before relying on it",
                ],
                validation_scope="filesystem_stat_and_parameter_presence",
            )

        applied, _ = set_parameters(light, overrides)
        bound_name = resolved.get("ies_file")
        return skill_success(
            "Configured light IES profile" if ies_exists else "Configured light IES parameters",
            light=node_summary(light),
            light_path=light.path(),
            ies_file=ies_file,
            expanded_ies_file=expanded,
            ies_file_exists=ies_exists,
            ies_state=ies_state,
            ies_bound=bool(bound_name) and ies_exists,
            applied_parameters=applied,
            skipped_parameters=skipped,
            resolved_names=resolved,
            valid=not skipped,
            setup_state="configured",
            required_setup=["verify the profile renders as expected before relying on it"],
            validation_scope="filesystem_stat_and_parameter_presence",
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to set light IES profile")


@skill_entry
def main(**kwargs):
    return set_light_ies(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
