"""Skill entrypoint for the stable Solaris-relit GSplat SOP bridge."""

from dcc_mcp_core.skill import skill_entry
from gsplat_relighting import refresh_gsplat_relight_sop_bridge


@skill_entry
def main(**kwargs):
    return refresh_gsplat_relight_sop_bridge(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
