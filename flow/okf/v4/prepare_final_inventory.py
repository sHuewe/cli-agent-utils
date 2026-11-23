"""Make content-bound final inventory tasks from validated merged concepts."""
from __future__ import annotations

import json
from pathlib import Path
import sys

from phase_b_contract import checked_b
from refine_b import inventory_tasks


def prepare(workspace: Path) -> dict:
    _, catalog, _ = checked_b(workspace, root="okf-v4/b-repair-2", stage="B-repair-2")
    return inventory_tasks(catalog, "okf-v4/b-repair-2")


def main() -> None:
    json.load(sys.stdin)
    print(json.dumps(prepare(Path(".").resolve()), ensure_ascii=False))


if __name__ == "__main__":
    main()
