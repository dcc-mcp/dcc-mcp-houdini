"""Unit tests for :mod:`dcc_mcp_houdini._context_snapshot`.

A fake ``hou`` is injected via the ``hou_provider`` parameter so we can assert
every branch — including the headless / unavailable fallback — without a live
Houdini.
"""

from __future__ import annotations

from types import SimpleNamespace

from dcc_mcp_houdini._context_snapshot import (
    HoudiniContextSnapshotProvider,
    collect_gateway_metadata,
    make_snapshot_provider,
)


def _fake_hou(*, scene="/projects/shot.hip", has_file=True, unsaved=False, version="20.5.445", obj_count=3):
    hip = SimpleNamespace(
        path=lambda: scene,
        name=lambda: scene,
        hasFile=lambda: has_file,
        hasUnsavedChanges=lambda: unsaved,
    )
    playbar = SimpleNamespace(playbackRange=lambda: (1001.0, 1100.0))
    children = [object()] * obj_count
    obj_node = SimpleNamespace(children=lambda: children)
    return SimpleNamespace(
        hipFile=hip,
        playbar=playbar,
        frame=lambda: 1001,
        node=lambda path: obj_node if path == "/obj" else None,
        applicationVersionString=lambda: version,
    )


def test_provider_collects_full_snapshot_when_houdini_available():
    provider = HoudiniContextSnapshotProvider(hou_provider=lambda: _fake_hou())
    snap = provider()
    assert snap["dcc"] == "houdini"
    assert snap["available"] is True
    assert snap["scene"] == "/projects/shot.hip"
    assert snap["scene_saved"] is True
    assert snap["frame"] == 1001
    assert snap["frame_range"] == [1001, 1100]
    assert snap["obj_node_count"] == 3
    assert snap["version"] == "20.5.445"
    assert snap["display_name"] == "Houdini 20.5.445 — shot.hip"
    assert snap["pid"] > 0


def test_provider_returns_stub_when_hou_unavailable():
    provider = HoudiniContextSnapshotProvider(hou_provider=lambda: None)
    snap = provider()
    assert snap["available"] is False
    assert snap["dcc"] == "houdini"
    assert "scene" not in snap


def test_provider_survives_hou_factory_exception():
    def boom():
        raise RuntimeError("hou not initialised")

    provider = HoudiniContextSnapshotProvider(hou_provider=boom)
    snap = provider()
    assert snap["available"] is False


def test_provider_unsaved_hip_omits_scene():
    provider = HoudiniContextSnapshotProvider(hou_provider=lambda: _fake_hou(has_file=False))
    snap = provider()
    assert "scene" not in snap
    assert snap["available"] is True


def test_provider_returns_fresh_dict_each_call():
    provider = HoudiniContextSnapshotProvider(hou_provider=lambda: _fake_hou())
    snap1 = provider()
    snap2 = provider()
    assert snap1 is not snap2


def test_collect_gateway_metadata_single_document():
    provider = HoudiniContextSnapshotProvider(hou_provider=lambda: _fake_hou(scene="/p/a.hip"))
    meta = collect_gateway_metadata(provider)
    assert meta["scene"] == "/p/a.hip"
    assert meta["version"] == "20.5.445"
    assert meta["documents"] == ["/p/a.hip"]
    assert meta["display_name"] == "Houdini 20.5.445 — a.hip"


def test_collect_gateway_metadata_no_scene_produces_empty_documents():
    provider = HoudiniContextSnapshotProvider(hou_provider=lambda: _fake_hou(has_file=False))
    meta = collect_gateway_metadata(provider)
    assert meta["scene"] is None
    assert meta["documents"] == []
    assert meta["version"] == "20.5.445"


def test_collect_gateway_metadata_headless_returns_all_none_or_empty():
    provider = HoudiniContextSnapshotProvider(hou_provider=lambda: None)
    meta = collect_gateway_metadata(provider)
    assert meta == {"scene": None, "version": None, "documents": [], "display_name": None}


def test_collect_gateway_metadata_defaults_to_builtin_provider():
    meta = collect_gateway_metadata()
    assert set(meta) == {"scene", "version", "documents", "display_name"}


def test_make_snapshot_provider_returns_callable_provider():
    provider = make_snapshot_provider(hou_provider=lambda: _fake_hou())
    assert callable(provider)
    assert provider()["available"] is True
