"""Remove a single HDA definition from its library (HDADefinition.destroy)."""

from __future__ import annotations

import os
from typing import Any, Optional

from _hda_auto_common import definition_summary, find_node_type, node_type_instances
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def _normalize(path: str) -> str:
    """Best-effort canonical form for comparing library paths across platforms."""
    return os.path.normcase(os.path.normpath(os.path.expanduser(path)))


def _resolve_definition(hou: Any, node_type_name: str, hda_file: Optional[str], dry_run: bool = False):
    """Return (definition, node_type) for removal, or (None, None) when absent.

    When *hda_file* is provided the library is installed first so that
    ``HDADefinition.destroy`` operates on a session-backed definition that
    rewrites that exact file. The active definition's library path is then
    verified to match the requested file, refusing ambiguous targets where a
    same-named definition from a different library is currently preferred.

    For a dry run the library is never installed: installing would mutate the
    loaded-library list and could switch the active/current definition, which a
    preview must not do.
    """
    if hda_file:
        if not dry_run:
            hou.hda.installFile(hda_file)
        node_type = find_node_type(hou, node_type_name)
        if node_type is None:
            return None, None
        definition = node_type.definition()
        if definition is None:
            return None, None
        library_path = definition.libraryFilePath()
        if library_path and _normalize(library_path) != _normalize(hda_file):
            raise ValueError(
                "Active definition of {!r} belongs to a different library ({!r}); refusing to remove from {!r}.".format(
                    node_type_name, library_path, hda_file
                )
            )
        return definition, node_type

    node_type = find_node_type(hou, node_type_name)
    if node_type is None:
        return None, None
    return node_type.definition(), node_type


def remove_hda_definition(
    node_type_name: str,
    hda_file: Optional[str] = None,
    allow_orphan_instances: bool = False,
    dry_run: bool = False,
) -> dict:
    """Remove a single HDA definition via ``HDADefinition.destroy``.

    This permanently deletes the definition from its library and rewrites the
    library file on disk (or the current HIP when the definition is embedded);
    existing instances are left as incomplete assets. Use ``uninstall_hda_file``
    for a reversible, session-only removal of an entire library instead.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        definition, node_type = _resolve_definition(hou, node_type_name, hda_file, dry_run=dry_run)
        if definition is None:
            return skill_error(
                "Definition not found",
                "No HDA definition for {!r}".format(node_type_name),
                node_type_name=node_type_name,
                hda_file=hda_file,
            )

        instance_paths = node_type_instances(node_type) if node_type is not None else None

        # Fail closed: an unknown instance count (enumeration failed/unavailable)
        # must never be treated as zero instances for a destructive removal.
        if instance_paths is None and not allow_orphan_instances:
            return skill_error(
                "Instance state unknown",
                "Could not reliably enumerate instances of {!r}; refusing to remove "
                "(fail-closed). Retry, or pass allow_orphan_instances=true to override.".format(node_type_name),
                node_type_name=node_type_name,
                hda_file=hda_file,
                instance_count=None,
                instances_unknown=True,
            )

        if instance_paths and not allow_orphan_instances:
            return skill_error(
                "Definition has live instances",
                "Refusing to orphan {} instance(s) of {!r}; pass allow_orphan_instances=true to proceed anyway.".format(
                    len(instance_paths), node_type_name
                ),
                node_type_name=node_type_name,
                hda_file=hda_file,
                instance_count=len(instance_paths),
                instance_paths=instance_paths,
            )

        known_paths = instance_paths or []
        summary = definition_summary(definition)
        summary["instance_count"] = None if instance_paths is None else len(known_paths)
        summary["instance_paths"] = known_paths
        summary["instances_unknown"] = instance_paths is None

        if dry_run:
            summary["dry_run"] = True
            return skill_success(
                "Dry run: HDA definition would be removed",
                **summary,
            )

        category = None
        if node_type is not None:
            try:
                category = node_type.category()
            except Exception:  # noqa: BLE001
                category = None

        definition.destroy()

        unregistered = False
        if category is not None:
            try:
                unregistered = find_node_type(hou, node_type_name) is None
            except Exception:  # noqa: BLE001
                unregistered = True

        summary["dry_run"] = False
        summary["instances_orphaned"] = len(known_paths)
        summary["node_type_unregistered"] = unregistered
        return skill_success("Removed HDA definition", **summary)
    except Exception as exc:
        return skill_exception(exc, message="Failed to remove HDA definition")


@skill_entry
def main(**kwargs) -> dict:
    return remove_hda_definition(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
