"""Run the checkpoint-aware OKF Flow, then publish named concept Markdown.

The runner remains generic. Publication happens only after the Flow exits
successfully. An existing completed Flow may be reused with --skip-flow.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys
import tomllib

from publish_named_okf import main as publish_main


FLOW = Path("flow/okf/flow_okf_from_doctrine_batched/flow.toml")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path("."))
    parser.add_argument("--skip-flow", action="store_true",
                        help="Publish an already completed OKF Flow without rerunning it.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preflight publication, do not update the published tree.")
    parser.add_argument("--destination-root", default="okf-batched-published-v3")
    args = parser.parse_args(argv)
    workspace = args.workspace.expanduser().resolve()
    flow = workspace / FLOW
    if not flow.is_file():
        parser.error("OKF flow.toml is missing from the workspace.")
    config = tomllib.loads(flow.read_text(encoding="utf-8"))
    source_root = config.get("vars", {}).get("okf_root")
    if not isinstance(source_root, str) or not source_root:
        parser.error("Missing [vars].okf_root in the OKF Flow.")

    if not args.skip_flow:
        command = [
            "cli-agent-flow", "run", FLOW.as_posix(), "--workspace", str(workspace),
        ]
        try:
            status = subprocess.run(command, cwd=workspace, check=False).returncode
        except FileNotFoundError:
            parser.error("cli-agent-flow is not installed or not on PATH.")
        if status != 0:
            print("Flow did not complete successfully; publication skipped.",
                  file=sys.stderr)
            return status

    flags = [
        "--workspace", str(workspace),
        "--source-root", source_root,
        "--destination-root", args.destination_root,
    ]
    if not args.dry_run:
        flags.append("--apply")
    return publish_main(flags)


if __name__ == "__main__":
    raise SystemExit(main())
