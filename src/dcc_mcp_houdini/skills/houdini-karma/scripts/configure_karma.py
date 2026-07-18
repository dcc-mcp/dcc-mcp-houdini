"""Configure Karma CPU/XPU render settings on a Karma LOP or ROP node."""

from __future__ import annotations

from typing import Optional

from _karma_common import get_node, node_summary, set_first_parm  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

# Karma device / engine options
KARMA_DEVICES = {
    "cpu": {"engine": "cpu", "description": "Karma CPU"},
    "xpu": {"engine": "xpu", "description": "Karma XPU (GPU accelerated)"},
}


def configure_karma(
    node_path: str,
    device: str = "cpu",
    max_samples: Optional[int] = None,
    pixel_samples: Optional[int] = None,
    diffuse_samples: Optional[int] = None,
    specular_samples: Optional[int] = None,
    transmission_samples: Optional[int] = None,
    volume_samples: Optional[int] = None,
    noise_threshold: Optional[float] = None,
    denoise: Optional[bool] = None,
) -> dict:
    """Configure Karma renderer settings (CPU/XPU, samples, denoising)."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        node = get_node(hou, node_path)
        applied: dict = {}

        # Device selection
        device_info = KARMA_DEVICES.get(device.lower(), KARMA_DEVICES["cpu"])
        engine_set = set_first_parm(
            node,
            ("renderengine", "engine", "render_engine", "karma_renderengine"),
            device_info["engine"],
        )
        if engine_set:
            applied["device"] = device
            applied["engine"] = device_info["engine"]
        else:
            applied["device"] = "{} (hint: node may not support engine param)".format(device)

        # Sample settings — defensive multi-candidate names
        sample_map = [
            (max_samples, ("maxsamples", "max_samples", "vm_samples", "vm_maxsamples")),
            (pixel_samples, ("pixelsamples", "pixel_samples", "vm_pixelsamples")),
            (diffuse_samples, ("diffusesamples", "diffuse_samples")),
            (specular_samples, ("specularsamples", "specular_samples")),
            (transmission_samples, ("transmissionsamples", "transmission_samples")),
            (volume_samples, ("volumesamples", "volume_samples")),
        ]
        for value, names in sample_map:
            if value is not None:
                used = set_first_parm(node, names, int(value))
                applied[names[0]] = int(value) if used else "unsupported"

        # Noise threshold
        if noise_threshold is not None:
            used = set_first_parm(
                node,
                ("noisethreshold", "noise_threshold", "vm_noisethreshold"),
                float(noise_threshold),
            )
            applied["noise_threshold"] = float(noise_threshold) if used else "unsupported"

        # Denoise
        if denoise is not None:
            used = set_first_parm(
                node,
                ("denoise", "enable_denoise", "vm_denoise"),
                int(denoise),
            )
            applied["denoise"] = denoise if used else "unsupported"

        return skill_success(
            "Configured Karma renderer",
            node=node_summary(node),
            applied=applied,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to configure Karma")


@skill_entry
def main(**kwargs) -> dict:
    return configure_karma(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
