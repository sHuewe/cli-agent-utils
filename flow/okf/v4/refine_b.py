"""Shared validation and deterministic, coverage-preserving Phase-B refinement.

Only LLM JSON review outputs may request edits. Python creates files,
assigns stable IDs and validates unchanged knowledge-item provenance.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import posixpath
import re
import shutil
import tempfile
from typing import Any

from migrate_v3 import safe_path, slugify, title_from_frontmatter
from phase_a_contract import checked_phase_a

B_SCHEMA = "okf.phase-b.v1"
B_INVENTORY = "okf.inventory.v1"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def encode(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def snapshot(workspace: Path, target_name: str, files: dict[str, bytes], marker: str) -> None:
    """Atomically replace a generated, validated tree without altering inputs."""
    root = safe_path(workspace, target_name + "/.placeholder", must_exist=False).parent
    if root.exists():
        if root.is_symlink() or not (root / marker).is_file():
            raise ValueError("Refusing to overwrite a different output tree.")
        for item in root.rglob("*"):
            if item.is_symlink() or (hasattr(item, "is_junction") and item.is_junction()):
                raise ValueError("Existing output tree has a symlink/junction.")
    root.parent.mkdir(parents=True, exist_ok=True)
    backup = root.with_name("." + root.name + ".previous")
    if backup.exists() or backup.is_symlink():
        raise ValueError("Previous output backup still exists.")
    staging = Path(tempfile.mkdtemp(prefix=".phase-b-", dir=root.parent))
    try:
        for name, content in files.items():
            if not isinstance(content, bytes):
                raise ValueError("Output content must be bytes.")
            dest = staging.joinpath(*name.split("/"))
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(content)
        found = {x.relative_to(staging).as_posix() for x in staging.rglob("*") if x.is_file()}
        if found != set(files):
            raise ValueError("Generated tree is incomplete.")
        prior = root.exists()
        if prior:
            os.replace(root, backup)
        try:
            os.replace(staging, root)
        except BaseException:
            if prior:
                os.replace(backup, root)
            raise
        if prior:
            shutil.rmtree(backup)
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def inventory_tasks(catalog: dict, root: str) -> dict:
    items = []
    used = set()
    source_hashes={doc["id"]: doc["sha256"] for doc in catalog["documents"]}
    for c in sorted(catalog["concepts"], key=lambda x: x["path"]):
        if c["document_id"] not in source_hashes:
            raise ValueError("Inventory concept has no source document.")
        # The LLM reviews the whole assignment, not only Markdown.
        # Any change to the source snapshot, content, identity, planned
        # title or complete Knowledge Item payload invalidates checkpoints.
        payload={
            "id":c["id"],"path":c["path"],"title":c["title"],
            "concept_sha256":c["sha256"],
            "source_sha256":source_hashes[c["document_id"]],
            "source_path":c["source_path"],
            "knowledge_item_ids":c["knowledge_item_ids"],
            "knowledge_items":c["knowledge_items"],
        }
        signature=sha(json.dumps(
            payload,sort_keys=True,ensure_ascii=False,separators=(",",":")
        ).encode("utf-8"))[:20]
        key = c["id"].replace(":", "--") + "--" + signature
        if not re.fullmatch(r"[a-z0-9_-]+", key) or key in used:
            raise ValueError("Invalid/duplicate concept inventory checkpoint key.")
        used.add(key)
        items.append({
            "id": c["id"], "key": key, "title": c["title"],
            "path": root + "/" + c["path"],
            "source": root + "/" + c["source_path"],
            "knowledge_item_count": len(c["knowledge_item_ids"]),
            "knowledge_items": c["knowledge_items"],
        })
    return {"schema": "okf.inventory-tasks.v1", "status": "ok",
            "count": len(items), "concepts": items}


def validate_tasks(tasks: Any, catalog: dict, root: str) -> list[dict]:
    expected = inventory_tasks(catalog, root)
    if not isinstance(tasks, dict) or tasks != expected:
        raise ValueError("Inventory tasks do not match the source catalog/content.")
    return expected["concepts"]


def summary(workspace: Path, state: str, item: dict) -> dict:
    value = json.loads(safe_path(
        workspace, f"{state}/summaries/{item['key']}.json"
    ).read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("id") != item["id"]:
        raise ValueError("Missing or mismatched concept inventory summary.")
    return _semantic(value, item["id"])


def _semantic(value: dict, expected_id: str) -> dict:
    title = value.get("summary")
    tags = value.get("tags")
    if value.get("id", expected_id) != expected_id or not isinstance(title, str) or not 20 <= len(title.strip()) <= 600:
        raise ValueError(f"Invalid LLM summary for {expected_id}")
    if not isinstance(tags, list) or not 1 <= len(tags) <= 5:
        raise ValueError(f"Invalid LLM tags for {expected_id}")
    normalized = set()
    cleaned = []
    for tag in tags:
        if not isinstance(tag, str) or not 2 <= len(tag.strip()) <= 80:
            raise ValueError(f"Invalid LLM tag for {expected_id}")
        name = slugify(tag.strip())
        if name not in normalized:
            normalized.add(name)
            cleaned.append(tag.strip())
    return {"summary": title.strip(), "tags": cleaned}


def markdown(title: str, body: str) -> bytes:
    if not isinstance(body, str) or not 70 <= len(body.encode("utf-8")) <= 250_000:
        raise ValueError("LLM revision must contain a substantive bounded Markdown document.")
    if not body.startswith("---\n"):
        raise ValueError("Replacement must begin with YAML frontmatter.")
    lines=body.splitlines()
    try:
        closing=lines.index("---", 1)
    except ValueError as exc:
        raise ValueError("Replacement frontmatter requires a closing --- delimiter.") from exc
    if closing < 2 or closing >= len(lines) - 1:
        raise ValueError("Replacement needs frontmatter and substantive body.")
    metadata=lines[1:closing]
    types=[re.fullmatch(r"type:\\s*([A-Za-z][A-Za-z0-9_-]*)\\s*",line)
           for line in metadata if re.match(r"^type\\s*:",line)]
    if len(types) != 1 or types[0] is None:
        raise ValueError("Replacement frontmatter requires one nonempty scalar type.")
    if title_from_frontmatter(body) != title:
        raise ValueError("LLM revision frontmatter title does not match the chosen title.")
    if "/index.md" in body or "\x00" in body:
        raise ValueError("Revised concept contains forbidden navigation/null bytes.")
    return body.encode("utf-8")


def _unit(original: dict, ident: str, title: str, body: bytes, item_ids: list[str], semantic: dict) -> dict:
    all_items = {x["id"]: x for x in original["knowledge_items"]}
    if not item_ids or any(i not in all_items for i in item_ids) or len(item_ids) != len(set(item_ids)):
        raise ValueError("Revised concept contains missing or duplicate source Knowledge Items.")
    result = dict(original)
    result["id"] = ident
    result["title"] = title
    result["knowledge_item_ids"] = item_ids
    result["knowledge_items"] = [all_items[i] for i in item_ids]
    # Preserve exact source-bound evidence instead of trusting LLM to alter it.
    result["evidence_ranges"] = [
        value for x in result["knowledge_items"]
        for value in x.get("evidence_ranges", [])
    ]
    result["sha256"] = sha(body)
    result["summary"] = semantic["summary"]
    result["tags"] = semantic["tags"]
    return result


def apply_quality(
    workspace: Path, *, phase_a: str, state: str, tasks: dict,
    destination: str,
) -> dict:
    marker, catalog, base = checked_phase_a(workspace, phase_a)
    entries = validate_tasks(tasks, catalog, phase_a)
    files: dict[str, bytes] = {}
    next_concepts: list[dict] = []
    old_to_primary: dict[str, str] = {}
    allocated: set[str] = set()
    old_knowledge: dict[str, dict] = {}
    for c in catalog["concepts"]:
        for ki in c["knowledge_items"]:
            if ki["id"] in old_knowledge:
                raise ValueError("Duplicate source Knowledge Item before quality stage.")
            old_knowledge[ki["id"]] = ki

    for item in entries:
        original = next(c for c in catalog["concepts"] if c["id"] == item["id"])
        initial = summary(workspace, state, item)
        review = json.loads(safe_path(
            workspace, f"{state}/reviews/{item['key']}.json"
        ).read_text(encoding="utf-8"))
        if not isinstance(review, dict) or review.get("id") != item["id"]:
            raise ValueError(f"Missing/mismatched quality review: {item['id']}")
        action, parts = review.get("action"), review.get("parts")
        if action not in ("keep", "rewrite", "split") or not isinstance(parts, list):
            raise ValueError(f"Invalid quality action: {item['id']}")
        if action == "keep":
            if parts:
                raise ValueError("Keep review must not provide replacement parts.")
            body = (base / original["path"]).read_bytes()
            records = [(original["id"], original["title"], original["path"],
                        body, list(original["knowledge_item_ids"]), initial)]
        else:
            if (action == "rewrite" and len(parts) != 1) or (action == "split" and not 2 <= len(parts) <= 8):
                raise ValueError("Rewrite must have one part; split requires 2–8 parts.")
            covered = [i for part in parts for i in part.get("knowledge_item_ids", [])] if all(isinstance(p, dict) for p in parts) else []
            if (len(covered) != len(set(covered))
                    or set(covered) != set(original["knowledge_item_ids"])):
                raise ValueError("Quality review lost or duplicated source Knowledge Items.")
            records = []
            for n, part in enumerate(parts):
                title = part.get("title")
                if not isinstance(title, str) or not title.strip():
                    raise ValueError("Missing quality part title.")
                if n == 0 and title != original["title"]:
                    raise ValueError("Primary concept must retain its title and descriptive path.")
                body = markdown(title, part.get("markdown"))
                sem = _semantic(part, original["id"])
                ident = original["id"] if n == 0 else f"{original['id']}--p{n+1:02d}"
                # Preserve the original ID/path on the first child so existing
                # references survive split and rewrite. New children get slugs.
                path = original["path"] if n == 0 else (
                    posixpath.dirname(original["path"]) + "/" + slugify(title) + ".md"
                )
                records.append((ident, title, path, body, part["knowledge_item_ids"], sem))
        for ident, title, path, body, ids, semantic in records:
            if path.casefold() in allocated or path.endswith("/index.md"):
                raise ValueError("Quality split/rewrite introduced a path collision.")
            allocated.add(path.casefold())
            files[path] = body
            entity = _unit(original, ident, title, body, ids, semantic)
            entity["path"] = path
            entity["origin_id"] = original["id"]
            next_concepts.append(entity)
        old_to_primary[original["id"]] = original["id"]

    new_knowledge = {ki["id"]: ki for c in next_concepts for ki in c["knowledge_items"]}
    if old_knowledge != new_knowledge or sum(len(c["knowledge_items"]) for c in next_concepts) != len(old_knowledge):
        raise ValueError("Quality phase violated source Knowledge Item coverage/content.")
    for doc in catalog["documents"]:
        data = (base / doc["source_snapshot"]).read_bytes()
        files[doc["source_snapshot"]] = data
    result = {
        "schema": B_SCHEMA, "stage": "B-draft",
        "origin_phase_a_sha256": sha((base / "phase-a.json").read_bytes()),
        "documents": [
            {**doc, "concept_ids": [c["id"] for c in next_concepts if c["document_id"] == doc["id"]]}
            for doc in catalog["documents"]
        ],
        "concepts": next_concepts,
        "aliases": old_to_primary,
    }
    files["catalog.json"] = encode(result)
    files["draft.json"] = encode({
        "schema": B_SCHEMA, "status": "reviewed",
        "catalog_sha256": sha(files["catalog.json"]),
        "concept_count": len(next_concepts),
        "knowledge_item_count": len(old_knowledge),
    })
    snapshot(workspace, destination, files, "draft.json")
    return {"status": "ok", "draft": destination, "concept_count": len(next_concepts),
            "reviewed_concepts": len(entries), "split_children": len(next_concepts) - len(entries)}
