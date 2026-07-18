"""Mock-hou unit tests for houdini-geometry and houdini-mesh-ops skills."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

from skill_loader import skill_script_import_context

_SKILLS_ROOT = Path(__file__).parent.parent / "src" / "dcc_mcp_houdini" / "skills"


def _load_script(skill_name: str, script_name: str) -> ModuleType:
    path = _SKILLS_ROOT / skill_name / "scripts" / script_name
    spec = importlib.util.spec_from_file_location(f"skill_{skill_name}_{path.stem}", path)
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


class TestGeometrySkills:
    def test_create_primitive_creates_box(self) -> None:
        mod = _load_script("houdini-geometry", "create_primitive.py")
        new = _node("/obj/geo1/box1", "box1", "box")
        parent = _node("/obj/geo1", "geo1")
        parent.createNode.return_value = new
        mock_hou = MagicMock()
        mock_hou.node.return_value = parent

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.create_primitive("/obj/geo1", "box")

        assert result["success"] is True
        parent.createNode.assert_called_once_with("box", node_name=None)
        new.setDisplayFlag.assert_called_once_with(True)
        assert result["context"]["node_path"] == "/obj/geo1/box1"

    def test_create_primitive_rejects_unknown(self) -> None:
        mod = _load_script("houdini-geometry", "create_primitive.py")
        with patch.dict(sys.modules, {"hou": MagicMock()}):
            result = mod.create_primitive("/obj/geo1", "torus")
        assert result["success"] is False

    def test_get_geometry_info_counts_and_bounds(self) -> None:
        mod = _load_script("houdini-geometry", "get_geometry_info.py")
        bbox = MagicMock()
        bbox.minvec.return_value = (0.0, 0.0, 0.0)
        bbox.maxvec.return_value = (1.0, 2.0, 3.0)
        bbox.sizevec.return_value = (1.0, 2.0, 3.0)
        geo = MagicMock()
        geo.points.return_value = [1, 2, 3, 4]
        geo.prims.return_value = [1, 2]
        geo.iterVertices.return_value = iter([1, 2, 3, 4, 5, 6, 7, 8])
        geo.boundingBox.return_value = bbox
        node = _node("/obj/geo1/box1", "box1", "box")
        node.geometry.return_value = geo
        mock_hou = MagicMock()
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.get_geometry_info("/obj/geo1/box1")

        assert result["success"] is True
        ctx = result["context"]
        assert ctx["point_count"] == 4
        assert ctx["primitive_count"] == 2
        assert ctx["vertex_count"] == 8
        assert ctx["bounds_max"] == [1.0, 2.0, 3.0]

    def test_list_attributes_groups_by_class(self) -> None:
        mod = _load_script("houdini-geometry", "list_attributes.py")
        attrib = MagicMock()
        attrib.name.return_value = "P"
        attrib.dataType.return_value = "Float"
        attrib.size.return_value = 3
        geo = MagicMock()
        geo.pointAttribs.return_value = [attrib]
        geo.primAttribs.return_value = []
        geo.vertexAttribs.return_value = []
        geo.globalAttribs.return_value = []
        node = _node("/obj/geo1/box1", "box1")
        node.geometry.return_value = geo
        mock_hou = MagicMock()
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.list_attributes("/obj/geo1/box1")

        assert result["success"] is True
        point_attrs = result["context"]["attributes"]["point"]
        assert point_attrs[0]["name"] == "P"
        assert point_attrs[0]["size"] == 3

    def test_list_groups_reports_counts(self) -> None:
        mod = _load_script("houdini-geometry", "list_groups.py")
        group = MagicMock()
        group.name.return_value = "myGroup"
        group.prims.return_value = [1, 2, 3]
        geo = MagicMock()
        geo.pointGroups.return_value = []
        geo.primGroups.return_value = [group]
        geo.edgeGroups.return_value = []
        node = _node("/obj/geo1/box1", "box1")
        node.geometry.return_value = geo
        mock_hou = MagicMock()
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.list_groups("/obj/geo1/box1")

        assert result["success"] is True
        prim_groups = result["context"]["groups"]["primitive"]
        assert prim_groups[0]["name"] == "myGroup"
        assert prim_groups[0]["count"] == 3

    def test_get_cook_status_reports_warnings(self) -> None:
        mod = _load_script("houdini-geometry", "get_cook_status.py")
        node = _node("/obj/geo1/box1", "box1")
        node.errors.return_value = []
        node.warnings.return_value = ["heads up"]
        mock_hou = MagicMock()
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.get_cook_status("/obj/geo1/box1")

        assert result["success"] is True
        assert result["context"]["cooked"] is True
        assert result["context"]["warnings"] == ["heads up"]
        node.cook.assert_called_once_with(force=False)

    def test_get_cook_status_surfaces_cook_error(self) -> None:
        mod = _load_script("houdini-geometry", "get_cook_status.py")
        node = _node("/obj/geo1/box1", "box1")
        node.cook.side_effect = RuntimeError("cook failed")
        node.errors.return_value = ["cook failed"]
        node.warnings.return_value = []
        mock_hou = MagicMock()
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.get_cook_status("/obj/geo1/box1")

        assert result["success"] is True
        assert result["context"]["cooked"] is False
        assert result["context"]["cook_error"] == "cook failed"


class TestMeshOpsSkills:
    def _wire_downstream(self, optype: str = "xform"):
        new = _node(f"/obj/geo1/{optype}1", f"{optype}1", optype)
        parent = _node("/obj/geo1", "geo1")
        parent.createNode.return_value = new
        source = _node("/obj/geo1/box1", "box1", "box")
        source.parent.return_value = parent
        mock_hou = MagicMock()
        mock_hou.node.return_value = source
        return mock_hou, source, parent, new

    def test_transform_geometry_sets_trs(self) -> None:
        mod = _load_script("houdini-mesh-ops", "transform_geometry.py")
        mock_hou, source, parent, new = self._wire_downstream("xform")
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.transform_geometry("/obj/geo1/box1", translate=[1, 0, 0], scale=[2, 2, 2])

        assert result["success"] is True
        parent.createNode.assert_called_once_with("xform", node_name=None)
        new.setInput.assert_called_once_with(0, source)
        assert result["context"]["applied"]["t"] == [1, 0, 0]
        assert result["context"]["applied"]["s"] == [2, 2, 2]

    def test_merge_geometry_wires_all_inputs(self) -> None:
        mod = _load_script("houdini-mesh-ops", "merge_geometry.py")
        merge = _node("/obj/geo1/merge1", "merge1", "merge")
        parent = _node("/obj/geo1", "geo1")
        parent.createNode.return_value = merge
        a = _node("/obj/geo1/box1", "box1", "box")
        b = _node("/obj/geo1/sphere1", "sphere1", "sphere")
        a.parent.return_value = parent
        mock_hou = MagicMock()
        mock_hou.node.side_effect = lambda p: {"/obj/geo1/box1": a, "/obj/geo1/sphere1": b}[p]

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.merge_geometry(["/obj/geo1/box1", "/obj/geo1/sphere1"])

        assert result["success"] is True
        assert result["context"]["input_count"] == 2
        assert merge.setInput.call_count == 2

    def test_merge_geometry_requires_inputs(self) -> None:
        mod = _load_script("houdini-mesh-ops", "merge_geometry.py")
        with patch.dict(sys.modules, {"hou": MagicMock()}):
            result = mod.merge_geometry([])
        assert result["success"] is False

    def test_blast_geometry_sets_group_and_negate(self) -> None:
        mod = _load_script("houdini-mesh-ops", "blast_geometry.py")
        mock_hou, source, parent, new = self._wire_downstream("blast")
        group_parm = MagicMock()
        type_parm = MagicMock()
        negate_parm = MagicMock()
        new.parmTuple.return_value = None
        new.parm.side_effect = lambda name: {
            "group": group_parm,
            "grouptype": type_parm,
            "negate": negate_parm,
        }.get(name)

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.blast_geometry("/obj/geo1/box1", group="0-5", group_type="prims", delete_non_selected=True)

        assert result["success"] is True
        group_parm.set.assert_called_once_with("0-5")
        type_parm.set.assert_called_once_with(4)
        negate_parm.set.assert_called_once_with(1)

    def test_group_geometry_sets_name_and_type(self) -> None:
        mod = _load_script("houdini-mesh-ops", "group_geometry.py")
        mock_hou, source, parent, new = self._wire_downstream("groupcreate")
        name_parm = MagicMock()
        type_parm = MagicMock()
        new.parmTuple.return_value = None
        new.parm.side_effect = lambda n: {"groupname": name_parm, "grouptype": type_parm}.get(n)

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.group_geometry("/obj/geo1/box1", group_name="top", group_type="points")

        assert result["success"] is True
        name_parm.set.assert_called_once_with("top")
        type_parm.set.assert_called_once_with(0)

    def test_add_normals_sets_class(self) -> None:
        mod = _load_script("houdini-mesh-ops", "add_normals.py")
        mock_hou, source, parent, new = self._wire_downstream("normal")
        type_parm = MagicMock()
        new.parmTuple.return_value = None
        new.parm.side_effect = lambda n: type_parm if n == "type" else None

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.add_normals("/obj/geo1/box1", attribute_class="vertex")

        assert result["success"] is True
        type_parm.set.assert_called_once_with(1)

    def test_triangulate_sets_convex(self) -> None:
        mod = _load_script("houdini-mesh-ops", "triangulate_geometry.py")
        mock_hou, source, parent, new = self._wire_downstream("divide")
        convex_parm = MagicMock()
        sides_parm = MagicMock()
        new.parmTuple.return_value = None
        new.parm.side_effect = lambda n: {"convex": convex_parm, "numsides": sides_parm}.get(n)

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.triangulate_geometry("/obj/geo1/box1")

        assert result["success"] is True
        convex_parm.set.assert_called_once_with(1)
        sides_parm.set.assert_called_once_with(3)

    def test_convert_geometry_maps_token(self) -> None:
        mod = _load_script("houdini-mesh-ops", "convert_geometry.py")
        mock_hou, source, parent, new = self._wire_downstream("convert")
        totype_parm = MagicMock()
        new.parmTuple.return_value = None
        new.parm.side_effect = lambda n: totype_parm if n == "totype" else None

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.convert_geometry("/obj/geo1/box1", to_type="polygons")

        assert result["success"] is True
        totype_parm.set.assert_called_once_with("poly")
        assert result["context"]["to_type"] == "poly"

    def test_convert_geometry_rejects_unknown(self) -> None:
        mod = _load_script("houdini-mesh-ops", "convert_geometry.py")
        with patch.dict(sys.modules, {"hou": MagicMock()}):
            result = mod.convert_geometry("/obj/geo1/box1", to_type="voxels")
        assert result["success"] is False
