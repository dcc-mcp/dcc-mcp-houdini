"""Public domain tool contracts for the UDIM-aware texture-bake tools."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from domain_graph_fakes import scene
from skill_error_assertions import skill_error_detail
from skill_loader import skill_script_import_context

_ROOT = Path(__file__).parents[1] / "src" / "dcc_mcp_houdini" / "skills" / "houdini-texture-bake"
_UV_ROOT = Path(__file__).parents[1] / "src" / "dcc_mcp_houdini" / "skills" / "houdini-uv"


def _load(name, root=_ROOT):
    spec = importlib.util.spec_from_file_location("bakeudim_" + name[:-3], root / "scripts" / name)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    with skill_script_import_context(spec):
        spec.loader.exec_module(module)
    return module


def _attribute(name, size):
    """Minimal attribute double: check_uvs reads name, size and dataType."""
    return SimpleNamespace(
        name=lambda: name,
        size=lambda: size,
        dataType=lambda: "float",
    )


def _uv_geometry(values, prims=(object(),)):
    class Geometry(SimpleNamespace):
        def pointAttribs(self):
            return [_attribute("P", 3)]

        def vertexAttribs(self):
            return [_attribute("uv", 3)]

        def vertexFloatAttribValues(self, name):
            return list(values) if name == "uv" else []

        def pointFloatAttribValues(self, name):
            return []

        def iterPrims(self):
            return list(prims)

    return Geometry()


class _DisplayNode:
    def __init__(self, geometry):
        self._geometry = geometry
        self.needsToCook = lambda: False

    def geometry(self):
        return self._geometry


def _scene_with_attrib_data():
    """scene() plus the hou.attribData enum that check_uvs compares against."""
    root, geo, hou = scene()
    hou.attribData = SimpleNamespace(Float="float", Int="int", String="string")
    return root, geo, hou


def _bake_rop(root):
    """Pre-create a bake ROP: create_or_get_bake_rop reuses an existing node."""
    out = root.createNode("ropnet", "out")
    return out.createNode("baker", "bake_maps")


def _bake_target(root, name="character", values=(0.2, 0.3, 1.4, 0.5)):
    node = root.createNode("geo", name)
    display = _DisplayNode(_uv_geometry(values))
    node.displayNode = lambda: display
    return node, display


# ---------------------------------------------------------------------------
# list_bake_targets UDIM fields
# ---------------------------------------------------------------------------


def test_bake_geometry_info_reports_udim_tiles():
    root, _geo, hou = _scene_with_attrib_data()
    target, _display = _bake_target(root)
    common = _load("_texture_bake_common.py")
    with patch.dict(sys.modules, {"hou": hou}):
        info = common.bake_geometry_info(hou, target.path())
    assert info["uv_layers"] == ["uv"]
    assert info["udim_detection"] == "computed"
    assert info["udim_tiles"] == [1001, 1002]
    assert info["udim_tile_count"] == 2
    assert info["needs_udim_output"] is True


def test_bake_geometry_info_single_tile_does_not_need_udim_output():
    root, _geo, hou = _scene_with_attrib_data()
    target, _display = _bake_target(root, values=(0.2, 0.3, 0.4, 0.5))
    common = _load("_texture_bake_common.py")
    with patch.dict(sys.modules, {"hou": hou}):
        info = common.bake_geometry_info(hou, target.path())
    assert info["udim_tiles"] == [1001]
    assert info["needs_udim_output"] is False


def test_bake_geometry_info_without_uvs_reports_no_uv_sets():
    root, _geo, hou = _scene_with_attrib_data()
    node = root.createNode("geo", "plain")
    display = _DisplayNode(
        SimpleNamespace(
            pointAttribs=lambda: [_attribute("P", 3)],
            vertexAttribs=list,
            iterPrims=lambda: [object()],
        )
    )
    node.displayNode = lambda: display
    common = _load("_texture_bake_common.py")
    with patch.dict(sys.modules, {"hou": hou}):
        info = common.bake_geometry_info(hou, node.path())
    assert info["has_uvs"] is False
    assert info["udim_detection"] == "no_uv_sets"
    assert info["needs_udim_output"] is False


def test_udim_info_never_cooks_a_dirty_node():
    root, _geo, hou = scene()
    node = root.createNode("geo", "dirty")
    cooks = []

    class Dirty(SimpleNamespace):
        def needsToCook(self):
            return True

        def geometry(self):
            cooks.append(1)
            return _uv_geometry((0.2, 0.3))

    node.displayNode = lambda: Dirty()
    common = _load("_texture_bake_common.py")
    with patch.dict(sys.modules, {"hou": hou}):
        info = common.udim_info(hou, node.path())
    assert info["udim_detection"] == "unavailable"
    assert cooks == []


def test_texture_bake_and_uv_agree_on_tiles():
    """Both packages must compute the same tiles from the same UV values."""
    root, _geo, hou = _scene_with_attrib_data()
    common = _load("_texture_bake_common.py")
    uv_module = _load("inspect_uv.py", _UV_ROOT)
    values = (0.2, 0.3, 1.4, 0.5, 0.1, 2.2)

    # udim_info resolves displayNode(), inspect_uv reads the node itself, so give
    # each one a holder carrying identical geometry.
    target, _display = _bake_target(root, values=values)
    direct = root.createNode("geo", "direct")
    direct.geometry = lambda: _uv_geometry(values)

    with patch.dict(sys.modules, {"hou": hou}):
        bake_tiles = common.udim_info(hou, target.path())["udim_tiles"]
        uv_tiles = uv_module.inspect_uv(direct.path())["context"]["udim_tiles"]
    assert bake_tiles == uv_tiles == [1001, 1002, 1021]


# ---------------------------------------------------------------------------
# configure_udim_bake
# ---------------------------------------------------------------------------


def test_configure_udim_bake_inserts_token_for_multi_tile_target():
    root, _geo, hou = scene()
    _bake_rop(root)
    target, _display = _bake_target(root)
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("configure_udim_bake.py").configure_udim_bake(
            "/obj/out/bake_maps", target_path=target.path(), output_path="/tmp/hero.exr"
        )
    assert result["success"]
    context = result["context"]
    assert context["udim_tiles"] == [1001, 1002]
    assert context["needs_udim_output"] is True
    assert context["output_path"] == "/tmp/hero.%(UDIM)d.exr"
    assert context["output_paths"] == ["/tmp/hero.1001.exr", "/tmp/hero.1002.exr"]
    assert context["tile_source"] == "geometry"


def test_configure_udim_bake_keeps_flat_path_for_single_tile():
    root, _geo, hou = scene()
    _bake_rop(root)
    target, _display = _bake_target(root, values=(0.2, 0.3))
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("configure_udim_bake.py").configure_udim_bake(
            "/obj/out/bake_maps", target_path=target.path(), output_path="/tmp/hero.exr"
        )
    assert result["success"]
    assert result["context"]["udim_tiles"] == [1001]
    assert result["context"]["needs_udim_output"] is False
    assert result["context"]["output_path"] == "/tmp/hero.exr"


def test_configure_udim_bake_honours_explicit_tile_range():
    root, _geo, hou = scene()
    _bake_rop(root)
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("configure_udim_bake.py").configure_udim_bake(
            "/obj/out/bake_maps", tile_range=[1011, 1001], output_path="/tmp/hero.%(UDIM)d.exr"
        )
    assert result["success"]
    assert result["context"]["udim_tiles"] == [1001, 1011]
    assert result["context"]["tile_source"] == "tile_range"
    assert result["context"]["output_paths"] == ["/tmp/hero.1001.exr", "/tmp/hero.1011.exr"]


def test_configure_udim_bake_requires_tiles_or_target():
    root, _geo, hou = scene()
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("configure_udim_bake.py").configure_udim_bake("/out/bake_maps")
    assert not result["success"]
    assert "target_path or tile_range is required" in skill_error_detail(result)


def test_configure_udim_bake_fails_when_tiles_cannot_be_read():
    root, _geo, hou = scene()
    node = root.createNode("geo", "plain")
    node.displayNode = lambda: _DisplayNode(
        SimpleNamespace(
            pointAttribs=lambda: [_attribute("P", 3)],
            vertexAttribs=list,
            iterPrims=lambda: [object()],
        )
    )
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("configure_udim_bake.py").configure_udim_bake("/out/bake_maps", target_path=node.path())
    assert not result["success"]
    assert "No UDIM tiles resolved" in result["message"]


def test_configure_udim_bake_strict_on_caller_parameters():
    root, _geo, hou = scene()
    _bake_rop(root)
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("configure_udim_bake.py").configure_udim_bake(
            "/obj/out/bake_maps", tile_range=[1001], parameters={"nope": 1}
        )
    assert not result["success"]
    assert "nope" in skill_error_detail(result)


@pytest.mark.parametrize("tile_range", [["1001"], [1.5], [True]])
def test_configure_udim_bake_validates_tile_range(tile_range):
    root, _geo, hou = scene()
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("configure_udim_bake.py").configure_udim_bake("/out/bake_maps", tile_range=tile_range)
    assert not result["success"]
    assert "tile_range" in skill_error_detail(result)


# ---------------------------------------------------------------------------
# inspect_bake_output
# ---------------------------------------------------------------------------


def test_inspect_bake_output_expands_udim_token(tmp_path):
    root, _geo, hou = scene()
    for tile in (1001, 1002):
        (tmp_path / "hero.{}.exr".format(tile)).write_bytes(b"x")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("inspect_bake_output.py").inspect_bake_output(
            str(tmp_path / "hero.%(UDIM)d.exr"), expected_tiles=[1001, 1002]
        )
    assert result["success"]
    context = result["context"]
    assert context["artifact_exists"] is True
    assert context["artifact_count"] == 2
    assert context["missing_tiles"] == []
    assert context["all_tiles_present"] is True
    assert context["udim_token"] == "%(UDIM)d"


def test_inspect_bake_output_names_missing_tiles(tmp_path):
    root, _geo, hou = scene()
    (tmp_path / "hero.1001.exr").write_bytes(b"x")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("inspect_bake_output.py").inspect_bake_output(
            str(tmp_path / "hero.%(UDIM)d.exr"), expected_tiles=[1001, 1002]
        )
    assert result["success"]
    assert result["context"]["missing_tiles"] == [1002]
    assert result["context"]["all_tiles_present"] is False


def test_inspect_bake_output_handles_flat_path(tmp_path):
    root, _geo, hou = scene()
    (tmp_path / "hero.exr").write_bytes(b"abc")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("inspect_bake_output.py").inspect_bake_output(str(tmp_path / "hero.exr"))
    assert result["success"]
    assert result["context"]["artifact_exists"] is True
    assert result["context"]["udim_token"] == ""
    assert result["context"]["expected_tiles"] == []


def test_inspect_bake_output_reports_nothing_written(tmp_path):
    root, _geo, hou = scene()
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("inspect_bake_output.py").inspect_bake_output(
            str(tmp_path / "hero.%(UDIM)d.exr"), expected_tiles=[1001]
        )
    assert result["success"]
    assert result["context"]["artifact_exists"] is False
    assert result["context"]["missing_tiles"] == [1001]
    assert result["context"]["bake_verified"] is False


def test_inspect_bake_output_survives_unexpandable_path(tmp_path):
    root, _geo, hou = scene()
    (tmp_path / "hero.1001.exr").write_bytes(b"x")
    hou.expandString = lambda value: (_ for _ in ()).throw(RuntimeError("no expand"))
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("inspect_bake_output.py").inspect_bake_output(
            str(tmp_path / "hero.%(UDIM)d.exr"), expected_tiles=[1001]
        )
    assert result["success"]
    assert result["context"]["all_tiles_present"] is True


def test_inspect_bake_output_rejects_empty_path():
    root, _geo, hou = scene()
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("inspect_bake_output.py").inspect_bake_output("")
    assert not result["success"]


def test_hou_missing_returns_structured_error():
    root, _geo, _hou = scene()
    assert "hou" not in sys.modules
    result = _load("inspect_bake_output.py").inspect_bake_output("/tmp/hero.exr")
    assert not result["success"]
    assert result["message"] == "Houdini not available"


# ---------------------------------------------------------------------------
# Regressions from review: the guard must hold through the caller, not just in
# the helper, and a failed request must not leave a ROP it created behind.
# ---------------------------------------------------------------------------


class _CookTrackingDisplay:
    """Display node that records whether geometry() was reached."""

    def __init__(self, dirty=True):
        self.cooks = []
        self.needsToCook = lambda: dirty
        self._geometry = _uv_geometry((0.2, 0.3, 1.4, 0.5))

    def geometry(self):
        self.cooks.append(1)
        return self._geometry


def test_list_bake_targets_does_not_cook_a_dirty_node():
    """The guard has to survive the list_bake_targets caller, not just udim_info.

    bake_geometry_info used to read display.geometry() before delegating to
    udim_info, which cooked the node first and made the guard report `computed`
    for geometry that was never cooked.
    """
    root, _geo, hou = _scene_with_attrib_data()
    node = root.createNode("geo", "dirty")
    display = _CookTrackingDisplay(dirty=True)
    node.displayNode = lambda: display
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("list_bake_targets.py").list_bake_targets()
    target = next((item for item in result["context"]["targets"] if item["path"] == node.path()), None)
    assert target is not None, result["context"]["targets"]
    assert target["udim_detection"] == "unavailable"
    assert target["geometry_available"] is False
    assert target["primitive_count"] == 0
    assert target["bake_ready"] is False
    assert display.cooks == []


def test_bake_geometry_info_reads_clean_geometry_and_stays_bake_ready():
    root, _geo, hou = _scene_with_attrib_data()
    node = root.createNode("geo", "clean")
    display = _CookTrackingDisplay(dirty=False)
    node.displayNode = lambda: display
    common = _load("_texture_bake_common.py")
    with patch.dict(sys.modules, {"hou": hou}):
        info = common.bake_geometry_info(hou, node.path())
    assert info["geometry_available"] is True
    assert info["udim_detection"] == "computed"
    assert info["bake_ready"] is True
    # Clean geometry is read (several helpers need it); only dirty nodes are refused.
    assert display.cooks


def test_configure_udim_bake_destroys_the_rop_it_created_on_failure():
    root, _geo, hou = scene()
    out = root.createNode("ropnet", "out")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("configure_udim_bake.py").configure_udim_bake(
            "/obj/out/bake_maps", tile_range=[1001], parameters={"nope": 1}
        )
    assert not result["success"]
    assert out.children() == ()


def test_configure_udim_bake_preserves_a_pre_existing_rop_on_failure():
    root, _geo, hou = scene()
    out = root.createNode("ropnet", "out")
    existing = out.createNode("baker", "bake_maps")
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("configure_udim_bake.py").configure_udim_bake(
            "/obj/out/bake_maps", tile_range=[1001], parameters={"nope": 1}
        )
    assert not result["success"]
    assert out.children() == (existing,)
    assert existing.destroyed is False


def test_configure_udim_bake_leaves_nothing_when_tiles_cannot_resolve():
    """Tile resolution happens before the ROP is created, so nothing to clean up."""
    root, _geo, hou = scene()
    out = root.createNode("ropnet", "out")
    node = root.createNode("geo", "plain")
    node.displayNode = lambda: _DisplayNode(
        SimpleNamespace(
            pointAttribs=lambda: [_attribute("P", 3)],
            vertexAttribs=list,
            iterPrims=lambda: [object()],
        )
    )
    with patch.dict(sys.modules, {"hou": hou}):
        result = _load("configure_udim_bake.py").configure_udim_bake("/obj/out/bake_maps", target_path=node.path())
    assert not result["success"]
    assert out.children() == ()


# ---------------------------------------------------------------------------
# Regressions from review: shared UV helper semantics
# ---------------------------------------------------------------------------


def test_uv_attribute_names_prefers_vertex_over_point():
    """Houdini stores UVs as a vertex attribute; point must not win."""

    class Geometry(SimpleNamespace):
        def pointAttribs(self):
            return [_attribute("uv", 3)]

        def vertexAttribs(self):
            return [_attribute("uv", 3)]

        def vertexFloatAttribValues(self, name):
            return [0.2, 0.3, 1.4, 0.5] if name == "uv" else []

        def pointFloatAttribValues(self, name):
            return [0.2, 0.3] if name == "uv" else []

    from dcc_mcp_houdini._domain_graph import uv_values

    geometry = Geometry()
    names = uv_attribute_names_fn(geometry)
    assert names == ["uv"]
    # The vertex accessor is tried first, so the 4-component list wins.
    assert uv_values(geometry, "uv") == [0.2, 0.3, 1.4, 0.5]


def test_uv_attribute_names_anchors_the_name_match():
    """A substring test would accept Cd_uv or flowuv, which are not UV sets."""

    class Geometry(SimpleNamespace):
        def pointAttribs(self):
            return [_attribute("Cd_uv", 3), _attribute("flowuv", 3), _attribute("uv", 3)]

        def vertexAttribs(self):
            return []

    assert uv_attribute_names_fn(Geometry()) == ["uv"]


def uv_attribute_names_fn(geometry):
    from dcc_mcp_houdini._domain_graph import uv_attribute_names

    return uv_attribute_names(geometry)
