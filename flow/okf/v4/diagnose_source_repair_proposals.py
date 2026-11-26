"""Preflight existing Phase-B source-repair reviews without running the LLM.

Default mode is read-only. --quarantine-invalid moves ONLY invalid existing
proposal JSON files into a fresh backup directory, leaving valid checkpoints
byte-for-byte unchanged and preserving all task/Phase-A evidence.
"""
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from source_repair import (
    STATE, _check_proposal_identity, _existing_repair_markdown,
    _source_repair_markdown, prepare,
)


def validate_proposal(proposal: object, task: dict) -> None:
    """Enforce the schema and all applicable deterministic apply preconditions."""
    if not isinstance(proposal, dict):
        raise ValueError("Proposal must be a JSON object.")
    fields = {"id", "action", "title", "markdown", "knowledge_item_ids"}
    if set(proposal) != fields:
        raise ValueError(
            f"Proposal fields differ: missing={sorted(fields - set(proposal))}, "
            f"extra={sorted(set(proposal) - fields)}"
        )
    if not isinstance(proposal["id"], str) or len(proposal["id"]) < 3:
        raise ValueError("Proposal id must be a string of length >= 3.")
    if proposal["action"] not in ("keep", "rewrite"):
        raise ValueError("Action must be 'keep' or 'rewrite'.")
    title = proposal["title"]
    if not isinstance(title, str):
        raise ValueError("Title must be a string.")
    body = proposal["markdown"]
    if not isinstance(body, str) or len(body) > 250000:
        raise ValueError("Markdown must be a string of at most 250000 characters.")
    ids = proposal["knowledge_item_ids"]
    if not isinstance(ids, list) or not ids or any(
        not isinstance(x, str) or len(x) < 3 for x in ids
    ) or len(ids) != len(set(ids)):
        raise ValueError("Knowledge Item IDs must be unique nonempty strings.")
    _check_proposal_identity(proposal, task)

    if proposal["action"] == "keep":
        if body != "":
            raise ValueError("Keep proposal cannot carry revised Markdown.")
        if task["kind"] != "existing":
            raise ValueError("Missing concept must use action='rewrite'.")
        return
    if not body.startswith("---\n"):
        raise ValueError("Rewrite Markdown must begin with YAML frontmatter.")
    if task["kind"] == "existing":
        _existing_repair_markdown(task["title"], title, body)
    else:
        if not title.strip():
            raise ValueError("Missing concept needs a nonempty title.")
        _source_repair_markdown(title, body)


def inspect(workspace: Path) -> tuple[dict, list[tuple[Path, str]]]:
    tasks = prepare(workspace, skip_coverage=True)
    result: dict = {
        "checked": 0, "valid": 0, "invalid": 0, "missing": 0,
        "examples": [], "status": "ok",
    }
    invalid: list[tuple[Path, str]] = []
    proposal_root = workspace / STATE / "source-repair" / "proposals"
    for task in tasks["concepts"]:
        path = proposal_root / (task["key"] + ".json")
        result["checked"] += 1
        if not path.is_file():
            result["missing"] += 1
            if len(result["examples"]) < 20:
                result["examples"].append({
                    "task_key": task["key"], "issue": "missing proposal",
                })
            continue
        try:
            if path.is_symlink():
                raise ValueError("Proposal file must not be a symlink.")
            proposal = json.loads(path.read_text(encoding="utf-8"))
            validate_proposal(proposal, task)
        except (ValueError, UnicodeError) as exc:
            result["invalid"] += 1
            reason = str(exc)
            invalid.append((path, reason))
            if len(result["examples"]) < 20:
                result["examples"].append({
                    "task_key": task["key"], "issue": reason,
                })
        else:
            result["valid"] += 1
    if result["invalid"] or result["missing"]:
        result["status"] = "invalid"
    return result, invalid


def quarantine(workspace: Path, invalid: list[tuple[Path, str]]) -> Path | None:
    """Move invalid files to a new, collision-resistant folder; never overwrite."""
    if not invalid:
        return None
    root = workspace / STATE / "source-repair"
    # Verify all paths before moving any file, and refuse symlinked files.
    for src, _ in invalid:
        if src.is_symlink() or src.parent.resolve() != (root / "proposals").resolve():
            raise ValueError(f"Unsafe proposal path: {src}")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    dest = root / "quarantine" / stamp
    dest.mkdir(parents=True, exist_ok=False)
    records = []
    for src, reason in invalid:
        target = dest / src.name
        if target.exists():
            raise FileExistsError(target)
        shutil.move(str(src), str(target))
        records.append({
            "original": src.relative_to(workspace).as_posix(),
            "backup": target.relative_to(workspace).as_posix(),
            "reason": reason,
        })
    (dest / "manifest.json").write_text(
        json.dumps({"files": records}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return dest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--quarantine-invalid", action="store_true",
        help="Move ONLY invalid, existing proposals into a timestamped backup.",
    )
    args = parser.parse_args()
    workspace = Path.cwd().resolve()
    report, invalid = inspect(workspace)
    if args.quarantine_invalid:
        backup = quarantine(workspace, invalid)
        report["quarantine"] = str(backup) if backup else None
        report["moved"] = len(invalid)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["status"] != "ok" and not args.quarantine_invalid:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
