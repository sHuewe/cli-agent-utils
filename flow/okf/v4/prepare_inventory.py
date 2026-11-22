"""Prepare bounded, one-concept-at-a-time LLM inventory tasks from Phase A.

Invoked as a generic Flow python_script step; exactly one JSON on stdout.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

from phase_a_contract import checked_phase_a


def prepare(workspace: Path, root: str) -> dict:
    _, catalog, _ = checked_phase_a(workspace, root)
    tasks = []
    seen = set()
    for concept in sorted(catalog["concepts"], key=lambda c: c["path"]):
        key = concept["id"].replace(":", "--")
        if not re.fullmatch(r"[a-z0-9_-]+", key) or key in seen:
            raise ValueError(f"Unsafe or duplicate inventory key: {key!r}")
        seen.add(key)
        tasks.append({
            "id": concept["id"],
            "key": key,
            "title": concept["title"],
            "path": root + "/" + concept["path"],
            "source": root + "/" + concept["source_path"],
            "knowledge_item_count": len(concept["knowledge_item_ids"]),
        })
    return {"schema": "okf.inventory-tasks.v1", "status": "ok",
            "count": len(tasks), "concepts": tasks}


def main(argv: list[str] | None = None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path("."))
    parser.add_argument("--phase-a", default="okf-v4/phase-a")
    args=parser.parse_args(argv)
    # Consume the standard JSON envelope even when no json_inputs are needed.
    json.load(sys.stdin)
    print(json.dumps(prepare(args.workspace.resolve(), args.phase_a), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
