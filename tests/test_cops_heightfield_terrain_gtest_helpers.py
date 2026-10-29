"""Regression tests for the COPS heightfield terrain ground-test helpers.

These lock in the two correctness fixes from review: render artifacts must be
fresh (stale PNGs from an earlier run cannot count) and consecutive terrain
operator stages must be compared by a real signature before any change claim.
The module under test imports ``hou`` lazily, so these pure helpers run offline.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

_GTEST = Path(__file__).parents[1] / "examples" / "houdini" / "cops_heightfield_terrain_gtest.py"


def _load():
    spec = importlib.util.spec_from_file_location("cops_hf_gtest_helpers", _GTEST)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeParm(SimpleNamespace):
    def set(self, value):  # noqa: D401 - simple fake
        self.value = value


class FakeRop(SimpleNamespace):
    """Minimal rop_image double: ``render`` optionally writes bytes or fails."""

    def __init__(self, payload=None, fail=False):
        self._parms = {"copoutput": FakeParm(value=None)}
        self.payload = payload
        self.fail = fail
        self.render_calls = 0

    def parm(self, name):
        return self._parms.get(name)

    def render(self):
        self.render_calls += 1
        if self.fail:
            raise RuntimeError("render failed")
        if self.payload is not None:
            Path(self._parms["copoutput"].value).write_bytes(self.payload)


def test_render_branch_fresh_png_is_from_this_run(tmp_path):
    gtest = _load()
    stale = tmp_path / "view.png"
    stale.write_bytes(b"STALE-ARTIFACT-FROM-EARLIER-RUN")
    rop = FakeRop(payload=b"FRESH")
    result = gtest._render_branch(rop, str(tmp_path), "view.png")
    assert result["render_called"] is True
    assert result["fresh"] is True
    # The stale bytes were removed; only this run's payload remains.
    assert stale.read_bytes() == b"FRESH"
    assert result["png_bytes"] == len(b"FRESH")


def test_render_branch_failed_render_does_not_reuse_stale_png(tmp_path):
    gtest = _load()
    stale = tmp_path / "view.png"
    stale.write_bytes(b"STALE")
    rop = FakeRop(fail=True)
    result = gtest._render_branch(rop, str(tmp_path), "view.png")
    assert result["render_called"] is False
    assert result["png_exists"] is False
    assert result["fresh"] is False


def test_render_pass_requires_both_configured_branches(tmp_path):
    """Simulate render_pass with one branch missing -> must not pass."""
    gtest = _load()
    rop = FakeRop(payload=b"FRESH")
    renders = {"cops_heightfield_terrain_height.png": gtest._render_branch(rop, str(tmp_path), "h.png")}
    expected = {branch[4] for branch in gtest.BRANCHES}
    render_pass = set(renders) == expected and all(r.get("fresh") for r in renders.values())
    assert render_pass is False  # only one of two branches present


def test_stage_digest_detects_change_and_equality():
    gtest = _load()
    base = [0.1, 0.2, 0.3, 0.4]
    assert gtest._digest(base) == gtest._digest(list(base))
    assert gtest._digest(base) != gtest._digest([0.1, 0.2, 0.3, 0.9])
    assert gtest._digest([]) is None


def test_voxel_stats_report_real_coverage(tmp_path):
    gtest = _load()
    sample = [0.1, 0.2, 0.2, 0.5]
    stats = gtest._voxel_stats(sample, total_count=8)
    assert stats["count"] == 8
    assert stats["distinct"] == 3
    assert stats["min"] == 0.1 and stats["max"] == 0.5
