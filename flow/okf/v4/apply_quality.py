"""Generic Python Flow step: apply and validate quality proposals."""
import json
from pathlib import Path
import sys

from refine_b import apply_quality


def main() -> None:
    envelope = json.load(sys.stdin)
    result = apply_quality(
        Path(".").resolve(), phase_a="okf-v4/b-source-repaired",
        state="okf-v4/state-b", tasks=envelope["inputs"]["tasks"],
        destination="okf-v4/b-reviewed",
    )
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
