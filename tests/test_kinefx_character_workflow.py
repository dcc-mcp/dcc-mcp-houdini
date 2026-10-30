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
    return (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)


def _translated(x, y=0.0, z=0.0):
    return (1, 0, 0, x, 0, 1, 0, y, 0, 0, 1, z, 0, 0, 0, 1)


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
        assert local[0][3] == pytest.approx(0.0)  # root at origin
        assert local[1][3] == pytest.approx(5.0)  # child world tx
        assert local[2][3] == pytest.approx(2.0)

    def test_compute_local_transforms_grandchild(self) -> None:
        mod = _load_common()
        # root at 10, child at 12 (local +2), grandchild at 17 (local +5).
        worlds = [_translated(10.0), _translated(12.0), _translated(17.0)]
        parents = [-1, 0, 1]
        local = mod.compute_local_transforms(worlds, parents)
        assert local[1][3] == pytest.approx(2.0)
        assert local[2][3] == pytest.approx(5.0)

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
        assert result["context"]["local_transforms"][1][3] == pytest.approx(3.0)

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
