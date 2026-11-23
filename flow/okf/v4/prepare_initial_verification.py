"""Build source-bound initial semantic verification tasks from B-merged."""
from __future__ import annotations

import json
from pathlib import Path
import sys

from phase_b_contract import checked_b
from refine_b import inventory_tasks


def prepare(workspace: Path) -> dict:
    _, catalog, _ = checked_b(workspace, root="okf-v4/b-merged", stage="B-merged")
    return inventory_tasks(catalog, "okf-v4/b-merged")


def main() -> None:
    json.load(sys.stdin)
    print(json.dumps(prepare(Path(".").resolve()), ensure_ascii=True))


if __name__ == "__main__":
    main()
