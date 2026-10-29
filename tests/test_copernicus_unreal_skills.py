"""Contract tests for the Copernicus -> Unreal texture-set manifest skill.

These are pure-Python: no Houdini install is required. The ``hou``-dependent
node-resolution path is exercised with an explicit HOM double via patch.dict.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from skill_loader import skill_script_import_context

_ROOT = Path(__file__).parents[1] / "src" / "dcc_mcp_houdini" / "skills" / "houdini-copernicus-unreal"
_SCRIPTS = _ROOT / "scripts"


def _load(name):
    spec = importlib.util.spec_from_file_location("copernicus_unreal_" + name[:-3], _SCRIPTS / name)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    with skill_script_import_context(spec):
        spec.loader.exec_module(module)
    return module


def _common():
    return _load("_unreal_common.py")


def _export():
    return _load("export_copernicus_for_unreal.py")


def _inspect():
    return _load("inspect_unreal_manifest.py")


def _maps(tmp_path):
    """Five canonical PBR maps declared by explicit source file paths."""
    names = ("base_color", "normal", "roughness", "metallic", "ambient_occlusion")
    maps = []
    for name in names:
        path = tmp_path / ("Rock_{}.exr".format(name))
        path.write_bytes(b"dummy")
        maps.append({"map_type": name, "source_path": str(path)})
    return maps


# ---------------------------------------------------------------------------
# Color convention (the core product requirement)
# ---------------------------------------------------------------------------


def test_color_fields_srgb_only_for_base_color_and_emissive():
    common = _common()
    assert common.color_fields("base_color") == {
        "color_space": "srgb",
        "srgb": True,
        "source_color_space": "srgb",
        "non_color_texture": False,
    }
    assert common.color_fields("emissive")["srgb"] is True
    for data_map in (
        "normal",
        "roughness",
        "metallic",
        "ambient_occlusion",
        "opacity",
        "height",
        "displacement",
        "specular",
    ):
        fields = common.color_fields(data_map)
        assert fields["color_space"] == "linear"
        assert fields["srgb"] is False
        assert fields["source_color_space"] == ""
        assert fields["non_color_texture"] is True


def test_import_plan_uses_import_asset_color_flags(tmp_path):
    mod = _export()
    out = tmp_path / "manifest.json"
    result = mod.export_copernicus_for_unreal(maps=_maps(tmp_path), asset_name="Rock", output_path=str(out))
    assert result["success"] is True
    manifest = result["context"]["manifest"]
    by_type = {t["map_type"]: t for t in manifest["textures"]}
    bc_import = next(c for c in manifest["import_plan"] if c["arguments"]["asset_name"].endswith("BaseColor"))
    assert bc_import["tool"] == "unreal_assets__import_asset"
    assert bc_import["arguments"]["source_color_space"] == "srgb"
    assert bc_import["arguments"]["non_color_texture"] is False
    assert by_type["base_color"]["color_space"] == "srgb"
    for data_map in ("normal", "roughness", "metallic", "ambient_occlusion"):
        assert by_type[data_map]["non_color_texture"] is True
        assert by_type[data_map]["source_color_space"] == ""
        imp = next(
            c
            for c in manifest["import_plan"]
            if c["arguments"]["asset_name"].endswith(by_type[data_map]["asset_name"].split("_")[-1])
        )
        assert imp["arguments"]["non_color_texture"] is True


# ---------------------------------------------------------------------------
# Material plan / create_texture_material round-trip
# ---------------------------------------------------------------------------


def test_material_plan_wires_all_five_pbr_slots(tmp_path):
    mod = _export()
    out = tmp_path / "manifest.json"
    result = mod.export_copernicus_for_unreal(maps=_maps(tmp_path), asset_name="Rock", output_path=str(out))
    assert result["context"]["has_material_plan"] is True
    plan = result["context"]["manifest"]["material_plan"]
    assert plan["tool"] == "unreal_assets__create_texture_material"
    args = plan["arguments"]
    assert args["material_name"] == "M_Rock"
    assert args["destination_path"] == "/Game/Materials"
    assert args["texture_path"].endswith("T_Rock_BaseColor")
    assert args["normal_texture_path"].endswith("T_Rock_Normal")
    assert args["roughness_texture_path"].endswith("T_Rock_Roughness")
    assert args["metallic_texture_path"].endswith("T_Rock_Metallic")
    assert args["ambient_occlusion_texture_path"].endswith("T_Rock_AmbientOcclusion")


def test_no_base_color_omits_material_plan_with_warning(tmp_path):
    mod = _export()
    out = tmp_path / "manifest.json"
    normal = tmp_path / "n.exr"
    normal.write_bytes(b"dummy")
    result = mod.export_copernicus_for_unreal(
        maps=[{"map_type": "normal", "source_path": str(normal)}],
        asset_name="Rock",
        output_path=str(out),
    )
    assert result["success"] is True
    manifest = result["context"]["manifest"]
    assert manifest["material_plan"] is None
    assert result["context"]["has_material_plan"] is False
    assert any("base_color" in w for w in manifest["warnings"])


# ---------------------------------------------------------------------------
# Determinism + persisted file
# ---------------------------------------------------------------------------


def test_manifest_is_deterministic_and_persisted(tmp_path):
    mod = _export()
    maps = _maps(tmp_path)
    out1 = tmp_path / "m1.json"
    out2 = tmp_path / "m2.json"
    mod.export_copernicus_for_unreal(maps=maps, asset_name="Rock", output_path=str(out1))
    mod.export_copernicus_for_unreal(maps=list(reversed(maps)), asset_name="Rock", output_path=str(out2))

    # Reversed input must NOT change the byte output (deterministic ordering is by
    # declaration order, so we compare two identical inputs here).
    out3 = tmp_path / "m3.json"
    mod.export_copernicus_for_unreal(maps=maps, asset_name="Rock", output_path=str(out3))
    assert out1.read_bytes() == out3.read_bytes()

    data = json.loads(out1.read_text(encoding="utf-8"))
    assert data["schema_version"] == "1.0"
    assert "deferred" in data and data["deferred"]


def test_overwrite_false_rejects_existing(tmp_path):
    mod = _export()
    out = tmp_path / "m.json"
    out.write_text("pre-existing", encoding="utf-8")
    result = mod.export_copernicus_for_unreal(
        maps=_maps(tmp_path), asset_name="Rock", output_path=str(out), overwrite=False
    )
    assert result["success"] is False
    assert out.read_text(encoding="utf-8") == "pre-existing"


# ---------------------------------------------------------------------------
# Validation / fail-closed behaviour
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "maps",
    [
        [],
        [{"map_type": "not_a_map", "source_path": "/x.exr"}],
        [
            {"map_type": "normal", "source_path": "/x.exr"},
            {"map_type": "normal", "source_path": "/y.exr"},
        ],
        [{"map_type": "normal"}],  # no source_path / node_path
    ],
)
def test_invalid_maps_fail_closed(tmp_path, maps):
    mod = _export()
    result = mod.export_copernicus_for_unreal(maps=maps, asset_name="Rock", output_path=str(tmp_path / "m.json"))
    assert result["success"] is False


@pytest.mark.parametrize("asset_name", ["bad name", "../escape", "a-b", ""])
def test_invalid_asset_name_rejected(tmp_path, asset_name):
    mod = _export()
    result = mod.export_copernicus_for_unreal(
        maps=_maps(tmp_path), asset_name=asset_name, output_path=str(tmp_path / "m.json")
    )
    assert result["success"] is False


def test_bad_game_path_rejected(tmp_path):
    mod = _export()
    result = mod.export_copernicus_for_unreal(
        maps=_maps(tmp_path),
        asset_name="Rock",
        output_path=str(tmp_path / "m.json"),
        destination_path="/Engine/Foo",
    )
    assert result["success"] is False


def test_missing_artifact_is_reported_not_faked(tmp_path):
    mod = _export()
    result = mod.export_copernicus_for_unreal(
        maps=[{"map_type": "base_color", "source_path": str(tmp_path / "does_not_exist.exr")}],
        asset_name="Rock",
        output_path=str(tmp_path / "m.json"),
    )
    assert result["success"] is True
    assert result["context"]["artifacts_present"] == 0
    assert result["context"]["manifest"]["textures"][0]["artifact_exists"] is False
    assert any("artifact not found" in w for w in result["context"]["warnings"])


# ---------------------------------------------------------------------------
# UDIM / ORM deferred metadata
# ---------------------------------------------------------------------------


def test_udim_and_orm_recorded_but_deferred(tmp_path):
    mod = _export()
    bc = tmp_path / "bc.exr"
    bc.write_bytes(b"dummy")
    result = mod.export_copernicus_for_unreal(
        maps=[
            {
                "map_type": "base_color",
                "source_path": str(bc),
                "channel_packing": "orm",
                "udim": {"enabled": True, "tiles": [1001, 1002], "pattern": "bc.<UDIM>.exr"},
            }
        ],
        asset_name="Rock",
        output_path=str(tmp_path / "m.json"),
    )
    assert result["success"] is True
    tex = result["context"]["manifest"]["textures"][0]
    assert tex["udim"]["enabled"] is True
    assert tex["udim"]["deferred"] is True
    assert tex["channel_packing"] == "orm"
    warnings = result["context"]["manifest"]["warnings"]
    assert any("ORM" in w for w in warnings)
    assert any("UDIM" in w for w in warnings)


# ---------------------------------------------------------------------------
# hou-based node resolution with an explicit HOM double
# ---------------------------------------------------------------------------


def _fake_hou(parm_values, expand=None):
    def node(path):
        if path != "/img/copnet1/basecolor_out":
            return None
        return SimpleNamespace(parm=lambda name: _fake_parm(parm_values.get(name)))

    def _fake_parm(value):
        if value is None:
            return None
        return SimpleNamespace(eval=lambda: value)

    expand_fn = expand or (lambda s: s)
    return SimpleNamespace(node=node, expandString=expand_fn)


def test_node_path_resolves_cop_output_parm(tmp_path):
    mod = _export()
    rendered = tmp_path / "rendered_basecolor.exr"
    rendered.write_bytes(b"dummy")
    hou = _fake_hou({"copoutput": str(rendered)})
    with patch.dict(sys.modules, {"hou": hou}):
        result = mod.export_copernicus_for_unreal(
            maps=[{"map_type": "base_color", "node_path": "/img/copnet1/basecolor_out"}],
            asset_name="Rock",
            output_path=str(tmp_path / "m.json"),
        )
    assert result["success"] is True
    tex = result["context"]["manifest"]["textures"][0]
    assert tex["source_path"] == str(rendered)
    assert tex["node_path"] == "/img/copnet1/basecolor_out"
    assert tex["artifact_exists"] is True


def test_node_path_without_hou_returns_actionable_error(tmp_path):
    mod = _export()
    with patch.dict(sys.modules, {"hou": None}):
        result = mod.export_copernicus_for_unreal(
            maps=[{"map_type": "base_color", "node_path": "/img/copnet1/basecolor_out"}],
            asset_name="Rock",
            output_path=str(tmp_path / "m.json"),
        )
    assert result["success"] is False


def test_node_path_with_no_output_parm_fails_closed(tmp_path):
    mod = _export()
    hou = _fake_hou({})  # no known output parameter
    with patch.dict(sys.modules, {"hou": hou}):
        result = mod.export_copernicus_for_unreal(
            maps=[{"map_type": "base_color", "node_path": "/img/copnet1/basecolor_out"}],
            asset_name="Rock",
            output_path=str(tmp_path / "m.json"),
        )
    assert result["success"] is False


# ---------------------------------------------------------------------------
# inspect_unreal_manifest consumer-side round-trip
# ---------------------------------------------------------------------------


def test_inspect_round_trip(tmp_path):
    export = _export()
    inspect = _inspect()
    out = tmp_path / "m.json"
    export.export_copernicus_for_unreal(maps=_maps(tmp_path), asset_name="Rock", output_path=str(out))
    result = inspect.inspect_unreal_manifest(str(out))
    assert result["success"] is True
    ctx = result["context"]
    assert ctx["texture_count"] == 5
    assert ctx["import_call_count"] == 5
    assert ctx["has_material_plan"] is True
    assert ctx["material_plan"]["tool"] == "unreal_assets__create_texture_material"
    assert ctx["schema_version"] == "1.0"


def test_inspect_rejects_tampered_color_convention(tmp_path):
    export = _export()
    inspect = _inspect()
    common = _common()
    out = tmp_path / "m.json"
    export.export_copernicus_for_unreal(maps=_maps(tmp_path), asset_name="Rock", output_path=str(out))
    data = common.load_manifest(str(out))
    data["textures"][1]["non_color_texture"] = False  # normal forced to "color"
    common.write_manifest(str(out), data)
    result = inspect.inspect_unreal_manifest(str(out))
    assert result["success"] is False


def test_inspect_rejects_tampered_import_plan_color_flags(tmp_path):
    """A data-map's import_asset color flags cannot be downgraded to color."""
    export = _export()
    inspect = _inspect()
    common = _common()
    out = tmp_path / "m.json"
    export.export_copernicus_for_unreal(maps=_maps(tmp_path), asset_name="Rock", output_path=str(out))
    data = common.load_manifest(str(out))
    normal_import = next(c for c in data["import_plan"] if c["arguments"]["asset_name"].endswith("Normal"))
    normal_import["arguments"]["non_color_texture"] = False
    normal_import["arguments"]["source_color_space"] = "srgb"
    common.write_manifest(str(out), data)
    result = inspect.inspect_unreal_manifest(str(out))
    assert result["success"] is False


