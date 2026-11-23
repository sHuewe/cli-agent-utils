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
MAX_COMPARE_ITEM_BYTES = 7000
MAX_COMPARE_CLAIM_BYTES = 2200

# V2 introduces independent extraction and batched cross-checks. New task
# hashes ensure V1 cached verdicts cannot be mistaken for V2 reviews.
TASK_SCHEMA = "okf.source-coverage-tasks.v2"
COMPARE_SCHEMA = "okf.source-coverage-comparison-tasks.v1"


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
        for index, chunk in enumerate(chunks):
            first = chunk[0]["line"]
            last = chunk[-1]["line"]
            item = {
                "document_id": doc["id"],
                "source": phase_a + "/" + doc["source_snapshot"],
                "source_original_path": doc["original_path"],
                "source_sha256": doc["sha256"],
                "chunk_index": index,
                "first_line": first,
                "last_line": last,
                "lines": chunk,
            }
            item["key"] = "audit-v2-" + digest(item)[:24]
            result.append(item)
    if len({x["key"] for x in result}) != len(result):
        raise ValueError("Source audit task hash collision.")
    return {
        "schema": TASK_SCHEMA, "status": "ok",
        "count": len(result), "chunks": result,
    }


def _reviewed_claims(workspace: Path, phase_a: str, state: str) -> tuple[dict, list[dict]]:
    tasks = json.loads(safe_path(
        workspace, state + "/coverage/tasks.json"
    ).read_text(encoding="utf-8"))
    if tasks != prepare(workspace, phase_a):
        raise ValueError("Stale, partial or modified source coverage tasks.")
    claims = []
    for task in tasks["chunks"]:
        result = json.loads(safe_path(
            workspace, state + "/coverage/reviews/" + task["key"] + ".json"
        ).read_text(encoding="utf-8"))
        if (not isinstance(result, dict) or result.get("key") != task["key"]
                or result.get("status") not in ("ok", "claims", "overflow")
                or not isinstance(result.get("missing"), list)
                or len(result["missing"]) > 16
                or (result["status"] == "ok" and result["missing"])
                or (result["status"] == "claims" and not result["missing"])
                or (result["status"] == "overflow" and result["missing"])):
            raise ValueError(f"Invalid independent source claim extraction: {task['key']}")
        if result["status"] == "overflow":
            raise ValueError(
                f"Source coverage chunk contains more than 16 assertions: "
                f"{task['key']}. Reduce MAX_CHARS/MAX_LINES and regenerate tasks."
            )
        for claim in result["missing"]:
            if not isinstance(claim, dict):
                raise ValueError("Malformed extracted source claim.")
            quote, statement = claim.get("source_quote"), claim.get("statement")
            number, normative = claim.get("line"), claim.get("normative")
            if (not isinstance(quote, str) or not 5 <= len(quote) <= 600
                    or not isinstance(statement, str)
                    or not 12 <= len(statement) <= 700
                    or type(number) is not int or type(normative) is not bool):
                raise ValueError(f"Malformed source claim: {task['key']}")
            if not any(
                line["line"] == number and quote in line["text"]
                for line in task["lines"]
            ):
                raise ValueError(
                    f"Source quote absent from claimed evidence line: {task['key']}"
                )
            ident = task["document_id"] + ":audit-" + digest({
                "document": task["document_id"],
                "line": number, "quote": quote,
            })[:20]
            claims.append({
                "id": ident, "document_id": task["document_id"],
                "chunk_key": task["key"], "line": number,
                "source_quote": quote, "statement": statement,
                "normative": normative,
                "source_original_path": task["source_original_path"],
            })
    by_id = {}
    for claim in claims:
        ident = claim["id"]
        if ident in by_id and by_id[ident] != {
                k: v for k, v in claim.items() if k != "chunk_key"}:
            previous = {k: v for k, v in by_id[ident].items() if k != "chunk_key"}
            current = {k: v for k, v in claim.items() if k != "chunk_key"}
            if previous != current:
                raise ValueError(f"Conflicting duplicate extracted source claim: {ident}")
        by_id[ident] = claim
    return tasks, [by_id[k] for k in sorted(by_id)]


def _batches(entries: list[dict], limit: int) -> list[list[dict]]:
    """Pack complete entries, never truncate or silently drop one."""
    result, chunk, size = [], [], 0
    for entry in entries:
        length = len(canonical(entry)) + 12
        if length > limit:
            raise ValueError(
                f"One coverage comparison entry is too large ({length} bytes). "
                "Inspect this Knowledge Item or extracted claim individually."
            )
        if chunk and size + length > limit:
            result.append(chunk)
            chunk, size = [], 0
        chunk.append(entry)
        size += length
    if chunk:
        result.append(chunk)
    return result


