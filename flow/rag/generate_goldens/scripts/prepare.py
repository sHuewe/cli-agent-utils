#!/usr/bin/env python3
"""Deterministically prepare small cross-document evidence packs for an RAG benchmark.

No LLM or RAG retrieval is used here. Requires Python 3.11+ only.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any

STOP = set("""
aber als also auch auf aus bei bis das dass dem den der des die dies diese
ein eine einem einen einer eines für fuer hat im in ist mit nach nicht oder
sich sie sind so über ueber um und unter von vor war was wenn werden wie wird
zu zum zur the and for from into with this that are were have has not can
its their these those which when where while about used using such than
""".split())
TOKEN = re.compile(r"[^\W_][\w-]{2,}", re.UNICODE)
MAX_FILE_BYTES = 8_000_000
MAX_TOTAL_WINDOWS = 1500
MAX_WINDOWS_PER_DOC = 80
MAX_DOCS = 300
PACK_VERSION = 1


def words(value: str) -> set[str]:
    return {w for w in TOKEN.findall(value.casefold())
            if len(w) >= 3 and w not in STOP and not w.isnumeric()}


def secure_path(workspace: Path, value: str, *, must_exist: bool = True) -> Path:
    path = Path(value)
    if path.is_absolute() or not value or ".." in path.parts or "\\" in value:
        raise ValueError(f"Unsafe workspace-relative path: {value!r}")
    candidate = workspace
    for part in path.parts:
        candidate = candidate / part
        if candidate.is_symlink():
            raise ValueError(f"Symlinks are not supported: {candidate}")
    resolved = candidate.resolve(strict=must_exist)
    if not resolved.is_relative_to(workspace):
        raise ValueError("Path escapes workspace")
    return resolved


def source_windows(workspace: Path, source_dir: str, max_chars: int) -> tuple[list[dict], dict]:
    root = secure_path(workspace, source_dir)
    if not root.is_dir():
        raise ValueError(f"Source directory not found: {root}")
    docs: dict[str, str] = {}
    windows: list[dict] = []
    for p in sorted(root.rglob("*")):
        if p.is_symlink():
            raise ValueError(f"Symlink in source corpus: {p}")
        if not p.is_file() or p.suffix.lower() not in {".md", ".markdown"}:
            continue
        if any(part.startswith(".") for part in p.relative_to(root).parts):
            continue
        if p.name.casefold() == "index.md":
            continue
        if p.stat().st_size > MAX_FILE_BYTES:
            raise ValueError(f"File exceeds 8 MB: {p}")
        rel = p.relative_to(workspace).as_posix()
        raw = p.read_bytes()
        doc_hash = hashlib.sha256(raw).hexdigest()
        lines = raw.decode("utf-8-sig").splitlines(keepends=True)
        docs[rel] = doc_hash
        if len(docs) > MAX_DOCS:
            raise ValueError(f"More than {MAX_DOCS} documents; partition the corpus")
        current: list[str] = []
        start = 1

        def emit(end: int) -> None:
            if not current:
                return
            value = "".join(current)
            if len(words(value)) < 8:
                return
            windows.append({
                "path": rel, "sha256": doc_hash,
                "start_line": start, "end_line": end,
                "text": value, "tokens": words(value),
            })

        for line_no, line in enumerate(lines, start=1):
            if len(line) > max_chars:
                raise ValueError(f"Single source line exceeds max window: {rel}:{line_no}")
            if current and sum(map(len, current)) + len(line) > max_chars:
                emit(line_no - 1)
                current = []
                start = line_no
            current.append(line)
        emit(len(lines))
        if sum(1 for w in windows if w["path"] == rel) > MAX_WINDOWS_PER_DOC:
            raise ValueError(f"Document needs >{MAX_WINDOWS_PER_DOC} windows: {rel}")
    if len(windows) > MAX_TOTAL_WINDOWS:
        raise ValueError(f"More than {MAX_TOTAL_WINDOWS} windows; partition the corpus")
    if len(docs) < 2:
        raise ValueError("At least two different Markdown source documents are required")
    return windows, docs


def similarity_pairs(windows: list[dict], *, threshold: float) -> list[tuple[float, int, int]]:
    df: Counter[str] = Counter()
    for w in windows:
        df.update(w["tokens"])
    total = len(windows)
    idf = {term: math.log((1 + total) / (1 + count)) + 1 for term, count in df.items()}
    weights = [{token: idf[token] for token in w["tokens"]} for w in windows]
    norms = [math.sqrt(sum(v * v for v in vec.values())) for vec in weights]
    candidates = []
    for i, first in enumerate(windows):
        for j in range(i + 1, len(windows)):
            second = windows[j]
            if first["path"] == second["path"]:
                continue
            overlap = first["tokens"] & second["tokens"]
            if len(overlap) < 3:
                continue
            score = sum(idf[t] ** 2 for t in overlap) / (norms[i] * norms[j])
            if score >= threshold:
                candidates.append((round(score, 8), i, j))
    return sorted(candidates, key=lambda x: (-x[0], windows[x[1]]["path"],
                                           windows[x[2]]["path"], x[1], x[2]))


def prepare(workspace: Path, source_dir: str, pack_dir: str,
            max_packs: int, max_chars: int, threshold: float) -> dict:
    windows, docs = source_windows(workspace, source_dir, max_chars)
    pairs = similarity_pairs(windows, threshold=threshold)
    selected = []
    doc_pair_uses: Counter[tuple[str, str]] = Counter()
    window_uses: Counter[int] = Counter()
    for score, i, j in pairs:
        a, b = windows[i], windows[j]
        doc_pair = tuple(sorted([a["path"], b["path"]]))
        if doc_pair_uses[doc_pair] >= 3 or window_uses[i] >= 2 or window_uses[j] >= 2:
            continue
        selected.append((score, [i, j]))
        doc_pair_uses[doc_pair] += 1
        window_uses[i] += 1
        window_uses[j] += 1
        if len(selected) >= max_packs:
            break
    if not selected:
        raise ValueError("No sufficiently related cross-document passages found. "
                         "Try --min-similarity 0.08 or inspect the corpus.")
    out_dir = secure_path(workspace, pack_dir, must_exist=False)
    out_dir.mkdir(parents=True, exist_ok=True)
    active: set[str] = set()
    for score, indexes in selected:
        sources = []
        for count, index in enumerate(indexes, 1):
            win = windows[index]
            sources.append({
                "id": f"s{count}", "path": win["path"], "sha256": win["sha256"],
                "start_line": win["start_line"], "end_line": win["end_line"],
                "text": win["text"],
            })
        fingerprint = json.dumps(
            [(s["path"], s["sha256"], s["start_line"], s["end_line"]) for s in sources],
            ensure_ascii=False, separators=(",", ":"),
        )
        pack_id = "p" + hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:16]
        pack = {"version": PACK_VERSION, "pack_id": pack_id,
                "similarity": score, "sources": sources}
        name = f"pack-{pack_id}.json"
        encoded = (json.dumps(pack, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        if len(encoded) > 12000:
            raise ValueError(f"Pack exceeds 12 KB, reduce --max-window-chars: {name}")
        (out_dir / name).write_bytes(encoded)
        active.add(name)
    for old in out_dir.glob("pack-*.json"):
        if old.name not in active:
            old.unlink()
    manifest = {"version": PACK_VERSION, "source_dir": source_dir,
                "sources": docs, "window_count": len(windows),
                "pack_count": len(active), "pack_ids": sorted(active)}
    manifest_path = out_dir.parent / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
    return {"documents": len(docs), "windows": len(windows),
            "packs": len(active), "manifest": str(manifest_path.relative_to(workspace))}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--source-dir", default="doctrines")
    parser.add_argument("--pack-dir", default="rag-goldens/packs")
    parser.add_argument("--max-packs", type=int, default=24)
    parser.add_argument("--max-window-chars", type=int, default=2400)
    parser.add_argument("--min-similarity", type=float, default=0.12)
    args = parser.parse_args()
    if not 1 <= args.max_packs <= 1000:
        parser.error("--max-packs must be between 1 and 1000")
    if not 500 <= args.max_window_chars <= 3000:
        parser.error("--max-window-chars must be between 500 and 3000")
    if not 0 < args.min_similarity < 1:
        parser.error("--min-similarity must be between 0 and 1")
    workspace = Path(args.workspace).resolve(strict=True)
    print(json.dumps(prepare(workspace, args.source_dir, args.pack_dir,
                             args.max_packs, args.max_window_chars,
                             args.min_similarity), indent=2))


if __name__ == "__main__":
    main()
