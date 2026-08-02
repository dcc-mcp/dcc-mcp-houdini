"""Unit coverage for Houdini 21 Karma render setting names."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from skill_loader import skill_script_import_context

SCRIPT = (
    Path(__file__).parent.parent
    / "src"
    / "dcc_mcp_houdini"
    / "skills"
    / "houdini-karma"
    / "scripts"
    / "configure_karma.py"
)


def _load_script():
    spec = importlib.util.spec_from_file_location("karma_configure_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    with skill_script_import_context(spec):
        spec.loader.exec_module(module)
    return module


class _Parm:
    def __init__(self, node, name: str) -> None:
        self.node = node
        self.name = name

    def set(self, value) -> None:
        self.node.values[self.name] = value


class _KarmaNode:
    def __init__(self) -> None:
        self.values = {
            "engine": "cpu",
            "pathtracedsamples": 128,
            "samplesperpixel": 9,
            "varianceaa_maxsamples": 256,
            "varianceaa_thresh": 0.01,
            "denoiser": "off",
        }

    def parm(self, name: str):
        return _Parm(self, name) if name in self.values else None

    def parmTuple(self, _name: str):
        return None

    def path(self) -> str:
        return "/stage/karma_settings"

    def name(self) -> str:
        return "karma_settings"

    def type(self):
        return type("NodeType", (), {"name": lambda _self: "karmarendersettings"})()


@pytest.mark.parametrize(
    ("device", "samples", "denoise", "expected"),
    [
        (
            "cpu",
            {"max_samples": 64, "pixel_samples": 8},
            True,
            {
                "engine": "cpu",
                "pathtracedsamples": 128,
                "samplesperpixel": 8,
                "varianceaa_maxsamples": 64,
                "varianceaa_thresh": 0.005,
                "denoiser": "oidn",
            },
        ),
        (
            "xpu",
            {"pixel_samples": 96},
            False,
            {
                "engine": "xpu",
                "pathtracedsamples": 96,
                "samplesperpixel": 9,
                "varianceaa_maxsamples": 256,
                "varianceaa_thresh": 0.005,
                "denoiser": "off",
            },
        ),
    ],
)
def test_configure_karma_uses_houdini21_parameters(device, samples, denoise: bool, expected) -> None:
    configure = _load_script()
    node = _KarmaNode()
    hou = type("Hou", (), {"node": lambda _self, _path: node})()

    with patch.dict(sys.modules, {"hou": hou}):
        result = configure.configure_karma(
            "/stage/karma_settings",
            device=device,
            noise_threshold=0.005,
            denoise=denoise,
            **samples,
        )

    assert result["success"] is True
    assert node.values == expected


def test_configure_karma_rejects_conflicting_xpu_samples() -> None:
    configure = _load_script()
    node = _KarmaNode()
    before = dict(node.values)
    hou = type("Hou", (), {"node": lambda _self, _path: node})()

    with patch.dict(sys.modules, {"hou": hou}):
        result = configure.configure_karma("/stage/karma_settings", device="xpu", max_samples=64, pixel_samples=8)

    assert result["success"] is False
    assert node.values == before


def test_configure_karma_keeps_legacy_boolean_denoise_fallback() -> None:
    configure = _load_script()
    node = _KarmaNode()
    node.values = {"renderengine": "cpu", "denoise": 0}
    hou = type("Hou", (), {"node": lambda _self, _path: node})()

    with patch.dict(sys.modules, {"hou": hou}):
        result = configure.configure_karma("/stage/karma_settings", device="xpu", denoise=True)

    assert result["success"] is True
    assert node.values == {"renderengine": "xpu", "denoise": 1}
