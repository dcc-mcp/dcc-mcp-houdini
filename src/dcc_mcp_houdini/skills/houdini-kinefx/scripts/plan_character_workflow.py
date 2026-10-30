"""Return the end-to-end Houdini character-animation workflow design.

This is a *pure* tool (no ``hou`` import): it returns the machine-readable
contract behind ``docs/guide/houdini-character-animation-workflow.md`` so an
agent can discover the eight stages, the tools that implement each stage, the
gaps that were filled, the enhancements, and the equivalent alternatives for
external (codex / hyper3d) capabilities that are not callable inside Houdini.

Stage order (given by the product requirement):

1. codex character design -> ``design_character`` (equivalent alternative)
2. hyper3d character generation -> ``import_generated_character`` (equivalent)
3. Biped template -> ``create_biped_template``
4. biped retarget -> ``configure_biped_retarget`` + ``build_retarget_motion_mixer``
5. rig inversion -> ``invert_rig``
6. Motion Mixer full body IK -> ``build_retarget_motion_mixer`` (enhanced)
7. ragdoll -> ``build_ragdoll``
8. KineFx APEX FBX biped template -> ``build_apex_fbx_biped``
"""

from __future__ import annotations

from typing import Optional

from dcc_mcp_core.skill import skill_entry, skill_success

# External capabilities: not bound as callable tools inside a Houdini adapter.
# An orchestrator may override the booleans after probing its own environment.
EXTERNAL_CAPABILITIES = {
    "codex": {
        "role": "Generate a character design brief/spec from a natural-language prompt.",
        "bound_to_adapter": False,
        "probing": (
            "A generic Codex/LLM coding agent is not a Houdini MCP tool. Its output "
            "must be captured as a JSON design spec and validated before use."
        ),
        "equivalent": "design_character",
        "equivalent_detail": (
            "Deterministic structured design spec (style, proportions, naming "
            "convention, capture/retarget/ragdoll options). Any LLM (incl. codex) or "
            "an artist can author the same JSON; the tool validates it."
        ),
    },
    "hyper3d": {
        "role": "Text/image-to-3D generation of a character mesh (Rodin/Hyper3D).",
        "bound_to_adapter": False,
        "probing": (
            "A host-neutral 'dcc-ai-hyper3d' skill (create_rodin_task / "
            "download_assets) and HYPER3D_API_KEY exist, but it is NOT registered as "
            "a running MCP server in this adapter's config; cloud generation is an "
            "out-of-band step. Its AssetDescriptor output is consumed by the existing "
            "houdini_import_to_scene__import_to_scene tool."
        ),
        "equivalent": "import_generated_character",
        "equivalent_detail": (
            "Ingest a hyper3d AssetDescriptor local_path or any generated mesh "
            "(FBX/OBJ/ABC/bgeo/USD) into a SOP network, normalize units/height and "
            "report a rig-ready contract; a procedural proxy mesh is the offline "
            "fallback when no service/file is available."
        ),
    },
}

# Gaps that this change fills and enhancements to the existing pipeline.
GAPS_AND_ENHANCEMENTS = [
    {
        "id": "G1",
        "kind": "gap",
        "stage": 1,
        "problem": "No in-Houdini character-design contract; codex output is free-form.",
        "resolution": "design_character emits and validates a structured design spec.",
    },
    {
        "id": "G2",
        "kind": "gap",
        "stage": 2,
        "problem": "No adapter tool ingests a hyper3d/Rodin generated character mesh.",
        "resolution": "import_generated_character imports + normalizes the mesh, or a proxy.",
    },
    {
        "id": "G3",
        "kind": "gap",
        "stage": 3,
        "problem": "create_rig is a generic chain; create_insect_rig is a honeybee. No humanoid biped template.",
        "resolution": "create_biped_template builds a standard 22-joint biped in 5 naming conventions.",
    },
    {
        "id": "G4",
        "kind": "gap",
        "stage": 4,
        "problem": "Retarget assumed same joint names (auto map); differently-named bipeds could not map.",
        "resolution": "biped_joint_map + configure_biped_retarget add explicit cross-convention mapping.",
    },
    {
        "id": "G5",
        "kind": "gap",
        "stage": 5,
        "problem": "No rig-inversion capability (world->local transform inversion).",
        "resolution": "invert_rig computes parent-relative local transforms from a posed skeleton.",
    },
    {
        "id": "G6",
        "kind": "gap",
        "stage": 7,
        "problem": "No character ragdoll setup; simulation skill offers only generic RBD blocks.",
        "resolution": "build_ragdoll builds proxy colliders + constraint network + RBD solver.",
    },
    {
        "id": "G7",
        "kind": "gap",
        "stage": 8,
        "problem": "No APEX FBX biped template export path.",
        "resolution": "build_apex_fbx_biped packs an APEX biped character and reports the FBX export.",
    },
    {
        "id": "E1",
        "kind": "enhancement",
        "stage": 6,
        "problem": "build_retarget_motion_mixer only auto-mapped identical joint names.",
        "resolution": "Added optional explicit joint_map / naming_convention support (backward compatible).",
    },
    {
        "id": "E2",
        "kind": "enhancement",
        "stage": 4,
        "problem": "No reusable biped naming map shared between retarget, rig inversion and APEX pack.",
        "resolution": "_character_common + biped_joint_map centralize conventions and FK-inversion math.",
    },
]

