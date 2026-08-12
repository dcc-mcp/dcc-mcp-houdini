"""Skill package validation and script unit tests (no live Houdini required)."""

from __future__ import annotations

import importlib.util
import sys
from contextlib import ExitStack
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, call, patch

import pytest
import yaml
from skill_loader import skill_script_import_context

_SKILLS_ROOT = Path(__file__).parent.parent / "src" / "dcc_mcp_houdini" / "skills"
_SKILL_DIRS = tuple(sorted(d.name for d in _SKILLS_ROOT.iterdir() if (d / "SKILL.md").is_file()))


def _load_script(skill_name: str, script_name: str) -> ModuleType:
    path = _SKILLS_ROOT / skill_name / "scripts" / script_name
    spec = importlib.util.spec_from_file_location(f"skill_{path.stem}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    with skill_script_import_context(spec):
        spec.loader.exec_module(module)
    return module


def _mock_inspection_node(category_name: str, path: str, type_name: str, *methods: str) -> MagicMock:
    category = MagicMock()
    category.name.return_value = category_name
    type_obj = MagicMock()
    type_obj.name.return_value = type_name
    type_obj.category.return_value = category
    node = MagicMock(spec=["children", "name", "parent", "path", "type", *methods])
    node.path.return_value = path
    node.name.return_value = path.rsplit("/", 1)[-1]
    node.type.return_value = type_obj
    node.parent.return_value = None
    node.children.return_value = []
    return node


@pytest.mark.parametrize("skill_dir", _SKILL_DIRS)
def test_validate_skill_clean(skill_dir: str) -> None:
    from dcc_mcp_core import validate_skill

    report = validate_skill(str(_SKILLS_ROOT / skill_dir))
    assert report.is_clean, report.issues


@pytest.mark.parametrize("skill_dir", _SKILL_DIRS)
def test_tools_yaml_contract(skill_dir: str) -> None:
    tools_path = _SKILLS_ROOT / skill_dir / "tools.yaml"
    data = yaml.safe_load(tools_path.read_text(encoding="utf-8"))
    for tool in data["tools"]:
        assert tool.get("execution") in ("sync", "async")
        assert tool.get("affinity") in ("main", "any")
        assert "input_schema" in tool
        assert isinstance(tool.get("read_only"), bool)
        assert isinstance(tool.get("destructive"), bool)
        assert isinstance(tool.get("idempotent"), bool)
        assert (tools_path.parent / tool["source_file"]).is_file()
        if tool["execution"] == "async":
            assert tool.get("timeout_hint_secs"), f"{tool['name']} missing timeout_hint_secs"


def test_flipbook_job_tools_have_dedicated_entrypoints() -> None:
    tools_path = _SKILLS_ROOT / "houdini-render" / "tools.yaml"
    tools = yaml.safe_load(tools_path.read_text(encoding="utf-8"))["tools"]
    sources = {tool["name"]: tool["source_file"] for tool in tools}

    assert sources["get_flipbook_job"] == "scripts/get_flipbook_job.py"
    assert sources["cancel_flipbook_job"] == "scripts/cancel_flipbook_job.py"


def test_flipbook_poll_transition_survives_loader_and_discovery() -> None:
    import dcc_mcp_core

    skill_dir = _SKILLS_ROOT / "houdini-render"
    manifest_tools = yaml.safe_load((skill_dir / "tools.yaml").read_text(encoding="utf-8"))["tools"]
    manifest_flipbook = next(tool for tool in manifest_tools if tool["name"] == "flipbook")
    expected = ["houdini_render__get_flipbook_job"]
    assert manifest_flipbook["next-tools"]["on-success"] == expected

    parsed = dcc_mcp_core.parse_skill_md(str(skill_dir))
    assert parsed is not None
    parsed_flipbook = next(tool for tool in parsed.tools if tool.name == "flipbook")
    assert parsed_flipbook.next_tools == {"on_success": expected, "on_failure": []}

    registry = dcc_mcp_core.ToolRegistry()
    catalog = dcc_mcp_core.SkillCatalog(registry)
    catalog.set_in_process_executor(lambda _script_path, _params, **_metadata: {"success": True})
    assert catalog.discover(extra_paths=[str(_SKILLS_ROOT)], dcc_name="houdini") >= 1
    assert any(skill.name == "houdini-render" for skill in catalog.search_skills(query="flipbook"))
    registered = catalog.load_skill("houdini-render")
    assert "houdini_render__flipbook" in registered
    assert "houdini_render__get_flipbook_job" in registered

    discovered = catalog.get_skill("houdini-render")
    assert discovered is not None
    discovered_flipbook = next(tool for tool in discovered.tools if tool.name == "flipbook")
    assert discovered_flipbook.next_tools == {"on_success": expected, "on_failure": []}


@pytest.mark.parametrize(
    ("skill_name", "tool_name"),
    (
        ("houdini-render", "render_rop"),
        ("houdini-animation", "cache_simulation"),
        ("houdini-hda-automation", "execute_rop_chain"),
    ),
)
def test_self_managed_rop_tools_return_adapter_job_identity_directly(
    skill_name: str,
    tool_name: str,
) -> None:
    tools_path = _SKILLS_ROOT / skill_name / "tools.yaml"
    tools = yaml.safe_load(tools_path.read_text(encoding="utf-8"))["tools"]
    tool = next(tool for tool in tools if tool["name"] == tool_name)

    assert tool["execution"] == "sync"
    assert "timeout_hint_secs" not in tool


def test_cache_simulation_job_is_pollable_via_public_render_status(tmp_path: Path) -> None:
    import uuid

    from dcc_mcp_houdini import _isolated_jobs, _rop_jobs

    cache = _load_script("houdini-animation", "cache_simulation.py")
    render_status = _load_script("houdini-render", "get_render_job.py")

    hip_path = tmp_path / "scene.hip"
    hip_path.write_bytes(b"hip")
    houdini_executable = tmp_path / ("houdini.exe" if _rop_jobs.os.name == "nt" else "houdini")
    hython_executable = tmp_path / ("hython.exe" if _rop_jobs.os.name == "nt" else "hython")
    hython_executable.write_bytes(b"exe")

    output = tmp_path / "cache.$F4.bgeo.sc"
    file_parm = MagicMock()
    file_parm.eval.return_value = str(output)
    file_parm.unexpandedString.return_value = str(output)
    rop = MagicMock()
    rop.path.return_value = "/out/filecache1"
    rop.parm.side_effect = lambda name: file_parm if name == "file" else None

    mock_hou = MagicMock()
    mock_hou.node.return_value = rop
    mock_hou.isUIAvailable.return_value = True
    mock_hou.hipFile.path.return_value = str(hip_path)
    mock_hou.hipFile.hasUnsavedChanges.return_value = False

    process = MagicMock(pid=4321)
    process.poll.return_value = None
    compact_id = None
    try:
        with patch.dict(sys.modules, {"hou": mock_hou}), patch.object(
            _rop_jobs.sys, "executable", str(houdini_executable)
        ), patch.object(_isolated_jobs.tempfile, "gettempdir", return_value=str(tmp_path)), patch.object(
            _isolated_jobs.subprocess, "Popen", return_value=process
        ):
            launched = cache.cache_simulation("/out/filecache1", frame_range=[1, 3, 1])
            assert launched["success"] is True
            compact_id = launched["context"]["job_id"]
            dashed_id = str(uuid.UUID(hex=compact_id))

            compact_status = render_status.get_render_job(compact_id)
            dashed_status = render_status.get_render_job(dashed_id)
    finally:
        if compact_id is not None:
            _isolated_jobs._PROCESS_HANDLES.pop(compact_id, None)

    assert compact_status["success"] is True
    assert dashed_status["success"] is True
    assert compact_status["context"]["job_id"] == compact_id
    assert dashed_status["context"]["job_id"] == compact_id
    assert compact_status["context"]["state"] == "queued"
    assert dashed_status["context"]["state"] == "queued"


def test_skills_index_exists() -> None:
    index = _SKILLS_ROOT / "SKILLS_INDEX.md"
    assert index.is_file()
    text = index.read_text(encoding="utf-8")
    for skill in _SKILL_DIRS:
        assert skill in text


def test_stage_loader_maps_bootstrap_and_scene() -> None:
    from dcc_mcp_houdini._skill_loader import build_minimal_mode_for_stages, skills_for_stage

    assert "houdini-scripting" in skills_for_stage("bootstrap")
    assert "houdini-scene" in skills_for_stage("scene")
    assert "houdini-materials" in skills_for_stage("authoring")
    assert "houdini-groom" in skills_for_stage("authoring")
    cfg = build_minimal_mode_for_stages(["scene"])
    assert "houdini-scene" in cfg.skills
    assert "houdini-scripting" in cfg.skills
    scene_tools = yaml.safe_load((_SKILLS_ROOT / "houdini-scene" / "tools.yaml").read_text(encoding="utf-8"))["tools"]
    inspect = next(tool for tool in scene_tools if tool["name"] == "inspect_selection")
    assert inspect["input_schema"]["additionalProperties"] is False


class TestGsplatRelightingSkills:
    def test_find_node_type_accepts_houdini_versioned_labs_name(self) -> None:
        mod = _load_script("houdini-gsplat-relighting", "gsplat_relighting.py")
        parent = MagicMock()
        parent.childTypeCategory.return_value.nodeTypes.return_value = {"labs::normals_from_gsplats::1.0": MagicMock()}

        result = mod._find_node_type(parent, ("labs::normals_from_gsplats",))

        assert result == "labs::normals_from_gsplats::1.0"

    def test_find_node_type_accepts_houdini_22_copernicus_name(self) -> None:
        mod = _load_script("houdini-gsplat-relighting", "gsplat_relighting.py")
        parent = MagicMock()
        parent.childTypeCategory.return_value.nodeTypes.return_value = {"rasterizegsplats": MagicMock()}

        result = mod._find_node_type(parent, ("rasterizegsplats", "rasterize_gsplats"))

        assert result == "rasterizegsplats"

    def test_menu_value_maps_label_to_houdini_token(self) -> None:
        mod = _load_script("houdini-gsplat-relighting", "gsplat_relighting.py")
        parm = MagicMock()
        parm.parmTemplate.return_value.menuItems.return_value = ["point", "UsdLuxDistantLight"]
        parm.parmTemplate.return_value.menuLabels.return_value = ["Point", "Distant"]

        assert mod._menu_value(parm, "Distant") == "UsdLuxDistantLight"

    def test_inspect_reports_relighting_contract(self) -> None:
        mod = _load_script("houdini-gsplat-relighting", "gsplat_relighting.py")
        attrs = []
        for name in ("P", "Cd", "orient", "pscale", "GS_Alpha", "GS_SPH_R", "GS_SPH_G", "GS_SPH_B"):
            attrib = MagicMock()
            attrib.name.return_value = name
            attrib.dataType.return_value.name.return_value = "Float"
            attrib.size.return_value = 3
            attrs.append(attrib)
        geometry = MagicMock()
        geometry.pointAttribs.return_value = attrs
        geometry.pointCount.return_value = 12
        geometry.primCount.return_value = 0
        node = MagicMock()
        node.path.return_value = "/obj/geo1/OUT"
        node.name.return_value = "OUT"
        node.type.return_value.name.return_value = "null"
        node.geometry.return_value = geometry
        with patch.dict(sys.modules, {"hou": MagicMock(node=lambda _path: node)}):
            result = mod.inspect_gsplat_relighting_input(node_path="/obj/geo1/OUT")

        assert result["success"] is True
        assert result["context"]["ready_for_relighting"] is True
        assert result["context"]["checks"]["spherical_harmonics"] is True

    def test_public_showcase_rejects_synthetic_point_sampling(self) -> None:
        mod = _load_script("houdini-gsplat-relighting", "gsplat_relighting.py")
        attrs = []
        for name in ("P", "Cd", "orient", "pscale", "GS_Alpha"):
            attrib = MagicMock()
            attrib.name.return_value = name
            attrib.dataType.return_value.name.return_value = "Float"
            attrib.size.return_value = 3
            attrs.append(attrib)
        geometry = MagicMock()
        geometry.pointAttribs.return_value = attrs
        geometry.pointCount.return_value = 100
        geometry.primCount.return_value = 0
        node = MagicMock()
        node.path.return_value = "/obj/geo1/OUT"
        node.name.return_value = "OUT"
        node.type.return_value.name.return_value = "null"
        node.geometry.return_value = geometry
        with patch.dict(sys.modules, {"hou": MagicMock(node=lambda _path: node)}):
            result = mod.inspect_gsplat_relighting_input(
                node_path="/obj/geo1/OUT",
                provenance_type="synthetic",
                public_showcase=True,
            )

        assert result["context"]["ready_for_relighting"] is False
        assert result["context"]["provenance"]["public_showcase_pass"] is False
        assert "captured_gsplat_provenance" in result["context"]["blocking_missing"]

    def test_prepare_rolls_back_when_labs_node_is_missing(self) -> None:
        mod = _load_script("houdini-gsplat-relighting", "gsplat_relighting.py")
        source = MagicMock()
        source.path.return_value = "/obj/geo1/OUT"
        source.parent.return_value = MagicMock(childTypeCategory=lambda: MagicMock(nodeTypes=dict))
        hou = MagicMock(node=lambda _path: source)
        with patch.dict(sys.modules, {"hou": hou}):
            result = mod.prepare_gsplat_sop_chain(node_path="/obj/geo1/OUT")

        assert result["success"] is False
        source.parent.return_value.createNode.assert_not_called()

    def test_copernicus_raster_uses_houdini_22_external_sop_and_resolution_contract(self) -> None:
        mod = _load_script("houdini-gsplat-relighting", "gsplat_relighting.py")

        def node(path: str, name: str, type_name: str) -> MagicMock:
            value = MagicMock()
            value.path.return_value = path
            value.name.return_value = name
            value.type.return_value.name.return_value = type_name
            return value

        copnet = node("/img/copnet1", "copnet1", "copnet")
        source = node("/obj/geo1/OUT", "OUT", "null")
        sop_import = node("/img/copnet1/gsplat_sop_import", "gsplat_sop_import", "sopimport")
        raster = node("/img/copnet1/gsplat_rasterize", "gsplat_rasterize", "rasterizegsplats")
        premult = node("/img/copnet1/gsplat_premult", "gsplat_premult", "premult")
        selected = []

        def set_first(target, names, value):
            selected.append((target, tuple(names), value))
            return names[0]

        with ExitStack() as stack:
            stack.enter_context(patch.object(mod, "_node", side_effect=[copnet, source]))
            stack.enter_context(patch.object(mod, "_create", side_effect=[sop_import, raster, premult]))
            stack.enter_context(patch.object(mod, "_set_first", side_effect=set_first))
            stack.enter_context(patch.dict(sys.modules, {"hou": MagicMock()}))
            result = mod.create_gsplat_copernicus_raster(
                copnet_path="/img/copnet1",
                sop_path="/obj/geo1/OUT",
                resolution=[960, 540],
            )

        assert result["success"] is True
        assert any(names[0] == "usesoppath" and value is True for _, names, value in selected)
        assert any(names[0] == "setres" and value is True for _, names, value in selected)
        assert any(names[0] == "res1" and value == 960 for _, names, value in selected)
        assert any(names[0] == "res2" and value == 540 for _, names, value in selected)
        raster.setInput.assert_called_once_with(1, sop_import)
        premult.setInput.assert_called_once_with(0, raster)

    def test_copernicus_raster_builds_official_refinement_order(self) -> None:
        mod = _load_script("houdini-gsplat-relighting", "gsplat_relighting.py")

        def node(path: str, name: str, type_name: str) -> MagicMock:
            value = MagicMock()
            value.path.return_value = path
            value.name.return_value = name
            value.type.return_value.name.return_value = type_name
            return value

        copnet = node("/img/copnet1", "copnet1", "copnet")
        source = node("/obj/geo1/OUT", "OUT", "null")
        sop_import = node("/img/copnet1/import", "import", "sopimport")
        raster = node("/img/copnet1/raster", "raster", "rasterizegsplats")
        sharpen = node("/img/copnet1/sharpen", "sharpen", "sharpen")
        hsv = node("/img/copnet1/hsv", "hsv", "hsv")
        gamma_node = node("/img/copnet1/gamma", "gamma", "gamma")
        premult = node("/img/copnet1/premult", "premult", "premult")

        with ExitStack() as stack:
            stack.enter_context(patch.object(mod, "_node", side_effect=[copnet, source]))
            create = stack.enter_context(
                patch.object(
                    mod,
                    "_create",
                    side_effect=[sop_import, raster, sharpen, hsv, gamma_node, premult],
                )
            )
            stack.enter_context(patch.object(mod, "_set_first", side_effect=lambda _node, names, _value: names[0]))
            stack.enter_context(patch.dict(sys.modules, {"hou": MagicMock()}))
            result = mod.create_gsplat_copernicus_raster(
                copnet_path="/img/copnet1",
                sop_path="/obj/geo1/OUT",
                sharpen_amount=0.1,
                saturation_scale=1.1,
                value_scale=1.2,
                gamma=0.8,
            )

        assert result["success"] is True
        assert [call.args[2] for call in create.call_args_list] == [
            "gsplat_sop_import",
            "gsplat_rasterize",
            "gsplat_sharpen",
            "gsplat_hsv",
            "gsplat_gamma",
            "gsplat_premult",
        ]
        sharpen.setInput.assert_called_once_with(0, raster)
        hsv.setInput.assert_called_once_with(0, sharpen)
        gamma_node.setInput.assert_called_once_with(0, hsv)
        premult.setInput.assert_called_once_with(0, gamma_node)

    def test_copernicus_raster_rejects_partial_resolution_contract(self) -> None:
        mod = _load_script("houdini-gsplat-relighting", "gsplat_relighting.py")
        copnet = MagicMock()
        source = MagicMock()
        sop_import = MagicMock()
        raster = MagicMock()

        def set_first(_node, names, _value):
            return None if names[0] == "res2" else names[0]

        with ExitStack() as stack:
            stack.enter_context(patch.object(mod, "_node", side_effect=[copnet, source]))
            stack.enter_context(patch.object(mod, "_create", side_effect=[sop_import, raster]))
            stack.enter_context(patch.object(mod, "_set_first", side_effect=set_first))
            stack.enter_context(patch.dict(sys.modules, {"hou": MagicMock()}))
            result = mod.create_gsplat_copernicus_raster(
                copnet_path="/img/copnet1",
                sop_path="/obj/geo1/OUT",
                resolution=[960, 540],
            )

        assert result["success"] is False
        assert "resolution parameters" in result["error"]
        raster.destroy.assert_called_once_with()
        sop_import.destroy.assert_called_once_with()


class TestGetSessionInfoSkill:
    def test_without_hou_returns_error(self) -> None:
        mod = _load_script("houdini-scripting", "get_session_info.py")
        import builtins

        real_import = builtins.__import__

        def _import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "hou":
                raise ImportError("no hou")
            return real_import(name, globals, locals, fromlist, level)

        with patch("builtins.__import__", side_effect=_import):
            result = mod.get_session_info()
        assert result["success"] is False

    def test_with_mock_hou(self) -> None:
        mod = _load_script("houdini-scripting", "get_session_info.py")
        mock_adapter = MagicMock(__version__="0.28.0", __file__="/tmp/dcc_mcp_houdini/__init__.py")
        mock_hou = MagicMock()
        mock_hou.applicationVersion.return_value = (20, 5, 0)
        mock_hou.applicationVersionString.return_value = "20.5.0"
        mock_hou.isUIAvailable.return_value = True
        mock_hou.hipFile.isNewFile.return_value = False
        mock_hou.hipFile.name.return_value = "/tmp/test.hip"

        with patch.dict(sys.modules, {"dcc_mcp_houdini": mock_adapter, "hou": mock_hou}):
            result = mod.get_session_info()

        assert result["success"] is True
        assert result["context"]["adapter_version"] == "0.28.0"
        assert result["context"]["adapter_module_path"] == "/tmp/dcc_mcp_houdini/__init__.py"
        assert result["context"]["houdini_version_string"] == "20.5.0"
        assert result["context"]["hip_file"] == "/tmp/test.hip"


class TestGetSceneInfoSkill:
    def test_with_mock_hou(self) -> None:
        mod = _load_script("houdini-scene", "get_scene_info.py")
        mock_hou = MagicMock()
        mock_hou.node.return_value = MagicMock(children=lambda: [1, 2, 3])
        mock_hou.hipFile.isNewFile.return_value = True
        mock_hou.hipFile.name.return_value = ""
        mock_hou.frame.return_value = 1
        mock_hou.playbar.playbackRange.return_value = (1, 240)

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.get_scene_info()

        assert result["success"] is True
        assert result["context"]["obj_node_count"] == 3
        assert result["context"]["end_frame"] == 240


class TestInspectSelectionSkill:
    def test_large_packed_geometry_uses_constant_time_queries(self) -> None:
        mod = _load_script("houdini-scene", "inspect_selection.py")

        class PoisonLargeGeometry:
            def pointCount(self):
                return 2_280_000

            def primCount(self):
                return 8_685

            def vertexCount(self):
                return 8_685

            def primTypeNames(self):
                return ("Poly", "PackedFragment")

            def countPrimType(self, type_name):
                return 8_685 if type_name == "PackedFragment" else 0

            def findPointAttrib(self, name):
                return object() if name == "P" else None

            def findPrimAttrib(self, name):
                return object() if name == "name" else None

            def findVertexAttrib(self, _name):
                return None

            def findGlobalAttrib(self, _name):
                return None

            def points(self):
                raise AssertionError("inspect_selection must not enumerate points")

            def prims(self):
                raise AssertionError("inspect_selection must not enumerate primitives")

            def iterPoints(self):
                raise AssertionError("inspect_selection must not iterate points")

            def iterPrims(self):
                raise AssertionError("inspect_selection must not iterate primitives")

            def iterVertices(self):
                raise AssertionError("inspect_selection must not iterate vertices")

        parent = MagicMock(spec=["displayNode"])
        current = _mock_inspection_node(
            "Sop",
            "/obj/geo1/material11",
            "material",
            "geometry",
            "isCurrent",
            "isDisplayFlagSet",
        )
        display = _mock_inspection_node(
            "Sop",
            "/obj/ue_export/OUT_vat_rbd",
            "null",
            "geometry",
            "isCurrent",
            "isDisplayFlagSet",
            "needsToCook",
        )
        current.parent.return_value = parent
        current.isCurrent.return_value = True
        parent.displayNode.return_value = display
        display.needsToCook.return_value = False
        display.geometry.return_value = PoisonLargeGeometry()

        mock_hou = MagicMock()
        mock_hou.selectedNodes.return_value = (current,)
        mock_hou.frame.return_value = 42
        mock_hou.fps.return_value = 24.0
        mock_hou.playbar.playbackRange.return_value = (1, 160)

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.inspect_selection()

        assert result["success"] is True
        context = result["context"]
        assert context["selection"][0]["path"] == "/obj/geo1/material11"
        assert context["display_node"]["path"] == "/obj/ue_export/OUT_vat_rbd"
        assert context["geometry"]["needs_cook"] is False
        assert context["geometry"]["point_count"] == 2_280_000
        assert context["geometry"]["packed_primitive_count"] == 8_685
        assert context["geometry"]["key_attributes"]["point"] == ["P"]
        assert context["geometry"]["key_attributes"]["primitive"] == ["name"]
        assert context["timeline"] == {
            "frame": 42,
            "start_frame": 1,
            "end_frame": 160,
            "fps": 24.0,
        }
        current.geometry.assert_not_called()

    def test_dirty_display_sop_is_not_cooked(self) -> None:
        mod = _load_script("houdini-scene", "inspect_selection.py")
        display = _mock_inspection_node(
            "Sop",
            "/obj/geo1/OUT_dirty",
            "null",
            "geometry",
            "isCurrent",
            "isDisplayFlagSet",
            "needsToCook",
        )
        display.isCurrent.return_value = True
        display.isDisplayFlagSet.return_value = True
        display.needsToCook.return_value = True

        mock_hou = MagicMock()
        mock_hou.selectedNodes.return_value = (display,)
        mock_hou.frame.return_value = 1
        mock_hou.fps.return_value = 24.0
        mock_hou.playbar.playbackRange.return_value = (1, 240)

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.inspect_selection()

        assert result["success"] is True
        assert result["context"]["geometry"] == {"needs_cook": True}
        display.geometry.assert_not_called()


class TestListObjNodesSkill:
    def test_with_mock_hou_and_filter(self) -> None:
        mod = _load_script("houdini-scene", "list_obj_nodes.py")
        child = MagicMock()
        child.path.return_value = "/obj/geo1"
        child.name.return_value = "geo1"
        child.type.return_value.name.return_value = "geo"
        mock_obj = MagicMock()
        mock_obj.children.return_value = [child]
        mock_hou = MagicMock()
        mock_hou.node.return_value = mock_obj

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.list_obj_nodes(type_filter="geo")

        assert result["success"] is True
        assert result["context"]["count"] == 1
        assert result["context"]["nodes"][0]["name"] == "geo1"


class TestSceneNodeInspectionSkills:
    def test_list_child_nodes_with_recursive_filter(self) -> None:
        mod = _load_script("houdini-scene", "list_child_nodes.py")
        box = MagicMock()
        box.path.return_value = "/obj/geo1/box1"
        box.name.return_value = "box1"
        box.type.return_value.name.return_value = "box"
        box.isHidden.return_value = False
        box.children.return_value = []
        geo = MagicMock()
        geo.path.return_value = "/obj/geo1"
        geo.name.return_value = "geo1"
        geo.type.return_value.name.return_value = "geo"
        geo.isHidden.return_value = False
        geo.children.return_value = [box]
        obj = MagicMock()
        obj.path.return_value = "/obj"
        obj.children.return_value = [geo]
        mock_hou = MagicMock()
        mock_hou.node.return_value = obj

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.list_child_nodes("/obj", type_filter="box", recursive=True, max_depth=1)

        assert result["success"] is True
        assert result["context"]["count"] == 1
        assert result["context"]["nodes"][0]["path"] == "/obj/geo1/box1"
        assert result["context"]["nodes"][0]["depth"] == 1

    def test_get_node_info_with_connections(self) -> None:
        mod = _load_script("houdini-scene", "get_node_info.py")
        category = MagicMock()
        category.name.return_value = "Sop"
        type_obj = MagicMock()
        type_obj.name.return_value = "box"
        type_obj.category.return_value = category
        parent = MagicMock()
        parent.path.return_value = "/obj/geo1"
        child = MagicMock()
        child.path.return_value = "/obj/geo1/child"
        input_node = MagicMock()
        input_node.path.return_value = "/obj/geo1/input"
        output_node = MagicMock()
        output_node.path.return_value = "/obj/geo1/output"
        node = MagicMock()
        node.path.return_value = "/obj/geo1/box1"
        node.name.return_value = "box1"
        node.type.return_value = type_obj
        node.parent.return_value = parent
        node.children.return_value = [child]
        node.inputs.return_value = [input_node, None]
        node.outputs.return_value = [output_node]
        node.isBypassed.return_value = False
        node.isDisplayFlagSet.return_value = True
        node.isRenderFlagSet.return_value = False
        node.isTemplateFlagSet.return_value = False
        node.isCurrent.return_value = True
        node.isSelected.return_value = True
        node.isHidden.return_value = False
        mock_hou = MagicMock()
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.get_node_info("/obj/geo1/box1")

        assert result["success"] is True
        info = result["context"]["node"]
        assert info["type"] == "box"
        assert info["category"] == "Sop"
        assert info["parent_path"] == "/obj/geo1"
        assert info["child_count"] == 1
        assert info["inputs"] == ["/obj/geo1/input", None]
        assert info["outputs"] == ["/obj/geo1/output"]

    def test_get_node_info_reports_object_visibility_without_fabricating_sop_flags(self) -> None:
        mod = _load_script("houdini-scene", "get_node_info.py")
        node = _mock_inspection_node(
            "Object",
            "/obj/geo1",
            "geo",
            "isCurrent",
            "isDisplayFlagSet",
            "isHidden",
            "isObjectDisplayed",
            "isSelected",
            "parm",
        )
        renderable = MagicMock(spec=["evalAsInt"])
        renderable.evalAsInt.return_value = 0
        node.isDisplayFlagSet.return_value = True
        node.isObjectDisplayed.return_value = False
        node.isCurrent.return_value = False
        node.isSelected.return_value = False
        node.isHidden.return_value = False
        node.parm.return_value = renderable
        mock_hou = MagicMock()
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.get_node_info("/obj/geo1", include_connections=False)

        assert result["success"] is True
        flags = result["context"]["node"]["flags"]
        assert flags["display"] is True
        assert flags["object_displayed"] is False
        assert flags["object_renderable"] is False
        assert flags["bypassed"] is None
        assert flags["render"] is None
        assert flags["template"] is None
        node.parm.assert_called_once_with("vm_renderable")

    def test_get_node_info_marks_object_visibility_unsupported_for_other_categories(self) -> None:
        mod = _load_script("houdini-scene", "get_node_info.py")
        node = _mock_inspection_node("Unknown", "/custom/node1", "custom", "isObjectDisplayed", "parm")
        node.isObjectDisplayed.return_value = False
        node.parm.return_value.evalAsInt.return_value = 0
        mock_hou = MagicMock()
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.get_node_info("/custom/node1", include_connections=False)

        flags = result["context"]["node"]["flags"]
        assert flags["object_displayed"] is None
        assert flags["object_renderable"] is None


class TestNodeSkills:
    def test_layout_children_can_match_network_editor_selected_layout(self) -> None:
        mod = _load_script("houdini-nodes", "layout_children.py")
        parent = MagicMock()
        parent.path.return_value = "/obj/geo1"
        selected = MagicMock()
        selected.path.return_value = "/obj/geo1/box1"
        selected.parent.return_value = parent
        sibling = MagicMock()
        sibling.parent.return_value = parent
        parent.children.return_value = [selected, sibling]
        mock_hou = MagicMock()
        mock_hou.node.return_value = parent
        mock_hou.selectedNodes.return_value = [selected]

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.layout_children("/obj/geo1", selected_only=True)

        assert result["success"] is True
        parent.layoutChildren.assert_called_once_with(items=[selected])
        assert result["context"]["node_paths"] == ["/obj/geo1/box1"]

    def test_create_node_with_mock_hou(self) -> None:
        mod = _load_script("houdini-nodes", "create_node.py")
        child = MagicMock()
        child.path.return_value = "/obj/geo1"
        child.name.return_value = "geo1"
        child.type.return_value.name.return_value = "geo"
        parent = MagicMock()
        parent.path.return_value = "/obj"
        parent.createNode.return_value = child
        mock_hou = MagicMock()
        mock_hou.node.return_value = parent

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.create_node("/obj", "geo", node_name="geo1")

        assert result["success"] is True
        parent.createNode.assert_called_once()
        assert result["context"]["node"]["path"] == "/obj/geo1"

    def test_set_node_parms_with_scalar_tuple_and_button(self) -> None:
        mod = _load_script("houdini-nodes", "set_node_parms.py")
        parm = MagicMock()
        tuple_parm = MagicMock()
        button = MagicMock()
        node = MagicMock()
        node.path.return_value = "/obj/geo1"
        node.name.return_value = "geo1"
        node.type.return_value.name.return_value = "geo"
        node.parmTuple.side_effect = lambda name: tuple_parm if name == "t" else None
        node.parm.side_effect = lambda name: {"scale": parm, "execute": button}.get(name)
        mock_hou = MagicMock()
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.set_node_parms("/obj/geo1", {"t": [1, 2, 3], "scale": 2}, ["execute"])

        assert result["success"] is True
        tuple_parm.set.assert_called_once_with((1, 2, 3))
        parm.set.assert_called_once_with(2)
        button.pressButton.assert_called_once()

    def test_connect_nodes_with_mock_hou(self) -> None:
        mod = _load_script("houdini-nodes", "connect_nodes.py")
        input_node = MagicMock()
        output_node = MagicMock()
        mock_hou = MagicMock()
        mock_hou.node.side_effect = lambda path: {"/obj/a": input_node, "/obj/b": output_node}[path]

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.connect_nodes("/obj/a", "/obj/b", input_index=1, output_index=0)

        assert result["success"] is True
        input_node.setInput.assert_called_once_with(1, output_node, 0)


class TestHdaSkills:
    def test_execute_hda_installs_sets_buttons_and_cooks(self, tmp_path: Path) -> None:
        mod = _load_script("houdini-hda", "execute_hda.py")
        hda_file = tmp_path / "asset.hda"
        hda_file.write_text("fake", encoding="utf-8")
        node = MagicMock()
        node.path.return_value = "/obj/myasset"
        node.name.return_value = "myasset"
        node.type.return_value.name.return_value = "my_hda"
        parm = MagicMock()
        button = MagicMock()
        node.parmTuple.return_value = None
        node.parm.side_effect = lambda name: {"scale": parm, "execute": button}.get(name)
        parent = MagicMock()
        parent.createNode.return_value = node
        mock_hou = MagicMock()
        mock_hou.node.return_value = parent

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.execute_hda(
                "my_hda",
                hda_file=str(hda_file),
                parameters={"scale": 2},
                press_buttons=["execute"],
            )

        assert result["success"] is True
        mock_hou.hda.installFile.assert_called_once_with(str(hda_file))
        parm.set.assert_called_once_with(2)
        button.pressButton.assert_called_once()
        node.cook.assert_called_once_with(force=False)

    def test_list_hda_definitions_from_file(self, tmp_path: Path) -> None:
        mod = _load_script("houdini-hda", "list_hda_definitions.py")
        hda_file = tmp_path / "asset.hda"
        hda_file.write_text("fake", encoding="utf-8")
        category = MagicMock()
        category.name.return_value = "Sop"
        node_type = MagicMock()
        node_type.category.return_value = category
        definition = MagicMock()
        definition.nodeType.return_value = node_type
        definition.nodeTypeName.return_value = "my_hda"
        definition.description.return_value = "My HDA"
        definition.version.return_value = "1.0"
        mock_hou = MagicMock()
        mock_hou.hda.definitionsInFile.return_value = [definition]

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.list_hda_definitions(str(hda_file))

        assert result["success"] is True
        assert result["context"]["definition_count"] == 1
        assert result["context"]["definitions"][0]["node_type_name"] == "my_hda"


class TestMaterialSkills:
    def test_create_material_sets_parameters(self) -> None:
        mod = _load_script("houdini-materials", "create_material.py")
        tuple_parm = MagicMock()
        scalar_parm = MagicMock()
        material = MagicMock()
        material.path.return_value = "/mat/clay"
        material.name.return_value = "clay"
        material.type.return_value.name.return_value = "principledshader::2.0"
        material.parmTuple.side_effect = lambda name: tuple_parm if name == "basecolor" else None
        material.parm.side_effect = lambda name: scalar_parm if name == "rough" else None
        parent = MagicMock()
        parent.path.return_value = "/mat"
        parent.createNode.return_value = material
        mock_hou = MagicMock()
        mock_hou.node.return_value = parent

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.create_material(
                material_name="clay",
                parameters={"basecolor": [0.8, 0.4, 0.2], "rough": 0.65},
            )

        assert result["success"] is True
        parent.createNode.assert_called_once()
        tuple_parm.set.assert_called_once_with((0.8, 0.4, 0.2))
        scalar_parm.set.assert_called_once_with(0.65)
        assert result["context"]["material"]["path"] == "/mat/clay"

    def test_assign_material_sets_material_path(self) -> None:
        mod = _load_script("houdini-materials", "assign_material.py")
        parm = MagicMock()
        target = MagicMock()
        target.path.return_value = "/obj/geo1"
        target.name.return_value = "geo1"
        target.type.return_value.name.return_value = "geo"
        target.parm.return_value = parm
        material = MagicMock()
        material.path.return_value = "/mat/clay"
        material.name.return_value = "clay"
        material.type.return_value.name.return_value = "principledshader::2.0"
        mock_hou = MagicMock()
        mock_hou.node.side_effect = lambda path: {"/obj/geo1": target, "/mat/clay": material}.get(path)

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.assign_material("/obj/geo1", "/mat/clay")

        assert result["success"] is True
        parm.set.assert_called_once_with("/mat/clay")
        assert result["context"]["target"]["path"] == "/obj/geo1"


class TestAutomationSkills:
    def test_run_python_file_with_mock_hou(self, tmp_path: Path) -> None:
        mod = _load_script("houdini-automation", "run_python_file.py")
        script = tmp_path / "script.py"
        script.write_text("print('hello')\nresult = context['value'] + 1\n", encoding="utf-8")

        with patch.dict(sys.modules, {"hou": MagicMock()}):
            result = mod.run_python_file(str(script), context={"value": 41})

        assert result["success"] is True
        assert "hello" in result["context"]["stdout"]
        assert result["context"]["result"] == "42"

    def test_save_hip_file_atomically_replaces_target(self, tmp_path: Path) -> None:
        mod = _load_script("houdini-automation", "save_hip_file.py")
        target = tmp_path / "scene.hip"
        target.write_bytes(b"old")
        hip_file = MagicMock()
        hip_file.name.return_value = str(target)
        hip_file.path.return_value = str(target)

        def save(file_name: str, save_to_recent_files: bool) -> None:
            assert save_to_recent_files is False
            Path(file_name).write_bytes(b"new")

        hip_file.save.side_effect = save
        mock_hou = MagicMock(hipFile=hip_file)
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.save_hip_file(str(target))

        resolved = str(target.resolve())
        assert result["success"] is True
        assert result["context"] == {"hip_file": resolved, "atomic_replace": True}
        assert target.read_bytes() == b"new"
        hip_file.setName.assert_called_once_with(resolved)
        assert list(tmp_path.iterdir()) == [target]

    def test_save_hip_file_preserves_target_when_replace_fails(self, tmp_path: Path) -> None:
        mod = _load_script("houdini-automation", "save_hip_file.py")
        previous = tmp_path / "previous.hip"
        target = tmp_path / "scene.hip"
        target.write_bytes(b"old")
        hip_file = MagicMock()
        hip_file.name.return_value = str(previous)
        hip_file.path.return_value = str(previous)
        hip_file.save.side_effect = lambda file_name, save_to_recent_files: Path(file_name).write_bytes(b"new")
        mock_hou = MagicMock(hipFile=hip_file)

        with patch.dict(sys.modules, {"hou": mock_hou}), patch.object(
            mod.os,
            "replace",
            side_effect=OSError("replace failed"),
        ):
            result = mod.save_hip_file(str(target))

        assert result["success"] is False
        assert target.read_bytes() == b"old"
        recovery = Path(result["context"]["recovery_file"])
        assert recovery.read_bytes() == b"new"
        assert hip_file.setName.call_args_list[-1] == call(str(recovery))
        assert sorted(path.name for path in tmp_path.iterdir()) == sorted([target.name, recovery.name])

    def test_build_node_chain_with_mock_hou(self) -> None:
        mod = _load_script("houdini-automation", "build_node_chain.py")
        box_type = MagicMock()
        box_type.name.return_value = "box"
        box_type.maxNumInputs.return_value = 0
        box_type.maxNumOutputs.return_value = 1
        null_type = MagicMock()
        null_type.name.return_value = "null"
        null_type.maxNumInputs.return_value = 4
        null_type.maxNumOutputs.return_value = 1
        box = MagicMock()
        box.name.return_value = "box1"
        box.path.return_value = "/obj/geo1/box1"
        box.type.return_value = box_type
        null = MagicMock()
        null.name.return_value = "OUT"
        null.path.return_value = "/obj/geo1/OUT"
        null.type.return_value = null_type
        connection = MagicMock()
        connection.inputIndex.return_value = 0
        connection.inputItem.return_value = box
        connection.inputItemOutputIndex.return_value = 0
        null.inputConnections.return_value = [connection]
        parent = MagicMock()
        parent.path.return_value = "/obj/geo1"
        parent.isNetwork.return_value = True
        parent.isEditable.return_value = True
        parent.children.return_value = []
        parent.childTypeCategory.return_value.nodeTypes.return_value = {
            "box": box_type,
            "null": null_type,
        }
        parent.createNode.side_effect = [box, null]
        parent.node.side_effect = lambda name: {"box1": box, "OUT": null}.get(name)
        mock_hou = MagicMock()
        mock_hou.node.return_value = parent
        mock_hou.text.variableName.side_effect = lambda value, safe_chars: value

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.build_node_chain(
                "/obj/geo1",
                [{"node_type": "box", "node_name": "box1"}, {"node_type": "null", "node_name": "OUT"}],
                [{"input": "OUT", "output": "box1"}],
            )

        assert result["success"] is True
        assert parent.createNode.call_args_list == [
            call("box", node_name="box1", exact_type_name=True),
            call("null", node_name="OUT", exact_type_name=True),
        ]
        null.setInput.assert_called_once_with(0, box, 0)
        null.cook.assert_called_once_with(force=False)
