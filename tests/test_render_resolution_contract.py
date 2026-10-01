"""Model effective Mantra resolution, not only successful parameter writes."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from test_render_camera_light_skills import _load_script


class _Parm:
    def __init__(self, node, name):
        self.node = node
        self.name = name

    def eval(self):
        return self.node.values[self.name]

    def set(self, value):
        if self.name not in self.node.ignored_writes:
            self.node.values[self.name] = value

    def menuItems(self):
        return ("1", "0.5", "specific") if self.name == "res_fraction" else ()

    def menuLabels(self):
        return ("Full resolution", "Half resolution", "User specified resolution")


class _Tuple:
    def __init__(self, node, names):
        self.node = node
        self.names = names

    def eval(self):
        return tuple(self.node.values[name] for name in self.names)

    def set(self, values):
        for name, value in zip(self.names, values):
            _Parm(self.node, name).set(value)


class _Node:
    def __init__(self, path, type_name, values, tuples=None):
        self.node_path = path
        self.type_name = type_name
        self.values = values
        self.tuples = tuples or {}
        self.ignored_writes = set()

    def path(self):
        return self.node_path

    def name(self):
        return self.node_path.rsplit("/", 1)[-1]

    def type(self):
        return SimpleNamespace(name=lambda: self.type_name)

    def parm(self, name):
        return _Parm(self, name) if name in self.values else None

    def parmTuple(self, name):
        names = self.tuples.get(name)
        if names is None and name in self.values:
            names = (name,)  # Real Houdini scalar controls also have ParmTuples.
        return _Tuple(self, names) if names and all(n in self.values for n in names) else None


def _scene():
    camera = _Node("/obj/cam1", "cam", {"resx": 960, "resy": 1200}, {"res": ("resx", "resy")})
    rop = _Node(
        "/out/mantra1",
        "ifd",
        {
            "camera": camera.path(),
            "override_camerares": 0,
            "res_fraction": "0.5",
            "res_overridex": 1200,
            "res_overridey": 1500,
        },
        {"res_override": ("res_overridex", "res_overridey")},
    )
    nodes = {node.path(): node for node in (rop, camera)}
    hou = SimpleNamespace(node=nodes.get, frame=lambda: 1.0)
    return hou, rop, camera


def test_mantra_request_enables_override_and_user_resolution_without_changing_camera():
    mod = _load_script("houdini-render", "set_render_settings.py")
    hou, rop, camera = _scene()
    with patch.dict(sys.modules, {"hou": hou}):
        result = mod.set_render_settings(rop.path(), resolution=[640, 800])
    assert result["success"] is True
    assert rop.values["override_camerares"] == 1
    assert rop.values["res_fraction"] == "specific"
    assert result["context"]["applied"]["resolution"] == [640, 800]
    assert result["context"]["readback"]["resolution"] == [640, 800]
    assert result["context"]["readback"]["resolution_source"] == "rop_override"
    assert result["context"]["unsupported"] == []
    assert camera.values == {"resx": 960, "resy": 1200}


@pytest.mark.parametrize("missing", ["override_camerares", "res_fraction", "res_overridex", "res_overridey"])
def test_mantra_missing_control_cannot_claim_resolution_applied(missing):
    mod = _load_script("houdini-render", "set_render_settings.py")
    hou, rop, _camera = _scene()
    del rop.values[missing]
    before = dict(rop.values)
    with patch.dict(sys.modules, {"hou": hou}):
        context = mod.set_render_settings(rop.path(), resolution=[640, 800])["context"]
    assert "resolution" not in context["applied"]
    assert "resolution" in context["unsupported"]
    assert rop.values == before


@pytest.mark.parametrize("ignored", ["override_camerares", "res_fraction", "res_overridex", "res_overridey"])
def test_mantra_ignored_write_cannot_claim_resolution_applied(ignored):
    mod = _load_script("houdini-render", "set_render_settings.py")
    hou, rop, _camera = _scene()
    rop.ignored_writes.add(ignored)
    with patch.dict(sys.modules, {"hou": hou}):
        context = mod.set_render_settings(rop.path(), resolution=[640, 800])["context"]
    assert "resolution" not in context["applied"]
    assert "resolution" in context["unsupported"]
    assert context["readback"]["resolution"] != [640, 800]


def test_generic_partial_resolution_is_unsupported_and_not_written():
    mod = _load_script("houdini-render", "set_render_settings.py")
    rop = _Node("/out/image1", "rop_image", {"setres": 0, "res1": 1024})
    hou = SimpleNamespace(node=lambda _path: rop)
    with patch.dict(sys.modules, {"hou": hou}):
        context = mod.set_render_settings(rop.path(), resolution=[640, 800])["context"]
    assert context["applied"] == {}
    assert context["unsupported"] == ["resolution"]
    assert rop.values == {"setres": 0, "res1": 1024}


@pytest.mark.parametrize("script", ["get_render_settings.py", "get_render_stats.py"])
@pytest.mark.parametrize(
    "override,scale,expected,source",
    [
        (0, "specific", [960, 1200], "camera"),
        (1, "0.5", [480, 600], "camera_scaled"),
        (1, "specific", [1200, 1500], "rop_override"),
    ],
)
def test_readers_report_current_effective_camera_or_override_resolution(script, override, scale, expected, source):
    mod = _load_script("houdini-render", script)
    hou, rop, _camera = _scene()
    rop.values.update(override_camerares=override, res_fraction=scale)
    with patch.dict(sys.modules, {"hou": hou}):
        result = (
            mod.get_render_settings(rop.path())
            if script == "get_render_settings.py"
            else mod.get_render_stats(rop.path())
        )
    assert result["success"] is True
    context = result["context"] if script == "get_render_settings.py" else result["context"]["stats"]
    assert context["resolution"] == expected
    assert context["resolution_source"] == source


def test_unknown_mantra_scale_reports_unresolved_instead_of_stale_override():
    mod = _load_script("houdini-render", "get_render_settings.py")
    hou, rop, _camera = _scene()
    rop.values.update(override_camerares=1, res_fraction="unknown_mode")
    with patch.dict(sys.modules, {"hou": hou}):
        context = mod.get_render_settings(rop.path())["context"]
    assert context["resolution"] is None
    assert context["resolution_unresolved"]


def test_fractional_pixels_are_unresolved_instead_of_guessing_renderer_rounding():
    mod = _load_script("houdini-render", "get_render_settings.py")
    hou, rop, camera = _scene()
    rop.values.update(override_camerares=1, res_fraction="0.5")
    camera.values["resx"] = 961
    with patch.dict(sys.modules, {"hou": hou}):
        context = mod.get_render_settings(rop.path())["context"]
    assert context["resolution"] is None
    assert context["resolution_unresolved"] == ["fractional_camera_resolution"]


def test_generic_tuple_resolution_and_clamping_are_read_back():
    mod = _load_script("houdini-render", "set_render_settings.py")
    rop = _Node("/out/image1", "rop_image", {"width": 1024, "height": 1024}, {"resolution": ("width", "height")})
    hou = SimpleNamespace(node=lambda _path: rop)
    with patch.dict(sys.modules, {"hou": hou}):
        context = mod.set_render_settings(rop.path(), resolution=[8192, 0])["context"]
    assert context["applied"]["resolution"] == [4096, 1]
    assert context["readback"]["resolution"] == [4096, 1]
    assert context["unsupported"] == []


def test_namespaced_mantra_uses_base_operator_controls():
    mod = _load_script("houdini-render", "set_render_settings.py")
    hou, rop, _camera = _scene()
    rop.type = lambda: SimpleNamespace(
        name=lambda: "studio::ifd::1.0", nameComponents=lambda: ("", "studio", "ifd", "1.0")
    )
    with patch.dict(sys.modules, {"hou": hou}):
        context = mod.set_render_settings(rop.path(), resolution=[640, 800])["context"]
    assert context["applied"]["resolution"] == [640, 800]
    assert context["readback"]["resolution_source"] == "rop_override"


def test_unknown_camera_inheriting_renderer_cannot_claim_inactive_override():
    setter = _load_script("houdini-render", "set_render_settings.py")
    getter = _load_script("houdini-render", "get_render_settings.py")
    hou, rop, _camera = _scene()
    rop.type_name = "other_camera_rop"
    before = dict(rop.values)
    with patch.dict(sys.modules, {"hou": hou}):
        context = setter.set_render_settings(rop.path(), resolution=[640, 800])["context"]
        settings = getter.get_render_settings(rop.path())["context"]
    assert context["unsupported"] == ["resolution"]
    assert context["applied"] == {}
    assert settings["resolution"] is None
    assert settings["resolution_unresolved"] == ["renderer_resolution_controls"]
    assert rop.values == before
