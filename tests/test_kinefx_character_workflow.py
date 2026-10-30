"""Tests for the houdini-kinefx character-animation workflow tools.

Covers the pure headless layer (design, planning, naming maps, rig-inversion
linear algebra) and the scene tools with a mock ``hou``. No licensed Houdini is
required; visual/cook acceptance is a separate QA step.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest
from skill_loader import skill_script_import_context

_SKILLS_ROOT = Path(__file__).parent.parent / "src" / "dcc_mcp_houdini" / "skills"
_SCRIPTS = _SKILLS_ROOT / "houdini-kinefx" / "scripts"


def _load_script(script_name: str) -> ModuleType:
    path = _SCRIPTS / script_name
    spec = importlib.util.spec_from_file_location("cwf_{}".format(path.stem), path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    with skill_script_import_context(spec):
        spec.loader.exec_module(module)
    return module


def _load_common() -> ModuleType:
    return _load_script("_character_common.py")


def _identity():
    """4x4 identity (Houdini row-vector, row-major)."""
    return (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)


def _translated(x, y=0.0, z=0.0):
    """Translation in the BOTTOM ROW (slots 12/13/14), Houdini row-vector."""
    return (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, x, y, z, 1)


# 90-degree CCW rotation about Z in Houdini row-vector form. (1,0,0) -> (0,1,0).
_ROT_Z90 = (0, 1, 0, 0, -1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)


# ---------------------------------------------------------------------------
# Pure shared module
# ---------------------------------------------------------------------------


class TestCharacterCommon:
    def test_conventions_cover_all_canonical_keys(self) -> None:
        mod = _load_common()
        keys = {key for key, _, _ in mod.BIPED_SPEC}
        assert len(keys) == 22
        for convention in mod.CONVENTIONS:
            names = mod.convention_names(convention)
            assert set(names.keys()) == keys
            assert len(set(names.values())) == 22, convention

    def test_convention_specific_names(self) -> None:
        mod = _load_common()
        assert mod.convention_names("kinefx")["hips"] == "Hips"
        assert mod.convention_names("mixamo")["hips"] == "mixamorig:Hips"
        assert "Bip01" in mod.convention_names("biped")["hips"]
        assert mod.convention_names("unreal")["hips"] == "pelvis"
        assert mod.convention_names("unreal")["calf_r"] == "calf_r"

    def test_unknown_convention_raises(self) -> None:
        mod = _load_common()
        with pytest.raises(ValueError):
            mod.convention_names("nope")

    def test_biped_joint_map_roundtrip(self) -> None:
        mod = _load_common()
        result = mod.biped_joint_map("mixamo", "kinefx")
        assert result["joint_count"] == 22
        assert result["pairs"]["mixamorig:Hips"] == "Hips"
        assert result["reverse_pairs"]["Hips"] == "mixamorig:Hips"

    def test_biped_chain_scaling_and_hierarchy(self) -> None:
        mod = _load_common()
        chain = mod.biped_chain(3.4, "kinefx", ground_z=0.0)
        assert len(chain["joint_chain"]) == 22
        assert chain["joint_chain"][0]["parent_index"] == -1
        # Root of the canonical skeleton is scaled ~2x for height 3.4.
        assert chain["joint_chain"][0]["translate"][1] == pytest.approx(1.8, abs=0.2)
        # Feet rest on ground_z.
        min_y = min(j["translate"][1] for j in chain["joint_chain"])
        assert min_y == pytest.approx(0.0)
        # Every non-root parent references a valid earlier joint.
        for index, parent in enumerate(chain["parent_indices"]):
            assert parent < index

    def test_biped_chain_rejects_bad_height(self) -> None:
        mod = _load_common()
        with pytest.raises(ValueError):
            mod.biped_chain(0, "kinefx")

    def test_compute_local_transforms_fk_inverse(self) -> None:
        mod = _load_common()
        worlds = [_identity(), _translated(5.0), _translated(2.0)]
        parents = [-1, 0, 0]
        local = mod.compute_local_transforms(worlds, parents)
        # Houdini row-vector convention: translation is in slot 12 (bottom row).
        assert local[0][12] == pytest.approx(0.0)  # root at origin
        assert local[1][12] == pytest.approx(5.0)  # child world tx
        assert local[2][12] == pytest.approx(2.0)

    def test_compute_local_transforms_grandchild(self) -> None:
        mod = _load_common()
        # root at 10, child at 12 (local +2), grandchild at 17 (local +5).
        worlds = [_translated(10.0), _translated(12.0), _translated(17.0)]
        parents = [-1, 0, 1]
        local = mod.compute_local_transforms(worlds, parents)
        assert local[1][12] == pytest.approx(2.0)
        assert local[2][12] == pytest.approx(5.0)

    def test_rotated_parent_known_answer(self) -> None:
        """A rotated parent must not mirror the child rotation on inversion.

        parent world = 90-degree CCW rotation about Z (no translation).
        child local  = pure translation (2, 0, 0).
        FK (row-vector): world[child] = local[child] * world[parent], which
        yields a child world matrix with translation (0, 2, 0). Inverting must
        recover the original local transform exactly -- a wrong multiplication
        order (inverse on the left) mirrors the rotation and fails this test.
        """
        mod = _load_common()
        parent_world = _ROT_Z90
        child_local = _translated(2.0)
        child_world = mod._mat4_mul(child_local, parent_world)
        # Known-answer child world matrix (computed once, asserted explicitly).
        assert child_world == pytest.approx((0, 1, 0, 0, -1, 0, 0, 0, 0, 0, 1, 0, 0, 2, 0, 1))
        local = mod.compute_local_transforms([parent_world, child_world], [-1, 0])
        assert local[0] == pytest.approx(parent_world)  # root unchanged
        assert local[1] == pytest.approx(child_local)  # rotation NOT mirrored
        assert local[1][12] == pytest.approx(2.0)  # bottom-row translation
        assert local[1][3] == pytest.approx(0.0)  # nothing in last column

    def test_compute_local_transforms_rejects_bad_input(self) -> None:
        mod = _load_common()
        with pytest.raises(ValueError):
            mod.compute_local_transforms([_identity()], [-1, 0])
        with pytest.raises(ValueError):
            mod.compute_local_transforms([_identity()], [1])  # self-parent
        with pytest.raises(ValueError):
            mod.compute_local_transforms([(1, 2, 3)], [-1])  # bad matrix length

    def test_mat4_inverse_identity(self) -> None:
        mod = _load_common()
        assert mod._mat4_inverse(_identity()) == pytest.approx(_identity())


# ---------------------------------------------------------------------------
# Pure/headless tools
# ---------------------------------------------------------------------------


class TestPlanCharacterWorkflow:
    def test_returns_full_design(self) -> None:
        mod = _load_script("plan_character_workflow.py")
        result = mod.plan_character_workflow()
        assert result["success"] is True
        ctx = result["context"]
        assert ctx["stage_count"] == 8
        assert [s["order"] for s in ctx["stages"]] == list(range(1, 9))
        assert "codex" in ctx["external_capabilities"]
        assert "hyper3d" in ctx["external_capabilities"]
        assert ctx["design_doc"].endswith(".md")
        assert any(g["kind"] == "gap" for g in ctx["gaps_and_enhancements"])
        assert any(e["kind"] == "enhancement" for e in ctx["gaps_and_enhancements"])

    def test_external_overrides(self) -> None:
        mod = _load_script("plan_character_workflow.py")
        ctx = mod.plan_character_workflow(codex_available=True, hyper3d_available=False)["context"]
        assert ctx["external_capabilities"]["codex"]["bound_to_adapter"] is True
        assert ctx["external_capabilities"]["hyper3d"]["bound_to_adapter"] is False

    def test_all_stages_have_tools(self) -> None:
        mod = _load_script("plan_character_workflow.py")
        ctx = mod.plan_character_workflow()["context"]
        for stage in ctx["stages"]:
            assert stage["tools"], stage["id"]


class TestDesignCharacter:
    def test_generates_valid_spec(self) -> None:
        mod = _load_script("design_character.py")
        result = mod.design_character(name="hero", height=1.8, naming_convention="mixamo")
        assert result["success"] is True
        assert result["context"]["validated"] is True
        spec = result["context"]["design_spec"]
        assert spec["name"] == "hero"
        assert spec["target_height"] == 1.8
        assert spec["naming_convention"] == "mixamo"
        assert spec["skeleton"]["naming"]["hips"] == "mixamorig:Hips"

    def test_validates_external_spec(self) -> None:
        mod = _load_script("design_character.py")
        external = {"name": "npc", "target_height": 2.0, "naming_convention": "unreal"}
        result = mod.design_character(spec=external)
        assert result["success"] is True
        assert result["context"]["source"] == "external"
        assert result["context"]["design_spec"] == external

    def test_rejects_bad_external_spec(self) -> None:
        mod = _load_script("design_character.py")
        result = mod.design_character(spec={"name": "x"})
        assert result["success"] is False
        assert "errors" in result["context"]

    def test_rejects_unknown_convention_and_height(self) -> None:
        mod = _load_script("design_character.py")
        assert mod.design_character(naming_convention="nope")["success"] is False
        assert mod.design_character(height=-1)["success"] is False
        assert mod.design_character(style="nope")["success"] is False


class TestBipedJointMapTool:
    def test_returns_map(self) -> None:
        mod = _load_script("biped_joint_map.py")
        result = mod.biped_joint_map("mixamo", "unreal")
        assert result["success"] is True
        ctx = result["context"]
        assert ctx["joint_count"] == 22
        assert ctx["pairs"]["mixamorig:Hips"] == "pelvis"

    def test_rejects_bad_convention(self) -> None:
        mod = _load_script("biped_joint_map.py")
        assert mod.biped_joint_map("nope", "kinefx")["success"] is False


class TestInvertRigHeadless:
    def test_headless_mode_no_hou(self) -> None:
        mod = _load_script("invert_rig.py")
        worlds = [_identity(), _translated(3.0)]
        result = mod.invert_rig(world_matrices=worlds, parent_indices=[-1, 0])
        assert result["success"] is True
        assert result["context"]["mode"] == "headless"
        assert result["context"]["joint_count"] == 2
        assert result["context"]["local_transforms"][1][12] == pytest.approx(3.0)

    def test_headless_rotated_parent_known_answer(self) -> None:
        """Headless path must not mirror a rotated parent's rotation (review F3)."""
        mod = _load_script("invert_rig.py")
        parent_world = _ROT_Z90
        child_local = _translated(2.0)
        common = _load_common()
        child_world_matrix = common._mat4_mul(child_local, parent_world)
        result = mod.invert_rig(world_matrices=[parent_world, child_world_matrix], parent_indices=[-1, 0])
        assert result["success"] is True, result
        local = result["context"]["local_transforms"]
        assert local[0] == pytest.approx(parent_world)
        assert local[1] == pytest.approx(child_local)
        assert result["context"]["convention"] == "houdini_row_vector"

    def test_point_world_from_bottom_row_translation(self) -> None:
        """_point_world_from must place P in slots 12/13/14, not 3/7/11 (F3)."""
        mod = _load_script("invert_rig.py")
        identity3 = (1, 0, 0, 0, 1, 0, 0, 0, 1)
        world = mod._point_world_from(identity3, (4.0, 5.0, 6.0))
        assert (world[12], world[13], world[14]) == pytest.approx((4.0, 5.0, 6.0))
        assert (world[3], world[7], world[11]) == pytest.approx((0.0, 0.0, 0.0))
        assert (world[0], world[1], world[2], world[4], world[5], world[6]) == pytest.approx((1, 0, 0, 0, 1, 0))
        # A 16-value transform keeps its 3x3 rotation but P stays authoritative
        # for translation (KineFX stores the joint position in P).
        full = (0, 1, 0, 0, -1, 0, 0, 0, 0, 0, 1, 0, 1, 2, 3, 1)
        world16 = mod._point_world_from(full, (9.0, 9.0, 9.0))
        assert (world16[0], world16[1], world16[2]) == pytest.approx((0, 1, 0))
        assert (world16[4], world16[5], world16[6]) == pytest.approx((-1, 0, 0))
        assert (world16[12], world16[13], world16[14]) == pytest.approx((9.0, 9.0, 9.0))

    def test_headless_requires_both_inputs(self) -> None:
        mod = _load_script("invert_rig.py")
        assert mod.invert_rig(world_matrices=[_identity()])["success"] is False

    def test_no_input_errors(self) -> None:
        mod = _load_script("invert_rig.py")
        assert mod.invert_rig()["success"] is False

    def test_headless_rejects_singular(self) -> None:
        mod = _load_script("invert_rig.py")
        zero = (0,) * 16  # singular parent transform
        result = mod.invert_rig(world_matrices=[zero, _identity()], parent_indices=[-1, 0])
        assert result["success"] is False

    def _vertex(self, point_number):
        v = MagicMock()
        v.point.return_value.number.return_value = point_number
        return v

    def test_parent_indices_no_incoming_edge_is_root(self) -> None:
        """N1: points with no incoming edge must be roots (-1), not previous point.

        Skeleton with 4 points and edges 2->0 and 2->1 (root at index 2, plus
        an isolated point 3). Every point not a child in an edge polygon is a
        root; the old linear-chain fallback wrongly kept index-1 as parent.
        """
        mod = _load_script("invert_rig.py")
        geometry = MagicMock()

        def prim(parent, child):
            p = MagicMock()
            p.vertices.return_value = [self._vertex(parent), self._vertex(child)]
            return p

        geometry.prims.return_value = [prim(2, 0), prim(2, 1)]
        parents = mod._parent_indices(geometry, 4)
        assert parents == [2, 2, -1, -1]

    def test_parent_indices_no_edges_linear_chain(self) -> None:
        """N1: with no edges the linear-chain fallback is unchanged."""
        mod = _load_script("invert_rig.py")
        geometry = MagicMock()
        geometry.prims.return_value = []
        assert mod._parent_indices(geometry, 3) == [-1, 0, 1]


