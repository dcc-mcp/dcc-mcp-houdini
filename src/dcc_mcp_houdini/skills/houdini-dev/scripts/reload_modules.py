"""Hot-reload Python modules by prefix or explicit name without restarting."""

from __future__ import annotations

import importlib
import sys
from typing import List, Optional

from _dev_common import reload_by_prefix  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def reload_modules(
    prefix: Optional[str] = None,
    modules: Optional[List[str]] = None,
    reimport: bool = False,
) -> dict:
    """Purge modules matching *prefix* and/or reload explicit *modules*.

    With ``reimport=true`` the purged ``prefix`` is re-imported afterwards so
    callers immediately get the fresh module object.
    """
    try:
        if not prefix and not modules:
            return skill_error(
                "Nothing to reload",
                "Provide a prefix and/or an explicit modules list",
            )
        purged: List[str] = []
        reloaded: List[str] = []
        errors = {}

        if prefix:
            purged = reload_by_prefix(prefix)
            if reimport:
                try:
                    importlib.import_module(prefix)
                    reloaded.append(prefix)
                except Exception as exc:  # noqa: BLE001
                    errors[prefix] = str(exc)

        if modules:
            for name in modules:
                mod = sys.modules.get(name)
                try:
                    if mod is not None:
                        importlib.reload(mod)
                    else:
                        importlib.import_module(name)
                    reloaded.append(name)
                except Exception as exc:  # noqa: BLE001
                    errors[name] = str(exc)

        return skill_success(
            "Reloaded modules",
            purged=purged,
            reloaded=reloaded,
            errors=errors,
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to reload modules")


@skill_entry
def main(**kwargs) -> dict:
    return reload_modules(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
