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


class _TimeSampledAttribute:
    """Doubles an array authored only as time samples (no default value).

    At ``Usd.TimeCode.Default()`` such an attribute reads empty; at
    ``EarliestTime()`` or a numeric time it returns the real sample data.
    """

    def __init__(self, value, sample_time=1.0, default=None):
        self._value = value
        self._sample_time = sample_time
        self._default = default
        self.read_times = []

    def GetNumTimeSamples(self):
        return 1

    def GetTimeSamples(self):
        return [self._sample_time]

    def Get(self, time):
        self.read_times.append(time)
        if getattr(time, "value", None) == "default":
            return self._default
        return self._value


class _Quat:
    """Doubles Gf.Quath: non-iterable, with GetReal/GetImaginary."""

    def __init__(self, real, i, j, k):
        self._real = real
        self._imag = (i, j, k)

    def GetReal(self):
        return self._real

    def GetImaginary(self):
        return self._imag


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

    @classmethod
    def EarliestTime(cls):
        return cls("earliest")


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


def _instancer_prim_with_positions(proto_indices, positions, prototype_targets=None):
    """Build a scatter double with an explicit (possibly missing/empty) positions.

    ``positions=None`` leaves the attribute unauthored; ``[]`` authors an empty
    array. Both are USD-invalid when instances exist (F2 regression).
    """
    attributes = {"protoIndices": _Attribute(list(proto_indices))}
    if positions is not None:
        attributes["positions"] = _Attribute(list(positions))
    return _Prim(
        "/World/scatter",
        attributes=attributes,
        prototype_targets=list(prototype_targets or ("/World/scatter/Protos/rock",)),
    )


