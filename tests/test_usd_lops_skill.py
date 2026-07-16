"""Tests for bounded, read-only Solaris/USD inspection (no Houdini process)."""

from __future__ import annotations

import importlib.util
import json
import sys
import urllib.request
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import patch

from dcc_mcp_core import McpHttpConfig, create_skill_server, validate_skill
from dcc_mcp_core.host import QueueDispatcher, StandaloneHost

_SKILLS_ROOT = Path(__file__).parent.parent / "src" / "dcc_mcp_houdini" / "skills"
_SKILL_ROOT = _SKILLS_ROOT / "houdini-usd-lops"


def _load_script(name: str) -> ModuleType:
    path = _SKILL_ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location("usd_lops_{}".format(path.stem), path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _Attribute:
    def __init__(self, name: str, value: Any, type_name: str = "float[]") -> None:
        self._name = name
        self._value = value
        self._type_name = type_name
        self.time_code = None

    def GetName(self) -> str:
        return self._name

    def GetTypeName(self) -> str:
        return self._type_name

    def Get(self, time_code: Any) -> Any:
        self.time_code = time_code
        return self._value

    def HasAuthoredValueOpinion(self) -> bool:
        return True


class _Prim:
    def __init__(
        self,
        path: str,
        type_name: str = "Xform",
        children: Optional[List["_Prim"]] = None,
        attributes: Optional[List[_Attribute]] = None,
    ) -> None:
        self._path = path
        self._type_name = type_name
        self._children = children or []
        self._attributes = attributes or []

    def __bool__(self) -> bool:
        return True

    def GetPath(self) -> "_Path":
        return _Path(self._path)

    def GetName(self) -> str:
        return self._path.rsplit("/", 1)[-1]

    def GetTypeName(self) -> str:
        return self._type_name

    def GetChildren(self) -> List["_Prim"]:
        return self._children

    def GetAttributes(self) -> List[_Attribute]:
        return self._attributes

    def IsActive(self) -> bool:
        return True

    def IsDefined(self) -> bool:
        return True

    def IsLoaded(self) -> bool:
        return True

    def IsInstance(self) -> bool:
        return False

    def IsInstanceProxy(self) -> bool:
        return False


class _Path(str):
    @property
    def pathElementCount(self) -> int:
        return len([part for part in self.split("/") if part])


class _PrimRangeIterator:
    def __init__(self, root: _Prim) -> None:
        self._stack = [iter([root])]
        self._current = None
        self._prune_current = False

    def __iter__(self):
        return self

    def __next__(self) -> _Prim:
        if self._current is not None and not self._prune_current:
            self._stack.append(iter(self._current.GetChildren()))
        self._current = None
        self._prune_current = False
        while self._stack:
            try:
                self._current = next(self._stack[-1])
                return self._current
            except StopIteration:
                self._stack.pop()
        raise StopIteration

    def PruneChildren(self) -> None:
        self._prune_current = True


class _PrimRange:
    def __init__(self, root: _Prim) -> None:
        self._root = root

    def __iter__(self) -> _PrimRangeIterator:
        return _PrimRangeIterator(self._root)


class _Stage:
    def __init__(self, root: _Prim, prims: Dict[str, _Prim]) -> None:
        self._root = root
        self._prims = prims

    def GetPseudoRoot(self) -> _Prim:
        return self._root

    def GetPrimAtPath(self, path: str) -> Optional[_Prim]:
        return self._prims.get(path)


class _LopNode:
    def __init__(self, stage: _Stage) -> None:
        self._stage = stage

    def path(self) -> str:
        return "/stage/OUT"

    def stage(self) -> _Stage:
        return self._stage


def _hou_module(stage: _Stage) -> ModuleType:
    module = ModuleType("hou")
    node = _LopNode(stage)
    module.node = lambda path: node if path == "/stage/OUT" else None  # type: ignore[attr-defined]
    return module


class _TimeCode:
    def __init__(self, value: Any) -> None:
        self.value = value

    @classmethod
    def Default(cls) -> "_TimeCode":
        return cls("default")


class _XformCache:
    def __init__(self, time_code: _TimeCode) -> None:
        self.time_code = time_code

    def GetLocalToWorldTransform(self, prim: _Prim) -> List[List[float]]:
        del prim
        return [
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [10.0, 20.0, 30.0, 1.0],
        ]


class _Range:
    def IsEmpty(self) -> bool:
        return False

    def GetMin(self) -> List[float]:
        return [-1.0, -2.0, -3.0]

    def GetMax(self) -> List[float]:
        return [1.0, 2.0, 3.0]


class _Bound:
    def ComputeAlignedRange(self) -> _Range:
        return _Range()


class _BBoxCache:
    def __init__(self, time_code: _TimeCode, purposes: List[str], useExtentsHint: bool) -> None:
        self.args = (time_code, purposes, useExtentsHint)

    def ComputeWorldBound(self, prim: _Prim) -> _Bound:
        del prim
        return _Bound()


class _Imageable:
    def __init__(self, prim: _Prim) -> None:
        self.prim = prim

    def __bool__(self) -> bool:
        return True

    def ComputeVisibility(self, time_code: _TimeCode) -> str:
        del time_code
        return "inherited"


class _Material:
    def GetPath(self) -> str:
        return "/World/Looks/clay"


class _MaterialBindingAPI:
    def __init__(self, prim: _Prim) -> None:
        self.prim = prim

    def ComputeBoundMaterial(self) -> tuple:
        return _Material(), None


def _pxr_module() -> ModuleType:
    module = ModuleType("pxr")
    module.Usd = SimpleNamespace(TimeCode=_TimeCode, PrimRange=_PrimRange)  # type: ignore[attr-defined]
    module.UsdGeom = SimpleNamespace(  # type: ignore[attr-defined]
        Tokens=SimpleNamespace(default_="default", proxy="proxy", render="render", guide="guide"),
        Xformable=lambda prim: prim,
        XformCache=_XformCache,
        BBoxCache=_BBoxCache,
        Imageable=_Imageable,
    )
    module.UsdShade = SimpleNamespace(MaterialBindingAPI=_MaterialBindingAPI)  # type: ignore[attr-defined]
    return module


def _sample_stage(attributes: Optional[List[_Attribute]] = None) -> _Stage:
    mesh = _Prim("/World/mesh", "Mesh", attributes=attributes)
    light = _Prim("/World/keyLight", "DistantLight")
    world = _Prim("/World", children=[mesh, light])
    root = _Prim("/", children=[world])
    return _Stage(root, {prim.GetPath(): prim for prim in (world, mesh, light)})


def test_skill_validates_clean() -> None:
    report = validate_skill(str(_SKILL_ROOT))
    assert report.is_clean, report.issues


def test_scripts_import_without_hou_or_pxr() -> None:
    with patch.dict(sys.modules, {"hou": None, "pxr": None}):
        for script in ("list_stage_prims.py", "get_prim_info.py", "get_prim_attributes.py"):
            module = _load_script(script)
            assert "hou" not in module.__dict__
            assert "pxr" not in module.__dict__


def test_list_stage_prims_reports_limit_and_depth_truncation() -> None:
    module = _load_script("list_stage_prims.py")
    stage = _sample_stage()
    with patch.dict(sys.modules, {"hou": _hou_module(stage), "pxr": _pxr_module()}):
        limited = module.list_stage_prims("/stage/OUT", max_depth=3, limit=2)
        shallow = module.list_stage_prims("/stage/OUT", max_depth=1, limit=10)

    assert limited["success"] is True
    assert [prim["path"] for prim in limited["context"]["prims"]] == ["/World", "/World/mesh"]
    assert limited["context"]["truncation_reasons"] == ["limit"]
    assert shallow["context"]["returned_count"] == 1
    assert shallow["context"]["truncation_reasons"] == ["max_depth"]


def test_list_stage_prims_pulls_only_limit_plus_one_from_wide_stage() -> None:
    module = _load_script("list_stage_prims.py")
    pulled = []

    class _WideRoot(_Prim):
        def GetChildren(self):
            for index in range(1000):
                pulled.append(index)
                yield _Prim("/prim{}".format(index))

    root = _WideRoot("/")
    stage = _Stage(root, {})
    with patch.dict(sys.modules, {"hou": _hou_module(stage), "pxr": _pxr_module()}):
        result = module.list_stage_prims("/stage/OUT", limit=1)

    assert result["success"] is True
    assert result["context"]["truncation_reasons"] == ["limit"]
    assert pulled == [0, 1]


def test_list_stage_prims_rejects_invalid_bounds() -> None:
    module = _load_script("list_stage_prims.py")
    stage = _sample_stage()
    with patch.dict(sys.modules, {"hou": _hou_module(stage), "pxr": _pxr_module()}):
        result = module.list_stage_prims("/stage/OUT", max_depth=0, limit=501)
    assert result["success"] is False
    assert "max_depth" in result["error"]


def test_get_prim_info_returns_typed_computed_fields() -> None:
    module = _load_script("get_prim_info.py")
    stage = _sample_stage()
    with patch.dict(sys.modules, {"hou": _hou_module(stage), "pxr": _pxr_module()}):
        result = module.get_prim_info("/stage/OUT", "/World/mesh", time_code=12.5)

    assert result["success"] is True
    prim = result["context"]["prim"]
    assert prim["type_name"] == "Mesh"
    assert prim["active"] is True
    assert prim["visibility"] == "inherited"
    assert prim["world_transform"][3] == [10.0, 20.0, 30.0, 1.0]
    assert prim["world_bounds"] == {"min": [-1.0, -2.0, -3.0], "max": [1.0, 2.0, 3.0]}
    assert prim["material_binding"] == "/World/Looks/clay"


def test_get_prim_info_rejects_non_finite_time_code() -> None:
    module = _load_script("get_prim_info.py")
    stage = _sample_stage()
    with patch.dict(sys.modules, {"hou": _hou_module(stage), "pxr": _pxr_module()}):
        result = module.get_prim_info("/stage/OUT", "/World/mesh", time_code=float("inf"))
    assert result["success"] is False
    assert "finite number" in result["error"]


def test_get_prim_attributes_filters_and_bounds_values() -> None:
    attributes = [
        _Attribute("primvars:displayColor", [1, 2, 3, 4]),
        _Attribute("primvars:label", "x" * 100, "string"),
        _Attribute("visibility", "inherited", "token"),
    ]
    module = _load_script("get_prim_attributes.py")
    stage = _sample_stage(attributes)
    with patch.dict(sys.modules, {"hou": _hou_module(stage), "pxr": _pxr_module()}):
        result = module.get_prim_attributes(
            "/stage/OUT",
            "/World/mesh",
            name_filter="PRIMVARS",
            time_code=7,
            max_attributes=2,
            max_value_items=2,
            max_value_chars=64,
        )

    assert result["success"] is True
    context = result["context"]
    assert context["matched_count"] == 2
    assert context["returned_count"] == 2
    assert context["value_truncated_count"] == 2
    assert context["truncated"] is True
    assert context["attributes"][0]["value"] == [1, 2]
    assert context["attributes"][0]["truncation_reasons"] == ["items"]
    assert context["attributes"][1]["value"] is None
    assert len(context["attributes"][1]["value_preview"]) == 64
    assert attributes[0].time_code.value == 7.0


def test_get_prim_attributes_rejects_oversized_name_filter() -> None:
    module = _load_script("get_prim_attributes.py")
    stage = _sample_stage()
    with patch.dict(sys.modules, {"hou": _hou_module(stage), "pxr": _pxr_module()}):
        result = module.get_prim_attributes("/stage/OUT", "/World/mesh", name_filter="x" * 129)
    assert result["success"] is False
    assert "128 characters" in result["error"]


def _post_mcp(url: str, payload: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read())


def test_scan_load_tools_list_and_call_integration(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MCP_LOG_LEVEL", "WARN")
    monkeypatch.setenv("DCC_MCP_LOG_LEVEL", "WARN")
    monkeypatch.setenv("DCC_MCP_REGISTRY_DIR", str(tmp_path / "registry"))
    config = McpHttpConfig(port=0, server_name="houdini-usd-lops-test")
    config.gateway_port = 0
    dispatcher = QueueDispatcher()
    host = StandaloneHost(dispatcher)
    calls = []

    def executor(script_path: str, params: dict, **metadata: Any) -> dict:
        calls.append({"script_path": script_path, "params": params, **metadata})
        return {"success": True, "message": "captured", "context": params}

    server = create_skill_server("houdini", config)
    server.attach_dispatcher(dispatcher)
    server.set_in_process_executor(executor)
    assert server.discover(extra_paths=[str(_SKILLS_ROOT)]) >= 1
    loaded = server.load_skill("houdini-usd-lops")
    assert set(loaded) == {
        "houdini_usd_lops__list_stage_prims",
        "houdini_usd_lops__get_prim_info",
        "houdini_usd_lops__get_prim_attributes",
    }

    host.start()
    handle = server.start()
    try:
        listed = _post_mcp(handle.mcp_url(), {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        tools = {tool["name"]: tool for tool in listed["result"]["tools"]}
        assert {"list_stage_prims", "get_prim_info", "get_prim_attributes"} <= set(tools)
        assert tools["list_stage_prims"]["annotations"]["readOnlyHint"] is True

        called = _post_mcp(
            handle.mcp_url(),
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "list_stage_prims", "arguments": {"lop_node_path": "/stage/OUT"}},
            },
        )
        assert called["result"]["isError"] is False
        assert called["result"]["structuredContent"]["success"] is True
    finally:
        handle.shutdown()
        host.stop()

    assert len(calls) == 1
    assert calls[0]["params"] == {"lop_node_path": "/stage/OUT"}
    assert calls[0]["action_name"] == "houdini_usd_lops__list_stage_prims"
    assert calls[0]["thread_affinity"] == "main"
    assert calls[0]["execution"] == "sync"
