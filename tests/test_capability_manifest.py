"""Unit tests for :mod:`dcc_mcp_houdini._capability_manifest`.

These tests verify the SOLID projection from live catalog state into a compact
gateway-friendly manifest. No live Houdini is required — the builder only
projects injected catalog data.
"""

from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import MagicMock

from dcc_mcp_houdini._capability_manifest import (
    CapabilityRecord,
    HoudiniCapabilityManifestBuilder,
    _as_dict,
    build_manifest_payload,
    register_capability_mcp_tool,
)


class _BadToDict:
    keep = "visible"

    def to_dict(self):
        raise ValueError("bad conversion")


def test_as_dict_falls_back_when_to_dict_raises_expected_error():
    assert _as_dict(_BadToDict())["keep"] == "visible"


def _action(
    name: str,
    *,
    skill: str = None,
    summary: str = "",
    tags: List[str] = None,
    execution: str = "sync",
    timeout_hint_secs: int = None,
    input_schema: Dict[str, Any] = None,
    group: str = None,
) -> Dict[str, Any]:
    entry: Dict[str, Any] = {"name": name}
    if skill is not None:
        entry["skill"] = skill
    if summary:
        entry["summary"] = summary
    if tags is not None:
        entry["tags"] = tags
    if execution:
        entry["execution"] = execution
    if timeout_hint_secs is not None:
        entry["timeout_hint_secs"] = timeout_hint_secs
    if input_schema is not None:
        entry["input_schema"] = input_schema
    if group:
        entry["group"] = group
    return entry


def _skill(name: str, *, tags: List[str] = None, summary: str = "") -> Dict[str, Any]:
    out: Dict[str, Any] = {"name": name}
    if tags is not None:
        out["tags"] = tags
    if summary:
        out["summary"] = summary
    return out


def test_builder_empty_catalog_returns_empty_records():
    builder = HoudiniCapabilityManifestBuilder(
        skill_lister=list,
        action_lister=list,
        is_loaded=lambda _: False,
    )
    assert builder.build() == []


def test_builder_tolerates_missing_lister_callables():
    builder = HoudiniCapabilityManifestBuilder()
    assert builder.build() == []


def test_builder_projects_loaded_and_unloaded_actions():
    actions = [
        _action("houdini_scene__get_scene_info", skill="houdini-scene", summary="Scene info", tags=["scene"]),
        _action(
            "houdini_scripting__execute_python",
            skill="houdini-scripting",
            summary="Run python",
            tags=["python"],
            execution="async",
            timeout_hint_secs=120,
            input_schema={"type": "object"},
        ),
        _action("houdini_render__render", skill="houdini-render", summary="Render", tags=["render"]),
    ]
    skills = [
        _skill("houdini-scene", tags=["scene", "io"]),
        _skill("houdini-scripting", tags=["scripting"]),
        _skill("houdini-render", tags=["render"]),
    ]
    loaded = {"houdini-scene", "houdini-scripting"}

    builder = HoudiniCapabilityManifestBuilder(
        skill_lister=lambda: skills,
        action_lister=lambda: actions,
        is_loaded=lambda name: name in loaded,
    )
    records = builder.build()
    assert len(records) == 3
    by_name = {r.backend_tool: r for r in records}
    assert by_name["houdini_scene__get_scene_info"].loaded is True
    assert by_name["houdini_render__render"].loaded is False
    rec = by_name["houdini_scripting__execute_python"]
    assert rec.execution == "async"
    assert rec.timeout_hint_secs == 120
    assert rec.has_schema is True
    assert rec.tool_slug == "houdini.instance.houdini_scripting__execute_python"
    assert set(by_name["houdini_scene__get_scene_info"].tags) >= {"scene", "io"}


def test_builder_drops_skill_and_group_stubs():
    actions = [
        _action("houdini_scene__get_scene_info", skill="houdini-scene"),
        _action("__skill__houdini_render", skill="houdini-render"),
        _action("__group__houdini-render.extended", skill="houdini-render"),
    ]
    builder = HoudiniCapabilityManifestBuilder(
        skill_lister=lambda: [_skill("houdini-scene")],
        action_lister=lambda: actions,
        is_loaded=lambda _: False,
    )
    records = builder.build()
    assert [r.backend_tool for r in records] == ["houdini_scene__get_scene_info"]


def test_builder_truncates_long_summary():
    long = "x" * 500
    actions = [_action("houdini_scene__get_scene_info", skill="houdini-scene", summary=long)]
    builder = HoudiniCapabilityManifestBuilder(
        skill_lister=lambda: [_skill("houdini-scene")],
        action_lister=lambda: actions,
        is_loaded=lambda _: True,
    )
    record = builder.build()[0]
    assert len(record.summary) <= 200
    assert record.summary.endswith("…")


def test_builder_infers_skill_from_tool_name_convention():
    actions = [_action("houdini_scene__get_scene_info")]
    builder = HoudiniCapabilityManifestBuilder(
        skill_lister=list,
        action_lister=lambda: actions,
        is_loaded=lambda _: False,
    )
    record = builder.build()[0]
    assert record.skill_name == "houdini-scene"


