"""Publish an HDA instance into its definition and advance its version."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def update_hda_definition(
    node_path: str,
    version: str,
    update_contents: bool = True,
    match_current: bool = True,
) -> dict:
    """Save unlocked contents, set definition metadata version, and optionally lock."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        if not isinstance(version, str) or not version.strip():
            raise ValueError("version must be a non-empty string")
        version = version.strip()
        node = hou.node(node_path)
        if node is None:
            raise ValueError("Houdini node not found: {}".format(node_path))
        definition = node.type().definition()
        if definition is None:
            raise ValueError("Node is not a Houdini Digital Asset: {}".format(node_path))

        old_version = definition.version()
        was_matched = node.matchesCurrentDefinition()
        contents_updated = bool(update_contents and not was_matched)
        if contents_updated:
            definition.updateFromNode(node)
        definition.setVersion(version)
        if match_current and not was_matched:
            node.matchCurrentDefinition()

        return skill_success(
            "Updated HDA definition",
            node_path=node.path(),
            node_type_name=definition.nodeTypeName(),
            library_path=definition.libraryFilePath(),
            old_version=old_version,
            version=version,
            contents_updated=contents_updated,
            matched_current_definition=node.matchesCurrentDefinition(),
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to update HDA definition")


@skill_entry
def main(**kwargs) -> dict:
    return update_hda_definition(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
