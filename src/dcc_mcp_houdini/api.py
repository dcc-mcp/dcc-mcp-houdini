"""Houdini skill authoring helpers."""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


def houdini_success(message: str, **kwargs: Any) -> Dict[str, Any]:
    """Create a success response dictionary."""
    result = {"status": "success", "message": message}
    result.update(kwargs)
    return result


def houdini_error(message: str, **kwargs: Any) -> Dict[str, Any]:
    """Create an error response dictionary."""
    result = {"status": "error", "message": message}
    result.update(kwargs)
    return result


def houdini_from_exception(exc: Exception) -> Dict[str, Any]:
    """Create an error response from an exception."""
    return {
        "status": "error",
        "message": str(exc),
        "exception_type": type(exc).__name__,
    }


def with_houdini(func: Callable) -> Callable:
    """Decorator ensuring ``hou`` is available before calling *func*."""

    import functools

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Dict[str, Any]:
        try:
            import hou  # noqa: PLC0415

            _ = hou
        except ImportError:
            return houdini_error("hou not available — not running inside Houdini")

        try:
            return func(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            logger.error("Error in %s: %s", func.__name__, exc)
            return houdini_from_exception(exc)

    return wrapper


class MissingParamError(ValueError):
    """Raised when a required parameter is missing."""


def require_param(params: Dict[str, Any], param_name: str) -> Any:
    """Get a required parameter or raise :class:`MissingParamError`."""
    if param_name not in params or params[param_name] is None:
        raise MissingParamError(f"Missing required parameter: {param_name}")
    return params[param_name]


def get_param(params: Dict[str, Any], param_name: str, default: Any = None) -> Any:
    """Get an optional parameter with a default value."""
    return params.get(param_name, default)


def is_houdini_available() -> bool:
    """Return ``True`` when running inside Houdini."""
    try:
        import hou  # noqa: PLC0415

        _ = hou
        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Safe HOM wrappers — guard against SIGSEGV when accessing stale/deleted
# Houdini objects whose backing native memory has been freed.
# ---------------------------------------------------------------------------


def safe_parm_node(parm: Any) -> Optional[Any]:
    """Return ``parm.node()`` if the parameter still references a valid node.

    After a node is deleted, ``hou.Parm.node()`` can return a stale HOM
    object whose native pointer has been freed.  Calling ``parm.eval()`` on
    such an object triggers a native SIGSEGV that kills the Houdini process.

    This function wraps ``parm.node()`` in an exception guard and returns
    ``None`` when the backing node is no longer accessible, allowing callers
    to skip the evaluation rather than crash.
    """
    try:
        node = parm.node()
        if node is None:
            return None
        # Touch a cheap attribute to verify the node is still alive.
        _ = node.path()
        return node
    except Exception:  # noqa: BLE001
        return None


def safe_parm_eval(parm: Any, default: Any = None) -> Any:
    """Evaluate ``parm.eval()`` with a validity check against deleted nodes.

    Returns *default* when the parameter's owning node has been deleted or
    the evaluation itself raises an exception.  Does not prevent Python-side
    errors in ``eval()`` from propagating — only guards the common SIGSEGV
    path where the node was freed between job submission and execution.
    """
    if safe_parm_node(parm) is None:
        logger.debug("safe_parm_eval: skipped — parm node is invalid or deleted")
        return default
    try:
        return parm.eval()
    except Exception:  # noqa: BLE001
        logger.debug("safe_parm_eval: eval raised — returning default", exc_info=True)
        return default