# ---------------------------------------------------------------------------
# Mock-hou scene tools
# ---------------------------------------------------------------------------


def _mock_node(path):
    node = MagicMock()
    node.path.return_value = path
    node.parm.return_value = MagicMock()
    node.errors.return_value = ()
    node.warnings.return_value = ()
    node.geometry.return_value = MagicMock()
    return node


def _mock_container(hou, geo_path="/obj/char", create_paths=None):
    """Wire a mock hou whose createNode returns predictable mock nodes."""
    container = _mock_node(geo_path)
    container.path.return_value = geo_path
    created = {}

    def create_node(type_name, node_name=None, **kwargs):
        name = node_name or type_name.split("::")[-1]
        node = _mock_node("{}/{}".format(geo_path, name))
        node.type_name = type_name
        created[name] = node
        return node

    container.createNode.side_effect = create_node
    container.parent.return_value = container
    container.layoutChildren.return_value = None
    return container, created


def _mock_point(position, name, transform=None):
    pt = MagicMock()
    pt.position.return_value = position
    if transform is None:
        transform = (1, 0, 0, 0, 1, 0, 0, 0, 1)
    values = {"name": name, "transform": transform, "localtransform": transform}

    def attrib_value(key, _values=values):
        if isinstance(key, str):
            return _values.get(key, "")
        return _values.get("transform")

    pt.attribValue.side_effect = attrib_value
    return pt


