"""Mock-HOM tests for the Houdini groom skill."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch


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
    assert "matching rest/deformed skin topology" in result["error"]
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
