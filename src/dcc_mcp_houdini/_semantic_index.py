"""Optional morphology-aware semantic skill recall.

Mirrors :mod:`dcc_mcp_maya._semantic_index`.  ``HoudiniMcpServer.find_skills``
routes through the Rust BM25-lite scorer in ``dcc-mcp-skills``.  That path is
excellent for exact / tokenised queries but misses morphology variants a
natural-language MCP agent commonly produces — ``"rendering the active frame"``
does not tokenise to the literal ``render`` token in a ``houdini-render``
skill's name / summary.

This module fuses the Python-side ``VectorSkillIndex`` (``HashedEmbedder``
char-3-gram defaults, zero runtime deps) with a ``LexicalSkillIndex`` through
``RrfFusionIndex``.  The fused index is used **only to augment** the canonical
base results: base ordering is preserved verbatim and vector-only recalls are
appended afterwards.

The whole feature is gated behind ``DCC_MCP_HOUDINI_SEMANTIC_INDEX=1`` so the
default behaviour is unchanged.  When ``dcc-mcp-core[semantic]`` is installed,
``DCC_MCP_HOUDINI_SEMANTIC_EMBEDDER=onnx`` swaps ``HashedEmbedder`` for the real
dense ``OnnxEmbedder`` without touching any call site.
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional, Sequence

from dcc_mcp_houdini._env import (
    ENV_SEMANTIC_EMBEDDER,
    ENV_SEMANTIC_INDEX,
    resolve_semantic_embedder_kind,
    resolve_semantic_index_enabled,
)

logger = logging.getLogger(__name__)

__all__ = [
    "ENV_SEMANTIC_EMBEDDER",
    "ENV_SEMANTIC_INDEX",
    "HoudiniSemanticIndex",
    "build_semantic_index",
    "resolve_embedder_kind",
    "resolve_semantic_index_enabled",
]

# Aliases for parity with Maya's module-level helper names.
resolve_embedder_kind = resolve_semantic_embedder_kind


def _summary_text(summary: Any) -> str:
    """Best-effort description string from a ``SkillSummary``-like object/dict."""
    parts: List[str] = []
    for attr in ("description", "search_hint", "summary"):
        value = _get(summary, attr)
        value = str(value) if value else ""
        if value and value not in parts:
            parts.append(value)
    return " ".join(parts)


def _summary_name(summary: Any) -> Optional[str]:
    name = _get(summary, "name")
    return str(name) if name else None


def _get(obj: Any, attr: str) -> Any:
    """Read ``attr`` from an object or dict, returning ``None`` when absent."""
    if isinstance(obj, dict):
        return obj.get(attr)
    return getattr(obj, attr, None)


def _build_embedder(kind: str) -> Any:
    """Construct the requested embedder, falling back to ``HashedEmbedder``."""
    from dcc_mcp_core import HashedEmbedder  # noqa: PLC0415

    if kind != "onnx":
        return HashedEmbedder()
    try:
        from dcc_mcp_core import OnnxEmbedder  # noqa: PLC0415

        return OnnxEmbedder()
    except Exception as exc:  # noqa: BLE001 — EmbedderError / ImportError
        logger.warning(
            "[houdini] DCC_MCP_HOUDINI_SEMANTIC_EMBEDDER=onnx requested but unavailable "
            "(%s); falling back to HashedEmbedder. Install dcc-mcp-core[semantic].",
            exc,
        )
        return HashedEmbedder()


class HoudiniSemanticIndex:
    """Lexical + vector fusion index used to augment base ``find_skills``."""

    def __init__(self, fusion: Any, embedder_kind: str) -> None:
        self._fusion = fusion
        self.embedder_kind = embedder_kind
        self._signature: Optional[frozenset] = None

    # ── construction ────────────────────────────────────────────────────
    @classmethod
    def build(cls, *, embedder_kind: Optional[str] = None) -> Optional["HoudiniSemanticIndex"]:
        """Build the fused index, or ``None`` when core lacks the semantic API."""
        try:
            from dcc_mcp_core import LexicalSkillIndex, RrfFusionIndex, VectorSkillIndex  # noqa: PLC0415
        except Exception as exc:  # noqa: BLE001 — older core without the vector API
            logger.info(
                "[houdini] semantic index requested but dcc-mcp-core lacks "
                "VectorSkillIndex (%s); needs dcc-mcp-core>=0.17.38.",
                exc,
            )
            return None
        kind = embedder_kind or resolve_semantic_embedder_kind()
        try:
            fusion = (
                RrfFusionIndex()
                .register("lex", LexicalSkillIndex())
                .register("vec", VectorSkillIndex(embedder=_build_embedder(kind)))
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[houdini] failed to build semantic fusion index: %s", exc)
            return None
        return cls(fusion, kind)

    # ── indexing / recall ───────────────────────────────────────────────
    def rebuild(self, summaries: Sequence[Any]) -> None:
        """(Re)index ``summaries`` only when the skill set changed."""
        from dcc_mcp_core import SkillDocument  # noqa: PLC0415

        signature = frozenset(
            (name, str(_get(s, "version") or ""))
            for s, name in ((s, _summary_name(s)) for s in summaries)
            if name is not None
        )
        if signature == self._signature:
            return
        docs = []
        for summary in summaries:
            name = _summary_name(summary)
            if name is None:
                continue
            tags = _get(summary, "tags") or ()
            docs.append(
                SkillDocument(
                    skill_id=name,
                    name=name,
                    summary=_summary_text(summary),
                    tags=tuple(str(t) for t in tags),
                    dcc_name=str(_get(summary, "dcc") or ""),
                )
            )
        self._fusion.clear()
        if docs:
            self._fusion.index(docs)
        self._signature = signature

    def recall(self, query: str, *, k: int = 16) -> List[str]:
        """Return fused-rank ``skill_id``s for ``query`` (best first)."""
        if not query or not str(query).strip():
            return []
        try:
            hits = self._fusion.search(str(query), k=k)
        except Exception as exc:  # noqa: BLE001
            logger.debug("[houdini] semantic recall failed for %r: %s", query, exc)
            return []
        return [hit.skill_id for hit in hits]

    # ── fusion / augmentation ───────────────────────────────────────────
    def augment(
        self,
        base: Sequence[Any],
        query: Optional[str],
        all_summaries: Sequence[Any],
        *,
        limit: Optional[int] = None,
    ) -> List[Any]:
        """Append morphology-recalled skills after the canonical ``base`` list.

        ``base`` ordering is preserved verbatim — RRF promotes, never demotes.
        Skills surfaced only by the vector backend are appended in fused-rank
        order.
        """
        result = list(base)
        if not query or not str(query).strip():
            return result
        try:
            self.rebuild(all_summaries)
        except Exception as exc:  # noqa: BLE001
            logger.debug("[houdini] semantic rebuild failed: %s", exc)
            return result

        by_name = {name: s for s, name in ((s, _summary_name(s)) for s in all_summaries) if name is not None}
        present = {_summary_name(s) for s in result}
        for skill_id in self.recall(query):
            if skill_id in present or skill_id not in by_name:
                continue
            result.append(by_name[skill_id])
            present.add(skill_id)

        if limit is not None and limit >= 0:
            result = result[:limit]
        return result


def build_semantic_index() -> Optional[HoudiniSemanticIndex]:
    """Return a ready index when the feature is enabled, else ``None``."""
    if not resolve_semantic_index_enabled():
        return None
    return HoudiniSemanticIndex.build()
