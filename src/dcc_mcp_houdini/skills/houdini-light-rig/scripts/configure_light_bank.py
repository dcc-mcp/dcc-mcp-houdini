"""Configure light-bank membership on a light.

Light bank parameter names differ between Houdini versions and light types, so
each setting is resolved against a small alias list. Nothing is assumed: a
setting the light does not expose is reported rather than silently dropped.
"""

from typing import Any, Optional, Tuple

from _light_rig_common import BANK_ALIASES
from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success

from dcc_mcp_houdini._domain_graph import get_node, hou_missing_error, node_summary, set_parameters

BANK_SETTINGS = tuple(BANK_ALIASES)

RENDER_NOTE = "confirm the light bank categories match the ones used at render time"


def _resolve(node: Any, key: str, value: Any) -> Tuple[Optional[str], Any, Optional[str]]:
    """Return (parm_name, value, miss) for the first alias the node exposes."""
    for name in BANK_ALIASES[key]:
        if node.parm(name) is not None:
            return name, value, None
    return None, None, key


def _first_existing(node: Any, key: str) -> Optional[str]:
    for name in BANK_ALIASES[key]:
        if node.parm(name) is not None:
            return name
    return None


def configure_light_bank(light_path: str, settings: dict) -> dict:
    try:
        import hou
    except ImportError:
        return hou_missing_error()
    try:
        if not isinstance(settings, dict) or not settings:
            raise ValueError("settings must be a non-empty object")
        unknown = sorted(set(settings) - set(BANK_SETTINGS))
        if unknown:
            raise ValueError(
                "Unsupported light bank settings: {}. Supported: {}".format(
                    ", ".join(unknown), ", ".join(sorted(BANK_SETTINGS))
                )
            )
        light = get_node(hou, light_path)

        # Read the categories before touching anything, so the response can
        # distinguish what the light had from what this call changed it to.
        found_name = _first_existing(light, "categories")
        found_categories = None
        if found_name is not None:
            try:
                found_categories = light.parm(found_name).eval()
            except Exception:
                found_categories = None

        overrides, skipped, resolved = {}, [], {}
        for key, value in settings.items():
            name, resolved_value, miss = _resolve(light, key, value)
            resolved[key] = name
            if miss is not None:
                skipped.append(miss)
            else:
                overrides[name] = resolved_value

        if not overrides:
            return skill_success(
                "No light bank parameters to apply",
                light=node_summary(light),
                light_path=light.path(),
                applied_parameters={},
                skipped_parameters=skipped,
                resolved_names=resolved,
                found_categories=found_categories,
                applied_categories=None,
                valid=False,
                setup_state="unchanged",
                required_setup=[
                    RENDER_NOTE,
                    "this light exposes none of the known light bank parameters",
                ],
                validation_scope="parameter_presence",
            )

        applied, _ = set_parameters(light, overrides)
        categories_name = resolved.get("categories")
        return skill_success(
            "Configured light bank",
            light=node_summary(light),
            light_path=light.path(),
            applied_parameters=applied,
            skipped_parameters=skipped,
            resolved_names=resolved,
            found_categories=found_categories,
            applied_categories=applied.get(categories_name) if categories_name else None,
            valid=not skipped,
            setup_state="configured",
            required_setup=[RENDER_NOTE],
            validation_scope="parameter_presence_and_readback",
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to configure light bank")


@skill_entry
def main(**kwargs):
    return configure_light_bank(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
