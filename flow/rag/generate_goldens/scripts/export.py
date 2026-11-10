#!/usr/bin/env python3
"""Validate reviewed multi-document questions and export reusable RAG goldens."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

from prepare import secure_path

ID = re.compile(r"p[0-9a-f]{16}")
MAX_JSON = 256_000


def read_json(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_JSON:
        raise ValueError(f"Missing, linked or oversized JSON file: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def valid_golden(pack: dict, draft: dict, review: dict) -> dict | None:
    if draft.get("status") == "rejected":
        return None
    if draft.get("status") != "ok" or review.get("status") != "accepted":
        return None
    pack_id = pack["pack_id"]
    if draft.get("pack_id") != pack_id or review.get("pack_id") != pack_id:
        return None
    checks = review.get("checks")
    if not isinstance(checks, dict) or set(checks) != {
        "grounded", "both_documents_necessary", "unambiguous", "no_source_leakage"
    } or not all(value is True for value in checks.values()):
        return None
    question, answer = draft.get("question"), draft.get("expected_output")
    if (not isinstance(question, str) or not 10 <= len(question.strip()) <= 500
            or not isinstance(answer, str) or not 10 <= len(answer.strip()) <= 1800):
        return None
    if draft.get("category") != "multi_document":
        return None
    sources = pack.get("sources")
    if (not isinstance(sources, list) or len(sources) != 2
            or sources[0]["path"] == sources[1]["path"]):
        return None
    indexed = {s["id"]: s for s in sources}
    if set(indexed) != {"s1", "s2"}:
        return None
    citations = draft.get("evidence")
    if not isinstance(citations, list) or not 2 <= len(citations) <= 4:
        return None
    used = set()
    clean_citations = []
    for citation in citations:
        if not isinstance(citation, dict) or citation.get("source_id") not in indexed:
            return None
        s = indexed[citation["source_id"]]
        quote, support = citation.get("quote"), citation.get("supports")
        lo, hi = citation.get("start_line"), citation.get("end_line")
        if (not isinstance(quote, str) or not 4 <= len(quote) <= 400
                or not isinstance(support, str) or not support or len(support) > 400
                or type(lo) is not int or type(hi) is not int
                or not s["start_line"] <= lo <= hi <= s["end_line"]):
            return None
        # A quote must be found in the specified lines, not merely somewhere
        # in the same document or nearby window.
        lines = s["text"].splitlines(keepends=True)
        offset_lo, offset_hi = lo - s["start_line"], hi - s["start_line"] + 1
        if quote not in "".join(lines[offset_lo:offset_hi]):
            return None
        used.add(citation["source_id"])
        clean_citations.append({
            "source_id": citation["source_id"], "path": s["path"],
            "start_line": lo, "end_line": hi, "quote": quote, "supports": support,
        })
    if used != {"s1", "s2"}:
        return None
    necessity = draft.get("necessity")
    if not isinstance(necessity, dict) or not all(
        isinstance(necessity.get(key), str) and necessity[key].strip()
        for key in ("without_s1", "without_s2")
    ):
        return None
    return {
        "id": pack_id, "input": question.strip(),
        "expected_output": answer.strip(), "category": "multi_document",
        "difficulty": draft.get("difficulty", "hard"),
        "evidence": clean_citations, "necessity": necessity,
        "sources": [
            {"path": s["path"], "sha256": s["sha256"],
             "start_line": s["start_line"], "end_line": s["end_line"]}
            for s in sources
        ],
        "review": {"status": "accepted", "reason": review.get("reason", "")},
    }


def export(workspace: Path, output_dir: str) -> dict:
    root = secure_path(workspace, output_dir)
    manifest = read_json(root / "manifest.json")
    source_hashes = manifest.get("sources")
    if not isinstance(source_hashes, dict) or len(source_hashes) < 2:
        raise ValueError("Invalid source manifest")
    for path, expected in source_hashes.items():
        source = secure_path(workspace, path)
        if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != expected:
            raise ValueError(f"Stale source since preparation: {path}")
    ids = manifest.get("pack_ids")
    if not isinstance(ids, list) or len(ids) != len(set(ids)) or not ids:
        raise ValueError("Empty or duplicate pack manifest")
    goldens: list[dict] = []
    counts = {"reviewed": 0, "rejected": 0, "missing": 0}
    for name in ids:
        if not isinstance(name, str) or not re.fullmatch(r"pack-p[0-9a-f]{16}\.json", name):
            raise ValueError(f"Invalid pack path: {name}")
        pack = read_json(root / "packs" / name)
        pack_id = name[len("pack-"):-len(".json")]
        if pack.get("pack_id") != pack_id or not ID.fullmatch(pack_id):
            raise ValueError(f"Pack identity mismatch: {name}")
        # Generated paths match cli-agent inventory stable_slugs.
        # Use the same deterministic scheme as the flow inventory operation.
        rel = f"{output_dir}/packs/{name}"
        prefix = re.sub(r"[^a-z0-9]+", "-", rel.casefold()).strip("-")[:60].strip("-")
        slug = f"{prefix or 'source'}-{hashlib.sha256(rel.encode('utf-8')).hexdigest()[:16]}"
        draft_path = root / "state" / f"draft-{slug}.json"
        review_path = root / "state" / f"review-{slug}.json"
        if not draft_path.is_file() or not review_path.is_file():
            counts["missing"] += 1
            continue
        draft, review = read_json(draft_path), read_json(review_path)
        counts["reviewed"] += 1
        candidate = valid_golden(pack, draft, review)
        if candidate is None:
            counts["rejected"] += 1
        else:
            goldens.append(candidate)
    unique: dict[str, dict] = {}
    for golden in goldens:
        key = re.sub(r"\s+", " ", golden["input"].casefold()).strip()
        unique.setdefault(key, golden)
    result = sorted(unique.values(), key=lambda x: x["id"])
    # Context is REFERENCE EVIDENCE, not retrieval_context from tested RAG.
    deepeval = [{
        "input": g["input"], "expected_output": g["expected_output"],
        "context": [c["quote"] for c in g["evidence"]],
    } for g in result]
    for filename, value in (
        ("goldens.json", result),
        ("deepeval-goldens.json", deepeval),
    ):
        (root / filename).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                                     encoding="utf-8")
    return {"accepted": len(result), "duplicates": len(goldens) - len(result),
            **counts, "total_packs": len(ids)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--output-dir", default="rag-goldens")
    args = parser.parse_args()
    workspace = Path(args.workspace).resolve(strict=True)
    print(json.dumps(export(workspace, args.output_dir), indent=2))


if __name__ == "__main__":
    main()
