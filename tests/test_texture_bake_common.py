"""Mock-hou unit tests for houdini-texture-bake shared helpers."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

from skill_loader import skill_script_import_context

_SKILLS_ROOT = Path(__file__).parent.parent / "src" / "dcc_mcp_houdini" / "skills"


def _load_module() -> ModuleType:
    path = _SKILLS_ROOT / "houdini-texture-bake" / "scripts" / "_texture_bake_common.py"
    spec = importlib.util.spec_from_file_location("_texture_bake_common", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    with skill_script_import_context(spec):
        spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# detect_bake_methods
# ---------------------------------------------------------------------------


class TestDetectBakeMethods:
    def test_labs_and_rop_both_available(self) -> None:
        mod = _load_module()
        mock_hou = MagicMock()
        # nodeType returns non-None for both categories → both methods detected
        mock_hou.nodeType.return_value = MagicMock()  # not None

        result = mod.detect_bake_methods(mock_hou)

        assert result["labs_maps_baker_available"] is True
        assert result["bake_texture_rop_available"] is True
        assert "labs_maps_baker" in result["available_methods"]
        assert "bake_texture_rop" in result["available_methods"]
        assert "cop_fallback" in result["available_methods"]
        assert result["recommended"] == "labs_maps_baker"
        assert result["recommendations"] == []

    def test_only_rop_available(self) -> None:
        mod = _load_module()
        mock_hou = MagicMock()

        # vopNodeTypeCategory returns None (labs not available)
        vop_cat = MagicMock()
        # ropNodeTypeCategory returns non-None (rop available)
        rop_cat = MagicMock()
        mock_hou.vopNodeTypeCategory.return_value = vop_cat
        mock_hou.ropNodeTypeCategory.return_value = rop_cat

        # nodeType returns None for vop lookup, MagicMock for rop lookup
        def _nt(cat, type_name=None):
            if cat is vop_cat:
                return None
            return MagicMock()

        mock_hou.nodeType.side_effect = _nt

        result = mod.detect_bake_methods(mock_hou)

        assert result["labs_maps_baker_available"] is False
        assert result["bake_texture_rop_available"] is True
        assert result["recommended"] == "bake_texture_rop"
        assert "Install sidefx_labs" in result["recommendations"][0]

    def test_nothing_available_cop_fallback_only(self) -> None:
        mod = _load_module()
        mock_hou = MagicMock()
        mock_hou.nodeType.return_value = None  # nothing available

        result = mod.detect_bake_methods(mock_hou)

        assert result["labs_maps_baker_available"] is False
        assert result["bake_texture_rop_available"] is False
        assert result["available_methods"] == ["cop_fallback"]
        assert result["recommended"] == "cop_fallback"
        assert len(result["recommendations"]) == 1

    def test_labs_detect_swallows_exceptions(self) -> None:
        mod = _load_module()
        mock_hou = MagicMock()
        mock_hou.nodeType.side_effect = RuntimeError("boom")

        result = mod.detect_bake_methods(mock_hou)

        assert result["labs_maps_baker_available"] is False
        assert result["bake_texture_rop_available"] is False


# ---------------------------------------------------------------------------
# validate_map_types
# ---------------------------------------------------------------------------


class TestValidateMapTypes:
    def test_all_valid(self) -> None:
        mod = _load_module()
        valid, invalid = mod.validate_map_types(["normals", "cavity", "diffuse"])
        assert valid == ["normals", "cavity", "diffuse"]
        assert invalid == []

    def test_all_invalid(self) -> None:
        mod = _load_module()
        valid, invalid = mod.validate_map_types(["unicorn", "rainbow", "glitter"])
        assert valid == []
        assert invalid == ["unicorn", "rainbow", "glitter"]

    def test_mixed_valid_and_invalid(self) -> None:
        mod = _load_module()
        valid, invalid = mod.validate_map_types(["normals", "bogus", "curvature", "nope"])
        assert valid == ["normals", "curvature"]
        assert invalid == ["bogus", "nope"]

    def test_empty_list(self) -> None:
        mod = _load_module()
        valid, invalid = mod.validate_map_types([])
        assert valid == []
        assert invalid == []

    def test_all_vocabulary_types_returned_as_valid(self) -> None:
        mod = _load_module()
        all_types = [
            "normals",
            "cavity",
            "curvature",
            "diffuse",
            "roughness",
            "metallic",
            "thickness",
            "world_position",
            "opacity",
            "ambient_occlusion",
            "displacement",
            "height",
            "emission",
            "scattering",
            "transmission",
            "basecolor",
            "specular",
            "subsurface",
            "anisotropy",
            "coat",
            "sheen",
        ]
        valid, invalid = mod.validate_map_types(all_types)
        assert valid == all_types
        assert invalid == []


# ---------------------------------------------------------------------------
# check_uvs
# ---------------------------------------------------------------------------


class TestCheckUvs:
    def _make_geo_with_uv(self, uv_name: str = "uv") -> MagicMock:
        geo = MagicMock()
        pt_attr = MagicMock()
        pt_attr.dataType.return_value = "Float"
        pt_attr.size.return_value = 2
        pt_attr.name.return_value = uv_name
        geo.pointAttribs.return_value = [pt_attr]
        geo.vertexAttribs.return_value = []
        return geo

    def _make_mock_hou(self, geo: MagicMock | None) -> MagicMock:
        mock_hou = MagicMock()
        mock_hou.attribData = MagicMock()
        mock_hou.attribData.Float = "Float"

        display = MagicMock()
        display.geometry.return_value = geo

        node = MagicMock()
        node.displayNode.return_value = display
        mock_hou.node.return_value = node

        return mock_hou

    def test_returns_uv_attribute_name(self) -> None:
        mod = _load_module()
        geo = self._make_geo_with_uv("uv")
        mock_hou = self._make_mock_hou(geo)

        result = mod.check_uvs(mock_hou, "/obj/geo1")
        assert result == ["uv"]

    def test_returns_multiple_uv_layers(self) -> None:
        mod = _load_module()
        geo = MagicMock()
        uv1 = MagicMock()
        uv1.dataType.return_value = "Float"
        uv1.size.return_value = 2
        uv1.name.return_value = "uv"
        uv2 = MagicMock()
        uv2.dataType.return_value = "Float"
        uv2.size.return_value = 2
        uv2.name.return_value = "uv2"
        geo.pointAttribs.return_value = [uv1, uv2]
        geo.vertexAttribs.return_value = []

        mock_hou = self._make_mock_hou(geo)
        result = mod.check_uvs(mock_hou, "/obj/geo1")
        assert set(result) == {"uv", "uv2"}

    def test_node_not_found_returns_none(self) -> None:
        mod = _load_module()
        mock_hou = MagicMock()
        mock_hou.node.return_value = None

        result = mod.check_uvs(mock_hou, "/obj/nope")
        assert result is None

    def test_no_display_node_returns_none(self) -> None:
        mod = _load_module()
        mock_hou = MagicMock()
        node = MagicMock()
        del node.displayNode  # hasattr returns False
        mock_hou.node.return_value = node

        result = mod.check_uvs(mock_hou, "/obj/geo1")
        assert result is None

    def test_no_geometry_returns_none(self) -> None:
        mod = _load_module()
        mock_hou = self._make_mock_hou(None)
        result = mod.check_uvs(mock_hou, "/obj/geo1")
        assert result is None

    def test_no_uv_attributes_returns_empty_list(self) -> None:
        mod = _load_module()
        geo = MagicMock()
        geo.pointAttribs.return_value = []
        geo.vertexAttribs.return_value = []
        mock_hou = self._make_mock_hou(geo)

        result = mod.check_uvs(mock_hou, "/obj/geo1")
        assert result == []

    def test_vertex_uvs_detected(self) -> None:
        mod = _load_module()
        mock_hou = MagicMock()
        mock_hou.attribData = MagicMock()
        mock_hou.attribData.Float = "Float"

        # Build vertex attribute with real method-mocks inline
        geo = MagicMock()
        geo.pointAttribs.return_value = []
        vtx_attr = MagicMock()
        vtx_attr.dataType = MagicMock(return_value="Float")
        vtx_attr.size = MagicMock(return_value=2)
        vtx_attr.name = MagicMock(return_value="uv1")
        geo.vertexAttribs.return_value = [vtx_attr]

        display = MagicMock()
        display.geometry.return_value = geo
        node = MagicMock()
        node.displayNode.return_value = display
        mock_hou.node.return_value = node

        result = mod.check_uvs(mock_hou, "/obj/geo1")
        assert result == ["uv1"]

    def test_skips_non_float_attribs(self) -> None:
        mod = _load_module()
        geo = MagicMock()
        pt_attr = MagicMock()
        pt_attr.dataType.return_value = "Int"  # not Float
        pt_attr.size.return_value = 2
        pt_attr.name.return_value = "uv"
        geo.pointAttribs.return_value = [pt_attr]
        geo.vertexAttribs.return_value = []
        mock_hou = self._make_mock_hou(geo)

        result = mod.check_uvs(mock_hou, "/obj/geo1")
        assert result == []

    def test_skips_non_2d_attribs(self) -> None:
        mod = _load_module()
        geo = MagicMock()
        pt_attr = MagicMock()
        pt_attr.configure_mock(**{"dataType.return_value": "Float", "size.return_value": 1, "name.return_value": "uv"})
        geo.pointAttribs.return_value = [pt_attr]
        geo.vertexAttribs.return_value = []
        mock_hou = self._make_mock_hou(geo)

        result = mod.check_uvs(mock_hou, "/obj/geo1")
        assert result == []


# ---------------------------------------------------------------------------
# bake_geometry_info
# ---------------------------------------------------------------------------


class TestBakeGeometryInfo:
    def test_node_not_found(self) -> None:
        mod = _load_module()
        mock_hou = MagicMock()
        mock_hou.node.return_value = None

        result = mod.bake_geometry_info(mock_hou, "/obj/nope")
        assert result is None

    def test_no_display_geometry(self) -> None:
        mod = _load_module()
        mock_hou = MagicMock()
        mock_hou.attribData = MagicMock()
        mock_hou.attribData.Float = "Float"
        node = MagicMock()
        node.name.return_value = "geo1"
        del node.displayNode
        mock_hou.node.return_value = node

        result = mod.bake_geometry_info(mock_hou, "/obj/geo1")
        assert result is not None
        assert result["path"] == "/obj/geo1"
        assert result["has_display_geo"] is False
        assert result["bake_ready"] is False
        assert result["primitive_count"] == 0

    def test_obj_with_uvs_and_prims(self) -> None:
        mod = _load_module()
        mock_hou = MagicMock()
        mock_hou.attribData = MagicMock()
        mock_hou.attribData.Float = "Float"
        # Set up display geometry
        geo = MagicMock()
        prim = MagicMock()
        geo.iterPrims.return_value = [prim]
        geo.pointAttribs.return_value = []
        geo.vertexAttribs.return_value = []
        display = MagicMock()
        display.geometry.return_value = geo
        node = MagicMock()
        node.name.return_value = "geo1"
        node.displayNode.return_value = display
        mock_hou.node.return_value = node

        result = mod.bake_geometry_info(mock_hou, "/obj/geo1")
        assert result is not None
        assert result["name"] == "geo1"
        assert result["type"] == "obj"
        assert result["has_display_geo"] is True
        assert result["primitive_count"] == 1
        # No UVs → not bake ready
        assert result["has_uvs"] is False
        assert result["bake_ready"] is False

    def test_sop_node_type(self) -> None:
        mod = _load_module()
        mock_hou = MagicMock()
        mock_hou.attribData = MagicMock()
        mock_hou.attribData.Float = "Float"
        geo = MagicMock()
        geo.iterPrims.return_value = []
        geo.pointAttribs.return_value = []
        geo.vertexAttribs.return_value = []
        display = MagicMock()
        display.geometry.return_value = geo
        node = MagicMock()
        node.name.return_value = "sphere1"
        node.displayNode.return_value = display
        mock_hou.node.return_value = node

        result = mod.bake_geometry_info(mock_hou, "/sop/path/sphere1")
        assert result is not None
        assert result["type"] == "sop"
        assert result["bake_ready"] is False  # no UVs, no primitives

    def test_bake_ready_when_has_uvs_and_primitives(self) -> None:
        mod = _load_module()
        mock_hou = MagicMock()
        mock_hou.attribData = MagicMock()
        mock_hou.attribData.Float = "Float"
        geo = MagicMock()
        prim = MagicMock()
        geo.iterPrims.return_value = [prim, prim, prim]  # 3 primitives
        uv_attr = MagicMock()
        uv_attr.dataType.return_value = "Float"
        uv_attr.size.return_value = 2
        uv_attr.name.return_value = "uv"
        geo.pointAttribs.return_value = [uv_attr]
        geo.vertexAttribs.return_value = []
        display = MagicMock()
        display.geometry.return_value = geo
        node = MagicMock()
        node.name.return_value = "geo1"
        node.displayNode.return_value = display
        mock_hou.node.return_value = node

        result = mod.bake_geometry_info(mock_hou, "/obj/geo1")
        assert result is not None
        assert result["has_uvs"] is True
        assert result["uv_layers"] == ["uv"]
        assert result["primitive_count"] == 3
        assert result["bake_ready"] is True


# ---------------------------------------------------------------------------
# collect_geometry
# ---------------------------------------------------------------------------


class TestCollectGeometry:
    def test_explicit_object_list_passed_through(self) -> None:
        mod = _load_module()
        mock_hou = MagicMock()
        result = mod.collect_geometry(mock_hou, ["/obj/geo1", "/obj/geo2"])
        assert result == ["/obj/geo1", "/obj/geo2"]

    def test_returns_empty_when_obj_root_missing(self) -> None:
        mod = _load_module()
        mock_hou = MagicMock()
        mock_hou.node.return_value = None

        result = mod.collect_geometry(mock_hou, None)
        assert result == []

    def test_collects_renderable_children(self) -> None:
        mod = _load_module()
        mock_hou = MagicMock()
        # Child with displayNode
        child1 = MagicMock()
        child1.path.return_value = "/obj/geo1"
        display1 = MagicMock()
        child1.displayNode.return_value = display1
        # Child without displayNode
        child2 = MagicMock()
        del child2.displayNode
        # Child with displayNode that returns None
        child3 = MagicMock()
        child3.displayNode.return_value = None
        child3.path.return_value = "/obj/geo3"

        root = MagicMock()
        root.children.return_value = [child1, child2, child3]
        mock_hou.node.return_value = root

        result = mod.collect_geometry(mock_hou, None)
        assert result == ["/obj/geo1"]


# ---------------------------------------------------------------------------
# validate_map_types (edge)
# ---------------------------------------------------------------------------


class TestValidateMapTypesEdgeCases:
    def test_duplicates_preserved_in_valid(self) -> None:
        mod = _load_module()
        valid, invalid = mod.validate_map_types(["diffuse", "diffuse"])
        assert valid == ["diffuse", "diffuse"]
        assert invalid == []

    def test_case_sensitive(self) -> None:
        mod = _load_module()
        valid, invalid = mod.validate_map_types(["Diffuse", "DIFFUSE"])
        assert valid == []
        assert invalid == ["Diffuse", "DIFFUSE"]
