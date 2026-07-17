"""Promote internal parameter tuples onto a reusable HDA interface."""

from __future__ import annotations

import re
from typing import Any, Dict, List

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

_PARM_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def promote_hda_parameters(node_path: str, promotions: List[Dict[str, Any]]) -> dict:
    """Clone internal parm templates onto *node_path* and link the sources."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        node = hou.node(node_path)
        if node is None:
            raise ValueError("Houdini node not found: {}".format(node_path))
        if not promotions:
            raise ValueError("promotions must not be empty")

        definition = node.type().definition()
        if definition is not None and node.matchesCurrentDefinition():
            raise ValueError("HDA must be unlocked before promoting internal parameters")
        interface_owner = definition or node
        group = interface_owner.parmTemplateGroup()

        prepared = []
        names = set()
        parent_prefix = node.path().rstrip("/") + "/"
        for promotion in promotions:
            source_path = promotion.get("source_node_path")
            source_parm_name = promotion.get("source_parm")
            target_name = promotion.get("name") or source_parm_name
            if not _PARM_NAME.match(target_name or ""):
                raise ValueError("Invalid promoted parameter name: {!r}".format(target_name))
            if target_name in names or group.find(target_name) is not None:
                raise ValueError("Promoted parameter already exists: {}".format(target_name))
            names.add(target_name)

            source = hou.node(source_path) if source_path else None
            if source is None:
                raise ValueError("Source node not found: {}".format(source_path))
            if not source.path().startswith(parent_prefix):
                raise ValueError("Source node must be inside the HDA node: {}".format(source.path()))
            source_tuple = source.parmTuple(source_parm_name)
            if source_tuple is None:
                raise ValueError("Source parameter tuple not found: {}/{}".format(source.path(), source_parm_name))

            template = source_tuple.parmTemplate().clone()
            label = promotion.get("label") or template.label()
            template.setName(target_name)
            template.setLabel(label)
            prepared.append((source, source_tuple, source_parm_name, target_name, label, template))

        for _source, _source_tuple, _source_name, _target_name, _label, template in prepared:
            group.append(template)
        interface_owner.setParmTemplateGroup(group)

        promoted = []
        for source, source_tuple, source_parm_name, target_name, label, _template in prepared:
            values = source_tuple.eval()
            target_tuple = node.parmTuple(target_name)
            if target_tuple is None:
                raise RuntimeError("Promoted parameter tuple was not created: {}".format(target_name))
            target_tuple.set(values)
            source_tuple.set(target_tuple, language=hou.exprLanguage.Hscript)
            promoted.append(
                {
                    "name": target_name,
                    "label": label,
                    "source": "{}/{}".format(source.path(), source_parm_name),
                    "component_count": len(values),
                }
            )

        return skill_success(
            "Promoted HDA parameters",
            node_path=node.path(),
            interface_owner="definition" if definition is not None else "node",
            promoted=promoted,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to promote HDA parameters")


@skill_entry
def main(**kwargs) -> dict:
    return promote_hda_parameters(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
