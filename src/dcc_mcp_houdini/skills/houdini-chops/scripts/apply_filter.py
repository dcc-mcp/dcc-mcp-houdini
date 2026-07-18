"""Apply a CHOP filter (lag, spring, noise, smooth) to a channel."""

from __future__ import annotations

from typing import Optional

from _chops_common import get_node  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

# Map filter type → Houdini CHOP node type + key parameter name.
_FILTER_TYPE_MAP = {
    "lag": ("lag", "lag"),
    "spring": ("spring", "mass"),
    "noise": ("noise", "amp"),
    "smooth": ("filter", "width"),
    "peak": ("peak", "cutoff"),
    "bandpass": ("bandpass", "freq"),
    "comp": ("comp", "max"),
    "limit": ("limit", "max"),
}


def apply_filter(
    network_path: str,
    source_node: str,
    filter_type: str,
    amount: float = 0.5,
    node_name: Optional[str] = None,
    extra_params: Optional[dict] = None,
) -> dict:
    """Apply a CHOP filter node to *source_node* inside *network_path*.

    Supported filter types (CHOP node → key param):

    - ``lag`` — exponential lag / inertia
    - ``spring`` — spring/mass dynamics with damping
    - ``noise`` — procedural noise overlay
    - ``smooth`` — Gaussian / moving-average smoothing filter
    - ``peak`` — peak / EQ filter
    - ``bandpass`` — bandpass frequency filter
    - ``comp`` — compression / limiting
    - ``limit`` — value clamp

    Args:
        network_path: Path to the CHOP network container.
        source_node: Name or path of the source CHOP node to filter.
        filter_type: One of the supported filter type keys (see above).
        amount: Primary filter strength (mapped to the key parameter).
        node_name: Name for the new filter node (auto-generated if omitted).
        extra_params: Additional parameter name → value overrides.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        network = get_node(hou, network_path)

        # Resolve source node.
        src = hou.node(source_node)
        if src is None:
            src = get_node(hou, "{}/{}".format(network.path(), source_node))

        filter_info = _FILTER_TYPE_MAP.get(filter_type.lower())
        if filter_info is None:
            supported = ", ".join(sorted(_FILTER_TYPE_MAP.keys()))
            return skill_error(
                "Unknown filter type: {}".format(filter_type),
                "supported_filters: {}".format(supported),
                supported_filters=supported,
            )

        chop_type, key_parm = filter_info
        name = node_name or "{}_{}".format(filter_type.lower(), "1")
        filter_node = network.createNode(chop_type, node_name=name)
        filter_node.setFirstInput(src)

        # Set key parameter.
        try:
            filter_node.parm(key_parm).set(float(amount))
        except Exception:  # noqa: BLE001
            pass

        applied_params = {key_parm: float(amount)}

        # Apply extra overrides.
        if extra_params:
            for parm_name, value in extra_params.items():
                try:
                    filter_node.parm(parm_name).set(value)
                    applied_params[parm_name] = value
                except Exception:  # noqa: BLE001
                    pass

        filter_node.moveToGoodPosition()

        return skill_success(
            "Applied CHOP filter",
            filter_path=filter_node.path(),
            filter_type=filter_type,
            chop_type=chop_type,
            source_path=src.path(),
            network_path=network_path,
            applied_params=applied_params,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to apply CHOP filter")


@skill_entry
def main(**kwargs) -> dict:
    return apply_filter(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