def _mock_invert_scene_hou(stash=True, cook_errors=()):
    """Mock hou for invert_rig scene mode using the fresh-geometry pattern."""
    hou = MagicMock()
    source_points = [
        _mock_point((0.0, 0.0, 0.0), "Hips"),
        _mock_point((0.0, 1.0, 0.0), "Spine"),
    ]
    geometry = MagicMock()
    geometry.points.return_value = source_points
    geometry.findPointAttrib.return_value = MagicMock()  # transform + name present
    geometry.prims.return_value = []  # linear-chain fallback

    rig = _mock_node("/obj/char/rig")
    rig.geometry.return_value = geometry

    container, created = _mock_container(hou)
    out_node = created.setdefault("inverted_rig", _mock_node("/obj/char/inverted_rig"))
    # Force createNode to return our out_node regardless of name.
    container.createNode.side_effect = None
    container.createNode.return_value = out_node
    out_node.parm.return_value = MagicMock() if stash else None
    out_node.errors.return_value = cook_errors
    rig.parent.return_value = container

    editable = MagicMock()
    new_points = [_mock_point((0.0, 0.0, 0.0), ""), _mock_point((0.0, 0.0, 0.0), "")]
    editable.createPoints.return_value = new_points
    # Distinct sentinels per attribute so tests can assert which value was
    # written where (localtransform must receive the full 16-value matrix4).
    attr_mocks = {}

    def add_attrib(kind, name, default, _am=attr_mocks):
        handle = MagicMock()
        handle.name = name
        handle.default = default
        _am[name] = handle
        return handle

    editable.addAttrib.side_effect = add_attrib
    editable.attr_mocks = attr_mocks
    editable.createPolygon.return_value = MagicMock()
    hou.Geometry.return_value = editable
    hou.attribType.Point = MagicMock()

    def node_lookup(path):
        return {"/obj/char": container, "/obj/char/rig": rig}.get(path)

    hou.node.side_effect = node_lookup
    return hou, editable, out_node, new_points


class TestCreateBipedTemplate:
    def _mock_hou(self):
        hou = MagicMock()
        container, created = _mock_container(hou)
        hou.node.side_effect = lambda p: container if p.startswith("/obj") else None
        # get_or_create_rig creates a kinefx::skeleton via container.createNode
        rig_geo = MagicMock()
        rig_geo.createPoints.return_value = [MagicMock() for _ in range(22)]
        rig_geo.addAttrib.return_value = MagicMock()
        hou.Geometry.return_value = rig_geo
        return hou, container, created

    def test_creates_biped_template(self) -> None:
        mod = _load_script("create_biped_template.py")
        hou, container, created = self._mock_hou()
        with patch.dict(sys.modules, {"hou": hou}):
            result = mod.create_biped_template("/obj/char", convention="kinefx", height=1.8)
        assert result["success"] is True, result
        ctx = result["context"]
        assert ctx["joint_count"] == 22
        assert "Hips" in ctx["joint_names"]
        assert ctx["support_joint_names"]

    def test_rejects_unknown_convention_before_hou(self) -> None:
        mod = _load_script("create_biped_template.py")
        result = mod.create_biped_template("/obj/char", convention="nope")
        assert result["success"] is False

    def test_rejects_bad_height(self) -> None:
        mod = _load_script("create_biped_template.py")
        assert mod.create_biped_template("/obj/char", height=0)["success"] is False


class TestImportGeneratedCharacter:
    def test_proxy_mode_when_no_file(self) -> None:
        mod = _load_script("import_generated_character.py")
        hou = MagicMock()
        container, created = _mock_container(hou)
        hou.node.side_effect = lambda p: container if p.startswith("/obj") else None
        with patch.dict(sys.modules, {"hou": hou}):
            result = mod.import_generated_character("/obj/char")
        assert result["success"] is True, result
        assert result["context"]["mode"] == "proxy"
        assert result["context"]["rig_ready"] is True

    def test_rejects_unsupported_extension(self) -> None:
        mod = _load_script("import_generated_character.py")
        result = mod.import_generated_character("/obj/char", mesh_file="/x/hero.txt")
        assert result["success"] is False

    def test_missing_file_without_proxy_errors(self) -> None:
        mod = _load_script("import_generated_character.py")
        result = mod.import_generated_character("/obj/char", mesh_file="/nonexistent/hero.fbx", proxy=False)
        assert result["success"] is False

    def test_descriptor_resolver_shapes(self) -> None:
        mod = _load_script("import_generated_character.py")
        resolve = mod._resolve_descriptor_file
        assert resolve({"local_path": "/out/hero.glb", "format": "glb"}) == "/out/hero.glb"
        assert resolve({"asset": {"path": "/out/hero.fbx"}}) == "/out/hero.fbx"
        # Supported format wins over an earlier unsupported variant.
        assert resolve({"variants": [{"local_path": "/a/hero.txt"}, {"local_path": "/a/hero.obj"}]}) == "/a/hero.obj"
        assert resolve({}) is None
        assert resolve("not a dict") is None

    def test_descriptor_drives_import_and_falls_back_to_proxy(self) -> None:
        mod = _load_script("import_generated_character.py")
        hou = MagicMock()
        container, created = _mock_container(hou)
        hou.node.side_effect = lambda p: container if p.startswith("/obj") else None
        descriptor = {"local_path": "/nonexistent/hero.fbx", "format": "fbx"}
        with patch.dict(sys.modules, {"hou": hou}):
            result = mod.import_generated_character("/obj/char", asset_descriptor=descriptor)
        assert result["success"] is True, result
        assert result["context"]["asset_descriptor_used"] is True
        # Missing file falls back to a proxy so offline workflows stay runnable.
        assert result["context"]["mode"] == "proxy"


