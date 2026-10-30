"""Mock-hou tests for the SOP -> USD modeling bridge (PIP-5116).

Covers the ``export_sop_to_usd`` tool and the USD-suffix guard added to
``export_geometry``. No live Houdini / pyUSD is required; ``hou``, ``pxr`` and
the USD stage are replaced with MagicMocks following the repo's skill-test
pattern.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

from skill_loader import skill_script_import_context

_SKILLS_ROOT = Path(__file__).parent.parent / "src" / "dcc_mcp_houdini" / "skills"


def _load_script(script_name: str) -> ModuleType:
    path = _SKILLS_ROOT / "houdini-interchange" / "scripts" / script_name
    spec = importlib.util.spec_from_file_location("sopusd_{}".format(path.stem), path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    with skill_script_import_context(spec):
        spec.loader.exec_module(module)
    return module


def _node(path: str, name: str, type_name: str = "geo") -> MagicMock:
    node = MagicMock()
    node.path.return_value = path
    node.name.return_value = name
    node.type.return_value.name.return_value = type_name
    return node


def _sop_with_geometry(points: int = 8, prims: int = 6) -> MagicMock:
    node = _node("/obj/geo1/box1", "box1", "box")
    geo = MagicMock()
    geo.points.return_value = [object()] * points
    geo.prims.return_value = [object()] * prims
    node.geometry.return_value = geo
    return node


def _pxr_stub(disk_prim_count: int = 2, open_raises: bool = False) -> dict:
    """Register USD the way Houdini exposes it: as ``pxr.*`` (F3 readback)."""
    pxr = ModuleType("pxr")
    usd = MagicMock()
    if open_raises:
        usd.Stage.Open.side_effect = RuntimeError("bad usd")
    else:
        disk_stage = MagicMock()
        disk_stage.Traverse.return_value = [MagicMock() for _ in range(disk_prim_count)]
        usd.Stage.Open.return_value = disk_stage
    pxr.Usd = usd
    return {"pxr": pxr, "pxr.Usd": usd}


class TestExportSopToUsd:
    def _success_setup(self, tmp_path: Path, stage_prims: int = 2, disk_prims: int = 2):
        """Build a mock Houdini where /stage exists and export writes a file."""
        mod = _load_script("export_sop_to_usd.py")
        out = tmp_path / "box.usd"
        sop = _sop_with_geometry()
        lopnet = _node("/stage", "stage", "lopnet")
        sopimport = _node("/stage/sop_to_usd_import", "sop_to_usd_import", "sopimport")
        stage = MagicMock()
        stage.Traverse.return_value = [MagicMock() for _ in range(stage_prims)]
        prim = MagicMock()
        prim.IsValid.return_value = True
        stage.GetPrimAtPath.return_value = prim
        stage.Export.side_effect = lambda p: Path(p).write_text("#usda 1.0", encoding="utf-8")
        sopimport.stage.return_value = stage
        lopnet.createNode.return_value = sopimport

        mock_hou = MagicMock()
        mock_hou.node.side_effect = lambda p: {
            "/obj/geo1/box1": sop,
            "/stage": lopnet,
        }.get(p)
        modules = _pxr_stub(disk_prims)
        modules["hou"] = mock_hou
        return mod, out, modules, sop, lopnet, sopimport, stage

    def test_export_bridges_sop_to_usd_with_readback(self, tmp_path: Path) -> None:
        mod, out, modules, sop, lopnet, sopimport, stage = self._success_setup(tmp_path)
        with patch.dict(sys.modules, modules):
            result = mod.export_sop_to_usd("/obj/geo1/box1", str(out))

        assert result["success"] is True
        ctx = result["context"]
        assert ctx["written_files"] == [str(out)]
        assert ctx["skipped"] == []
        assert ctx["source_point_count"] == 8
        assert ctx["source_primitive_count"] == 6
        assert ctx["composed_stage_prim_count"] == 2
        assert ctx["composed_stage_prim_count_scope"] == "in_memory_composed_stage"
        assert ctx["disk_prim_count"] == 2
        assert ctx["disk_readback_status"] == "ok"
        assert ctx["prim_path_applied"] is True
        assert ctx["prim_path_parm"] == "primpath"
        assert ctx["prim_path_valid"] is True
        lopnet.createNode.assert_called_once()
        sopimport.cook.assert_called_once_with(force=True)
        stage.Export.assert_called_once_with(str(out))
        sopimport.destroy.assert_called_once()

    # --- F1: only a fresh write may be reported as success -------------------

    def test_export_exception_returns_error(self, tmp_path: Path) -> None:
        mod, out, modules, sop, lopnet, sopimport, stage = self._success_setup(tmp_path)
        stage.Export.side_effect = RuntimeError("disk full")
        with patch.dict(sys.modules, modules):
            result = mod.export_sop_to_usd("/obj/geo1/box1", str(out))
        assert result["success"] is False
        assert not out.exists()
        sopimport.destroy.assert_called_once()

    def test_stale_file_not_reported_as_written_on_export_failure(self, tmp_path: Path) -> None:
        mod, out, modules, sop, lopnet, sopimport, stage = self._success_setup(tmp_path)
        out.write_text("STALE", encoding="utf-8")
        stage.Export.side_effect = RuntimeError("disk full")
        with patch.dict(sys.modules, modules):
            result = mod.export_sop_to_usd("/obj/geo1/box1", str(out))
        assert result["success"] is False
        assert result["context"].get("written_files") != [str(out)]
        assert out.read_text(encoding="utf-8") == "STALE"
        sopimport.destroy.assert_called_once()

    def test_export_writes_nothing_returns_error(self, tmp_path: Path) -> None:
        mod, out, modules, sop, lopnet, sopimport, stage = self._success_setup(tmp_path)
        stage.Export.side_effect = lambda p: None
        with patch.dict(sys.modules, modules):
            result = mod.export_sop_to_usd("/obj/geo1/box1", str(out))
        assert result["success"] is False
        assert not out.exists()

    def test_unchanged_stale_file_returns_error(self, tmp_path: Path) -> None:
        """Export returns without throwing but rewrites nothing -> not a fresh write."""
        mod, out, modules, sop, lopnet, sopimport, stage = self._success_setup(tmp_path)
        out.write_text("STALE", encoding="utf-8")
        stage.Export.side_effect = lambda p: None
        with patch.dict(sys.modules, modules):
            result = mod.export_sop_to_usd("/obj/geo1/box1", str(out))
        assert result["success"] is False

    def test_fresh_overwrite_of_existing_file_is_reported(self, tmp_path: Path) -> None:
        mod, out, modules, sop, lopnet, sopimport, stage = self._success_setup(tmp_path)
        out.write_text("STALE", encoding="utf-8")
        stage.Export.side_effect = lambda p: Path(p).write_text("#usda 1.0 FRESH", encoding="utf-8")
        with patch.dict(sys.modules, modules):
            result = mod.export_sop_to_usd("/obj/geo1/box1", str(out))
        assert result["success"] is True
        assert result["context"]["written_files"] == [str(out)]

    # --- F2: prim_path is reported as applied or not, never asserted blindly --

    def test_prim_path_not_applied_when_no_parm(self, tmp_path: Path) -> None:
        mod, out, modules, sop, lopnet, sopimport, stage = self._success_setup(tmp_path)
        sop_parm = MagicMock()
        sopimport.parm.side_effect = lambda name: sop_parm if name == "soppath" else None
        # With no destination parm applied, the requested prim is absent in the
        # composed stage -> GetPrimAtPath(...).IsValid() is False.
        absent = MagicMock()
        absent.IsValid.return_value = False
        stage.GetPrimAtPath.return_value = absent
        with patch.dict(sys.modules, modules):
            result = mod.export_sop_to_usd("/obj/geo1/box1", str(out), prim_path="/custom/geo")
        assert result["success"] is True
        ctx = result["context"]
        assert ctx["prim_path_applied"] is False
        assert ctx["prim_path_parm"] is None
        assert ctx["prim_path_valid"] is False
        assert any("prim_path was not applied" in w for w in ctx["warnings"])

    # --- F3: disk readback is best-effort and degrades cleanly ---------------

    def test_disk_readback_failure_degrades_with_warning(self, tmp_path: Path) -> None:
        mod, out, modules, sop, lopnet, sopimport, stage = self._success_setup(tmp_path)
        modules.update(_pxr_stub(open_raises=True))
        with patch.dict(sys.modules, modules):
            result = mod.export_sop_to_usd("/obj/geo1/box1", str(out))
        assert result["success"] is True
        ctx = result["context"]
        assert ctx["disk_prim_count"] is None
        assert ctx["disk_readback_status"] == "open_failed"
        assert any("Disk readback unavailable" in w for w in ctx["warnings"])

    def test_pxr_unavailable_degrades_with_warning(self, tmp_path: Path) -> None:
        mod, out, modules, sop, lopnet, sopimport, stage = self._success_setup(tmp_path)
        pxr = ModuleType("pxr")
        pxr.Usd = MagicMock()
        pxr.Usd.Stage = None  # Stage.Open is not callable -> readback unavailable
        modules["pxr"] = pxr
        modules["pxr.Usd"] = pxr.Usd
        with patch.dict(sys.modules, modules):
            result = mod.export_sop_to_usd("/obj/geo1/box1", str(out))
        assert result["success"] is True
        ctx = result["context"]
        assert ctx["disk_prim_count"] is None
        assert ctx["disk_readback_status"] == "pxr_unavailable"

    # --- pre-existing behaviour / error paths ---------------------------------

    def test_creates_transient_lopnet_when_no_stage_parent(self, tmp_path: Path) -> None:
        mod = _load_script("export_sop_to_usd.py")
        sop = _sop_with_geometry()
        root = _node("/", "")
        lopnet = _node("/sop_to_usd_lopnet", "sop_to_usd_lopnet", "lopnet")
        sopimport = _node("/sop_to_usd_lopnet/imp", "imp", "sopimport")
        stage = MagicMock()
        stage.Traverse.return_value = []
        stage.Export.side_effect = lambda p: Path(p).write_text("usd", encoding="utf-8")
        sopimport.stage.return_value = stage
        lopnet.createNode.return_value = sopimport
        root.createNode.return_value = lopnet

        mock_hou = MagicMock()
        mock_hou.node.side_effect = lambda p: {
            "/obj/geo1/box1": sop,
            "/stage": None,
            "/": root,
        }.get(p)
        modules = _pxr_stub(0)
        modules["hou"] = mock_hou
        custom = tmp_path / "custom.usd"
        with patch.dict(sys.modules, modules):
            result = mod.export_sop_to_usd("/obj/geo1/box1", str(custom))

        assert result["success"] is True
        root.createNode.assert_called_once()
        lopnet.destroy.assert_called_once()
        sopimport.destroy.assert_called_once()

    def test_no_houdini_errors(self, tmp_path: Path) -> None:
        mod = _load_script("export_sop_to_usd.py")
        with patch.dict(sys.modules, {"hou": None}):
            result = mod.export_sop_to_usd("/obj/geo1/box1", str(tmp_path / "x.usd"))
        assert result["success"] is False

    def test_missing_sop_node_errors(self, tmp_path: Path) -> None:
        mod = _load_script("export_sop_to_usd.py")
        mock_hou = MagicMock()
        mock_hou.node.return_value = None
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.export_sop_to_usd("/obj/geo1/missing", str(tmp_path / "x.usd"))
        assert result["success"] is False

    def test_node_without_geometry_errors(self, tmp_path: Path) -> None:
        mod = _load_script("export_sop_to_usd.py")
        sop = _sop_with_geometry()
        sop.geometry.return_value = None
        mock_hou = MagicMock()
        mock_hou.node.return_value = sop
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.export_sop_to_usd("/obj/geo1/box1", str(tmp_path / "x.usd"))
        assert result["success"] is False

    def test_no_stage_errors_and_cleans_up(self, tmp_path: Path) -> None:
        mod, out, modules, sop, lopnet, sopimport, stage = self._success_setup(tmp_path)
        sopimport.stage.return_value = None
        with patch.dict(sys.modules, modules):
            result = mod.export_sop_to_usd("/obj/geo1/box1", str(out))
        assert result["success"] is False
        sopimport.destroy.assert_called_once()

    def test_missing_soppath_parm_errors_and_cleans_up(self, tmp_path: Path) -> None:
        mod, out, modules, sop, lopnet, sopimport, stage = self._success_setup(tmp_path)
        sopimport.parm.return_value = None
        with patch.dict(sys.modules, modules):
            result = mod.export_sop_to_usd("/obj/geo1/box1", str(out))
        assert result["success"] is False
        sopimport.destroy.assert_called_once()


class TestExportGeometryUsdGuard:
    def test_usd_suffix_fails_closed_with_redirect(self, tmp_path: Path) -> None:
        mod = _load_script("export_geometry.py")
        out = tmp_path / "box.usd"
        geo = MagicMock()
        node = _node("/obj/geo1/box1", "box1", "box")
        node.geometry.return_value = geo
        mock_hou = MagicMock()
        mock_hou.node.return_value = node
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.export_geometry("/obj/geo1/box1", str(out))
        assert result["success"] is False
        # F4: guard fails closed but must not assert the runtime cannot author USD.
        geo.saveToFile.assert_not_called()
        assert not out.exists()
        assert "cannot author" not in result["message"]
        ctx = result["context"]
        assert ctx["format"] == "usd"
        assert ctx["dcc"]["next_tools"] == ["houdini_interchange__export_sop_to_usd"]

    def test_bgeo_still_writes(self, tmp_path: Path) -> None:
        mod = _load_script("export_geometry.py")
        out = tmp_path / "box.bgeo"
        geo = MagicMock()
        geo.saveToFile.side_effect = lambda p: Path(p).write_bytes(b"geo")
        node = _node("/obj/geo1/box1", "box1", "box")
        node.geometry.return_value = geo
        mock_hou = MagicMock()
        mock_hou.node.return_value = node
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.export_geometry("/obj/geo1/box1", str(out))
        assert result["success"] is True
        geo.saveToFile.assert_called_once_with(str(out))