def test_capability_record_to_dict_omits_empty_optional_fields():
    rec = CapabilityRecord(
        tool_slug="houdini.instance.houdini_scene__get_scene_info",
        backend_tool="houdini_scene__get_scene_info",
        skill_name="houdini-scene",
        summary="",
        loaded=False,
    )
    dumped = rec.to_dict()
    assert "summary" not in dumped
    assert "tags" not in dumped
    assert dumped["loaded"] is False


def test_build_manifest_payload_headers_and_totals():
    records = [
        CapabilityRecord("houdini.instance.a", "a", "s1", "", True),
        CapabilityRecord("houdini.instance.b", "b", "s2", "", False),
    ]
    payload = build_manifest_payload(records, dcc_version="20.5", scene="/a.hip", instance_id="abc")
    assert payload["schema_version"] == "1"
    assert payload["dcc_type"] == "houdini"
    assert payload["metadata"]["scene"] == "/a.hip"
    assert payload["totals"] == {
        "actions": 2,
        "loaded_actions": 1,
        "unloaded_actions": 1,
        "skills": 2,
        "loaded_skills": 1,
        "unloaded_skills": 1,
    }


def test_build_manifest_payload_strips_none_metadata():
    payload = build_manifest_payload([], dcc_version=None, scene="", instance_id=None)
    assert "dcc_version" not in payload["metadata"]
    assert "scene" not in payload["metadata"]
    assert "instance_id" not in payload["metadata"]


class _FakeRegistry:
    def __init__(self):
        self.registered: List[tuple] = []

    def register(self, name, **kwargs):
        self.registered.append((name, kwargs))


class _FakeInner:
    def __init__(self):
        self.registry = _FakeRegistry()
        self.handlers: Dict[str, Any] = {}

    def register_handler(self, name: str, handler):
        self.handlers[name] = handler


def test_register_capability_mcp_tool_returns_manifest_via_handler():
    inner = _FakeInner()
    builder = HoudiniCapabilityManifestBuilder(
        skill_lister=lambda: [_skill("houdini-scene")],
        action_lister=lambda: [_action("houdini_scene__get_scene_info", skill="houdini-scene")],
        is_loaded=lambda _: True,
    )
    fake_server = MagicMock()
    fake_server._server = inner
    fake_server._config = MagicMock(scene="/p/a.hip", dcc_version="20.5")

    ok = register_capability_mcp_tool(fake_server, builder=builder)
    assert ok is True
    assert "dcc_capability_manifest" in inner.handlers
    declared = [name for name, _ in inner.registry.registered]
    assert "dcc_capability_manifest" in declared

    result = inner.handlers["dcc_capability_manifest"]({})
    assert result["success"] is True
    assert result["context"]["totals"]["loaded_actions"] == 1
    assert result["context"]["capabilities"][0]["backend_tool"] == "houdini_scene__get_scene_info"


def test_register_capability_mcp_tool_honours_loaded_only_param():
    inner = _FakeInner()
    builder = HoudiniCapabilityManifestBuilder(
        skill_lister=lambda: [_skill("houdini-scene"), _skill("houdini-render")],
        action_lister=lambda: [
            _action("houdini_scene__get_scene_info", skill="houdini-scene"),
            _action("houdini_render__render", skill="houdini-render"),
        ],
        is_loaded=lambda name: name == "houdini-scene",
    )
    fake_server = MagicMock()
    fake_server._server = inner
    fake_server._config = MagicMock(scene=None, dcc_version="20.5")

    register_capability_mcp_tool(fake_server, builder=builder)
    handler = inner.handlers["dcc_capability_manifest"]
    full = handler({})["context"]
    subset = handler({"loaded_only": True})["context"]
    assert full["totals"]["actions"] == 2
    assert subset["totals"]["actions"] == 1


def test_register_capability_mcp_tool_missing_inner_returns_false():
    fake_server = MagicMock()
    fake_server._server = None
    builder = HoudiniCapabilityManifestBuilder()
    assert register_capability_mcp_tool(fake_server, builder=builder) is False


def test_builder_projects_unloaded_skills_with_load_hint():
    actions = [_action("houdini_scene__get_scene_info", skill="houdini-scene")]
    skills = [_skill("houdini-scene"), _skill("houdini-nodes", tags=["nodes"])]
    skill_info_map = {
        "houdini-nodes": {
            "tags": ["nodes"],
            "tools": [
                {
                    "name": "create_node",
                    "description": "Create a node.",
                    "execution": "sync",
                    "group": "nodes",
                    "input_schema": {"type": "object"},
                },
                {"name": "__skill__houdini-nodes"},
            ],
        },
    }
    builder = HoudiniCapabilityManifestBuilder(
        skill_lister=lambda: skills,
        action_lister=lambda: actions,
        is_loaded=lambda name: name == "houdini-scene",
        skill_info_lister=lambda name: skill_info_map.get(name),
    )
    records = builder.build()
    by_tool = {r.backend_tool: r for r in records}
    create = by_tool["houdini_nodes__create_node"]
    assert create.loaded is False
    assert create.requires_load_skill is True
    assert create.load_hint == {"tool": "load_skill", "arguments": {"skill_name": "houdini-nodes"}}
    assert "nodes" in create.tags
    assert not any(r.backend_tool.startswith("__skill__") for r in records)
