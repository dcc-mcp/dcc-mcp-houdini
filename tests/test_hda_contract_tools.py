"""Mock-HOM tests for declarative HDA authoring, publishing, and validation."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

from skill_loader import skill_script_import_context

_SCRIPTS = Path(__file__).parents[1] / "src" / "dcc_mcp_houdini" / "skills" / "houdini-hda" / "scripts"


def _load_script(name: str) -> ModuleType:
    path = _SCRIPTS / name
    spec = importlib.util.spec_from_file_location("hda_contract_{}".format(path.stem), path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    with skill_script_import_context(spec):
        spec.loader.exec_module(module)
    return module


class _Template:
    def __init__(self, name: str, label: str, kind: str, children=(), **settings) -> None:
        self._name = name
        self._label = label
        self._kind = kind
        self._children = tuple(children)
        self.settings = settings

    def name(self) -> str:
        return self._name

    def label(self) -> str:
        return self._label

    def type(self):
        return SimpleNamespace(name=lambda: self._kind)

    def numComponents(self) -> int:
        return int(self.settings.get("num_components", 1))

    def parmTemplates(self):
        return self._children

    def scriptCallback(self) -> str:
        return self.settings.get("script_callback", "")

    def itemGeneratorScript(self) -> str:
        return self.settings.get("item_generator_script", "")


class _Group:
    def __init__(self, entries=()) -> None:
        self._entries = list(entries)

    def entries(self):
        return tuple(self._entries)

    def find(self, name):
        return next((entry for entry in self._entries if entry.name() == name), None)

    def append(self, template) -> None:
        self._entries.append(template)

    def replace(self, name, template) -> None:
        index = next(i for i, entry in enumerate(self._entries) if entry.name() == name)
        self._entries[index] = template


def _template_api():
    def factory(kind):
        def build(name, label, *args, **kwargs):
            if kind == "Folder":
                children = kwargs.pop("parm_templates", args[0] if args else ())
                return _Template(name, label, kind, children, **kwargs)
            if kind in {"Float", "Int", "String"}:
                kwargs["num_components"] = args[0]
            return _Template(name, label, kind, **kwargs)

        return build

    return {
        "FloatParmTemplate": factory("Float"),
        "IntParmTemplate": factory("Int"),
        "ToggleParmTemplate": factory("Toggle"),
        "StringParmTemplate": factory("String"),
        "MenuParmTemplate": factory("Menu"),
        "FolderParmTemplate": factory("Folder"),
    }


def test_author_hda_interface_builds_safe_templates_and_promotion() -> None:
    mod = _load_script("author_hda_interface.py")
    group = _Group()
    definition = MagicMock()
    definition.parmTemplateGroup.return_value = group
    node_type = MagicMock()
    node_type.definition.return_value = definition
    target_tuple = MagicMock()
    node = MagicMock()
    node.path.return_value = "/obj/planet"
    node.type.return_value = node_type
    node.matchesCurrentDefinition.return_value = False
    node.parmTuple.return_value = target_tuple
    source_tuple = MagicMock()
    source_tuple.eval.return_value = (2.5,)
    source = MagicMock()
    source.path.return_value = "/obj/planet/noise"
    source.parmTuple.return_value = source_tuple
    mock_hou = MagicMock(**_template_api())
    mock_hou.node.side_effect = lambda path: {"/obj/planet": node, "/obj/planet/noise": source}.get(path)

    specs = [
        {
            "type": "folder",
            "name": "surface",
            "label": "Surface",
            "children": [
                {
                    "type": "float",
                    "name": "relief",
                    "label": "Relief",
                    "default": 0.25,
                    "min": 0.0,
                    "max": 4.0,
                    "promotion": {"source_node_path": "/obj/planet/noise", "source_parm": "amplitude"},
                },
                {"type": "int", "name": "octaves", "label": "Octaves", "default": 5, "min": 1, "max": 12},
                {"type": "toggle", "name": "clouds", "label": "Clouds", "default": True},
                {"type": "string", "name": "texture", "label": "Texture", "default": "$HIP/earth.exr"},
                {
                    "type": "menu",
                    "name": "quality",
                    "label": "Quality",
                    "items": [{"token": "preview", "label": "Preview"}, {"token": "final", "label": "Final"}],
                    "default": "final",
                },
            ],
        }
    ]

    with patch.dict(sys.modules, {"hou": mock_hou}):
        result = mod.author_hda_interface("/obj/planet", specs)

    assert result["success"] is True
    assert result["context"]["parameter_count"] == 6
    assert result["context"]["promoted"] == [
        {"name": "relief", "source": "/obj/planet/noise/amplitude", "component_count": 1}
    ]
    definition.setParmTemplateGroup.assert_called_once_with(group)
    assert group.entries()[0].name() == "surface"
    assert [entry.name() for entry in group.entries()[0].parmTemplates()] == [
        "relief",
        "octaves",
        "clouds",
        "texture",
        "quality",
    ]
    target_tuple.set.assert_called_once_with((2.5,))
    source_tuple.set.assert_called_once_with(target_tuple, language=mock_hou.exprLanguage.Hscript)


def test_author_hda_interface_rejects_script_fields() -> None:
    mod = _load_script("author_hda_interface.py")
    mock_hou = MagicMock(**_template_api())
    node = MagicMock()
    mock_hou.node.return_value = node

    with patch.dict(sys.modules, {"hou": mock_hou}):
        result = mod.author_hda_interface(
            "/obj/asset",
            [{"type": "float", "name": "gain", "label": "Gain", "script_callback": "danger()"}],
        )

    assert result["success"] is False
    assert "not allowed" in str(result["error"])


def test_author_hda_interface_accepts_one_sided_numeric_ranges() -> None:
    mod = _load_script("author_hda_interface.py")
    group = _Group()
    node = MagicMock()
    node.path.return_value = "/obj/asset"
    node.type.return_value.definition.return_value = None
    node.parmTemplateGroup.return_value = group
    mock_hou = MagicMock(**_template_api())
    mock_hou.node.return_value = node

    with patch.dict(sys.modules, {"hou": mock_hou}):
        result = mod.author_hda_interface(
            "/obj/asset",
            [
                {"type": "float", "name": "large", "label": "Large", "min": 20.0},
                {"type": "int", "name": "negative", "label": "Negative", "max": -5},
            ],
        )

    assert result["success"] is True
    node.setParmTemplateGroup.assert_called_once_with(group)


def test_publish_hda_library_namespaces_versions_and_embeds_manifest(tmp_path: Path) -> None:
    mod = _load_script("publish_hda_library.py")
    resource = tmp_path / "earth_albedo.exr"
    resource.write_bytes(b"texture")
    target = tmp_path / "planets.hda"
    source_definition = MagicMock()
    source_definition.description.return_value = "Planet"
    published = MagicMock()
    published.nodeTypeName.return_value = "studio::planet::1.2.0"
    source_type = MagicMock()
    source_type.definition.return_value = source_definition
    node = MagicMock()
    node.type.return_value = source_type
    mock_hou = MagicMock()
    mock_hou.node.return_value = node
    mock_hou.hda.fullNodeTypeNameFromComponents.return_value = "studio::planet::1.2.0"
    mock_hou.hda.definitionsInFile.return_value = [published]

    with patch.dict(sys.modules, {"hou": mock_hou}):
        result = mod.publish_hda_library(
            "/obj/planet",
            str(target),
            namespace="studio",
            asset_name="planet",
            version="1.2.0",
            label="Procedural Planet",
            icon="MISC_digital_asset",
            help_text="# Procedural Planet",
            dependencies=["$JOB/textures/stars.exr"],
            custom_sections={"dcc_mcp/provenance.json": "{}"},
            embedded_resources=[{"file_path": str(resource), "section_name": "textures/earth_albedo.exr"}],
            install=False,
        )

    assert result["success"] is True
    source_definition.copyToHDAFile.assert_called_once_with(
        str(target), new_name="studio::planet::1.2.0", new_menu_name="Procedural Planet"
    )
    published.setVersion.assert_called_once_with("1.2.0")
    published.setDescription.assert_called_once_with("Procedural Planet")
    published.setIcon.assert_called_once_with("MISC_digital_asset")
    sections = {call.args[0]: call.args[1] for call in published.addSection.call_args_list}
    assert sections["Help"] == "# Procedural Planet"
    assert sections["dcc_mcp/provenance.json"] == "{}"
    assert sections["dcc_mcp/resources/textures/earth_albedo.exr"] == b"texture"
    manifest = json.loads(sections["dcc_mcp/manifest.json"])
    assert manifest["node_type_name"] == "studio::planet::1.2.0"
    assert manifest["dependencies"] == ["$JOB/textures/stars.exr"]
    assert manifest["resources"][0]["sha256"]


def test_publish_hda_library_requires_explicit_overwrite(tmp_path: Path) -> None:
    mod = _load_script("publish_hda_library.py")
    target = tmp_path / "planets.hda"
    target.write_bytes(b"existing")
    existing = MagicMock()
    existing.nodeTypeName.return_value = "studio::planet::1.2.0"
    source_definition = MagicMock()
    node = MagicMock()
    node.type.return_value.definition.return_value = source_definition
    mock_hou = MagicMock()
    mock_hou.node.return_value = node
    mock_hou.hda.fullNodeTypeNameFromComponents.return_value = "studio::planet::1.2.0"
    mock_hou.hda.definitionsInFile.return_value = [existing]

    with patch.dict(sys.modules, {"hou": mock_hou}):
        result = mod.publish_hda_library(
            "/obj/planet",
            str(target),
            namespace="studio",
            asset_name="planet",
            version="1.2.0",
            conflict_policy="error",
            install=False,
        )

    assert result["success"] is False
    assert "already exists" in str(result["error"])
    source_definition.updateFromNode.assert_not_called()
    source_definition.copyToHDAFile.assert_not_called()


def test_validate_hda_contract_checks_definition_interface_dependencies_and_instantiation(tmp_path: Path) -> None:
    mod = _load_script("validate_hda_contract.py")
    library = tmp_path / "planets.hda"
    library.write_bytes(b"hda")
    dependency = tmp_path / "stars.exr"
    dependency.write_bytes(b"stars")
    manifest = {
        "schema_version": 1,
        "node_type_name": "studio::planet::1.2.0",
        "version": "1.2.0",
        "dependencies": [str(dependency)],
        "resources": [
            {
                "section": "dcc_mcp/resources/earth.exr",
                "sha256": hashlib.sha256(b"abc").hexdigest(),
                "size": 3,
            }
        ],
    }
    manifest_section = MagicMock()
    manifest_section.contents.return_value = json.dumps(manifest)
    resource_section = MagicMock()
    resource_section.contents.return_value = b"abc"
    definition = MagicMock()
    definition.nodeTypeName.return_value = "studio::planet::1.2.0"
    definition.version.return_value = "1.2.0"
    definition.libraryFilePath.return_value = str(library)
    definition.sections.return_value = {
        "Help": MagicMock(),
        "dcc_mcp/manifest.json": manifest_section,
        "dcc_mcp/resources/earth.exr": resource_section,
    }
    definition.parmTemplateGroup.return_value = _Group([_Template("relief", "Relief", "Float")])
    instance_type = MagicMock()
    instance_type.definition.return_value = definition
    instance = MagicMock()
    instance.type.return_value = instance_type
    parent = MagicMock()
    parent.createNode.return_value = instance
    mock_hou = MagicMock()
    mock_hou.hda.definitionsInFile.return_value = [definition]
    mock_hou.hda.loadedFiles.return_value = []
    mock_hou.hda.componentsFromFullNodeTypeName.return_value = ("", "studio", "planet", "1.2.0")
    mock_hou.node.return_value = parent
    mock_hou.expandString.side_effect = lambda value: value

    with patch.dict(sys.modules, {"hou": mock_hou}):
        result = mod.validate_hda_contract(
            "studio::planet::1.2.0",
            hda_file=str(library),
            expected_version="1.2.0",
            required_parameters=[{"name": "relief", "type": "float"}],
            required_sections=["Help"],
        )

    assert result["success"] is True
    assert result["context"]["valid"] is True
    assert result["context"]["instantiable"] is True
    parent.createNode.assert_called_once_with(
        "studio::planet::1.2.0",
        node_name="__dcc_mcp_hda_contract__",
        run_init_scripts=False,
        exact_type_name=True,
    )
    instance.destroy.assert_called_once_with()
    mock_hou.hda.installFile.assert_called_once_with(str(library))
    mock_hou.hda.uninstallFile.assert_called_once_with(str(library))


def test_validate_hda_contract_reports_callbacks_and_missing_dependency(tmp_path: Path) -> None:
    mod = _load_script("validate_hda_contract.py")
    missing = tmp_path / "missing.exr"
    manifest_section = MagicMock()
    manifest_section.contents.return_value = json.dumps(
        {"schema_version": 1, "dependencies": [str(missing)], "resources": []}
    )
    definition = MagicMock()
    definition.nodeTypeName.return_value = "studio::planet::1.2.0"
    definition.version.return_value = "1.2.0"
    definition.sections.return_value = {"dcc_mcp/manifest.json": manifest_section}
    definition.parmTemplateGroup.return_value = _Group(
        [_Template("unsafe", "Unsafe", "String", script_callback="danger()")]
    )
    mock_hou = MagicMock()
    mock_hou.hda.componentsFromFullNodeTypeName.return_value = ("", "studio", "planet", "1.2.0")
    mock_hou.nodeTypeCategories.return_value = {
        "Sop": SimpleNamespace(
            nodeTypes=lambda: {"studio::planet::1.2.0": SimpleNamespace(definition=lambda: definition)}
        )
    }
    mock_hou.expandString.side_effect = lambda value: value

    with patch.dict(sys.modules, {"hou": mock_hou}):
        result = mod.validate_hda_contract("studio::planet::1.2.0", instantiate=False)

    assert result["success"] is True
    assert result["context"]["valid"] is False
    codes = {item["code"] for item in result["context"]["diagnostics"]}
    assert {"unsafe_callback", "missing_dependency"}.issubset(codes)
