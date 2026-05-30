"""Standalone (hython batch) dispatcher."""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class HoudiniStandaloneDispatcher:
    """Dispatcher for headless ``hython`` contexts.

    All jobs execute directly on the calling thread — there is no UI
    event loop and no separate main thread.
    """

    def submit(
        self,
        action_name: str,
        payload: Optional[str] = None,
        affinity: str = "any",
        timeout_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Execute a job synchronously on the calling thread."""
        _ = timeout_ms
        return {
            "request_id": action_name,
            "affinity": affinity,
            "success": True,
            "output": payload,
            "error": None,
        }

    def submit_callable(
        self,
        request_id: str,
        task: Callable[[], Any],
        affinity: str = "any",
        timeout_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Execute a callable synchronously."""
        _ = timeout_ms
        try:
            output = task()
            return {
                "request_id": request_id,
                "affinity": affinity,
                "success": True,
                "output": output,
                "error": None,
            }
        except Exception as exc:
            return {
                "request_id": request_id,
                "affinity": affinity,
                "success": False,
                "output": None,
                "error": str(exc),
            }

    def submit_async_callable(
        self,
        request_id: str,
        task: Callable[[], Any],
        *,
        job_id: Optional[str] = None,
        progress_token: Optional[str] = None,
        on_complete: Optional[Callable[[Dict[str, Any]], None]] = None,
        affinity: str = "any",
        timeout_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Execute synchronously and invoke ``on_complete`` immediately."""
        result = self.submit_callable(request_id, task, affinity, timeout_ms)
        result["job_id"] = job_id
        result["status"] = "completed" if result.get("success") else "failed"
        if on_complete is not None:
            try:
                on_complete(result)
            except Exception as exc:
                logger.warning(
                    "HoudiniStandaloneDispatcher.submit_async_callable on_complete raised: %s",
                    exc,
                )
        return result

    def dispatch_callable(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Run *func* synchronously (standalone has no UI thread)."""
        return func(*args, **kwargs)

    def supported(self) -> List[str]:
        """Return supported affinity values."""
        return ["any", "main"]

    def capabilities(self) -> Dict[str, bool]:
        """Return capability flags."""
        return {
            "supports_main_thread": True,
            "supports_named_threads": False,
            "supports_any_thread": True,
            "supports_time_slicing": False,
        }
