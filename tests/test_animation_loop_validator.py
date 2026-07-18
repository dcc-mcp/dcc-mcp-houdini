"""Loop-contract tests for the bounded, read-only Houdini animation validator."""

from __future__ import annotations

import importlib.util
import json
import math
import sys
import urllib.request
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from unittest.mock import patch

import pytest
import yaml
from dcc_mcp_core import McpHttpConfig, create_skill_server
from dcc_mcp_core.host import QueueDispatcher, StandaloneHost
from skill_loader import skill_script_import_context

_SKILLS_ROOT = Path(__file__).parent.parent / "src" / "dcc_mcp_houdini" / "skills"
_SKILL_ROOT = _SKILLS_ROOT / "houdini-animation"


def _load_validator() -> ModuleType:
    path = _SKILL_ROOT / "scripts" / "validate_loop_contract.py"
    spec = importlib.util.spec_from_file_location("anim_validate_loop_contract", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    with skill_script_import_context(spec):
        spec.loader.exec_module(module)
    return module


class _Matrix3:
    def __init__(self, values: Sequence[float]) -> None:
        self._values = tuple(values)

    def asTuple(self) -> Tuple[float, ...]:
        return self._values


class _Matrix4:
    def __init__(
        self,
        translate: Sequence[float] = (0.0, 0.0, 0.0),
        rotate_z: float = 0.0,
        scale: Sequence[float] = (1.0, 1.0, 1.0),
        matrix_override: Optional[Sequence[float]] = None,
    ) -> None:
        self._translate = tuple(float(value) for value in translate)
        self._rotate = (0.0, 0.0, float(rotate_z))
        self._scale = tuple(float(value) for value in scale)
        angle = math.radians(float(rotate_z))
        cosine = math.cos(angle)
        sine = math.sin(angle)
        self._rotation = (cosine, sine, 0.0, -sine, cosine, 0.0, 0.0, 0.0, 1.0)
        self._matrix = (
            tuple(matrix_override)
            if matrix_override is not None
            else (
                cosine * self._scale[0],
                sine * self._scale[0],
                0.0,
                0.0,
                -sine * self._scale[1],
                cosine * self._scale[1],
                0.0,
                0.0,
                0.0,
                0.0,
                self._scale[2],
                0.0,
                self._translate[0],
                self._translate[1],
                self._translate[2],
                1.0,
            )
        )

    def asTuple(self) -> Tuple[float, ...]:
        return self._matrix

    def extractTranslates(self) -> Tuple[float, float, float]:
        return self._translate

    def extractRotates(self) -> Tuple[float, float, float]:
        return self._rotate

    def extractScales(self) -> Tuple[float, float, float]:
        return self._scale

    def extractRotationMatrix3(self) -> _Matrix3:
        return _Matrix3(self._rotation)


class _Keyframe:
    def __init__(self, frame: float) -> None:
        self._frame = frame

    def frame(self) -> float:
        return self._frame


class _Language:
    def name(self) -> str:
        return "Hscript"


class _Parm:
    def __init__(
        self,
        name: str,
        expression: Optional[str] = None,
        keyframes: Iterable[float] = (),
        time_dependent: bool = False,
    ) -> None:
        self._name = name
        self._expression = expression
        self._keyframes = [_Keyframe(frame) for frame in keyframes]
        self._time_dependent = time_dependent

    def name(self) -> str:
        return self._name

    def expression(self) -> str:
        if self._expression is None:
            raise RuntimeError("no expression")
        return self._expression

    def expressionLanguage(self) -> _Language:
        return _Language()

    def keyframes(self) -> List[_Keyframe]:
        return list(self._keyframes)

    def isTimeDependent(self) -> bool:
        return self._time_dependent


class _NodeType:
    def category(self) -> str:
        return "obj"


class _ObjNode:
    def __init__(self, path: str, hou: "_Hou", transforms: Dict[float, _Matrix4], parms: Iterable[_Parm] = ()):
        self._path = path
        self._hou = hou
        self._transforms = transforms
        self._parms = {parm.name(): parm for parm in parms}

    def path(self) -> str:
        return self._path

    def type(self) -> _NodeType:
        return _NodeType()

    def worldTransform(self) -> _Matrix4:
        return self._transforms[self._hou.current_frame]

    def parm(self, name: str) -> Optional[_Parm]:
        return self._parms.get(name)

    def geometry(self) -> None:
        raise AssertionError("loop validation must not inspect or cook geometry")

    def cook(self, *args: Any, **kwargs: Any) -> None:
        raise AssertionError("loop validation must not cook nodes")


class _Hou:
    def __init__(self, original_frame: float = 42.0, fps: float = 24.0) -> None:
        self.current_frame = original_frame
        self._fps = fps
        self.nodes: Dict[str, _ObjNode] = {}
        self.set_frame_calls: List[float] = []

    def frame(self) -> float:
        return self.current_frame

    def setFrame(self, frame: float) -> None:
        self.current_frame = float(frame)
        self.set_frame_calls.append(float(frame))

    def fps(self) -> float:
        return self._fps

    def node(self, path: str) -> Optional[_ObjNode]:
        return self.nodes.get(path)

    def objNodeTypeCategory(self) -> str:
        return "obj"


def _constant_transforms(frames: Iterable[float], matrix: Optional[_Matrix4] = None) -> Dict[float, _Matrix4]:
    value = matrix or _Matrix4()
    return {float(frame): value for frame in frames}


def test_validate_loop_contract_passes_closed_transform_and_restores_frame() -> None:
    module = _load_validator()
    hou = _Hou(original_frame=42.0)
    frames = (1.0, 2.0, 3.0, 4.0, 5.0, 6.0)
    parms = [
        _Parm("tx", expression="$F % 4", time_dependent=True),
        _Parm("ry", keyframes=(1.0, 5.0), time_dependent=True),
        _Parm("sx"),
    ]
    hou.nodes["/obj/planet"] = _ObjNode("/obj/planet", hou, _constant_transforms(frames), parms)

    with patch.dict(sys.modules, {"hou": hou}):
        result = module.validate_loop_contract(["/obj/planet"], 1, 5)

    assert result["success"] is True
    context = result["context"]
    assert context["passed"] is True
    assert context["sample_frames"] == [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    assert context["virtual_periodic_frame"] == 6.0
    assert context["original_frame"] == 42.0
    assert context["restored_frame"] is True
    assert hou.current_frame == 42.0
    assert hou.set_frame_calls[-1] == 42.0
    diagnostic = context["nodes"][0]
    assert diagnostic["passed"] is True
    assert diagnostic["duplicate_endpoint_hold_risk"] is False
    assert diagnostic["endpoint_duplicate_delta"]["translation_distance"] == 0.0
    assert diagnostic["periodic_delta"]["translation_distance"] == 0.0
    assert diagnostic["velocity_residuals"]["linear_magnitude_per_second"] == 0.0
    assert diagnostic["acceleration_residuals"]["angular_magnitude_degrees_per_second2"] == 0.0
    assert diagnostic["drivers"]["counts"] == {
        "expression": 1,
        "keyframes": 1,
        "static": 1,
        "time_dependent": 0,
    }


def test_validate_loop_contract_reports_seam_and_derivative_failures() -> None:
    module = _load_validator()
    hou = _Hou()
    transforms = {
        1.0: _Matrix4((0, 0, 0), rotate_z=0, scale=(1, 1, 1)),
        2.0: _Matrix4((1, 0, 0), rotate_z=10, scale=(1, 1, 1)),
        3.0: _Matrix4((4, 0, 0), rotate_z=30, scale=(1, 1, 1)),
        9.0: _Matrix4((8, 0, 0), rotate_z=80, scale=(2, 1, 1)),
        10.0: _Matrix4((10, 0, 0), rotate_z=90, scale=(2, 1, 1)),
        11.0: _Matrix4((15, 0, 0), rotate_z=120, scale=(2, 1, 1)),
    }
    hou.nodes["/obj/bad_loop"] = _ObjNode("/obj/bad_loop", hou, transforms)

    with patch.dict(sys.modules, {"hou": hou}):
        result = module.validate_loop_contract(["/obj/bad_loop"], 1, 10)

    assert result["success"] is True
    diagnostic = result["context"]["nodes"][0]
    assert result["context"]["passed"] is False
    assert diagnostic["passed"] is False
    assert diagnostic["endpoint_duplicate_delta"]["translation_distance"] == pytest.approx(10.0)
    assert diagnostic["periodic_delta"]["translation_distance"] == pytest.approx(15.0)
    assert diagnostic["periodic_delta"]["angular_degrees"] == pytest.approx(120.0)
    assert diagnostic["periodic_delta"]["scale_max_abs"] == pytest.approx(1.0)
    assert diagnostic["velocity_residuals"]["linear_magnitude_per_second"] > 0
    assert diagnostic["acceleration_residuals"]["linear_magnitude_per_second2"] > 0
    assert hou.current_frame == 42.0


def test_validate_loop_contract_uses_shortest_angular_arc() -> None:
    module = _load_validator()
    hou = _Hou()
    transforms = {}
    for frame in (1.0, 2.0, 3.0):
        transforms[frame] = _Matrix4(rotate_z=179.0)
    for frame in (9.0, 10.0, 11.0):
        transforms[frame] = _Matrix4(rotate_z=-179.0)
    hou.nodes["/obj/wrapped"] = _ObjNode("/obj/wrapped", hou, transforms)
    relaxed = {
        "matrix_max_abs": 10.0,
        "translation": 1.0,
        "angular_degrees": 3.0,
        "scale": 1.0,
        "linear_velocity": 1.0,
        "angular_velocity_degrees": 1.0,
        "linear_acceleration": 1.0,
        "angular_acceleration_degrees": 1.0,
    }

    with patch.dict(sys.modules, {"hou": hou}):
        result = module.validate_loop_contract(["/obj/wrapped"], 1, 10, tolerances=relaxed)

    diagnostic = result["context"]["nodes"][0]
    assert diagnostic["periodic_delta"]["angular_degrees"] == pytest.approx(2.0)
    assert diagnostic["checks"]["periodic_angular"] is True


def test_validate_loop_contract_treats_range_as_unique_periodic_samples() -> None:
    module = _load_validator()
    hou = _Hou()
    transforms = {float(frame): _Matrix4(rotate_z=(frame - 1) * 72.0) for frame in (1, 2, 3, 4, 5, 6)}
    hou.nodes["/obj/unique_samples"] = _ObjNode("/obj/unique_samples", hou, transforms)

    with patch.dict(sys.modules, {"hou": hou}):
        result = module.validate_loop_contract(["/obj/unique_samples"], 1, 5)

    diagnostic = result["context"]["nodes"][0]
    assert result["context"]["passed"] is True
    assert diagnostic["endpoint_duplicate_delta"]["angular_degrees"] == pytest.approx(72.0)
    assert diagnostic["periodic_delta"]["angular_degrees"] == pytest.approx(0.0)
    assert diagnostic["velocity_residuals"]["angular_magnitude_degrees_per_second"] == pytest.approx(0.0)
    assert diagnostic["acceleration_residuals"]["angular_magnitude_degrees_per_second2"] == pytest.approx(
        0.0, abs=1.0e-9
    )


def test_validate_loop_contract_flags_duplicate_endpoint_hold_without_failing_static_nodes() -> None:
    module = _load_validator()
    hou = _Hou()
    moving = {float(frame): _Matrix4(rotate_z=(frame - 1) * 90.0) for frame in (1, 2, 3, 4, 5, 6)}
    hou.nodes["/obj/moving"] = _ObjNode("/obj/moving", hou, moving)
    hou.nodes["/obj/static"] = _ObjNode("/obj/static", hou, _constant_transforms((1.0, 2.0, 3.0, 4.0, 5.0, 6.0)))

    with patch.dict(sys.modules, {"hou": hou}):
        result = module.validate_loop_contract(["/obj/moving", "/obj/static"], 1, 5)

    moving_diagnostic, static_diagnostic = result["context"]["nodes"]
    assert moving_diagnostic["endpoint_duplicate_delta"]["angular_degrees"] == pytest.approx(0.0)
    assert moving_diagnostic["first_step_motion"]["angular_degrees"] == pytest.approx(90.0)
    assert moving_diagnostic["duplicate_endpoint_hold_risk"] is True
    assert static_diagnostic["duplicate_endpoint_hold_risk"] is False


def test_validate_loop_contract_marks_non_finite_samples_and_restores_frame() -> None:
    module = _load_validator()
    hou = _Hou(original_frame=17.0)
    transforms = _constant_transforms((1.0, 2.0, 3.0, 4.0, 5.0, 6.0))
    transforms[6.0] = _Matrix4(
        translate=(float("nan"), 0, 0),
        matrix_override=(float("nan"),) + (0.0,) * 15,
    )
    hou.nodes["/obj/nonfinite"] = _ObjNode("/obj/nonfinite", hou, transforms)

    with patch.dict(sys.modules, {"hou": hou}):
        result = module.validate_loop_contract(["/obj/nonfinite"], 1, 5)

    assert result["success"] is True
    diagnostic = result["context"]["nodes"][0]
    assert diagnostic["finite"] is False
    assert diagnostic["passed"] is False
    assert diagnostic["checks"]["finite"] is False
    assert hou.current_frame == 17.0


@pytest.mark.parametrize(
    "node_paths,start,end,error_fragment",
    [
        (["/stage/world"], 1, 5, "under /obj"),
        (["/obj/a"] * 65, 1, 5, "at most 64"),
        (["/obj/a"], -1_000_001, 5, "bounded"),
        (["/obj/a"], 999_995, 1_000_000, "virtual"),
        (["/obj/a"], 1, 4, "at least four sample steps"),
    ],
)
def test_validate_loop_contract_rejects_unbounded_requests(
    node_paths: List[str], start: float, end: float, error_fragment: str
) -> None:
    module = _load_validator()
    hou = _Hou()
    with patch.dict(sys.modules, {"hou": hou}):
        result = module.validate_loop_contract(node_paths, start, end)
    assert result["success"] is False
    assert error_fragment in result["error"]
    assert hou.set_frame_calls == []


def _post_mcp(url: str, payload: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read())


def test_loop_validator_discovery_load_and_call_path(monkeypatch, tmp_path: Path) -> None:
    tools = yaml.safe_load((_SKILL_ROOT / "tools.yaml").read_text(encoding="utf-8"))["tools"]
    metadata = next(tool for tool in tools if tool["name"] == "validate_loop_contract")
    assert metadata["source_file"] == "scripts/validate_loop_contract.py"
    assert metadata["execution"] == "sync"
    assert metadata["affinity"] == "main"
    assert metadata["read_only"] is True
    assert metadata["destructive"] is False
    assert metadata["idempotent"] is True

    monkeypatch.setenv("MCP_LOG_LEVEL", "WARN")
    monkeypatch.setenv("DCC_MCP_LOG_LEVEL", "WARN")
    monkeypatch.setenv("DCC_MCP_REGISTRY_DIR", str(tmp_path / "registry"))
    config = McpHttpConfig(port=0, server_name="houdini-animation-loop-test")
    config.gateway_port = 0
    dispatcher = QueueDispatcher()
    host = StandaloneHost(dispatcher)
    calls = []

    def executor(script_path: str, params: dict, **call_metadata: Any) -> dict:
        calls.append({"script_path": script_path, "params": params, **call_metadata})
        return {"success": True, "message": "captured", "context": {"passed": True}}

    server = create_skill_server("houdini", config)
    server.attach_dispatcher(dispatcher)
    server.set_in_process_executor(executor)
    assert server.discover(extra_paths=[str(_SKILLS_ROOT)]) >= 1
    loaded = server.load_skill("houdini-animation")
    assert "houdini_animation__validate_loop_contract" in loaded

    host.start()
    handle = server.start()
    try:
        listed = _post_mcp(handle.mcp_url(), {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        listed_tools = {tool["name"]: tool for tool in listed["result"]["tools"]}
        assert listed_tools["validate_loop_contract"]["annotations"]["readOnlyHint"] is True

        arguments = {"node_paths": ["/obj/planet"], "start_frame": 1, "end_frame": 5}
        called = _post_mcp(
            handle.mcp_url(),
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "validate_loop_contract", "arguments": arguments},
            },
        )
        assert called["result"]["isError"] is False
        assert called["result"]["structuredContent"]["context"]["passed"] is True
    finally:
        handle.shutdown()
        host.stop()

    assert len(calls) == 1
    assert calls[0]["params"] == arguments
    assert calls[0]["action_name"] == "houdini_animation__validate_loop_contract"
    assert calls[0]["thread_affinity"] == "main"
    assert calls[0]["execution"] == "sync"
