"""Houdini skill authoring helpers."""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict

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
