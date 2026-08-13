"""Contract tests for the bounded Houdini Asset Sync skill."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).parents[1]
_SKILL = _ROOT / "src" / "dcc_mcp_houdini" / "skills" / "houdini-asset-sync"


def _module():
    spec = importlib.util.spec_from_file_location("houdini_asset_sync_test", _SKILL / "scripts" / "asset_sync.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_source_name_is_confined_to_operator_root(tmp_path: Path) -> None:
    module = _module()
    assert module._safe_relative(tmp_path, "exports/bee.usdc") == tmp_path / "exports" / "bee.usdc"
    with pytest.raises(ValueError, match="safe relative"):
        module._safe_relative(tmp_path, "../secret.usdc")
    with pytest.raises(ValueError, match="safe relative"):
        module._safe_relative(tmp_path, str(tmp_path / "absolute.usdc"))


def test_public_schemas_are_bounded_and_path_free() -> None:
    tools = yaml.safe_load((_SKILL / "tools.yaml").read_text(encoding="utf-8"))["tools"]
    by_name = {tool["name"]: tool for tool in tools}
    assert set(by_name) == {"publish_usd_revision", "read_asset_head", "reference_usd_revision"}
    for tool in tools:
        assert tool["input_schema"]["additionalProperties"] is False
    publish_properties = by_name["publish_usd_revision"]["input_schema"]["properties"]
    assert "source_name" in publish_properties
    assert "source_path" not in publish_properties
    assert "store_root" not in publish_properties
