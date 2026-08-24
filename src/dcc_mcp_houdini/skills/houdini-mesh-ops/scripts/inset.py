"""Inset selected primitives through the verified PolyExtrude path."""

from __future__ import annotations

from typing import Optional

from dcc_mcp_core.skill import skill_entry
from extrude_faces import extrude_faces  # noqa: E402


def inset(
    input_path: str,
    amount: float,
    group: Optional[str] = None,
    node_name: Optional[str] = None,
) -> dict:
    """Inset selected primitives without exposing raw HOM execution."""
    return extrude_faces(
        input_path=input_path,
        group=group,
        distance=0.0,
        inset=amount,
        node_name=node_name,
    )


@skill_entry
def main(**kwargs) -> dict:
    return inset(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
