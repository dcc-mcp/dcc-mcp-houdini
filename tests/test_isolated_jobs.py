"""Durable isolated-job identity contracts."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from dcc_mcp_houdini import _isolated_jobs, _rop_jobs


def test_hex_and_dashed_uuid_resolve_the_same_job_and_process(tmp_path) -> None:
    with patch.object(_isolated_jobs.tempfile, "gettempdir", return_value=str(tmp_path)):
        status, _ = _isolated_jobs.create_job({"job_kind": "render"})
        compact_id = status["job_id"]
        dashed_id = str(uuid.UUID(hex=compact_id))
        process = MagicMock()
        process.poll.return_value = None
        _isolated_jobs._PROCESS_HANDLES[compact_id] = process
        try:
            compact = _rop_jobs.read_render_job(compact_id)
            dashed = _rop_jobs.read_render_job(dashed_id)
        finally:
            _isolated_jobs._PROCESS_HANDLES.pop(compact_id, None)

    assert _isolated_jobs._status_path(compact_id) == _isolated_jobs._status_path(dashed_id)
    assert compact["job_id"] == dashed["job_id"] == compact_id
    assert compact["owned_by_current_process"] is dashed["owned_by_current_process"] is True


@pytest.mark.parametrize("job_id", ("../status", "{00000000-0000-0000-0000-000000000000}", 7))
def test_job_id_normalization_rejects_noncanonical_identifiers(job_id) -> None:
    with pytest.raises(ValueError, match="32-character hex or canonical UUID"):
        _isolated_jobs._status_path(job_id)
