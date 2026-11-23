"""Independently audit immutable source snapshots in bounded, line-anchored chunks.

The audit is advisory until every chunk has an LLM verdict. Only verified
source quotations can produce new Knowledge Items. Original V3 scan records
and immutable Phase A remain unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

from migrate_v3 import safe_path
from phase_a_contract import checked_phase_a

PHASE_A = "okf-v4/phase-a"
STATE = "okf-v4/state-b"
MAX_CHARS = 2600
MAX_LINES = 18
MAX_ITEMS_CHARS = 9000


def canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def _chunks(text: str) -> list[list[dict]]:
    """Cover every source character, including very long individual lines."""
    segments = []
    for number, line in enumerate(text.splitlines(keepends=True), 1):
        # String splitting retains the full source; a long line is processed
        # as successive windows with the same original evidence line.
        line = line.rstrip("\r\n")
        if not line:
            segments.append({"line": number, "text": ""})
        for i in range(0, len(line), 1500):
            segments.append({"line": number, "text": line[i:i + 1500]})
    if not segments and text == "":
        raise ValueError("Empty source document cannot be audited.")
    groups = []
    current = []
    size = 0
    for segment in segments:
        length = len(segment["text"]) + 28
        if current and (size + length > MAX_CHARS or len(current) >= MAX_LINES):
            groups.append(current)
            current = []
            size = 0
        current.append(segment)
        size += length
    if current:
        groups.append(current)
    return groups


def prepare(workspace: Path, phase_a: str = PHASE_A) -> dict:
    _, catalog, base = checked_phase_a(workspace, phase_a)
    result = []
    for doc in sorted(catalog["documents"], key=lambda d: d["id"]):
        source = safe_path(workspace, phase_a + "/" + doc["source_snapshot"])
        lines = source.read_text(encoding="utf-8")
        chunks = _chunks(lines)
        source_items = doc["source_knowledge_items"]
        for index, chunk in enumerate(chunks):
            first = chunk[0]["line"]
            last = chunk[-1]["line"]
            related = []
            for item in source_items:
                if any(
                    ev.get("start_line", 0) <= last and ev.get("end_line", 0) >= first
                    for ev in item["evidence_ranges"]
                ):
                    related.append({
                        "id": item["id"],
                        "description": item.get("description", ""),
                        "normative": item.get("normative", False),
                    })
            if len(canonical(related)) > MAX_ITEMS_CHARS:
                raise ValueError(
                    f"Too many overlapping Knowledge Items in source window "
                    f"{doc['id']}:{first}-{last}; reduce the coverage chunk size."
                )
            item = {
                "document_id": doc["id"],
                "source": phase_a + "/" + doc["source_snapshot"],
                "source_original_path": doc["original_path"],
                "source_sha256": doc["sha256"],
                "chunk_index": index,
                "first_line": first,
                "last_line": last,
                "lines": chunk,
                "known_items": related,
            }
            item["key"] = "audit-" + digest(item)[:24]
            result.append(item)
    if len({x["key"] for x in result}) != len(result):
        raise ValueError("Source audit task hash collision.")
    return {
        "schema": "okf.source-coverage-tasks.v1", "status": "ok",
        "count": len(result), "chunks": result,
    }


def additions(workspace: Path, *, required: bool = False,
              phase_a: str = PHASE_A, state: str = STATE) -> list[dict]:
    """Fail closed unless all source chunks have valid, line-bound decisions.

    Optional mode retains compatibility with existing direct library tests
    that produce B-source without running the command-line B flow.
    """
    tasks_path = workspace / state / "coverage" / "tasks.json"
    if not tasks_path.is_file():
        if required:
            raise ValueError("Missing full-source coverage task ledger.")
        return []
    tasks = json.loads(safe_path(
        workspace, state + "/coverage/tasks.json"
    ).read_text(encoding="utf-8"))
    if tasks != prepare(workspace, phase_a):
        raise ValueError("Stale, partial or modified source coverage tasks.")
    found = {}
    for task in tasks["chunks"]:
        result = json.loads(safe_path(
            workspace, state + "/coverage/reviews/" + task["key"] + ".json"
        ).read_text(encoding="utf-8"))
        if (not isinstance(result, dict)
                or result.get("key") != task["key"]
                or result.get("status") not in ("ok", "missing", "overflow")
                or not isinstance(result.get("missing"), list)
                or len(result["missing"]) > 16
                or (result["status"] == "ok" and result["missing"])
                or (result["status"] == "missing" and not result["missing"])):
            raise ValueError(f"Invalid independent source coverage review: {task['key']}")
        if result["status"] == "overflow":
            raise ValueError(
                f"Source coverage chunk contains more than 16 missing "
                f"assertions: {task['key']}. Reduce MAX_CHARS/MAX_LINES "
                "and regenerate source coverage tasks."
            )
        for missing in result["missing"]:
            if not isinstance(missing, dict):
                raise ValueError("Malformed missing source assertion.")
            quote = missing.get("source_quote")
            statement = missing.get("statement")
            line_number = missing.get("line")
            normative = missing.get("normative")
            if (not isinstance(quote, str) or not 5 <= len(quote) <= 600
                    or not isinstance(statement, str) or not 12 <= len(statement) <= 700
                    or type(line_number) is not int
                    or type(normative) is not bool):
                raise ValueError(f"Malformed source coverage finding: {task['key']}")
            if not any(
                line["line"] == line_number and quote in line["text"]
                for line in task["lines"]
            ):
                raise ValueError(
                    f"Source quote absent from claimed evidence line: {task['key']}"
                )
            signature = digest({
                "document": task["document_id"],
                "line": line_number, "quote": quote,
            })[:20]
            identity = task["document_id"] + ":audit-" + signature
            item = {
                "id": identity, "description": statement,
                "normative": normative,
                "evidence_ranges": [{
                    "doctrine": task["source_original_path"],
                    "start_line": line_number, "end_line": line_number,
                }],
            }
            if identity in found and found[identity] != item:
                raise ValueError("Conflicting repeated source coverage finding.")
            found[identity] = item
    _, catalog, _ = checked_phase_a(workspace, phase_a)
    original_ids = {
        x["id"] for doc in catalog["documents"]
        for x in doc["source_knowledge_items"]
    }
    if original_ids.intersection(found):
        raise ValueError("Source audit attempted to replace an existing item.")
    return [found[k] for k in sorted(found)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("prepare", "check"), required=True)
    args = parser.parse_args()
    json.load(sys.stdin)
    workspace = Path(".").resolve()
    if args.mode == "prepare":
        output = prepare(workspace)
    else:
        found = additions(workspace, required=True)
        output = {
            "status": "ok", "source_coverage_complete": True,
            "new_knowledge_item_count": len(found),
            "new_knowledge_item_ids": [x["id"] for x in found],
        }
    # ASCII-only transport for Windows cp1252 subprocess pipes. File content
    # and the parsed JSON values remain Unicode/UTF-8.
    print(json.dumps(output, ensure_ascii=True))


if __name__ == "__main__":
    main()
