"""Unit tests for houdini-parameters and houdini-node-graph skills (issue #12).

No live Houdini is required; the HOM ``hou`` module is mocked per test.
"""

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


def _node(path: str = "/obj/geo1") -> MagicMock:
    node = MagicMock()
    node.path.return_value = path
    return node


class TestParameterQuery:
    def test_list_parms_with_filter(self) -> None:
        mod = _load_script("houdini-parameters", "list_parms.py")
        p1 = MagicMock()
        p1.name.return_value = "scale"
        p1.eval.return_value = 2.0
        p1.label.return_value = "Scale"
        p2 = MagicMock()
        p2.name.return_value = "tx"
        p2.eval.return_value = 0.0
        node = _node()
        node.parms.return_value = [p1, p2]
        mock_hou = MagicMock()
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.list_parms("/obj/geo1", name_filter="scale")

        assert result["success"] is True
        assert result["context"]["count"] == 1
        assert result["context"]["parms"][0]["name"] == "scale"

    def test_get_parms_specific_and_missing(self) -> None:
        mod = _load_script("houdini-parameters", "get_parms.py")
        scale = MagicMock()
        scale.eval.return_value = 2.0
        node = _node()
        node.parm.side_effect = lambda n: scale if n == "scale" else None
        node.parmTuple.side_effect = lambda n: None
        mock_hou = MagicMock()
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.get_parms("/obj/geo1", names=["scale", "nope"])

        assert result["success"] is True
        assert result["context"]["values"] == {"scale": 2.0}
        assert result["context"]["missing"] == ["nope"]


class TestParameterEdit:
    def test_set_parms_coerces_and_reports_errors(self) -> None:
        mod = _load_script("houdini-parameters", "set_parms.py")
        count_parm = MagicMock()
        count_parm.eval.return_value = 3  # int -> coerce "5" to 5
        count_parm.keyframes.return_value = []
        count_parm.isTimeDependent.return_value = False
        node = _node()
        node.parmTuple.side_effect = lambda n: None
        node.parm.side_effect = lambda n: count_parm if n == "count" else None
        mock_hou = MagicMock()
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.set_parms("/obj/geo1", {"count": "5", "ghost": 1})

        assert result["success"] is True
        count_parm.set.assert_called_once_with(5)
        assert result["context"]["applied"]["count"] == 5
        assert "ghost" in result["context"]["errors"]

    def test_set_parms_rejects_animated_parm_without_adding_ghost_keyframe(self) -> None:
        mod = _load_script("houdini-parameters", "set_parms.py")
        keyframes = [MagicMock()]
        animated_parm = MagicMock()
        animated_parm.name.return_value = "tx"
        animated_parm.eval.return_value = 1.25
        animated_parm.keyframes.side_effect = lambda: list(keyframes)
        animated_parm.isTimeDependent.return_value = True
        animated_parm.set.side_effect = lambda _value: keyframes.append(MagicMock())
        node = _node()
        node.parm.side_effect = lambda name: animated_parm if name == "tx" else None
        mock_hou = MagicMock()
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.set_parms(node.path(), {"tx": 2.5})

        assert result["success"] is False
        assert "tx" not in result["context"].get("applied", {})
        assert "tx" in result["context"]["errors"]
        assert "keyframe" in result["context"]["errors"]["tx"].lower()
        animated_parm.set.assert_not_called()
        assert len(keyframes) == 1

    def test_set_parms_rejects_time_dependent_parm_without_keyframes(self) -> None:
        mod = _load_script("houdini-parameters", "set_parms.py")
        animated_parm = MagicMock()
        animated_parm.name.return_value = "tx"
        animated_parm.keyframes.return_value = []
        animated_parm.isTimeDependent.return_value = True
        node = _node()
        node.parm.side_effect = lambda name: animated_parm if name == "tx" else None
        mock_hou = MagicMock()
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.set_parms("/obj/geo1", {"tx": 2.5})

        assert result["success"] is False
        assert "time-dependent" in result["context"]["errors"]["tx"]
        animated_parm.set.assert_not_called()

    def test_set_parms_applies_static_values_but_reports_animated_conflicts(self) -> None:
        mod = _load_script("houdini-parameters", "set_parms.py")
        static_parm = MagicMock()
        static_parm.eval.return_value = 1.0
        static_parm.keyframes.return_value = []
        static_parm.isTimeDependent.return_value = False
        animated_parm = MagicMock()
        animated_parm.name.return_value = "tx"
        animated_parm.eval.return_value = 1.25
        animated_parm.keyframes.return_value = [MagicMock()]
        animated_parm.isTimeDependent.return_value = True
        node = _node()
        node.parm.side_effect = lambda name: {
            "ty": static_parm,
            "tx": animated_parm,
        }.get(name)
        mock_hou = MagicMock()
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.set_parms("/obj/geo1", {"ty": 2.5, "tx": 3.5})

        assert result["success"] is True
        assert result["context"]["applied"] == {"ty": 2.5}
        assert "tx" in result["context"]["errors"]
        static_parm.set.assert_called_once_with(2.5)
        animated_parm.set.assert_not_called()

    def test_set_parms_tuple(self) -> None:
        mod = _load_script("houdini-parameters", "set_parms.py")
        t_tuple = MagicMock()
        tuple_parms = [MagicMock(), MagicMock(), MagicMock()]
        for parm in tuple_parms:
            parm.keyframes.return_value = []
            parm.isTimeDependent.return_value = False
        t_tuple.__iter__.return_value = iter(tuple_parms)
        node = _node()
        node.parmTuple.side_effect = lambda n: t_tuple if n == "t" else None
        node.parm.side_effect = lambda n: None
        mock_hou = MagicMock()
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.set_parms("/obj/geo1", {"t": [1, 2, 3]})

        assert result["success"] is True
        t_tuple.set.assert_called_once_with((1, 2, 3))

    def test_set_parms_rejects_tuple_when_a_component_is_animated(self) -> None:
        mod = _load_script("houdini-parameters", "set_parms.py")
        static_component = MagicMock()
        static_component.name.return_value = "ty"
        static_component.keyframes.return_value = []
        static_component.isTimeDependent.return_value = False
        animated_component = MagicMock()
        animated_component.name.return_value = "tx"
        animated_component.keyframes.return_value = [MagicMock()]
        animated_component.isTimeDependent.return_value = True
        t_tuple = MagicMock()
        t_tuple.__iter__.return_value = iter([animated_component, static_component])
        node = _node()
        node.parmTuple.side_effect = lambda name: t_tuple if name == "t" else None
        mock_hou = MagicMock()
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.set_parms("/obj/geo1", {"t": [1.5, 2.5]})

        assert result["success"] is False
        assert "t" in result["context"]["errors"]
        assert "tx" in result["context"]["errors"]["t"]
        t_tuple.set.assert_not_called()

    def test_add_spare_parm_unsupported(self) -> None:
        mod = _load_script("houdini-parameters", "add_spare_parm.py")
        node = _node()
        mock_hou = MagicMock()
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.add_spare_parm("/obj/geo1", "foo", parm_type="ramp")

        assert result["success"] is False
        node.addSpareParmTuple.assert_not_called()

    def test_add_spare_parm_float(self) -> None:
        mod = _load_script("houdini-parameters", "add_spare_parm.py")
        node = _node()
        mock_hou = MagicMock()
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.add_spare_parm("/obj/geo1", "foo", parm_type="float", num_components=2)

        assert result["success"] is True
        mock_hou.FloatParmTemplate.assert_called_once_with("foo", "foo", 2)
        node.addSpareParmTuple.assert_called_once()

    def test_remove_spare_parm(self) -> None:
        mod = _load_script("houdini-parameters", "remove_spare_parm.py")
        pt = MagicMock()
        node = _node()
        node.parmTuple.return_value = pt
        mock_hou = MagicMock()
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.remove_spare_parm("/obj/geo1", "foo")

        assert result["success"] is True
        node.removeSpareParmTuple.assert_called_once_with(pt)


