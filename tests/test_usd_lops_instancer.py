"""Contracts for read-only PointInstancer (scattered assets) inspection.

Unit tests use dependency-free USD doubles. A separate, optional block builds
real in-memory ``pxr`` PointInstancer stages as layered evidence; it is skipped
cleanly where ``usd-core`` is not installed (the project's Python 3.7 floor does
not require pxr), so no 3.8+-only dependency is introduced into the test env.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

import pytest
from skill_loader import skill_script_import_context

_SKILLS_ROOT = Path(__file__).parent.parent / "src" / "dcc_mcp_houdini" / "skills"
_ROOT = _SKILLS_ROOT / "houdini-usd-lops"


def _load_script(name: str) -> ModuleType:
    path = _ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location("usd_instancer_{}".format(path.stem), path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    with skill_script_import_context(spec):
        spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Dependency-free USD doubles
# ---------------------------------------------------------------------------
class _Path(str):
    pass


class _Attribute:
    def __init__(self, value):
        self._value = value
        self.time = None

    def Get(self, time):
        self.time = time
        return self._value


class _Relationship:
    def __init__(self, targets):
        self._targets = list(targets)

    def GetTargets(self):
        return list(self._targets)


class _Prim:
    def __init__(
        self,
        path,
        type_name="PointInstancer",
        attributes=None,
        prototype_targets=None,
        is_instancer=True,
    ):
        self._path = path
        self._type_name = type_name
        self._attributes = attributes or {}
        self._proto_targets = prototype_targets or []
        self._is_instancer = is_instancer

    def __bool__(self):
        return True

    def GetPath(self):
        return _Path(self._path)

    def GetTypeName(self):
        return self._type_name

    def GetAttribute(self, name):
        return self._attributes.get(name)

    def GetRelationship(self, name):
        return _Relationship(self._proto_targets) if name == "prototypes" else None


class _Schema:
    def __init__(self, valid):
        self._valid = valid

    def __bool__(self):
        return self._valid


def _point_instancer_schema(prim):
    return _Schema(bool(getattr(prim, "_is_instancer", False)))


class _Stage:
    def __init__(self, prims):
        self._prims = prims

    def GetPrimAtPath(self, path):
        return self._prims.get(str(path))


class _Node:
    def __init__(self, stage):
        self._stage = stage

    def path(self):
        return "/stage/OUT"

    def stage(self):
        return self._stage


class _TimeCode:
    def __init__(self, value):
        self.value = value

    @classmethod
    def Default(cls):
        return cls("default")


def _hou_module(stage):
    node = _Node(stage)
    module = ModuleType("hou")
    module.node = lambda path: node if path == "/stage/OUT" else None  # type: ignore[attr-defined]
    return module


def _pxr_modules():
    module = ModuleType("pxr")
    Usd = SimpleNamespace(TimeCode=_TimeCode)
    UsdGeom = SimpleNamespace(PointInstancer=_point_instancer_schema)
    module.Usd = Usd  # type: ignore[attr-defined]
    module.UsdGeom = UsdGeom  # type: ignore[attr-defined]
    return {
        "pxr": module,
        "pxr.Usd": Usd,
        "pxr.UsdGeom": UsdGeom,
    }


def _instancer_prim(
    proto_indices=(0, 0, 1),
    prototype_targets=("/World/scatter/Protos/rock", "/World/scatter/Protos/tree"),
    positions=((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (2.0, 0.0, 0.0)),
):
    attributes = {
        "protoIndices": _Attribute(list(proto_indices)),
        "positions": _Attribute([list(p) for p in positions]),
    }
    return _Prim(
        "/World/scatter",
        attributes=attributes,
        prototype_targets=list(prototype_targets),
    )


def _run(mod, prim, **kwargs):
    stage = _Stage({"/World/scatter": prim})
    modules = dict(_pxr_modules(), hou=_hou_module(stage))
    with patch.dict(sys.modules, modules):
        return mod.get_instancer_info("/stage/OUT", "/World/scatter", **kwargs)


# ---------------------------------------------------------------------------
# Import-safety and well-formed scatter
# ---------------------------------------------------------------------------
def test_script_uses_pxr_import_shape_only():
    source = (_ROOT / "scripts" / "get_instancer_info.py").read_text(encoding="utf-8")
    assert "from pxr import" in source
    assert "\n    import Usd" not in source
    assert "\n    import UsdGeom" not in source


def test_instancer_info_reports_well_formed_scatter():
    mod = _load_script("get_instancer_info.py")
    result = _run(mod, _instancer_prim())

    assert result["success"] is True
    context = result["context"]
    assert context["instance_count"] == 3
    assert context["prototype_count"] == 2
    assert context["prototypes"] == ["/World/scatter/Protos/rock", "/World/scatter/Protos/tree"]
    assert context["proto_indices"]["value"] == [0, 0, 1]
    assert context["instance_arrays"]["positions"]["value"] == [
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [2.0, 0.0, 0.0],
    ]
    assert context["array_counts"]["protoIndices"] == 3
    assert context["array_counts"]["positions"] == 3
    assert context["array_counts"]["orientations"] == 0
    validation = context["validation"]
    assert validation["proto_indices_in_range"] is True
    assert validation["out_of_range_count"] == 0
    assert validation["per_instance_arrays_match"] is True
    assert validation["consistent"] is True
    assert validation["issue_codes"] == []


def test_instancer_info_never_authors_to_stage():
    mod = _load_script("get_instancer_info.py")
    prim = _instancer_prim()
    # The doubles expose no CreateAttribute/Set — any authoring attempt raises.
    before = dict(prim._attributes)
    result = _run(mod, prim)
    assert result["success"] is True
    assert set(prim._attributes) == set(before)


# ---------------------------------------------------------------------------
# Decidable validation verdicts
# ---------------------------------------------------------------------------
def test_proto_indices_out_of_range_is_flagged():
    mod = _load_script("get_instancer_info.py")
    prim = _instancer_prim(proto_indices=(0, 2, 5), positions=((0, 0, 0),) * 3)
    result = _run(mod, prim)

    assert result["success"] is True
    validation = result["context"]["validation"]
    assert validation["proto_indices_in_range"] is False
    assert validation["out_of_range_count"] == 2
    assert "proto_indices_out_of_range" in validation["issue_codes"]
    assert validation["consistent"] is False


def test_negative_and_non_integer_indices_are_flagged():
    mod = _load_script("get_instancer_info.py")
    prim = _instancer_prim(proto_indices=(-1, 0), positions=((0, 0, 0),) * 2)
    validation = _run(mod, prim)["context"]["validation"]
    assert validation["out_of_range_count"] == 1
    assert validation["proto_indices_in_range"] is False


def test_missing_prototypes_is_flagged():
    mod = _load_script("get_instancer_info.py")
    prim = _instancer_prim(proto_indices=(0, 0), prototype_targets=(), positions=((0, 0, 0),) * 2)
    validation = _run(mod, prim)["context"]["validation"]
    assert validation["prototype_count"] == 0
    assert "missing_prototypes" in validation["issue_codes"]
    assert validation["consistent"] is False


def test_per_instance_array_length_mismatch_is_flagged():
    mod = _load_script("get_instancer_info.py")
    prim = _instancer_prim(proto_indices=(0, 0, 0), positions=((0, 0, 0), (1, 0, 0)))
    validation = _run(mod, prim)["context"]["validation"]
    assert validation["per_instance_arrays_match"] is False
    assert "positions_length_mismatch" in validation["issue_codes"]
    assert validation["consistent"] is False


def test_empty_instancer_is_consistent():
    mod = _load_script("get_instancer_info.py")
    prim = _instancer_prim(proto_indices=(), positions=())
    validation = _run(mod, prim)["context"]["validation"]
    assert validation["instance_count"] == 0
    assert validation["consistent"] is True
    assert validation["issue_codes"] == []


# ---------------------------------------------------------------------------
# Bounds, errors, and time codes
# ---------------------------------------------------------------------------
def test_arrays_and_prototypes_are_bounded():
    mod = _load_script("get_instancer_info.py")
    prim = _instancer_prim(
        proto_indices=tuple(range(100)),
        prototype_targets=tuple("/proto{}".format(i) for i in range(100)),
        positions=tuple((float(i), 0.0, 0.0) for i in range(100)),
    )
    result = _run(mod, prim, max_values=5, max_prototypes=3)

    assert result["success"] is True
    context = result["context"]
    assert context["instance_count"] == 100
    assert context["prototype_count"] == 100
    assert len(context["prototypes"]) == 3
    assert context["prototypes_truncated"] is True
    assert context["proto_indices"]["truncated"] is True
    assert len(context["proto_indices"]["value"]) <= 5
    # Bounds are echoed so a caller can tell the validation used full data.
    assert context["bounds"] == {"max_values": 5, "max_prototypes": 3}
    # Full counts are reported even when the samples are truncated.
    assert context["array_counts"]["protoIndices"] == 100
    assert context["array_counts"]["positions"] == 100
    # Range validation uses the full protoIndices, not the truncated sample.
    assert context["validation"]["out_of_range_count"] == 0


@pytest.mark.parametrize(
    "bounds",
    [
        {"max_values": 0},
        {"max_values": 257},
        {"max_prototypes": 0},
        {"max_prototypes": 257},
    ],
)
def test_invalid_bounds_are_rejected(bounds):
    mod = _load_script("get_instancer_info.py")
    result = _run(mod, _instancer_prim(), **bounds)
    assert result["success"] is False


def test_non_instancer_prim_is_rejected():
    mod = _load_script("get_instancer_info.py")
    prim = _Prim("/World/mesh", type_name="Mesh", is_instancer=False)
    result = _run(mod, prim)
    assert result["success"] is False
    assert "PointInstancer" in json.dumps(result)


def test_missing_prim_is_rejected():
    mod = _load_script("get_instancer_info.py")
    stage = _Stage({})
    modules = dict(_pxr_modules(), hou=_hou_module(stage))
    with patch.dict(sys.modules, modules):
        result = mod.get_instancer_info("/stage/OUT", "/World/missing")
    assert result["success"] is False


def test_time_code_is_forwarded_to_array_reads():
    mod = _load_script("get_instancer_info.py")
    prim = _instancer_prim()
    result = _run(mod, prim, time_code=7.0)
    assert result["success"] is True
    assert result["context"]["time_code"] == 7.0
    assert prim._attributes["protoIndices"].time.value == 7.0


def test_requires_houdini_usd_apis():
    mod = _load_script("get_instancer_info.py")
    with patch.dict(sys.modules, {"hou": None, "pxr": None}):
        result = mod.get_instancer_info("/stage/OUT", "/World/scatter")
    assert result["success"] is False


# ---------------------------------------------------------------------------
# Layered evidence: real pxr (usd-core) in-memory stages. Skipped on runtimes
# without pxr (e.g. Python 3.7 CI), so no hard 3.8+ dependency is introduced.
# ---------------------------------------------------------------------------
def _real_pxr():
    pytest.importorskip("pxr.UsdGeom", reason="usd-core not installed; real-stage evidence skipped")
    from pxr import Gf, Sdf, Usd, UsdGeom, Vt  # noqa: F401

    return Usd, UsdGeom, Sdf, Gf, Vt


def _real_hou(stage):
    module = ModuleType("hou")
    node = _Node(stage)
    module.node = lambda path: node if path == "/stage/OUT" else None  # type: ignore[attr-defined]
    return module


def _real_run(mod, stage, prim_path, **kwargs):
    with patch.dict(sys.modules, {"hou": _real_hou(stage)}):
        return mod.get_instancer_info("/stage/OUT", prim_path, **kwargs)


def test_real_pxr_well_formed_instancer_is_consistent():
    Usd, UsdGeom, Sdf, Gf, Vt = _real_pxr()
    mod = _load_script("get_instancer_info.py")
    stage = Usd.Stage.CreateInMemory()
    pi = UsdGeom.PointInstancer.Define(stage, "/World/scatter")
    rock = stage.DefinePrim("/World/scatter/Protos/rock", "Xform")
    pi.GetPrototypesRel().SetTargets([rock.GetPath()])
    pi.GetProtoIndicesAttr().Set(Vt.IntArray([0, 0, 0]))
    pi.GetPositionsAttr().Set(Vt.Vec3fArray([Gf.Vec3f(0, 0, 0), Gf.Vec3f(1, 0, 0), Gf.Vec3f(2, 0, 0)]))
    pi.GetScalesAttr().Set(Vt.Vec3fArray([Gf.Vec3f(1, 1, 1)] * 3))

    result = _real_run(mod, stage, "/World/scatter")

    assert result["success"] is True
    context = result["context"]
    assert context["instance_count"] == 3
    assert context["prototype_count"] == 1
    assert context["prototypes"] == ["/World/scatter/Protos/rock"]
    assert context["proto_indices"]["value"] == [0, 0, 0]
    assert context["validation"]["consistent"] is True
    assert context["validation"]["issue_codes"] == []


def test_real_pxr_out_of_range_instancer_is_flagged():
    Usd, UsdGeom, Sdf, Gf, Vt = _real_pxr()
    mod = _load_script("get_instancer_info.py")
    stage = Usd.Stage.CreateInMemory()
    pi = UsdGeom.PointInstancer.Define(stage, "/World/scatter")
    rock = stage.DefinePrim("/World/scatter/Protos/rock", "Xform")
    pi.GetPrototypesRel().SetTargets([rock.GetPath()])
    pi.GetProtoIndicesAttr().Set(Vt.IntArray([0, 3, 0]))
    pi.GetPositionsAttr().Set(Vt.Vec3fArray([Gf.Vec3f(0, 0, 0), Gf.Vec3f(1, 0, 0), Gf.Vec3f(2, 0, 0)]))

    result = _real_run(mod, stage, "/World/scatter")

    assert result["success"] is True
    validation = result["context"]["validation"]
    assert validation["out_of_range_count"] == 1
    assert validation["proto_indices_in_range"] is False
    assert "proto_indices_out_of_range" in validation["issue_codes"]
    assert validation["consistent"] is False


def test_real_pxr_non_instancer_prim_is_rejected():
    Usd, UsdGeom, Sdf, Gf, Vt = _real_pxr()
    mod = _load_script("get_instancer_info.py")
    stage = Usd.Stage.CreateInMemory()
    stage.DefinePrim("/World/geo", "Xform")

    result = _real_run(mod, stage, "/World/geo")

    assert result["success"] is False
    assert "PointInstancer" in json.dumps(result)
