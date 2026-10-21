"""Mock-HOM tests for the reusable HDA lifecycle tools."""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest
from skill_error_assertions import skill_error_detail
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


def test_validate_hda_path_accepts_sidefx_expanded_library(tmp_path: Path) -> None:
    mod = _load_script("_hda_common.py")
    library = tmp_path / "normals_from_gsplats.1.0.hda"
    library.mkdir()
    (library / "Sections.list").write_text("INDEX__SECTION\n", encoding="utf-8")

    assert mod.validate_hda_path(str(library)) == library


def test_validate_hda_path_rejects_empty_hda_directory(tmp_path: Path) -> None:
    mod = _load_script("_hda_common.py")
    library = tmp_path / "not_a_library.hda"
    library.mkdir()

    with pytest.raises(FileNotFoundError, match="HDA library not found"):
        mod.validate_hda_path(str(library))


def test_install_hda_file_reports_expanded_library(tmp_path: Path) -> None:
    mod = _load_script("install_hda_file.py")
    library = tmp_path / "delight_gsplats.1.0.hda"
    library.mkdir()
    (library / "Sections.list").write_text("INDEX__SECTION\n", encoding="utf-8")
    definition = MagicMock()
    definition.nodeTypeName.return_value = "labs::delight_gsplats::1.0"
    definition.nodeType.return_value.category.return_value.name.return_value = "Sop"
    mock_hou = MagicMock()
    mock_hou.hda.definitionsInFile.return_value = [definition]

    with patch.dict(sys.modules, {"hou": mock_hou}):
        result = mod.install_hda_file(str(library))

    assert result["success"] is True
    assert result["context"]["library_format"] == "expanded"
    mock_hou.hda.installFile.assert_called_once_with(str(library))


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
    assert "already exists" in skill_error_detail(result).lower()
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


def test_sync_hda_instance_forces_target_library_current_and_upgrades(tmp_path: Path) -> None:
    mod = _load_script("sync_hda_instance.py")
    library = tmp_path / "solar.hda"
    library.write_text("dummy", encoding="utf-8")

    target_definition = MagicMock()
    target_definition.nodeTypeName.return_value = "studio::solar"
    target_definition.version.return_value = "2.0"

    definition = MagicMock()
    definition.version.return_value = "2.0"
    definition.libraryFilePath.return_value = "/assets/solar.hda"
    definition.nodeTypeName.return_value = "studio::solar"
    node_type = MagicMock()
    node_type.name.return_value = "studio::solar"
    node_type.category.return_value = MagicMock()
    node_type.definition.return_value = definition
    node = MagicMock()
    node.path.return_value = "/obj/solar1"
    node.type.return_value = node_type
    node.isDelayedDefinition.return_value = False
    node.matchesCurrentDefinition.return_value = True

    mock_hou = MagicMock()
    mock_hou.node.return_value = node
    # Already loaded is exactly the condition where reloadFile used to be a
    # no-op and left an older last-installed definition current.
    mock_hou.hda.loadedFiles.return_value = [str(library)]
    mock_hou.hda.definitionsInFile.return_value = [target_definition]

    with patch.dict(sys.modules, {"hou": mock_hou}):
        result = mod.sync_hda_instance("/obj/solar1", "1.0", hda_file=str(library))

    assert result["success"] is True
    ctx = result["context"]
    assert ctx["version"] == "2.0"
    assert ctx["target_version"] == "2.0"
    assert ctx["matched_current_definition"] is True
    mock_hou.hda.installFile.assert_called_once_with(str(library), force_use_assets=True)
    mock_hou.hda.reloadFile.assert_not_called()
    node.syncNodeVersionIfNeeded.assert_called_once_with("1.0")


def test_sync_hda_instance_errors_when_target_version_not_reached(tmp_path: Path) -> None:
    mod = _load_script("sync_hda_instance.py")
    library = tmp_path / "solar.hda"
    library.write_text("dummy", encoding="utf-8")

    target_definition = MagicMock()
    target_definition.nodeTypeName.return_value = "studio::solar"
    target_definition.version.return_value = "2.0"

    # Host still resolves the instance to the old definition after the attempt.
    stale_definition = MagicMock()
    stale_definition.version.return_value = "1.0"
    stale_definition.libraryFilePath.return_value = "/assets/solar.hda"
    stale_definition.nodeTypeName.return_value = "studio::solar"
    node_type = MagicMock()
    node_type.name.return_value = "studio::solar"
    node_type.category.return_value = MagicMock()
    node_type.definition.return_value = stale_definition
    node = MagicMock()
    node.path.return_value = "/obj/solar1"
    node.type.return_value = node_type
    node.isDelayedDefinition.return_value = False
    node.matchesCurrentDefinition.return_value = False

    mock_hou = MagicMock()
    mock_hou.node.return_value = node
    mock_hou.hda.definitionsInFile.return_value = [target_definition]
    mock_hou.nodeType.return_value = None

    with patch.dict(sys.modules, {"hou": mock_hou}):
        result = mod.sync_hda_instance("/obj/solar1", "1.0", hda_file=str(library))

    assert result["success"] is False
    ctx = result["context"]
    assert ctx["target_version"] == "2.0"
    assert ctx["version"] == "1.0"
    detail = skill_error_detail(result)
    assert "2.0" in detail and "1.0" in detail
    node.syncNodeVersionIfNeeded.assert_called_once_with("1.0")