class TestExpressions:
    def test_set_expression(self) -> None:
        mod = _load_script("houdini-parameters", "set_expression.py")
        parm = MagicMock()
        node = _node()
        node.parm.return_value = parm
        mock_hou = MagicMock()
        mock_hou.node.return_value = node
        mock_hou.exprLanguage.Hscript = "HSCRIPT"
        mock_hou.exprLanguage.Python = "PY"

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.set_expression("/obj/geo1", "tx", "$F", language="hscript")

        assert result["success"] is True
        parm.setExpression.assert_called_once_with("$F", language="HSCRIPT")

    def test_get_expression_none(self) -> None:
        mod = _load_script("houdini-parameters", "get_expression.py")
        parm = MagicMock()
        parm.expression.side_effect = Exception("no expression")
        parm.eval.return_value = 1.0
        node = _node()
        node.parm.return_value = parm
        mock_hou = MagicMock()
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.get_expression("/obj/geo1", "tx")

        assert result["success"] is True
        assert result["context"]["has_expression"] is False
        assert result["context"]["value"] == 1.0

    def test_clear_expression_freezes_value(self) -> None:
        mod = _load_script("houdini-parameters", "clear_expression.py")
        parm = MagicMock()
        parm.eval.return_value = 7.5
        node = _node()
        node.parm.return_value = parm
        mock_hou = MagicMock()
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.clear_expression("/obj/geo1", "tx")

        assert result["success"] is True
        parm.deleteAllKeyframes.assert_called_once()
        parm.set.assert_called_once_with(7.5)


class TestNodeGraph:
    def test_get_connections(self) -> None:
        mod = _load_script("houdini-node-graph", "get_connections.py")
        src = _node("/obj/geo1/box1")
        out = _node("/obj/geo1/out1")
        node = _node("/obj/geo1/xform1")
        node.inputs.return_value = [src, None]
        node.outputs.return_value = [out]
        node.dependents.return_value = []
        mock_hou = MagicMock()
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.get_connections("/obj/geo1/xform1")

        assert result["success"] is True
        assert result["context"]["inputs"] == ["/obj/geo1/box1", None]
        assert result["context"]["outputs"] == ["/obj/geo1/out1"]

    def test_connect_input(self) -> None:
        mod = _load_script("houdini-node-graph", "connect_input.py")
        target = _node("/obj/geo1/xform1")
        source = _node("/obj/geo1/box1")
        mock_hou = MagicMock()
        mock_hou.node.side_effect = lambda p: {
            "/obj/geo1/xform1": target,
            "/obj/geo1/box1": source,
        }.get(p)

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.connect_input("/obj/geo1/xform1", 0, "/obj/geo1/box1", source_output=0)

        assert result["success"] is True
        target.setInput.assert_called_once_with(0, source, 0)

    def test_disconnect_input(self) -> None:
        mod = _load_script("houdini-node-graph", "disconnect_input.py")
        node = _node("/obj/geo1/xform1")
        mock_hou = MagicMock()
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.disconnect_input("/obj/geo1/xform1", 1)

        assert result["success"] is True
        node.setInput.assert_called_once_with(1, None)
