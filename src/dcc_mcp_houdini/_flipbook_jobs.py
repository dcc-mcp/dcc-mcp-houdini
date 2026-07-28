"""Process-wide storage shared by flipbook tool entrypoints."""

from __future__ import annotations

from typing import Any

flipbook_jobs: dict[str, dict[str, Any]] = {}
