"""Regression coverage for the public flipbook job query route."""

from __future__ import annotations

import importlib.util
import json
import sys
import urllib.request
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

from dcc_mcp_core import McpHttpConfig, create_skill_server
from dcc_mcp_core.host import QueueDispatcher, StandaloneHost
from skill_loader import skill_script_import_context

_SKILLS_ROOT = Path(__file__).parent.parent / "src" / "dcc_mcp_houdini" / "skills"


def _load_script(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"issue_263_{path.stem}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    with skill_script_import_context(spec):
        spec.loader.exec_module(module)
    return module


def _post_mcp(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read())


def test_get_flipbook_job_query_returns_existing_job_without_pending_wrapper(monkeypatch, tmp_path: Path) -> None:
    """Polling an adapter job must not create a second core pending job."""
    monkeypatch.setenv("MCP_LOG_LEVEL", "WARN")
    monkeypatch.setenv("DCC_MCP_LOG_LEVEL", "WARN")
    monkeypatch.setenv("DCC_MCP_REGISTRY_DIR", str(tmp_path / "registry"))

    scripts = _SKILLS_ROOT / "houdini-render" / "scripts"
    flipbook = _load_script(scripts / "flipbook.py")
    import _flipbook_chunked as chunked

    existing_job_id = "flipbook-existing-job"
    chunked._flipbook_jobs[existing_job_id] = {
        "runner": SimpleNamespace(
            progress=SimpleNamespace(completed=1, total=2, last_step_at=123.0),
            outcome=None,
        ),
        "output_path": str(tmp_path / "frame.$F4.jpg"),
        "frame_range": [1.0, 2.0, 1.0],
    }

    calls: list[dict[str, Any]] = []

    def executor(script_path: str, params: dict[str, Any], **metadata: Any) -> dict[str, Any]:
        calls.append({"script_path": script_path, "params": params, **metadata})
        if Path(script_path).name == "get_flipbook_job.py":
            query = _load_script(Path(script_path))
            return query.main(**params)
        raise AssertionError(f"unexpected tool script: {script_path}")

    config = McpHttpConfig(port=0, server_name="houdini-flipbook-query-test")
    config.gateway_port = 0
    dispatcher = QueueDispatcher()
    host = StandaloneHost(dispatcher)
    server = create_skill_server("houdini", config)
    server.attach_dispatcher(dispatcher)
    server.set_in_process_executor(executor)
    assert server.discover(extra_paths=[str(_SKILLS_ROOT)]) >= 1
    assert "houdini_render__get_flipbook_job" in server.load_skill("houdini-render")

    host.start()
    handle = server.start()
    try:
        response = _post_mcp(
            handle.mcp_url(),
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "get_flipbook_job",
                    "arguments": {"job_id": existing_job_id},
                },
            },
        )
    finally:
        handle.shutdown()
        host.stop()
        chunked._flipbook_jobs.pop(existing_job_id, None)
        sys.modules.pop(flipbook.__name__, None)

    content = response["result"]["structuredContent"]
    assert content["context"]["job_id"] == existing_job_id
    assert content["context"]["state"] == "running"
    assert content["context"]["state"] != "pending"
    assert len(calls) == 1
    assert calls[0]["params"] == {"job_id": existing_job_id}
    assert calls[0]["execution"] == "sync"
