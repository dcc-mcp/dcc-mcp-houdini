"""Environment variable helpers for dcc-mcp-houdini."""

import os
from pathlib import Path
from typing import Any, Optional

# Re-export core helpers for convenience
from dcc_mcp_core.environment import (  # noqa: F401
    resolve_bool,
    resolve_int,
    resolve_path,
    resolve_str,
)


def get_extra_skill_paths() -> list[str]:
    """Read DCC_MCP_HOUDINI_SKILL_PATHS and DCC_MCP_SKILL_PATHS."""
    sep = ";" if os.sep == "\\" else ":"
    paths: list[str] = []

    for env_var in ("DCC_MCP_HOUDINI_SKILL_PATHS", "DCC_MCP_SKILL_PATHS"):
        raw = os.environ.get(env_var, "")
        if raw:
            for p in raw.split(sep):
                p = p.strip()
                if p:
                    paths.append(p)

    return paths


def resolve_enable_gateway_failover(value: Optional[bool]) -> bool:
    """Resolve enable_gateway_failover with env var fallback."""
    if value is not None:
        return value
    return resolve_bool("DCC_MCP_HOUDINI_ENABLE_GATEWAY_FAILOVER", default=True)


def resolve_metrics_enabled(value: Optional[bool]) -> bool:
    """Resolve metrics_enabled with env var fallback."""
    if value is not None:
        return value
    return resolve_bool("DCC_MCP_HOUDINI_METRICS_ENABLED", default=False)


def resolve_job_storage(value: Optional[str]) -> Optional[str]:
    """Resolve job_storage_path with env var fallback."""
    if value is not None:
        return value
    return resolve_path("DCC_MCP_HOUDINI_JOB_STORAGE_PATH", default=None)


def resolve_enable_workflows(value: Optional[bool]) -> bool:
    """Resolve enable_workflows with env var fallback."""
    if value is not None:
        return value
    return resolve_bool("DCC_MCP_HOUDINI_ENABLE_WORKFLOWS", default=False)