class TestConfigureBipedRetarget:
    def _mock_hou(self):
        hou = MagicMock()
        container, created = _mock_container(hou)
        target = _mock_node("/obj/char/biped")
        source = _mock_node("/obj/char/mocap")

        def node_lookup(path):
            return {"/obj/char": container, "/obj/char/biped": target, "/obj/char/mocap": source}.get(path)

        hou.node.side_effect = node_lookup
        return hou, container, created

    def test_explicit_map_builds_chain(self) -> None:
        mod = _load_script("configure_biped_retarget.py")
        hou, container, created = self._mock_hou()
        with patch.dict(sys.modules, {"hou": hou}):
            result = mod.configure_biped_retarget(
                "/obj/char",
                "/obj/char/biped",
                "/obj/char/mocap",
                source_convention="mixamo",
                target_convention="kinefx",
            )
        assert result["success"] is True, result
        assert result["context"]["mapped_joint_count"] == 22
        assert result["context"]["validated"] is True
        types = {n.type_name for n in created.values()}
        assert "kinefx::rigmatchpose" in types
        assert "kinefx::mappoints" in types
        assert "kinefx::fullbodyik" in types

    def test_requires_mapping(self) -> None:
        mod = _load_script("configure_biped_retarget.py")
        result = mod.configure_biped_retarget("/obj/char", "/obj/char/biped", "/obj/char/mocap")
        assert result["success"] is False

    def test_missing_container_is_structured_error(self) -> None:
        """A missing geo container must be a structured error, not a TypeError."""
        mod = _load_script("configure_biped_retarget.py")
        hou, container, created = self._mock_hou()
        hou.node.side_effect = lambda path: None if path == "/obj/char" else container
        with patch.dict(sys.modules, {"hou": hou}):
            result = mod.configure_biped_retarget(
                "/obj/char", "/obj/char/biped", "/obj/char/mocap", joint_map={"src_hip": "Hips"}
            )
        assert result["success"] is False, result
        assert result["message"] == "Geometry container not found"

    def test_joint_map_takes_precedence(self) -> None:
        mod = _load_script("configure_biped_retarget.py")
        hou, container, created = self._mock_hou()
        with patch.dict(sys.modules, {"hou": hou}):
            result = mod.configure_biped_retarget(
                "/obj/char",
                "/obj/char/biped",
                "/obj/char/mocap",
                joint_map={"src_hip": "Hips"},
            )
        assert result["success"] is True
        assert result["context"]["joint_map"] == {"src_hip": "Hips"}

    def test_explicit_map_missing_attribute_not_validated(self) -> None:
        """B1: source skeleton without mapping_attribute must not report success.

        Attribute-mode retargeting (automapinline=0/mapusing=1) is only real
        when the source skeleton carries mapping_attribute point values. A
        missing attribute must be a structured error, never validated=true.
        """
        mod = _load_script("configure_biped_retarget.py")
        hou, container, created = self._mock_hou()
        source = hou.node("/obj/char/mocap")
        source.geometry().findPointAttrib.return_value = None
        with patch.dict(sys.modules, {"hou": hou}):
            result = mod.configure_biped_retarget(
                "/obj/char",
                "/obj/char/biped",
                "/obj/char/mocap",
                joint_map={"src_hip": "Hips"},
            )
        assert result["success"] is False, result
        assert result["error"] == "mapping_attribute_missing"
        assert result["context"].get("validated") is not True
        # No retarget nodes are built when the mapping cannot take effect.
        assert created == {}

    def test_explicit_map_missing_attribute_via_conventions_not_validated(self) -> None:
        """B1: the convention-derived map path is verified the same way."""
        mod = _load_script("configure_biped_retarget.py")
        hou, container, created = self._mock_hou()
        source = hou.node("/obj/char/mocap")
        source.geometry().findPointAttrib.return_value = None
        with patch.dict(sys.modules, {"hou": hou}):
            result = mod.configure_biped_retarget(
                "/obj/char",
                "/obj/char/biped",
                "/obj/char/mocap",
                source_convention="mixamo",
                target_convention="kinefx",
            )
        assert result["success"] is False, result
        assert result["error"] == "mapping_attribute_missing"
        assert result["context"].get("validated") is not True

    def test_explicit_map_with_attribute_is_verified(self) -> None:
        """B1: when the attribute exists, success reports it as verified."""
        mod = _load_script("configure_biped_retarget.py")
        hou, container, created = self._mock_hou()
        source = hou.node("/obj/char/mocap")
        source.geometry().findPointAttrib.return_value = MagicMock()  # present
        with patch.dict(sys.modules, {"hou": hou}):
            result = mod.configure_biped_retarget(
                "/obj/char",
                "/obj/char/biped",
                "/obj/char/mocap",
                joint_map={"src_hip": "Hips"},
            )
        assert result["success"] is True, result
        assert result["context"]["mapping_attribute_verified"] is True
        assert result["context"]["validated"] is True


