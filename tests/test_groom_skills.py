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
    hair, clump, deform = MagicMock(), MagicMock(), MagicMock()
    hair.path.return_value = "/obj/bee/bee_fur_generate"
    clump.path.return_value = "/obj/bee/bee_fur_clump"
    deform.path.return_value = "/obj/bee/bee_fur_deform"
    geo.createNode.side_effect = [hair, clump, deform]
    for node in (hair, clump, deform):
        node.parm.side_effect = lambda _name: MagicMock()

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
