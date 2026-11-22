"""Strictly validate reviewed, merged and completed Phase-B trees."""
from __future__ import annotations

import json
from pathlib import Path

from migrate_v3 import safe_path
from phase_a_contract import checked_phase_a, digest
from refine_b import B_SCHEMA


def checked_b(
    workspace: Path, *, root: str, stage: str,
    phase_a: str = "okf-v4/phase-a",
) -> tuple[dict, dict, Path]:
    workspace = workspace.resolve()
    marker_name = {"B-draft": "draft.json", "B-merged": "merged.json",
                   "B": "phase-b.json"}.get(stage)
    if marker_name is None:
        raise ValueError(f"Unknown B stage: {stage}")
    base = safe_path(workspace, root + "/.placeholder", must_exist=False).parent
    marker = json.loads(safe_path(workspace, root + "/" + marker_name).read_text(encoding="utf-8"))
    raw_catalog = safe_path(workspace, root + "/catalog.json").read_bytes()
    catalog = json.loads(raw_catalog)
    if (marker.get("schema") != B_SCHEMA or catalog.get("schema") != B_SCHEMA
            or marker.get("catalog_sha256") != digest(raw_catalog)
            or catalog.get("stage") != stage):
        raise ValueError(f"Invalid or stale Phase-{stage} catalog/marker")
    _, original, original_root = checked_phase_a(workspace, phase_a)
    if catalog.get("origin_phase_a_sha256") != digest((original_root / "phase-a.json").read_bytes()):
        raise ValueError("Phase B was created against a different A snapshot.")
    docs, concepts = catalog.get("documents"), catalog.get("concepts")
    if not isinstance(docs, list) or not isinstance(concepts, list) or not concepts:
        raise ValueError("Malformed Phase-B corpus.")
    original_ids = {c["id"]: c for c in original["concepts"]}
    orig_items = {x["id"]: x for c in original["concepts"] for x in c["knowledge_items"]}
    current_items = {}
    ids = set()
    paths = set()
    docs_seen = set()
    actual_sources = set()
    for doc in docs:
        if doc.get("id") in docs_seen:
            raise ValueError("Duplicate B document.")
        docs_seen.add(doc["id"])
        source = safe_path(workspace, root + "/" + doc["source_snapshot"])
        if digest(source.read_bytes()) != doc["sha256"]:
            raise ValueError("B source snapshot differs from A.")
        actual_sources.add(doc["source_snapshot"])
        original_doc = next((d for d in original["documents"] if d["id"] == doc["id"]), None)
        if original_doc is None or doc["source_snapshot"] != original_doc["source_snapshot"]:
            raise ValueError("B has unexpected source document.")
    if docs_seen != {d["id"] for d in original["documents"]}:
        raise ValueError("B dropped a source document.")
    for c in concepts:
        cid, path, doc_id = c.get("id"), c.get("path"), c.get("document_id")
        if (not isinstance(cid,str) or cid in ids or not isinstance(path,str)
                or path.casefold() in paths or not path.endswith(".md")
                or path.lower().endswith("/index.md")
                or not path.startswith(f"doctrines/{doc_id}/")
                or doc_id not in docs_seen):
            raise ValueError("B concept identity/path collision.")
        ids.add(cid)
        paths.add(path.casefold())
        content = safe_path(workspace, root + "/" + path).read_bytes()
        if digest(content) != c["sha256"]:
            raise ValueError(f"Modified B concept: {path}")
        for x in c.get("knowledge_items", []):
            kid = x.get("id") if isinstance(x,dict) else None
            if not isinstance(kid,str) or kid in current_items:
                raise ValueError("Duplicate/invalid B source item.")
            current_items[kid] = x
        if [x["id"] for x in c["knowledge_items"]] != c.get("knowledge_item_ids"):
            raise ValueError("B Knowledge-Item order/identity differs.")
    if current_items != orig_items:
        raise ValueError("B discarded or altered the source-derived Knowledge Items.")
    current_paths={c["path"] for c in concepts}
    retired=catalog.get("retired_paths",{})
    if (not isinstance(retired,dict)
            or any(not isinstance(old,str) or not isinstance(new,str)
                   or old in current_paths or new not in current_paths
                   or not old.startswith("doctrines/") or old.endswith("/index.md")
                   for old,new in retired.items())):
        raise ValueError("Invalid retired concept path mapping.")
    aliases=catalog.get("aliases",{})
    if (not isinstance(aliases,dict)
            or any(not isinstance(old,str) or new not in ids
                   for old,new in aliases.items())):
        raise ValueError("Invalid concept ID alias mapping.")
    for doc in docs:
        if set(doc.get("concept_ids",[])) != {c["id"] for c in concepts if c["document_id"]==doc["id"]}:
            raise ValueError("B source document concept membership inconsistent.")
    if marker.get("knowledge_item_count") != len(orig_items) or marker.get("concept_count") != len(concepts):
        raise ValueError("B marker totals incorrect.")
    allowed = {"catalog.json",marker_name,*actual_sources,*(c["path"] for c in concepts)}
    if stage == "B":
        allowed.add("inventory.json")
        raw = safe_path(workspace, root + "/inventory.json").read_bytes()
        if digest(raw) != marker.get("inventory_sha256"):
            raise ValueError("Final B inventory checksum mismatch.")
        inventory = json.loads(raw)
        if inventory.get("schema") != "okf.inventory.v1":
            raise ValueError("Final B inventory has wrong schema.")
        entries = inventory.get("concepts", [])
        if (not isinstance(entries,list)
                or any(not isinstance(entry,dict) for entry in entries)
                or {entry.get("id") for entry in entries} != ids
                or len(entries)!=len(ids)):
            raise ValueError("Final B inventory is incomplete.")
        final_by_id={c["id"]:c for c in concepts}
        for entry in entries:
            entity=final_by_id[entry["id"]]
            for field in ("id","path","title","summary","tags","sha256",
                          "document_id","knowledge_item_ids","source_path"):
                if entry.get(field)!=entity.get(field):
                    raise ValueError(
                        f"Final B inventory field {field} disagrees with the "
                        f"verified concept {entity['id']}"
                    )
    actual = set()
    for file in base.rglob("*"):
        if file.is_symlink() or (hasattr(file,"is_junction") and file.is_junction()):
            raise ValueError("Phase B contains symlinks/junctions.")
        if file.is_file():
            actual.add(file.relative_to(base).as_posix())
    if allowed != actual:
        raise ValueError(f"B tree contains unexpected/missing files: {sorted(actual ^ allowed)[:12]}")
    return marker,catalog,base