class TestBuildRagdoll:
    def test_builds_ragdoll_network(self) -> None:
        mod = _load_script("build_ragdoll.py")
        hou = MagicMock()
        container, created = _mock_container(hou)
        skeleton = _mock_node("/obj/char/biped")
        dop_parent = _mock_node("/obj")
        dop_parent.createNode.side_effect = None
        dopnet = _mock_node("/obj/ragdoll_dopnet")
        dopnet.createNode.side_effect = container.createNode.side_effect

        def node_lookup(path):
            return {"/obj/char": container, "/obj/char/biped": skeleton, "/obj": dop_parent}.get(path)

        hou.node.side_effect = node_lookup
        with patch.dict(sys.modules, {"hou": hou}):
            result = mod.build_ragdoll("/obj/char", "/obj/char/biped", dopnet_path="/obj/ragdoll_dopnet")
        assert result["success"] is True, result
        assert result["context"]["constraint_type"] == "conetwist"
        assert result["context"]["validated"] is True
        assert result["context"]["created_sop_nodes"]
        assert result["context"]["created_dop_nodes"]

    def test_rejects_bad_constraint(self) -> None:
        mod = _load_script("build_ragdoll.py")
        assert mod.build_ragdoll("/obj/char", "/obj/char/biped", constraint_type="nope")["success"] is False

    def test_wiring_failure_returns_error(self) -> None:
        """F1: a setInput failure must be surfaced, not swallowed as validated."""
        mod = _load_script("build_ragdoll.py")
        hou = MagicMock()
        container, created = _mock_container(hou)
        skeleton = _mock_node("/obj/char/biped")
        dop_parent = _mock_node("/obj")
        dopnet = _mock_node("/obj/ragdoll_dopnet")

        def create_dop(type_name, node_name=None, **kwargs):
            name = node_name or type_name.split("::")[-1]
            node = _mock_node("/obj/ragdoll_dopnet/{}".format(name))
            node.type_name = type_name
            if name.endswith("_merge"):
                node.setInput.side_effect = RuntimeError("simulated wiring failure")
            created[name] = node
            return node

        dopnet.createNode.side_effect = create_dop

        def node_lookup(path):
            return {
                "/obj/char": container,
                "/obj/char/biped": skeleton,
                "/obj": dop_parent,
                "/obj/ragdoll_dopnet": dopnet,
            }.get(path)

        hou.node.side_effect = node_lookup
        with patch.dict(sys.modules, {"hou": hou}):
            result = mod.build_ragdoll("/obj/char", "/obj/char/biped", dopnet_path="/obj/ragdoll_dopnet")
        assert result["success"] is False, result
        assert result["context"]["wiring_failures"]
        assert all("simulated wiring failure" in f["error"] for f in result["context"]["wiring_failures"])

    def test_wiring_failure_never_validated(self) -> None:
        """F1: validated must be False whenever any wiring connection fails."""
        mod = _load_script("build_ragdoll.py")
        hou = MagicMock()
        container, created = _mock_container(hou)
        skeleton = _mock_node("/obj/char/biped")
        dop_parent = _mock_node("/obj")
        dopnet = _mock_node("/obj/ragdoll_dopnet")

        def create_dop(type_name, node_name=None, **kwargs):
            name = node_name or type_name.split("::")[-1]
            node = _mock_node("/obj/ragdoll_dopnet/{}".format(name))
            node.type_name = type_name
            if name.endswith("_output"):
                node.setInput.side_effect = RuntimeError("output wiring failure")
            created[name] = node
            return node

        dopnet.createNode.side_effect = create_dop

        def node_lookup(path):
            return {
                "/obj/char": container,
                "/obj/char/biped": skeleton,
                "/obj": dop_parent,
                "/obj/ragdoll_dopnet": dopnet,
            }.get(path)

        hou.node.side_effect = node_lookup
        with patch.dict(sys.modules, {"hou": hou}):
            result = mod.build_ragdoll("/obj/char", "/obj/char/biped", dopnet_path="/obj/ragdoll_dopnet")
        assert result["success"] is False
        assert result["context"]["wiring_failures"]
        # No success result may claim validated=True on a wiring failure.
        assert result["context"].get("validated") is not True

    def test_invalid_dopnet_path_is_structured_error(self) -> None:
        """N3: a dopnet_path without '/' must not raise ValueError."""
        mod = _load_script("build_ragdoll.py")
        hou = MagicMock()
        container, created = _mock_container(hou)
        skeleton = _mock_node("/obj/char/biped")

        def node_lookup(path):
            return {"/obj/char": container, "/obj/char/biped": skeleton}.get(path)

        hou.node.side_effect = node_lookup
        with patch.dict(sys.modules, {"hou": hou}):
            result = mod.build_ragdoll("/obj/char", "/obj/char/biped", dopnet_path="ragdoll_dopnet")
        assert result["success"] is False, result
        assert "Invalid DOP network path" in result["message"]
        # Validation precedes any node creation, so no SOP orphans are left.
        container.createNode.assert_not_called()

    def test_missing_dop_parent_creates_no_orphans(self) -> None:
        """N3: a missing DOP parent must error before creating SOP nodes."""
        mod = _load_script("build_ragdoll.py")
        hou = MagicMock()
        container, created = _mock_container(hou)
        skeleton = _mock_node("/obj/char/biped")

        def node_lookup(path):
            return {"/obj/char": container, "/obj/char/biped": skeleton}.get(path)

        hou.node.side_effect = node_lookup  # /obj is absent -> parent is None
        with patch.dict(sys.modules, {"hou": hou}):
            result = mod.build_ragdoll("/obj/char", "/obj/char/biped", dopnet_path="/obj/ragdoll_dopnet")
        assert result["success"] is False, result
        assert "DOP parent not found" in result["message"]
        container.createNode.assert_not_called()


class TestBuildApexFbxBiped:
    def test_packs_and_reports_export(self) -> None:
        mod = _load_script("build_apex_fbx_biped.py")
        hou = MagicMock()
        container, created = _mock_container(hou)
        skeleton = _mock_node("/obj/char/biped")

        def node_lookup(path):
            return {"/obj/char": container, "/obj/char/biped": skeleton}.get(path)

        hou.node.side_effect = node_lookup
        with patch.dict(sys.modules, {"hou": hou}):
            result = mod.build_apex_fbx_biped("/obj/char", "/obj/char/biped", output_fbx="/out/biped.fbx")
        assert result["success"] is True, result
        ctx = result["context"]
        assert ctx["joint_count"] == 22
        assert ctx["export_fbx"]["arguments"]["convert_units"] is True
        assert ctx["export_fbx"]["arguments"]["output_path"] == "/out/biped.fbx"
        assert ctx["validated"] is True

    def test_rejects_unknown_convention(self) -> None:
        mod = _load_script("build_apex_fbx_biped.py")
        assert mod.build_apex_fbx_biped("/obj/char", "/obj/char/biped", convention="nope")["success"] is False

    def test_graphname_uses_rig_path(self) -> None:
        """N2: graphname must follow rig_path, not a hardcoded Base.rig."""
        mod = _load_script("build_apex_fbx_biped.py")
        hou = MagicMock()
        container, created = _mock_container(hou)
        skeleton = _mock_node("/obj/char/biped")

        def node_lookup(path):
            return {"/obj/char": container, "/obj/char/biped": skeleton}.get(path)

        hou.node.side_effect = node_lookup
        with patch.dict(sys.modules, {"hou": hou}):
            mod.build_apex_fbx_biped("/obj/char", "/obj/char/biped", rig_path="Custom.rig", output_fbx="/out/biped.fbx")
        biped_graph = created["dcc_mcp_apex_biped_biped_graph"]
        graphname_calls = [c for c in biped_graph.parm.call_args_list if c[0] == ("graphname",)]
        assert graphname_calls, "graphname parm was never set"
        assert biped_graph.parm("graphname").set.call_args[0][0] == "Custom.rig"

    def test_no_output_fbx_has_no_placeholder_path(self) -> None:
        """N2: output_fbx absent must not emit a bogus '<set output_fbx>' path."""
        mod = _load_script("build_apex_fbx_biped.py")
        hou = MagicMock()
        container, created = _mock_container(hou)
        skeleton = _mock_node("/obj/char/biped")

        def node_lookup(path):
            return {"/obj/char": container, "/obj/char/biped": skeleton}.get(path)

        hou.node.side_effect = node_lookup
        with patch.dict(sys.modules, {"hou": hou}):
            result = mod.build_apex_fbx_biped("/obj/char", "/obj/char/biped")
        assert result["success"] is True, result
        contract = result["context"]["export_fbx"]
        assert "output_path" not in contract["arguments"]
        assert contract["output_fbx_required"] is True
        assert "<set output_fbx>" not in str(contract)


