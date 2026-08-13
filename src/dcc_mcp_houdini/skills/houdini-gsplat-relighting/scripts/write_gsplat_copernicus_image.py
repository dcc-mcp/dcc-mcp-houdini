"""Skill entrypoint for verified Copernicus Image ROP output."""

from typing import Sequence

from dcc_mcp_core.skill import skill_entry
from gsplat_relighting import write_gsplat_copernicus_image


@skill_entry
def main(
    cop_output_path: str,
    output_file: str,
    frame: float,
    resolution: Sequence[int],
    color_conversion: str,
    rop_name: str = "dcc_mcp_gsplat_image_proof",
):
    return write_gsplat_copernicus_image(
        cop_output_path=cop_output_path,
        output_file=output_file,
        frame=frame,
        resolution=resolution,
        color_conversion=color_conversion,
        rop_name=rop_name,
    )


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
