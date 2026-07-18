"""Set up audio-driven animation using an Envelope CHOP driven by audio."""

from __future__ import annotations

from _chops_common import get_node  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def create_audio_driven(
    network_path: str,
    audio_file: str,
    target_parm: str,
    channel_name: str = "amplitude",
    envelope_name: str = "envelope1",
    amplitude_multiplier: float = 1.0,
) -> dict:
    """Create an audio-driven animation setup inside *network_path*.

    Imports an audio file as a File CHOP, then creates an Envelope CHOP to
    extract amplitude and drive a target parameter.  The chain is:

    1. ``file`` CHOP → loads *audio_file*
    2. ``envelope`` CHOP → extracts *channel_name* amplitude
    3. Connect envelope output to *target_parm* via an export flag.

    Args:
        network_path: Path to the CHOP network container.
        audio_file: Path to a ``.wav`` / ``.mp3`` / ``.aiff`` audio file.
        target_parm: Target parameter path like ``/obj/geo1/tx``.
        channel_name: Audio channel to extract (amplitude, bass, mid, treble).
        envelope_name: Name for the Envelope CHOP node.
        amplitude_multiplier: Scale factor applied to output.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        network = get_node(hou, network_path)

        # 1. Create File CHOP for the audio.
        file_node = network.createNode("file", node_name="audio_file1")
        file_node.parm("file").set(audio_file)

        # 2. Create Envelope CHOP to extract amplitude.
        envelope = network.createNode("envelope", node_name=envelope_name)
        envelope.setFirstInput(file_node)
        envelope.parm("channel").set(channel_name)
        if amplitude_multiplier != 1.0:
            envelope.parm("amp").set(float(amplitude_multiplier))

        # 3. Set export flag so CHOP drives the target parameter.
        try:
            envelope.setExportFlag(target_parm)
        except Exception:  # noqa: BLE001
            # Fallback: set generic export context.
            envelope.setGenericFlag(hou.chopNode.ExportFlag, True)

        file_node.moveToGoodPosition()
        envelope.moveToGoodPosition()

        return skill_success(
            "Created audio-driven animation",
            network_path=network_path,
            audio_file_path=file_node.path(),
            envelope_path=envelope.path(),
            audio_file=audio_file,
            channel_name=channel_name,
            target_parm=target_parm,
            amplitude_multiplier=amplitude_multiplier,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to create audio-driven animation")


@skill_entry
def main(**kwargs) -> dict:
    return create_audio_driven(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
