"""Publish a namespaced, versioned HDA definition with safe metadata sections."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _hda_common import hou_import_error, validate_hda_path

_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SECTION_PART = re.compile(r"^[A-Za-z0-9._-]+$")
_MAX_TEXT_BYTES = 2 * 1024 * 1024
_MAX_RESOURCE_BYTES = 64 * 1024 * 1024
_MANIFEST_SECTION = "dcc_mcp/manifest.json"


def _safe_relative_section(value: str) -> str:
    value = str(value).strip().strip("/")
    parts = value.split("/")
    if not value or any(part in {"", ".", ".."} or not _SECTION_PART.match(part) for part in parts):
        raise ValueError("Invalid embedded section name: {!r}".format(value))
    return value


def _safe_custom_section(value: str) -> str:
    name = _safe_relative_section(value)
    if not name.startswith("dcc_mcp/"):
        raise ValueError("Custom sections must use the dcc_mcp/ namespace: {}".format(name))
    if name == _MANIFEST_SECTION or name.startswith("dcc_mcp/resources/"):
        raise ValueError("Reserved custom section name: {}".format(name))
    return name


def _text(value: Optional[str], field: str) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("{} must be a string".format(field))
    if len(value.encode("utf-8")) > _MAX_TEXT_BYTES:
        raise ValueError("{} exceeds the 2 MiB limit".format(field))
    return value


def publish_hda_library(
    node_path: str,
    hda_file_path: str,
    namespace: str,
    asset_name: str,
    version: str,
    label: Optional[str] = None,
    icon: Optional[str] = None,
    help_text: Optional[str] = None,
    dependencies: Optional[Sequence[str]] = None,
    custom_sections: Optional[Dict[str, str]] = None,
    embedded_resources: Optional[Sequence[Dict[str, str]]] = None,
    conflict_policy: str = "error",
    update_contents: bool = True,
    install: bool = True,
    make_preferred: bool = False,
) -> dict:
    """Copy an HDA definition to a public library contract without executable sections."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return hou_import_error()

    try:
        namespace = str(namespace).strip()
        asset_name = str(asset_name).strip()
        version = str(version).strip()
        if not _NAME.match(namespace) or not _NAME.match(asset_name):
            raise ValueError("namespace and asset_name must start with a letter and contain only letters, digits, '_'")
        if not _VERSION.match(version):
            raise ValueError("Invalid HDA version: {!r}".format(version))
        if conflict_policy not in {"error", "overwrite"}:
            raise ValueError("conflict_policy must be 'error' or 'overwrite'")
        if make_preferred and not install:
            raise ValueError("make_preferred requires install=true")
        label = _text(label, "label")
        icon = _text(icon, "icon")
        help_text = _text(help_text, "help_text")

        dependency_list = []
        if len(dependencies or []) > 256:
            raise ValueError("dependencies cannot contain more than 256 entries")
        for dependency in dependencies or []:
            value = str(dependency).strip()
            if not value:
                raise ValueError("dependencies must not contain empty paths")
            if value not in dependency_list:
                dependency_list.append(value)

        prepared_sections = []
        if len(custom_sections or {}) > 64:
            raise ValueError("custom_sections cannot contain more than 64 entries")
        for raw_name, contents in (custom_sections or {}).items():
            name = _safe_custom_section(raw_name)
            contents = _text(contents, "custom section {}".format(name))
            if contents is None:
                raise ValueError("custom section contents must be a string: {}".format(name))
            prepared_sections.append((name, contents))

        prepared_resources: List[dict] = []
        if len(embedded_resources or []) > 64:
            raise ValueError("embedded_resources cannot contain more than 64 entries")
        section_names = {name for name, _contents in prepared_sections}
        resource_bytes = 0
        for resource in embedded_resources or []:
            if not isinstance(resource, dict):
                raise ValueError("embedded_resources entries must be objects")
            path = Path(str(resource.get("file_path", ""))).expanduser()
            if not path.is_file():
                raise FileNotFoundError("Embedded resource not found: {}".format(path))
            if path.stat().st_size > _MAX_RESOURCE_BYTES:
                raise ValueError("Embedded resource exceeds the 64 MiB limit: {}".format(path))
            relative_name = _safe_relative_section(resource.get("section_name", ""))
            section_name = "dcc_mcp/resources/{}".format(relative_name)
            if section_name in section_names:
                raise ValueError("Duplicate embedded section name: {}".format(section_name))
            section_names.add(section_name)
            contents = path.read_bytes()
            resource_bytes += len(contents)
            if resource_bytes > 256 * 1024 * 1024:
                raise ValueError("Embedded resources exceed the 256 MiB library limit")
            prepared_resources.append(
                {
                    "source_path": str(path),
                    "section": section_name,
                    "contents": contents,
                    "size": len(contents),
                    "sha256": hashlib.sha256(contents).hexdigest(),
                }
            )

        node = hou.node(node_path)
        if node is None:
            raise ValueError("Houdini node not found: {}".format(node_path))
        source_definition = node.type().definition()
        if source_definition is None:
            raise ValueError("Node is not a Houdini Digital Asset: {}".format(node_path))
        target_path = validate_hda_path(hda_file_path, must_exist=False)
        target_name = hou.hda.fullNodeTypeNameFromComponents("", namespace, asset_name, version)
        existing_names = []
        if target_path.is_file():
            existing_names = [definition.nodeTypeName() for definition in hou.hda.definitionsInFile(str(target_path))]
        if target_name in existing_names and conflict_policy == "error":
            raise ValueError("HDA definition already exists: {}".format(target_name))

        contents_updated = bool(update_contents and not node.matchesCurrentDefinition())
        if contents_updated:
            source_definition.updateFromNode(node)

        menu_name = label or source_definition.description() or asset_name
        source_definition.copyToHDAFile(str(target_path), new_name=target_name, new_menu_name=menu_name)
        published = next(
            (
                definition
                for definition in hou.hda.definitionsInFile(str(target_path))
                if definition.nodeTypeName() == target_name
            ),
            None,
        )
        if published is None:
            raise RuntimeError("Published HDA definition could not be reopened: {}".format(target_name))

        published.setVersion(version)
        published.setDescription(menu_name)
        if icon:
            published.setIcon(icon)
        if help_text is not None:
            published.addSection("Help", help_text)
        for section_name, contents in prepared_sections:
            published.addSection(section_name, contents)
        for resource in prepared_resources:
            published.addSection(resource["section"], resource["contents"])

        manifest = {
            "schema_version": 1,
            "node_type_name": target_name,
            "namespace": namespace,
            "asset_name": asset_name,
            "version": version,
            "dependencies": dependency_list,
            "custom_sections": sorted(name for name, _contents in prepared_sections),
            "resources": [
                {"section": item["section"], "sha256": item["sha256"], "size": item["size"]}
                for item in prepared_resources
            ],
        }
        published.addSection(_MANIFEST_SECTION, json.dumps(manifest, indent=2, sort_keys=True))

        if install:
            hou.hda.installFile(str(target_path), force_use_assets=bool(make_preferred))

        return skill_success(
            "Published HDA library",
            source_node=node.path(),
            hda_file_path=str(target_path),
            node_type_name=target_name,
            namespace=namespace,
            asset_name=asset_name,
            version=version,
            conflict_policy=conflict_policy,
            overwritten=target_name in existing_names,
            contents_updated=contents_updated,
            installed=bool(install),
            preferred=bool(make_preferred),
            sections=sorted(set(section_names) | {_MANIFEST_SECTION} | ({"Help"} if help_text is not None else set())),
            dependency_count=len(dependency_list),
            resource_count=len(prepared_resources),
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to publish HDA library")


@skill_entry
def main(**kwargs) -> dict:
    return publish_hda_library(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
