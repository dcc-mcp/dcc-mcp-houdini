"""Mock-hou unit tests for the houdini-hda-automation skill."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

from skill_loader import skill_script_import_context

_SKILLS_ROOT = Path(__file__).parent.parent / "src" / "dcc_mcp_houdini" / "skills"


def _load_script(script_name: str) -> ModuleType:
    path = _SKILLS_ROOT / "houdini-hda-automation" / "scripts" / script_name
    spec = importlib.util.spec_from_file_location(f"hda_auto_{path.stem}", path)
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


class TestHdaQuery:
    def test_scan_hda_libraries(self) -> None:
        mod = _load_script("scan_hda_libraries.py")
        definition = MagicMock()
        definition.nodeTypeName.return_value = "labs::my_asset"
        mock_hou = MagicMock()
        mock_hou.hda.loadedFiles.return_value = ["/libs/my_asset.hda"]
        mock_hou.hda.definitionsInFile.return_value = [definition]
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.scan_hda_libraries()
        assert result["success"] is True
        assert result["context"]["count"] == 1
        lib = result["context"]["libraries"][0]
        assert lib["definition_count"] == 1
        assert lib["node_types"] == ["labs::my_asset"]

    def test_inspect_hda_definition(self) -> None:
        mod = _load_script("inspect_hda_definition.py")
        node_type = MagicMock()
        node_type.name.return_value = "labs::my_asset"
        node_type.category.return_value.name.return_value = "Sop"
        node_type.maxNumInputs.return_value = 2
        node_type.inputLabels.return_value = ["input1", "input2"]
        template = MagicMock()
        template.name.return_value = "scale"
        node_type.parmTemplateGroup.return_value.entries.return_value = [template]

        definition = MagicMock()
        definition.nodeType.return_value = node_type
        definition.nodeTypeName.return_value = "labs::my_asset"
        definition.libraryFilePath.return_value = "/libs/my_asset.hda"
        definition.version.return_value = "1.0"
        definition.sections.return_value = {"Help": object()}

        mock_hou = MagicMock()
        mock_hou.hda.definitionsInFile.return_value = [definition]
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.inspect_hda_definition("labs::my_asset", hda_file="/libs/my_asset.hda")
        assert result["success"] is True
        ctx = result["context"]
        assert ctx["max_inputs"] == 2
        assert ctx["input_labels"] == ["input1", "input2"]
        assert ctx["parm_templates"] == ["scale"]

    def test_inspect_missing_definition_errors(self) -> None:
        mod = _load_script("inspect_hda_definition.py")
        mock_hou = MagicMock()
        mock_hou.hda.definitionsInFile.return_value = []
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.inspect_hda_definition("labs::nope", hda_file="/libs/x.hda")
        assert result["success"] is False

    def test_validate_hda_clean(self) -> None:
        mod = _load_script("validate_hda.py")
        node = _node("/obj/asset1", "asset1", "labs::my_asset")
        node.errors.return_value = []
        node.warnings.return_value = []
        mock_hou = MagicMock()
        mock_hou.node.return_value = node
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.validate_hda("/obj/asset1")
        assert result["success"] is True
        assert result["context"]["valid"] is True
        node.cook.assert_called_once_with(force=True)

    def test_validate_hda_reports_errors(self) -> None:
        mod = _load_script("validate_hda.py")
        node = _node("/obj/asset1", "asset1", "labs::my_asset")
        node.errors.return_value = ["bad cook"]
        node.warnings.return_value = []
        mock_hou = MagicMock()
        mock_hou.node.return_value = node
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.validate_hda("/obj/asset1", cook=False)
        assert result["success"] is True
        assert result["context"]["valid"] is False
        assert result["context"]["errors"] == ["bad cook"]
        node.cook.assert_not_called()


class TestHdaEdit:
    def test_instantiate_hda_wires_and_sets(self) -> None:
        mod = _load_script("instantiate_hda.py")
        new_node = _node("/obj/asset1", "asset1", "labs::my_asset")
        new_node.errors.return_value = []
        new_node.children.return_value = []
        scalar = MagicMock()
        tuple_parm = MagicMock()
        new_node.parm.side_effect = lambda n: scalar if n == "scale" else None
        new_node.parmTuple.side_effect = lambda n: tuple_parm if n == "color" else None
        parent = _node("/obj", "obj", "obj")
        parent.createNode.return_value = new_node
        src = _node("/obj/in1", "in1", "geo")

        mock_hou = MagicMock()
        mock_hou.node.side_effect = lambda p: {"/obj": parent, "/obj/in1": src}.get(p)
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.instantiate_hda(
                "/obj",
                "labs::my_asset",
                parameters={"scale": 2.0, "color": [1, 0, 0]},
                inputs=["/obj/in1"],
            )
        assert result["success"] is True
        parent.createNode.assert_called_once_with("labs::my_asset", node_name=None)
        new_node.setInput.assert_called_once_with(0, src)
        scalar.set.assert_called_once_with(2.0)
        tuple_parm.set.assert_called_once_with((1, 0, 0))
        new_node.cook.assert_called_once_with(force=True)

    def test_instantiate_hda_missing_input_warns(self) -> None:
        mod = _load_script("instantiate_hda.py")
        new_node = _node("/obj/asset1", "asset1", "labs::my_asset")
        new_node.errors.return_value = []
        new_node.children.return_value = []
        parent = _node("/obj", "obj", "obj")
        parent.createNode.return_value = new_node
        mock_hou = MagicMock()
        mock_hou.node.side_effect = lambda p: parent if p == "/obj" else None
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.instantiate_hda("/obj", "labs::my_asset", inputs=["/obj/missing"], cook=False)
        assert result["success"] is True
        assert any("missing" in w for w in result["context"]["warnings"])


class TestPdgRop:
    def test_cook_top_network(self) -> None:
        mod = _load_script("cook_top_network.py")
        node = _node("/obj/topnet1/output", "output", "output")
        node.errors.return_value = []
        graph = MagicMock()
        graph.workItems.return_value = [object(), object()]
        node.getPDGGraphContext.return_value.graph = graph
        mock_hou = MagicMock()
        mock_hou.node.return_value = node
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.cook_top_network("/obj/topnet1/output")
        assert result["success"] is True
        assert result["context"]["work_item_count"] == 2
        node.cookWorkItems.assert_called_once()

    def test_cook_top_network_rejects_non_top(self) -> None:
        mod = _load_script("cook_top_network.py")
        node = _node("/obj/geo1", "geo1", "geo")
        del node.cookWorkItems
        mock_hou = MagicMock()
        mock_hou.node.return_value = node
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.cook_top_network("/obj/geo1")
        assert result["success"] is False

    def test_execute_rop_chain(self) -> None:
        mod = _load_script("execute_rop_chain.py")
        node = _node("/out/mantra1", "mantra1", "ifd")
        node.errors.return_value = []
        mock_hou = MagicMock()
        mock_hou.node.return_value = node
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.execute_rop_chain("/out/mantra1", frame_range=[1, 24], background=False)
        assert result["success"] is True
        node.render.assert_called_once()
        _, kwargs = node.render.call_args
        assert kwargs["frame_range"] == (1.0, 24.0, 1.0)
        assert kwargs["ignore_inputs"] is False

    def test_execute_rop_chain_defaults_to_background_and_preserves_ignore_inputs(self) -> None:
        mod = _load_script("execute_rop_chain.py")
        node = _node("/out/mantra1", "mantra1", "ifd")
        picture = MagicMock()
        picture.unexpandedString.return_value = "/tmp/beauty.$F4.exr"
        node.parm.side_effect = lambda name: picture if name == "picture" else None
        mock_hou = MagicMock()
        mock_hou.node.return_value = node
        mock_hou.isUIAvailable.return_value = True
        job = {"job_id": "b" * 32, "state": "queued", "pid": 9876}

        with patch.dict(sys.modules, {"hou": mock_hou}), patch.object(
            mod, "launch_background_render", return_value=job
        ) as launch:
            result = mod.execute_rop_chain(
                "/out/mantra1",
                frame_range=[1, 24, 2],
                ignore_inputs=True,
            )

        assert result["success"] is True
        assert result["context"]["background"] is True
        launch.assert_called_once_with(
            mock_hou,
            "/out/mantra1",
            [1, 24, 2],
            "/tmp/beauty.$F4.exr",
            ignore_inputs=True,
            job_kind="rop_chain",
        )
        node.render.assert_not_called()

    def test_execute_rop_chain_detects_lopoutput(self) -> None:
        mod = _load_script("execute_rop_chain.py")
        lopoutput = MagicMock()
        lopoutput.unexpandedString.return_value = "/tmp/stage.$F4.usd"
        node = MagicMock()
        node.parm.side_effect = lambda name: lopoutput if name == "lopoutput" else None

        assert mod._output_pattern(node) == "/tmp/stage.$F4.usd"

    def test_execute_rop_chain_defaults_to_foreground_without_ui(self) -> None:
        mod = _load_script("execute_rop_chain.py")
        node = _node("/out/mantra1", "mantra1", "ifd")
        node.errors.return_value = []
        mock_hou = MagicMock()
        mock_hou.node.return_value = node
        mock_hou.isUIAvailable.return_value = False

        with patch.dict(sys.modules, {"hou": mock_hou}), patch.object(mod, "launch_background_render") as launch:
            result = mod.execute_rop_chain("/out/mantra1", frame_range=[1, 24, 2], ignore_inputs=True)

        assert result["success"] is True
        assert result["context"]["background"] is False
        launch.assert_not_called()
        _, kwargs = node.render.call_args
        assert kwargs["frame_range"] == (1.0, 24.0, 2.0)
        assert kwargs["ignore_inputs"] is True

    def test_execute_rop_chain_fallback_never_drops_ignore_inputs(self) -> None:
        mod = _load_script("execute_rop_chain.py")
        node = _node("/out/mantra1", "mantra1", "ifd")
        node.errors.return_value = []
        accepted = []

        def render(**kwargs):
            if "verbose" in kwargs:
                raise TypeError("verbose is unsupported")
            accepted.append(kwargs)

        node.render.side_effect = render
        mock_hou = MagicMock()
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.execute_rop_chain(
                "/out/mantra1",
                frame_range=[1, 24, 2],
                ignore_inputs=True,
                background=False,
            )

        assert result["success"] is True
        assert accepted == [{"ignore_inputs": True, "frame_range": (1.0, 24.0, 2.0)}]

    def test_execute_rop_chain_rejects_non_rop(self) -> None:
        mod = _load_script("execute_rop_chain.py")
        node = _node("/obj/geo1", "geo1", "geo")
        del node.render
        mock_hou = MagicMock()
        mock_hou.node.return_value = node
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.execute_rop_chain("/obj/geo1")
        assert result["success"] is False
