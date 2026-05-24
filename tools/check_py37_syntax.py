"""Check that shipped Python sources parse with Python 3.7 grammar."""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path
from typing import Iterable, List, Optional


def iter_python_files(paths: Iterable[Path]) -> Iterable[Path]:
    for path in paths:
        if path.is_file() and path.suffix == ".py":
            yield path
        elif path.is_dir():
            for child in path.rglob("*.py"):
                if "__pycache__" not in child.parts:
                    yield child


def check(paths: Iterable[Path]) -> List[str]:
    errors: List[str] = []
    for path in sorted(set(iter_python_files(paths))):
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path), feature_version=(3, 7))
        except SyntaxError as exc:
            errors.append("{}:{}:{}: {}".format(path, exc.lineno, exc.offset, exc.msg))
    return errors


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path, default=[Path("src"), Path("tests"), Path("tools")])
    args = parser.parse_args(argv)
    errors = check(args.paths)
    if errors:
        print("Python 3.7 syntax errors:")
        for error in errors:
            print("  - {}".format(error))
        return 1
    print("Python 3.7 syntax check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
