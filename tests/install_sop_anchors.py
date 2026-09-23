"""Measured byte identity of the Core Install SOP schema, keyed by Core release.

Core republishes the Install SOP schema artifact, so its byte identity is a property of the
Core release rather than a constant of the contract. A single hard-coded size/digest pair
therefore breaks as soon as Core ships a new revision under the same revision id.

Callers verify the artifact the installed Core actually serves against the row selected by the
installed Core version. A Core release newer than `CORE_SCHEMA_ANCHOR_MEASURED_THROUGH` has no
measured row and is accepted without a pinned digest, so a new Core release can never fail the
suite; the observed bytes are still reported so the release can be measured later.

This module is stdlib-only and must stay importable on Python 3.7 (the floor declared in
pyproject.toml). In particular it must not use `importlib.metadata`, which is 3.8+; the Core
version is read from `dcc_mcp_core.__version__` instead.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Mapping, NamedTuple, Optional, Tuple


class CoreSchemaAnchor(NamedTuple):
    """Measured byte identity of one published revision of the Core Install SOP schema."""

    size: int
    sha256: str


# Key every measured revision by the first Core release that shipped it and append new rows;
# editing an existing row would silently re-pin a digest that was already published.
#
# Rows whose floor is above `CORE_SCHEMA_ANCHOR_MEASURED_THROUGH` are staged: the bytes are
# recorded as soon as they are known, but the row only goes live once that Core release is
# published and `CORE_SCHEMA_ANCHOR_MEASURED_THROUGH` is raised to it. The `0.20.34` row is the
# `adapter-install-sop-v2` artifact Core `main` already carries.
CORE_SCHEMA_ANCHORS: Tuple[Tuple[Tuple[int, int, int], CoreSchemaAnchor], ...] = (
    ((0, 20, 14), CoreSchemaAnchor(4261, "3ca25788439917b4d4c0617230a762f9797756b5b54f45c8c4149f975b90f904")),
    ((0, 20, 30), CoreSchemaAnchor(4899, "2b3a8a101384a5163c7569c4a2b0de6586c672c5ee291735f94334a33b7d37a0")),
    ((0, 20, 34), CoreSchemaAnchor(4899, "daa5840e07c956d7c9269e5709d6993a3988b905f986c06e7c4c02f5023e9422")),
)

# Highest Core release whose schema bytes were measured into CORE_SCHEMA_ANCHORS.
CORE_SCHEMA_ANCHOR_MEASURED_THROUGH = "0.20.33"


def version_tuple(value: str) -> Optional[Tuple[int, int, int]]:
    """Parse a bounded `major[.minor[.patch]]` release version, or return None."""
    if not isinstance(value, str):
        return None
    parts = value.strip().split(".")
    if not 1 <= len(parts) <= 3:
        return None
    parsed = []
    for part in parts:
        if not (part.isascii() and part.isdigit()):
            return None
        parsed.append(int(part))
    while len(parsed) < 3:
        parsed.append(0)
    return (parsed[0], parsed[1], parsed[2])


def core_schema_anchor(core_version: str) -> Optional[CoreSchemaAnchor]:
    """Return the measured schema identity for a Core version, or None when unmeasured.

    Returns `None` for an unparseable version and for a version newer than
    `CORE_SCHEMA_ANCHOR_MEASURED_THROUGH`. That is the forward-compatible path: the caller
    accepts the release and records what it observed instead of failing.
    """
    parsed = version_tuple(core_version)
    if parsed is None:
        return None
    measured_through = version_tuple(CORE_SCHEMA_ANCHOR_MEASURED_THROUGH)
    if measured_through is not None and parsed > measured_through:
        return None
    anchor: Optional[CoreSchemaAnchor] = None
    for floor, candidate in CORE_SCHEMA_ANCHORS:
        if parsed >= floor:
            anchor = candidate
    return anchor


def installed_core_version() -> Optional[str]:
    """Return the installed Core version, or None when Core does not expose one.

    Reads `dcc_mcp_core.__version__` rather than `importlib.metadata.version`: this repository
    supports Python 3.7, and `importlib.metadata` only exists from 3.8 onwards.
    """
    try:
        import dcc_mcp_core
    except ImportError:  # pragma: no cover - Core is a hard dependency of this suite
        return None
    version = getattr(dcc_mcp_core, "__version__", None)
    return version if isinstance(version, str) else None


def core_schema_artifact(shared: Mapping[str, Any]) -> Optional[CoreSchemaAnchor]:
    """Measure the schema artifact Core actually serves for `shared`, or return None.

    Core names the artifact by revision (`adapter-install-sop-vN.schema.json`), so the file whose
    parsed document equals `shared` is the one Core loaded. Matching on content rather than on a
    fixed filename keeps this working when Core moves from the v1 artifact to v2.
    """
    from dcc_mcp_core.deployment import install_sop

    schemas = Path(install_sop.__file__).resolve().parent.parent / "schemas"
    for candidate in sorted(schemas.glob("adapter-install-sop-v*.schema.json")):
        raw = candidate.read_bytes()
        try:
            document = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            continue
        if document == dict(shared):
            return CoreSchemaAnchor(len(raw), hashlib.sha256(raw).hexdigest())
    return None


def core_schema_report(shared: Mapping[str, Any]) -> Dict[str, Any]:
    """Describe how the installed Core schema is pinned, including the observed bytes."""
    core_version = installed_core_version()
    anchor = core_schema_anchor(core_version or "")
    observed = core_schema_artifact(shared)
    return {
        "status": "pinned" if anchor is not None else "unpinned",
        "core_version": core_version,
        "measured_through": CORE_SCHEMA_ANCHOR_MEASURED_THROUGH,
        "size": anchor.size if anchor is not None else None,
        "sha256": anchor.sha256 if anchor is not None else None,
        "observed_size": observed.size if observed is not None else None,
        "observed_sha256": observed.sha256 if observed is not None else None,
    }
