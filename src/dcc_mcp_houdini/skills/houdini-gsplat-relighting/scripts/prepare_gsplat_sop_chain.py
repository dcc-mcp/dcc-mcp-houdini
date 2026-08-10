"""Skill entrypoint for GSplat SOP preparation."""

from dcc_mcp_core.skill import run_main, skill_entry
from gsplat_relighting import prepare_gsplat_sop_chain


@skill_entry
def main(**kwargs):
    return prepare_gsplat_sop_chain(**kwargs)


if __name__ == "__main__":
    run_main(main)
