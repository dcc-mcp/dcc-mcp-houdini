"""Mock-HOM tests for the Houdini groom skill."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from domain_graph_fakes import scene
from skill_error_assertions import skill_error_detail
from skill_loader import skill_script_import_context


def _load_script():
    path = (
        Path(__file__).parents[1]
        / "src"
        / "dcc_mcp_houdini"
        / "skills"
        / "houdini-groom"
        / "scripts"
        / "build_short_fur_groom.py"
    )
    spec = importlib.util.spec_from_file_location("build_short_fur_groom_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_build_short_fur_groom_with_animated_skin() -> None:
    mod = _load_script()
    geo = MagicMock()
    geo.path.return_value = "/obj/bee"
    geo.childTypeCategory.return_value.nodeTypes.return_value = {
        "hairgen::2.0": MagicMock(),
        "hairclump::2.0": MagicMock(),
        "guidedeform::2.0": MagicMock(),
    }
    rest, animated, guides = MagicMock(), MagicMock(), MagicMock()
    rest.path.return_value = "/obj/bee/rest_skin"
    animated.path.return_value = "/obj/bee/animated_skin"
    guides.path.return_value = "/obj/bee/guides"
    for skin in (rest, animated):
        skin.geometry.return_value.intrinsicValue.side_effect = lambda name: {
            "pointcount": 100,
            "primitivecount": 50,
        }[name]
    hair, clump, deform = MagicMock(), MagicMock(), MagicMock()
    hair.path.return_value = "/obj/bee/bee_fur_generate"
    clump.path.return_value = "/obj/bee/bee_fur_clump"
    deform.path.return_value = "/obj/bee/bee_fur_deform"
    geo.createNode.side_effect = [hair, clump, deform]
    for node in (hair, clump, deform):
        node.parm.side_effect = lambda _name: MagicMock()
    deform.errors.return_value = ()
    deform.geometry.return_value.intrinsicValue.side_effect = lambda name: {
        "pointcount": 600,
        "primitivecount": 100,
    }[name]

    mock_hou = MagicMock()
    mock_hou.node.side_effect = {
        "/obj/bee": geo,
        "/obj/bee/rest_skin": rest,
        "/obj/bee/animated_skin": animated,
        "/obj/bee/guides": guides,
    }.get
    with patch.dict(sys.modules, {"hou": mock_hou}):
        result = mod.build_short_fur_groom(
            "/obj/bee", "rest_skin", animated_skin="animated_skin", guides="guides", name_prefix="bee_fur"
        )

    assert result["success"] is True
    hair.setInput.assert_any_call(0, rest, 0)
    hair.setInput.assert_any_call(1, guides, 0)
    clump.setFirstInput.assert_called_once_with(hair)
    clump.setInput.assert_called_once_with(1, rest, 0)
    deform.setInput.assert_any_call(0, clump, 0)
    deform.setInput.assert_any_call(1, rest, 0)
    deform.setInput.assert_any_call(2, animated, 0)
    deform.setDisplayFlag.assert_called_once_with(True)
    deform.setRenderFlag.assert_called_once_with(True)
    deform.cook.assert_called_once_with(force=True)
    assert result["context"]["output_primitive_count"] == 100


def test_build_short_fur_groom_builds_anatomy_regions() -> None:
    mod = _load_script()
    geo = MagicMock()
    geo.path.return_value = "/obj/bee"
    geo.childTypeCategory.return_value.nodeTypes.return_value = {
        "hairgen::2.0": MagicMock(),
        "hairclump::2.0": MagicMock(),
        "guidedeform::2.0": MagicMock(),
    }
    rest, animated, body_guides, abdomen_guides = (MagicMock() for _ in range(4))
    rest.path.return_value = "/obj/bee/rest_skin"
    animated.path.return_value = "/obj/bee/animated_skin"
    body_guides.path.return_value = "/obj/bee/body_guides"
    abdomen_guides.path.return_value = "/obj/bee/abdomen_guides"
    for skin in (rest, animated):
        skin.geometry.return_value.intrinsicValue.side_effect = lambda name: {
            "pointcount": 100,
            "primitivecount": 50,
        }[name]

    head_hair, abdomen_hair, abdomen_clump, merge, deform = (MagicMock() for _ in range(5))
    head_hair.path.return_value = "/obj/bee/bee_fur_head_generate"
    abdomen_hair.path.return_value = "/obj/bee/bee_fur_abdomen_generate"
    abdomen_clump.path.return_value = "/obj/bee/bee_fur_abdomen_clump"
    merge.path.return_value = "/obj/bee/bee_fur_merge"
    deform.path.return_value = "/obj/bee/bee_fur_deform"
    geo.createNode.side_effect = [head_hair, abdomen_hair, abdomen_clump, merge, deform]
    for node in (head_hair, abdomen_hair, abdomen_clump, merge, deform):
        node.parm.side_effect = lambda _name: MagicMock()
    deform.errors.return_value = ()
    deform.geometry.return_value.intrinsicValue.side_effect = lambda name: {
        "pointcount": 900,
        "primitivecount": 150,
    }[name]

    mock_hou = MagicMock()
    mock_hou.node.side_effect = {
        "/obj/bee": geo,
        "/obj/bee/rest_skin": rest,
        "/obj/bee/animated_skin": animated,
        "/obj/bee/body_guides": body_guides,
        "/obj/bee/abdomen_guides": abdomen_guides,
    }.get
    with patch.dict(sys.modules, {"hou": mock_hou}):
        result = mod.build_short_fur_groom(
            "/obj/bee",
            "rest_skin",
            animated_skin="animated_skin",
            guides="body_guides",
            name_prefix="bee_fur",
            region_profiles=[
                {
                    "name": "head",
                    "skin_group": "head_fur",
                    "density": 80000,
                    "length": 0.018,
                    "segments": 4,
                    "clump_strength": 0.0,
                },
                {
                    "name": "abdomen",
                    "skin_group": "abdomen_fur",
                    "guides": "abdomen_guides",
                    "density": 150000,
                    "length": 0.035,
                    "segments": 6,
                    "clump_strength": 0.25,
                },
            ],
        )

    assert result["success"] is True
    head_hair.setInput.assert_any_call(0, rest, 0)
    head_hair.setInput.assert_any_call(1, body_guides, 0)
    abdomen_hair.setInput.assert_any_call(1, abdomen_guides, 0)
    abdomen_clump.setFirstInput.assert_called_once_with(abdomen_hair)
    merge.setInput.assert_any_call(0, head_hair, 0)
    merge.setInput.assert_any_call(1, abdomen_clump, 0)
    deform.setInput.assert_any_call(0, merge, 0)
    assert result["context"]["region_count"] == 2
    assert result["context"]["merge_path"] == "/obj/bee/bee_fur_merge"
    assert [region["name"] for region in result["context"]["regions"]] == ["head", "abdomen"]


def test_build_short_fur_groom_rejects_invalid_region_before_mutation() -> None:
    mod = _load_script()
    geo = MagicMock()
    geo.path.return_value = "/obj/bee"
    mock_hou = MagicMock()
    mock_hou.node.side_effect = {"/obj/bee": geo, "/obj/bee/rest_skin": MagicMock()}.get
    with patch.dict(sys.modules, {"hou": mock_hou}):
        result = mod.build_short_fur_groom(
            "/obj/bee",
            "rest_skin",
            region_profiles=[{"name": "../bad", "skin_group": "head_fur"}],
        )

    assert result["success"] is False
    geo.createNode.assert_not_called()


def test_build_short_fur_groom_rejects_surface_topology_mismatch() -> None:
    mod = _load_script()
    geo, rest, animated = MagicMock(), MagicMock(), MagicMock()
    geo.path.return_value = "/obj/bee"
    rest.geometry.return_value.intrinsicValue.side_effect = lambda name: {
        "pointcount": 100,
        "primitivecount": 50,
    }[name]
    animated.geometry.return_value.intrinsicValue.side_effect = lambda name: {
        "pointcount": 101,
        "primitivecount": 50,
    }[name]
    mock_hou = MagicMock()
    mock_hou.node.side_effect = {
        "/obj/bee": geo,
        "/obj/bee/rest_skin": rest,
        "/obj/bee/animated_skin": animated,
    }.get
    with patch.dict(sys.modules, {"hou": mock_hou}):
        result = mod.build_short_fur_groom(
            "/obj/bee", "rest_skin", animated_skin="animated_skin", deform_method="surface"
        )

    assert result["success"] is False
    assert "matching rest/deformed skin topology" in skill_error_detail(result)
    geo.createNode.assert_not_called()


def test_build_short_fur_groom_rolls_back_on_missing_node_type() -> None:
    mod = _load_script()
    geo = MagicMock()
    geo.path.return_value = "/obj/bee"
    geo.childTypeCategory.return_value.nodeTypes.return_value = {}
    mock_hou = MagicMock()
    mock_hou.node.side_effect = {"/obj/bee": geo, "/obj/bee/rest_skin": MagicMock()}.get
    with patch.dict(sys.modules, {"hou": mock_hou}):
        result = mod.build_short_fur_groom("/obj/bee", "rest_skin")

    assert result["success"] is False
    geo.createNode.assert_not_called()


# ---------------------------------------------------------------------------
# add_groom_step
# ---------------------------------------------------------------------------


def _load_step():
    path = (
        Path(__file__).parents[1]
        / "src"
        / "dcc_mcp_houdini"
        / "skills"
        / "houdini-groom"
        / "scripts"
        / "add_groom_step.py"
    )
    spec = importlib.util.spec_from_file_location("add_groom_step_test", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    with skill_script_import_context(spec):
        spec.loader.exec_module(module)
    return module


def test_add_groom_step_wires_into_the_chain():
    root, geo, hou = scene()
    upstream = geo.createNode("hairgen")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load_step().add_groom_step(geo.path(), "clump", source_path=upstream.path())
    assert result["success"]
    context = result["context"]
    assert context["node_type"] == "hairclump"
    assert context["step_type"] == "clump"
    assert context["wired"] is True
    assert context["required_setup"] == []
    assert hou.node(context["node_path"]).inputs() == (upstream,)


def test_add_groom_step_defaults_node_name_from_type():
    root, geo, hou = scene()
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load_step().add_groom_step(geo.path(), "frizz")
    assert result["success"]
    assert result["context"]["node_path"].endswith("/frizz1")
    assert result["context"]["setup_state"] == "unwired"
    assert result["context"]["required_setup"] == ["wire the step into the groom chain"]


def test_add_groom_step_applies_parameters():
    root, geo, hou = scene()
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load_step().add_groom_step(geo.path(), "generate", parameters={"size": 2})
    assert result["success"]
    assert result["context"]["applied_parameters"] == {"size": 2}


def test_add_groom_step_fails_and_cleans_up_on_unknown_parameter():
    root, geo, hou = scene()
    preserved = geo.createNode("hairgen")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load_step().add_groom_step(geo.path(), "clump", parameters={"nope": 1})
    assert not result["success"]
    assert geo.children() == (preserved,)


def test_add_groom_step_rejects_unknown_type():
    root, geo, hou = scene()
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load_step().add_groom_step(geo.path(), "comb")
    assert not result["success"]
    assert "Unsupported step_type" in str(result.get("error", "")) + str(result.get("_meta", ""))
    assert geo.children() == ()


def test_add_groom_step_requires_sop_parent():
    root, geo, hou = scene()
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load_step().add_groom_step(root.path(), "clump")
    assert not result["success"]


def test_add_groom_step_hou_missing():
    root, geo, _hou = scene()
    assert "hou" not in sys.modules
    result = _load_step().add_groom_step(geo.path(), "clump")
    assert not result["success"]
    assert result["message"] == "Houdini not available"


def test_groom_step_types_are_stable() -> None:
    module = _load_step()
    assert module.GROOM_STEP_TYPES["generate"] == "hairgen"
    assert module.GROOM_STEP_TYPES["guide_deform"] == "guidedeform"
    assert set(module.GROOM_STEP_TYPES) == {
        "generate",
        "clump",
        "guide_deform",
        "frizz",
        "brush",
        "guide_groom",
        "hair_card",
        "copy",
    }
