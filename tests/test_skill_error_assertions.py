"""Compatibility regressions for structured Skill exception assertions."""

from __future__ import annotations

from skill_error_assertions import skill_error_detail


def test_skill_error_detail_reads_legacy_error_repr() -> None:
    result = {
        "success": False,
        "error": "ValueError('matching topology required')",
        "context": {"error_type": "ValueError"},
    }

    assert skill_error_detail(result) == "ValueError('matching topology required')"


def test_skill_error_detail_prefers_core_020_metadata_message() -> None:
    result = {
        "success": False,
        "error": "ValueError",
        "_meta": {
            "dcc.error": {
                "type": "ValueError",
                "message": "matching topology required",
            }
        },
    }

    assert skill_error_detail(result) == "matching topology required"
