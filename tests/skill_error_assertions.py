"""Assertions that span the Core 0.19 and 0.20 Skill error envelopes."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def skill_error_detail(result: Mapping[str, Any]) -> str:
    """Return bounded exception detail without changing the runtime contract."""
    metadata = result.get("_meta")
    if isinstance(metadata, Mapping):
        error_metadata = metadata.get("dcc.error")
        if isinstance(error_metadata, Mapping):
            message = error_metadata.get("message")
            if isinstance(message, str) and message:
                return message
    error = result.get("error")
    return str(error) if error is not None else ""
