"""Morphology-aware semantic skill recall tests for Houdini.

These exercise :mod:`dcc_mcp_houdini._semantic_index` directly (no live server
/ Houdini needed).  The vector backend ships in ``dcc-mcp-core>=0.17.38``;
tests skip cleanly on older cores.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

import pytest

from dcc_mcp_houdini import _semantic_index

pytestmark = pytest.mark.skipif(
    _semantic_index.HoudiniSemanticIndex.build(embedder_kind="hashed") is None,
    reason="dcc-mcp-core lacks VectorSkillIndex (needs >=0.17.38)",
)


@dataclass
class _FakeSummary:
    name: str
    description: str = ""
    search_hint: str = ""
    tags: Tuple[str, ...] = field(default_factory=tuple)
    dcc: str = "houdini"
    version: str = "1.0.0"


def _catalog() -> List[_FakeSummary]:
    return [
        _FakeSummary("houdini-render", description="render the active frame and write images to disk"),
        _FakeSummary("houdini-nodes", description="create and connect SOP nodes in the network"),
        _FakeSummary("houdini-automation", description="set frame range and save the hip file"),
        _FakeSummary("houdini-materials", description="create and assign materials"),
    ]


class TestGating:
    def test_disabled_by_default(self):
        assert _semantic_index.resolve_semantic_index_enabled({}) is False

    @pytest.mark.parametrize("token", ["1", "true", "YES", "on"])
    def test_enabled_truthy_tokens(self, token: str):
        env = {_semantic_index.ENV_SEMANTIC_INDEX: token}
        assert _semantic_index.resolve_semantic_index_enabled(env) is True

    def test_build_semantic_index_none_when_disabled(self, monkeypatch):
        monkeypatch.delenv(_semantic_index.ENV_SEMANTIC_INDEX, raising=False)
        assert _semantic_index.build_semantic_index() is None

    def test_build_semantic_index_present_when_enabled(self, monkeypatch):
        monkeypatch.setenv(_semantic_index.ENV_SEMANTIC_INDEX, "1")
        index = _semantic_index.build_semantic_index()
        assert index is not None
        assert index.embedder_kind == "hashed"

    def test_embedder_kind_resolution(self):
        assert _semantic_index.resolve_embedder_kind({}) == "hashed"
        assert _semantic_index.resolve_embedder_kind({_semantic_index.ENV_SEMANTIC_EMBEDDER: "onnx"}) == "onnx"


class TestMorphologyRecall:
    def _index(self):
        idx = _semantic_index.HoudiniSemanticIndex.build(embedder_kind="hashed")
        assert idx is not None
        return idx

    def test_inflected_query_recovers_skill_missed_by_lexical(self):
        idx = self._index()
        catalog = _catalog()
        fused = idx.augment(base=[], query="rendering the current frame", all_summaries=catalog)
        names = [s.name for s in fused]
        assert "houdini-render" in names

    def test_base_results_are_never_demoted(self):
        idx = self._index()
        catalog = _catalog()
        base = [catalog[2], catalog[3]]  # automation, materials (canonical order)
        fused = idx.augment(base=base, query="rendering", all_summaries=catalog)
        assert [s.name for s in fused[:2]] == ["houdini-automation", "houdini-materials"]

    def test_no_duplicates_when_recall_overlaps_base(self):
        idx = self._index()
        catalog = _catalog()
        base = [catalog[0]]  # houdini-render already present
        fused = idx.augment(base=base, query="rendering", all_summaries=catalog)
        assert [s.name for s in fused].count("houdini-render") == 1

    def test_empty_query_returns_base_unchanged(self):
        idx = self._index()
        catalog = _catalog()
        base = [catalog[1]]
        assert idx.augment(base=base, query="", all_summaries=catalog) == base
        assert idx.augment(base=base, query=None, all_summaries=catalog) == base

    def test_limit_truncates_fused_result(self):
        idx = self._index()
        catalog = _catalog()
        fused = idx.augment(base=list(catalog), query="rendering", all_summaries=catalog, limit=2)
        assert len(fused) == 2

    def test_augment_accepts_dict_summaries(self):
        """find_skills returns dicts; the index must handle dict summaries too."""
        idx = self._index()
        catalog = [
            {"name": "houdini-render", "description": "render the active frame"},
            {"name": "houdini-nodes", "description": "create SOP nodes"},
        ]
        fused = idx.augment(base=[], query="rendering", all_summaries=catalog)
        names = [_semantic_index._summary_name(s) for s in fused]
        assert "houdini-render" in names

    def test_rebuild_is_cached_until_catalog_changes(self):
        idx = self._index()
        catalog = _catalog()
        idx.rebuild(catalog)
        sig = idx._signature
        idx.rebuild(catalog)
        assert idx._signature == sig
        idx.rebuild(catalog + [_FakeSummary("houdini-new", description="brand new skill")])
        assert idx._signature != sig
