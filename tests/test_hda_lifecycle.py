"""Mock-HOM tests for the reusable HDA lifecycle tools."""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

from skill_loader import skill_script_import_context

_SCRIPTS = Path(__file__).parents[1] / "src" / "dcc_mcp_houdini" / "skills" / "houdini-hda" / "scripts"


def _load_script(name: str) -> ModuleType:
    path = _SCRIPTS / name
    spec = importlib.util.spec_from_file_location("hda_lifecycle_{}".format(path.stem), path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    with skill_script_import_context(spec):
        spec.loader.exec_module(module)
    return module


def test_promote_hda_parameters_clones_interface_and_links_internal_tuple() -> None:
    mod = _load_script("promote_hda_parameters.py")
    template = MagicMock()
    cloned = MagicMock()
    template.clone.return_value = cloned
    source_tuple = MagicMock()
    source_tuple.parmTemplate.return_value = template
    source_tuple.eval.return_value = (1.25,)
    target_tuple = MagicMock()
    group = MagicMock()
    group.find.return_value = None

    node_type = MagicMock()
    node_type.definition.return_value = None
    parent = MagicMock()
    parent.path.return_value = "/obj/solar_asset"
    parent.type.return_value = node_type
    parent.parmTemplateGroup.return_value = group
    parent.parmTuple.return_value = target_tuple
    source = MagicMock()
    source.path.return_value = "/obj/solar_asset/bloom"
    source.parmTuple.return_value = source_tuple
    mock_hou = MagicMock()
    mock_hou.node.side_effect = lambda path: {
        "/obj/solar_asset": parent,
        "/obj/solar_asset/bloom": source,
    }.get(path)

    with patch.dict(sys.modules, {"hou": mock_hou}):
        result = mod.promote_hda_parameters(
            "/obj/solar_asset",
            [
                {
                    "source_node_path": "/obj/solar_asset/bloom",
                    "source_parm": "gain",
                    "name": "bloom_gain",
                    "label": "Bloom Gain",
                }
            ],
        )

    assert result["success"] is True
    assert result["context"]["promoted"] == [
        {
            "name": "bloom_gain",
            "label": "Bloom Gain",
            "source": "/obj/solar_asset/bloom/gain",
            "component_count": 1,
        }
    ]
    cloned.setName.assert_called_once_with("bloom_gain")
    cloned.setLabel.assert_called_once_with("Bloom Gain")
    group.append.assert_called_once_with(cloned)
    parent.setParmTemplateGroup.assert_called_once_with(group)
    target_tuple.set.assert_called_once_with((1.25,))
    source_tuple.set.assert_called_once_with(target_tuple, language=mock_hou.exprLanguage.Hscript)


def test_promote_hda_parameters_reacquires_tuple_after_definition_interface_change() -> None:
    mod = _load_script("promote_hda_parameters.py")
    template = MagicMock()
    template.clone.return_value = MagicMock()
    stale_source_tuple = MagicMock()
    stale_source_tuple.parmTemplate.return_value = template
    fresh_source_tuple = MagicMock()
    fresh_source_tuple.eval.return_value = (2.5,)
    target_tuple = MagicMock()
    group = MagicMock()
    group.find.return_value = None

    definition = MagicMock()
    definition.parmTemplateGroup.return_value = group
    node_type = MagicMock()
    node_type.definition.return_value = definition
    parent = MagicMock()
    parent.path.return_value = "/obj/solar_asset"
    parent.type.return_value = node_type
    parent.matchesCurrentDefinition.return_value = False
    parent.parmTuple.return_value = target_tuple
    source = MagicMock()
    source.path.return_value = "/obj/solar_asset/bloom"
    source.parmTuple.side_effect = [stale_source_tuple, fresh_source_tuple]
    mock_hou = MagicMock()
    mock_hou.node.side_effect = lambda path: {
        "/obj/solar_asset": parent,
        "/obj/solar_asset/bloom": source,
    }.get(path)

    with patch.dict(sys.modules, {"hou": mock_hou}):
        result = mod.promote_hda_parameters(
            "/obj/solar_asset",
            [{"source_node_path": "/obj/solar_asset/bloom", "source_parm": "gain"}],
        )

    assert result["success"] is True
    definition.setParmTemplateGroup.assert_called_once_with(group)
    fresh_source_tuple.eval.assert_called_once_with()
    fresh_source_tuple.set.assert_called_once_with(target_tuple, language=mock_hou.exprLanguage.Hscript)
    stale_source_tuple.set.assert_not_called()


def test_save_node_as_hda_persists_promoted_subnet_interface() -> None:
    mod = _load_script("save_node_as_hda.py")

    class _FolderSetParmTemplate:
        def __init__(self) -> None:
            self.clone = MagicMock()

    promoted_group = MagicMock()
    promoted_template = MagicMock()
    promoted_clone = MagicMock()
    promoted_template.clone.return_value = promoted_clone
    promoted_parm = MagicMock()
    promoted_parm.isSpare.return_value = True
    promoted_tuple = MagicMock()
    promoted_tuple.__iter__.return_value = iter([promoted_parm])
    promoted_tuple.parmTemplate.return_value = promoted_template
    built_in_parm = MagicMock()
    built_in_parm.isSpare.return_value = False
    built_in_tuple = MagicMock()
    built_in_tuple.__iter__.return_value = iter([built_in_parm])
    folder_template = _FolderSetParmTemplate()
    folder_parm = MagicMock()
    folder_parm.isSpare.return_value = True
    folder_tuple = MagicMock()
    folder_tuple.__iter__.return_value = iter([folder_parm])
    folder_tuple.parmTemplate.return_value = folder_template
    definition = MagicMock()
    hda_type = MagicMock()
    hda_type.definition.return_value = definition
    hda_node = MagicMock()
    hda_node.type.return_value = hda_type
    hda_node.path.return_value = "/obj/solar_asset"
    hda_node.name.return_value = "solar_asset"
    node = MagicMock()
    node.parmTuples.return_value = [built_in_tuple, folder_tuple, promoted_tuple]
    node.createDigitalAsset.return_value = hda_node
    mock_hou = MagicMock()
    mock_hou.FolderSetParmTemplate = _FolderSetParmTemplate
    mock_hou.node.return_value = node
    mock_hou.ParmTemplateGroup.return_value = promoted_group

    with patch.dict(sys.modules, {"hou": mock_hou}):
        with patch.object(mod, "validate_hda_path", return_value=Path("/assets/solar.hda")):
            result = mod.save_node_as_hda(
                "/obj/solar_asset",
                "/assets/solar.hda",
                "studio::solar",
                version="1.0.0",
            )

    assert result["success"] is True
    promoted_group.append.assert_called_once_with(promoted_clone)
    built_in_tuple.parmTemplate.assert_not_called()
    folder_template.clone.assert_not_called()
    definition.setParmTemplateGroup.assert_called_once_with(promoted_group)
    definition.save.assert_called_once_with(str(Path("/assets/solar.hda")))


def test_save_node_as_hda_refuses_existing_library_without_explicit_overwrite(tmp_path: Path) -> None:
    mod = _load_script("save_node_as_hda.py")
    hda_path = tmp_path / "solar.hda"
    hda_path.write_bytes(b"existing-library")
    before_sha256 = hashlib.sha256(hda_path.read_bytes()).hexdigest()
    node = MagicMock()
    mock_hou = MagicMock()
    mock_hou.node.return_value = node

    with patch.dict(sys.modules, {"hou": mock_hou}):
        result = mod.save_node_as_hda(
            "/obj/solar_asset",
            str(hda_path),
            "studio::solar",
        )

    assert result["success"] is False
    assert "already exists" in result["error"].lower()
    assert hashlib.sha256(hda_path.read_bytes()).hexdigest() == before_sha256
    node.createDigitalAsset.assert_not_called()


def test_save_node_as_hda_allows_explicit_in_place_overwrite(tmp_path: Path) -> None:
    mod = _load_script("save_node_as_hda.py")
    hda_path = tmp_path / "solar.hda"
    hda_path.write_bytes(b"existing-library")
    definition = MagicMock()
    hda_node = MagicMock()
    hda_node.type.return_value.definition.return_value = definition
    node = MagicMock()
    node.parmTuples.return_value = []
    node.createDigitalAsset.return_value = hda_node
    mock_hou = MagicMock()
    mock_hou.node.return_value = node

    with patch.dict(sys.modules, {"hou": mock_hou}):
        result = mod.save_node_as_hda(
            "/obj/solar_asset",
            str(hda_path),
            "studio::solar",
            overwrite=True,
        )

    assert result["success"] is True
    assert result["context"]["overwritten"] is True
    node.createDigitalAsset.assert_called_once()


def test_update_hda_definition_saves_unlocked_contents_bumps_version_and_locks() -> None:
    mod = _load_script("update_hda_definition.py")
    definition = MagicMock()
    definition.version.return_value = "1.1.0"
    definition.libraryFilePath.return_value = "/assets/solar.hda"
    definition.nodeTypeName.return_value = "studio::solar"
    node_type = MagicMock()
    node_type.definition.return_value = definition
    node = MagicMock()
    node.path.return_value = "/obj/solar1"
    node.type.return_value = node_type
    node.matchesCurrentDefinition.side_effect = [False, True]
    mock_hou = MagicMock()
    mock_hou.node.return_value = node

    with patch.dict(sys.modules, {"hou": mock_hou}):
        result = mod.update_hda_definition("/obj/solar1", "1.2.0")

    assert result["success"] is True
    assert result["context"] == {
        "node_path": "/obj/solar1",
        "node_type_name": "studio::solar",
        "library_path": "/assets/solar.hda",
        "old_version": "1.1.0",
        "version": "1.2.0",
        "contents_updated": True,
        "matched_current_definition": True,
    }
    definition.updateFromNode.assert_called_once_with(node)
    definition.setVersion.assert_called_once_with("1.2.0")
    node.matchCurrentDefinition.assert_called_once_with()


def test_sync_hda_instance_matches_definition_and_runs_version_handler() -> None:
    mod = _load_script("sync_hda_instance.py")
    definition = MagicMock()
    definition.version.return_value = "1.2.0"
    definition.libraryFilePath.return_value = "/assets/solar.hda"
    definition.nodeTypeName.return_value = "studio::solar"
    node_type = MagicMock()
    node_type.definition.return_value = definition
    node = MagicMock()
    node.path.return_value = "/obj/solar1"
    node.type.return_value = node_type
    node.isDelayedDefinition.return_value = True
    node.matchesCurrentDefinition.side_effect = [False, True]
    mock_hou = MagicMock()
    mock_hou.node.return_value = node

    with patch.dict(sys.modules, {"hou": mock_hou}):
        result = mod.sync_hda_instance("/obj/solar1", "1.1.0")

    assert result["success"] is True
    assert result["context"] == {
        "node_path": "/obj/solar1",
        "node_type_name": "studio::solar",
        "library_path": "/assets/solar.hda",
        "from_version": "1.1.0",
        "version": "1.2.0",
        "delayed_definition_synced": True,
        "matched_current_definition": True,
    }
    node.syncDelayedDefinition.assert_called_once_with()
    node.matchCurrentDefinition.assert_called_once_with()
    node.syncNodeVersionIfNeeded.assert_called_once_with("1.1.0")