def _time_sampled_instancer_prim(
    proto_indices=(0, 0),
    positions=((0.0, 0.0, 0.0), (1.0, 0.0, 0.0)),
    prototype_targets=("/World/scatter/Protos/rock", "/World/scatter/Protos/tree"),
    sample_time=1.0,
):
    """A scatter whose arrays exist only as time samples (no default value)."""
    attributes = {
        "protoIndices": _TimeSampledAttribute(list(proto_indices), sample_time),
        "positions": _TimeSampledAttribute([list(p) for p in positions], sample_time),
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


# ---------------------------------------------------------------------------
# F2 regression: USD requires positions to be authored and match instance count.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("positions", [None, []])
def test_missing_or_empty_positions_is_flagged(positions):
    """F2: a scatter with instances but no (or empty) positions produces no
    instance transforms, so it must never be reported as consistent."""
    mod = _load_script("get_instancer_info.py")
    prim = _instancer_prim_with_positions([0, 0], positions)
    result = _run(mod, prim)

    assert result["success"] is True
    context = result["context"]
    assert context["instance_count"] == 2
    assert context["array_counts"]["positions"] == 0
    validation = context["validation"]
    assert validation["per_instance_arrays_match"] is False
    assert "positions_length_mismatch" in validation["issue_codes"]
    assert validation["consistent"] is False


def test_optional_arrays_may_stay_empty_when_positions_match():
    """orientations/scales are optional: empty them without a false mismatch."""
    mod = _load_script("get_instancer_info.py")
    prim = _instancer_prim(proto_indices=(0, 0), positions=((0, 0, 0), (1, 0, 0)))
    prim._attributes["orientations"] = _Attribute([])
    prim._attributes["scales"] = _Attribute([])
    validation = _run(mod, prim)["context"]["validation"]
    assert validation["per_instance_arrays_match"] is True
    assert "positions_length_mismatch" not in validation["issue_codes"]
    assert validation["consistent"] is True
    assert validation["issue_codes"] == []


def test_empty_instancer_is_consistent():
    mod = _load_script("get_instancer_info.py")
    prim = _instancer_prim(proto_indices=(), positions=())
    validation = _run(mod, prim)["context"]["validation"]
    assert validation["instance_count"] == 0
    assert validation["consistent"] is True
    assert validation["issue_codes"] == []


# ---------------------------------------------------------------------------
# F1 regression: time-sampled-only scatter must never be a silent green.
# ---------------------------------------------------------------------------
def test_timesampled_only_without_time_code_is_not_false_consistent():
    """F1: arrays with only time samples read empty at Default(); the tool must
    re-read at the earliest sample and refuse to report a silent ``consistent``."""
    mod = _load_script("get_instancer_info.py")
    prim = _time_sampled_instancer_prim()
    result = _run(mod, prim)

    assert result["success"] is True
    context = result["context"]
    # Real data was read at the earliest sample, not an empty default.
    assert context["instance_count"] == 2
    assert context["array_counts"]["protoIndices"] == 2
    assert context["proto_indices"]["value"] == [0, 0]
    assert context["time_code_source"] == "earliest_sample"
    assert context["effective_time_code"] == 1.0
    assert "protoIndices" in context["time_sampled_arrays"]
    validation = context["validation"]
    assert "time_samples_require_time_code" in validation["issue_codes"]
    assert validation["consistent"] is False


def test_timesampled_only_out_of_range_indices_are_still_flagged():
    """F1: re-reading at the earliest sample keeps range validation honest, so a
    bad protoIndex in a time-varying scatter is reported, not a false green."""
    mod = _load_script("get_instancer_info.py")
    prim = _time_sampled_instancer_prim(proto_indices=(0, 5))
    validation = _run(mod, prim)["context"]["validation"]
    assert validation["out_of_range_count"] == 1
    assert "proto_indices_out_of_range" in validation["issue_codes"]
    assert "time_samples_require_time_code" in validation["issue_codes"]
    assert validation["consistent"] is False


def test_explicit_time_code_skips_earliest_sample_reread():
    """When the caller pins a time code, the tool validates at that time and does
    not flag time_samples_require_time_code."""
    mod = _load_script("get_instancer_info.py")
    prim = _time_sampled_instancer_prim()
    result = _run(mod, prim, time_code=1.0)

    assert result["success"] is True
    context = result["context"]
    assert context["time_code"] == 1.0
    assert context["time_code_source"] == "explicit"
    assert context["effective_time_code"] == 1.0
    assert context["time_sampled_arrays"] == []
    assert context["instance_count"] == 2
    assert context["validation"]["consistent"] is True
    assert context["validation"]["issue_codes"] == []


def test_default_value_arrays_are_not_flagged_as_time_sampled():
    """Arrays with a default value must follow the normal path (no flag)."""
    mod = _load_script("get_instancer_info.py")
    result = _run(mod, _instancer_prim())
    assert result["context"]["time_code_source"] == "default"
    assert result["context"]["time_sampled_arrays"] == []
    assert "time_samples_require_time_code" not in result["context"]["validation"]["issue_codes"]


def test_orientations_are_decomposed_to_numeric_arrays():
    """P3: quaternion orientations become [real, i, j, k] numeric lists."""
    mod = _load_script("get_instancer_info.py")
    prim = _instancer_prim()
    prim._attributes["orientations"] = _Attribute([_Quat(1.0, 0.5, 0.25, 0.125)] * 3)
    result = _run(mod, prim)

    assert result["success"] is True
    sample = result["context"]["instance_arrays"]["orientations"]["value"]
    assert sample == [[1.0, 0.5, 0.25, 0.125]] * 3


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


def test_real_pxr_timesampled_only_without_time_code_is_not_false_consistent():
    """F1 (real usd-core): protoIndices/positions authored ONLY as time samples at
    t=1 have no default value. At Default() they read empty (which previously gave
    instance_count=0, consistent=True). The fix must re-read at the earliest
    sample and refuse a silent green, while keeping range validation honest.
    """
    Usd, UsdGeom, Sdf, Gf, Vt = _real_pxr()
    mod = _load_script("get_instancer_info.py")
    stage = Usd.Stage.CreateInMemory()
    pi = UsdGeom.PointInstancer.Define(stage, "/World/scatter")
    rock = stage.DefinePrim("/World/scatter/Protos/rock", "Xform")
    pi.GetPrototypesRel().SetTargets([rock.GetPath()])
    sample_time = Usd.TimeCode(1.0)
    pi.GetProtoIndicesAttr().Set(Vt.IntArray([0, 5]), sample_time)
    pi.GetPositionsAttr().Set(Vt.Vec3fArray([Gf.Vec3f(0, 0, 0), Gf.Vec3f(1, 0, 0)]), sample_time)

    # Sanity: the arrays really are time-sampled-only (empty at Default()).
    assert pi.GetProtoIndicesAttr().GetNumTimeSamples() == 1
    assert pi.GetProtoIndicesAttr().Get(Usd.TimeCode.Default()) is None

    result = _real_run(mod, stage, "/World/scatter")  # no time_code

    assert result["success"] is True
    context = result["context"]
    assert context["instance_count"] == 2
    assert context["proto_indices"]["value"] == [0, 5]
    assert context["time_code_source"] == "earliest_sample"
    assert context["effective_time_code"] == 1.0
    validation = context["validation"]
    assert "time_samples_require_time_code" in validation["issue_codes"]
    # 5 is out of range for the single prototype -> honest range check on re-read.
    assert "proto_indices_out_of_range" in validation["issue_codes"]
    assert validation["consistent"] is False


def test_real_pxr_timesampled_only_with_explicit_time_code_validates_normally():
    """F1 complement: pinning the frame validates real data with no false flag."""
    Usd, UsdGeom, Sdf, Gf, Vt = _real_pxr()
    mod = _load_script("get_instancer_info.py")
    stage = Usd.Stage.CreateInMemory()
    pi = UsdGeom.PointInstancer.Define(stage, "/World/scatter")
    rock = stage.DefinePrim("/World/scatter/Protos/rock", "Xform")
    tree = stage.DefinePrim("/World/scatter/Protos/tree", "Xform")
    pi.GetPrototypesRel().SetTargets([rock.GetPath(), tree.GetPath()])
    sample_time = Usd.TimeCode(1.0)
    pi.GetProtoIndicesAttr().Set(Vt.IntArray([0, 1]), sample_time)
    pi.GetPositionsAttr().Set(Vt.Vec3fArray([Gf.Vec3f(0, 0, 0), Gf.Vec3f(1, 0, 0)]), sample_time)

    result = _real_run(mod, stage, "/World/scatter", time_code=1.0)

    assert result["success"] is True
    context = result["context"]
    assert context["time_code_source"] == "explicit"
    assert context["time_sampled_arrays"] == []
    assert context["instance_count"] == 2
    assert context["validation"]["consistent"] is True
    assert context["validation"]["issue_codes"] == []


def test_real_pxr_orientations_quat_is_numeric_array():
    """P3 (real usd-core): Gf.Quath orientations must be [real, i, j, k] numeric
    lists, not stringified tuples that a caller cannot parse.
    """
    Usd, UsdGeom, Sdf, Gf, Vt = _real_pxr()
    mod = _load_script("get_instancer_info.py")
    stage = Usd.Stage.CreateInMemory()
    pi = UsdGeom.PointInstancer.Define(stage, "/World/scatter")
    rock = stage.DefinePrim("/World/scatter/Protos/rock", "Xform")
    pi.GetPrototypesRel().SetTargets([rock.GetPath()])
    pi.GetProtoIndicesAttr().Set(Vt.IntArray([0, 0]))
    pi.GetPositionsAttr().Set(Vt.Vec3fArray([Gf.Vec3f(0, 0, 0), Gf.Vec3f(1, 0, 0)]))
    quats = Vt.QuathArray([Gf.Quath(1.0, 0.5, 0.25, 0.125), Gf.Quath(0.0, 1.0, 0.0, 0.0)])
    pi.GetOrientationsAttr().Set(quats)

    result = _real_run(mod, stage, "/World/scatter")

    assert result["success"] is True
    sample = result["context"]["instance_arrays"]["orientations"]["value"]
    assert sample == [[1.0, 0.5, 0.25, 0.125], [0.0, 1.0, 0.0, 0.0]]
    for entry in sample:
        assert all(isinstance(component, float) for component in entry)


@pytest.mark.parametrize("positions_mode", ["unauthored", "empty"])
def test_real_pxr_missing_or_empty_positions_is_flagged(positions_mode):
    """F2 (real usd-core): USD requires ``positions`` to be authored and to
    match ``protoIndices`` length. With instances but no/empty positions,
    ComputeInstanceTransformsAtTime yields zero transforms and warns "no
    positions"/"expected [2]"; the tool must flag it, not report consistent.
    """
    Usd, UsdGeom, Sdf, Gf, Vt = _real_pxr()
    mod = _load_script("get_instancer_info.py")
    stage = Usd.Stage.CreateInMemory()
    pi = UsdGeom.PointInstancer.Define(stage, "/World/scatter")
    rock = stage.DefinePrim("/World/scatter/Protos/rock", "Xform")
    pi.GetPrototypesRel().SetTargets([rock.GetPath()])
    pi.GetProtoIndicesAttr().Set(Vt.IntArray([0, 0]))

    positions_attr = pi.GetPositionsAttr()
    if positions_mode == "unauthored":
        assert positions_attr.Get(Usd.TimeCode.Default()) is None
    else:
        positions_attr.Set(Vt.Vec3fArray([]))
        assert len(positions_attr.Get(Usd.TimeCode.Default())) == 0
    assert pi.GetProtoIndicesAttr().GetNumTimeSamples() == 0

    # Ground truth from USD itself: no instance transforms without positions.
    default = Usd.TimeCode.Default()
    transforms = pi.ComputeInstanceTransformsAtTime(default, default)
    assert len(list(transforms)) == 0

    result = _real_run(mod, stage, "/World/scatter")

    assert result["success"] is True
    context = result["context"]
    assert context["instance_count"] == 2
    assert context["array_counts"]["positions"] == 0
    validation = context["validation"]
    assert validation["per_instance_arrays_match"] is False
    assert "positions_length_mismatch" in validation["issue_codes"]
    # No time samples were authored, so F1's flag stays off (isolates F2).
    assert "time_samples_require_time_code" not in validation["issue_codes"]
    assert validation["consistent"] is False


def test_real_pxr_matching_positions_is_consistent():
    """F2 complement (real usd-core): positions length == instance count, and
    empty optional orientations/scales, stays a clean consistent verdict."""
    Usd, UsdGeom, Sdf, Gf, Vt = _real_pxr()
    mod = _load_script("get_instancer_info.py")
    stage = Usd.Stage.CreateInMemory()
    pi = UsdGeom.PointInstancer.Define(stage, "/World/scatter")
    rock = stage.DefinePrim("/World/scatter/Protos/rock", "Xform")
    pi.GetPrototypesRel().SetTargets([rock.GetPath()])
    pi.GetProtoIndicesAttr().Set(Vt.IntArray([0, 0]))
    pi.GetPositionsAttr().Set(Vt.Vec3fArray([Gf.Vec3f(0, 0, 0), Gf.Vec3f(1, 0, 0)]))
    pi.GetOrientationsAttr().Set(Vt.QuathArray([]))
    pi.GetScalesAttr().Set(Vt.Vec3fArray([]))

    default = Usd.TimeCode.Default()
    assert len(list(pi.ComputeInstanceTransformsAtTime(default, default))) == 2

    result = _real_run(mod, stage, "/World/scatter")

    assert result["success"] is True
    validation = result["context"]["validation"]
    assert validation["per_instance_arrays_match"] is True
    assert "positions_length_mismatch" not in validation["issue_codes"]
    assert validation["consistent"] is True
    assert validation["issue_codes"] == []