def test_sync_hda_instance_without_hda_file_skips_promotion_and_target() -> None:
    mod = _load_script("sync_hda_instance.py")
    definition = MagicMock()
    definition.version.return_value = "1.2.0"
    definition.libraryFilePath.return_value = "/assets/solar.hda"
    definition.nodeTypeName.return_value = "studio::solar"
    node_type = MagicMock()
    node_type.name.return_value = "studio::solar"
    node_type.definition.return_value = definition
    node = MagicMock()
    node.path.return_value = "/obj/solar1"
    node.type.return_value = node_type
    node.isDelayedDefinition.return_value = False
    node.matchesCurrentDefinition.return_value = True

    mock_hou = MagicMock()
    mock_hou.node.return_value = node

    with patch.dict(sys.modules, {"hou": mock_hou}):
        result = mod.sync_hda_instance("/obj/solar1", "1.1.0")

    assert result["success"] is True
    assert "target_version" not in result["context"]
    mock_hou.hda.installFile.assert_not_called()
    mock_hou.hda.reloadFile.assert_not_called()


def test_library_definition_version_prefers_current_definition_from_same_library(tmp_path: Path) -> None:
    mod = _load_script("sync_hda_instance.py")
    library = tmp_path / "solar.hda"
    library.write_text("dummy", encoding="utf-8")

    older = MagicMock()
    older.nodeTypeName.return_value = "studio::solar"
    older.version.return_value = "1.0"
    newer = MagicMock()
    newer.nodeTypeName.return_value = "studio::solar"
    newer.version.return_value = "2.0"

    current_definition = MagicMock()
    current_definition.version.return_value = "2.0"
    current_definition.libraryFilePath.return_value = str(library)
    current_type = MagicMock()
    current_type.definition.return_value = current_definition

    mock_hou = MagicMock()
    mock_hou.hda.definitionsInFile.return_value = [older, newer]
    mock_hou.nodeType.return_value = current_type

    version = mod._library_definition_version(mock_hou, str(library), "studio::solar", MagicMock())
    assert version == "2.0"


def test_version_key_orders_dotted_versions_numerically() -> None:
    mod = _load_script("sync_hda_instance.py")
    assert mod._version_key("1.10") > mod._version_key("1.9")
    assert mod._version_key("2.0") > mod._version_key("1.9.9")
    assert mod._version_key("1.0.0") > mod._version_key("1.0")


def _hda_definition(node_type_name: str, library: str, category_name: str = "Sop") -> MagicMock:
    """Build a mock hou.HDADefinition suitable for install/uninstall tests."""
    category = MagicMock()
    category.name.return_value = category_name
    node_type = MagicMock()
    node_type.category.return_value = category
    definition = MagicMock()
    definition.nodeType.return_value = node_type
    definition.nodeTypeName.return_value = node_type_name
    definition.libraryFilePath.return_value = library
    definition.description.return_value = "Solar asset"
    definition.version.return_value = "1.0"
    return definition


def test_uninstall_hda_file_uninstalls_loaded_library_and_unregister_types(tmp_path: Path) -> None:
    mod = _load_script("uninstall_hda_file.py")
    library = str(tmp_path / "solar.hda")
    definition = _hda_definition("studio::solar", library)
    sop_category = definition.nodeType.return_value.category.return_value

    mock_hou = MagicMock()
    # First call (before uninstall) reports loaded; second call (after) reports gone.
    mock_hou.hda.loadedFiles.side_effect = [[library], []]
    mock_hou.hda.definitionsInFile.return_value = [definition]
    mock_hou.nodeType.return_value = None  # node type unregistered after uninstall

    with patch.dict(sys.modules, {"hou": mock_hou}):
        result = mod.uninstall_hda_file(library)

    assert result["success"] is True
    ctx = result["context"]
    assert ctx["was_loaded"] is True
    assert ctx["still_loaded"] is False
    assert ctx["removed_definition_count"] == 1
    assert ctx["removed_definitions"][0]["node_type_name"] == "studio::solar"
    assert ctx["unregistered_node_types"] == ["studio::solar"]
    assert ctx["session_only"] is True
    mock_hou.hda.uninstallFile.assert_called_once_with(library)
    # Post-check must look the node type up with the captured category.
    mock_hou.nodeType.assert_called_once_with(sop_category, "studio::solar")


