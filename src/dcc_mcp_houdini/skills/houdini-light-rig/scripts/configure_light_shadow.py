"""Apply bounded shadow settings to an existing light."""

from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success

from dcc_mcp_houdini._domain_graph import get_node, hou_missing_error, node_summary, parameter_edit

# Light types differ in which shadow parameters they expose. Each name is only
# applied when the light exposes it; anything the light does not support is
# reported so a caller never mistakes an unsupported knob for one that took.
SHADOW_PARM_ALIASES = {
    "enable": ("shadowenable", "enableshadows", "castshadow", "vm_castshadow"),
    "type": ("shadowtype", "vm_shadowtype", "shadow_type"),
    "quality": ("shadowquality", "vm_shadowquality"),
    "softness": ("shadowblur", "vm_shadowblur", "shadowsoft"),
    "samples": ("shadowsamples", "vm_shadowsamples", "samples"),
    "distance": ("shadowdistance", "vm_shadowdistance"),
    "bias": ("shadowbias", "vm_shadowbias"),
    "color": ("shadowcolor", "vm_shadowcolor"),
}


def _resolve(node, key, value):
    """Return (parm_name, applied_value, skipped) for the first matching alias."""
    for name in SHADOW_PARM_ALIASES[key]:
        parm = node.parm(name)
        if parm is not None:
            return name, value, None
    return None, None, key


def configure_light_shadow(light_path: str, settings) -> dict:
    try:
        import hou
    except ImportError:
        return hou_missing_error()
    try:
        if not isinstance(settings, dict) or not settings:
            raise ValueError("settings must be a non-empty object")
        unknown = sorted(set(settings) - set(SHADOW_PARM_ALIASES))
        if unknown:
            raise ValueError("Unsupported shadow settings: {}".format(", ".join(unknown)))
        light = get_node(hou, light_path)
        # Single pass: collect the resolved parameter name alongside the value so
        # every setting is resolved exactly once.
        overrides = {}
        skipped = []
        resolved = {}
        for key, value in settings.items():
            name, resolved_value, miss = _resolve(light, key, value)
            resolved[key] = name
            if miss is not None:
                skipped.append(miss)
            else:
                overrides[name] = resolved_value
        if not overrides:
            return skill_success(
                "No shadow parameters to apply",
                light=node_summary(light),
                light_path=light.path(),
                applied_parameters={},
                skipped_parameters=skipped,
                resolved_names=resolved,
                # Nothing was applied, so this is not a valid configuration.
                valid=not skipped,
                validation_scope="parameter_presence",
            )
        applied = None
        with parameter_edit(light, overrides) as applied_values:
            applied = applied_values
        return skill_success(
            "Configured light shadow",
            light=node_summary(light),
            light_path=light.path(),
            applied_parameters=applied,
            skipped_parameters=skipped,
            resolved_names=resolved,
            # A partial configuration is not a valid one: some settings were
            # skipped, so reporting valid=True would contradict both fields.
            valid=not skipped,
            validation_scope="parameter_presence_and_readback",
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to configure light shadow")


@skill_entry
def main(**kwargs):
    return configure_light_shadow(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