def compare_prepare(workspace: Path, *, phase_a: str = PHASE_A,
                    state: str = STATE) -> dict:
    """Bound each LLM call without discarding overlapping Knowledge Items."""
    _, claims = _reviewed_claims(workspace, phase_a, state)
    _, catalog, _ = checked_phase_a(workspace, phase_a)
    by_doc = {d["id"]: d for d in catalog["documents"]}
    by_chunk = {}
    for claim in claims:
        by_chunk.setdefault(claim["chunk_key"], []).append(claim)
    chunks = {task["key"]: task for task in prepare(workspace, phase_a)["chunks"]}
    comparisons = []
    for chunk_key, candidates in sorted(by_chunk.items()):
        window = chunks[chunk_key]
        doc = by_doc[window["document_id"]]
        known = []
        for item in doc["source_knowledge_items"]:
            if any(
                evidence.get("start_line", 0) <= window["last_line"]
                and evidence.get("end_line", 0) >= window["first_line"]
                for evidence in item["evidence_ranges"]
            ):
                known.append({
                    "id": item["id"],
                    "description": item.get("description", ""),
                    "normative": item.get("normative", False),
                })
        # An empty overlap is legitimate. The extracted claim will be
        # uncovered unless a Knowledge Item can actually be compared.
        claim_batches = _batches(candidates, MAX_COMPARE_CLAIM_BYTES)
        item_batches = _batches(known, MAX_COMPARE_ITEM_BYTES)
        for i, candidate_batch in enumerate(claim_batches):
            for j, item_batch in enumerate(item_batches):
                comparison = {
                    "document_id": doc["id"], "chunk_key": chunk_key,
                    "candidate_batch": i, "item_batch": j,
                    "claims": candidate_batch, "known_items": item_batch,
                }
                comparison["key"] = "compare-" + digest(comparison)[:24]
                comparisons.append(comparison)
    if len({t["key"] for t in comparisons}) != len(comparisons):
        raise ValueError("Duplicate comparison task identity.")
    return {
        "schema": COMPARE_SCHEMA, "status": "ok",
        "count": len(comparisons), "comparisons": comparisons,
    }


def additions(workspace: Path, *, required: bool = False,
              phase_a: str = PHASE_A, state: str = STATE) -> list[dict]:
    """Certify every comparison batch before creating any source claim."""
    tasks_path = workspace / state / "coverage" / "tasks.json"
    if not tasks_path.is_file():
        if required:
            raise ValueError("Missing full-source coverage task ledger.")
        return []
    _, claims = _reviewed_claims(workspace, phase_a, state)
    comparisons_path = workspace / state / "coverage" / "comparison-tasks.json"
    if not comparisons_path.is_file():
        raise ValueError("Missing source coverage comparison task ledger.")
    expected = compare_prepare(workspace, phase_a=phase_a, state=state)
    stored = json.loads(safe_path(
        workspace, state + "/coverage/comparison-tasks.json"
    ).read_text(encoding="utf-8"))
    if expected != stored:
        raise ValueError("Stale or modified coverage comparison task ledger.")
    covered = set()
    for task in expected["comparisons"]:
        verdict = json.loads(safe_path(
            workspace, state + "/coverage/comparisons/" + task["key"] + ".json"
        ).read_text(encoding="utf-8"))
        valid_ids = {claim["id"] for claim in task["claims"]}
        selected = verdict.get("covered_ids") if isinstance(verdict, dict) else None
        if (not isinstance(verdict, dict) or verdict.get("key") != task["key"]
                or not isinstance(selected, list) or len(set(selected)) != len(selected)
                or not all(isinstance(i, str) and i in valid_ids for i in selected)):
            raise ValueError(f"Invalid source comparison verdict: {task['key']}")
        covered.update(selected)
    _, catalog, _ = checked_phase_a(workspace, phase_a)
    original_ids = {
        item["id"] for doc in catalog["documents"]
        for item in doc["source_knowledge_items"]
    }
    result = []
    for claim in claims:
        if claim["id"] in covered:
            continue
        if claim["id"] in original_ids:
            raise ValueError("Source audit attempted to replace an existing item.")
        result.append({
            "id": claim["id"], "description": claim["statement"],
            "normative": claim["normative"],
            "source_quote": claim["source_quote"],
            "evidence_ranges": [{
                "doctrine": claim["source_original_path"],
                "start_line": claim["line"], "end_line": claim["line"],
            }],
        })
    return result

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("prepare", "compare-tasks", "check"), required=True)
    args = parser.parse_args()
    json.load(sys.stdin)
    workspace = Path(".").resolve()
    if args.mode == "prepare":
        output = prepare(workspace)
    elif args.mode == "compare-tasks":
        output = compare_prepare(workspace)
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
