"""Temporary adapter-owned constants pending Core Install SOP release.

The canonical Draft 2020-12 schema is tracked and validated as an exact fixture
from dcc-mcp/dcc-mcp-core#2320. Runtime import of an unreleased Core API would
misrepresent the public dependency floor, so this module deliberately exposes
only the stable numeric values until that dependency is released.
"""

from __future__ import annotations

INSTALL_SOP_SCHEMA_VERSION = 1
INSTALL_EXIT_OK = 0
INSTALL_EXIT_PREFLIGHT = 10
INSTALL_EXIT_ACQUIRE = 20
INSTALL_EXIT_INSTALL = 30
INSTALL_EXIT_VERIFY = 40
INSTALL_EXIT_REQUIRES_RESTART = 50
INSTALL_SOP_CONTRACT_SOURCE = "temporary exact fixture from dcc-mcp/dcc-mcp-core#2320"

__all__ = [
    "INSTALL_EXIT_ACQUIRE",
    "INSTALL_EXIT_INSTALL",
    "INSTALL_EXIT_OK",
    "INSTALL_EXIT_PREFLIGHT",
    "INSTALL_EXIT_REQUIRES_RESTART",
    "INSTALL_EXIT_VERIFY",
    "INSTALL_SOP_SCHEMA_VERSION",
    "INSTALL_SOP_CONTRACT_SOURCE",
]
