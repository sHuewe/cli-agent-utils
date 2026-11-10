#!/usr/bin/env python3
"""Export reviewed multi-doctrine goldens without requiring any extra dependency.

Reads only the flow-generated registry/draft/review JSON and the cited original
Markdown sources. No retrieval is run; the tested RAG receives only question.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

MAX_JSON_BYTES = 4_000_000
# The registry-batches.json file holds up to 1000 independently bounded
# 24 KB batches. Its *aggregate* size can therefore legitimately exceed
# the ordinary single-result JSON cap. 32 MB accommodates the entire
# bounded manifest while still rejecting unexpectedly large inputs.
MAX_REGISTRY_MANIFEST_BYTES = 32_000_000
MAX_REGISTRY_BATCH_BYTES = 24_000
MAX_DOCUMENT_BYTES = 8_000_000
GROUP_ID = re.compile(r"b[0-9]{4}-g[0-9]{4}\Z")
BATCH_ID = re.compile(r"b[0-9]{4}\Z")


def confined(root: Path, path: str, *, must_exist: bool = True) -> Path:
    if not isinstance(path, str) or not path.strip() or "\\" in path:
        raise ValueError("Invalid path")
    relative = Path(path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"Workspace path traversal: {path!r}")
    current = root
    for component in relative.parts:
        current = current / component
        if current.is_symlink():
            raise ValueError(f"Refusing symlink: {path}")
    resolved = current.resolve(strict=must_exist)
    if not resolved.is_relative_to(root):
        raise ValueError("Path leaves workspace")
    return resolved


def read_json(root: Path, path: str, *, max_bytes: int = MAX_JSON_BYTES) -> dict:
    file = confined(root, path)
    if not file.is_file() or file.stat().st_size > max_bytes:
        raise ValueError(f"Missing/oversized JSON: {path}")
    payload = json.loads(file.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def source(root: Path, path: str, cache: dict) -> tuple[list[str], str]:
    if path not in cache:
        file = confined(root, path)
        if (not file.is_file() or file.suffix.casefold() not in {".md", ".markdown"}
                or file.stat().st_size > MAX_DOCUMENT_BYTES):
            raise ValueError(f"Invalid Markdown source: {path}")
        raw = file.read_bytes()
        cache[path] = (raw.decode("utf-8-sig").splitlines(keepends=True),
                       hashlib.sha256(raw).hexdigest())
    return cache[path]


def make_golden(root: Path, group: dict, draft: dict, review: dict, cache: dict) -> dict | None:
    gid = group.get("id")
    if (not isinstance(gid, str) or not GROUP_ID.fullmatch(gid)
            or draft.get("group_id") != gid or review.get("group_id") != gid):
        raise ValueError(f"Group identity mismatch: {gid!r}")
    if draft.get("status") != "ok" or review.get("status") != "accepted":
        return None
    checks = review.get("checks")
    if (not isinstance(checks, dict)
            or set(checks) != {"grounded", "both_documents_necessary",
                              "unambiguous", "no_source_leakage"}
            or not all(v is True for v in checks.values())):
        return None
    text = draft.get("question")
    answer = draft.get("expected_output")
    if (not isinstance(text, str) or not 10 <= len(text.strip()) <= 500
            or not isinstance(answer, str) or not 10 <= len(answer.strip()) <= 1800
            or draft.get("category") != "multi_document"):
        return None
    declared = group.get("sources")
    if not isinstance(declared, list) or not 2 <= len(declared) <= 3:
        return None
    allowed: dict[str, dict] = {}
    for d in declared:
        if not isinstance(d, dict):
            return None
        name, lo, hi = d.get("path"), d.get("start_line"), d.get("end_line")
        if (not isinstance(name, str) or type(lo) is not int or type(hi) is not int
                or lo < 1 or hi < lo or hi - lo > 500
                or name in allowed):
            return None
        allowed[name] = d
    if len(allowed) < 2:
        return None
    evidence = draft.get("evidence")
    if not isinstance(evidence, list) or not 2 <= len(evidence) <= 4:
        return None
    referenced_paths: set[str] = set()
    clean = []
    for e in evidence:
        if not isinstance(e, dict):
            return None
        path, quote, reason = e.get("path"), e.get("quote"), e.get("supports")
        lo, hi = e.get("start_line"), e.get("end_line")
        if (not isinstance(path, str) or path not in allowed
                or not isinstance(quote, str) or not 4 <= len(quote) <= 400
                or not isinstance(reason, str) or not 1 <= len(reason) <= 400
                or type(lo) is not int or type(hi) is not int
                or not allowed[path]["start_line"] <= lo <= hi <= allowed[path]["end_line"]):
            return None
        lines, digest = source(root, path, cache)
        if hi > len(lines):
            return None
        if quote not in "".join(lines[lo - 1:hi]):
            return None
        referenced_paths.add(path)
        clean.append({"path": path, "sha256": digest, "start_line": lo,
                      "end_line": hi, "quote": quote, "supports": reason})
    if len(referenced_paths) < 2:
        return None
    necessity = draft.get("necessity")
    if (not isinstance(necessity, dict)
            or not all(isinstance(necessity.get(k), str) and necessity[k].strip()
                       for k in ("without_first", "without_second"))):
        return None
    return {
        "id": gid, "input": text.strip(), "expected_output": answer.strip(),
        "category": "multi_document", "difficulty": draft.get("difficulty", "hard"),
        "topic": group.get("topic", ""), "relationship": group.get("relation", ""),
        "sources": [{"path": p, "sha256": source(root, p, cache)[1],
                     "start_line": allowed[p]["start_line"],
                     "end_line": allowed[p]["end_line"]}
                    for p in sorted(referenced_paths)],
        "evidence": clean, "necessity": necessity,
        "review": {"status": "accepted", "reason": review.get("reason", "")},
    }


def export(root: Path, output_dir: str = "rag-goldens") -> dict:
    root = root.resolve(strict=True)
    # Normalize equivalent spellings (./rag-goldens, rag-goldens/).
    output = confined(root, output_dir, must_exist=False)
    directory = output.relative_to(root).as_posix()
    if directory == ".":
        raise ValueError("Refusing to write benchmark files to workspace root")
    manifest = read_json(
        root, f"{directory}/state/topics/registry-batches.json",
        max_bytes=MAX_REGISTRY_MANIFEST_BYTES,
    )
    batches = manifest.get("batches")
    if not isinstance(batches, list) or len(batches) > 1000:
        raise ValueError("Missing or malformed registry batch manifest")
    batch_ids: list[str] = []
    # Source statuses are retained in the deterministic batch artifact.
    # Do not trust the final LLM to carry needs_attention through unchanged.
    upstream_incomplete: set[str] = set()
    upstream_warnings: list[str] = []
    for batch in batches:
        if not isinstance(batch, dict):
            raise ValueError("Malformed registry batch entry")
        # Independently enforce the same per-batch byte budget as the
        # flow's deterministic batch operation. Aggregate growth is
        # permitted, but individual model inputs must remain bounded.
        batch_size = len(json.dumps(
            batch, ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8"))
        if batch_size > MAX_REGISTRY_BATCH_BYTES:
            raise ValueError("Oversized registry input batch")
        bid = batch.get("id")
        if not isinstance(bid, str) or not BATCH_ID.fullmatch(bid):
            raise ValueError("Invalid registry batch ID")
        if bid in batch_ids:
            raise ValueError("Duplicate registry batch ID")
        batch_ids.append(bid)
        items = batch.get("items")
        if not isinstance(items, list):
            raise ValueError(f"Invalid registry input items in {bid}")
        for position, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                raise ValueError(f"Invalid registry input item in {bid}")
            status = item.get("status")
            if status not in {"ok", "needs_attention"}:
                raise ValueError(f"Invalid upstream coverage status in {bid}")
            warnings = item.get("warnings", [])
            if not isinstance(warnings, list) or any(
                not isinstance(w, str) for w in warnings
            ):
                raise ValueError(f"Invalid upstream warnings in {bid}")
            if status == "needs_attention" or warnings:
                upstream_incomplete.add(bid)
                if len(upstream_warnings) < 32:
                    label = f"{bid} input {position}"
                    reason = "; ".join(warnings[:3])
                    upstream_warnings.append(
                        f"{label}: {reason[:320]}" if reason
                        else f"{label}: incomplete coverage"
                    )

    # Validate and load ALL registry shards before writing any benchmark file.
    # A missing shard must not be interpreted as a legitimate empty benchmark.
    groups: list[dict] = []
    statuses: list[str] = []
    for bid in batch_ids:
        registry = read_json(root, f"{directory}/state/topics/registry-{bid}.json")
        if registry.get("status") not in {"ok", "needs_attention"}:
            raise ValueError(f"Invalid registry status in batch {bid}")
        local = registry.get("groups")
        if not isinstance(local, list) or len(local) > 15:
            raise ValueError(f"Invalid group list in batch {bid}")
        for group in local:
            if not isinstance(group, dict):
                raise ValueError(f"Non-object group in batch {bid}")
            gid = group.get("id")
            if not isinstance(gid, str) or not GROUP_ID.fullmatch(gid):
                raise ValueError(f"Invalid group ID: {gid!r}")
            if not gid.startswith(f"{bid}-"):
                raise ValueError(f"Group belongs to wrong registry batch: {gid}")
        groups.extend(local)
        statuses.append(registry["status"])
    if len({group["id"] for group in groups}) != len(groups):
        raise ValueError("Duplicate group IDs across registry batches")

    stats = Counter()
    cache: dict = {}
    result: list[dict] = []
    dedup: set[str] = set()
    for group in groups:
        gid = group["id"]
        draft_path = f"{directory}/state/draft-{gid}.json"
        review_path = f"{directory}/state/review-{gid}.json"
        if not confined(root, draft_path, must_exist=False).is_file() or not confined(
                root, review_path, must_exist=False).is_file():
            stats["missing"] += 1
            continue
        draft, review = read_json(root, draft_path), read_json(root, review_path)
        stats["reviewed"] += 1
        golden = make_golden(root, group, draft, review, cache)
        if golden is None:
            stats["rejected"] += 1
            continue
        normalized = " ".join(golden["input"].casefold().split())
        if normalized in dedup:
            stats["duplicates"] += 1
            continue
        dedup.add(normalized)
        result.append(golden)
    output.mkdir(parents=True, exist_ok=True)
    result.sort(key=lambda x: x["id"])
    for name, payload in (
        ("goldens.json", result),
        ("deepeval-goldens.json", [
            {"input": g["input"], "expected_output": g["expected_output"],
             "context": [item["quote"] for item in g["evidence"]]}
            for g in result
        ]),
    ):
        file = confined(root, f"{directory}/{name}", must_exist=False)
        file.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    return {"accepted": len(result), "total_groups": len(groups),
            "registry_count": len(batch_ids),
            "registry_status": (
                "needs_attention"
                if upstream_incomplete or "needs_attention" in statuses
                else "ok"
            ),
            "upstream_incomplete_batches": len(upstream_incomplete),
            "upstream_warnings": upstream_warnings,
            **dict(stats)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--output-dir", default="rag-goldens")
    args = parser.parse_args()
    print(json.dumps(export(Path(args.workspace), args.output_dir), indent=2))


if __name__ == "__main__":
    main()