class TestBuildRetargetMotionMixerEnhancement:
    def _mock_hou(self):
        hou = MagicMock()
        container, created = _mock_container(hou)
        target = _mock_node("/obj/char/target")
        sources = [_mock_node("/obj/char/src_a"), _mock_node("/obj/char/src_b")]
        lookup = {
            "/obj/char": container,
            "/obj/char/target": target,
            "/obj/char/src_a": sources[0],
            "/obj/char/src_b": sources[1],
        }
        hou.node.side_effect = lambda p: lookup.get(p)
        return hou, container, created

    def test_default_auto_mapping_preserved(self) -> None:
        mod = _load_script("build_retarget_motion_mixer.py")
        hou, container, created = self._mock_hou()
        with patch.dict(sys.modules, {"hou": hou}):
            result = mod.build_retarget_motion_mixer(
                "/obj/char",
                "/obj/char/target",
                ["/obj/char/src_a", "/obj/char/src_b"],
            )
        assert result["success"] is True, result
        assert result["context"]["mapping_mode"] == "auto_by_name"
        assert result["context"]["mapped_joint_count"] == 0

    def test_explicit_mapping_via_conventions(self) -> None:
        mod = _load_script("build_retarget_motion_mixer.py")
        hou, container, created = self._mock_hou()
        with patch.dict(sys.modules, {"hou": hou}):
            result = mod.build_retarget_motion_mixer(
                "/obj/char",
                "/obj/char/target",
                ["/obj/char/src_a", "/obj/char/src_b"],
                source_convention="mixamo",
                target_convention="kinefx",
            )
        assert result["success"] is True, result
        assert result["context"]["mapping_mode"] == "explicit"
        assert result["context"]["mapped_joint_count"] == 22
        assert result["context"]["mapping_attribute"] == "retarget_joint"
        assert result["context"]["mapping_attribute_verified"] is True

    def test_explicit_mapping_via_joint_map(self) -> None:
        mod = _load_script("build_retarget_motion_mixer.py")
        hou, container, created = self._mock_hou()
        with patch.dict(sys.modules, {"hou": hou}):
            result = mod.build_retarget_motion_mixer(
                "/obj/char",
                "/obj/char/target",
                ["/obj/char/src_a", "/obj/char/src_b"],
                joint_map={"a": "b"},
            )
        assert result["success"] is True
        assert result["context"]["joint_map"] == {"a": "b"}

    def test_explicit_mapping_missing_attribute_errors(self) -> None:
        """F2: explicit mapping must error when sources lack the mapping attribute."""
        mod = _load_script("build_retarget_motion_mixer.py")
        hou, container, created = self._mock_hou()
        for source in (hou.node("/obj/char/src_a"), hou.node("/obj/char/src_b")):
            source.geometry.return_value.findPointAttrib.return_value = None
        with patch.dict(sys.modules, {"hou": hou}):
            result = mod.build_retarget_motion_mixer(
                "/obj/char",
                "/obj/char/target",
                ["/obj/char/src_a", "/obj/char/src_b"],
                source_convention="mixamo",
                target_convention="kinefx",
            )
        assert result["success"] is False, result
        assert result["error"] == "mapping_attribute_missing"
        assert result["context"]["mapping_attribute"] == "retarget_joint"
        assert len(result["context"]["missing_sources"]) == 2

    def test_explicit_mapping_missing_attribute_via_joint_map_errors(self) -> None:
        """F2: same guard applies to an explicit joint_map (not only conventions)."""
        mod = _load_script("build_retarget_motion_mixer.py")
        hou, container, created = self._mock_hou()
        hou.node("/obj/char/src_a").geometry.return_value.findPointAttrib.return_value = None
        with patch.dict(sys.modules, {"hou": hou}):
            result = mod.build_retarget_motion_mixer(
                "/obj/char",
                "/obj/char/target",
                ["/obj/char/src_a", "/obj/char/src_b"],
                joint_map={"a": "b"},
            )
        assert result["success"] is False
        assert result["error"] == "mapping_attribute_missing"

    def test_auto_mapping_does_not_require_attribute(self) -> None:
        """F2: default auto-by-name mapping stays backward compatible."""
        mod = _load_script("build_retarget_motion_mixer.py")
        hou, container, created = self._mock_hou()
        for source in (hou.node("/obj/char/src_a"), hou.node("/obj/char/src_b")):
            source.geometry.return_value.findPointAttrib.return_value = None
        with patch.dict(sys.modules, {"hou": hou}):
            result = mod.build_retarget_motion_mixer(
                "/obj/char",
                "/obj/char/target",
                ["/obj/char/src_a", "/obj/char/src_b"],
            )
        assert result["success"] is True, result
        assert result["context"]["mapping_mode"] == "auto_by_name"
        assert result["context"]["mapping_attribute_verified"] is False

    def test_rejects_bad_convention(self) -> None:
        mod = _load_script("build_retarget_motion_mixer.py")
        result = mod.build_retarget_motion_mixer(
            "/obj/char",
            "/obj/char/target",
            ["/obj/char/src_a", "/obj/char/src_b"],
            source_convention="nope",
            target_convention="kinefx",
        )
        assert result["success"] is False


