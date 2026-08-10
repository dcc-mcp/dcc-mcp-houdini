"""Skill entrypoint for Solaris GSplat relighting."""

from dcc_mcp_core.skill import run_main, skill_entry
from gsplat_relighting import create_gsplat_relight_lop


@skill_entry
def main(**kwargs):
    return create_gsplat_relight_lop(**kwargs)


if __name__ == "__main__":
    run_main(main)