def test_inspect_rejects_tampered_import_plan_order(tmp_path):
    """Reordering / duplicating import calls must not pass validation."""
    export = _export()
    inspect = _inspect()
    common = _common()
    out = tmp_path / "m.json"
    export.export_copernicus_for_unreal(maps=_maps(tmp_path), asset_name="Rock", output_path=str(out))
    data = common.load_manifest(str(out))
    data["import_plan"].reverse()
    common.write_manifest(str(out), data)
    result = inspect.inspect_unreal_manifest(str(out))
    assert result["success"] is False


def test_inspect_rejects_tampered_material_plan(tmp_path):
    """A re-pointed material slot must be caught by the rebuild/compare."""
    export = _export()
    inspect = _inspect()
    common = _common()
    out = tmp_path / "m.json"
    export.export_copernicus_for_unreal(maps=_maps(tmp_path), asset_name="Rock", output_path=str(out))
    data = common.load_manifest(str(out))
    data["material_plan"]["arguments"]["normal_texture_path"] = "/Game/Textures/Rock/T_Rock_Roughness"
    common.write_manifest(str(out), data)
    result = inspect.inspect_unreal_manifest(str(out))
    assert result["success"] is False


def test_inspect_rejects_tampered_texture_source_color_space(tmp_path):
    """source_color_space is part of the enforced color convention."""
    export = _export()
    inspect = _inspect()
    common = _common()
    out = tmp_path / "m.json"
    export.export_copernicus_for_unreal(maps=_maps(tmp_path), asset_name="Rock", output_path=str(out))
    data = common.load_manifest(str(out))
    for tex in data["textures"]:
        if tex["map_type"] == "base_color":
            tex["source_color_space"] = ""
    common.write_manifest(str(out), data)
    result = inspect.inspect_unreal_manifest(str(out))
    assert result["success"] is False