class TestInvertRigScene:
    def test_scene_writes_localtransform_attribute(self) -> None:
        """F3: parent-relative transforms go to a Float-16 localtransform matrix4.

        Verified on licensed Houdini 22.0.368: localtransform is a Float-16
        matrix4 (not a Float-9 matrix3); P keeps world positions and transform
        stays the world matrix3.
        """
        mod = _load_script("invert_rig.py")
        hou, editable, out_node, new_points = _mock_invert_scene_hou()
        with patch.dict(sys.modules, {"hou": hou}):
            result = mod.invert_rig(rig_node="/obj/char/rig")
        assert result["success"] is True, result
        ctx = result["context"]
        assert ctx["mode"] == "scene"
        assert ctx["local_attribute"] == "localtransform"
        assert ctx["local_attribute_type"] == "matrix4"
        assert ctx["convention"] == "houdini_row_vector"
        assert ctx["writeback"] is True
        assert ctx["validated"] is True
        assert ctx["joint_count"] == 2
        # Fresh geometry (not the unverified copy constructor) is used.
        hou.Geometry.assert_called_once_with()
        editable.createPoints.assert_called_once()
        # P keeps the WORLD positions, not local translations.
        world_positions = editable.createPoints.call_args[0][0]
        assert [tuple(p) for p in world_positions] == [(0.0, 0.0, 0.0), (0.0, 1.0, 0.0)]
        added_names = [call[0][1] for call in editable.addAttrib.call_args_list]
        assert "localtransform" in added_names
        assert "name" in added_names
        assert "transform" in added_names
        # localtransform defaults to a 16-value identity matrix4; transform is matrix3.
        assert len(editable.attr_mocks["localtransform"].default) == 16
        assert len(editable.attr_mocks["transform"].default) == 9
        # Each point received the FULL 16-value local transform in localtransform.
        lt_handle = editable.attr_mocks["localtransform"]
        for pt in new_points:
            lt_values = [c[0][1] for c in pt.setAttribValue.call_args_list if c[0][0] is lt_handle]
            assert len(lt_values) == 1
            assert len(lt_values[0]) == 16
        out_node.parm.assert_called_with("stash")
        assert out_node.parm.return_value.set.called

    def test_scene_missing_stash_is_hard_error(self) -> None:
        """F3: a missing stash parameter must never be a silent success."""
        mod = _load_script("invert_rig.py")
        hou, editable, out_node, new_points = _mock_invert_scene_hou(stash=False)
        with patch.dict(sys.modules, {"hou": hou}):
            result = mod.invert_rig(rig_node="/obj/char/rig")
        assert result["success"] is False, result
        assert result["error"] == "writeback_failed"
        assert "stash" in result["context"]["detail"].lower()
        assert result["context"].get("validated") is not True

    def test_scene_cook_failure_is_hard_error(self) -> None:
        """F3: a cook error on the inverted skeleton must be surfaced."""
        mod = _load_script("invert_rig.py")
        hou, editable, out_node, new_points = _mock_invert_scene_hou(cook_errors=("bad cook",))
        with patch.dict(sys.modules, {"hou": hou}):
            result = mod.invert_rig(rig_node="/obj/char/rig")
        assert result["success"] is False, result
        assert result["error"] == "cook_failed"
        assert result["context"]["errors"] == ["bad cook"]

    def test_scene_local_transforms_use_bottom_row_translation(self) -> None:
        """F3: scene-computed locals carry translation in slots 12/13/14."""
        mod = _load_script("invert_rig.py")
        hou, editable, out_node, new_points = _mock_invert_scene_hou()
        with patch.dict(sys.modules, {"hou": hou}):
            result = mod.invert_rig(rig_node="/obj/char/rig")
        assert result["success"] is True
        locals_out = result["context"]["local_transforms"]
        # Root at origin; child is 1 unit up in Y (bottom-row translation).
        assert locals_out[0][12] == pytest.approx(0.0)
        assert locals_out[1][13] == pytest.approx(1.0)
        assert all(local[3] == pytest.approx(0.0) for local in locals_out)
        # The FULL 16-value matrix4 written to localtransform carries the same
        # bottom-row translation (not a rotation-only matrix3 in last column).
        lt_handle = editable.attr_mocks["localtransform"]
        written = [c[0][1] for c in new_points[1].setAttribValue.call_args_list if c[0][0] is lt_handle][0]
        assert len(written) == 16
        assert written[13] == pytest.approx(1.0)
        assert (written[3], written[7], written[11]) == pytest.approx((0.0, 0.0, 0.0))


# ---------------------------------------------------------------------------
# QA real-machine blocking regressions (head 348317d -> cook guard fixes).
#
# The previous mock-hou tests were "false green": _mock_node.cook() never
# raises, so an unguarded node.cook(force=True) that throws hou.OperationFailed
# on licensed Houdini was invisible. These tests make the mock cook RAISE and
# assert the tools degrade gracefully (validated=False + cook_failures) instead
# of returning success=False / OperationFailed. The non-mock real-host proof is
# .github/scripts/run_houdini_kinefx_cook_acceptance.py (run under hython).
# ---------------------------------------------------------------------------


class _ThrowingCook(Exception):
    """Stand-in for hou.OperationFailed raised by a standalone cook."""


def _mock_raising_node(path):
    node = _mock_node(path)
    node.errors.return_value = ()
    node.warnings.return_value = ()
    node.cook.side_effect = _ThrowingCook("The attempted operation failed. Error while cooking.")
    return node


class TestGuardedCookFailures:
    def test_cook_exception_becomes_failure_not_raise(self) -> None:
        """guarded_cook_failures never raises; it records the cook exception."""
        common = _load_script("_kinefx_common.py")
        nodes = [_mock_raising_node("/obj/a"), _mock_node("/obj/b")]
        failures = common.guarded_cook_failures(nodes)
        assert len(failures) == 1
        assert failures[0]["path"] == "/obj/a"
        assert "Error while cooking" in failures[0]["errors"][0]
        assert failures[0]["warnings"] == []

    def test_clean_cook_yields_no_failures(self) -> None:
        common = _load_script("_kinefx_common.py")
        assert common.guarded_cook_failures([_mock_node("/obj/a")]) == []

    def test_errors_and_warnings_are_recorded(self) -> None:
        common = _load_script("_kinefx_common.py")
        node = _mock_node("/obj/a")
        node.errors.return_value = ("bad",)
        node.warnings.return_value = ("warn",)
        failures = common.guarded_cook_failures([node])
        assert failures[0]["errors"] == ["bad"]
        assert failures[0]["warnings"] == ["warn"]

    def test_errors_probe_exception_is_recorded_not_raised(self) -> None:
        common = _load_script("_kinefx_common.py")
        node = _mock_node("/obj/a")
        node.errors.side_effect = RuntimeError("diagnostic probe failed")
        failures = common.guarded_cook_failures([node])
        assert len(failures) == 1
        assert "diagnostic probe failed" in failures[0]["errors"][0]

    def test_capability_create_node_translates_missing_type(self) -> None:
        common = _load_script("_kinefx_common.py")
        container = MagicMock()
        container.createNode.side_effect = RuntimeError("The attempted operation failed.\nInvalid node type name")
        with pytest.raises(common.RequiresHoudini22) as info:
            common.capability_create_node(container, "kinefx::motionmixer", "mixer")
        assert info.value.node_type == "kinefx::motionmixer"

    def test_capability_create_node_reraises_other_errors(self) -> None:
        common = _load_script("_kinefx_common.py")
        container = MagicMock()
        container.createNode.side_effect = RuntimeError("some unrelated failure")
        with pytest.raises(RuntimeError):
            common.capability_create_node(container, "kinefx::mappoints", "mp")


