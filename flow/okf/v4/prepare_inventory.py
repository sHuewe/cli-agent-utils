"""Prepare bounded, one-concept-at-a-time LLM inventory tasks from repaired B-source.

Invoked as a generic Flow python_script step; exactly one JSON on stdout.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

from phase_b_contract import checked_b


from refine_b import inventory_tasks


def prepare(workspace: Path, root: str) -> dict:
    # Never let the inventory/quality pipeline bypass source conservation.
    _, catalog, _ = checked_b(workspace, root=root, stage="B-source")
    return inventory_tasks(catalog, root)

def main(argv: list[str] | None = None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path("."))
    parser.add_argument("--phase-a", default="okf-v4/b-source-repaired")
    args=parser.parse_args(argv)
    # Consume the standard JSON envelope even when no json_inputs are needed.
    json.load(sys.stdin)
    print(json.dumps(prepare(args.workspace.resolve(), args.phase_a), ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
