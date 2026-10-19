"""Remove a single HDA definition from its library (HDADefinition.destroy)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from _hda_auto_common import definition_summary, find_node_type, node_type_instances
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success

# Library load classification. ``_UNKNOWN`` is deliberately distinct from
# ``_NOT_LOADED``: a rollback that uninstalls a library must only ever be
# authorized for a library that was provably NOT loaded before this call. When
# the pre-existing load state cannot be determined, uninstalling could remove a
# library this call did not install, so the tool fails safe and leaves it alone.
_LOADED = "loaded"
_NOT_LOADED = "not_loaded"
_UNKNOWN = "unknown"


def _normalize(path: str) -> str:
    """Best-effort canonical form for comparing library paths across platforms.

    Matches ``uninstall_hda_file._normalize`` so both tools agree whether two
    path strings denote the same loaded library: expand ``~``, resolve to an
    absolute path (following symlinks so a symlinked request matches the real
    loaded file), then apply platform case normalization.
    """
    try:
        expanded = os.path.expanduser(str(path))
    except (OSError, RuntimeError):
        expanded = str(path)
    try:
        resolved = str(Path(expanded).resolve())
    except (OSError, RuntimeError):
        resolved = os.path.normpath(expanded)
    return os.path.normcase(resolved)


def _expand_hou_vars(hou: Any, path: Any) -> str:
    """Expand Houdini ``$VAR`` tokens (``$HIP``, ``$HOUDINI_USER_PREF_DIR``, ...).

    Houdini reports ``loadedFiles()`` / ``libraryFilePath()`` with variables
    already expanded to absolute host paths, so a request path still containing
    ``$VAR`` must be expanded before comparison or it can never match a loaded
    entry. Expansion is best-effort: when ``hou`` is unavailable or a mock, or
    when expansion fails or returns a non-string, the input is returned unchanged.
    """
    text = str(path)
    expand = getattr(hou, "expandString", None) if hou is not None else None
    if callable(expand):
        try:
            expanded = expand(text)
        except Exception:  # noqa: BLE001 - expansion is best-effort
            return text
        if isinstance(expanded, str):
            return expanded
    return text


def _canonical(hou: Any, path: Any) -> str:
    """Canonical comparison form aligned with ``loadedFiles()`` reporting.

    Expands Houdini variables and ``~``, then resolves to an absolute path
    (following symlinks) before platform case normalization, so ``$VAR``/
    relative/symlink request forms match the canonical entry Houdini reports.
    """
    return _normalize(_expand_hou_vars(hou, path))


def _library_load_state(hou: Any, hda_file: str) -> str:
    """Classify whether *hda_file* is already loaded as one of three states.

    Returns ``"loaded"`` only on a positive canonical match against the readable
    loaded-library list, ``"not_loaded"`` only when the whole list was readable
    and contained no match, and ``"unknown"`` whenever the list (or any entry)
    could not be reliably read. ``"unknown"`` must never authorize a destructive
    rollback: we cannot prove we installed the library, so we must not uninstall
    it (fail safe).
    """
    target = _canonical(hou, hda_file)
    try:
        loaded = hou.hda.loadedFiles()
    except Exception:  # noqa: BLE001 - cannot prove anything about load state
        return _UNKNOWN
    if loaded is None:
        return _UNKNOWN
    try:
        entries = list(loaded)
    except Exception:  # noqa: BLE001 - not iterable; cannot prove not loaded
        return _UNKNOWN
    for entry in entries:
        try:
            if _canonical(hou, entry) == target:
                return _LOADED
        except Exception:  # noqa: BLE001 - an unreadable entry might be the target
            return _UNKNOWN
    return _NOT_LOADED


def _rollback_target(hou: Any, hda_file: str) -> str:
    """Return the string to pass to ``uninstallFile`` when rolling back.

    Prefers the canonical ``loadedFiles()`` entry that matches *hda_file*, so a
    rollback targets exactly what Houdini registered (robust when the request
    used ``$VAR``/relative/symlink form). Falls back to the request path.
    """
    target = _canonical(hou, hda_file)
    try:
        loaded = hou.hda.loadedFiles() or []
        for entry in loaded:
            if _canonical(hou, entry) == target:
                return str(entry)
    except Exception:  # noqa: BLE001 - canonical lookup is best-effort
        pass
    return hda_file


def _resolve_definition(hou: Any, node_type_name: str, hda_file: Optional[str]):
    """Return (definition, node_type) for removal, or (None, None) when absent.

    When *hda_file* is provided, the active definition's library path is verified
    to match the requested file, refusing ambiguous targets where a same-named
    definition from a different library is currently preferred. The comparison
    uses the same canonical form as ``loadedFiles()`` so ``$VAR``/relative/
    symlink request forms match the active library. The caller is responsible for
    installing *hda_file* beforehand (so ``HDADefinition.destroy`` rewrites that
    exact file) and for rolling that install back when the removal does not
    proceed.
    """
    if hda_file:
        node_type = find_node_type(hou, node_type_name)
        if node_type is None:
            return None, None
        definition = node_type.definition()
        if definition is None:
            return None, None
        library_path = definition.libraryFilePath()
        if library_path and _canonical(hou, library_path) != _canonical(hou, hda_file):
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

    When *hda_file* is given the library is installed first (never for a dry run)
    so ``destroy`` rewrites that exact file. If the removal is then refused or
    fails for any reason, an install performed by this call is rolled back,
    leaving the session's loaded-library list exactly as it was. A rollback is
    authorized only when the library was provably NOT loaded before this call: a
    library already loaded beforehand is never uninstalled, and when the load
    state is indeterminate (e.g. ``loadedFiles()`` fails) the tool fails safe and
    leaves the library alone rather than uninstalling a load it cannot prove it
    created. If the rollback itself fails, that is reported on the result context
    (``rollback_failed``) instead of being silently swallowed.
    """
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return skill_error("Houdini not available", "hou could not be imported")

    # Install the target library only for a real removal (never for a dry run),
    # and remember whether this call added it so a refused/failed removal can
    # roll it back without disturbing libraries that were already loaded.
    install_for_removal = bool(hda_file) and not dry_run
    installed_by_us = False
    destroyed = False
    result: dict = {}
    try:
        if install_for_removal:
            load_state = _library_load_state(hou, hda_file)
            hou.hda.installFile(hda_file)
            # Authorize rollback only when the library was provably not loaded
            # before this call. A previously-loaded library must be preserved;
            # an unknown load state must NOT authorize a rollback, because we
            # cannot prove this call installed it and uninstalling could remove a
            # pre-existing load.
            installed_by_us = load_state == _NOT_LOADED

        definition, node_type = _resolve_definition(hou, node_type_name, hda_file)
        if definition is None:
            result = skill_error(
                "Definition not found",
                "No HDA definition for {!r}".format(node_type_name),
                node_type_name=node_type_name,
                hda_file=hda_file,
            )
            return result

        instance_paths = node_type_instances(node_type) if node_type is not None else None

        # Fail closed: an unknown instance count (enumeration failed/unavailable)
        # must never be treated as zero instances for a destructive removal.
        if instance_paths is None and not allow_orphan_instances:
            result = skill_error(
                "Instance state unknown",
                "Could not reliably enumerate instances of {!r}; refusing to remove "
                "(fail-closed). Retry, or pass allow_orphan_instances=true to override.".format(node_type_name),
                node_type_name=node_type_name,
                hda_file=hda_file,
                instance_count=None,
                instances_unknown=True,
            )
            return result

        if instance_paths and not allow_orphan_instances:
            result = skill_error(
                "Definition has live instances",
                "Refusing to orphan {} instance(s) of {!r}; pass allow_orphan_instances=true to proceed anyway.".format(
                    len(instance_paths), node_type_name
                ),
                node_type_name=node_type_name,
                hda_file=hda_file,
                instance_count=len(instance_paths),
                instance_paths=instance_paths,
            )
            return result

        known_paths = instance_paths or []
        summary = definition_summary(definition)
        summary["instance_count"] = None if instance_paths is None else len(known_paths)
        summary["instance_paths"] = known_paths
        summary["instances_unknown"] = instance_paths is None

        if dry_run:
            summary["dry_run"] = True
            result = skill_success(
                "Dry run: HDA definition would be removed",
                **summary,
            )
            return result

        category = None
        if node_type is not None:
            try:
                category = node_type.category()
            except Exception:  # noqa: BLE001
                category = None

        definition.destroy()
        destroyed = True

        unregistered = False
        if category is not None:
            try:
                unregistered = find_node_type(hou, node_type_name) is None
            except Exception:  # noqa: BLE001
                unregistered = True

        summary["dry_run"] = False
        summary["instances_orphaned"] = len(known_paths)
        summary["node_type_unregistered"] = unregistered
        result = skill_success("Removed HDA definition", **summary)
        return result
    except Exception as exc:
        result = skill_exception(exc, message="Failed to remove HDA definition")
        return result
    finally:
        # Roll back only an install this call performed, and only when destroy()
        # was not reached: a refused or failed removal must not leak a newly
        # installed library, while a library that was already loaded stays put.
        # Because ``return result`` holds a reference to the same dict, mutating
        # it here is visible to the caller even though the return already ran.
        if installed_by_us and not destroyed:
            rollback_path = _rollback_target(hou, hda_file)
            try:
                hou.hda.uninstallFile(rollback_path)
            except Exception as exc:  # noqa: BLE001 - surface rollback failure, do not mask
                if isinstance(result, dict) and result:
                    context = result.setdefault("context", {})
                    if isinstance(context, dict):
                        context["rollback_failed"] = True
                        context["rollback_error"] = "{}: {}".format(type(exc).__name__, exc)
                        context["rolled_back_library"] = hda_file


@skill_entry
def main(**kwargs) -> dict:
    return remove_hda_definition(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