class TestConfigureBipedRetargetCookGuard:
    def _mock_hou_with_cook_failure(self, fail_name):
        """hou whose created node named *fail_name* raises on cook(force=True)."""
        hou = MagicMock()
        container, created = _mock_container(hou)
        target = _mock_node("/obj/char/biped")
        source = _mock_node("/obj/char/mocap")

        def create_node(type_name, node_name=None, **kwargs):
            name = node_name or type_name.split("::")[-1]
            if name == fail_name:
                node = _mock_raising_node("/obj/char/{}".format(name))
            else:
                node = _mock_node("/obj/char/{}".format(name))
            node.type_name = type_name
            created[name] = node
            return node

        container.createNode.side_effect = create_node

        def node_lookup(path):
            return {"/obj/char": container, "/obj/char/biped": target, "/obj/char/mocap": source}.get(path)

        hou.node.side_effect = node_lookup
        return hou, container, created

    def test_cook_exception_does_not_fail_tool(self) -> None:
        """QA blocking 1: a raised cook must be a cook_failure, not success=False."""
        mod = _load_script("configure_biped_retarget.py")
        hou, container, created = self._mock_hou_with_cook_failure(fail_name="dcc_mcp_biped_retarget_map")
        source = hou.node("/obj/char/mocap")
        source.geometry().findPointAttrib.return_value = MagicMock()
        with patch.dict(sys.modules, {"hou": hou}):
            result = mod.configure_biped_retarget(
                "/obj/char", "/obj/char/biped", "/obj/char/mocap", joint_map={"src_hip": "Hips"}
            )
        assert result["success"] is True, result
        assert result["context"]["validated"] is False
        assert result["context"]["cook_failures"]
        assert "Error while cooking" in result["context"]["cook_failures"][0]["errors"][0]

    def test_target_map_wires_second_input(self) -> None:
        """QA blocking 1: kinefx::mappoints needs 2 inputs; verify input 1 is set."""
        mod = _load_script("configure_biped_retarget.py")
        hou, container, created = self._mock_hou_with_cook_failure(fail_name="__none__")
        source = hou.node("/obj/char/mocap")
        source.geometry().findPointAttrib.return_value = MagicMock()
        with patch.dict(sys.modules, {"hou": hou}):
            result = mod.configure_biped_retarget(
                "/obj/char", "/obj/char/biped", "/obj/char/mocap", joint_map={"src_hip": "Hips"}
            )
        assert result["success"] is True
        target_map = created["dcc_mcp_biped_retarget_target_map"]
        # setInput(1, source) must be called (input 0 alone crashes on real Houdini).
        inputs = [c[0][0] for c in target_map.setInput.call_args_list]
        assert 1 in inputs
        second = [c for c in target_map.setInput.call_args_list if c[0][0] == 1]
        assert second and second[0][0][1] is source


class TestBuildRagdollCookGuard:
    def _mock_hou(self, dopnet_cook_raises=False):
        hou = MagicMock()
        container, created = _mock_container(hou)
        skeleton = _mock_node("/obj/char/biped")
        dop_parent = _mock_node("/obj")
        dop_parent.createNode.side_effect = None
        dopnet = _mock_node("/obj/ragdoll_dopnet")
        if dopnet_cook_raises:
            dopnet.cook.side_effect = _ThrowingCook("The attempted operation failed. Error while cooking.")
        dopnet.createNode.side_effect = container.createNode.side_effect

        def node_lookup(path):
            return {
                "/obj/char": container,
                "/obj/char/biped": skeleton,
                "/obj": dop_parent,
                "/obj/ragdoll_dopnet": dopnet,
            }.get(path)

        hou.node.side_effect = node_lookup
        return hou, container, created, dopnet

    def test_dop_data_nodes_not_standalone_cooked(self) -> None:
        """QA blocking 2: DOP data nodes are not standalone-cookable; cook dopnet."""
        mod = _load_script("build_ragdoll.py")
        hou, container, created, dopnet = self._mock_hou()
        with patch.dict(sys.modules, {"hou": hou}):
            result = mod.build_ragdoll("/obj/char", "/obj/char/biped", dopnet_path="/obj/ragdoll_dopnet")
        assert result["success"] is True, result
        # The dopnet is cooked as a whole (recursively validates the DOP network).
        dopnet.cook.assert_called()
        # constraintnetwork / merge DOP data nodes are NOT force-cooked alone.
        for name in ("dcc_mcp_ragdoll_constraintnetwork", "dcc_mcp_ragdoll_merge"):
            node = created[name]
            assert node.cook.call_count == 0, "{} must not be standalone-cooked".format(name)

    def test_dopnet_cook_exception_does_not_fail_tool(self) -> None:
        """QA blocking 2: a dopnet cook exception is a cook_failure, not success=False."""
        mod = _load_script("build_ragdoll.py")
        hou, container, created, dopnet = self._mock_hou(dopnet_cook_raises=True)
        with patch.dict(sys.modules, {"hou": hou}):
            result = mod.build_ragdoll("/obj/char", "/obj/char/biped", dopnet_path="/obj/ragdoll_dopnet")
        assert result["success"] is True, result
        assert result["context"]["validated"] is False
        assert any("Error while cooking" in f["errors"][0] for f in result["context"]["cook_failures"])


class TestMotionMixerCapabilityDegradation:
    def _mock_hou_missing_type(self, missing_type):
        hou = MagicMock()
        container, created = _mock_container(hou)
        target = _mock_node("/obj/char/biped")
        sources = [_mock_node("/obj/char/s1"), _mock_node("/obj/char/s2")]
        real_create = container.createNode.side_effect

        def create_node(type_name, node_name=None, **kwargs):
            if type_name == missing_type:
                raise RuntimeError("The attempted operation failed.\nInvalid node type name")
            return real_create(type_name, node_name=node_name, **kwargs)

        container.createNode.side_effect = create_node

        def node_lookup(path):
            lookup = {"/obj/char": container, "/obj/char/biped": target}
            for i, s in enumerate(sources, start=1):
                lookup["/obj/char/s{}".format(i)] = s
            return lookup.get(path)

        hou.node.side_effect = node_lookup
        return hou, container

    def test_missing_h22_node_type_is_structured_capability_error(self) -> None:
        """20.5/21: a missing H22 node type must degrade, not raise uncaught."""
        mod = _load_script("build_retarget_motion_mixer.py")
        hou, container = self._mock_hou_missing_type(missing_type="apex::packcharacter")
        with patch.dict(sys.modules, {"hou": hou}):
            result = mod.build_retarget_motion_mixer("/obj/char", "/obj/char/biped", ["/obj/char/s1", "/obj/char/s2"])
        assert result["success"] is False, result
        assert result["error"] == "capability_unavailable"
        assert result["context"]["requires_houdini_22"] is True
        assert result["context"]["missing_node_type"] == "apex::packcharacter"
        assert result["error"] not in ("OperationFailed", "TypeError", "RuntimeError")
