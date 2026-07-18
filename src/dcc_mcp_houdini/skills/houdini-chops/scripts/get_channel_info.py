"""Inspect CHOP node channels — names, sample rate, length, value range."""

from __future__ import annotations

from _chops_common import chop_node_info, get_node  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def get_channel_info(node_path: str) -> dict:
    """Return summary information for the CHOP node at *node_path*.

    Includes: node type, sample rate, segment length, channel names/count,
    time range, and metadata.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        node = get_node(hou, node_path)
        info = chop_node_info(node)

        # Per-channel details (value range at current frame).
        channels_detail = []
        try:
            for ch in node.channels():
                detail = {
                    "name": ch.name(),
                    "sample_rate": node.sampleRate() if hasattr(node, "sampleRate") else None,
                }
                # Try to read current values.
                try:
                    detail["value"] = ch.eval(hou.frame())
                except Exception:  # noqa: BLE001
                    detail["value"] = None
                channels_detail.append(detail)
        except Exception:  # noqa: BLE001
            pass

        info["channels"] = channels_detail

        return skill_success(
            "Retrieved CHOP channel info",
            node_path=node.path(),
            **info,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to get CHOP channel info")


@skill_entry
def main(**kwargs) -> dict:
    return get_channel_info(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