def test_uninstall_hda_file_is_idempotent_noop_when_not_loaded(tmp_path: Path) -> None:
    mod = _load_script("uninstall_hda_file.py")
    library = str(tmp_path / "solar.hda")
    mock_hou = MagicMock()
    mock_hou.hda.loadedFiles.return_value = ["/libs/other.hda"]

    with patch.dict(sys.modules, {"hou": mock_hou}):
        result = mod.uninstall_hda_file(library)

    assert result["success"] is True
    ctx = result["context"]
    assert ctx["was_loaded"] is False
    assert ctx["still_loaded"] is False
    assert ctx["removed_definition_count"] == 0
    assert ctx["removed_definitions"] == []
    assert ctx["session_only"] is True
    mock_hou.hda.uninstallFile.assert_not_called()


def test_uninstall_hda_file_reports_still_loaded_when_houdini_keeps_library(tmp_path: Path) -> None:
    mod = _load_script("uninstall_hda_file.py")
    library = str(tmp_path / "solar.hda")
    definition = _hda_definition("studio::solar", library)
    mock_hou = MagicMock()
    mock_hou.hda.loadedFiles.side_effect = [[library], [library]]
    mock_hou.hda.definitionsInFile.return_value = [definition]
    mock_hou.nodeType.return_value = definition.nodeType.return_value

    with patch.dict(sys.modules, {"hou": mock_hou}):
        result = mod.uninstall_hda_file(library)

    assert result["success"] is True
    assert result["context"]["was_loaded"] is True
    assert result["context"]["still_loaded"] is True
    assert result["context"]["unregistered_node_types"] == []
    mock_hou.hda.uninstallFile.assert_called_once_with(library)


def test_uninstall_hda_file_uninstalls_when_definitions_cannot_be_read(tmp_path: Path) -> None:
    """A loaded library whose file is missing/corrupt must still be uninstallable.

    Regression: an unguarded ``hou.hda.definitionsInFile`` call raised for such a
    library, so ``hou.hda.uninstallFile`` was never reached and the library could
    not be removed from the session at all — contradicting the tool's own design
    intent that a library removed from disk may still be session-registered.
    """
    mod = _load_script("uninstall_hda_file.py")
    library = str(tmp_path / "solar.hda")
    mock_hou = MagicMock()
    # The library is still registered in the session, but its backing file can no
    # longer be read (removed or corrupted on disk).
    mock_hou.hda.loadedFiles.side_effect = [[library], []]
    mock_hou.hda.definitionsInFile.side_effect = RuntimeError("library file missing or corrupt")

    with patch.dict(sys.modules, {"hou": mock_hou}):
        result = mod.uninstall_hda_file(library)

    assert result["success"] is True
    ctx = result["context"]
    assert ctx["was_loaded"] is True
    assert ctx["still_loaded"] is False
    assert ctx["removed_definition_count"] == 0
    assert ctx["removed_definitions"] == []
    assert ctx["unregistered_node_types"] == []
    # The whole point of the fix: uninstallFile still runs despite the read error.
    mock_hou.hda.uninstallFile.assert_called_once_with(library)


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="Case/separator-insensitive path matching relies on Windows ntpath.normcase semantics.",
)
def test_uninstall_hda_file_is_case_and_separator_insensitive_on_windows(tmp_path: Path) -> None:
    mod = _load_script("uninstall_hda_file.py")
    library = tmp_path / "solar.hda"
    library.write_bytes(b"hda")
    # Pass an upper-cased, back-slashed variant of the same loaded path.
    requested = str(library).upper().replace("/", "\\")
    definition = _hda_definition("studio::solar", str(library))
    mock_hou = MagicMock()
    mock_hou.hda.loadedFiles.side_effect = [[str(library)], []]
    mock_hou.hda.definitionsInFile.return_value = [definition]
    mock_hou.nodeType.return_value = None

    with patch.dict(sys.modules, {"hou": mock_hou}):
        result = mod.uninstall_hda_file(requested)

    assert result["success"] is True
    assert result["context"]["was_loaded"] is True
    # uninstallFile must be called with Houdini's canonical loaded string, not the raw input.
    mock_hou.hda.uninstallFile.assert_called_once_with(str(library))


def test_uninstall_hda_file_rejects_unsupported_extension() -> None:
    mod = _load_script("uninstall_hda_file.py")
    mock_hou = MagicMock()

    with patch.dict(sys.modules, {"hou": mock_hou}):
        result = mod.uninstall_hda_file("/libs/solar.txt")

    assert result["success"] is False
    mock_hou.hda.uninstallFile.assert_not_called()


def test_uninstall_hda_file_without_hou_returns_error(tmp_path: Path) -> None:
    mod = _load_script("uninstall_hda_file.py")
    import builtins

    real_import = builtins.__import__

    def _import(name, *args, **kwargs):
        if name == "hou":
            raise ImportError("no hou")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=_import):
        result = mod.uninstall_hda_file(str(tmp_path / "solar.hda"))

    assert result["success"] is False
