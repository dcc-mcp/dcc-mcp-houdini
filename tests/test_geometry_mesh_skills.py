"""Mock-hou unit tests for houdini-geometry and houdini-mesh-ops skills."""

from __future__ import annotations

import importlib.util
import json
import math
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

    def test_create_curve_guides_builds_bounded_root_to_tip_geometry(self) -> None:
        mod = _load_script("houdini-geometry", "create_curve_guides.py")

        class FakePoint:
            def __init__(self) -> None:
                self.position = None
                self.attributes = {}

            def setPosition(self, value) -> None:
                self.position = tuple(value)

            def setAttribValue(self, name, value) -> None:
                self.attributes[name] = value

        class FakePrimitive:
            def __init__(self) -> None:
                self.vertices = []
                self.attributes = {}

            def setIsClosed(self, value) -> None:
                assert value is False

            def addVertex(self, point) -> None:
                self.vertices.append(point)

            def setAttribValue(self, name, value) -> None:
                self.attributes[name] = value

        class FakeBounds:
            def minvec(self):
                return (0.0, 0.0, 0.0)

            def maxvec(self):
                return (2.0, 1.0, 0.0)

            def sizevec(self):
                return (2.0, 1.0, 0.0)

        class FakeGeometry:
            def __init__(self) -> None:
                self.points = []
                self.primitives = []
                self.attributes = []

            def addAttrib(self, owner, name, default):
                self.attributes.append((owner, name, default))
                return name

            def createPoint(self):
                point = FakePoint()
                self.points.append(point)
                return point

            def createPolygon(self, is_closed=True):
                assert is_closed is False
                primitive = FakePrimitive()
                self.primitives.append(primitive)
                return primitive

            def boundingBox(self):
                return FakeBounds()

        geometry = FakeGeometry()
        stash = _node("/obj/groom/guides", "guides", "stash")
        parent = _node("/obj/groom", "groom")
        parent.createNode.return_value = stash
        mock_hou = MagicMock()
        mock_hou.node.return_value = parent
        mock_hou.Geometry.return_value = geometry
        mock_hou.attribType.Point = "point"
        mock_hou.attribType.Prim = "primitive"
        guides = [
            {
                "guide_id": 7,
                "cluster_id": 3,
                "cluster_name": "crown",
                "cvs": [[0, 0, 0], [1, 0.5, 0], [2, 1, 0]],
                "widths": [0.03, 0.02, 0.01],
                "colors": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
            }
        ]

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.create_curve_guides("/obj/groom", guides=guides, node_name="guides")

        assert result["success"] is True
        context = result["context"]
        assert context["node_path"] == "/obj/groom/guides"
        assert context["metrics"]["curve_count"] == 1
        assert context["metrics"]["cv_count"] == 3
        assert context["metrics"]["root_to_tip_valid"] is True
        assert context["attribute_schema"]["point"] == ["u", "root_flag", "Cd", "width"]
        assert context["attribute_schema"]["primitive"] == ["guide_id", "cluster_id", "cluster_name"]
        assert geometry.points[0].attributes["root_flag"] == 1
        assert geometry.points[-1].attributes["u"] == 1.0
        assert geometry.primitives[0].attributes == {
            "guide_id": 7,
            "cluster_id": 3,
            "cluster_name": "crown",
        }
        stash.parm.return_value.set.assert_called_once_with(geometry)

    def test_create_curve_guides_supports_typed_nurbs_topology(self) -> None:
        mod = _load_script("houdini-geometry", "create_curve_guides.py")
        points = [MagicMock() for _ in range(4)]
        vertices = []
        for point in points:
            vertex = MagicMock()
            vertex.point.return_value = point
            vertices.append(vertex)
        primitive = MagicMock()
        primitive.vertices.return_value = vertices
        geometry = MagicMock()
        geometry.createNURBSCurve.return_value = primitive
        geometry.boundingBox.return_value.minvec.return_value = (0, 0, 0)
        geometry.boundingBox.return_value.maxvec.return_value = (3, 1, 0)
        geometry.boundingBox.return_value.sizevec.return_value = (3, 1, 0)
        parent = _node("/obj/groom", "groom")
        parent.createNode.return_value = _node("/obj/groom/nurbs_guides", "nurbs_guides", "stash")
        mock_hou = MagicMock()
        mock_hou.node.return_value = parent
        mock_hou.Geometry.return_value = geometry
        mock_hou.attribType.Point = "point"
        mock_hou.attribType.Prim = "primitive"
        guides = [
            {
                "guide_id": 1,
                "cluster_id": 1,
                "curve_type": "nurbs",
                "order": 4,
                "cvs": [[0, 0, 0], [1, 1, 0], [2, 1, 0], [3, 0, 0]],
            }
        ]

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.create_curve_guides("/obj/groom", guides=guides)

        assert result["success"] is True
        assert result["context"]["topology"] == ["nurbs"]
        geometry.createNURBSCurve.assert_called_once_with(4, False, 4)
        geometry.createPolygon.assert_not_called()

    def test_create_curve_guides_rolls_back_node_when_stash_write_fails(self) -> None:
        mod = _load_script("houdini-geometry", "create_curve_guides.py")
        geometry = MagicMock()
        geometry.boundingBox.return_value.minvec.return_value = (0, 0, 0)
        geometry.boundingBox.return_value.maxvec.return_value = (0, 1, 0)
        geometry.boundingBox.return_value.sizevec.return_value = (0, 1, 0)
        node = _node("/obj/groom/guides", "guides", "stash")
        node.parm.return_value = None
        parent = _node("/obj/groom", "groom")
        parent.createNode.return_value = node
        mock_hou = MagicMock()
        mock_hou.node.return_value = parent
        mock_hou.Geometry.return_value = geometry
        mock_hou.attribType.Point = "point"
        mock_hou.attribType.Prim = "primitive"
        guides = [{"guide_id": 1, "cluster_id": 1, "cvs": [[0, 0, 0], [0, 1, 0]]}]

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.create_curve_guides("/obj/groom", guides=guides)

        assert result["success"] is False
        node.destroy.assert_called_once_with()

    def test_create_curve_guides_reads_bounded_json_file_and_reports_digest(self, tmp_path: Path) -> None:
        mod = _load_script("houdini-geometry", "create_curve_guides.py")
        payload = {
            "guides": [
                {
                    "guide_id": 1,
                    "cluster_id": 2,
                    "cvs": [[0, 0, 0], [0, 1, 0]],
                }
            ]
        }
        source = tmp_path / "guides.json"
        source.write_text(json.dumps(payload), encoding="utf-8")
        parent = _node("/obj/groom", "groom")
        stash = _node("/obj/groom/guides", "guides", "stash")
        parent.createNode.return_value = stash
        geometry = MagicMock()
        point_a = MagicMock()
        point_b = MagicMock()
        geometry.createPoint.side_effect = [point_a, point_b]
        mock_hou = MagicMock()
        mock_hou.node.return_value = parent
        mock_hou.Geometry.return_value = geometry
        mock_hou.attribType.Point = "point"
        mock_hou.attribType.Prim = "primitive"

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.create_curve_guides("/obj/groom", input_file=str(source))

        assert result["success"] is True
        assert result["context"]["source"]["kind"] == "json_file"
        assert len(result["context"]["source"]["sha256"]) == 64
        assert result["context"]["source"]["size_bytes"] == source.stat().st_size

    def test_create_curve_guides_rejects_ambiguous_or_non_finite_input_before_mutation(self) -> None:
        mod = _load_script("houdini-geometry", "create_curve_guides.py")
        guide = {"guide_id": 1, "cluster_id": 1, "cvs": [[0, 0, 0], [math.nan, 1, 0]]}
        mock_hou = MagicMock()

        with patch.dict(sys.modules, {"hou": mock_hou}):
            ambiguous = mod.create_curve_guides("/obj/groom", guides=[guide], input_file="guides.json")
            invalid = mod.create_curve_guides("/obj/groom", guides=[guide])

        assert ambiguous["success"] is False
        assert invalid["success"] is False
        assert invalid["context"]["rejected_guides"][0]["guide_id"] == 1
        mock_hou.node.assert_not_called()

    def test_create_curve_guides_enforces_total_cv_limit(self) -> None:
        mod = _load_script("houdini-geometry", "create_curve_guides.py")
        oversized = [
            {"guide_id": index, "cluster_id": 1, "cvs": [[0, 0, 0], [0, 1, 0]]} for index in range(mod.MAX_GUIDES + 1)
        ]

        result = mod.create_curve_guides("/obj/groom", guides=oversized)

        assert result["success"] is False
        assert "limit" in result["message"].lower()

    def test_get_geometry_info_counts_and_bounds(self) -> None:
        mod = _load_script("houdini-geometry", "get_geometry_info.py")
        bbox = MagicMock()
        bbox.minvec.return_value = (0.0, 0.0, 0.0)
        bbox.maxvec.return_value = (1.0, 2.0, 3.0)
        bbox.sizevec.return_value = (1.0, 2.0, 3.0)

        class PoisonLargeGeometry:
            def pointCount(self):
                return 2_280_000

            def primCount(self):
                return 8_685

            def vertexCount(self):
                return 26_055

            def boundingBox(self):
                return bbox

            def points(self):
                raise AssertionError("get_geometry_info must not enumerate points")

            def prims(self):
                raise AssertionError("get_geometry_info must not enumerate primitives")

            def iterVertices(self):
                raise AssertionError("get_geometry_info must not iterate vertices")

        geo = PoisonLargeGeometry()
        node = _node("/obj/geo1/box1", "box1", "box")
        node.geometry.return_value = geo
        mock_hou = MagicMock()
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.get_geometry_info("/obj/geo1/box1")

        assert result["success"] is True
        ctx = result["context"]
        assert ctx["point_count"] == 2_280_000
        assert ctx["primitive_count"] == 8_685
        assert ctx["vertex_count"] == 26_055
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
