"""Validate a reusable HDA definition, interface, dependencies, and instantiation."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _hda_common import hou_import_error, validate_hda_path

_MANIFEST_SECTION = "dcc_mcp/manifest.json"


def _path_key(value: Any) -> str:
    return os.path.normcase(os.path.abspath(os.path.expanduser(str(value))))


def _diagnostic(items: List[dict], code: str, message: str, severity: str = "error", **context: Any) -> None:
    entry = {"code": code, "severity": severity, "message": message}
    if context:
        entry["context"] = context
    items.append(entry)


def _definition_from_session(hou: Any, node_type_name: str) -> Optional[Any]:
    for category in hou.nodeTypeCategories().values():
        try:
            node_type = category.nodeTypes().get(node_type_name)
        except Exception:  # noqa: BLE001
            node_type = None
        if node_type is not None:
            try:
                return node_type.definition()
            except Exception:  # noqa: BLE001
                return None
    return None


def _template_type(template: Any) -> str:
    try:
        return str(template.type().name()).lower()
    except Exception:  # noqa: BLE001
        return type(template).__name__.replace("ParmTemplate", "").lower()


def _interface_templates(entries: Sequence[Any], diagnostics: List[dict], path: str = "") -> List[dict]:
    templates = []
    for template in entries:
        name = template.name()
        kind = _template_type(template)
        qualified = "{}/{}".format(path, name).strip("/")
        summary = {"name": name, "label": template.label(), "type": kind, "path": qualified}
        try:
            summary["components"] = int(template.numComponents())
        except Exception:  # noqa: BLE001
            summary["components"] = 0 if kind == "folder" else 1
        templates.append(summary)
        for attr in ("scriptCallback", "itemGeneratorScript"):
            callback = getattr(template, attr, None)
            if callable(callback):
                try:
                    value = callback()
                except Exception:  # noqa: BLE001
                    value = ""
                if isinstance(value, str) and value.strip():
                    _diagnostic(
                        diagnostics,
                        "unsafe_callback",
                        "Executable parameter callbacks are not allowed",
                        parameter=name,
                        callback_kind=attr,
                    )
        children = getattr(template, "parmTemplates", None)
        if kind == "folder" and callable(children):
            templates.extend(_interface_templates(children(), diagnostics, qualified))
    return templates


def _section_contents(section: Any) -> bytes:
    contents = section.contents()
    return contents.encode("utf-8") if isinstance(contents, str) else bytes(contents)


def validate_hda_contract(
    node_type_name: str,
    hda_file: Optional[str] = None,
    expected_version: Optional[str] = None,
    required_parameters: Optional[Sequence[Dict[str, str]]] = None,
    required_sections: Optional[Sequence[str]] = None,
    require_namespace: bool = True,
    require_type_version: bool = True,
    require_manifest: bool = False,
    check_dependencies: bool = True,
    instantiate: bool = True,
    parent_path: str = "/obj",
) -> dict:
    """Return structured diagnostics for a namespaced, versioned HDA contract."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return hou_import_error()

    installed_for_validation = False
    library_path = None
    diagnostics: List[dict] = []
    try:
        node_type_name = str(node_type_name).strip()
        if not node_type_name:
            raise ValueError("node_type_name must not be empty")
        if hda_file:
            library_path = validate_hda_path(hda_file, must_exist=True)
            definitions = list(hou.hda.definitionsInFile(str(library_path)))
            definition = next((item for item in definitions if item.nodeTypeName() == node_type_name), None)
        else:
            definition = _definition_from_session(hou, node_type_name)
        if definition is None:
            _diagnostic(
                diagnostics, "definition_not_found", "HDA definition was not found", node_type_name=node_type_name
            )
            return skill_success(
                "HDA contract is invalid",
                valid=False,
                node_type_name=node_type_name,
                hda_file=str(library_path) if library_path else None,
                diagnostics=diagnostics,
                error_count=1,
                warning_count=0,
                interface=[],
                instantiable=False if instantiate else None,
            )

        if library_path is not None:
            loaded = {_path_key(path) for path in hou.hda.loadedFiles()}
            if _path_key(library_path) not in loaded:
                hou.hda.installFile(str(library_path))
                installed_for_validation = True
                definition = next(
                    item
                    for item in hou.hda.definitionsInFile(str(library_path))
                    if item.nodeTypeName() == node_type_name
                )

        actual_name = definition.nodeTypeName()
        actual_version = definition.version() or ""
        try:
            _scope, namespace, asset_name, type_version = hou.hda.componentsFromFullNodeTypeName(actual_name)
        except Exception as exc:  # noqa: BLE001
            namespace, asset_name, type_version = "", actual_name, ""
            _diagnostic(diagnostics, "invalid_node_type_name", str(exc), node_type_name=actual_name)
        if require_namespace and not namespace:
            _diagnostic(diagnostics, "missing_namespace", "HDA node type name has no namespace")
        if require_type_version and not type_version:
            _diagnostic(diagnostics, "missing_type_version", "HDA node type name has no version component")
        if type_version and actual_version and type_version != actual_version:
            _diagnostic(
                diagnostics,
                "version_mismatch",
                "HDA metadata version does not match its node type version",
                type_version=type_version,
                definition_version=actual_version,
            )
        if expected_version is not None and actual_version != str(expected_version):
            _diagnostic(
                diagnostics,
                "unexpected_version",
                "HDA definition version does not match the expected version",
                expected=str(expected_version),
                actual=actual_version,
            )

        sections = definition.sections()
        section_names = sorted(sections)
        for section_name in required_sections or []:
            if section_name not in sections:
                _diagnostic(
                    diagnostics,
                    "missing_section",
                    "Required HDA section is missing",
                    section=section_name,
                )

        interface = _interface_templates(definition.parmTemplateGroup().entries(), diagnostics)
        by_name = {}
        for template in interface:
            if template["name"] in by_name:
                _diagnostic(
                    diagnostics,
                    "duplicate_parameter",
                    "Parameter name occurs more than once",
                    parameter=template["name"],
                )
            by_name[template["name"]] = template
        for requirement in required_parameters or []:
            name = str(requirement.get("name", ""))
            expected_type = str(requirement.get("type", "")).lower()
            actual = by_name.get(name)
            if actual is None:
                _diagnostic(diagnostics, "missing_parameter", "Required parameter is missing", parameter=name)
            elif expected_type and actual["type"] != expected_type:
                _diagnostic(
                    diagnostics,
                    "parameter_type_mismatch",
                    "Required parameter has a different type",
                    parameter=name,
                    expected=expected_type,
                    actual=actual["type"],
                )

        manifest = None
        manifest_section = sections.get(_MANIFEST_SECTION)
        if manifest_section is None:
            _diagnostic(
                diagnostics,
                "missing_manifest",
                "HDA dependency manifest is missing",
                severity="error" if require_manifest else "warning",
            )
        else:
            try:
                manifest = json.loads(_section_contents(manifest_section).decode("utf-8"))
            except Exception as exc:  # noqa: BLE001
                _diagnostic(diagnostics, "invalid_manifest", "HDA dependency manifest is invalid", details=str(exc))
        if isinstance(manifest, dict):
            if manifest.get("schema_version") != 1:
                _diagnostic(diagnostics, "unsupported_manifest", "Unsupported HDA manifest schema version")
            if manifest.get("node_type_name") and manifest["node_type_name"] != actual_name:
                _diagnostic(diagnostics, "manifest_name_mismatch", "Manifest node type name does not match definition")
            if manifest.get("version") and manifest["version"] != actual_version:
                _diagnostic(diagnostics, "manifest_version_mismatch", "Manifest version does not match definition")
            for custom_section in manifest.get("custom_sections", []):
                if custom_section not in sections:
                    _diagnostic(
                        diagnostics,
                        "missing_section",
                        "Manifest custom section is missing",
                        section=custom_section,
                    )
            for resource in manifest.get("resources", []):
                section_name = resource.get("section") if isinstance(resource, dict) else None
                if not section_name or section_name not in sections:
                    _diagnostic(
                        diagnostics,
                        "missing_resource",
                        "Manifest embedded resource is missing",
                        section=section_name,
                    )
                    continue
                expected_sha = resource.get("sha256")
                if expected_sha:
                    actual_sha = hashlib.sha256(_section_contents(sections[section_name])).hexdigest()
                    if actual_sha != expected_sha:
                        _diagnostic(
                            diagnostics,
                            "resource_checksum_mismatch",
                            "Embedded resource checksum does not match the manifest",
                            section=section_name,
                        )
            if check_dependencies:
                for dependency in manifest.get("dependencies", []):
                    if not isinstance(dependency, str) or not dependency.strip():
                        _diagnostic(diagnostics, "invalid_dependency", "Manifest dependency path is invalid")
                        continue
                    expanded = hou.expandString(dependency)
                    if not Path(expanded).expanduser().exists():
                        _diagnostic(
                            diagnostics,
                            "missing_dependency",
                            "External HDA dependency does not exist",
                            dependency=dependency,
                            expanded_path=expanded,
                        )

        instantiable = None
        if instantiate:
            instantiable = False
            parent = hou.node(parent_path)
            if parent is None:
                _diagnostic(
                    diagnostics, "parent_not_found", "Validation parent node was not found", parent_path=parent_path
                )
            else:
                instance = None
                try:
                    instance = parent.createNode(
                        actual_name,
                        node_name="__dcc_mcp_hda_contract__",
                        run_init_scripts=False,
                        exact_type_name=True,
                    )
                    instance_definition = instance.type().definition()
                    if instance_definition is None or instance_definition.nodeTypeName() != actual_name:
                        _diagnostic(
                            diagnostics,
                            "instantiated_definition_mismatch",
                            "Temporary instance did not resolve to the requested exact HDA definition",
                        )
                    elif library_path is not None and _path_key(instance_definition.libraryFilePath()) != _path_key(
                        library_path
                    ):
                        _diagnostic(
                            diagnostics,
                            "instantiated_library_mismatch",
                            "Temporary instance resolved to the same node type from a different HDA library",
                            expected_library=str(library_path),
                            actual_library=instance_definition.libraryFilePath(),
                        )
                    else:
                        instantiable = True
                except Exception as exc:  # noqa: BLE001
                    _diagnostic(diagnostics, "instantiation_failed", "HDA could not be instantiated", details=str(exc))
                finally:
                    if instance is not None:
                        try:
                            instance.destroy()
                        except Exception as exc:  # noqa: BLE001
                            _diagnostic(
                                diagnostics,
                                "probe_cleanup_failed",
                                "Temporary HDA validation node could not be removed",
                                details=str(exc),
                            )

        error_count = sum(item["severity"] == "error" for item in diagnostics)
        warning_count = sum(item["severity"] == "warning" for item in diagnostics)
        valid = error_count == 0 and instantiable is not False
        return skill_success(
            "HDA contract is valid" if valid else "HDA contract is invalid",
            valid=valid,
            node_type_name=actual_name,
            namespace=namespace,
            asset_name=asset_name,
            type_version=type_version,
            definition_version=actual_version,
            hda_file=str(library_path) if library_path else definition.libraryFilePath(),
            sections=section_names,
            interface=interface,
            manifest=manifest,
            instantiable=instantiable,
            diagnostics=diagnostics,
            error_count=error_count,
            warning_count=warning_count,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to validate HDA contract")
    finally:
        if installed_for_validation and library_path is not None:
            try:
                hou.hda.uninstallFile(str(library_path))
            except Exception:  # noqa: BLE001
                pass


@skill_entry
def main(**kwargs) -> dict:
    return validate_hda_contract(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