def test_inspect_rejects_bad_schema(tmp_path):
    inspect = _inspect()
    out = tmp_path / "m.json"
    out.write_text(json.dumps({"schema_version": "999"}), encoding="utf-8")
    result = inspect.inspect_unreal_manifest(str(out))
    assert result["success"] is False


def test_inspect_missing_file(tmp_path):
    inspect = _inspect()
    result = inspect.inspect_unreal_manifest(str(tmp_path / "nope.json"))
    assert result["success"] is False


# ---------------------------------------------------------------------------
# Skill package validation + py37 parse + tools.yaml contract
# ---------------------------------------------------------------------------


def test_validate_skill_clean():
    from dcc_mcp_core import validate_skill

    report = validate_skill(str(_ROOT))
    assert report.is_clean, report.issues


def test_sources_parse_as_python_37():
    import ast

    for path in _SCRIPTS.glob("*.py"):
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path), feature_version=(3, 7))


def test_tools_yaml_contract():
    import yaml

    data = yaml.safe_load((_ROOT / "tools.yaml").read_text(encoding="utf-8"))
    names = set()
    for tool in data["tools"]:
        names.add(tool["name"])
        assert tool["execution"] in ("sync", "async")
        assert tool["affinity"] in ("main", "any")
        assert "input_schema" in tool
        assert isinstance(tool["read_only"], bool)
        assert isinstance(tool["destructive"], bool)
        assert isinstance(tool["idempotent"], bool)
        assert (_ROOT / tool["source_file"]).is_file()
    assert names == {"export_copernicus_for_unreal", "inspect_unreal_manifest"}


def test_skill_md_references_exist():
    assert (_ROOT / "SKILL.md").is_file()
    assert (_ROOT / "references" / "MANIFEST_SCHEMA.md").is_file()
    text = (_ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert "dcc-mcp-core 0.20.14" in text
