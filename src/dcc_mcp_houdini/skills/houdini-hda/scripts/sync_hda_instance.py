"""Synchronize an HDA instance with a loaded definition and version handler."""

from __future__ import annotations

import os
from typing import Optional

from _hda_common import validate_hda_path  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def _same_library(a: str, b: str) -> bool:
    """Compare two HDA library paths case-/separator-insensitively."""
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def _version_key(version: str) -> list:
    """Return a Python 3-safe sort key for a dotted HDA version string."""
    key = []
    for token in str(version).split("."):
        try:
            key.append((1, int(token), ""))
        except ValueError:
            key.append((0, 0, token))
    return key


def _library_definition_version(hou, file_path: str, node_type_name: str, node_category) -> Optional[str]:
    """Return the version *file_path* provides for *node_type_name*, or ``None``.

    A single library usually carries one definition per operator, but it may
    hold several versions. Prefer the definition Houdini currently resolves the
    operator to (after the forced re-install this is the one
    ``matchCurrentDefinition`` will bind to), then the preferred definition,
    then the highest version.
    """
    try:
        definitions = [d for d in hou.hda.definitionsInFile(file_path) if d.nodeTypeName() == node_type_name]
    except Exception:  # noqa: BLE001 - a malformed library must not mask the sync result
        return None
    if not definitions:
        return None
    if len(definitions) == 1:
        return definitions[0].version()

    try:
        current_type = hou.nodeType(node_category, node_type_name)
        current_def = current_type.definition() if current_type is not None else None
    except Exception:  # noqa: BLE001
        current_def = None
    if current_def is not None:
        try:
            if _same_library(str(current_def.libraryFilePath()), file_path):
                return current_def.version()
        except Exception:  # noqa: BLE001
            pass
    for defn in definitions:
        try:
            if defn.isPreferred():
                return defn.version()
        except Exception:  # noqa: BLE001
            continue
    return max(definitions, key=lambda d: _version_key(d.version())).version()


def sync_hda_instance(
    node_path: str,
    from_version: str,
    hda_file: Optional[str] = None,
    match_current: bool = True,
    sync_delayed: bool = True,
) -> dict:
    """Reload an optional library and run the HDA version synchronization hook."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    try:
        if not isinstance(from_version, str) or not from_version.strip():
            raise ValueError("from_version must be a non-empty string")
        from_version = from_version.strip()

        node = hou.node(node_path)
        if node is None:
            raise ValueError("Houdini node not found: {}".format(node_path))
        node_type = node.type()
        if node_type is None:
            raise ValueError("Houdini node has no node type: {}".format(node_path))
        node_type_name = node_type.name()

        target_version = None
        if hda_file:
            path = validate_hda_path(hda_file, must_exist=True)
            # Promote the target library to current. Houdini makes the most
            # recently installed definition current (not the highest version),
            # and re-installing/reloading an already-loaded file is a no-op that
            # leaves an older, last-installed definition in charge. Passing
            # force_use_assets=True unconditionally re-promotes this file's
            # definitions (validated on Houdini 19.5 / 20.5 / 21.0), so the
            # matchCurrentDefinition() call below has the intended target to
            # bind to.
            hou.hda.installFile(str(path), force_use_assets=True)
            target_version = _library_definition_version(hou, str(path), node_type_name, node_type.category())

        definition = node.type().definition()
        if definition is None:
            raise ValueError("Node is not a Houdini Digital Asset: {}".format(node_path))

        delayed = bool(node.isDelayedDefinition())
        if sync_delayed and delayed:
            node.syncDelayedDefinition()
        if match_current and not node.matchesCurrentDefinition():
            node.matchCurrentDefinition()
        node.syncNodeVersionIfNeeded(from_version)

        actual_definition = node.type().definition()
        actual_version = actual_definition.version() if actual_definition is not None else None

        # Post-check: never report success when the host did not actually reach
        # the requested target version. Without this, a silent no-op upgrade
        # returned success:true with the stale version (see PIP-4984).
        if target_version is not None and actual_version != target_version:
            return skill_error(
                "HDA instance was not upgraded to the target version",
                "target version {!r} was not reached (host definition version is {!r})".format(
                    target_version, actual_version
                ),
                node_path=node.path(),
                node_type_name=(actual_definition.nodeTypeName() if actual_definition is not None else node_type_name),
                library_path=(actual_definition.libraryFilePath() if actual_definition is not None else ""),
                from_version=from_version,
                target_version=target_version,
                version=actual_version,
                delayed_definition_synced=bool(sync_delayed and delayed),
                matched_current_definition=node.matchesCurrentDefinition(),
            )

        context = {
            "node_path": node.path(),
            "node_type_name": actual_definition.nodeTypeName(),
            "library_path": actual_definition.libraryFilePath(),
            "from_version": from_version,
            "version": actual_version,
            "delayed_definition_synced": bool(sync_delayed and delayed),
            "matched_current_definition": node.matchesCurrentDefinition(),
        }
        if target_version is not None:
            context["target_version"] = target_version
        return skill_success("Synchronized HDA instance", **context)
    except Exception as exc:
        return skill_exception(exc, message="Failed to synchronize HDA instance")


@skill_entry
def main(**kwargs) -> dict:
    return sync_hda_instance(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
