"""Inspect an HDA definition: inputs, parm templates, sections, version, help."""

from __future__ import annotations

from typing import Optional

from _hda_auto_common import definition_summary, find_node_type  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def _find_definition(hou, node_type_name, hda_file):
    if hda_file:
        for defn in hou.hda.definitionsInFile(hda_file):
            if not node_type_name or defn.nodeTypeName() == node_type_name:
                return defn
        return None
    node_type = find_node_type(hou, node_type_name)
    if node_type is None:
        return None
    return node_type.definition()


def inspect_hda_definition(
    node_type_name: str,
    hda_file: Optional[str] = None,
) -> dict:
    """Return a structured summary of an HDA definition."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        if hda_file:
            hou.hda.installFile(hda_file)
        definition = _find_definition(hou, node_type_name, hda_file)
        if definition is None:
            return skill_error(
                "Definition not found",
                "No HDA definition for {!r}".format(node_type_name),
                hda_file=hda_file,
            )
        summary = definition_summary(definition)
        node_type = definition.nodeType() if hasattr(definition, "nodeType") else None
        if node_type is not None:
            try:
                summary["max_inputs"] = node_type.maxNumInputs()
            except Exception:  # noqa: BLE001
                summary["max_inputs"] = None
            try:
                summary["input_labels"] = list(node_type.inputLabels())
            except Exception:  # noqa: BLE001
                summary["input_labels"] = []
            try:
                templates = node_type.parmTemplateGroup().entries()
                summary["parm_templates"] = [t.name() for t in templates]
            except Exception:  # noqa: BLE001
                summary["parm_templates"] = []
        return skill_success("Inspected HDA definition", **summary)
    except Exception as exc:
        return skill_exception(exc, message="Failed to inspect HDA definition")


@skill_entry
def main(**kwargs) -> dict:
    return inspect_hda_definition(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