WORKFLOW_STAGES = [
    {
        "order": 1,
        "id": "design",
        "name": "Character design (codex)",
        "goal": "Produce a validated, structured character design spec.",
        "external": "codex",
        "tools": ["design_character"],
        "inputs": ["prompt/style", "target_height", "naming_convention"],
        "outputs": ["character_design_spec (JSON)"],
        "status": "equivalent_alternative",
    },
    {
        "order": 2,
        "id": "generate",
        "name": "Character generation (hyper3d)",
        "goal": "Obtain a rig-ready character mesh in a SOP network.",
        "external": "hyper3d",
        "tools": [
            "import_generated_character",
            "houdini_import_to_scene__import_to_scene",
            "houdini_interchange__import_geometry",
        ],
        "inputs": ["generated mesh file (FBX/OBJ/ABC/bgeo) or proxy"],
        "outputs": ["mesh SOP", "rigging contract"],
        "status": "equivalent_alternative",
    },
    {
        "order": 3,
        "id": "biped_template",
        "name": "Biped template",
        "goal": "Create a standard humanoid KineFX skeleton with stable joint names.",
        "external": None,
        "tools": ["create_biped_template"],
        "inputs": ["character_design_spec"],
        "outputs": ["biped skeleton SOP", "joint map"],
        "status": "implemented",
    },
    {
        "order": 4,
        "id": "retarget",
        "name": "Biped motion retarget",
        "goal": "Map source mocap skeleton onto the biped target (Rig Match Pose -> Map Points -> FBIK).",
        "external": None,
        "tools": ["biped_joint_map", "configure_biped_retarget", "build_retarget_motion_mixer"],
        "inputs": ["source skeleton", "biped skeleton", "joint map"],
        "outputs": ["retargeted animated skeleton"],
        "status": "implemented",
    },
    {
        "order": 5,
        "id": "rig_inversion",
        "name": "Rig inversion",
        "goal": "Recover parent-relative local transforms from a world-posed skeleton.",
        "external": None,
        "tools": ["invert_rig", "_character_common.compute_local_transforms"],
        "inputs": ["posed skeleton (world transforms)", "parent indices"],
        "outputs": ["local transforms", "inverted rig skeleton"],
        "status": "implemented",
    },
    {
        "order": 6,
        "id": "motion_mixer_fbik",
        "name": "Motion Mixer full body IK",
        "goal": "Blend multiple retargeted clips on an APEX character with Full Body IK.",
        "external": None,
        "tools": ["build_retarget_motion_mixer"],
        "inputs": ["2+ animated source skeletons", "APEX character"],
        "outputs": ["Motion Mixer", "Fetch", "APEX scene"],
        "status": "enhanced",
    },
    {
        "order": 7,
        "id": "ragdoll",
        "name": "Ragdoll",
        "goal": "Set up physics-driven ragdoll from the biped skeleton.",
        "external": None,
        "tools": ["build_ragdoll", "houdini_simulation__create_constraint_network"],
        "inputs": ["biped skeleton", "proxy/collider settings"],
        "outputs": ["DOP RBD network", "constraint network"],
        "status": "implemented",
    },
    {
        "order": 8,
        "id": "apex_fbx_biped",
        "name": "KineFx APEX FBX biped template",
        "goal": "Pack an APEX biped character and export an FBX biped template.",
        "external": None,
        "tools": ["build_apex_fbx_biped", "houdini_interchange__export_fbx"],
        "inputs": ["biped skeleton", "skinned mesh"],
        "outputs": ["APEX character", "FBX file"],
        "status": "implemented",
    },
]

ACCEPTANCE_CRITERIA = [
    "All eight stages have a typed tool or a documented equivalent alternative.",
    "External (codex/hyper3d) steps degrade to offline equivalents with recorded evidence.",
    "Biped template joint names are stable and map across 5 naming conventions.",
    "Retarget supports explicit cross-convention joint maps (not only auto map).",
    "Rig inversion is verifiable with pure linear-algebra unit tests (no Houdini).",
    "Every tool has mock-hou unit tests, a tools.yaml contract and passes skill lint.",
    "Final visual/cook acceptance on a licensed Houdini 20.5+/22 is owned by QA/release.",
]


def plan_character_workflow(
    codex_available: Optional[bool] = None,
    hyper3d_available: Optional[bool] = None,
) -> dict:
    """Return the full workflow design, gaps, enhancements and external status.

    Args:
        codex_available: Optional override from an orchestrator's probe. ``None``
            (default) leaves the adapter's documented default (not bound).
        hyper3d_available: Optional override from an orchestrator's probe.
    """
    external = {name: dict(info) for name, info in EXTERNAL_CAPABILITIES.items()}
    if codex_available is not None:
        external["codex"]["bound_to_adapter"] = bool(codex_available)
    if hyper3d_available is not None:
        external["hyper3d"]["bound_to_adapter"] = bool(hyper3d_available)

    return skill_success(
        "Houdini character-animation workflow plan",
        schema="dcc-mcp-houdini.character-workflow/v1",
        stage_count=len(WORKFLOW_STAGES),
        stages=WORKFLOW_STAGES,
        gaps_and_enhancements=GAPS_AND_ENHANCEMENTS,
        external_capabilities=external,
        acceptance_criteria=ACCEPTANCE_CRITERIA,
        design_doc="docs/guide/houdini-character-animation-workflow.md",
        tool_chain=[tool for stage in WORKFLOW_STAGES for tool in stage["tools"]],
    )


@skill_entry
def main(**kwargs) -> dict:
    return plan_character_workflow(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
