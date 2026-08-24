"""Agent-first installer entry point for Houdini."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional, Sequence

from dcc_mcp_houdini._installer import COMMAND, run_lifecycle


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=COMMAND)
    parser.add_argument("verb", choices=("install", "status", "verify", "uninstall", "upgrade"))
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--dcc-path")
    parser.add_argument("--python", dest="python_path")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run the Houdini lifecycle command."""
    args = _parser().parse_args(argv)
    outcome = run_lifecycle(
        args.verb,
        dcc_path=args.dcc_path,
        python_path=args.python_path,
        yes=args.yes,
        dry_run=args.dry_run,
    )
    if args.as_json:
        print(json.dumps(outcome.result, sort_keys=True))
    else:
        print("Houdini {}: {}".format(args.verb, outcome.result["status"]))
    return outcome.exit_code


if __name__ == "__main__":
    sys.exit(main())
